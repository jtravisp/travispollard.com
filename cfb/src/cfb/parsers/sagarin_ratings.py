"""Parse section 1 of Jeff Sagarin's college football ratings page.

The page (http://sagarin.com/sports/cfsend.htm) is fixed-width text inside a
``<pre>`` block and has three sections: teams by rating, conference averages, then
teams grouped by conference. **Section 3 reprints every team**, byte-identical, so
a whole-page parse returns all 266 teams twice and reports no error at all. Only
section 1 is parsed here.

Section boundaries, the part that is easy to get wrong:

* The literal ``CONFERENCE AVERAGES`` occurs exactly **once** on the real page, in
  the intro legend *above* section 1. Stopping at it returns zero teams.
* Section 1 starts at the first ratings header block -- identified by the
  ``HOME ADVANTAGE=[`` line, whose bracketed form is unique to the ratings header
  (the predictions header prints the same numbers bare).
* Section 1 ends at the rule of underscores that follows the last rank. Everything
  after it -- the UNRATED sentinel's own header block, the conference table, the
  section-3 reprints -- is out of scope for this module.

Rows are matched against the full column schema and anchored on structural tokens:
the ``=`` after the division code and the ``|`` separators. Never split on
whitespace (``Texas A&M``, ``Hawai'i``, ``Central Florida(UCF)`` -- which has no
space before the paren) and never slice fixed columns, which move when a name grows.

Validation posture (``cfb/CLAUDE.md``, SPEC-phase0 section 4.5): a row that does not
conform is an alert, not a null. Nothing here returns ``None`` for a field, coerces
a missing value, or skips a row it did not recognise.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from cfb.errors import DuplicateRankError, ParseError
from cfb.models import TeamRating, validating

__all__ = [
    "HFA_COLUMNS",
    "parse_hfa",
    "parse_page_date_stamp",
    "parse_page_state",
    "parse_ratings",
    "parse_season",
]

#: The page prints five bracketed home-field values, one per rating column -- not
#: the four that end up in the manifest. They are identical on the 2026 preseason
#: capture but Sagarin states they vary during the season, so each is captured
#: separately, per snapshot. There is no default anywhere to fall back to.
HFA_COLUMNS = ("rating", "predictor", "golden_mean", "recent", "strong_recent")

# --- structural anchors ---------------------------------------------------

# The ratings header block, reprinted every 10 rows mid-table.
_TITLE_LINE = re.compile(r"^(?P<season>\d{4})\s+College Football\b(?P<rest>.*)$", re.IGNORECASE)
_COLUMN_HEADER = re.compile(r"^\s+RATING\s+W\s+L\s+SCHEDL\(RANK\)")
_HFA_HEADER = re.compile(r"^\s*HOME ADVANTAGE=\[")

# Only the ratings header brackets its home-field values; the predictions header
# prints the same numbers bare. Anchoring on the bracket picks out the ratings
# header alone.
_BRACKETED = re.compile(r"\[\s*(-?\d+\.\d+)\s*\]")

# Section 1 is closed by a rule of underscores after the last rank.
_RULE = re.compile(r"^_{20,}\s*$")

# ``\s*`` and ``.*?``, not ``\s+`` and ``.+?``: the phrase with an empty date after
# it has to *match* so it can be rejected. Requiring a non-empty stamp in the regex
# turns a truncated line into "no stamp here", which is the one answer this parser
# must never give a page that says it has one.
_DATE_STAMP = re.compile(r"through\s+games\s+of\b(?P<stamp>.*?)\s*$", re.IGNORECASE)

# Formats seen on in-season title lines. A stamp that parses under none of them is
# a format change, and a format change is an alert.
_DATE_FORMATS = ("%B %d, %Y", "%d %B %Y", "%Y %B %d", "%m/%d/%Y", "%B %d %Y")

# The real in-season page omits the year: the 2026-09-01 capture stamps itself
# "through games of August 29 Saturday". The year is not missing information --
# the same title line carries the season -- so these are parsed year-less and the
# year is supplied by ``_year_for``.
_DATE_FORMATS_NO_YEAR = ("%B %d", "%d %B")

# ...and it prints the weekday *after* the date, unseparated. A leading weekday
# with a comma has also been assumed; both are stripped, because the weekday is
# redundant with the date it decorates and pinning either position would make the
# parser fail on a page that merely moved it.
_WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
_TRAILING_WEEKDAY = re.compile(r",?\s+(?:" + _WEEKDAYS + r")$", re.IGNORECASE)
_LEADING_WEEKDAY = re.compile(r"^(?:" + _WEEKDAYS + r"),?\s+", re.IGNORECASE)

# A season spans the New Year. Sagarin's year-less stamp is read against the
# season on its own title line, so the 2026 page's "January 10" is 2027 and its
# "August 29" is 2026. July is the split: no college football is played in it, so
# no real stamp can land on the boundary itself.
_SEASON_ROLLOVER_MONTH = 7

# --- row shapes -----------------------------------------------------------

# Anything that opens like a rank in the rank column. Tells "this is a row and it
# is broken" (raise) apart from "this is not a row" (a reprinted header line).
_ROW_CANDIDATE = re.compile(r"^ {0,3}\d{1,3} {2}\S")

# Enough of a row to name it in an error message when the full match fails.
_ROW_HEAD = re.compile(r"^ {0,3}(?P<rank>\d{1,3}) {2}(?P<name>\S.*?) +(?P<division>A|AA|__) +=")

# The full section-1 column schema. Every field is matched, including the ones this
# module does not carry, so a shifted column is a parse failure rather than a
# plausible-looking wrong number.
_ROW = re.compile(
    r"^ {0,3}(?P<rank>\d{1,3}) {2}"
    r"(?P<name>\S.*?) +"
    r"(?P<division>A|AA|__) +=\s+"
    r"(?P<rating>-?\d+\.\d{2}) +"
    r"(?P<wins>\d+) +(?P<losses>\d+) +"
    r"-?\d+\.\d{2}\( *\d+\) +"  # schedule strength (rank)
    r"\d+ +\d+ +\| +"  # record vs top 10
    r"\d+ +\d+ +\| +"  # record vs top 30
    r"(?P<predictor>-?\d+\.\d{2}) +\d+ +\| +"
    r"(?P<golden_mean>-?\d+\.\d{2}) +\d+ +\| +"
    r"(?P<recent>-?\d+\.\d{2}) +\d+ +\| +"
    r"-?\d+\.\d{2} +\d+ +"  # STRONG RECENT and its rank
    r"(?P<conference>\S.*?) +\((?:A|AA|__)\)\s*$"
)

# Sits past section 1 under its own header block, with ``__`` where the division
# goes. Matched by name so that any *other* row carrying a non-team division is
# still an error rather than a silent skip.
_UNRATED_NAME = "***UNRATED***"


def _lines(text: str) -> list[str]:
    """Split on newlines only.

    ``str.splitlines`` also breaks on form feed and a handful of unicode
    separators. On a fixed-width page captured verbatim off the wire, a stray
    control byte must not silently become a line boundary.
    """
    return [line.rstrip("\r") for line in text.split("\n")]


def _section_one(text: str) -> list[tuple[int, str]]:
    """Return ``(line number, line)`` for section 1's body, reprinted headers included."""
    lines = _lines(text)

    start = next((i + 1 for i, line in enumerate(lines) if _HFA_HEADER.match(line)), None)
    if start is None:
        raise ParseError(
            "no ratings header found: expected a line matching 'HOME ADVANTAGE=[' above section 1"
        )

    end = next((i for i in range(start, len(lines)) if _RULE.match(lines[i])), None)
    if end is None:
        raise ParseError(
            f"section 1 opens at line {start} but is never closed by a rule of underscores; "
            "refusing to parse to end of page, which would swallow the conference table and "
            "the section-3 reprints"
        )

    return [(i + 1, lines[i]) for i in range(start, end)]


def _is_header(line: str) -> bool:
    """Is this one of the three header lines reprinted every 10 rows?"""
    return bool(_TITLE_LINE.match(line) or _COLUMN_HEADER.match(line) or _HFA_HEADER.match(line))


def _describe_bad_row(lineno: int, line: str) -> str:
    head = _ROW_HEAD.match(line)
    if head is not None:
        return (
            f"line {lineno}: rank {head['rank']} ({head['name']}) does not match the "
            f"section-1 column schema -- a field is missing or the columns have shifted: {line!r}"
        )
    return f"line {lineno}: unparseable section-1 row: {line!r}"


def parse_ratings(text: str) -> list[TeamRating]:
    """Parse section 1 into one :class:`TeamRating` per team, in published order.

    Raises :class:`~cfb.errors.DuplicateRankError` on a repeated rank and
    :class:`~cfb.errors.ParseError` on anything else that does not conform: a
    malformed row, an unrecognised line inside the section, a gap in the rank
    sequence, or an empty section.
    """
    teams: list[TeamRating] = []
    seen: dict[int, tuple[int, str]] = {}

    for lineno, raw in _section_one(text):
        line = raw.rstrip()
        if not line or _is_header(line):
            continue

        if not _ROW_CANDIDATE.match(line):
            raise ParseError(f"line {lineno}: unrecognised line inside section 1: {line!r}")

        row = _ROW.match(line)
        if row is None:
            raise ParseError(_describe_bad_row(lineno, line))

        name = row["name"]
        division = row["division"]
        if division not in ("A", "AA"):
            if name == _UNRATED_NAME:
                continue  # the sentinel, not a team
            raise ParseError(
                f"line {lineno}: {name!r} carries division {division!r}, which is neither a "
                f"team division nor the {_UNRATED_NAME} sentinel: {line!r}"
            )

        rank = int(row["rank"])
        if rank in seen:
            first_line, first_name = seen[rank]
            raise DuplicateRankError(
                f"rank {rank} is published twice in section 1: {first_name!r} at line "
                f"{first_line} and {name!r} at line {lineno}. Rank is the join key; a "
                f"duplicate makes it unusable."
            )
        seen[rank] = (lineno, name)

        with validating(f"line {lineno}: team rank {rank} ({name!r})"):
            teams.append(
                TeamRating(
                    rank=rank,
                    name=name,
                    rating=float(row["rating"]),
                    predictor=float(row["predictor"]),
                    golden_mean=float(row["golden_mean"]),
                    recent=float(row["recent"]),
                    division=division,
                    conference=row["conference"],
                    wins=int(row["wins"]),
                    losses=int(row["losses"]),
                )
            )

    if not teams:
        raise ParseError("section 1 contained no team rows")

    # Sagarin's ranks are dense. A gap means a row was dropped, which is the one
    # thing a lenient parser does silently.
    expected = list(range(1, len(teams) + 1))
    if sorted(seen) != expected:
        missing = sorted(set(expected) - set(seen))
        raise ParseError(
            f"section 1 ranks are not contiguous: parsed {len(teams)} teams, "
            f"missing rank(s) {missing}"
        )

    return teams


def parse_hfa(text: str) -> dict[str, float]:
    """Read the per-column home-field advantage out of the ratings header.

    Never hardcode this. Sagarin states it varies during the season and that the
    value in the output is the one to use; a constant silently degrades every
    prediction as the season progresses. The five columns are currently identical
    but can diverge, so each is carried separately.
    """
    for line in _lines(text):
        if not _HFA_HEADER.match(line):
            continue
        values = _BRACKETED.findall(line)
        if len(values) != len(HFA_COLUMNS):
            raise ParseError(
                f"ratings header carries {len(values)} bracketed home-field values, expected "
                f"{len(HFA_COLUMNS)} ({', '.join(HFA_COLUMNS)}): {line!r}"
            )
        return dict(zip(HFA_COLUMNS, (float(v) for v in values), strict=True))

    raise ParseError("no 'HOME ADVANTAGE=[...]' line found; home-field advantage has no default")


def _title(text: str) -> re.Match[str]:
    """The ratings-table title line: the line directly above the column header.

    Taken from the table rather than from the page's HTML heading, because this is
    the line that carries the in-season date stamp.
    """
    lines = _lines(text)
    for i, line in enumerate(lines):
        if not _COLUMN_HEADER.match(line):
            continue
        if i == 0:
            raise ParseError("ratings column header appears with no title line above it")
        title = lines[i - 1].strip()
        match = _TITLE_LINE.match(title)
        if match is None:
            raise ParseError(f"line {i}: unrecognised ratings title line: {title!r}")
        return match

    raise ParseError("no ratings column header found; cannot locate the title line")


def parse_season(text: str) -> int:
    """The season the page is for, from the ratings title line."""
    return int(_title(text)["season"])


def parse_page_state(text: str) -> Literal["preseason", "in-season"]:
    """``"preseason"`` while the title line says STARTING, otherwise ``"in-season"``.

    Preseason is a legal degenerate state, not an error: all four rating columns are
    identical, records are 0-0, and schedule strength is 0.00. It is flagged here so
    nothing downstream mistakes week-zero ratings for ratings that carry schedule
    information.
    """
    return "preseason" if "STARTING" in _title(text)["rest"].upper() else "in-season"


def parse_page_date_stamp(text: str) -> date | None:
    """The page's internal "through games of ..." stamp, or ``None``.

    ``None`` has exactly one meaning: **this page carries no stamp**. The preseason
    page is that case -- its title line is season and state, nothing else -- so the
    field is legitimately nullable and SPEC 4.6 has nothing to compare until the
    first in-season page lands.

    Everything else raises. A page that says "through games of" and then hands over
    something this parser cannot read is a format change, and returning ``None``
    for it would be indistinguishable downstream from the preseason case: the
    freshness check would skip the comparison, every run would stay green, and the
    source could stop updating for a month with nothing to show it. That is the
    failure mode this project is built to prevent, so the phrase being present is
    treated as the page's own claim that a date is here, and the parser either
    reads it or fails loudly.
    """
    title = _title(text)
    stamp = _DATE_STAMP.search(title["rest"])
    if stamp is None:
        return None

    found = " ".join(stamp["stamp"].split())
    if not found:
        raise ParseError(
            "page date stamp is empty: the title line carries 'through games of' with no "
            "date after it. The phrase is the page's claim that a date is here, so this is "
            "a truncated or changed page, not a page without a stamp"
        )

    # The weekday adds nothing the date does not already carry. The live page
    # trails it ("August 29 Saturday"); a leading one has also been assumed.
    bare = _TRAILING_WEEKDAY.sub("", _LEADING_WEEKDAY.sub("", found)).strip()

    for candidate in (found, bare):
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue

    # Year-less last, so a stamp that carries its own year is never overruled by
    # the season we would have inferred for it.
    season = int(title["season"])
    for candidate in (found, bare):
        for fmt in _DATE_FORMATS_NO_YEAR:
            parsed = _dated(candidate, fmt, season)
            if parsed is not None:
                return parsed

    raise ParseError(f"page date stamp {found!r} matches no known date format")


def _dated(candidate: str, fmt: str, season: int) -> date | None:
    """``candidate`` read under year-less ``fmt``, dated against ``season``.

    Sagarin's in-season stamp names a month and a day and no year, while its title
    line names the season -- so the year is derived, not guessed. A season runs
    August into January, so a month before the summer split belongs to the year
    after the season: the 2026 page's "January 10" is 2027-01-10.

    The year is appended to the text rather than substituted into the parsed date,
    because a year-less ``strptime`` defaults to 1900, cannot represent February 29,
    and is deprecated for exactly those reasons -- it is slated to change or raise
    in Python 3.15. Both candidate years are tried and the one the season rule
    wants is the one returned, so February 29 resolves in whichever of the two is
    a leap year and is rejected when neither is.
    """
    for year in (season, season + 1):
        try:
            parsed = datetime.strptime(f"{candidate} {year}", f"{fmt} %Y").date()
        except ValueError:
            continue
        if parsed.year == (season if parsed.month >= _SEASON_ROLLOVER_MONTH else season + 1):
            return parsed
    return None

"""Parse the Predictions_with_Totals_and_Moneylines section of the Sagarin page.

This section matters more than the ratings table (SPEC-phase0 4.4). It is a
published competitor's game-by-game predictions with totals and moneylines, which
can be scored head-to-head against ours and against the market line. A rating
would have to be converted into a prediction first; these already are one.

Two traps, both live on the 2026 preseason capture:

* **The section is printed twice.** The regular set comes first, then a second
  full copy under ``EXPERIMENTAL NUMBERS INVOLVING HOME-AWAY ADJUSTMENTS FOR EACH
  TEAM``. Taking the whole page doubles every game. Only the first block is parsed.
* **The section name appears twice too**, and the first one is a decoy: line 120
  of the capture is the navigation *link* (``href="#Predictions_..."``) sitting in
  the intro, ~860 lines above the section. The section itself starts at the
  *anchor* (``a name="Predictions_..."``). Matching the bare string finds the link
  and starts the parse in the middle of the ratings intro.

Row shape, anchored on structural tokens rather than column offsets::

    rank [N|C] [@] FAVORITE  rating pred golden recent strong  [@] UNDERDOG \\
        MONEY WIN%  home away TOTAL  <tail>

The ``@`` marks the nominal home team, sits on exactly one of the two names, and is
present even on neutral-site games. The flag after the rank is blank for an
ordinary game, ``N`` for neutral, and ``C`` for a classic; it moves the home/away
split columns, so it changes what ``home`` means and is carried, not discarded.

**The tail has two shapes and the page switches between them.** Preseason it is a
single unlabelled percentage. In-season the header grows ``MARG WIN% MONEY`` and
the row grows with it: the margin implied by the home/away split, and the win
probability and moneyline that go with *that* margin rather than with the rating
columns. The two disagree on real rows -- on the 2026-09-01 capture San Jose State
is favoured by 1.75 on rating while the split has Eastern Michigan by 7.85 -- so
the trailing pair is not a restatement of the leading MONEY/WIN% and must not be
read as one. None of the three is carried into ``GamePrediction``: SPEC-phase0 4.4
names PREDICTOR as the column to benchmark against, and a second margin under the
same name would be worse than no margin at all.

Every column is matched, including the ones the model does not carry, so a shifted
column is a parse failure rather than a plausible-looking wrong number. That is why
the in-season tail is spelled out rather than absorbed by a loosened anchor: three
new columns arriving is exactly the change this parser exists to notice.
"""

from __future__ import annotations

import re

from cfb.errors import DuplicateRankError, ParseError
from cfb.models import GamePrediction, validating

__all__ = ["parse_predictions"]

# The anchor, not the navigation link. ``name=`` is what distinguishes them.
_SECTION_ANCHOR = re.compile(r'<a\s+name="Predictions_with_Totals_and_Moneylines"', re.IGNORECASE)

# The second, duplicate copy of the whole section starts here.
_EXPERIMENTAL = re.compile(r"^EXPERIMENTAL NUMBERS INVOLVING HOME-AWAY ADJUSTMENTS", re.IGNORECASE)

# Header lines, reprinted every 50 rows. The predictions header prints its
# home-field values bare; only the ratings header brackets them.
_TITLE = re.compile(r"^\d{4}\s+College Football\b", re.IGNORECASE)
_HFA_HEADER = re.compile(r"^\s*HOME ADVANTAGE=")
_COLUMN_HEADER = re.compile(r"^\s+FAVORITE\s+Rating\s+Pred\s+Golden")
_ANCHOR_LINE = re.compile(r"^\s*<")

_FLOAT = r"-?\d+\.\d{2}"

_ROW = re.compile(
    rf"^\s*(?P<rank>\d+)\s+"
    rf"(?:(?P<flag>[NC])\s+)?"
    rf"(?:(?P<favorite_home>@)\s+)?(?P<favorite>\S.*?)\s+"
    rf"(?P<rating>{_FLOAT})\s+(?P<predictor>{_FLOAT})\s+(?P<golden_mean>{_FLOAT})\s+"
    rf"(?P<recent>{_FLOAT})\s+(?P<strong_recent>{_FLOAT})\s+"
    rf"(?:(?P<underdog_home>@)\s+)?(?P<underdog>\S.*?)\s+"
    rf"(?P<moneyline>-?\d+)\s+(?P<win_pct>\d+)%\s+"
    rf"(?P<home_points>{_FLOAT})\s+(?P<away_points>{_FLOAT})\s+(?P<total>{_FLOAT})\s+"
    rf"(?:"
    rf"(?P<split_pct>\d+)%"
    rf"|"
    rf"(?P<split_margin>{_FLOAT})\s+(?P<split_win_pct>\d+)%\s+(?P<split_moneyline>-?\d+)"
    rf")\s*$"
)

# Anything opening like a rank in the rank column: tells "this is a row and it is
# broken" (raise) apart from "this is not a row" (a reprinted header).
_ROW_CANDIDATE = re.compile(r"^\s{0,6}\d{1,3}\s")

_SITE_BY_FLAG = {None: "home", "N": "neutral", "C": "classic"}


def _lines(text: str) -> list[str]:
    """Split on newlines only; see the note in ``sagarin_ratings._lines``."""
    return [line.rstrip("\r") for line in text.split("\n")]


def _first_block(text: str) -> list[tuple[int, str]]:
    """Return ``(line number, line)`` for the first predictions block only."""
    lines = _lines(text)

    start = next((i for i, line in enumerate(lines) if _SECTION_ANCHOR.search(line)), None)
    if start is None:
        raise ParseError(
            'no predictions section found: expected an <a name="Predictions_with_Totals'
            '_and_Moneylines"> anchor. Note the navigation link of the same name is not it.'
        )

    end = next((i for i in range(start, len(lines)) if _EXPERIMENTAL.match(lines[i])), len(lines))
    return [(i + 1, lines[i]) for i in range(start, end)]


def _is_header(line: str) -> bool:
    """Is this the section anchor or one of the headers reprinted every 50 rows?"""
    return bool(
        _ANCHOR_LINE.match(line)
        or _TITLE.match(line)
        or _HFA_HEADER.match(line)
        or _COLUMN_HEADER.match(line)
    )


def parse_predictions(text: str) -> list[GamePrediction]:
    """Parse the first predictions block into one :class:`GamePrediction` per game.

    Raises :class:`~cfb.errors.DuplicateRankError` on a repeated rank and
    :class:`~cfb.errors.ParseError` on a malformed row, an unrecognised line inside
    the block, a row whose ``@`` marker is missing or doubled, a gap in the rank
    sequence, or an empty block.
    """
    games: list[GamePrediction] = []
    seen: dict[int, int] = {}

    for lineno, raw in _first_block(text):
        line = raw.rstrip()
        if not line or _is_header(line):
            continue

        if not _ROW_CANDIDATE.match(line):
            raise ParseError(
                f"line {lineno}: unrecognised line inside the predictions block: {line!r}"
            )

        row = _ROW.match(line)
        if row is None:
            raise ParseError(f"line {lineno}: row does not match the predictions schema: {line!r}")

        rank = int(row["rank"])
        favorite, underdog = row["favorite"], row["underdog"]
        favorite_home = row["favorite_home"] is not None
        underdog_home = row["underdog_home"] is not None

        # Exactly one side is the nominal home team. Neither or both means the @ was
        # misread, which would silently invert a prediction.
        if favorite_home == underdog_home:
            side = "both sides" if favorite_home else "neither side"
            raise ParseError(
                f"line {lineno}: prediction {rank} marks {side} as home with '@'; "
                f"cannot tell {favorite!r} from {underdog!r}: {line!r}"
            )

        if rank in seen:
            raise DuplicateRankError(
                f"prediction rank {rank} is published twice: line {seen[rank]} and line "
                f"{lineno}. Rank is the join key; a duplicate makes it unusable."
            )
        seen[rank] = lineno

        margin = float(row["predictor"])
        home, away = (favorite, underdog) if favorite_home else (underdog, favorite)
        with validating(f"line {lineno}: prediction rank {rank} ({home!r} vs {away!r})"):
            games.append(
                GamePrediction(
                    rank=rank,
                    home=home,
                    away=away,
                    site=_SITE_BY_FLAG[row["flag"]],
                    # The page always states the margin in the favorite's favour.
                    # Signed from the home team's perspective, an away favorite is
                    # negative.
                    predicted_margin=margin if favorite_home else -margin,
                    total=float(row["total"]),
                    moneyline=int(row["moneyline"]),
                )
            )

    if not games:
        raise ParseError("the predictions block contained no game rows")

    expected = list(range(1, len(games) + 1))
    if sorted(seen) != expected:
        missing = sorted(set(expected) - set(seen))
        raise ParseError(
            f"prediction ranks are not contiguous: parsed {len(games)} games, "
            f"missing rank(s) {missing}"
        )

    return games

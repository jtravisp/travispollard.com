"""Contract tests for the Sagarin section-1 ratings parser (PHASE-0 section 2).

Fixture provenance
------------------
``fixtures/sagarin_2026_preseason.txt`` is a verbatim capture of
http://sagarin.com/sports/cfsend.htm taken 2026-08-27: 148,793 bytes,
sha256 ba40d83651ea42b961c8042c82831724c4d2c278b187930370f75115897090a2.
Nothing was normalised -- CRLF line endings, the HTML wrapper, and the repeated
header blocks are all as the server sent them. It is the 2026 STARTING page, so
it is also the preseason degenerate state of SPEC-phase0 4.5. Fixtures are
marked ``-text`` in .gitattributes; without that, core.autocrlf rewrites the
bytes on checkout and the capture stops being golden.

``fixtures/sagarin_2026_week01.txt`` is the same page in-season, captured
2026-09-01 by the collector itself and read back out of its immutable snapshot:
178,410 bytes,
sha256 55cc2274f9e82ebd7c40a9fa310da7b54bcbc440ebac7373a41574b2b1b900eb.
It exists because the preseason capture has no date stamp, which left the only
line that carries one with no golden bytes behind it until the Tuesday collector
failed on the real format in production.

``fixtures/sagarin_malformed_row.txt`` is derived from it: the header block and
ranks 1-10, with rank 5's rating value deleted while the ``=`` anchor and every
other field on the line stay put. That is the shape a lenient parser turns into
``rating=None`` instead of an error.

No parser exists yet. These tests are the contract it has to satisfy, and they
are expected to fail until ``cfb.parsers.sagarin_ratings`` lands.
"""

from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from cfb.errors import DuplicateRankError, ParseError
from cfb.parsers.sagarin_ratings import (
    parse_hfa,
    parse_page_date_stamp,
    parse_page_state,
    parse_ratings,
    parse_season,
)

FIXTURES = Path(__file__).parent / "fixtures"

# The page states its own count in prose: "266 TEAMS RATED".
SECTION_1_TEAM_COUNT = 266
FBS_COUNT = 138
FCS_COUNT = 128

# SPEC-phase0 2.2 names these four HFA columns. The page prints a fifth
# (STRONG RECENT); a parser may carry it, but these four must be there.
HFA_COLUMNS = ("rating", "predictor", "golden_mean", "recent")


def _read(name: str) -> str:
    """Read a fixture the way the collector does: bytes off disk, then decode.

    SPEC-phase0 4.2 tries utf-8 first. This capture is pure ASCII, so utf-8
    wins; decoding here rather than using read_text keeps the test honest about
    the fixture being bytes.
    """
    return (FIXTURES / name).read_bytes().decode("utf-8")


@pytest.fixture(scope="module")
def page() -> str:
    return _read("sagarin_2026_preseason.txt")


@pytest.fixture(scope="module")
def teams(page):
    return parse_ratings(page)


@pytest.fixture(scope="module")
def by_rank(teams):
    return {t.rank: t for t in teams}


# --- section 1 only -------------------------------------------------------

def test_parses_exactly_the_section_one_team_count(teams):
    assert len(teams) == SECTION_1_TEAM_COUNT


def test_section_three_does_not_duplicate_any_team(page, teams):
    # The trap is live in this fixture: section 3 reprints every team, so the
    # identical row text occurs twice in the file.
    assert page.count("  85  Hawai'i              A  =  60.58") == 2

    names = [t.name for t in teams]
    assert names.count("Hawai'i") == 1
    assert len(set(names)) == len(names)

    assert sorted(t.rank for t in teams) == list(range(1, SECTION_1_TEAM_COUNT + 1))


def test_non_team_rows_are_not_parsed_as_teams(teams):
    """Section 2 conference rows and the UNRATED sentinel look like team rows.

    Conference averages print as ``   1  SEC                 (A) =  87.67`` and
    the sentinel as ``267  ***UNRATED***        __ = -76.07`` -- both match a
    naive "rank name division = rating" shape.
    """
    names = {t.name for t in teams}
    assert names.isdisjoint({"SEC", "BIG TEN", "ACC", "BIG 12", "PAC-12"})
    assert not [n for n in names if "UNRATED" in n]


# --- row parsing ----------------------------------------------------------

@pytest.mark.parametrize(
    "rank, name",
    [
        (7, "Miami-Florida"),
        (8, "Texas A&M"),
        (11, "Southern California"),
        (60, "Central Florida(UCF)"),   # no space before the paren
        (85, "Hawai'i"),
        (129, "Stephen F. Austin"),
        (160, "LouisianaMonroe(ULM)"),
        (171, "William & Mary"),
        (206, "St. Thomas-Mn."),
        (260, "Ark.-Pine Bluff"),
    ],
)
def test_names_with_punctuation_survive_intact(by_rank, rank, name):
    assert by_rank[rank].name == name


def test_conference_is_captured_per_row(by_rank):
    assert by_rank[1].conference == "BIG TEN"
    assert by_rank[68].conference == "MISSOURI VALLEY"


@pytest.mark.parametrize(
    "rating, first, second",
    [
        (77.49, (42, "Virginia Tech"), (43, "Northwestern")),
        (56.53, (99, "Tulsa"), (100, "Toledo")),
        (53.34, (120, "Georgia Southern"), (121, "Kennesaw State")),
        (34.46, (234, "Grambling State"), (235, "Morgan State")),
    ],
)
def test_duplicate_rating_values_with_distinct_ranks_do_not_collide(
    teams, by_rank, rating, first, second
):
    (rank_a, name_a), (rank_b, name_b) = first, second

    assert by_rank[rank_a].name == name_a
    assert by_rank[rank_b].name == name_b
    assert by_rank[rank_a].rating == by_rank[rank_b].rating == rating

    # Neither row was dropped by a dedupe or a join on the rating value.
    assert len(teams) == SECTION_1_TEAM_COUNT


def test_duplicate_ranks_raise(page):
    broken = page.replace(
        "  43  Northwestern         A  =  77.49",
        "  42  Northwestern         A  =  77.49",
    )
    assert broken != page

    with pytest.raises(DuplicateRankError) as excinfo:
        parse_ratings(broken)
    assert "42" in str(excinfo.value)


# --- home-field advantage -------------------------------------------------

def test_home_field_advantage_is_captured_from_the_page(page):
    hfa = parse_hfa(page)

    assert hfa, "hfa must never be empty -- there is no default to fall back to"
    assert set(HFA_COLUMNS) <= set(hfa)
    assert all(hfa[column] == 2.41 for column in HFA_COLUMNS)


def test_home_field_advantage_is_not_a_constant(page):
    """Move the page's HFA and the parser must move with it.

    2.41 is this week's value, not a property of the format. Only the ratings
    header uses the bracketed form, so this rewrite leaves the predictions
    section alone.
    """
    moved = page.replace("[  2.41]", "[  3.17]")
    assert moved != page

    hfa = parse_hfa(moved)
    assert all(hfa[column] == 3.17 for column in HFA_COLUMNS)


# --- preseason ------------------------------------------------------------

def test_preseason_state_is_flagged(page):
    assert parse_page_state(page) == "preseason"
    assert parse_season(page) == 2026


def test_preseason_degeneracy_parses(teams):
    for team in teams:
        assert team.rating == team.predictor == team.golden_mean == team.recent
        assert (team.wins, team.losses) == (0, 0)


def test_preseason_page_carries_no_internal_date_stamp(page):
    """The STARTING page has no date stamp at all.

    Its title line is ``2026 College Football STARTING ratings`` -- season and
    state, no date. In-season pages carry "through games of <date>". So
    page_date_stamp has to be optional, and freshness (SPEC-phase0 4.6) has
    nothing to compare until the first in-season page lands.
    """
    assert parse_page_date_stamp(page) is None


# --- the date stamp, and the two reasons it can come back None ------------
#
# ``None`` means "this page has no stamp", which is legal and makes SPEC 4.6 skip
# the comparison. It must never also mean "this page has a stamp and the parser
# could not read it", because the two are indistinguishable downstream and the
# second one disables the freshness check silently, forever, with every run green.
# So: absent phrase -> None. Phrase present and unreadable -> raise.

PRESEASON_TITLE = "2026 College Football STARTING ratings"


def retitled(page: str, rest: str) -> str:
    """The golden capture with its title line's tail replaced.

    The title block reprints every 10 rows (SPEC 4.7), so this rewrites all of
    them and the page stays internally consistent.
    """
    assert PRESEASON_TITLE in page, "the golden capture's title line changed; this helper is stale"
    return page.replace(PRESEASON_TITLE, f"2026 College Football {rest}")


def test_an_in_season_title_with_no_date_phrase_has_no_stamp(page):
    """Case 1: nothing claiming to be a date, so nothing to fail to read.

    Separated from the preseason test above because that one confounds two
    things -- the STARTING marker and the missing phrase -- and only the missing
    phrase is what makes the stamp legitimately null.
    """
    assert parse_page_date_stamp(retitled(page, "ratings")) is None


@pytest.mark.parametrize(
    "stamp",
    [
        "Blorptember 45, 2026",  # a month that does not exist
        "2026-09-15",  # ISO, which _DATE_FORMATS does not list
        "Sep. 15, 2026",  # abbreviated with a period
        "15/09/2026",  # day-first
        "September 2026",  # no day at all
    ],
)
def test_a_date_after_the_phrase_that_will_not_parse_raises(page, stamp):
    """Case 2: the page says it has a stamp, so the parser owes an answer or an error.

    Returning ``None`` here would be the failure this whole section guards. The
    page is in-season, the stamp is right there, and a null would tell SPEC 4.6
    to skip the comparison -- permanently, and without a single red run to say so.
    """
    with pytest.raises(ParseError) as excinfo:
        parse_page_date_stamp(retitled(page, f"ratings  through games of {stamp}"))
    assert stamp in str(excinfo.value), "the error should quote what it could not read"


@pytest.mark.parametrize("tail", ["", " ", "   ", "	"])
def test_the_phrase_with_nothing_after_it_raises(page, tail):
    """Case 2, at its edge: the phrase is present and the date is empty.

    A truncated line is exactly what a mid-publish fetch or a format change looks
    like, and it is the shape where "no stamp" and "unreadable stamp" are easiest
    to confuse -- there is no text to point at either way. The phrase is the
    evidence that a date was meant to be here.
    """
    with pytest.raises(ParseError):
        parse_page_date_stamp(retitled(page, f"ratings  through games of{tail}"))


@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        ("September 15, 2026", date(2026, 9, 15)),
        ("Tuesday, September 15, 2026", date(2026, 9, 15)),
        ("15 September 2026", date(2026, 9, 15)),
        ("9/15/2026", date(2026, 9, 15)),
    ],
)
def test_a_readable_stamp_parses(page, stamp, expected):
    """The control. Without it the two tests above are satisfied by a parser that
    raises on everything, which would take the collector down every Tuesday.
    """
    assert parse_page_date_stamp(retitled(page, f"ratings  through games of {stamp}")) == expected


@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        # The shape the live page actually prints: no year, weekday trailing.
        ("August 29 Saturday", date(2026, 8, 29)),
        ("September 5 Saturday", date(2026, 9, 5)),
        # A season crosses the New Year, and the stamp still names no year. Read
        # against the 2026 title line, a January date is 2027.
        ("January 10 Saturday", date(2027, 1, 10)),
        ("December 6 Saturday", date(2026, 12, 6)),
        # Year-less without the weekday, and the weekday without the year in the
        # other position. Neither has been seen; both are the same date.
        ("August 29", date(2026, 8, 29)),
        ("Saturday, August 29", date(2026, 8, 29)),
        ("29 August", date(2026, 8, 29)),
        # A stamp that carries its own year is read from the page, never from the
        # season -- including when the two disagree.
        ("August 29, 2026 Saturday", date(2026, 8, 29)),
        ("August 29, 2019", date(2019, 8, 29)),
    ],
)
def test_a_year_less_stamp_is_dated_from_the_season_on_the_title_line(page, stamp, expected):
    """The live page omits the year and trails the weekday: "August 29 Saturday".

    This is what took the Tuesday collector down on 2026-09-01 -- the first
    in-season page the parser had ever been handed, against a set of accepted
    formats that had only ever been guessed at. The year is not missing: the same
    title line names the season, so it is derived rather than assumed.
    """
    assert parse_page_date_stamp(retitled(page, f"ratings  through games of {stamp}")) == expected


def test_february_29_resolves_only_in_a_year_that_has_one(page):
    """The leap day is where "append the year" and "default to 1900" diverge.

    A year-less ``strptime`` cannot represent February 29 at all. Dating the text
    before parsing it can, in whichever of the season's two years is a leap year
    -- and must still reject the day in a season that spans neither.
    """
    leap = retitled(page, "ratings  through games of February 29").replace(
        "2026 College Football", "2027 College Football"
    )
    assert parse_page_date_stamp(leap) == date(2028, 2, 29)

    with pytest.raises(ParseError):
        parse_page_date_stamp(retitled(page, "ratings  through games of February 29"))


# --- the in-season page ---------------------------------------------------

@pytest.fixture(scope="module")
def in_season_page() -> str:
    """The 2026-09-01 capture: 178,410 bytes, the first in-season page fetched.

    Provenance is the collector's own immutable snapshot --
    ``s3://travispollard-cfb-data/raw/sagarin/season=2026/week=01/2026-09-01T161731Z.txt``,
    written before the parse that then failed on it. Bytes verbatim, CRLF intact.
    """
    return _read("sagarin_2026_week01.txt")


def test_the_in_season_page_parses_end_to_end(in_season_page):
    """The regression this fixture exists for.

    Every earlier test in this file runs against the preseason capture, so the
    in-season title line -- the only line that carries a date stamp -- had no
    golden bytes behind it and the collector met the real format in production.
    """
    assert parse_season(in_season_page) == 2026
    assert parse_page_state(in_season_page) == "in-season"
    assert parse_page_date_stamp(in_season_page) == date(2026, 8, 29)
    assert parse_hfa(in_season_page)["predictor"] == 2.41

    teams = parse_ratings(in_season_page)
    assert len(teams) == SECTION_1_TEAM_COUNT
    assert Counter(t.division for t in teams) == {"A": FBS_COUNT, "AA": FCS_COUNT}
    assert sorted(t.rank for t in teams) == list(range(1, SECTION_1_TEAM_COUNT + 1))


def test_the_in_season_page_is_not_the_preseason_degenerate_state(in_season_page):
    """What makes this capture worth keeping: games have been played in it.

    On the preseason page all four columns are identical and every record is 0-0.
    Pinning the difference here keeps a future fixture refresh from quietly
    swapping in another STARTING page and restoring the blind spot.
    """
    teams = parse_ratings(in_season_page)
    assert any(t.rating != t.predictor for t in teams)
    assert any(t.wins or t.losses for t in teams)


# --- FCS ------------------------------------------------------------------

def test_fcs_teams_are_present_and_marked(teams, by_rank):
    assert Counter(t.division for t in teams) == {"A": FBS_COUNT, "AA": FCS_COUNT}

    assert by_rank[68].name == "South Dakota State"
    assert by_rank[68].division == "AA"
    assert by_rank[1].division == "A"


# --- malformed input ------------------------------------------------------

def test_malformed_row_raises_rather_than_returning_none():
    text = _read("sagarin_malformed_row.txt")

    with pytest.raises(ParseError) as excinfo:
        parse_ratings(text)

    message = str(excinfo.value)
    assert "5" in message and "Texas" in message

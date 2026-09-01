"""Contract tests for the Sagarin predictions parser (SPEC-phase0 4.4).

Fixture provenance
------------------
These run against the same golden capture as ``test_sagarin_parser.py``:
``fixtures/sagarin_2026_preseason.txt``, a verbatim capture of
http://sagarin.com/sports/cfsend.htm taken 2026-08-27, 148,793 bytes, sha256
ba40d83651ea42b961c8042c82831724c4d2c278b187930370f75115897090a2. Nothing was
normalised. See that module's docstring for why the fixture directory is marked
``-text`` in .gitattributes.

The predictions section is the benchmark competitor -- a published set of
game-by-game predictions that can be scored head-to-head against ours -- so these
tests pin the two ways a parser silently doubles or misreads it: the section is
printed twice, and the section name appears twice with the first one a decoy.

Mutations are applied in memory rather than as new fixture files. The golden
capture stays the only Sagarin bytes on disk.
"""

from pathlib import Path

import pytest

from cfb.errors import DuplicateRankError, ParseError
from cfb.parsers.sagarin_predictions import _ROW, _first_block, parse_predictions

FIXTURES = Path(__file__).parent / "fixtures"

# Both blocks hold this many games on the 2026 preseason page.
BLOCK_GAME_COUNT = 53

# Verbatim rows, used both as edit targets and as the duplication trap.
ROW_01 = (
    "    1   @ Austin Peay           10.67  10.67  10.67  10.67  10.67"
    "   Gardner-Webb             309    76%   27.21  24.79  52.00  57%"
)
ROW_02 = (
    "    2     Stony Brook            5.56   5.56   5.56   5.56   5.56"
    " @ Delaware State           184    65%   27.21  24.79  52.00  43%"
)
ROW_20 = (
    "   20 N   TCU                    6.20   6.20   6.20   6.20   6.20"
    " @ North Carolina           197    66%   26.00  26.00  52.00  50%"
)
ROW_27 = (
    "   27 C @ Alabama State          7.00   7.00   7.00   7.00   7.00"
    "   Southern U.              214    68%   26.60  25.40  52.00  53%"
)


def _read(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("utf-8")


@pytest.fixture(scope="module")
def page() -> str:
    return _read("sagarin_2026_preseason.txt")


@pytest.fixture(scope="module")
def games(page):
    return parse_predictions(page)


@pytest.fixture(scope="module")
def by_rank(games):
    return {g.rank: g for g in games}


# --- first block only -----------------------------------------------------

def test_parses_exactly_one_block_of_games(games):
    assert len(games) == BLOCK_GAME_COUNT


def test_the_experimental_reprint_does_not_double_the_games(page, games):
    # The trap is live: the EXPERIMENTAL block reprints every game, so the
    # identical row text occurs twice in the file.
    assert page.count(ROW_01) == 2
    assert "EXPERIMENTAL NUMBERS INVOLVING HOME-AWAY ADJUSTMENTS" in page

    assert sorted(g.rank for g in games) == list(range(1, BLOCK_GAME_COUNT + 1))
    assert len({(g.home, g.away) for g in games}) == BLOCK_GAME_COUNT


def test_the_navigation_link_is_not_mistaken_for_the_section(page, games):
    """The section name occurs twice and the first one is a decoy.

    The intro carries a navigation *link* (``href="#Predictions_..."``) hundreds of
    lines above the section's own *anchor* (``a name="Predictions_..."``). A parser
    that matches the bare string starts in the middle of the ratings intro.
    """
    assert page.count("Predictions_with_Totals_and_Moneylines") > 2
    assert page.index('href="#Predictions_with_Totals_and_Moneylines"') < page.index(
        'a name="Predictions_with_Totals_and_Moneylines"'
    )

    # Starting at the link would sweep the ratings table in as prediction rows.
    assert len(games) == BLOCK_GAME_COUNT


def test_ratings_rows_are_not_parsed_as_games(games):
    """Section 1 rows are ranked 1..266 and would blow past the block count."""
    assert not [g for g in games if g.home == "Ohio State" or g.away == "Ohio State"]


# --- home and away --------------------------------------------------------

def test_at_marker_on_the_favorite_makes_the_favorite_home(by_rank):
    game = by_rank[1]
    assert (game.home, game.away) == ("Austin Peay", "Gardner-Webb")
    assert game.predicted_margin == 10.67
    assert game.site == "home"
    assert (game.total, game.moneyline) == (52.00, 309)


def test_at_marker_on_the_underdog_makes_the_underdog_home(by_rank):
    """The favorite is the away team here, so the home margin is negative.

    Getting this backwards inverts the prediction without changing anything a
    count or a schema check would notice.
    """
    game = by_rank[2]
    assert (game.home, game.away) == ("Delaware State", "Stony Brook")
    assert game.predicted_margin == -5.56
    assert game.site == "home"


def test_every_game_has_a_distinct_home_and_away(games):
    for game in games:
        assert game.home != game.away


def test_a_row_marking_neither_side_home_raises(page):
    broken = page.replace(ROW_01, ROW_01.replace("@ Austin Peay", "  Austin Peay"), 1)
    assert broken != page

    with pytest.raises(ParseError) as excinfo:
        parse_predictions(broken)
    assert "neither side" in str(excinfo.value)


def test_a_row_marking_both_sides_home_raises(page):
    broken = page.replace(ROW_01, ROW_01.replace("  Gardner-Webb", "@ Gardner-Webb"), 1)
    assert broken != page

    with pytest.raises(ParseError) as excinfo:
        parse_predictions(broken)
    assert "both sides" in str(excinfo.value)


# --- the site flag --------------------------------------------------------

@pytest.mark.parametrize(
    "rank, site, home, away",
    [
        (1, "home", "Austin Peay", "Gardner-Webb"),
        (20, "neutral", "North Carolina", "TCU"),
        (25, "neutral", "Virginia", "NC State"),
        (27, "classic", "Alabama State", "Southern U."),
    ],
)
def test_the_flag_after_the_rank_is_captured(by_rank, rank, site, home, away):
    game = by_rank[rank]
    assert (game.site, game.home, game.away) == (site, home, away)


def test_all_three_site_states_occur_on_this_page(games):
    assert {g.site for g in games} == {"home", "neutral", "classic"}


def test_the_at_marker_survives_on_neutral_rows(by_rank):
    """A neutral game still names a nominal home team.

    ``@`` is present on every row regardless of site, so "neutral" must not be
    allowed to erase the home/away assignment.
    """
    assert by_rank[20].home == "North Carolina"
    assert by_rank[25].home == "Virginia"


# --- names ----------------------------------------------------------------

@pytest.mark.parametrize(
    "rank, name",
    [
        (1, "Gardner-Webb"),
        (5, "Miss. Valley State"),
        (13, "Albany-NY"),
        (14, "Cal Poly-SLO"),
        (23, "Hawai'i"),
        (26, "Alabama A&M"),
        (50, "William & Mary"),
        (53, "The Citadel"),
    ],
)
def test_names_with_punctuation_survive_intact(by_rank, rank, name):
    game = by_rank[rank]
    assert name in (game.home, game.away)


def test_a_team_name_beginning_with_the_flag_letters_is_not_eaten(by_rank):
    """``N`` and ``C`` are flag values and also the first letter of team names.

    ``NC Central`` and ``The Citadel`` sit next to rows that really do carry an
    ``N`` or ``C`` flag, so an over-eager flag match silently truncates a name.
    """
    assert by_rank[48].away == "NC Central"
    assert by_rank[48].site == "home"
    assert by_rank[53].away == "The Citadel"


# --- malformed input ------------------------------------------------------

def test_duplicate_ranks_raise(page):
    broken = page.replace(ROW_02, ROW_02.replace("    2  ", "    1  ", 1), 1)
    assert broken != page

    with pytest.raises(DuplicateRankError) as excinfo:
        parse_predictions(broken)
    assert "1" in str(excinfo.value)


def test_a_missing_field_raises_rather_than_returning_none(page):
    """Delete the total and leave every other field and separator in place.

    That is the shape a lenient parser turns into ``total=None``.
    """
    broken = page.replace(ROW_20, ROW_20.replace("52.00", "     "), 1)
    assert broken != page

    with pytest.raises(ParseError) as excinfo:
        parse_predictions(broken)
    assert "20" in str(excinfo.value)


def test_an_unrecognised_line_inside_the_block_raises(page):
    broken = page.replace(ROW_27, "   27 C @ Alabama State  ???", 1)
    assert broken != page

    with pytest.raises(ParseError):
        parse_predictions(broken)


def test_a_dropped_row_raises_rather_than_shortening_the_block(page):
    broken = page.replace(ROW_27 + "\r\n", "", 1)
    assert broken != page

    with pytest.raises(ParseError) as excinfo:
        parse_predictions(broken)
    assert "27" in str(excinfo.value)


def test_a_page_with_no_predictions_section_raises():
    with pytest.raises(ParseError) as excinfo:
        parse_predictions("2026 College Football STARTING ratings\r\n")
    assert "anchor" in str(excinfo.value)


# --- preseason ------------------------------------------------------------

def test_preseason_totals_are_the_degenerate_constant(games):
    """Before any games every total is the same 52.00 and no line is missing.

    Week zero carries no game-specific information, which is exactly why the
    model must not be allowed to treat these as informative later.
    """
    assert {g.total for g in games} == {52.00}
    assert all(g.moneyline is not None for g in games)


# --- in-season ------------------------------------------------------------

@pytest.fixture(scope="module")
def in_season_page() -> str:
    """The 2026-09-01 capture -- see the provenance note in test_sagarin_parser."""
    return _read("sagarin_2026_week01.txt")


@pytest.fixture(scope="module")
def in_season_games(in_season_page):
    return parse_predictions(in_season_page)


def test_the_in_season_tail_parses(in_season_page, in_season_games):
    """The regression. In-season the header grows ``MARG WIN% MONEY`` and every
    row grows three columns with it, which took the collector down on 2026-09-01.
    """
    assert "TOTAL   MARG WIN%  MONEY" in in_season_page
    assert len(in_season_games) == 118


def test_the_in_season_page_is_not_the_preseason_degenerate_state(in_season_games):
    """Games have been played: the totals vary instead of all being 52.00."""
    assert len({g.total for g in in_season_games}) > 1


def test_the_new_columns_did_not_shift_the_old_ones(in_season_page):
    """Three columns arriving is only safe if nothing slid left into them.

    Checked against the page's own arithmetic rather than against fixed offsets:
    the split scores must still sum to the total, and MARG must still be their
    difference. A regex that let the underdog name or the leading moneyline
    absorb a column would break both, while still returning a full row.
    """
    matched = [_ROW.match(line) for _, line in _first_block(in_season_page)]
    rows = [m for m in matched if m is not None]
    assert len(rows) == 118

    for row in rows:
        home, away, total = (float(row[c]) for c in ("home_points", "away_points", "total"))
        assert home + away == pytest.approx(total, abs=0.011)
        assert row["split_margin"] is not None, "every in-season row carries the new tail"
        assert home - away == pytest.approx(float(row["split_margin"]), abs=0.011)


def test_the_trailing_pair_belongs_to_the_split_margin_not_the_rating(in_season_page):
    """The trailing WIN%/MONEY are not a restatement of the leading ones.

    Rank 12 is the proof on this capture: San Jose State is favoured by 1.75 on
    rating and gets 55% / 122, while the home/away split has Eastern Michigan by
    7.85 and the tail reads 70% / 233. Reading either pair as the other would
    publish a number the page never claimed.
    """
    row = next(
        _ROW.match(line)
        for _, line in _first_block(in_season_page)
        if _ROW.match(line) and _ROW.match(line)["rank"] == "12"
    )
    assert (row["moneyline"], row["win_pct"]) == ("122", "55")
    assert (row["split_moneyline"], row["split_win_pct"]) == ("233", "70")
    assert float(row["split_margin"]) == -7.85


def test_the_preseason_tail_is_still_rejected_when_truncated(in_season_page):
    """The two tails are alternatives, not a loosened anchor.

    Dropping the last column of an in-season row must not quietly fall through to
    the preseason branch, which would leave MARG parsed as a score column.
    """
    row = next(line for _, line in _first_block(in_season_page) if _ROW.match(line))
    broken = in_season_page.replace(row, row.rsplit(" ", 1)[0], 1)
    assert broken != in_season_page

    with pytest.raises(ParseError):
        parse_predictions(broken)

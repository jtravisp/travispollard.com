"""Rebuilding a season's Elo from ``raw/`` (SPEC-phase1 3.5).

The claim under test is the one §3.5 makes about the stored state: it is a cache
and not a source of truth. That is only true if the state can be regenerated from
snapshots alone and the regeneration is checked, which is what SPEC-phase1 11
step 5 runs and what this file asserts offline.

## Ordering is the property with no symptom

Elo is path-dependent -- the rating a team carries into a game is the sum of
everything before it -- and ``/games`` does not return kickoff order. An
out-of-order replay produces a complete, plausible set of ratings that are
silently wrong, and no downstream check would see it: the totals still conserve,
every team is still present, and the numbers are still in a believable range.

So the fixture below is built to make the two orders *disagree*, and the tests
assert both halves: that the replay matches the kickoff-ordered fold, **and** that
it differs from each order a plausible implementation would produce instead.
A test that only asserted the first would pass on a store whose captures happened
to be listed in kickoff order.

Three orders are distinguishable on this fixture:

    kickoff       G1, G2, G3     <- correct
    capture       G3, G1, G2     <- newest capture per week, then array order
    array         G3, G1, G2     <- same here; the week 01 file is reversed

The chain is what makes them differ. Each game shares a team with the one before
it, so every rating that feeds a later game is produced by an earlier one:

    G1  wk 1  Sep  5   Michigan at Ohio State     31-24
    G2  wk 2  Sep 12   Texas    at Michigan       21-17
    G3  wk 1  Sep 17   Ohio State at Texas        28-27

**G3 is the SPEC-phase1 5.1 case, not a contrivance.** It is a week 1 game
postponed and played after week 2 -- a game that "moves week for weather" -- which
is why the sort has to be global rather than per-week, and why the week 01
capture is the *newer* of the two (it was re-pulled after the game was finally
played).

## What is asserted about the arithmetic: nothing

``tests/test_elo.py`` owns the update step, against constants worked by hand. The
expectations here are folds of ``update`` over an order this file writes down, so
they isolate ordering and provenance and say nothing about whether the formula is
right. Asserting hand-computed Elo values here as well would mean two files fail
for one cause.
"""

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cfb.cli import main
from cfb.crosswalk import load as load_crosswalk
from cfb.elo import SCHEMA_VERSION, EloState, Game, Ratings, state_key, update
from cfb.elo.seed import seed
from cfb.errors import ReplayError, StateMismatchError, UnmappedTeamError
from cfb.models import Manifest, SagarinSnapshot
from cfb.parsers.sagarin_predictions import parse_predictions
from cfb.parsers.sagarin_ratings import (
    parse_hfa,
    parse_page_date_stamp,
    parse_page_state,
    parse_ratings,
)
from cfb.replay import load_state, newest_state_key, replay, verify
from cfb.storage import MemorySnapshotStore

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "sagarin_2026_preseason.txt"

SEASON = 2026

#: The preseason capture the season seeds from, and the HFA every game below uses
#: unless a test writes a later snapshot. 2.41 is what the golden page says.
PRESEASON_AT = datetime(2026, 8, 28, 17, 20, 6, tzinfo=UTC)
PRESEASON_HFA = 2.41

WEEK_01_PULLED_AT = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
WEEK_02_PULLED_AT = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)

G1_KICKOFF = datetime(2026, 9, 5, 23, 0, tzinfo=UTC)
G2_KICKOFF = datetime(2026, 9, 12, 23, 0, tzinfo=UTC)
G3_KICKOFF = datetime(2026, 9, 17, 23, 0, tzinfo=UTC)


# --- building a store ---------------------------------------------------------


def cfbd_game(
    *,
    game_id: int,
    week: int,
    kickoff: datetime,
    home: str,
    away: str,
    home_points: int | None,
    away_points: int | None,
    neutral_site: bool = False,
    season_type: str = "regular",
    season: int = SEASON,
) -> dict:
    """One ``/games`` row in the vendor's shape, with the vendor's spellings."""
    return {
        "id": game_id,
        "season": season,
        "week": week,
        "seasonType": season_type,
        "startDate": kickoff.isoformat().replace("+00:00", ".000Z"),
        "neutralSite": neutral_site,
        "conferenceGame": True,
        "homeTeam": home,
        "homeConference": "Big Ten",
        "homePoints": home_points,
        "awayTeam": away,
        "awayConference": "Big Ten",
        "awayPoints": away_points,
    }


G1 = cfbd_game(
    game_id=101, week=1, kickoff=G1_KICKOFF,
    home="Ohio State", away="Michigan", home_points=31, away_points=24,
)
G2 = cfbd_game(
    game_id=102, week=2, kickoff=G2_KICKOFF,
    home="Michigan", away="Texas", home_points=21, away_points=17,
)
G3 = cfbd_game(
    game_id=103, week=1, kickoff=G3_KICKOFF,
    home="Texas", away="Ohio State", home_points=28, away_points=27,
)
#: On the week 2 slate and not yet played. SPEC-phase1 5.2: normal, not an error.
UNPLAYED = cfbd_game(
    game_id=104, week=2, kickoff=datetime(2026, 9, 19, 23, 0, tzinfo=UTC),
    home="USC", away="UCLA", home_points=None, away_points=None,
)


def put_games(store, *, week: str, fetched_at: datetime, games: list[dict]) -> str:
    """Store one ``/games`` capture and its manifest. Returns the snapshot key."""
    data = json.dumps(games).encode("utf-8")
    key = f"raw/cfbd/season={SEASON}/week={week}/games/{_stamp(fetched_at)}.json"
    store.put_bytes(key, data, "application/json")
    store.put_json(
        key.removesuffix(".json") + ".meta.json",
        Manifest(
            schema_version=1,
            source="cfbd",
            resource="games",
            source_url="https://api.collegefootballdata.com/games",
            http_status=200,
            sha256=hashlib.sha256(data).hexdigest(),
            bytes=len(data),
            encoding=None,
            fetched_at=fetched_at,
            season=SEASON,
            week=week,
            week_resolution="calendar",
            snapshot_key=key,
        ).model_dump(mode="json", exclude={"unmapped"}),
    )
    return key


def put_sagarin(
    store,
    *,
    fetched_at: datetime,
    week: str = "preseason",
    page_state: str = "preseason",
    hfa: dict[str, float] | None = None,
    page_date_stamp=None,
) -> str:
    """Store the golden preseason page under a key, with a manifest describing it.

    The bytes are the real capture every time. Only the manifest varies, which is
    what the replay reads for an HFA -- SPEC-phase0 2.2 records ``hfa`` per
    snapshot precisely so nothing downstream re-parses the page for it.
    """
    data = GOLDEN.read_bytes()
    key = f"raw/sagarin/season={SEASON}/week={week}/{_stamp(fetched_at)}.txt"
    store.put_bytes(key, data, "text/plain")
    store.put_json(
        key.removesuffix(".txt") + ".meta.json",
        Manifest(
            schema_version=1,
            source="sagarin",
            resource="ratings",
            source_url="http://sagarin.com/sports/cfsend.htm",
            http_status=200,
            sha256=hashlib.sha256(data).hexdigest(),
            bytes=len(data),
            encoding="cp1252",
            fetched_at=fetched_at,
            season=SEASON,
            week=week,
            week_resolution="calendar",
            snapshot_key=key,
            parse_ok=True,
            page_date_stamp=page_date_stamp,
            page_state=page_state,
            team_count=266,
            fbs_count=138,
            hfa=hfa or {"rating": 2.41, "predictor": PRESEASON_HFA},
            predictions_count=106,
            unmapped=[],
        ).model_dump(mode="json"),
    )
    return key


def _stamp(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H%M%SZ")


@pytest.fixture
def store():
    """The season as it would sit in the bucket after week 2 was scored."""
    store = MemorySnapshotStore()
    put_sagarin(store, fetched_at=PRESEASON_AT)
    # Reversed inside the file on purpose: kickoff order is not array order, and
    # a replay that iterated the JSON as it came would apply G3 before G1.
    put_games(store, week="01", fetched_at=WEEK_01_PULLED_AT, games=[G3, G1])
    put_games(store, week="02", fetched_at=WEEK_02_PULLED_AT, games=[G2, UNPLAYED])
    return store


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


@pytest.fixture(scope="module")
def seeded(crosswalk) -> Ratings:
    """The week-0 ratings, from the same page and the same ``seed`` the replay uses.

    Built here rather than taken from a replay so the folds below start from
    something this file produced, not from the thing they are checking.
    """
    page = GOLDEN.read_bytes().decode("cp1252")
    return seed(
        SagarinSnapshot(
            fetched_at=PRESEASON_AT,
            page_date_stamp=parse_page_date_stamp(page),
            page_state=parse_page_state(page),
            hfa=parse_hfa(page),
            teams=parse_ratings(page),
            predictions=parse_predictions(page),
        ),
        crosswalk,
    )


def fold(ratings: Ratings, rows: list[dict], *, hfa: float = PRESEASON_HFA) -> Ratings:
    """Apply ``rows`` in the order given. The order is the whole point."""
    for row in rows:
        ratings = update(
            ratings,
            Game(
                cfbd_game_id=row["id"],
                home={"Ohio State": "ohio-state", "Michigan": "michigan", "Texas": "texas"}[
                    row["homeTeam"]
                ],
                away={"Ohio State": "ohio-state", "Michigan": "michigan", "Texas": "texas"}[
                    row["awayTeam"]
                ],
                home_points=row["homePoints"],
                away_points=row["awayPoints"],
                neutral_site=row["neutralSite"],
            ),
            hfa=hfa,
        )
    return ratings


# --- the tests ----------------------------------------------------------------


class TestKickoffOrder:
    """The property that fails silently if it is not asserted."""

    def test_games_apply_in_kickoff_order(self, store, crosswalk, seeded):
        expected = fold(seeded, [G1, G2, G3])
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.ratings == expected

    def test_it_is_not_the_order_the_captures_are_listed_in(self, store, crosswalk, seeded):
        """**Fails if the sort is dropped.**

        The week 01 capture is newer than the week 02 one, because week 1 was
        re-pulled after its postponed game was finally played. An implementation
        that walked captures newest-first and applied each file's rows as it found
        them would produce exactly this, and it is a different season.
        """
        wrong = fold(seeded, [G3, G1, G2])
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)

        assert rebuilt.ratings != wrong
        # Not a rounding difference -- the two disagree by whole rating points.
        assert max(abs(rebuilt.ratings[t] - wrong[t]) for t in ("texas", "ohio-state")) > 1

    def test_it_is_not_the_order_inside_the_file(self, store, crosswalk, seeded):
        """The week 01 capture holds ``[G3, G1]``. ``/games`` is not sorted."""
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.ratings != fold(seeded, [G3, G1, G2])
        assert rebuilt.ratings != fold(seeded, [G1, G3, G2])

    def test_a_game_moved_out_of_its_week_still_sorts_by_kickoff(
        self, store, crosswalk, seeded
    ):
        """SPEC-phase1 5.1's weather case, which is why the sort is not per-week.

        G3 is a week 1 game played after week 2. Sorting within each week and then
        concatenating the weeks would apply it before G2, and that is the ordering
        bug most likely to be written by someone who knows the sort matters.
        """
        per_week_then_concatenated = fold(seeded, [G1, G3, G2])
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.ratings != per_week_then_concatenated
        assert rebuilt.ratings == fold(seeded, [G1, G2, G3])

    def test_the_applied_sequence_is_reported_in_the_order_it_ran(
        self, store, crosswalk
    ):
        """Provenance, so a mismatch can be read rather than guessed at."""
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert [entry.game.cfbd_game_id for entry in rebuilt.applied] == [101, 102, 103]
        assert [entry.kickoff for entry in rebuilt.applied] == [
            G1_KICKOFF,
            G2_KICKOFF,
            G3_KICKOFF,
        ]

    def test_the_replay_is_deterministic(self, store, crosswalk):
        first = replay(store=store, season=SEASON, crosswalk=crosswalk)
        second = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert first.ratings == second.ratings


class TestStateIsNotAnInput:
    """§3.5's actual claim: ``elo/`` is a cache, and the rebuild never reads it."""

    def test_a_wrong_stored_state_does_not_change_the_rebuild(
        self, store, crosswalk, seeded
    ):
        """The strongest available form of "no state file".

        A replay that consulted the stored object -- to start from, to fill a gap,
        to short-circuit -- would drift toward these numbers. It must not move at
        all.
        """
        store.put_json(
            state_key(season=SEASON, week="02", generated_at=WEEK_02_PULLED_AT),
            {
                "schema_version": SCHEMA_VERSION,
                "season": SEASON,
                "week": "02",
                "generated_at": "2026-09-13T12:00:00Z",
                "seeded_from": "raw/sagarin/nonsense.txt",
                "games_applied": 999,
                "ratings": {"texas": 1.0, "ohio-state": 2.0, "michigan": 3.0},
            },
        )

        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.ratings == fold(seeded, [G1, G2, G3])
        assert rebuilt.games_applied == 3

    def test_the_rebuild_names_the_snapshots_it_came_from(self, store, crosswalk):
        """A number that cannot say where it came from is an assertion, not a record."""
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.seeded_from == (
            f"raw/sagarin/season={SEASON}/week=preseason/{_stamp(PRESEASON_AT)}.txt"
        )
        assert len(rebuilt.games_keys) == 2
        assert all(key.startswith(f"raw/cfbd/season={SEASON}/") for key in rebuilt.games_keys)
        for entry in rebuilt.applied:
            assert entry.hfa_key.startswith("raw/sagarin/")


class TestWhichGamesCount:
    def test_an_unplayed_game_is_skipped_not_an_error(self, store, crosswalk):
        """SPEC-phase1 5.2. A game with no result is normal, and 0-0 is not a score."""
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.games_applied == 3
        assert 104 not in [entry.game.cfbd_game_id for entry in rebuilt.applied]

    def test_one_score_present_and_the_other_missing_raises(self, crosswalk):
        """Not an unplayed game and not a completed one -- a malformed row.

        Treating it as unplayed would drop a result that was played, which is the
        silent filtering the whole project is built to prevent.
        """
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        half = dict(G1, awayPoints=None)
        put_games(store, week="01", fetched_at=WEEK_01_PULLED_AT, games=[half])

        with pytest.raises(ReplayError) as excinfo:
            replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert "101" in str(excinfo.value)

    def test_the_newest_capture_of_a_week_wins_entirely(self, crosswalk, seeded):
        """A re-pull supersedes; it does not merge.

        Merging both captures would resurrect a game the later pull had dropped --
        a cancellation, a schedule correction -- and apply a game that never
        happened. Here the second pull of week 1 no longer lists G3.
        """
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(store, week="01", fetched_at=datetime(2026, 9, 6, 12, tzinfo=UTC),
                  games=[G1, G3])
        put_games(store, week="01", fetched_at=datetime(2026, 9, 20, 12, tzinfo=UTC),
                  games=[G1])

        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.games_applied == 1
        assert rebuilt.ratings == fold(seeded, [G1])

    def test_a_game_appearing_under_two_weeks_is_applied_once(self, crosswalk, seeded):
        """A game moved for weather is in both weeks' slates (SPEC-phase1 5.1).

        Applying it twice would double its effect on two teams and leave every
        rating plausible, which is why the count is asserted alongside the values.
        """
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(store, week="01", fetched_at=WEEK_01_PULLED_AT, games=[G1])
        put_games(store, week="02", fetched_at=WEEK_02_PULLED_AT, games=[G2, G1])

        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.games_applied == 2
        assert rebuilt.ratings == fold(seeded, [G1, G2])

    def test_a_capture_holding_another_season_raises(self, crosswalk):
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(
            store, week="01", fetched_at=WEEK_01_PULLED_AT,
            games=[dict(G1, season=2025)],
        )
        with pytest.raises(ReplayError, match="2025"):
            replay(store=store, season=SEASON, crosswalk=crosswalk)

    def test_an_unmapped_cfbd_name_raises(self, crosswalk):
        """The replay is a second place vendor names cross into canonical space.

        Same treatment as the collector (SPEC-phase0 6.4): the run fails rather
        than rebuilding a season with one team's games missing.
        """
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(
            store, week="01", fetched_at=WEEK_01_PULLED_AT,
            games=[dict(G1, homeTeam="Ohio Statte")],
        )
        with pytest.raises(UnmappedTeamError, match="Ohio Statte"):
            replay(store=store, season=SEASON, crosswalk=crosswalk)


class TestThroughWeek:
    def test_it_cuts_on_the_week_the_game_belongs_to_not_on_the_clock(
        self, store, crosswalk, seeded
    ):
        """G3 is a week 1 game played after week 2's.

        A cutoff implemented as "kickoff before the end of week 1" would drop it;
        the state at ``elo/season=2026/week=01/`` is the state after every week 1
        game, whenever they were played.
        """
        rebuilt = replay(
            store=store, season=SEASON, through_week="01", crosswalk=crosswalk
        )
        assert [entry.game.cfbd_game_id for entry in rebuilt.applied] == [101, 103]
        assert rebuilt.ratings == fold(seeded, [G1, G3])

    def test_the_week_it_reports_is_the_one_asked_for(self, store, crosswalk):
        rebuilt = replay(
            store=store, season=SEASON, through_week="01", crosswalk=crosswalk
        )
        assert rebuilt.week == "01"

    def test_without_it_the_week_is_the_furthest_reached_not_the_last_kickoff(
        self, store, crosswalk
    ):
        """The last game by kickoff is G3, which is a week 1 game.

        Reporting "01" would send the verification at the stored week 2 state,
        which is the state this replay actually reproduces.
        """
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.week == "02"

    def test_a_week_with_no_games_is_still_that_week(self, crosswalk, seeded):
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(store, week="02", fetched_at=WEEK_02_PULLED_AT, games=[G2])

        rebuilt = replay(
            store=store, season=SEASON, through_week="01", crosswalk=crosswalk
        )
        assert rebuilt.week == "01"
        assert rebuilt.games_applied == 0
        assert rebuilt.ratings == seeded

    def test_an_illegal_value_raises(self, store, crosswalk):
        with pytest.raises(ReplayError, match="through-week"):
            replay(store=store, season=SEASON, through_week="16", crosswalk=crosswalk)


class TestSeeding:
    def test_a_season_with_no_preseason_snapshot_raises(self, crosswalk):
        """There is nothing to replay from, and 1500 across the board is not it."""
        store = MemorySnapshotStore()
        put_games(store, week="01", fetched_at=WEEK_01_PULLED_AT, games=[G1])
        with pytest.raises(ReplayError, match="preseason"):
            replay(store=store, season=SEASON, crosswalk=crosswalk)

    def test_the_first_preseason_capture_seeds_not_the_newest(self, crosswalk):
        """§3.2: seeding runs once, from the first preseason snapshot.

        Two preseason fetches in August are ordinary. Taking the newest would
        re-seed the season every time one landed, which is the mid-season re-seed
        §3.2 refuses, arriving through a different door.
        """
        store = MemorySnapshotStore()
        first = put_sagarin(store, fetched_at=PRESEASON_AT)
        put_sagarin(store, fetched_at=datetime(2026, 8, 29, 17, 20, 6, tzinfo=UTC))
        put_games(store, week="01", fetched_at=WEEK_01_PULLED_AT, games=[G1])

        assert replay(store=store, season=SEASON, crosswalk=crosswalk).seeded_from == first

    def test_a_snapshot_whose_parse_never_finished_is_not_a_seed(self, crosswalk):
        """A fetch-only manifest has no ``page_state`` (SPEC-phase0 4.3).

        The bytes are there and the run that wrote them failed at step 4 or later.
        Seeding from it would mean trusting a page nothing ever validated.
        """
        store = MemorySnapshotStore()
        data = GOLDEN.read_bytes()
        key = f"raw/sagarin/season={SEASON}/week=preseason/{_stamp(PRESEASON_AT)}.txt"
        store.put_bytes(key, data, "text/plain")
        store.put_json(
            key.removesuffix(".txt") + ".meta.json",
            Manifest(
                schema_version=1, source="sagarin", resource="ratings",
                source_url="http://sagarin.com/sports/cfsend.htm", http_status=200,
                sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), encoding="cp1252",
                fetched_at=PRESEASON_AT, season=SEASON, week="preseason",
                week_resolution="calendar", snapshot_key=key,
            ).model_dump(mode="json", exclude={"unmapped"}),
        )

        with pytest.raises(ReplayError, match="preseason"):
            replay(store=store, season=SEASON, crosswalk=crosswalk)


class TestHomeFieldAdvantage:
    """§3.3, and ``cfb/CLAUDE.md``'s "never hardcode home-field advantage"."""

    def test_a_game_uses_the_newest_snapshot_captured_before_its_kickoff(
        self, crosswalk, seeded
    ):
        """What a live Sunday run reads, stated as a function of the data.

        On the SPEC-phase1 8 schedule the Sunday scoring run sees that week's
        Tuesday capture, which was taken before Saturday's games. "Newest strictly
        before kickoff" reproduces that and stays stable as later snapshots
        arrive; a rule anchored to run time could not be replayed at all.
        """
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_sagarin(
            store,
            fetched_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
            week="01",
            page_state="in-season",
            page_date_stamp=date(2026, 9, 7),
            hfa={"rating": 3.5, "predictor": 3.5},
        )
        put_games(store, week="01", fetched_at=WEEK_01_PULLED_AT, games=[G1])
        put_games(store, week="02", fetched_at=WEEK_02_PULLED_AT, games=[G2])

        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)

        assert [entry.hfa for entry in rebuilt.applied] == [PRESEASON_HFA, 3.5]
        assert rebuilt.ratings == fold(fold(seeded, [G1], hfa=PRESEASON_HFA), [G2], hfa=3.5)

    def test_a_later_snapshot_does_not_reach_back_to_an_earlier_game(
        self, store, crosswalk
    ):
        """A value captured after a game cannot have informed it.

        Without the ``<`` this would quietly become "the newest snapshot overall",
        and every replay would drift as new snapshots landed -- the exact drift the
        verification exists to detect, introduced by the verifier.
        """
        put_sagarin(
            store,
            fetched_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
            week="04",
            page_state="in-season",
            page_date_stamp=date(2026, 9, 30),
            hfa={"rating": 9.9, "predictor": 9.9},
        )
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert {entry.hfa for entry in rebuilt.applied} == {PRESEASON_HFA}

    def test_no_snapshot_before_a_game_raises_rather_than_defaulting(self, crosswalk):
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=datetime(2026, 9, 30, 12, tzinfo=UTC))
        put_games(store, week="01", fetched_at=WEEK_01_PULLED_AT, games=[G1])

        with pytest.raises(ReplayError, match="hfa"):
            replay(store=store, season=SEASON, crosswalk=crosswalk)


class TestVerify:
    """SPEC-phase1 11 step 5: the check that makes the stored state a cache."""

    @pytest.fixture
    def rebuilt(self, store, crosswalk):
        return replay(store=store, season=SEASON, crosswalk=crosswalk)

    @pytest.fixture
    def stored(self, rebuilt) -> EloState:
        return rebuilt.as_state(generated_at=datetime(2026, 9, 20, 12, 5, tzinfo=UTC))

    def test_a_matching_state_passes(self, rebuilt, stored):
        verify(rebuilt, stored, key="elo/x.json")

    def test_a_state_that_round_tripped_through_json_still_matches(
        self, store, rebuilt, stored
    ):
        """Exact equality is only defensible if the storage round trip is exact.

        Python's float repr round-trips, so a stored rating that was ever equal
        still is -- which is what lets ``verify`` compare with ``==`` rather than a
        tolerance that would hide the drift it exists to find.
        """
        key = state_key(season=SEASON, week="02", generated_at=stored.generated_at)
        store.put_json(key, stored.model_dump(mode="json"))
        verify(rebuilt, load_state(store, key), key=key)

    def test_one_drifted_rating_is_a_mismatch(self, rebuilt, stored):
        drifted = stored.model_copy(
            update={"ratings": {**stored.ratings, "texas": stored.ratings["texas"] + 0.5}}
        )
        with pytest.raises(StateMismatchError) as excinfo:
            verify(rebuilt, drifted, key="elo/x.json")
        assert "texas" in str(excinfo.value)

    def test_the_smallest_possible_drift_is_still_a_mismatch(self, rebuilt, stored):
        """No tolerance. A cache that is nearly reproducible is not reproducible."""
        import math

        team = "ohio-state"
        nudged = stored.model_copy(
            update={
                "ratings": {**stored.ratings, team: math.nextafter(stored.ratings[team], math.inf)}
            }
        )
        with pytest.raises(StateMismatchError):
            verify(rebuilt, nudged, key="elo/x.json")

    def test_a_matching_set_of_ratings_with_a_different_game_count_is_a_mismatch(
        self, rebuilt, stored
    ):
        """Two applications that cancelled out leave every rating right.

        Nothing in a rating comparison would show it, which is why the count is
        in the document and checked beside them.
        """
        with pytest.raises(StateMismatchError, match="games_applied"):
            verify(rebuilt, stored.model_copy(update={"games_applied": 4}), key="elo/x.json")

    def test_a_missing_team_is_reported_as_missing_not_as_drift(self, rebuilt, stored):
        """It sends whoever reads it to the crosswalk rather than to the arithmetic."""
        ratings = dict(stored.ratings)
        del ratings["texas"]
        with pytest.raises(StateMismatchError) as excinfo:
            verify(rebuilt, stored.model_copy(update={"ratings": ratings}), key="elo/x.json")
        assert "absent from the stored state" in str(excinfo.value)

    def test_a_team_the_state_has_and_the_replay_does_not_is_reported_too(
        self, rebuilt, stored
    ):
        """The other direction, and the one that means the seed shrank."""
        with pytest.raises(StateMismatchError) as excinfo:
            verify(
                rebuilt,
                stored.model_copy(update={"ratings": {**stored.ratings, "atlantis": 1500.0}}),
                key="elo/x.json",
            )
        assert "not replayed at all" in str(excinfo.value)

    def test_comparing_two_different_weeks_says_so(self, rebuilt, stored):
        with pytest.raises(StateMismatchError, match="scope"):
            verify(rebuilt, stored.model_copy(update={"week": "03"}), key="elo/x.json")

    def test_the_message_names_the_evidence(self, rebuilt, stored):
        """A red run at 12:30 on a Sunday is read by one person once."""
        drifted = stored.model_copy(
            update={"ratings": {**stored.ratings, "texas": 1.0}}
        )
        with pytest.raises(StateMismatchError) as excinfo:
            verify(rebuilt, drifted, key="elo/season=2026/week=02/x.json")
        message = str(excinfo.value)
        assert "elo/season=2026/week=02/x.json" in message
        assert rebuilt.seeded_from in message
        assert "regenerate" in message


class TestNewestStateKey:
    def test_an_empty_prefix_is_none_not_an_error(self, store):
        """Normal before the first scored week: SPEC-phase1 8 writes these Sunday."""
        assert newest_state_key(store, season=SEASON, week="02") is None

    def test_the_newest_write_wins(self, store):
        """State is write-once, so regenerating leaves both. The newest is current."""
        older = state_key(
            season=SEASON, week="02", generated_at=datetime(2026, 9, 20, 12, tzinfo=UTC)
        )
        newer = state_key(
            season=SEASON, week="02", generated_at=datetime(2026, 9, 27, 12, tzinfo=UTC)
        )
        store.put_json(older, {"ratings": {}})
        store.put_json(newer, {"ratings": {}})
        assert newest_state_key(store, season=SEASON, week="02") == newer

    def test_a_neighbouring_week_is_not_offered(self, store):
        store.put_json(
            state_key(
                season=SEASON, week="03", generated_at=datetime(2026, 9, 27, 12, tzinfo=UTC)
            ),
            {"ratings": {}},
        )
        assert newest_state_key(store, season=SEASON, week="02") is None


class TestTheCommand:
    """``cfb elo replay`` -- SPEC-phase1 11 step 5 as a human types it.

    The store is passed as ``file://`` so this exercises the same argument path a
    real run takes. No network: ``FileSnapshotStore`` and the committed crosswalk
    are all it touches.
    """

    @pytest.fixture
    def rooted(self, tmp_path, store):
        """The in-memory season, copied to disk under a ``file://`` root."""
        from cfb.storage import FileSnapshotStore

        disk = FileSnapshotStore(tmp_path)
        for key, data in sorted(store._objects.items()):  # noqa: SLF001 - the test store
            disk.put_bytes(key, data, "application/octet-stream")
        return tmp_path, disk

    def test_a_replay_with_no_stored_state_exits_zero_and_says_why(self, rooted, capsys):
        root, _ = rooted
        assert main(["elo", "replay", "--season", "2026", "--store", f"file://{root}"]) == 0

        out = capsys.readouterr().out
        assert "event=elo_replay" in out
        assert "games=3" in out
        assert "event=elo_verify" in out
        assert "reason=no_stored_state" in out

    def test_a_matching_state_verifies(self, rooted, crosswalk, capsys):
        root, disk = rooted
        rebuilt = replay(store=disk, season=SEASON, crosswalk=crosswalk)
        generated_at = datetime(2026, 9, 20, 12, 5, tzinfo=UTC)
        disk.put_json(
            state_key(season=SEASON, week="02", generated_at=generated_at),
            rebuilt.as_state(generated_at=generated_at).model_dump(mode="json"),
        )

        assert main(["elo", "replay", "--season", "2026", "--store", f"file://{root}"]) == 0
        assert "event=elo_verify" in capsys.readouterr().out.replace("result=skip", "")

    def test_a_drifted_state_is_exit_1_and_a_named_error(self, rooted, crosswalk, capsys):
        """The red run §3.5 is worth. A cache nobody can regenerate is not a cache."""
        root, disk = rooted
        rebuilt = replay(store=disk, season=SEASON, crosswalk=crosswalk)
        generated_at = datetime(2026, 9, 20, 12, 5, tzinfo=UTC)
        state = rebuilt.as_state(generated_at=generated_at)
        disk.put_json(
            state_key(season=SEASON, week="02", generated_at=generated_at),
            state.model_copy(
                update={"ratings": {**state.ratings, "texas": 1234.5}}
            ).model_dump(mode="json"),
        )

        assert main(["elo", "replay", "--season", "2026", "--store", f"file://{root}"]) == 1
        assert "StateMismatchError" in capsys.readouterr().err

    def test_through_week_accepts_a_bare_number(self, rooted, capsys):
        """SPEC-phase1 11 writes ``04``; a person at a terminal writes ``1``."""
        root, _ = rooted
        assert (
            main(
                ["elo", "replay", "--season", "2026", "--through-week", "1",
                 "--store", f"file://{root}"]
            )
            == 0
        )
        assert "week=01 " in capsys.readouterr().out

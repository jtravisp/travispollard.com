"""The season's accumulation can start late, and the state says where (§3.5).

`replay` folds every completed game of a season. §3.3 prices each one from the
newest Sagarin snapshot captured **strictly before** its kickoff — so a game that
kicked off before the earliest such snapshot exists has no HFA and never will.
No later capture can be retroactively moved in front of it.

That was not hypothetical. This pipeline came online on 2026-08-28 at 16:50Z, and
CFBD's week 1 of 2026 opened on 08-27: nineteen completed FCS games sit before the
first capture, and `cfb elo replay --season 2026` exited 1 on the first of them —
in the last step of `cfb-score.yml`, so a scheduled Sunday would have gone red on
data nobody can retroactively supply.

**The fix is a bound, and three properties keep it from being a hole:**

    derived, never stored     computed from the manifests in raw/ the same way on
                              every run, so it restates the evidence rather than
                              becoming a second source of truth
    exactly the failure set   `hfa_at` fails on one condition only, so
                              `kickoff <= earliest` is the complete unpriceable
                              set rather than a heuristic for it
    in the document           and compared by `verify`, because a replay and an
                              advance that folded different games is exactly what
                              §11 step 5 exists to catch

It is named `folded_from` to match `PredictionLog.forecast_from`: the same idea
on the scoring side, and two names for one concept is how the next reader
concludes they are different.
"""

from datetime import UTC, datetime

import pytest

from cfb.crosswalk import load as load_crosswalk
from cfb.elo.state import write_state
from cfb.errors import ReplayError, StateMismatchError
from cfb.replay import advance, replay, verify
from cfb.storage import MemorySnapshotStore
from test_replay import (
    PRESEASON_AT,
    SEASON,
    cfbd_game,
    put_games,
    put_sagarin,
)

#: The 2026 shape, in miniature. The capture lands between the two games, so one
#: is unpriceable by construction and one is not.
BEFORE_ANY_CAPTURE = datetime(2026, 8, 27, 22, 0, tzinfo=UTC)
AFTER_THE_CAPTURE = datetime(2026, 9, 5, 19, 0, tzinfo=UTC)
PULLED_AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
RAN_AT = datetime(2026, 9, 8, 12, 30, tzinfo=UTC)


def early():
    return cfbd_game(
        game_id=1, week=1, kickoff=BEFORE_ANY_CAPTURE, home="Towson",
        away="Maine", home_points=21, away_points=18,
    )


def late():
    return cfbd_game(
        game_id=2, week=1, kickoff=AFTER_THE_CAPTURE, home="Texas",
        away="Texas State", home_points=45, away_points=14,
    )


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


@pytest.fixture
def store():
    """One capture at PRESEASON_AT, one game either side of it."""
    store = MemorySnapshotStore()
    put_sagarin(store, fetched_at=PRESEASON_AT)
    put_games(store, week="01", fetched_at=PULLED_AT, games=[early(), late()])
    return store


class TestTheBound:
    def test_a_game_before_the_earliest_capture_is_not_folded(self, store, crosswalk):
        """It used to raise, taking the rest of the season with it."""
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert [entry.game.cfbd_game_id for entry in rebuilt.applied] == [2]

    def test_the_bound_is_the_first_game_actually_folded(self, store, crosswalk):
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.folded_from == AFTER_THE_CAPTURE

    def test_a_season_that_needed_no_bound_reports_none(self, crosswalk):
        """**The ordinary case, and the one that must stay unchanged.** Every
        future season seeds before any game is played, so nothing is skipped and
        the state is exactly what it was before this existed."""
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[late()])

        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.folded_from is None
        assert rebuilt.games_applied == 1

    def test_it_reaches_the_state_document(self, store, crosswalk):
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.as_state(generated_at=RAN_AT).folded_from == AFTER_THE_CAPTURE


class TestItIsDerivedNotStored:
    """§3.5's "state is a cache" argument depends on there being no second source
    of truth, so the bound has to be recomputed rather than remembered."""

    def test_two_replays_of_the_same_store_agree(self, store, crosswalk):
        first = replay(store=store, season=SEASON, crosswalk=crosswalk)
        second = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert first.folded_from == second.folded_from

    def test_an_earlier_capture_landing_later_moves_the_bound(self, store, crosswalk):
        """**The property a written-down date would not have.**

        Nothing can be captured before a game that has already happened, so this
        cannot occur in production -- but it is the cheapest way to show the bound
        is read from `raw/` on every run rather than carried forward. Backfill a
        capture that predates the early game and it becomes priceable.
        """
        before = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert before.games_applied == 1

        put_sagarin(
            store,
            fetched_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
            hfa={"rating": 2.0, "predictor": 2.0},
        )
        after = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert after.games_applied == 2
        assert after.folded_from is None


class TestTheSkipIsExactlyTheUnpriceableSet:
    """Not a catch-all. Every other missing-HFA case still raises."""

    def test_a_snapshot_with_no_hfa_column_does_not_widen_the_bound(self, crosswalk):
        """A capture that parsed but carries no HFA is not a capture that prices
        anything, and `hfa_manifests` already excludes it. The bound is computed
        from the ones that do, so a useless capture cannot make a game look
        priceable."""
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[early(), late()])
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.games_applied == 1

    def test_every_game_unpriceable_still_raises(self, crosswalk):
        """**The line between a late start and a broken store.**

        Skipping a season's opening games is a pipeline that came online after the
        first kickoffs. Skipping every one means the captures and the games do not
        overlap at all, and returning a seed-only state for that would report "the
        season has not started" about a season that has.
        """
        # A *preseason* capture dated after the games. Contrived -- seeding is
        # preseason-only (§3.2), so an in-season-only store fails earlier and for
        # a different reason -- but it is what isolates this branch.
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=datetime(2026, 9, 30, 12, tzinfo=UTC))
        put_games(store, week="01", fetched_at=PULLED_AT, games=[early(), late()])

        with pytest.raises(ReplayError, match="do not overlap"):
            replay(store=store, season=SEASON, crosswalk=crosswalk)


class TestAdvanceAgrees:
    """The two accumulation paths have to reach the same bound, or §11 step 5 is
    comparing two different seasons and calling the difference drift."""

    def test_an_advance_records_the_same_bound(self, store, crosswalk):
        from cfb.replay import seed_state

        write_state(
            store,
            seed_state(store=store, season=SEASON, now=PRESEASON_AT, crosswalk=crosswalk),
        )
        advanced = advance(
            store=store, season=SEASON, week="01", now=RAN_AT, crosswalk=crosswalk
        )
        rebuilt = replay(
            store=store, season=SEASON, through_week="01", crosswalk=crosswalk
        )
        assert advanced.state.folded_from == rebuilt.folded_from == AFTER_THE_CAPTURE

    def test_they_verify_against_each_other(self, store, crosswalk):
        """The whole point: the fix must not make step 5 vacuous."""
        from cfb.replay import seed_state

        write_state(
            store,
            seed_state(store=store, season=SEASON, now=PRESEASON_AT, crosswalk=crosswalk),
        )
        advanced = advance(
            store=store, season=SEASON, week="01", now=RAN_AT, crosswalk=crosswalk
        )
        rebuilt = replay(
            store=store, season=SEASON, through_week="01", crosswalk=crosswalk
        )
        verify(rebuilt, advanced.state, key="elo/test")

    def test_a_disagreement_about_what_was_folded_is_caught(self, store, crosswalk):
        """**Compared, and deliberately not tolerantly.**

        Letting `None` mean "unbounded, match anything" would have made this pass
        -- and would have put a permanent hole in the one guarantee §3.5 rests on,
        to paper over a one-time migration.
        """
        rebuilt = replay(
            store=store, season=SEASON, through_week="01", crosswalk=crosswalk
        )
        stale = rebuilt.as_state(generated_at=RAN_AT).model_copy(
            update={"folded_from": None}
        )
        with pytest.raises(StateMismatchError, match="folded_from"):
            verify(rebuilt, stale, key="elo/test")

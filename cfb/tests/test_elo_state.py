"""Writing the stored Elo state, and the check that it is only a cache (§3.5).

Two paths reach a season's ratings and this file is mostly about the one property
that matters between them:

    replay    seed, then every completed game of the season in kickoff order
    advance   last week's stored ratings, then this week's completed games

`advance` is what the Sunday run of §8 calls: one week's arithmetic onto ratings
it read rather than derived. `replay` folds the whole season from the seed and
reads nothing but `raw/`. §11 step 5 asserts they agree.

They are *not* different in I/O — both walk every week's newest `/games` capture,
because a postponed game can appear under any of them. The difference is the
accumulation path, and that is the difference that matters.

**The agreement is only worth asserting because it can fail.** A writer
implemented as `replay() -> write` would satisfy step 5 perfectly and prove
nothing, so `TestTheChainAgreesWithAReplay` is paired with two classes that show
the comparison doing real work:

- `TestTheChainCatchesUp` — a missed Sunday and a postponed game both look like
  divergences and are not. The incremental batch is bounded by the previous
  state's kickoff cutoff as well as by the week, so the next run absorbs whatever
  the last one missed and the chain lands where a replay does.
- `TestWhereTheyDiverge` — what genuinely goes stale: a score corrected after its
  game was already folded in, and a regeneration that ran backward into an
  earlier week.

## The builders come from `test_replay.py`

Imported rather than copied. The store layout a replay reads is the store layout
an advance reads, and two hand-maintained copies of a manifest builder is how the
two test files start exercising subtly different buckets. `test_replay.py` owns
them because it needed them first.

Its `G1`/`G2`/`G3` fixture is built around a week 1 game played after week 2's,
which is exactly the case the kickoff cutoff exists for — so it is reused here,
and this file adds a clean chain where kickoff order and week order agree.
"""

from datetime import UTC, datetime

import pytest

from cfb.cli import main
from cfb.crosswalk import load as load_crosswalk
from cfb.elo import EloState
from cfb.elo.state import (
    load_state,
    newest_state_key,
    partition_position,
    previous_state,
    season_states,
    write_state,
)
from cfb.errors import ReplayError, SeedStateError, SnapshotExistsError, StateMismatchError
from cfb.replay import advance, replay, seed_state, verify
from cfb.storage import FileSnapshotStore, MemorySnapshotStore
from test_replay import G1 as POSTPONED_W1
from test_replay import G2 as POSTPONED_W2
from test_replay import G3 as PLAYED_LATE
from test_replay import PRESEASON_AT, PRESEASON_HFA, SEASON, cfbd_game, put_games, put_sagarin

# --- a clean three-week chain: kickoff order and week order agree -------------

W1 = cfbd_game(
    game_id=201, week=1, kickoff=datetime(2026, 9, 5, 23, 0, tzinfo=UTC),
    home="Ohio State", away="Michigan", home_points=31, away_points=24,
)
W2 = cfbd_game(
    game_id=202, week=2, kickoff=datetime(2026, 9, 12, 23, 0, tzinfo=UTC),
    home="Michigan", away="Texas", home_points=21, away_points=17,
)
W3 = cfbd_game(
    game_id=203, week=3, kickoff=datetime(2026, 9, 19, 23, 0, tzinfo=UTC),
    home="Texas", away="Ohio State", home_points=28, away_points=27,
)
UNPLAYED_W3 = cfbd_game(
    game_id=204, week=3, kickoff=datetime(2026, 9, 19, 23, 30, tzinfo=UTC),
    home="USC", away="UCLA", home_points=None, away_points=None,
)

#: When each week's Sunday run fires. Every one is after that week's games and
#: before the next week's, which is what §8's schedule actually produces.
SEEDED_AT = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
RAN_AT = {
    "01": datetime(2026, 9, 6, 12, 30, tzinfo=UTC),
    "02": datetime(2026, 9, 13, 12, 30, tzinfo=UTC),
    "03": datetime(2026, 9, 20, 12, 30, tzinfo=UTC),
}


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


@pytest.fixture
def store():
    """Three weeks played, captured the Sunday after each."""
    store = MemorySnapshotStore()
    put_sagarin(store, fetched_at=PRESEASON_AT)
    put_games(store, week="01", fetched_at=RAN_AT["01"], games=[W1])
    put_games(store, week="02", fetched_at=RAN_AT["02"], games=[W2])
    put_games(store, week="03", fetched_at=RAN_AT["03"], games=[W3, UNPLAYED_W3])
    return store


def seed_and_write(store, crosswalk, *, now=SEEDED_AT) -> EloState:
    state = seed_state(store=store, season=SEASON, now=now, crosswalk=crosswalk)
    write_state(store, state)
    return state


def run_chain(store, crosswalk, weeks=("01", "02", "03")) -> list[EloState]:
    """Seed, then one `advance` per week, exactly as §8's Sundays would."""
    seed_and_write(store, crosswalk)
    written = []
    for week in weeks:
        advanced = advance(
            store=store, season=SEASON, week=week, now=RAN_AT[week], crosswalk=crosswalk
        )
        write_state(store, advanced.state)
        written.append(advanced.state)
    return written


# --- the document -------------------------------------------------------------


class TestPartitionOrder:
    """`preseason` sorts after `postseason` as a string and before it as a season."""

    def test_the_season_runs_preseason_then_weeks_then_postseason(self):
        weeks = ["preseason", *[f"{n:02d}" for n in range(1, 16)], "postseason"]
        positions = [partition_position(week) for week in weeks]
        assert positions == sorted(positions)
        assert len(set(positions)) == len(positions)

    def test_lexicographic_order_would_have_been_wrong(self):
        """The reason this is a function and not `sorted()` at the call site."""
        assert partition_position("preseason") < partition_position("postseason")
        assert "preseason" > "postseason"

    @pytest.mark.parametrize("week", ["0", "4", "16", "00", "week1", "", "season"])
    def test_an_unknown_partition_raises_rather_than_sorting_somewhere(self, week):
        """A value this cannot place would sort plausibly and break the chain."""
        with pytest.raises(ReplayError):
            partition_position(week)


class TestWriteOnce:
    """§3.5 gives state `raw/`'s discipline: timestamped, nothing overwritten."""

    def test_a_state_round_trips_exactly(self, store, crosswalk):
        """Exact, because `verify` compares with `==` and no tolerance.

        If the writer's float serialisation lost a bit, every replay check would
        fail against a state that was correct when written — and the failure would
        look like model drift rather than like a storage bug.
        """
        state = seed_and_write(store, crosswalk)
        key = newest_state_key(store, season=SEASON, week="preseason")
        assert load_state(store, key).ratings == state.ratings

    def test_rewriting_the_same_key_raises(self, store, crosswalk):
        """`put_bytes`, not `put_json`. The manifest is the mutable object, not this."""
        state = seed_and_write(store, crosswalk)
        with pytest.raises(SnapshotExistsError):
            write_state(store, state)

    def test_regenerating_writes_a_new_key_and_leaves_the_old_one(self, store, crosswalk):
        """What a re-run does. The superseded state stays and the newest wins."""
        first = seed_and_write(store, crosswalk)
        second = seed_state(
            store=store, season=SEASON,
            now=datetime(2026, 8, 29, 9, 0, tzinfo=UTC), crosswalk=crosswalk,
        )
        second_key = write_state(store, second)

        keys = store.list_keys("elo/season=2026/week=preseason/")
        assert len(keys) == 2
        assert newest_state_key(store, season=SEASON, week="preseason") == second_key
        assert first.ratings == second.ratings

    def test_the_stored_json_is_readable_at_a_terminal(self, store, crosswalk):
        """§11's verification is `aws s3 cp <key> -`, not a formatter."""
        seed_and_write(store, crosswalk)
        key = newest_state_key(store, season=SEASON, week="preseason")
        assert store.get_bytes(key).startswith(b"{\n  ")


class TestSeedState:
    def test_it_is_the_preseason_partition_with_no_games(self, store, crosswalk):
        state = seed_and_write(store, crosswalk)
        assert state.week == "preseason"
        assert state.games_applied == 0
        assert len(state.ratings) == 266

    def test_it_names_the_page_it_came_from(self, store, crosswalk):
        """A state that cannot name its own seed cannot be rebuilt (§3.5)."""
        state = seed_and_write(store, crosswalk)
        assert state.seeded_from.startswith(f"raw/sagarin/season={SEASON}/week=preseason/")

    def test_a_season_with_no_preseason_capture_raises(self, crosswalk):
        store = MemorySnapshotStore()
        put_games(store, week="01", fetched_at=RAN_AT["01"], games=[W1])
        with pytest.raises(ReplayError, match="preseason"):
            seed_state(store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk)


class TestPreviousState:
    def test_nothing_before_the_seed(self, store, crosswalk):
        seed_and_write(store, crosswalk)
        assert previous_state(store, season=SEASON, week="preseason") is None

    def test_week_one_builds_on_the_seed(self, store, crosswalk):
        seed_and_write(store, crosswalk)
        found = previous_state(store, season=SEASON, week="01")
        assert found is not None
        assert found.state.week == "preseason"

    def test_it_takes_the_nearest_earlier_week_not_week_minus_one(self, store, crosswalk):
        """A missed Sunday leaves a hole, and one hole must not block every week after.

        Building on the older state keeps the pipeline moving and stays detectable:
        the result is short a week of games, so a replay disagrees with it.
        `TestWhereTheyDiverge` asserts that it does.
        """
        run_chain(store, crosswalk, weeks=("01",))
        found = previous_state(store, season=SEASON, week="03")
        assert found is not None
        assert found.state.week == "01"

    def test_it_takes_the_newest_generation_of_that_week(self, store, crosswalk):
        run_chain(store, crosswalk, weeks=("01",))
        regenerated = advance(
            store=store, season=SEASON, week="01",
            now=datetime(2026, 9, 8, 9, 0, tzinfo=UTC), crosswalk=crosswalk,
        )
        newer_key = write_state(store, regenerated.state)

        found = previous_state(store, season=SEASON, week="02")
        assert found.key == newer_key

    def test_a_stray_object_under_the_prefix_is_ignored_not_fatal(self, store, crosswalk):
        """Refusing to read a season's state because of one hand-placed file would
        be a failure caused entirely by the stray file.
        """
        seed_and_write(store, crosswalk)
        store.put_bytes("elo/season=2026/notes.txt", b"scratch", "text/plain")
        store.put_bytes("elo/season=2026/week=99/x.json", b"{}", "application/json")

        assert len(season_states(store, season=SEASON)) == 1


class TestAdvance:
    def test_it_applies_only_that_week(self, store, crosswalk):
        seed_and_write(store, crosswalk)
        advanced = advance(
            store=store, season=SEASON, week="01", now=RAN_AT["01"], crosswalk=crosswalk
        )
        assert [entry.game.cfbd_game_id for entry in advanced.applied] == [201]

    def test_the_season_total_accumulates_while_the_week_count_does_not(
        self, store, crosswalk
    ):
        """`games_applied` on the state is the season; on the `Advance` it is the week.

        The distinction is load-bearing: §3.5's stored count is what a replay
        compares against, and a per-week number there would never match.
        """
        states = run_chain(store, crosswalk)
        assert [state.games_applied for state in states] == [1, 2, 3]

    def test_the_seed_is_carried_forward_not_re_derived(self, store, crosswalk):
        """Every state in a season names one origin. A chain whose seed changed
        halfway is a chain that cannot be replayed.
        """
        seeded = seed_and_write(store, crosswalk)
        states = run_chain_after_seed = [
            advance(store=store, season=SEASON, week=week, now=RAN_AT[week],
                    crosswalk=crosswalk).state
            for week in ("01",)
        ]
        for state in run_chain_after_seed:
            assert state.seeded_from == seeded.seeded_from
        assert states  # the loop ran

    def test_an_unplayed_game_is_not_applied(self, store, crosswalk):
        states = run_chain(store, crosswalk)
        assert states[-1].games_applied == 3  # not 4; UNPLAYED_W3 has no result

    def test_a_week_with_no_results_still_writes_a_state(self, store, crosswalk):
        """A fully postponed week, or a run that fires before anything lands.

        The ratings do not move, the cutoff is carried forward, and a state still
        belongs at that week so the next advance has something to build on.
        """
        run_chain(store, crosswalk)
        advanced = advance(
            store=store, season=SEASON, week="04",
            now=datetime(2026, 9, 27, 12, 30, tzinfo=UTC), crosswalk=crosswalk,
        )
        assert advanced.games_applied == 0
        assert advanced.state.ratings == advanced.previous.state.ratings
        assert advanced.state.through_kickoff == advanced.previous.state.through_kickoff
        assert write_state(store, advanced.state).endswith(".json")

    def test_the_cutoff_is_the_last_kickoff_applied(self, store, crosswalk):
        """What lets the next advance know where this one stopped."""
        states = run_chain(store, crosswalk)
        assert [state.through_kickoff for state in states] == [
            datetime(2026, 9, 5, 23, 0, tzinfo=UTC),
            datetime(2026, 9, 12, 23, 0, tzinfo=UTC),
            datetime(2026, 9, 19, 23, 0, tzinfo=UTC),
        ]

    def test_the_seed_has_no_cutoff(self, store, crosswalk):
        assert seed_and_write(store, crosswalk).through_kickoff is None

    def test_a_game_already_applied_is_not_applied_again(self, store, crosswalk):
        """The freshness half of the cut. Re-running the latest week must be a
        no-op when nothing new has landed, or a regenerate would double-count.
        """
        run_chain(store, crosswalk)
        again = advance(
            store=store, season=SEASON, week="03",
            now=datetime(2026, 9, 21, 9, 0, tzinfo=UTC), crosswalk=crosswalk,
        )
        assert again.previous.state.week == "02"
        assert again.games_applied == 1  # week 3's game, once
        assert again.state.games_applied == 3

    def test_advancing_with_no_seed_says_what_to_run(self, store, crosswalk):
        with pytest.raises(ReplayError) as excinfo:
            advance(store=store, season=SEASON, week="01",
                    now=RAN_AT["01"], crosswalk=crosswalk)
        assert "cfb elo seed" in str(excinfo.value)

    def test_it_names_the_state_it_built_on(self, store, crosswalk):
        """A wrong answer here is almost always a wrong predecessor."""
        seed_and_write(store, crosswalk)
        advanced = advance(
            store=store, season=SEASON, week="01", now=RAN_AT["01"], crosswalk=crosswalk
        )
        assert advanced.previous.key.endswith(".json")
        assert "week=preseason" in advanced.previous.key


# --- the property step 5 exists to check --------------------------------------


class TestTheChainAgreesWithAReplay:
    """§11 step 5, offline. The reason the stored state is a cache."""

    def test_the_chain_agrees_with_a_replay(self, store, crosswalk):
        run_chain(store, crosswalk)
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        key = newest_state_key(store, season=SEASON, week="03")

        verify(rebuilt, load_state(store, key), key=key)  # must not raise

    def test_the_ratings_are_bit_for_bit_identical(self, store, crosswalk):
        """Not approximately. Two different accumulation orders over the same
        games, and floating point gives the same bits because the games each
        `update` touches are disjoint per step.
        """
        states = run_chain(store, crosswalk)
        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        assert rebuilt.ratings == states[-1].ratings

    @pytest.mark.parametrize("week", ["01", "02", "03"])
    def test_every_intermediate_week_agrees_too(self, store, crosswalk, week):
        """Not just the last one. A chain can be wrong in the middle and right at
        the end if two errors cancel, and only the per-week check finds that.
        """
        run_chain(store, crosswalk)
        rebuilt = replay(
            store=store, season=SEASON, through_week=week, crosswalk=crosswalk
        )
        key = newest_state_key(store, season=SEASON, week=week)
        verify(rebuilt, load_state(store, key), key=key)

    def test_the_two_paths_really_are_different(self, store, crosswalk):
        """The premise. If `advance` were `replay()` under another name, every
        assertion above would hold and none of them would mean anything.

        The difference is the accumulation path, not the I/O — both walk every
        week's newest capture, because a postponed game can appear under any of
        them. A replay through week 3 folds three games onto a seed it computed;
        an advance to week 3 folds one onto ratings it read and did not derive.
        """
        run_chain(store, crosswalk)
        rebuilt = replay(store=store, season=SEASON, through_week="03", crosswalk=crosswalk)
        advanced = advance(
            store=store, season=SEASON, week="03", now=RAN_AT["03"], crosswalk=crosswalk
        )

        assert rebuilt.games_applied == 3
        assert advanced.games_applied == 1
        assert advanced.state.games_applied == 3

    def test_a_replay_needs_no_stored_state_and_an_advance_cannot_run_without_one(
        self, store, crosswalk
    ):
        """The structural difference, and why one can check the other.

        `replay` reads `raw/` only, so it cannot be contaminated by the object it
        is checking. `advance` cannot even start without that object.
        """
        replay(store=store, season=SEASON, crosswalk=crosswalk)  # no state exists yet
        with pytest.raises(ReplayError):
            advance(store=store, season=SEASON, week="01",
                    now=RAN_AT["01"], crosswalk=crosswalk)


@pytest.fixture
def postponed(crosswalk):
    """A season where a week 1 game was played after week 2's, and the chain was
    already written before it landed.

    `test_replay.py`'s `G3` is that game. The chain runs for weeks 01 and 02
    against the captures that existed at the time, and only then does a re-pull of
    week 01 bring the postponed result in — which is the order these things happen
    in.
    """
    store = MemorySnapshotStore()
    put_sagarin(store, fetched_at=PRESEASON_AT)
    put_games(store, week="01", fetched_at=RAN_AT["01"], games=[POSTPONED_W1])
    put_games(store, week="02", fetched_at=RAN_AT["02"], games=[POSTPONED_W2])

    seed_and_write(store, crosswalk)
    for week in ("01", "02"):
        write_state(store, advance(store=store, season=SEASON, week=week,
                                   now=RAN_AT[week], crosswalk=crosswalk).state)

    put_games(
        store, week="01",
        fetched_at=datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
        games=[POSTPONED_W1, PLAYED_LATE],
    )
    return store, crosswalk


class TestWhereTheyDiverge:
    """The failures the comparison has to be able to catch.

    Every one leaves ratings that are complete, conserved and plausible. Nothing
    but this check would notice, which is the whole argument of §3.5.
    """

    def test_a_corrected_score_is_caught(self, store, crosswalk):
        """CFBD backfills. A week re-pulled after its state was written is new
        evidence, and the state is stale rather than wrong.
        """
        run_chain(store, crosswalk)
        put_games(
            store, week="01",
            fetched_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
            games=[dict(W1, homePoints=45)],
        )

        rebuilt = replay(store=store, season=SEASON, crosswalk=crosswalk)
        key = newest_state_key(store, season=SEASON, week="03")
        with pytest.raises(StateMismatchError):
            verify(rebuilt, load_state(store, key), key=key)

    def test_regenerating_an_earlier_week_strands_a_later_game_and_is_caught(
        self, postponed
    ):
        """**The sharp edge of the incremental path, and the reason it is tested.**

        An advance's batch has to be a contiguous block of the season in kickoff
        order, because that is the only way the chain composes to what a single
        sorted pass produces. Re-running week 01 alone breaks that: its batch
        becomes {G1, G3} — every week 1 game, including the one played on Sep 17 —
        so its cutoff jumps past G2 on Sep 12, and week 02's advance then finds
        nothing newer to apply. G2 is stranded.

        So regeneration goes *forward from the latest state*, never backward into
        an earlier week. The recovery that does work is the next test.

        This is asserted rather than commented so that the constraint is a
        property: if a future selection rule made backward regeneration safe, this
        test is what says so by failing.
        """
        store, crosswalk = postponed
        for week, when in (("01", datetime(2026, 9, 21, 9, 0, tzinfo=UTC)),
                           ("02", datetime(2026, 9, 21, 9, 1, tzinfo=UTC))):
            write_state(store, advance(store=store, season=SEASON, week=week,
                                       now=when, crosswalk=crosswalk).state)

        rebuilt = replay(store=store, season=SEASON, through_week="02", crosswalk=crosswalk)
        key = newest_state_key(store, season=SEASON, week="02")
        with pytest.raises(StateMismatchError):
            verify(rebuilt, load_state(store, key), key=key)


class TestTheChainCatchesUp:
    """Two things that look like divergences and are not, because of the kickoff cut.

    Both were divergences under a purely week-scoped batch, and both are why the
    batch is bounded by the previous state's cutoff as well as by the week. A rule
    that could only ever go forward one week at a time would leave the chain
    permanently out of step after either.
    """

    def test_a_missed_week_is_absorbed_by_the_next_run(self, store, crosswalk):
        """Week 2's Sunday never ran, so week 3 builds on week 1's state.

        Week 3's batch is everything after week 1's cutoff and no later than week
        3 — which is week 2's game and week 3's, in kickoff order. The chain ends
        up exactly where a replay does, so one missed Sunday costs nothing and
        needs no intervention.
        """
        run_chain(store, crosswalk, weeks=("01", "03"))
        rebuilt = replay(store=store, season=SEASON, through_week="03", crosswalk=crosswalk)
        key = newest_state_key(store, season=SEASON, week="03")

        assert load_state(store, key).games_applied == 3
        verify(rebuilt, load_state(store, key), key=key)  # must not raise

    def test_a_postponed_game_is_absorbed_by_the_next_week(self, postponed):
        """§5.1's weather case. `PLAYED_LATE` is a week 1 game played after week 2.

        Week 01's state was written before it existed. Week 02's advance takes it
        anyway — a week 1 game passes the season cut, and a Sep 17 kickoff passes
        the freshness cut — and sorts it after week 2's Sep 12 game rather than
        ahead of it, which is where a replay puts it too.
        """
        store, crosswalk = postponed
        advanced = advance(
            store=store, season=SEASON, week="02",
            now=datetime(2026, 9, 21, 9, 0, tzinfo=UTC), crosswalk=crosswalk,
        )
        write_state(store, advanced.state)

        assert [entry.game.cfbd_game_id for entry in advanced.applied] == [102, 103]
        rebuilt = replay(store=store, season=SEASON, through_week="02", crosswalk=crosswalk)
        key = newest_state_key(store, season=SEASON, week="02")
        verify(rebuilt, load_state(store, key), key=key)  # must not raise

    def test_the_stale_earlier_week_still_reports_as_stale(self, postponed):
        """Week 01's state predates the postponed game and says so when asked.

        Honest rather than a problem: that state *is* what the model believed on
        the Sunday after week 1. The chain is what has to be right, and it is.
        """
        store, crosswalk = postponed
        rebuilt = replay(store=store, season=SEASON, through_week="01", crosswalk=crosswalk)
        key = newest_state_key(store, season=SEASON, week="01")
        with pytest.raises(StateMismatchError):
            verify(rebuilt, load_state(store, key), key=key)


# --- the commands -------------------------------------------------------------


class TestTheCommands:
    """`cfb elo seed`, `cfb elo advance`, `cfb elo replay` — §9, as typed."""

    @pytest.fixture
    def rooted(self, tmp_path, store):
        disk = FileSnapshotStore(tmp_path)
        for key, data in sorted(store._objects.items()):  # noqa: SLF001 - the test store
            disk.put_bytes(key, data, "application/octet-stream")
        return f"file://{tmp_path}", disk

    @staticmethod
    def sunday(url, week: str) -> int:
        """One `cfb elo advance`, with the clock supplied.

        `now` is a seam on `main` for exactly this reason: the generation stamp is
        second-resolution and part of the key, so two commands in the same second
        would collide on a write-once object.
        """
        return main(
            ["elo", "advance", "--season", "2026", "--week", week, "--store", url],
            now=RAN_AT[f"{int(week):02d}"],
        )

    def test_the_whole_sunday_sequence_runs_green(self, rooted, capsys):
        """Seed, three weeks, then step 5 verifies the chain it just built."""
        url, _ = rooted
        assert main(["elo", "seed", "--season", "2026", "--store", url],
                    now=SEEDED_AT) == 0
        for week in ("1", "2", "3"):
            assert self.sunday(url, week) == 0
        assert main(["elo", "replay", "--season", "2026", "--store", url]) == 0

        out = capsys.readouterr().out
        assert "event=elo_state" in out
        assert "event=elo_verify" in out
        assert "reason=no_stored_state" not in out
        assert "result=skip" not in out

    def test_seed_reports_what_it_wrote(self, rooted, capsys):
        url, _ = rooted
        main(["elo", "seed", "--season", "2026", "--store", url], now=SEEDED_AT)
        out = capsys.readouterr().out
        assert "week=preseason" in out
        assert "teams=266" in out

    def test_advance_reports_the_week_and_the_season_total(self, rooted, capsys):
        url, _ = rooted
        main(["elo", "seed", "--season", "2026", "--store", url], now=SEEDED_AT)
        self.sunday(url, "1")
        self.sunday(url, "2")
        out = capsys.readouterr().out
        assert "games=1 season_games=2" in out

    def test_re_seeding_a_season_in_progress_is_refused(self, rooted, capsys):
        """§9's "refuses in-season", at the level the CLI can actually enforce it."""
        url, _ = rooted
        main(["elo", "seed", "--season", "2026", "--store", url], now=SEEDED_AT)
        self.sunday(url, "1")

        assert main(["elo", "seed", "--season", "2026", "--store", url]) == 1
        assert "SeedStateError" in capsys.readouterr().err

    def test_force_re_seeds(self, rooted, capsys):
        url, _ = rooted
        main(["elo", "seed", "--season", "2026", "--store", url], now=SEEDED_AT)
        self.sunday(url, "1")
        capsys.readouterr()

        assert main(
            ["elo", "seed", "--season", "2026", "--force", "--store", url],
            now=datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
        ) == 0
        assert "week=preseason" in capsys.readouterr().out

    def test_advancing_before_seeding_is_exit_1(self, rooted, capsys):
        url, _ = rooted
        assert self.sunday(url, "1") == 1
        assert "ReplayError" in capsys.readouterr().err

    def test_a_bare_week_number_is_accepted(self, rooted, capsys):
        """§11 writes `04`; a person at a terminal writes `4`."""
        url, _ = rooted
        main(["elo", "seed", "--season", "2026", "--store", url], now=SEEDED_AT)
        assert self.sunday(url, "1") == 0
        assert "week=01" in capsys.readouterr().out

    def test_an_illegal_week_is_a_usage_error_not_a_pipeline_failure(self, rooted):
        url, _ = rooted
        with pytest.raises(SystemExit) as excinfo:
            main(["elo", "advance", "--season", "2026", "--week", "16", "--store", url])
        assert excinfo.value.code == 2


def test_seed_state_refuses_an_in_season_page(store, crosswalk):
    """§3.2's refusal, and why it cannot fire through this path.

    `seed_state` selects its snapshot by `page_state == "preseason"`, so an
    in-season page is never a candidate — the guard in `seed()` is unreachable
    from here. It is asserted directly so the defence in depth is a property
    rather than a claim: if the selection ever loosened, this is what fails.
    """
    from cfb.elo.seed import seed
    from cfb.models import SagarinSnapshot
    from cfb.parsers.sagarin_predictions import parse_predictions
    from cfb.parsers.sagarin_ratings import parse_hfa, parse_ratings

    page = store.get_bytes(
        seed_state(
            store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk
        ).seeded_from
    ).decode("cp1252")

    in_season = SagarinSnapshot(
        fetched_at=PRESEASON_AT,
        page_date_stamp=datetime(2026, 9, 15, tzinfo=UTC).date(),
        page_state="in-season",
        hfa=parse_hfa(page),
        teams=parse_ratings(page),
        predictions=parse_predictions(page),
    )
    with pytest.raises(SeedStateError):
        seed(in_season, crosswalk)

    assert PRESEASON_HFA == 2.41  # the fixture's HFA, unchanged by any of this

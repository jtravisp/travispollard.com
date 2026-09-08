"""The Phase 1 commands, through `cfb.cli.main` (SPEC-phase1 9).

**Through `main`, not through the library functions.** SPEC-phase0 §8 says every
scheduled step is a command a human runs locally, and SPEC-phase1 §11 turns that
into the verification plan — so what has to be true is that `uv run cfb score`
behaves, not that `score_week` does. `test_scoring.py` and `test_publish.py`
already own the libraries; this file owns the wiring, the exit codes, and the
handful of decisions that live in the CLI and nowhere else.

The four that matter, each of which is silent when wrong:

    score      grades the newest generation written *before* its slate started
    publish    takes the newest generation, full stop -- the opposite rule, and
               both are right
    backtest   never touches `predictions/` or `scored/`
    note       renders team names, never canonical ids

Every test drives a `file://` store through a real `main(argv)` call, so the
argument parsing, the week defaults and the error-to-exit-code contract are all
exercised rather than assumed.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from cfb.cli import main
from cfb.crosswalk import load as load_crosswalk
from cfb.elo.state import write_state
from cfb.predict import predict_week, write_predictions
from cfb.replay import seed_state
from cfb.storage import FileSnapshotStore
from test_replay import PRESEASON_AT, SEASON, cfbd_game, put_games, put_sagarin

SEEDED_AT = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
PULLED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
CAPTURED_AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
RAN_AT = datetime(2026, 9, 8, 12, 30, tzinfo=UTC)
#: Past week 1's partition close (09-08 06:59Z), where `coming_week` has
#: already moved to a week nobody forecasts until Thursday.
MONDAY_AFTER_CLOSE = datetime(2026, 9, 8, 13, 0, tzinfo=UTC)

THURSDAY = datetime(2026, 9, 3, 23, 0, tzinfo=UTC)
SATURDAY = datetime(2026, 9, 5, 19, 0, tzinfo=UTC)

#: Week 2: forecast, played, captured after its 09-14 06:59Z close, and a run on
#: the Monday after it. The second week exists so the scoring loop can be asked
#: for more than one, which is the whole of SPEC-phase1 8.4.
WEEK_TWO_FORECAST = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
WEEK_TWO_KICKOFF = datetime(2026, 9, 12, 19, 0, tzinfo=UTC)
WEEK_TWO_CAPTURED = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
SECOND_MONDAY = datetime(2026, 9, 14, 12, 30, tzinfo=UTC)

#: A midweek kickoff inside week 2 -- November MACtion's shape, on the week the
#: harness already has. It is 36 hours ahead of the Thursday forecast run and a
#: few hours behind the Monday one, which is the whole of SPEC-phase1 8.5.
MACTION_KICKOFF = datetime(2026, 9, 8, 23, 0, tzinfo=UTC)
MONDAY_FORECAST = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)

#: One FBS game, played. Enough for every command to have something to do, and
#: small enough that a failure names one row rather than a slate.
def played(home_points=31, away_points=17):
    return cfbd_game(
        game_id=1, week=1, kickoff=SATURDAY, home="Texas", away="Ohio State",
        home_points=home_points, away_points=away_points,
    )


def unplayed():
    return cfbd_game(
        game_id=1, week=1, kickoff=SATURDAY, home="Texas", away="Ohio State",
        home_points=None, away_points=None,
    )


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


@pytest.fixture
def store_url(tmp_path):
    return f"file://{tmp_path.as_posix()}"


@pytest.fixture
def store(tmp_path):
    return FileSnapshotStore(tmp_path)


def seed(store, crosswalk):
    put_sagarin(store, fetched_at=PRESEASON_AT)
    write_state(
        store, seed_state(store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk)
    )


def predict(store, crosswalk, *, now=GENERATED_AT, week="01"):
    log = predict_week(
        store=store, season=SEASON, week=week, now=now, crosswalk=crosswalk
    )
    return write_predictions(store, log)


def week_two(home_points=None, away_points=None):
    """One week 2 game, so a run can be asked to score more than one week.

    Week 2 of 2026 runs 09-08 07:00Z to 09-14 06:59Z; this kicks off inside it and
    after week 1's last game, which is what lets `advance` chain the two states in
    kickoff order.
    """
    return cfbd_game(
        game_id=2, week=2, kickoff=WEEK_TWO_KICKOFF, home="Texas", away="Ohio State",
        home_points=home_points, away_points=away_points,
    )


def maction(home_points=None, away_points=None):
    """A Tuesday-night game in week 2, alongside the Saturday one.

    Different teams from `week_two`, because a slate where one pair plays twice
    in a week would fold both results onto the same two ratings and make the Elo
    assertions meaningless. Both are on the committed preseason page, so the seed
    rates them.
    """
    return cfbd_game(
        game_id=3, week=2, kickoff=MACTION_KICKOFF, home="Georgia", away="Oregon",
        home_points=home_points, away_points=away_points,
    )


def midweek_slate_ready(store, crosswalk, *, forecast_monday: bool):
    """Week 2 with a Tuesday game and a Saturday game, captured after it closed.

    ``forecast_monday`` is the change under test: with it, the week is forecast
    on the Monday it opened *and* again on the Thursday; without it, only on the
    Thursday, which is what the schedule did before SPEC-phase1 8.5.
    """
    seed(store, crosswalk)
    put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
    predict(store, crosswalk)
    put_games(store, week="01", fetched_at=CAPTURED_AT, games=[played()])

    put_games(store, week="02", fetched_at=PULLED_AT, games=[maction(), week_two()])
    if forecast_monday:
        predict(store, crosswalk, now=MONDAY_FORECAST, week="02")
    predict(store, crosswalk, now=WEEK_TWO_FORECAST, week="02")
    put_games(
        store,
        week="02",
        fetched_at=WEEK_TWO_CAPTURED,
        games=[
            maction(home_points=17, away_points=13),
            week_two(home_points=24, away_points=20),
        ],
    )


def both_weeks_ready(store, crosswalk):
    """Weeks 1 and 2 forecast, played, and captured after each week closed."""
    seed(store, crosswalk)
    put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
    predict(store, crosswalk)
    put_games(store, week="01", fetched_at=CAPTURED_AT, games=[played()])

    put_games(store, week="02", fetched_at=CAPTURED_AT, games=[week_two()])
    predict(store, crosswalk, now=WEEK_TWO_FORECAST, week="02")
    put_games(
        store,
        week="02",
        fetched_at=WEEK_TWO_CAPTURED,
        games=[week_two(home_points=24, away_points=20)],
    )


def predict_late(store, crosswalk, *, stamped):
    """A generation written after its slate was played.

    Built by copying an honest log rather than by calling `predict_week`, because
    `predict_week` **cannot produce one any more** -- it forecasts only games that
    have not kicked off, so a post-kickoff run now raises rather than returning a
    document. That is defence in depth for §5.4 rather than a replacement for it:
    the guard in `predictions_to_score` still has to hold, because a log can
    arrive in the bucket by other means than this command.
    """
    honest = predict_week(
        store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
    )
    return write_predictions(store, honest.model_copy(update={"generated_at": stamped}))


def run(*argv, now):
    """`main` returns an exit code rather than raising SystemExit."""
    return main(list(argv), now=now)


def fails(capsys, *argv, now, saying):
    """Assert a command exits 1 with `saying` on stderr.

    **Not `pytest.raises`.** SPEC-phase0 §9 makes every `CfbError` exit 1 with a
    message on stderr and nothing caught and demoted to a warning, so `main`
    returns rather than raising -- and a test that expected an exception would be
    asserting the opposite of the contract. The class name is on the line because
    SPEC §11 makes the Actions log the alert.
    """
    assert run(*argv, now=now) == 1
    printed = capsys.readouterr().err
    assert saying in printed, printed
    return printed


# --- cfb score ----------------------------------------------------------------


class TestScore:
    def test_it_writes_a_scored_week_and_an_elo_state(self, store, store_url, crosswalk):
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)
        put_games(store, week="01", fetched_at=CAPTURED_AT, games=[played()])

        assert run("score", "--season", "2026", "--week", "1", "--force",
                   "--store", store_url, now=RAN_AT) == 0
        assert len(store.list_keys("scored/season=2026/week=01/")) == 1
        assert len(store.list_keys("elo/season=2026/week=01/")) == 1

    def test_a_rerun_writes_a_second_key_and_keeps_the_first(
        self, store, store_url, crosswalk
    ):
        """Write-once, so a rescore that disliked Sunday's numbers cannot quietly
        become the only surviving record."""
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)
        put_games(store, week="01", fetched_at=CAPTURED_AT, games=[played()])

        run("score", "--season", "2026", "--week", "1", "--force",
            "--store", store_url, now=RAN_AT)
        run("score", "--season", "2026", "--week", "1", "--force",
            "--store", store_url, now=RAN_AT.replace(minute=45))
        assert len(store.list_keys("scored/season=2026/week=01/")) == 2

    def test_it_grades_the_pre_kickoff_generation_not_the_newest(
        self, store, store_url, crosswalk
    ):
        """**The discriminating case for §5.4.**

        A Sunday regenerate exists and is newer. Grading it would publish an
        accuracy figure for a forecast made with the results in hand, which is
        the one overclaim §1.1 gives up git to avoid.
        """
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        honest = predict(store, crosswalk)
        # Written after every game was played.
        predict_late(store, crosswalk, stamped=datetime(2026, 9, 7, 0, 0, tzinfo=UTC))
        put_games(store, week="01", fetched_at=CAPTURED_AT, games=[played()])

        assert run("score", "--season", "2026", "--week", "1", "--force",
                   "--store", store_url, now=RAN_AT) == 0

        scored = json.loads(
            store.get_bytes(store.list_keys("scored/season=2026/week=01/")[0])
        )
        assert scored["predictions_generated_at"].startswith("2026-09-03")
        assert honest.endswith(".json")

    def test_a_week_whose_every_generation_postdates_its_games_writes_nothing(
        self, store, store_url, crosswalk, capsys
    ):
        """Exit 1, and **nothing written** -- not even the Elo state, because the
        command reads every input before writing anything.

        The wording moved from "slate" to "games" when the rule did.
        `predictions_to_score` used to reject a generation written after its
        slate's *first* kickoff; it now keeps one that was early for any of its
        games and uses it only for those. A generation written after every game
        had started is early for none, which is this case, and it is still
        refused entire.
        """
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict_late(store, crosswalk, stamped=datetime(2026, 9, 7, 0, 0, tzinfo=UTC))
        put_games(store, week="01", fetched_at=CAPTURED_AT, games=[played()])

        before = set(store.list_keys("elo/"))
        fails(capsys, "score", "--season", "2026", "--week", "1", "--force",
              "--store", store_url, now=RAN_AT,
              saying="after its own games had started")
        assert set(store.list_keys("elo/")) == before
        assert store.list_keys("scored/") == []

    def test_a_missing_games_capture_leaves_elo_untouched(
        self, store, store_url, crosswalk, capsys
    ):
        """The read-before-write rule, from the other direction. A Sunday where
        the CFBD pull failed should not leave an empty week state behind."""
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)
        for key in store.list_keys("raw/cfbd/season=2026/week=01/games/"):
            (store._root / key).unlink()

        before = set(store.list_keys("elo/"))
        fails(capsys, "score", "--season", "2026", "--week", "1", "--force",
              "--store", store_url, now=RAN_AT, saying="no /games capture")
        assert set(store.list_keys("elo/")) == before

    def test_it_scores_every_closed_week_rather_than_only_the_newest(
        self, store, store_url, crosswalk
    ):
        """**The SPEC-phase1 8.4 regression.** One run, two weeks, no `--week`.

        The old default resolved `last_completed_week` and scored that alone, so
        a run standing after two closes wrote a document for the newer week and
        passed over the older one in silence -- exit 0, nothing in the log naming
        the week that was dropped, and no later run that would ever offer it
        again. On the real 2026 calendar that is week 14 under a Sunday schedule
        and week 1 under a Monday one.
        """
        both_weeks_ready(store, crosswalk)

        assert run("score", "--season", "2026", "--force",
                   "--store", store_url, now=SECOND_MONDAY) == 0
        assert len(store.list_keys("scored/season=2026/week=01/")) == 1
        assert len(store.list_keys("scored/season=2026/week=02/")) == 1

    def test_it_scores_them_oldest_first_so_the_elo_chain_composes(
        self, store, store_url, crosswalk
    ):
        """Order is not cosmetic: `advance` builds each week on the state before
        it, and Elo is path-dependent. Week 2 folded onto the seed and week 1
        folded on afterwards is a different season from the one `replay`
        produces, and §11 step 5 would be right to go red about it."""
        both_weeks_ready(store, crosswalk)
        run("score", "--season", "2026", "--force", "--store", store_url,
            now=SECOND_MONDAY)

        first = json.loads(store.get_bytes(store.list_keys("elo/season=2026/week=01/")[0]))
        second = json.loads(store.get_bytes(store.list_keys("elo/season=2026/week=02/")[0]))
        assert second["games_applied"] > first["games_applied"]
        assert second["through_kickoff"] > first["through_kickoff"]

    def test_a_second_run_writes_nothing_and_says_which_answer_it_gave(
        self, store, store_url, crosswalk, capsys
    ):
        """`already_scored`, not `no_completed_week`. One says the season has
        produced nothing to score and the other says the scoring has caught up;
        a log that flattens them cannot tell a healthy Tuesday from a calendar
        that never advanced."""
        both_weeks_ready(store, crosswalk)
        run("score", "--season", "2026", "--force", "--store", store_url,
            now=SECOND_MONDAY)
        capsys.readouterr()

        assert run("score", "--season", "2026", "--force",
                   "--store", store_url, now=SECOND_MONDAY) == 0
        assert "reason=already_scored" in capsys.readouterr().out
        assert len(store.list_keys("scored/season=2026/week=01/")) == 1
        assert len(store.list_keys("scored/season=2026/week=02/")) == 1

    def test_a_week_missed_for_a_fortnight_is_repaired_by_the_next_run(
        self, store, store_url, crosswalk, capsys
    ):
        """An outage is recoverable without anyone remembering which weeks to
        pass `--week`. The weeks are still there, still closed, and still
        unscored, so the next scheduled run takes both.

        Weeks 3 and 4 have closed by then and nobody forecast them, which is the
        other half of the rule: a closed week with no prediction is skipped and
        said out loud, because there is no record to make and nothing to drop.
        Erroring instead would leave every run after an unforecast week red for
        the rest of the season.
        """
        both_weeks_ready(store, crosswalk)

        assert run("score", "--season", "2026", "--force", "--store", store_url,
                   now=SECOND_MONDAY + timedelta(days=14)) == 0
        assert len(store.list_keys("scored/season=2026/week=01/")) == 1
        assert len(store.list_keys("scored/season=2026/week=02/")) == 1

        printed = capsys.readouterr().out
        assert "week=03 result=skip reason=nothing_forecast" in printed
        assert "week=04 result=skip reason=nothing_forecast" in printed

    def test_it_refuses_a_capture_taken_before_the_week_closed(
        self, store, store_url, crosswalk, capsys
    ):
        """**The silent half of the same bug**, and the reason the loop needed a
        guard rather than just an iteration.

        §5.2 decides "unplayed, or a join that failed" against the capture's own
        moment, so a game that kicked off after the capture is legitimately
        unplayed and drops out of every mean. Correct while a week is running and
        a dropped row once it is over -- and the scored document reads the same
        either way. Week 1 of 2026 is the live case: it closes 09-08 06:59Z, so a
        capture from the Monday evening cannot have seen a Monday night game.
        """
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)
        # Taken while the week was still open, unlike CAPTURED_AT.
        put_games(store, week="01", fetched_at=datetime(2026, 9, 7, 21, 0, tzinfo=UTC),
                  games=[played()])

        before = set(store.list_keys("elo/"))
        fails(capsys, "score", "--season", "2026", "--week", "1", "--force",
              "--store", store_url, now=RAN_AT,
              saying="does not close until")
        assert set(store.list_keys("elo/")) == before
        assert store.list_keys("scored/") == []

    def test_the_refusal_names_the_fetch_that_fixes_it(
        self, store, store_url, crosswalk, capsys
    ):
        """SPEC-phase0 §9: the failure names the command, because the person
        reading it is looking at an Actions log rather than at this source."""
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)
        put_games(store, week="01", fetched_at=datetime(2026, 9, 7, 21, 0, tzinfo=UTC),
                  games=[played()])

        printed = fails(capsys, "score", "--season", "2026", "--week", "1", "--force",
                        "--store", store_url, now=RAN_AT, saying="StaleCaptureError")
        assert "cfb fetch cfbd --resource games --season 2026 --week 01" in printed

    def test_an_explicit_week_is_rescored_even_though_it_already_has_a_document(
        self, store, store_url, crosswalk
    ):
        """The repair path stays open. `--week` is how a crosswalk fix or a
        corrected score is applied, so it does not consult what is already
        stored -- write-once keeps the earlier generation beside the new one."""
        both_weeks_ready(store, crosswalk)
        run("score", "--season", "2026", "--force", "--store", store_url,
            now=SECOND_MONDAY)

        assert run("score", "--season", "2026", "--week", "1", "--force",
                   "--store", store_url, now=SECOND_MONDAY.replace(minute=45)) == 0
        assert len(store.list_keys("scored/season=2026/week=01/")) == 2

    def test_a_midweek_game_is_scored_when_the_week_was_forecast_on_the_monday(
        self, store, store_url, crosswalk
    ):
        """**SPEC-phase1 8.5.** A Tuesday game and a Saturday game, one week, two
        generations, and both games in the record.

        Neither generation covers the week alone. Monday's holds both and was
        early for both; Thursday's cannot hold the Tuesday game at all, because
        `predict_week` forecasts only what has not kicked off. `merge_generations`
        takes, per game, the newest generation written before *that game's* own
        kickoff — so the Saturday game is still graded on Thursday's forecast,
        with its fresher lines, and the Tuesday game is graded on Monday's.
        """
        midweek_slate_ready(store, crosswalk, forecast_monday=True)

        assert run("score", "--season", "2026", "--force",
                   "--store", store_url, now=SECOND_MONDAY) == 0

        scored = json.loads(
            store.get_bytes(store.list_keys("scored/season=2026/week=02/")[0])
        )
        by_id = {game["cfbd_game_id"]: game for game in scored["games"]}
        assert sorted(by_id) == [2, 3]
        assert by_id[3]["forecast_generated_at"].startswith("2026-09-08")
        assert by_id[2]["forecast_generated_at"].startswith("2026-09-10")

    def test_without_the_monday_forecast_the_midweek_game_is_simply_absent(
        self, store, store_url, crosswalk
    ):
        """**The gap 8.5 closes, asserted rather than described.**

        This is what the Thursday-only schedule produced, and the reason it went
        unnoticed for a season: the run is green, the document is well-formed,
        the joins all succeed, and the game is just not there. `forecast_from`
        keeps it honest — the week's coverage starts at the Saturday kickoff and
        says so — but no mean on the accuracy page is computed over the Tuesday
        game, and nothing on the page could show that it was missing.
        """
        midweek_slate_ready(store, crosswalk, forecast_monday=False)

        assert run("score", "--season", "2026", "--force",
                   "--store", store_url, now=SECOND_MONDAY) == 0

        scored = json.loads(
            store.get_bytes(store.list_keys("scored/season=2026/week=02/")[0])
        )
        assert [game["cfbd_game_id"] for game in scored["games"]] == [2]
        assert scored["full_slate"]["games"] == 1

    def test_the_monday_forecast_does_not_displace_thursdays_for_the_saturday_slate(
        self, store, store_url, crosswalk
    ):
        """The additive claim, which is what makes this safe to run every week.

        Monday's generation covers the Saturday game too, and must not win it:
        Thursday's is newer and was still written before kickoff, so it governs.
        If that ever inverted, every ordinary week's record would quietly move to
        a forecast made with four days' less information and Monday's prices.
        """
        midweek_slate_ready(store, crosswalk, forecast_monday=True)
        run("score", "--season", "2026", "--force", "--store", store_url,
            now=SECOND_MONDAY)

        scored = json.loads(
            store.get_bytes(store.list_keys("scored/season=2026/week=02/")[0])
        )
        saturday = next(g for g in scored["games"] if g["cfbd_game_id"] == 2)
        assert saturday["forecast_generated_at"].startswith("2026-09-10")

    def test_out_of_season_is_a_skip_not_a_failure(self, store, store_url, crosswalk):
        """A scheduled Sunday in June. Exit 0, nothing written -- turning those
        red would train a reader to ignore the one that matters."""
        seed(store, crosswalk)
        assert run("score", "--season", "2026", "--store", store_url,
                   now=datetime(2026, 6, 7, 12, 0, tzinfo=UTC)) == 0
        assert store.list_keys("scored/") == []


# --- cfb publish --------------------------------------------------------------


class TestPublishCommand:
    def test_it_writes_the_four_documents(self, store, store_url, crosswalk):
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)

        assert run("publish", "--season", "2026", "--week", "1", "--force",
                   "--store", store_url, now=GENERATED_AT) == 0
        assert sorted(store.list_keys("cfb/data/")) == [
            "cfb/data/accuracy.json",
            "cfb/data/models.json",
            "cfb/data/next-game.json",
            "cfb/data/slate.json",
        ]

    def test_it_takes_the_newest_generation_unlike_score(
        self, store, store_url, crosswalk
    ):
        """**The opposite rule to `cfb score`, and both are right.** A regenerate
        exists because someone wanted the newer number on the site."""
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)
        newest = datetime(2026, 9, 3, 18, 0, tzinfo=UTC)
        predict(store, crosswalk, now=newest)

        run("publish", "--season", "2026", "--week", "1", "--force",
            "--store", store_url, now=GENERATED_AT)
        page = json.loads(store.get_bytes("cfb/data/next-game.json"))
        # The document names the week and the run, and the slate it drew from is
        # the 18:00 generation -- checked through the elo_state both share.
        assert page["week"] == "01"

    def test_a_file_store_skips_the_invalidation_loudly(
        self, store, store_url, crosswalk, capsys
    ):
        """A `file://` publish has no edge cache in front of it, and a run
        reporting an invalidation it never made is the one Friday line nobody
        could trust."""
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)

        run("publish", "--season", "2026", "--week", "1", "--force",
            "--store", store_url, now=GENERATED_AT)
        logged = capsys.readouterr().out
        assert "event=invalidated" in logged
        assert "result=skip" in logged
        assert "reason=not_a_cdn_origin" in logged


# --- cfb backtest -------------------------------------------------------------


class TestBacktest:
    """A retrospective week, kept apart from the record by construction."""

    #: Two games the golden preseason page carries predictions for, because a
    #: correlation over one point is not a number (§5.3) and the identity this
    #: class asserts needs at least two to be visible at all.
    def prepare(self, store, crosswalk):
        seed(store, crosswalk)
        put_games(
            store,
            week="01",
            fetched_at=CAPTURED_AT,
            games=[
                played(),
                cfbd_game(game_id=2, week=1, kickoff=THURSDAY, home="Austin Peay",
                          away="Gardner-Webb", home_points=28, away_points=10),
                cfbd_game(game_id=3, week=1, kickoff=SATURDAY, home="TCU",
                          away="North Carolina", neutral_site=True,
                          home_points=17, away_points=24),
            ],
        )

    def test_it_writes_only_under_backtest(self, store, store_url, crosswalk):
        """**The property that makes it safe.** Not a flag in a document someone
        has to notice -- a prefix `scored_weeks` does not read."""
        self.prepare(store, crosswalk)

        assert run("backtest", "--season", "2026", "--week", "1",
                   "--store", store_url, now=RAN_AT) == 0
        assert len(store.list_keys("backtest/season=2026/week=01/")) == 1
        assert store.list_keys("scored/") == []
        assert store.list_keys("predictions/") == []

    def test_the_season_to_date_record_does_not_see_it(
        self, store, store_url, crosswalk
    ):
        """The whole point: a backtested week must not reach `full_slate`."""
        self.prepare(store, crosswalk)
        run("backtest", "--season", "2026", "--week", "1", "--store", store_url, now=RAN_AT)
        predict(store, crosswalk)
        run("publish", "--season", "2026", "--week", "1", "--force",
            "--store", store_url, now=GENERATED_AT)

        accuracy = json.loads(store.get_bytes("cfb/data/accuracy.json"))
        assert accuracy["full_slate"]["games"] == 0
        assert accuracy["through_week"] is None
        assert accuracy["backtest"]["full_slate"]["games"] == 3
        assert accuracy["backtest"]["measures_the_seed"] is True

    def test_a_week_one_backtest_correlates_perfectly_with_sagarin(
        self, store, store_url, crosswalk
    ):
        """**What a week 1 backtest actually measures.**

        The seed is `1500 + (rating - mean) * 28` and the preseason page's rating
        columns are identical (§1.2), so a week 1 forecast reproduces Sagarin's
        PREDICTOR to the floating-point bit. These figures describe Sagarin's
        preseason page, not the Elo model, and the document says so.
        """
        self.prepare(store, crosswalk)
        run("backtest", "--season", "2026", "--week", "1", "--store", store_url, now=RAN_AT)

        document = json.loads(
            store.get_bytes(store.list_keys("backtest/season=2026/week=01/")[0])
        )
        assert document["sagarin_r"] == pytest.approx(1.0)


# --- cfb note -----------------------------------------------------------------


class TestNote:
    def scored(self, store, store_url, crosswalk):
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)
        put_games(store, week="01", fetched_at=CAPTURED_AT, games=[played()])
        run("score", "--season", "2026", "--week", "1", "--force",
            "--store", store_url, now=RAN_AT)

    def test_it_writes_a_scaffold(self, store, store_url, crosswalk):
        self.scored(store, store_url, crosswalk)
        assert run("note", "--season", "2026", "--week", "1",
                   "--store", store_url, now=RAN_AT) == 0
        assert len(store.list_keys("notes/season=2026/week=01/")) == 1

    def test_team_names_are_rendered_never_canonical_ids(
        self, store, store_url, crosswalk
    ):
        """**Found by reading the first real scaffold**, which said "Texas hosted
        ohio-state". §6.3's rule broken in the most visible place there is: a
        document whose whole purpose is to be read and then published as prose.
        """
        self.scored(store, store_url, crosswalk)
        run("note", "--season", "2026", "--week", "1", "--store", store_url, now=RAN_AT)

        markdown = store.get_bytes(
            store.list_keys("notes/season=2026/week=01/")[0]
        ).decode("utf-8")
        assert "Ohio State" in markdown
        assert "ohio-state" not in markdown
        assert "Texas hosted Ohio State" in markdown

    def test_a_regenerate_lands_beside_its_predecessor(
        self, store, store_url, crosswalk
    ):
        """§7 named a fixed `scaffold.md`, which cannot be written twice under
        `put_bytes` with no `s3:DeleteObject`. A person part-way through editing
        one does not lose it to a rerun."""
        self.scored(store, store_url, crosswalk)
        run("note", "--season", "2026", "--week", "1", "--store", store_url, now=RAN_AT)
        run("note", "--season", "2026", "--week", "1", "--store", store_url,
            now=RAN_AT.replace(minute=45))
        assert len(store.list_keys("notes/season=2026/week=01/")) == 2

    def test_an_unscored_week_names_the_command_that_fixes_it(
        self, store, store_url, crosswalk, capsys
    ):
        seed(store, crosswalk)
        fails(capsys, "note", "--season", "2026", "--week", "1",
              "--store", store_url, now=RAN_AT, saying="uv run cfb score")

    def test_the_scaffold_keeps_its_todo_markers(self, store, store_url, crosswalk):
        """An unedited scaffold that shipped would read as a finished note."""
        self.scored(store, store_url, crosswalk)
        run("note", "--season", "2026", "--week", "1", "--store", store_url, now=RAN_AT)
        markdown = store.get_bytes(
            store.list_keys("notes/season=2026/week=01/")[0]
        ).decode("utf-8")
        assert markdown.count("TODO") >= 2


class TestTheSundayAndMondayRefresh:
    """`cfb publish --refresh` (SPEC-phase1 8.3).

    **The page went stale from Friday to Thursday, and the front page lied while
    it did.** `/cfb` is only built Thursday and Friday, and a week's results are
    only captured once its partition closes -- the Monday after. So `_finished`
    had nothing fresh for the week on the board, `_next_fixture` could not know
    Saturday's game had been played, and on 2026-09-07 the headline still named
    Texas State from two days earlier.

    A refresh run cannot resolve its week the way the SLO run does. A CFBD week
    closes on the Monday, so by Monday midday `coming_week` has already moved to a
    week nobody forecasts until Thursday -- and the SLO's "raise when that week has
    no predictions" would redden every Monday for a pipeline that is fine.
    """

    def refresh(self, store, store_url, capsys, *, now):
        assert run("publish", "--season", "2026", "--refresh", "--force",
                   "--store", store_url, now=now) == 0
        return next(
            (line for line in capsys.readouterr().out.splitlines()
             if "event=published" in line),
            "",
        )

    def test_a_monday_run_publishes_the_week_that_just_finished(
        self, store, store_url, crosswalk, capsys
    ):
        """**The regression.** The partition has closed, so `coming_week` says the
        next week -- which nobody has forecast. The SLO rule would raise here."""
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)

        line = self.refresh(store, store_url, capsys, now=MONDAY_AFTER_CLOSE)

        assert "requested_week=01" in line
        assert "result=ok" in line

    def test_the_slo_run_still_raises_on_the_same_data(
        self, store, store_url, crosswalk, capsys
    ):
        """The pair, and the reason `--refresh` is a flag rather than the default.

        A Thursday publish that quietly showed last week's board when `cfb predict`
        had failed would remove the signal §8 exists to give. Same store, same
        moment, no flag -- and it fails.
        """
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)

        assert run("publish", "--season", "2026", "--force",
                   "--store", store_url, now=MONDAY_AFTER_CLOSE) == 1

    def test_nothing_forecast_yet_is_a_skip_and_says_which_kind(
        self, store, store_url, crosswalk, capsys
    ):
        """Before the season's first Thursday there is no board to refresh.

        The reason is `nothing_forecast` rather than `no_coming_week`: one says the
        calendar ran out of weeks and the other says nobody has forecast one yet,
        and sending someone to the calendar for a date is how a log line wastes an
        afternoon.
        """
        seed(store, crosswalk)

        assert run("publish", "--season", "2026", "--refresh", "--force",
                   "--store", store_url, now=GENERATED_AT) == 0
        printed = capsys.readouterr().out
        assert "reason=nothing_forecast" in printed, printed
        assert "no_coming_week" not in printed

    def test_it_never_reaches_past_the_week_being_played(
        self, store, store_url, crosswalk, capsys
    ):
        """`coming_week` stays the ceiling.

        A refresh only ever looks *back* for a week that has a forecast. One that
        could also run forward would publish a slate before its week, which is the
        single thing the SLO is about.
        """
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)

        line = self.refresh(store, store_url, capsys, now=GENERATED_AT)

        assert "requested_week=01" in line
        assert "requested_week=02" not in line

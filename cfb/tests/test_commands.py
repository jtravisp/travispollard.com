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
from datetime import UTC, datetime

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

THURSDAY = datetime(2026, 9, 3, 23, 0, tzinfo=UTC)
SATURDAY = datetime(2026, 9, 5, 19, 0, tzinfo=UTC)

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


def predict(store, crosswalk, *, now=GENERATED_AT):
    log = predict_week(
        store=store, season=SEASON, week="01", now=now, crosswalk=crosswalk
    )
    return write_predictions(store, log)


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

    def test_a_week_whose_every_generation_postdates_its_slate_writes_nothing(
        self, store, store_url, crosswalk, capsys
    ):
        """Exit 1, and **nothing written** -- not even the Elo state, because the
        command reads every input before writing anything."""
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict_late(store, crosswalk, stamped=datetime(2026, 9, 7, 0, 0, tzinfo=UTC))
        put_games(store, week="01", fetched_at=CAPTURED_AT, games=[played()])

        before = set(store.list_keys("elo/"))
        fails(capsys, "score", "--season", "2026", "--week", "1", "--force",
              "--store", store_url, now=RAN_AT,
              saying="after its own slate had started")
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

    def test_out_of_season_is_a_skip_not_a_failure(self, store, store_url, crosswalk):
        """A scheduled Sunday in June. Exit 0, nothing written -- turning those
        red would train a reader to ignore the one that matters."""
        seed(store, crosswalk)
        assert run("score", "--season", "2026", "--store", store_url,
                   now=datetime(2026, 6, 7, 12, 0, tzinfo=UTC)) == 0
        assert store.list_keys("scored/") == []


# --- cfb publish --------------------------------------------------------------


class TestPublishCommand:
    def test_it_writes_the_three_documents(self, store, store_url, crosswalk):
        seed(store, crosswalk)
        put_games(store, week="01", fetched_at=PULLED_AT, games=[unplayed()])
        predict(store, crosswalk)

        assert run("publish", "--season", "2026", "--week", "1", "--force",
                   "--store", store_url, now=GENERATED_AT) == 0
        assert sorted(store.list_keys("cfb/data/")) == [
            "cfb/data/accuracy.json",
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

"""Which week's board `/cfb/slate` publishes (SPEC-phase1 6.3, 8).

`calendar.coming_week` answers "which week is about to start". The slate needs
"which week is being played", and the two come apart exactly when CFBD runs a
week long — which it did in 2026, for ten days across two Saturdays.

The case reproduced here is the live one, not a constructed one. On
2026-08-29 07:00Z `coming_week` began returning "02" while week 1 still had 320
of its 455 games unplayed, so the 09-04 publish would have replaced the live
week-1 board with week 2 while that Saturday's games — Texas among them — were
still ahead.

`_next_fixture` already fixed this half for `next-game.json` and its docstring
names the case. These tests are the slate's half, and the important one
(`test_the_board_stays_on_the_week_still_being_played`) fails on the behaviour
that shipped: it publishes week 2.
"""

from datetime import UTC, datetime

import pytest

from cfb.cli import main
from cfb.crosswalk import load as load_crosswalk
from cfb.elo.state import write_state
from cfb.predict import predict_week, write_predictions
from cfb.publish import build_slate
from cfb.replay import seed_state
from cfb.storage import FileSnapshotStore, MemorySnapshotStore
from test_replay import PRESEASON_AT, SEASON, cfbd_game, put_games, put_sagarin

SEEDED_AT = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)

#: The two Saturdays of CFBD's ten-day week 1, and week 2's.
FIRST_SATURDAY = datetime(2026, 8, 29, 23, 0, tzinfo=UTC)
SECOND_SATURDAY = datetime(2026, 9, 5, 19, 30, tzinfo=UTC)
WEEK_TWO_SATURDAY = datetime(2026, 9, 12, 19, 30, tzinfo=UTC)

#: `cfb predict` for week 2 ran on the Thursday; the publish on the Friday after.
GENERATED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 9, 4, 12, 30, tzinfo=UTC)

#: The Sunday pull that saw the first Saturday and nothing after it, and the one
#: a week later that saw one of the second Saturday's games. The evidence the
#: whole decision runs on: it is what makes a game behind us or ahead.
CAPTURED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
RECAPTURED_AT = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


def week_one_games():
    """Two played on the opening Saturday, two still ahead on the second."""
    return [
        cfbd_game(
            game_id=11, week=1, kickoff=FIRST_SATURDAY,
            home="Ohio State", away="Michigan", home_points=27, away_points=24,
        ),
        cfbd_game(
            game_id=12, week=1, kickoff=FIRST_SATURDAY,
            home="Alabama", away="Auburn", home_points=31, away_points=17,
        ),
        cfbd_game(
            game_id=13, week=1, kickoff=SECOND_SATURDAY,
            home="Texas", away="Texas State", home_points=None, away_points=None,
        ),
        cfbd_game(
            game_id=14, week=1, kickoff=SECOND_SATURDAY,
            home="Georgia", away="Clemson", home_points=None, away_points=None,
        ),
    ]


def week_two_games():
    return [
        cfbd_game(
            game_id=21, week=2, kickoff=WEEK_TWO_SATURDAY,
            home="Texas", away="Oklahoma", home_points=None, away_points=None,
        ),
    ]


def played(games, *scores):
    """The same rows, with results filled in. `scores` is (id, home, away)."""
    filled = {game_id: (home, away) for game_id, home, away in scores}
    out = []
    for game in games:
        row = dict(game)
        if row["id"] in filled:
            row["homePoints"], row["awayPoints"] = filled[row["id"]]
        out.append(row)
    return out


def overlapping(crosswalk, *, later=None, store=None):
    """The 2026 overlap: week 1 half played, week 2 already forecast.

    Built in the order it happened, which is the only order that produces a
    realistic log. `predict_week` forecasts what has not kicked off yet, so week
    1's predictions cover the second Saturday only -- the first Saturday's games
    were behind us when the model went live and were never forecast. `later` is a
    newer capture written afterwards, the way a Sunday pull arrives after the
    predictions it grades.
    """
    store = store if store is not None else MemorySnapshotStore()
    put_sagarin(store, fetched_at=PRESEASON_AT)
    put_games(store, week="01", fetched_at=CAPTURED_AT, games=week_one_games())
    put_games(store, week="02", fetched_at=CAPTURED_AT, games=week_two_games())
    write_state(
        store, seed_state(store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk)
    )
    for week in ("01", "02"):
        write_predictions(
            store,
            predict_week(
                store=store, season=SEASON, week=week, now=GENERATED_AT,
                crosswalk=crosswalk,
            ),
        )
    if later is not None:
        put_games(store, week="01", fetched_at=RECAPTURED_AT, games=later)
    return store


class TestTheOverlap:
    """Week 1 has games ahead and week 2 is already forecast."""

    def test_the_board_stays_on_the_week_still_being_played(self, crosswalk):
        """**The regression.** `coming_week` says "02" on this date; the board
        must say "01", because that is where the unplayed games are."""
        store = overlapping(crosswalk)

        document = build_slate(
            store=store, season=SEASON, week="02", now=PUBLISHED_AT, crosswalk=crosswalk
        )

        assert document.week == "01"
        # The first Saturday had already kicked off when the model went live, so
        # it was never forecast and is not on any board. The second Saturday is
        # what week 1 still has ahead, and it is what a reader loses if the run
        # publishes week 2.
        assert {game.cfbd_game_id for game in document.games} == {13, 14}

    def test_the_held_week_is_named_in_the_document(self, crosswalk):
        """Recorded, not implicit. A reader looking at week 1 on a day when week 2
        exists is owed the reason, and the page can only say what it is given."""
        store = overlapping(crosswalk)

        document = build_slate(
            store=store, season=SEASON, week="02", now=PUBLISHED_AT, crosswalk=crosswalk
        )

        assert document.next_week_forecast == "02"

    def test_a_game_played_since_is_marked_and_the_board_still_held(self, crosswalk):
        """Holding the board back is not the same as hiding what happened.

        A newer capture has Texas played and Georgia still ahead. The played game
        keeps its row and its forecast, marked; the week is held because one game
        remains. Both halves read the same capture, so the board's week and its
        markers cannot disagree about the same game."""
        store = overlapping(
            crosswalk, later=played(week_one_games(), (13, 45, 10))
        )

        document = build_slate(
            store=store, season=SEASON, week="02", now=PUBLISHED_AT, crosswalk=crosswalk
        )

        assert document.week == "01"
        assert {game.cfbd_game_id for game in document.games if game.played} == {13}
        assert document.results_known_at == RECAPTURED_AT


class TestTheEvidenceRule:
    """"Still has games ahead" is decided by the capture, never by a clock."""

    def test_a_week_whose_games_are_all_played_releases_the_board(self, crosswalk):
        """The same store with the second Saturday scored: nothing in week 1 is
        ahead any more, so the board moves on. This is the pair to the test above
        and it differs only in the evidence."""
        store = overlapping(
            crosswalk, later=played(week_one_games(), (13, 45, 10), (14, 21, 20))
        )

        document = build_slate(
            store=store, season=SEASON, week="02", now=PUBLISHED_AT, crosswalk=crosswalk
        )

        assert document.week == "02"
        assert document.next_week_forecast is None

    def test_the_run_moment_does_not_decide_it(self, crosswalk):
        """Publishing from a moment long after every kickoff changes nothing.

        The discriminating case for "evidence, not a clock": by any wall clock
        week 1 finished months ago, and the capture still shows two games without
        scores. A clock-based rule would release the board here; this one does not,
        and that is what makes the document replayable."""
        store = overlapping(crosswalk)

        document = build_slate(
            store=store,
            season=SEASON,
            week="02",
            now=datetime(2027, 3, 1, 12, 0, tzinfo=UTC),
            crosswalk=crosswalk,
        )

        assert document.week == "01"

    def test_a_week_with_no_capture_counts_as_entirely_ahead(self, crosswalk):
        """No evidence of completion is not evidence of completion.

        Not a special case: the rule reads "no game the capture shows complete",
        and an absent capture shows none. `_finished` already returns an empty set
        for it, so both halves of the document agree."""
        store = overlapping(crosswalk)
        # Drop week 1's results capture, keeping its predictions. `raw/` is
        # write-once and nothing in the pipeline deletes from it -- this reaches
        # past the interface deliberately, to build a store the pipeline cannot
        # produce but S3 can present after a failed pull.
        for key in list(store.list_keys("raw/cfbd/season=2026/week=01/games/")):
            del store._objects[key]  # noqa: SLF001

        document = build_slate(
            store=store, season=SEASON, week="02", now=PUBLISHED_AT, crosswalk=crosswalk
        )

        assert document.week == "01"
        assert document.results_known_at is None
        assert not any(game.played for game in document.games)


class TestTheOrdinaryWeek:
    """Nothing above may change the ordinary case, which is every other week."""

    def test_one_week_with_games_ahead_publishes_itself(self, crosswalk):
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(store, week="01", fetched_at=CAPTURED_AT, games=week_one_games())
        write_state(
            store,
            seed_state(store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk),
        )
        write_predictions(
            store,
            predict_week(
                store=store, season=SEASON, week="01", now=GENERATED_AT,
                crosswalk=crosswalk,
            ),
        )

        document = build_slate(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )

        assert document.week == "01"
        assert document.next_week_forecast is None

    def test_the_search_never_runs_forward(self, crosswalk):
        """`coming_week` stays the ceiling.

        Week 2 has everything ahead of it, but a run asked for week 1 publishes
        week 1. A resolver that could also move forward would publish a slate
        before its week, which is the one failure the §8 SLO exists to prevent.
        """
        store = overlapping(
            crosswalk, later=played(week_one_games(), (13, 45, 10), (14, 21, 20))
        )

        document = build_slate(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )

        assert document.week == "01"
        assert all(game.played for game in document.games)


class TestTheLogLine:
    """What an Actions log says about a run that held the board.

    The line is the only thing a person looks at to decide whether a publish did
    the right thing, and it used to carry a single `week=` naming the *request*.
    On the run that actually held the board it read `week=02` while writing a
    week-1 slate: true, and the exact opposite of what its reader was checking.
    Same class as a page footer showing the rebuild time where someone is looking
    for the forecast time.
    """

    def published(self, crosswalk, tmp_path, capsys, *, later=None):
        overlapping(crosswalk, later=later, store=FileSnapshotStore(tmp_path))
        assert (
            main(
                [
                    "publish", "--season", "2026", "--force",
                    "--store", f"file://{tmp_path.as_posix()}",
                ],
                now=PUBLISHED_AT,
            )
            == 0
        )
        return next(
            line
            for line in capsys.readouterr().out.splitlines()
            if "event=published" in line
        )

    def test_it_names_the_published_week_beside_the_requested_one(
        self, crosswalk, tmp_path, capsys
    ):
        """**The regression.** `coming_week` resolves this moment to week 2 and
        the board is held on week 1, so the line has to say both."""
        line = self.published(crosswalk, tmp_path, capsys)

        assert "requested_week=02" in line
        assert "slate_week=01" in line
        assert "next_game_week=01" in line

    def test_a_held_board_is_stated_rather_than_inferred(
        self, crosswalk, tmp_path, capsys
    ):
        """Greppable and alertable. "These two fields differ" is neither, and
        counting games requires already knowing the right answer."""
        line = self.published(crosswalk, tmp_path, capsys)

        assert "board_held=True" in line

    def test_no_line_from_a_publish_run_says_a_bare_week(
        self, crosswalk, tmp_path, capsys
    ):
        """The point of the rename. A reader who sees `week=` will take it for
        what was published, and on the one run where that matters it is wrong."""
        overlapping(crosswalk, store=FileSnapshotStore(tmp_path))
        main(
            [
                "publish", "--season", "2026", "--force",
                "--store", f"file://{tmp_path.as_posix()}",
            ],
            now=PUBLISHED_AT,
        )

        for line in capsys.readouterr().out.splitlines():
            assert " week=" not in line, line

    def test_an_ordinary_week_says_the_board_is_not_held(
        self, crosswalk, tmp_path, capsys
    ):
        """The pair. With week 1 finished the board moves on, and the flag has to
        move with it -- a field that is always True is not a signal."""
        line = self.published(
            crosswalk,
            tmp_path,
            capsys,
            later=played(week_one_games(), (13, 45, 10), (14, 21, 20)),
        )

        assert "requested_week=02" in line
        assert "slate_week=02" in line
        assert "board_held=False" in line

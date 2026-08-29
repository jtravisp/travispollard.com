"""What `/cfb` shows besides the next game (§6.3).

Three additions, all pure projections of documents the pipeline already wrote:
Texas's rating and rank at every stored state, the final score of a result, and
the opponent's standing. No new source, no new arithmetic.

**Two of them are optional fields on documents that are already stored, and that
is the interesting constraint.** `scored/` is write-once, so a week written before
`home_points` existed cannot be rewritten to add it — a required field would make
every archived week unreadable the moment it shipped, which is a worse outcome
than a page that cannot print a scoreline. The same holds for a `next-game.json`
published before `history` existed and read by a page deployed after.

That second case is not hypothetical, it is **guaranteed**: routes deploy before
the pipeline republishes, so the first thing that happens in production is a new
page reading an old document. `TestReadingADocumentWrittenBefore` is that case.
"""

import json
from datetime import UTC, datetime

import pytest

from cfb.crosswalk import load as load_crosswalk
from cfb.elo.scoring import ScoredGame, ScoredWeek, score_week, write_scored
from cfb.elo.state import write_state
from cfb.predict import predict_week, write_predictions
from cfb.publish import NextGameDocument, build_next_game
from cfb.replay import advance, seed_state
from cfb.sources import week_slate
from cfb.storage import MemorySnapshotStore
from test_replay import PRESEASON_AT, SEASON, cfbd_game, put_games, put_sagarin

SEEDED_AT = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
PULLED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
PLAYED_AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
SATURDAY = datetime(2026, 9, 5, 19, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 12, 19, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


def seeded(crosswalk, games, *, week="01"):
    store = MemorySnapshotStore()
    put_sagarin(store, fetched_at=PRESEASON_AT)
    put_games(store, week=week, fetched_at=PULLED_AT, games=games)
    write_state(
        store, seed_state(store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk)
    )
    return store


def texas_game(*, home_points=None, away_points=None, away="Texas State"):
    return cfbd_game(
        game_id=1, week=1, kickoff=SATURDAY, home="Texas", away=away,
        home_points=home_points, away_points=away_points,
    )


# --- (b) the score ------------------------------------------------------------


class TestTheFinalScore:
    """`ScoredGame` knew the margin and the winner and threw the points away."""

    def scored(self, crosswalk, home_points, away_points):
        store = seeded(crosswalk, [texas_game()])
        log = predict_week(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        put_games(
            store, week="01", fetched_at=PLAYED_AT,
            games=[texas_game(home_points=home_points, away_points=away_points)],
        )
        results, _ = week_slate(store, SEASON, lambda raw: True)
        return score_week(
            log, [raw for raw, _ in results],
            results_fetched_at=PLAYED_AT, now=PLAYED_AT,
        )

    def test_the_points_are_carried_through(self, crosswalk):
        game = self.scored(crosswalk, 45, 14).games[0]
        assert (game.home_points, game.away_points) == (45, 14)

    def test_they_agree_with_the_margin_that_was_already_there(self, crosswalk):
        """The margin is not recomputed from them, so the two could disagree."""
        game = self.scored(crosswalk, 45, 14).games[0]
        assert game.home_points - game.away_points == game.actual_margin

    def test_a_margin_alone_cannot_reconstruct_them(self, crosswalk):
        """Why carrying the points is not redundant: 45-14 and 38-7 are the same
        margin and different games."""
        first = self.scored(crosswalk, 45, 14).games[0]
        second = self.scored(crosswalk, 38, 7).games[0]
        assert first.actual_margin == second.actual_margin
        assert (first.home_points, first.away_points) != (
            second.home_points,
            second.away_points,
        )


class TestReadingAScoredWeekWrittenBefore:
    """**`scored/` is write-once and the archive cannot be rewritten.**

    A required field would have made every already-stored week unreadable the
    moment this shipped. These are the shapes actually sitting in the bucket.
    """

    def test_a_game_without_points_still_loads(self):
        stored = {
            "cfbd_game_id": 1,
            "kickoff": "2026-09-05T19:30:00Z",
            "home": "texas", "away": "texas-state", "neutral_site": False,
            "predicted_margin": 39.3, "win_probability": 0.98,
            "actual_margin": 31, "home_won": True,
            "error": 8.3, "abs_error": 8.3, "brier": 0.0004,
            "market_line": None, "market_line_source": None, "market_margin": None,
            "market_abs_error": None, "market_pick": None,
            "beat_market": None, "market_push": None,
            "sagarin_predictor_margin": None, "sagarin_abs_error": None,
        }
        game = ScoredGame.model_validate_json(json.dumps(stored))
        assert game.home_points is None
        assert game.away_points is None
        assert game.actual_margin == 31

    def test_a_whole_week_without_points_still_loads(self):
        """The document is what `scored_weeks` reads, so it is the shape that
        matters -- a per-game failure would surface as an unreadable week."""
        stored = {
            "schema_version": 1, "season": 2026, "week": "01",
            "generated_at": "2026-09-13T12:30:00Z",
            "predictions_generated_at": "2026-09-03T12:00:00Z",
            "results_fetched_at": "2026-09-13T12:00:00Z",
            "forecast_from": None,
            "games": [], "unplayed": 0,
            "texas": {
                "games": 0, "mae": None, "brier": None,
                "market_games": 0, "market_mae": None,
                "sagarin_games": 0, "sagarin_mae": None,
                "ats": {"wins": 0, "losses": 0, "pushes": 0,
                        "excluded_no_line": 0, "excluded_no_edge": 0},
            },
            "full_slate": {
                "games": 0, "mae": None, "brier": None,
                "market_games": 0, "market_mae": None,
                "sagarin_games": 0, "sagarin_mae": None,
                "ats": {"wins": 0, "losses": 0, "pushes": 0,
                        "excluded_no_line": 0, "excluded_no_edge": 0},
            },
            "calibration": [], "sagarin_r": None,
        }
        assert ScoredWeek.model_validate_json(json.dumps(stored)).week == "01"


# --- (a) the series -----------------------------------------------------------


class TestTheHistory:
    def test_a_seeded_season_has_one_point(self, crosswalk):
        """**The state production is in until 2026-09-13.** `cfb score` defaults
        to the last *completed* week and CFBD's week 1 runs to 09-08, so the first
        `elo/week=NN` state lands on the 13th. Until then the series is the
        preseason seed alone, and the page has to say so rather than draw a line
        through one point."""
        store = seeded(crosswalk, [texas_game()])
        write_predictions(
            store,
            predict_week(store=store, season=SEASON, week="01",
                         now=GENERATED_AT, crosswalk=crosswalk),
        )
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert [point.week for point in page.history] == ["preseason"]
        assert page.history[0].rank == 5
        assert page.history[0].fbs_teams == 138

    def test_it_grows_as_weeks_are_advanced(self, crosswalk):
        store = seeded(crosswalk, [texas_game(home_points=45, away_points=14)])
        write_predictions(
            store,
            predict_week(store=store, season=SEASON, week="01",
                         now=GENERATED_AT, crosswalk=crosswalk),
        )
        write_state(
            store,
            advance(store=store, season=SEASON, week="01", now=PLAYED_AT,
                    crosswalk=crosswalk).state,
        )
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert [point.week for point in page.history] == ["preseason", "01"]
        # Texas won by 31 as a heavy favourite, so it should move a little and up.
        assert page.history[1].elo > page.history[0].elo

    def test_it_is_in_season_order_not_listing_order(self, crosswalk):
        store = seeded(crosswalk, [texas_game(home_points=45, away_points=14)])
        write_predictions(
            store,
            predict_week(store=store, season=SEASON, week="01",
                         now=GENERATED_AT, crosswalk=crosswalk),
        )
        write_state(
            store,
            advance(store=store, season=SEASON, week="01", now=PLAYED_AT,
                    crosswalk=crosswalk).state,
        )
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        # "preseason" sorts after "01" as a string and before it as a season.
        assert [point.week for point in page.history] == ["preseason", "01"]

    def test_a_re_advanced_week_appears_once(self, crosswalk):
        """A regenerated week writes a second object and both survive (§3.5).
        Charting both would draw one week twice at two ratings."""
        store = seeded(crosswalk, [texas_game(home_points=45, away_points=14)])
        write_predictions(
            store,
            predict_week(store=store, season=SEASON, week="01",
                         now=GENERATED_AT, crosswalk=crosswalk),
        )
        for moment in (PLAYED_AT, PLAYED_AT.replace(hour=18)):
            write_state(
                store,
                advance(store=store, season=SEASON, week="01", now=moment,
                        crosswalk=crosswalk).state,
            )
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert [point.week for point in page.history] == ["preseason", "01"]


# --- (c) opponent context -----------------------------------------------------


class TestOpponentContext:
    def test_an_fbs_opponent_carries_a_rank(self, crosswalk):
        store = seeded(
            crosswalk,
            [cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                       away="Ohio State", home_points=None, away_points=None)],
        )
        write_predictions(
            store,
            predict_week(store=store, season=SEASON, week="01",
                         now=GENERATED_AT, crosswalk=crosswalk),
        )
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert page.game.opponent == "Ohio State"
        assert page.game.opponent_rank == 1
        assert page.game.opponent_elo is not None

    def test_an_fcs_opponent_has_no_fbs_rank(self, crosswalk):
        """**`None`, not a rank on a different denominator.** The FBS table has no
        place for an FCS team, and inventing one would be a different number
        wearing the same word.

        Gardner-Webb rather than Texas State, which is Sun Belt FBS -- the real
        opponent on 09-05 does not exercise this path.
        """
        store = seeded(crosswalk, [texas_game(away="Gardner-Webb")])
        write_predictions(
            store,
            predict_week(store=store, season=SEASON, week="01",
                         now=GENERATED_AT, crosswalk=crosswalk),
        )
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert crosswalk.division("gardner-webb") == "FCS"
        assert page.game.opponent_rank is None
        # The rating is still real and still worth showing.
        assert page.game.opponent_elo is not None

    def test_it_comes_from_the_state_as_of_names(self, crosswalk):
        """Both standings on the page must come from one week, or the reader is
        comparing two different moments."""
        store = seeded(
            crosswalk,
            [cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                       away="Ohio State", home_points=None, away_points=None)],
        )
        write_predictions(
            store,
            predict_week(store=store, season=SEASON, week="01",
                         now=GENERATED_AT, crosswalk=crosswalk),
        )
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        preseason = next(p for p in page.history if p.week == page.as_of.week)
        assert page.as_of.elo == preseason.elo
        assert page.game.opponent_rank < page.as_of.national_rank


# --- the guaranteed case ------------------------------------------------------


class TestReadingADocumentWrittenBefore:
    """A `next-game.json` published before these fields existed.

    **Guaranteed, not hypothetical.** Routes deploy before the pipeline
    republishes, so a new page reading an old document is the first thing that
    happens in production every time this ships.
    """

    def test_it_loads_with_no_history_and_no_opponent_rank(self):
        stored = {
            "schema_version": 1,
            "generated_at": "2026-08-29T19:41:00Z",
            "season": 2026, "week": "01", "team": "Texas",
            "game": {
                "kickoff": "2026-09-05T19:30:00Z", "week": "01",
                "opponent": "Texas State", "home": True, "neutral_site": False,
                "predicted_margin": 39.3, "win_probability": 0.9893,
                "market_line": -30.5, "line_source": "DraftKings",
            },
            "as_of": {
                "week": "preseason", "elo": 2113.0,
                "national_rank": 5, "fbs_teams": 138,
            },
        }
        page = NextGameDocument.model_validate_json(json.dumps(stored))
        assert page.history == []
        assert page.game.opponent_rank is None
        assert page.game.opponent_elo is None
        # And the fields that were always there still read.
        assert page.game.opponent == "Texas State"
        assert page.as_of.national_rank == 5


# --- (b) on the page ----------------------------------------------------------


class TestTheLastResult:
    """The one block on `/cfb` that says what happened rather than what will."""

    def played(self, crosswalk, *, home_points=45, away_points=14):
        store = seeded(crosswalk, [texas_game()])
        write_predictions(
            store,
            predict_week(store=store, season=SEASON, week="01",
                         now=GENERATED_AT, crosswalk=crosswalk),
        )
        put_games(
            store, week="01", fetched_at=PLAYED_AT,
            games=[texas_game(home_points=home_points, away_points=away_points)],
        )
        return store

    def scored_page(self, crosswalk, **kwargs):
        store = self.played(crosswalk, **kwargs)
        results, _ = week_slate(store, SEASON, lambda raw: True)
        log = predict_week(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        write_scored(
            store,
            score_week(log, [raw for raw, _ in results],
                       results_fetched_at=PLAYED_AT, now=PLAYED_AT),
        )
        return build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )

    def test_nothing_scored_yet_is_none(self, crosswalk):
        """**Production's state until 2026-09-13.** The page must draw it."""
        store = self.played(crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert page.last_result is None

    def test_it_carries_the_scoreline(self, crosswalk):
        result = self.scored_page(crosswalk).last_result
        assert (result.team_points, result.opponent_points) == (45, 14)
        assert result.won is True
        assert result.opponent == "Texas State"

    def test_the_margins_are_from_the_teams_side(self, crosswalk):
        """Texas at home, so home perspective and Texas perspective agree here --
        the assertion that matters is that the error is signed and reported, not
        just its magnitude."""
        result = self.scored_page(crosswalk).last_result
        assert result.actual_margin == 31
        assert result.error == pytest.approx(result.predicted_margin - 31)

    def test_a_loss_reads_as_a_loss(self, crosswalk):
        result = self.scored_page(crosswalk, home_points=14, away_points=45).last_result
        assert result.won is False
        assert result.actual_margin == -31

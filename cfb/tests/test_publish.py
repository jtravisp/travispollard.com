"""The documents the site fetches (SPEC-phase1 6).

Most of this file is about **conventions meeting**, not about arithmetic. The
numbers were all computed and tested upstream — `test_elo.py` owns the formulas,
`test_scoring.py` owns the figures — and publishing's whole job is to hand them
to a page without changing what they mean. The two ways that goes wrong are a
sign flipped and a `null` rounded to zero, and both render perfectly.

Three rules are pinned here because each of them is invisible when broken:

    the clamp is publish-side only    storage keeps what the model said, so
                                      §5.3's Brier scores stay honest
    away games are re-signed          `next-game.json` is about one team and
                                      `predictions/` is about the home team
    a null mean never becomes 0.0     §5.3's rule, at the last place it can be
                                      broken
"""

from datetime import UTC, datetime

import pytest

from cfb.crosswalk import load as load_crosswalk
from cfb.elo.scoring import score_week, write_scored
from cfb.elo.state import write_state
from cfb.predict import predict_week, write_predictions
from cfb.publish import (
    ACCURACY_KEY,
    NEXT_GAME_KEY,
    PROBABILITY_CEILING,
    PROBABILITY_FLOOR,
    SLATE_KEY,
    build_accuracy,
    build_next_game,
    build_slate,
    clamp,
    publish,
)
from cfb.replay import advance, seed_state
from cfb.sources import week_slate
from cfb.storage import MemorySnapshotStore
from test_replay import (
    PRESEASON_AT,
    PRESEASON_HFA,
    SEASON,
    cfbd_game,
    put_games,
    put_sagarin,
)

SEEDED_AT = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
PULLED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
PLAYED_AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)

THURSDAY = datetime(2026, 9, 3, 23, 0, tzinfo=UTC)
SATURDAY = datetime(2026, 9, 5, 19, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(SEASON)


def slate_of(*games):
    return list(games)


def seeded(crosswalk, games, *, week="01", fetched_at=PULLED_AT):
    store = MemorySnapshotStore()
    put_sagarin(store, fetched_at=PRESEASON_AT)
    put_games(store, week=week, fetched_at=fetched_at, games=games)
    write_state(
        store, seed_state(store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk)
    )
    return store


def with_predictions(store, crosswalk, *, week="01"):
    log = predict_week(
        store=store, season=SEASON, week=week, now=GENERATED_AT, crosswalk=crosswalk
    )
    write_predictions(store, log)
    return log


# --- §3.7, the clamp ----------------------------------------------------------


class TestTheClamp:
    """§3.7. **Applied on the way out and never in storage.**

    Clamping on the way in would grade the model on what the page displayed
    rather than on what it said, and §5.3's Brier scores are computed on the
    stored value.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (0.0, PROBABILITY_FLOOR),
            (0.00001, PROBABILITY_FLOOR),
            (1.0, PROBABILITY_CEILING),
            (0.9999970913013003, PROBABILITY_CEILING),
            (0.5, 0.5),
            (0.4138309029504286, 0.4138309029504286),
        ],
    )
    def test_the_endpoints_and_the_middle(self, raw, expected):
        assert clamp(raw) == expected

    def test_storage_keeps_what_the_model_said(self, crosswalk):
        """The discriminating case: a mismatch this extreme is only visible
        because the two values are read from two places."""
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(
                    # Ahead of PUBLISHED_AT: `/cfb` shows the next *unplayed*
                    # game, so a Thursday kickoff would correctly come back as a
                    # bye on a Friday run and there would be nothing to clamp.
                    game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                    away="Stetson", home_points=None, away_points=None,
                )
            ),
        )
        log = with_predictions(store, crosswalk)
        stored = log.games[0].win_probability

        page = build_next_game(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert stored > PROBABILITY_CEILING
        assert page.game.win_probability == PROBABILITY_CEILING


# --- §6.3, next-game.json -----------------------------------------------------


class TestTheSubjectTeamPerspective:
    """`predictions/` is home perspective (§4.2); this document is about one team.

    An away game left in the storage convention renders perfectly and says the
    opposite thing, which is the failure this class exists for.
    """

    def test_a_home_game_is_carried_straight_through(self, crosswalk):
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                          away="Ohio State", home_points=None, away_points=None)
            ),
        )
        log = with_predictions(store, crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert page.game.home is True
        assert page.game.opponent == "Ohio State"
        assert page.game.predicted_margin == log.games[0].predicted_margin

    def test_an_away_game_is_re_signed(self, crosswalk):
        """Both halves flip, and the probabilities must still sum to one."""
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Ohio State",
                          away="Texas", home_points=None, away_points=None)
            ),
        )
        log = with_predictions(store, crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )

        assert page.game.home is False
        assert page.game.opponent == "Ohio State"
        assert page.game.predicted_margin == pytest.approx(-log.games[0].predicted_margin)
        assert page.game.win_probability == pytest.approx(1 - log.games[0].win_probability)

    def test_the_market_line_is_not_re_signed(self, crosswalk):
        """**The one field that stays in the vendor's convention** (§4.3).

        It is the book's own quote, printed beside the book's name. Converting it
        would publish a number no book ever posted under a name saying one did.
        """
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Ohio State",
                          away="Texas", home_points=None, away_points=None)
            ),
        )
        with_predictions(store, crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        # No lines snapshot in this store, so the null path is what is asserted:
        # absent, never a zero, which would be a pick'em.
        assert page.game.market_line is None
        assert page.game.line_source is None


class TestABye:
    def test_no_game_yields_a_null_game_and_intact_ratings(self, crosswalk):
        """A bye is an ordinary week. Blanking the page would say less than
        stating it, and the ratings are true either way."""
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Ohio State",
                          away="Michigan", home_points=None, away_points=None)
            ),
        )
        with_predictions(store, crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert page.game is None
        assert page.team == "Texas"
        assert page.as_of.national_rank >= 1
        assert page.as_of.elo > 0

    def test_a_team_playing_twice_raises(self, crosswalk):
        """One team plays once a week, so this is a duplicated game or two names
        collapsing to one id -- and `/cfb` would render whichever came first."""
        from cfb.errors import ReplayError

        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=THURSDAY, home="Texas",
                          away="Michigan", home_points=None, away_points=None),
                cfbd_game(game_id=2, week=1, kickoff=SATURDAY, home="Ohio State",
                          away="Texas", home_points=None, away_points=None),
            ),
        )
        with_predictions(store, crosswalk)
        with pytest.raises(ReplayError, match="appears in 2 games"):
            build_next_game(
                store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
            )


class TestTheRank:
    def test_it_is_among_the_fbs_and_carries_its_denominator(self, crosswalk):
        """The state rates 266 teams, 128 of them FCS. A rank over the whole
        table is a different number wearing the same word."""
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                          away="Ohio State", home_points=None, away_points=None)
            ),
        )
        with_predictions(store, crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert page.as_of.fbs_teams == 138
        assert 1 <= page.as_of.national_rank <= 138

    def test_texas_opens_at_the_rank_the_sagarin_page_gives_it(self, crosswalk):
        """SPEC-phase1 §1.2's table records Texas at rank 5 on the preseason
        page. The seed is an affine transform of those ratings, so the ranking
        has to survive it -- and this is the cheapest place that identity is
        visible."""
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                          away="Ohio State", home_points=None, away_points=None)
            ),
        )
        with_predictions(store, crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert page.as_of.national_rank == 5


# --- the slate ----------------------------------------------------------------


class TestTheSlate:
    @pytest.fixture
    def store(self, crosswalk):
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=2, week=1, kickoff=SATURDAY, home="Ohio State",
                          away="Michigan", home_points=None, away_points=None),
                cfbd_game(game_id=1, week=1, kickoff=THURSDAY, home="Texas",
                          away="Oklahoma", home_points=None, away_points=None),
            ),
        )
        with_predictions(store, crosswalk)
        return store

    def test_every_game_is_present_in_kickoff_order(self, store, crosswalk):
        document = build_slate(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert [game.cfbd_game_id for game in document.games] == [1, 2]

    def test_it_is_home_perspective_not_subject_perspective(self, store, crosswalk):
        """**The convention that differs from `next-game.json`.** A slate has no
        subject team to re-sign against."""
        document = build_slate(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        texas_game = next(game for game in document.games if game.cfbd_game_id == 1)
        assert texas_game.home == "Texas"
        assert texas_game.away == "Oklahoma"

    def test_the_subject_team_is_flagged(self, store, crosswalk):
        document = build_slate(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert [game.featured for game in document.games] == [True, False]

    def test_names_are_rendered_never_canonical_ids(self, store, crosswalk):
        document = build_slate(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert all("-" not in game.home.lower() or game.home[0].isupper()
                   for game in document.games)
        assert {game.home for game in document.games} == {"Texas", "Ohio State"}

    def test_probabilities_are_clamped_here_too(self, crosswalk):
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=THURSDAY, home="Texas",
                          away="Stetson", home_points=None, away_points=None)
            ),
        )
        with_predictions(store, crosswalk)
        document = build_slate(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert document.games[0].win_probability == PROBABILITY_CEILING

    def test_priced_counts_what_a_book_quoted(self, store, crosswalk):
        """No lines snapshot in this store, so zero -- and zero rather than a
        missing field, because a week where this collapses is a `/lines` pull
        that did not happen."""
        document = build_slate(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert document.priced == 0


# --- §6.4, accuracy.json ------------------------------------------------------


class TestAnEmptySeason:
    """The Friday before the season's first Sunday. **A legal, publishable
    document**, because refusing would fail §8's SLO over results nobody could
    have had."""

    @pytest.fixture
    def document(self, crosswalk):
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                          away="Ohio State", home_points=None, away_points=None)
            ),
        )
        with_predictions(store, crosswalk)
        return build_accuracy(store=store, season=SEASON, week="01", now=PUBLISHED_AT)

    def test_through_week_is_null_not_the_envelope_week(self, document):
        assert document.week == "01"
        assert document.through_week is None

    def test_every_mean_is_null_and_never_zero(self, document):
        for record in (document.texas, document.full_slate):
            assert record.games == 0
            assert record.mae is None
            assert record.brier is None
            assert record.line_mae is None
            assert record.sagarin_mae is None

    def test_the_series_are_empty_rather_than_fabricated(self, document):
        assert document.by_week == []
        assert document.calibration == []
        assert document.backtest is None


class TestTheSeedDisclosure:
    """§3.6, and the rule that it never un-retires."""

    def make(self, crosswalk, correlations):
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                          away="Ohio State", home_points=21, away_points=14)
            ),
        )
        log = with_predictions(store, crosswalk)
        results, _ = week_slate(store, SEASON, lambda raw: True)
        base = score_week(
            log,
            [raw for raw, _ in results],
            results_fetched_at=PLAYED_AT,
            now=PLAYED_AT,
        )
        for week, correlation in correlations:
            write_scored(
                store,
                base.model_copy(
                    update={
                        "week": week,
                        "sagarin_r": correlation,
                        "generated_at": datetime(2026, 9, 8 + int(week), 12, tzinfo=UTC),
                    }
                ),
            )
        return build_accuracy(store=store, season=SEASON, week="05", now=PUBLISHED_AT)

    def test_it_is_active_while_the_correlation_holds(self, crosswalk):
        document = self.make(crosswalk, [("01", 1.0), ("02", 0.95)])
        assert document.seed_disclosure.active is True
        assert document.seed_disclosure.retired_week is None
        assert document.seed_disclosure.current_r == 0.95

    def test_it_retires_at_the_first_week_below_the_threshold(self, crosswalk):
        document = self.make(crosswalk, [("01", 1.0), ("02", 0.85)])
        assert document.seed_disclosure.active is False
        assert document.seed_disclosure.retired_week == "02"

    def test_retirement_is_one_way(self, crosswalk):
        """**The discriminating case.** The claim being retired is "these ratings
        are still a restatement of Sagarin's page", and once that has been false
        for a week it is not something the page can assert again."""
        document = self.make(crosswalk, [("01", 1.0), ("02", 0.85), ("03", 0.99)])
        assert document.seed_disclosure.active is False
        assert document.seed_disclosure.retired_week == "02"
        assert document.seed_disclosure.current_r == 0.99

    def test_a_null_correlation_retires_nothing(self, crosswalk):
        """A week Sagarin covered fewer than two games of is not a low
        correlation. §5.3: a correlation over one point is not a number."""
        document = self.make(crosswalk, [("01", None), ("02", None)])
        assert document.seed_disclosure.active is True
        assert document.seed_disclosure.current_r is None


# --- writing them -------------------------------------------------------------


class TestPublish:
    @pytest.fixture
    def store(self, crosswalk):
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                          away="Ohio State", home_points=None, away_points=None)
            ),
        )
        with_predictions(store, crosswalk)
        return store

    def test_it_writes_all_three_documents(self, store, crosswalk):
        written = publish(
            store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
        )
        assert set(written) == {NEXT_GAME_KEY, SLATE_KEY, ACCURACY_KEY}

    def test_republishing_overwrites_rather_than_adding_keys(self, store, crosswalk):
        """**The mutable end of the pipeline**, unlike everything it is derived
        from. Safe precisely because the evidence behind it is write-once."""
        publish(store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk)
        before = set(store.list_keys("cfb/data/"))
        publish(
            store=store,
            season=SEASON,
            week="01",
            now=PUBLISHED_AT.replace(hour=18),
            crosswalk=crosswalk,
        )
        assert set(store.list_keys("cfb/data/")) == before
        assert len(before) == 3

    def test_a_week_with_no_predictions_refuses_to_publish(self, crosswalk):
        """The Friday SLO failing loudly. A page published without a forecast
        would have removed the only signal that it did not happen."""
        from cfb.errors import ReplayError

        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                          away="Ohio State", home_points=None, away_points=None)
            ),
        )
        with pytest.raises(ReplayError, match="no predictions are stored"):
            publish(
                store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk
            )


class TestTheEloAdvanceIsNotInvolved:
    def test_publishing_reads_state_and_never_writes_it(self, crosswalk):
        """Publishing is on the read path. Anything it recomputed would be a
        second implementation of the model where no replay check looks."""
        store = seeded(
            crosswalk,
            slate_of(
                cfbd_game(game_id=1, week=1, kickoff=SATURDAY, home="Texas",
                          away="Ohio State", home_points=21, away_points=14)
            ),
        )
        with_predictions(store, crosswalk)
        write_state(
            store,
            advance(store=store, season=SEASON, week="01", now=PLAYED_AT).state,
        )
        before = set(store.list_keys("elo/"))
        publish(store=store, season=SEASON, week="01", now=PUBLISHED_AT, crosswalk=crosswalk)
        assert set(store.list_keys("elo/")) == before


# --- the next game is the next game -------------------------------------------


class TestLookingAhead:
    """**The bug this class exists for shipped to production.**

    CFBD's week 1 of 2026 ran ten days across two Saturdays. Week 1 could not be
    predicted -- its first kickoff predated the first Sagarin capture -- so the
    run published week 2, and `/cfb` showed a game a fortnight out while the
    team's actual next opponent sat unforecast in week 1. Every number on the
    page was correct and the page was wrong.
    """

    def two_weeks(self, crosswalk):
        """Week 1 holding a later game, week 2 holding an earlier-labelled one."""
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(
            store,
            week="01",
            fetched_at=PULLED_AT,
            games=[
                cfbd_game(game_id=1, week=1, kickoff=datetime(2026, 9, 5, 19, tzinfo=UTC),
                          home="Texas", away="Texas State",
                          home_points=None, away_points=None)
            ],
        )
        put_games(
            store,
            week="02",
            fetched_at=PULLED_AT,
            games=[
                cfbd_game(game_id=2, week=2, kickoff=datetime(2026, 9, 12, 23, 30, tzinfo=UTC),
                          home="Texas", away="Ohio State",
                          home_points=None, away_points=None)
            ],
        )
        write_state(
            store, seed_state(store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk)
        )
        for week in ("01", "02"):
            write_predictions(
                store,
                predict_week(store=store, season=SEASON, week=week,
                             now=GENERATED_AT, crosswalk=crosswalk),
            )
        return store

    def test_it_finds_the_earlier_game_from_a_later_weeks_run(self, crosswalk):
        """Publishing week 2 must still surface the week 1 game that is sooner."""
        store = self.two_weeks(crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert page.game.opponent == "Texas State"
        assert page.game.week == "01"

    def test_the_game_carries_its_own_week_not_the_runs(self, crosswalk):
        """Printing the envelope's week beside the kickoff labelled a week 1
        game "Week 2", which is how the original bug looked on the page."""
        store = self.two_weeks(crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="01", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert page.game.week == "01"

    def test_a_played_game_is_skipped_for_the_next_one(self, crosswalk):
        """Once the week 1 game has kicked off, week 2's becomes next."""
        store = self.two_weeks(crosswalk)
        page = build_next_game(
            store=store,
            season=SEASON,
            week="01",
            now=datetime(2026, 9, 6, 12, tzinfo=UTC),
            crosswalk=crosswalk,
        )
        assert page.game.opponent == "Ohio State"
        assert page.game.week == "02"

    def test_it_never_looks_backwards(self, crosswalk):
        """A week before the one being published is finished business, and a
        "next game" pointing backwards would be worse than the bug it replaces."""
        store = self.two_weeks(crosswalk)
        page = build_next_game(
            store=store, season=SEASON, week="02", now=GENERATED_AT, crosswalk=crosswalk
        )
        assert page.game.opponent == "Ohio State"

    def test_nothing_ahead_anywhere_is_a_bye(self, crosswalk):
        store = self.two_weeks(crosswalk)
        page = build_next_game(
            store=store,
            season=SEASON,
            week="01",
            now=datetime(2026, 12, 1, 12, tzinfo=UTC),
            crosswalk=crosswalk,
        )
        assert page.game is None
        assert page.as_of.national_rank == 5


class TestPredictingOnlyWhatIsAhead:
    """A run forecasts the games that have not kicked off, and says so."""

    def week_one(self, crosswalk, *, now):
        store = MemorySnapshotStore()
        put_sagarin(store, fetched_at=PRESEASON_AT)
        put_games(
            store,
            week="01",
            fetched_at=PULLED_AT,
            games=[
                cfbd_game(game_id=1, week=1, kickoff=datetime(2026, 8, 29, 19, tzinfo=UTC),
                          home="Ohio State", away="Michigan",
                          home_points=21, away_points=17),
                cfbd_game(game_id=2, week=1, kickoff=datetime(2026, 9, 5, 19, tzinfo=UTC),
                          home="Texas", away="Texas State",
                          home_points=None, away_points=None),
            ],
        )
        write_state(
            store, seed_state(store=store, season=SEASON, now=SEEDED_AT, crosswalk=crosswalk)
        )
        return store, predict_week(
            store=store, season=SEASON, week="01", now=now, crosswalk=crosswalk
        )

    def test_a_game_already_kicked_off_is_not_forecast(self, crosswalk):
        _, log = self.week_one(crosswalk, now=datetime(2026, 8, 30, 12, tzinfo=UTC))
        assert [game.cfbd_game_id for game in log.games] == [2]

    def test_the_log_records_that_it_is_partial(self, crosswalk):
        """`forecast_from` is what lets scoring tell a game nobody could have
        forecast from a join that failed."""
        _, log = self.week_one(crosswalk, now=datetime(2026, 8, 30, 12, tzinfo=UTC))
        assert log.forecast_from == datetime(2026, 9, 5, 19, tzinfo=UTC)

    def test_a_whole_slate_records_nothing(self, crosswalk):
        """An ordinary week is unchanged by any of this."""
        _, log = self.week_one(crosswalk, now=datetime(2026, 8, 20, 12, tzinfo=UTC))
        assert len(log.games) == 2
        assert log.forecast_from is None

    def test_a_fully_played_week_refuses(self, crosswalk):
        from cfb.errors import ReplayError

        with pytest.raises(ReplayError, match="had already kicked off"):
            self.week_one(crosswalk, now=datetime(2026, 9, 20, 12, tzinfo=UTC))

    def test_the_hfa_boundary_follows_the_games_being_forecast(self, crosswalk):
        """**The fix, stated directly.** The boundary used to be the slate's first
        kickoff, so one early game whose kickoff predated every snapshot refused
        the entire week -- taking eight days of forecastable games with it."""
        _, log = self.week_one(crosswalk, now=datetime(2026, 8, 30, 12, tzinfo=UTC))
        assert log.model.hfa == PRESEASON_HFA

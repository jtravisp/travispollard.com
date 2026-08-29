"""Scoring a week against its predictions (SPEC-phase1 5).

**Written before `cfb/elo/scoring.py` exists.** Every name imported below is a
proposal; the signatures are argued for in `TestTheSignature` and in the notes
here, and the module is what has to match them.

## The three §5.2 failure modes are the accuracy page's whole integrity story

The page publishes MAE, Brier and an against-the-spread record. Each of those is a
mean, and a mean over a set that quietly lost a game is not wrong in any way a
reader can see. So §5.2 makes all three joins errors rather than filters, and the
tests below are arranged around the two that are easy to write badly:

**A prediction with no result is conditional**, and a test that only asserts "no
result, no error" passes against an implementation that never raises at all.
`TestAPredictionWithNoResult` asserts both halves in one class, and the
discriminating case is a game that *was played* and whose result did not come
back.

Knowing whether a game has been played is not free — the `/games` shape carries no
`completed` flag, only nullable scores — so these tests pin
`results_fetched_at` as the boundary: a game that kicked off before the results
capture was taken should have a score in it. That is a fact about the evidence
rather than about when the scoring run happened, which is the same rule §3.3's HFA
selection settled on, and for the same reason: a wall clock cannot be replayed.

**Teams disagreeing under a matching id is the one nobody writes by accident.**
The id matches, so the join succeeds; the teams do not, so every number computed
from it is attributed to the wrong game. `TestTheIdMatchesAndTheTeamsDoNot` builds
that fixture deliberately, including the subtle version where home and away are
merely swapped — which produces a perfectly plausible scored game with every sign
inverted.

## Two things §5.3 inherits from §4

**ATS goes through `sources.market_home_margin`.** `market_line` is CFBD's sign
convention (negative favours the home team) and `predicted_margin` is ours. The
cases in `TestTheMarketConversion` are chosen so that dropping the conversion
turns a loss into a win — not merely a different number, but the opposite verdict,
which is what makes the resulting record plausible and backwards.

**A null `market_line` is excluded, not pushed.** Zero is a real line meaning
pick'em; absent is not a line. `TestNullLinesAreExcluded` asserts the
**denominator** rather than the outcome, because a game entering as a push is
invisible in a win-loss count and shows up only in the count of games the record
was computed over.

## Fixtures

The market numbers are the real ones from `cfbd_lines_2026_week01.json` — Iowa
State −29.5, Portland State +24.5 — so the sign cases are the ones that actually
occur rather than ones chosen to make a point.

The results are constructed, and for now they have to be. The three §5.2 failure
modes cannot be captured from a real response by definition — no vendor publishes
a game whose id matches a prediction and whose teams do not. And there are no real
results at all yet: at the time of writing the 2026 season's first kickoff is
still hours away, so `/games` has nothing to return. `TestARealWeek` is the one
place a real capture would replace a constructed slate, and it is marked.
"""

from datetime import UTC, datetime, timedelta

import pytest

from cfb.elo.scoring import AtsRecord, ScoredWeek, score_week
from cfb.errors import UnscoredGameError
from cfb.predict import ModelBlock, PredictedGame, PredictionLog
from cfb.sources import RawGame, market_home_margin

SEASON = 2026
WEEK = "01"

KICKOFF = datetime(2026, 9, 5, 17, 0, tzinfo=UTC)
LATER = KICKOFF + timedelta(hours=6)
#: When the Sunday `/games` pull was taken. Every kickoff above is before it, so
#: every game in these fixtures has been played unless a test says otherwise.
RESULTS_FETCHED_AT = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
SCORED_AT = datetime(2026, 9, 6, 12, 30, tzinfo=UTC)

MODEL = ModelBlock(
    name="elo",
    elo_per_point=28,
    k=20,
    hfa=2.41,
    hfa_source="raw/sagarin/season=2026/week=preseason/2026-08-28T172006Z.meta.json",
    seeded_from="raw/sagarin/season=2026/week=preseason/2026-08-28T172006Z.txt",
    elo_state="elo/season=2026/week=preseason/2026-08-28T180000Z.json",
    sagarin_predictions_from="raw/sagarin/season=2026/week=preseason/2026-08-28T172006Z.txt",
    market_lines_from="raw/cfbd/season=2026/week=01/lines/2026-08-28T223443Z.json",
)


def predicted(
    game_id: int,
    *,
    home: str = "texas",
    away: str = "ohio-state",
    margin: float = 7.0,
    probability: float = 0.75,
    market_line: float | None = -7.5,
    source: str | None = "DraftKings",
    sagarin: float | None = 6.5,
    kickoff: datetime = KICKOFF,
    neutral: bool = False,
) -> PredictedGame:
    return PredictedGame(
        cfbd_game_id=game_id,
        kickoff=kickoff,
        home=home,
        away=away,
        neutral_site=neutral,
        predicted_margin=margin,
        win_probability=probability,
        elo_home=2358.0,
        elo_away=2486.0,
        market_line=market_line,
        market_line_source=source,
        sagarin_predictor_margin=sagarin,
    )


def log(*games: PredictedGame) -> PredictionLog:
    return PredictionLog(
        schema_version=1,
        season=SEASON,
        week=WEEK,
        generated_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        model=MODEL,
        games=list(games),
    )


def result(
    game_id: int,
    *,
    home: str = "Texas",
    away: str = "Ohio State",
    home_points: int | None = 24,
    away_points: int | None = 17,
    kickoff: datetime = KICKOFF,
    neutral: bool = False,
) -> RawGame:
    return RawGame.model_validate(
        {
            "id": game_id,
            "season": SEASON,
            "week": 1,
            "seasonType": "regular",
            "startDate": kickoff.isoformat().replace("+00:00", ".000Z"),
            "neutralSite": neutral,
            "homeTeam": home,
            "awayTeam": away,
            "homePoints": home_points,
            "awayPoints": away_points,
        }
    )


def score(predictions, results, **overrides):
    kwargs = {
        "results_fetched_at": RESULTS_FETCHED_AT,
        "now": SCORED_AT,
        **overrides,
    }
    return score_week(predictions, results, **kwargs)


# --- the signature ------------------------------------------------------------


class TestTheSignature:
    """§5.2 writes `score_week(predictions: dict, results: list[Game])`. Both
    argument types have moved on since, and one argument is missing.

    `predictions` is a `PredictionLog` rather than a bare dict, because §5.2's
    third failure mode compares the prediction's teams against the result's and a
    dict of margins cannot answer that. `results` are `RawGame`, which is what
    `sources` already produces for `replay` and `predict`.

    `results_fetched_at` is the addition, and it exists because the second failure
    mode needs to know whether a game has been played. The `/games` shape carries
    no `completed` flag, so the only honest signal is that the results capture was
    taken after the game kicked off.
    """

    def test_it_scores_a_matching_week(self):
        week = score(log(predicted(1)), [result(1)])
        assert isinstance(week, ScoredWeek)
        assert week.season == SEASON
        assert week.week == WEEK

    def test_the_scored_week_names_the_predictions_it_scored(self):
        """A scored week that cannot say which generation it graded is not
        auditable: predictions are write-once and a week can have several.
        """
        week = score(log(predicted(1)), [result(1)])
        assert week.predictions_generated_at == datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


# --- §5.2, the three failure modes --------------------------------------------


class TestAResultWithNoPrediction:
    """§5.2's first: the slate changed after generation, or the run missed a game."""

    def test_it_raises(self):
        with pytest.raises(UnscoredGameError):
            score(log(predicted(1)), [result(1), result(2, home="TCU", away="Baylor")])

    def test_the_error_names_the_unpredicted_game(self):
        with pytest.raises(UnscoredGameError) as excinfo:
            score(log(predicted(1)), [result(1), result(2, home="TCU", away="Baylor")])
        message = str(excinfo.value)
        assert "2" in message
        assert "TCU" in message or "Baylor" in message

    def test_an_unplayed_extra_game_raises_too(self):
        """A game on the results capture with no prediction is a hole in the
        prediction run whether or not it has been played. The prediction was
        supposed to cover the slate.
        """
        with pytest.raises(UnscoredGameError):
            score(
                log(predicted(1)),
                [result(1), result(2, home_points=None, away_points=None)],
            )


class TestAPredictionWithNoResult:
    """§5.2's second, and **both halves belong in one class**.

    Asserting only that an unplayed game is fine passes against an implementation
    that never raises at all. The pair is the test.
    """

    def test_an_unplayed_game_is_not_an_error(self):
        """Kickoff is after the results capture, so the game had not been played
        when the evidence was gathered. A postponement is normal.
        """
        week = score(
            log(predicted(1), predicted(2, kickoff=RESULTS_FETCHED_AT + timedelta(days=2))),
            [result(1)],
        )
        assert len(week.games) == 1

    def test_a_played_game_with_no_result_raises(self):
        """**The discriminating case.** Kickoff was before the capture, so a score
        should have come back and did not. That is a join that failed, and the
        game would otherwise vanish from every mean on the accuracy page.
        """
        with pytest.raises(UnscoredGameError):
            score(log(predicted(1), predicted(2)), [result(1)])

    def test_the_error_says_the_game_was_played(self):
        with pytest.raises(UnscoredGameError) as excinfo:
            score(log(predicted(1), predicted(2)), [result(1)])
        message = str(excinfo.value)
        assert "2" in message
        assert "kickoff" in message.lower() or "played" in message.lower()

    def test_a_result_row_with_no_score_is_the_same_failure(self):
        """The game is in the capture and unscored. Same conclusion as absent:
        it kicked off before the pull and no score came back.
        """
        with pytest.raises(UnscoredGameError):
            score(
                log(predicted(1), predicted(2)),
                [result(1), result(2, home_points=None, away_points=None)],
            )

    def test_an_unplayed_game_carrying_no_score_is_still_fine(self):
        """The control for the case above: same missing score, kickoff in the
        future, and no error. If these two agreed, the boundary would be doing
        nothing.
        """
        week = score(
            log(predicted(1), predicted(2, kickoff=RESULTS_FETCHED_AT + timedelta(days=2))),
            [
                result(1),
                result(
                    2,
                    home_points=None,
                    away_points=None,
                    kickoff=RESULTS_FETCHED_AT + timedelta(days=2),
                ),
            ],
        )
        assert len(week.games) == 1

    def test_a_postponed_game_is_counted_as_unscored_rather_than_forgotten(self):
        """Not an error, and not silent either. §5.2 forbids dropping a game
        without trace, and "nothing was warned about" is only acceptable if the
        document says how many were left out.
        """
        week = score(
            log(predicted(1), predicted(2, kickoff=RESULTS_FETCHED_AT + timedelta(days=2))),
            [result(1)],
        )
        assert week.unplayed == 1


class TestTheIdMatchesAndTheTeamsDoNot:
    """§5.2's third, and the one no test writes by accident.

    The join succeeds on the id, so nothing about the arithmetic looks wrong. Every
    number then describes a different game from the one it is filed under.
    """

    def test_swapped_home_and_away_raises(self):
        """**The subtle version.** The same two teams, the other way round.

        Scored rather than raised, this produces a complete game with the margin,
        the error and the ATS verdict all sign-inverted, and nothing downstream can
        tell. A neutral-site disagreement between the sources looks exactly like
        this (§5.1), which is why it has to be an error and not a repair.
        """
        with pytest.raises(UnscoredGameError):
            score(
                log(predicted(1, home="texas", away="ohio-state")),
                [result(1, home="Ohio State", away="Texas")],
            )

    def test_a_completely_different_team_raises(self):
        with pytest.raises(UnscoredGameError):
            score(
                log(predicted(1, home="texas", away="ohio-state")),
                [result(1, home="Texas", away="Baylor")],
            )

    def test_the_error_shows_both_sides_of_the_disagreement(self):
        """The reader has to be able to tell which source is wrong, and that means
        seeing what each of them said.
        """
        with pytest.raises(UnscoredGameError) as excinfo:
            score(
                log(predicted(1, home="texas", away="ohio-state")),
                [result(1, home="Ohio State", away="Texas")],
            )
        message = str(excinfo.value)
        assert "texas" in message.lower()
        assert "ohio" in message.lower()

    def test_it_is_checked_against_canonical_ids_not_vendor_names(self):
        """The prediction stores canonical ids and the result carries CFBD names,
        so the comparison has to resolve one side. Doing it the other way — string
        equality — would make every correctly matched game fail.
        """
        week = score(
            log(predicted(1, home="texas", away="ohio-state")),
            [result(1, home="Texas", away="Ohio State")],
        )
        assert len(week.games) == 1

    def test_a_neutral_site_game_is_held_to_the_same_check(self):
        """§4.2 makes home/away at a neutral site arbitrary, which is a reason to
        award no HFA — not a reason to accept the two sources disagreeing.
        """
        with pytest.raises(UnscoredGameError):
            score(
                log(predicted(1, home="texas", away="ohio-state", neutral=True)),
                [result(1, home="Ohio State", away="Texas", neutral=True)],
            )


# --- §5.3, per game -----------------------------------------------------------


class TestPerGameFigures:
    def test_actual_margin_is_from_the_home_perspective(self):
        week = score(log(predicted(1)), [result(1, home_points=24, away_points=17)])
        assert week.games[0].actual_margin == 7

    def test_error_is_predicted_minus_actual(self):
        week = score(
            log(predicted(1, margin=10.0)), [result(1, home_points=24, away_points=17)]
        )
        game = week.games[0]
        assert game.error == pytest.approx(3.0)
        assert game.abs_error == pytest.approx(3.0)

    def test_an_error_can_be_negative_and_the_absolute_one_cannot(self):
        week = score(
            log(predicted(1, margin=3.0)), [result(1, home_points=24, away_points=17)]
        )
        game = week.games[0]
        assert game.error == pytest.approx(-4.0)
        assert game.abs_error == pytest.approx(4.0)

    def test_the_brier_contribution_uses_the_unclamped_probability(self):
        """§3.7's clamp is presentational and applied at publish. Scoring against
        a clamped value would grade the model on what the page showed rather than
        on what it said.
        """
        week = score(
            log(predicted(1, probability=0.75)),
            [result(1, home_points=24, away_points=17)],
        )
        assert week.games[0].brier == pytest.approx(0.0625)

    def test_a_home_loss_scores_the_outcome_as_zero(self):
        week = score(
            log(predicted(1, probability=0.75)),
            [result(1, home_points=17, away_points=24)],
        )
        assert week.games[0].home_won is False
        assert week.games[0].brier == pytest.approx(0.5625)

    def test_the_sagarin_benchmark_is_scored_when_present(self):
        week = score(
            log(predicted(1, sagarin=6.5)), [result(1, home_points=24, away_points=17)]
        )
        assert week.games[0].sagarin_abs_error == pytest.approx(0.5)

    def test_a_missing_sagarin_margin_scores_as_none(self):
        week = score(
            log(predicted(1, sagarin=None)), [result(1, home_points=24, away_points=17)]
        )
        assert week.games[0].sagarin_abs_error is None


# --- §5.3, the market conversion ----------------------------------------------


class TestTheMarketConversion:
    """**These fail if `market_home_margin` is dropped**, and they fail as a
    reversed verdict rather than a different number.

    Both use real spreads from `cfbd_lines_2026_week01.json`. The numbers are
    chosen so the model's pick lands on opposite sides of the line depending on
    whether the conversion happened, and the actual result then makes one reading
    a win and the other a loss.
    """

    def test_an_away_favourite_the_model_liked_less(self):
        """Portland State's real line: `spread: +24.5`, meaning **away** by 24.5.

        Converted, the market's home margin is −24.5. The model has the home team
        losing by only 12.91, so it takes the home side. Home lost by 30, which
        does not cover −24.5, so the pick **loses**.

        Unconverted, the market reads as +24.5 (home favoured by 24.5); the model's
        −12.91 is below that, so it takes the away side, and the away team winning
        by 30 covers — a **win**. Same game, opposite verdict, and the record it
        produces looks entirely reasonable.
        """
        week = score(
            log(predicted(1, margin=-12.91, market_line=24.5)),
            [result(1, home_points=10, away_points=40)],
        )
        game = week.games[0]
        assert game.market_margin == pytest.approx(-24.5)
        assert game.beat_market is False

    def test_a_home_favourite_the_model_liked_less(self):
        """Iowa State's real line: `spread: -29.5`, home by 29.5.

        Converted, the market's home margin is +29.5 and the model's +27.24 is
        below it, so the pick is the away side. Home won by 35, so away did not
        cover: a **loss**. Unconverted, the market reads as −29.5, the model is
        above it, the pick becomes the home side, and home winning by 35 covers: a
        **win**.
        """
        week = score(
            log(predicted(1, margin=27.24, market_line=-29.5)),
            [result(1, home_points=45, away_points=10)],
        )
        game = week.games[0]
        assert game.market_margin == pytest.approx(29.5)
        assert game.beat_market is False

    def test_the_conversion_is_the_shared_one(self):
        """Not a local minus sign. §4.3 makes `sources.market_home_margin` the
        single site so scoring and anything else cannot drift apart.
        """
        week = score(
            log(predicted(1, market_line=24.5)), [result(1, home_points=10, away_points=40)]
        )
        assert week.games[0].market_margin == market_home_margin(24.5)

    def test_a_correct_pick_is_recorded_as_a_win(self):
        """The control. Without it every assertion above is satisfied by an
        implementation that always returns `False`.
        """
        week = score(
            log(predicted(1, margin=-12.91, market_line=24.5)),
            [result(1, home_points=10, away_points=20)],
        )
        assert week.games[0].beat_market is True

    def test_landing_exactly_on_the_line_is_a_push(self):
        week = score(
            log(predicted(1, margin=10.0, market_line=-7.0)),
            [result(1, home_points=24, away_points=17)],
        )
        game = week.games[0]
        assert game.beat_market is None
        assert game.market_push is True

    def test_the_market_is_scored_for_accuracy_on_its_own_margin(self):
        """§5.3's "the same figure for the market line": the market's MAE has to
        be computed on the converted margin too, or the benchmark it provides is
        the mirror of the real one.
        """
        week = score(
            log(predicted(1, market_line=-7.5)),
            [result(1, home_points=24, away_points=17)],
        )
        assert week.games[0].market_abs_error == pytest.approx(0.5)


class TestNullLinesAreExcluded:
    """§5.3: absent is not a line, and zero is.

    Every assertion here is about the **denominator**. A game entering the record
    as a push is invisible in a win-loss count — the wins and losses are unchanged
    and only the number of games the record covers moves.
    """

    def test_a_null_line_is_not_scored_against(self):
        week = score(
            log(predicted(1, market_line=None, source=None)),
            [result(1, home_points=24, away_points=17)],
        )
        game = week.games[0]
        assert game.market_margin is None
        assert game.beat_market is None
        assert game.market_abs_error is None

    def test_it_leaves_the_ats_record_empty_rather_than_one_and_zero(self):
        week = score(
            log(predicted(1, market_line=None, source=None)),
            [result(1, home_points=24, away_points=17)],
        )
        ats = week.full_slate.ats
        assert (ats.wins, ats.losses, ats.pushes) == (0, 0, 0)
        assert ats.excluded_no_line == 1
        assert ats.scored == 0

    def test_a_null_line_is_not_a_push(self):
        """The specific confusion. A push is a real outcome against a real line;
        this game had no line to push against.
        """
        week = score(
            log(predicted(1, market_line=None, source=None)),
            [result(1, home_points=24, away_points=17)],
        )
        assert week.full_slate.ats.pushes == 0
        assert week.games[0].market_push is None

    def test_a_zero_line_is_a_real_line_and_is_scored(self):
        """Pick'em. The distinction the exclusion exists to preserve."""
        week = score(
            log(predicted(1, margin=7.0, market_line=0.0)),
            [result(1, home_points=24, away_points=17)],
        )
        game = week.games[0]
        assert game.market_margin == 0.0
        assert game.beat_market is True
        assert week.full_slate.ats.scored == 1
        assert week.full_slate.ats.excluded_no_line == 0

    def test_the_denominator_accounts_for_every_game(self):
        """The property that makes the record readable: nothing is unaccounted
        for. Wins plus losses plus pushes plus exclusions is the whole slate.
        """
        week = score(
            log(
                predicted(1, margin=-12.91, market_line=24.5),
                predicted(2, margin=10.0, market_line=-7.0, home="tcu", away="baylor"),
                predicted(
                    3, market_line=None, source=None,
                    home="southern-california", away="ucla",
                ),
            ),
            [
                result(1, home_points=10, away_points=40),
                result(2, home="TCU", away="Baylor", home_points=24, away_points=17),
                result(3, home="USC", away="UCLA", home_points=24, away_points=17),
            ],
        )
        ats = week.full_slate.ats
        assert ats.scored + ats.excluded_no_line == len(week.games) == 3

    def test_a_model_that_matches_the_line_exactly_takes_no_side(self):
        """No edge, so no bet — and that is not a push.

        A push is a position that tied. This is the absence of a position, and
        counting it as a push would assert a bet the model never took and pull the
        record toward 50%. It fires almost never against half-point lines, which
        makes it cheap to get right rather than safe to ignore.
        """
        week = score(
            log(predicted(1, margin=7.5, market_line=-7.5)),
            [result(1, home_points=24, away_points=17)],
        )
        game = week.games[0]
        assert game.market_margin == pytest.approx(7.5)
        assert game.market_pick is None
        assert game.beat_market is None
        assert game.market_push is None

        ats = week.full_slate.ats
        assert (ats.wins, ats.losses, ats.pushes) == (0, 0, 0)
        assert ats.excluded_no_edge == 1
        assert ats.excluded_no_line == 0

    def test_every_game_lands_in_exactly_one_bucket_of_the_denominator(self):
        """The property all of this exists to protect: nothing is unaccounted for.

        Four games, one of each kind — a real pick, a push, no line, no edge — and
        the five counters have to sum to the slate. A game that fell out of the
        record entirely would leave the totals disagreeing and nothing else would
        show it.
        """
        week = score(
            log(
                predicted(1, margin=-12.91, market_line=24.5),
                predicted(2, margin=10.0, market_line=-7.0, home="tcu", away="baylor"),
                predicted(
                    3, market_line=None, source=None,
                    home="southern-california", away="ucla",
                ),
                predicted(4, margin=7.5, market_line=-7.5, home="oregon", away="washington"),
            ),
            [
                result(1, home_points=10, away_points=40),
                result(2, home="TCU", away="Baylor", home_points=24, away_points=17),
                result(3, home="USC", away="UCLA", home_points=24, away_points=17),
                result(4, home="Oregon", away="Washington", home_points=24, away_points=17),
            ],
        )
        ats = week.full_slate.ats
        assert ats.wins + ats.losses + ats.pushes == ats.scored
        assert ats.scored + ats.excluded_no_line + ats.excluded_no_edge == 4
        assert ats.games == len(week.games) == 4
        assert (ats.excluded_no_line, ats.excluded_no_edge, ats.pushes) == (1, 1, 1)

    def test_the_market_mae_skips_unpriced_games_too(self):
        """Averaging the market's error over games it never priced would divide by
        the wrong denominator and flatter the benchmark.
        """
        week = score(
            log(
                predicted(1, market_line=-7.5),
                predicted(2, market_line=None, source=None, home="tcu", away="baylor"),
            ),
            [
                result(1, home_points=24, away_points=17),
                result(2, home="TCU", away="Baylor", home_points=24, away_points=17),
            ],
        )
        assert week.full_slate.market_mae == pytest.approx(0.5)
        assert week.full_slate.market_games == 1


# --- §5.3, the aggregates -----------------------------------------------------


class TestTexasAndTheFullSlate:
    """The PRD wants both, separately, and Texas is a subset of one game a week."""

    def test_the_full_slate_averages_every_game(self):
        week = score(
            log(
                predicted(1, margin=10.0),
                predicted(2, margin=0.0, home="tcu", away="baylor"),
            ),
            [
                result(1, home_points=24, away_points=17),
                result(2, home="TCU", away="Baylor", home_points=24, away_points=17),
            ],
        )
        # errors of 3 and 7
        assert week.full_slate.games == 2
        assert week.full_slate.mae == pytest.approx(5.0)

    def test_texas_covers_only_games_texas_played(self):
        week = score(
            log(
                predicted(1, margin=10.0, home="texas", away="ohio-state"),
                predicted(2, margin=0.0, home="tcu", away="baylor"),
            ),
            [
                result(1, home_points=24, away_points=17),
                result(2, home="TCU", away="Baylor", home_points=24, away_points=17),
            ],
        )
        assert week.texas.games == 1
        assert week.texas.mae == pytest.approx(3.0)

    def test_texas_counts_a_road_game(self):
        """Texas is the team, not the home slot."""
        week = score(
            log(predicted(1, margin=-3.0, home="ohio-state", away="texas")),
            [result(1, home="Ohio State", away="Texas", home_points=17, away_points=24)],
        )
        assert week.texas.games == 1

    def test_a_week_texas_did_not_play_is_zero_games_not_an_error(self):
        week = score(
            log(predicted(1, home="tcu", away="baylor")),
            [result(1, home="TCU", away="Baylor", home_points=24, away_points=17)],
        )
        assert week.texas.games == 0
        assert week.texas.mae is None

    def test_the_ats_record_always_carries_its_sample_size(self):
        """§5.3: "always with the sample size attached". A 2-2 record over four
        games and over four hundred are different claims.
        """
        week = score(log(predicted(1)), [result(1)])
        assert isinstance(week.full_slate.ats, AtsRecord)
        assert week.full_slate.ats.scored == week.full_slate.ats.wins + (
            week.full_slate.ats.losses + week.full_slate.ats.pushes
        )


class TestTheSagarinCorrelation:
    """§3.6's series, which the accuracy page uses to retire the seed disclosure."""

    def test_it_is_computed_over_games_the_page_covered(self):
        week = score(
            log(
                predicted(1, margin=10.0, sagarin=10.0),
                predicted(2, margin=3.0, sagarin=3.0, home="tcu", away="baylor"),
                predicted(3, margin=-4.0, sagarin=-4.0, home="southern-california", away="ucla"),
            ),
            [
                result(1, home_points=24, away_points=17),
                result(2, home="TCU", away="Baylor", home_points=24, away_points=17),
                result(3, home="USC", away="UCLA", home_points=17, away_points=24),
            ],
        )
        assert week.sagarin_r == pytest.approx(1.0)

    def test_week_one_opens_at_one_because_the_seed_makes_it_an_identity(self):
        """§3.6, confirmed in §4: on seeded ratings a week 1 prediction *is*
        Sagarin's prediction, so the disclosure opens at exactly 1.0.
        """
        week = score(
            log(
                predicted(1, margin=10.67, sagarin=10.67),
                predicted(2, margin=6.2, sagarin=6.2, home="tcu", away="baylor"),
            ),
            [
                result(1, home_points=24, away_points=17),
                result(2, home="TCU", away="Baylor", home_points=30, away_points=17),
            ],
        )
        assert week.sagarin_r == pytest.approx(1.0)

    def test_it_is_none_when_too_few_games_carry_a_benchmark(self):
        """A correlation over one point is not a number. Publishing one would put
        a meaningless value on the page that retires a disclosure.
        """
        week = score(
            log(predicted(1, sagarin=6.5), predicted(2, sagarin=None, home="tcu", away="baylor")),
            [
                result(1, home_points=24, away_points=17),
                result(2, home="TCU", away="Baylor", home_points=24, away_points=17),
            ],
        )
        assert week.sagarin_r is None


class TestCalibration:
    """§5.3's curve: predicted probability bucket against observed win rate."""

    def test_each_bucket_carries_its_sample_size(self):
        week = score(
            log(
                predicted(1, probability=0.75),
                predicted(2, probability=0.72, home="tcu", away="baylor"),
            ),
            [
                result(1, home_points=24, away_points=17),
                result(2, home="TCU", away="Baylor", home_points=17, away_points=24),
            ],
        )
        buckets = {bucket.label: bucket for bucket in week.calibration}
        assert buckets["70-80%"].n == 2
        assert buckets["70-80%"].observed == pytest.approx(0.5)

    def test_empty_buckets_are_not_published_as_zero(self):
        """An unobserved bucket has no observed rate. Reporting 0.0 would draw a
        calibration curve through a point nothing supports.
        """
        week = score(log(predicted(1, probability=0.75)), [result(1)])
        assert all(bucket.n > 0 for bucket in week.calibration)


# --- the stored document ------------------------------------------------------


class TestTheScoredDocument:
    def test_it_carries_the_envelope(self):
        week = score(log(predicted(1)), [result(1)])
        assert week.schema_version == 1
        assert week.generated_at == SCORED_AT

    def test_it_round_trips(self):
        week = score(log(predicted(1)), [result(1)])
        assert ScoredWeek.model_validate_json(week.model_dump_json()) == week


@pytest.mark.skip(reason="week 1 has not been played yet; first kickoff 2026-08-29T07:00Z")
class TestARealWeek:
    """The one place a constructed slate should be a real response.

    Everything above is built by hand because the §5.2 failure modes cannot occur
    in a real capture by definition — a vendor does not publish a game whose id
    matches a prediction and whose teams do not. What a real week adds is scale:
    MAE, Brier and the calibration curve over ~90 games rather than three, which is
    where an off-by-one in a denominator becomes visible.

    Unskip once `tests/fixtures/cfbd_games_2026_week01.json` exists.
    """

    def test_a_real_slate_scores_end_to_end(self):
        raise NotImplementedError

"""Scoring a week's results against the predictions that anticipated them (§5).

The accuracy page publishes MAE, a Brier score and an against-the-spread record.
Every one of those is a mean, and **a mean over a set that quietly lost a game is
not wrong in any way a reader can see.** That is why §5.2 makes all three join
failures errors rather than filters, and why nothing in this module drops, warns
about, or repairs a row.

    a result with no prediction        -> UnscoredGameError
    a prediction with no result        -> only if the game was played
    the id matches, the teams do not   -> UnscoredGameError

The third is the one that would never announce itself. The join succeeds on the
id, so the arithmetic runs cleanly and every number produced describes a different
game from the one it is filed under. Its worst form is a straight home/away swap,
which yields a complete, plausible scored game with every sign inverted -- and
SPEC-phase1 5.1 records that the two sources genuinely do disagree about which
team is nominally home at a neutral site, so this is a real shape and not a
hypothetical.

**Two things come from §4 and both are easy to get backwards.** ``market_line`` is
CFBD's sign convention, negative favouring the home team, and every comparison
here goes through ``sources.market_home_margin`` rather than a local minus sign.
And a null line is *excluded* from the ATS record rather than scored as a push:
zero is a real line meaning pick'em, absent is not a line at all, and a game that
entered as a push would be invisible in a win-loss count.
"""

import statistics
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cfb.crosswalk import Crosswalk
from cfb.crosswalk import load as load_crosswalk
from cfb.elo import SCHEMA_VERSION
from cfb.errors import UnscoredGameError
from cfb.models import validating
from cfb.predict import PredictedGame, PredictionLog
from cfb.sources import RawGame, market_home_margin, week_position
from cfb.storage import SnapshotStore

__all__ = [
    "TEXAS",
    "Accuracy",
    "AtsRecord",
    "CalibrationBucket",
    "ScoredGame",
    "ScoredWeek",
    "accuracy_of",
    "calibration_of",
    "read_scored",
    "score_week",
    "scored_key",
    "scored_weeks",
    "write_scored",
]

#: The canonical id the PRD's per-team figures are about.
TEXAS = "texas"

#: Width of a calibration bucket, in probability. Ten points is what §6.4's
#: example prints ("70-80%") and it is the coarsest split that still shows a
#: model systematically over- or under-confident at the extremes.
_BUCKET = 0.10

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)

#: Second resolution and no colons, matching every other key this project builds.
_STAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"


class CalibrationBucket(BaseModel):
    """One band of the calibration curve (§5.3).

    ``n`` travels with every bucket because the curve is read as a shape, and a
    point resting on two games looks exactly like one resting on two hundred.
    """

    model_config = _STRICT

    label: str = Field(min_length=1)
    #: Mean predicted probability of the games in the band, not the band's midpoint.
    predicted: float
    observed: float
    n: int = Field(gt=0)


class AtsRecord(BaseModel):
    """A record against the spread, with everything it excluded (§5.3).

    **The exclusions are the point.** A bare ``2-2`` cannot distinguish a slate of
    four priced games from a slate of forty where thirty-six had no line, and the
    difference is the whole claim. ``games`` accounts for every game scored that
    week; nothing falls out of this record without being counted somewhere in it.
    """

    model_config = _STRICT

    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    pushes: int = Field(ge=0)
    #: No book priced the game. Not a push -- see the module docstring.
    excluded_no_line: int = Field(ge=0)
    #: The model's margin equalled the market's, so there was no side to take. A
    #: push is a position that tied; this is the absence of a position, and
    #: counting it as one would assert a bet that was never made.
    excluded_no_edge: int = Field(ge=0)

    @property
    def scored(self) -> int:
        """Games the record was actually computed over."""
        return self.wins + self.losses + self.pushes

    @property
    def games(self) -> int:
        return self.scored + self.excluded_no_line + self.excluded_no_edge

    @property
    def record(self) -> str:
        """``"2-2"``, or ``"2-2-1"`` when something pushed."""
        base = f"{self.wins}-{self.losses}"
        return f"{base}-{self.pushes}" if self.pushes else base


class Accuracy(BaseModel):
    """One population's figures (§5.3): Texas, or the full slate.

    Every mean is ``None`` rather than ``0.0`` when it has nothing to average.
    Texas plays once a week and has bye weeks, and a zero would draw a point on
    the accuracy page claiming a perfect prediction that was never made.
    """

    model_config = _STRICT

    games: int = Field(ge=0)
    mae: float | None
    brier: float | None
    #: Counted separately because the market prices a subset of the slate, so its
    #: MAE has a different denominator from ours. Averaging over games it never
    #: priced would flatter the benchmark.
    market_games: int = Field(ge=0)
    market_mae: float | None
    sagarin_games: int = Field(ge=0)
    sagarin_mae: float | None
    ats: AtsRecord


class ScoredGame(BaseModel):
    """One game, graded (§5.3). Home perspective throughout, except ``market_line``."""

    model_config = _STRICT

    cfbd_game_id: int
    kickoff: datetime
    home: str = Field(min_length=1)
    away: str = Field(min_length=1)
    neutral_site: bool

    predicted_margin: float
    #: Unclamped, as stored. §3.7's clamp is presentational and applied at
    #: publish; grading against it would score the model on what the page showed
    #: rather than on what it said.
    win_probability: float

    actual_margin: int
    home_won: bool
    error: float
    abs_error: float
    brier: float

    #: As CFBD published it: negative favours the home team.
    market_line: float | None
    market_line_source: str | None
    #: The same number in this project's convention, through
    #: ``sources.market_home_margin``. Everything below is computed from this and
    #: never from ``market_line``.
    market_margin: float | None
    market_abs_error: float | None
    #: Which side the model's edge pointed at, or ``None`` when there was no line
    #: or no edge. Carried so a published record can be audited game by game.
    market_pick: str | None
    #: ``True`` won, ``False`` lost, ``None`` when there was no bet to settle --
    #: which is a push, no line, or no edge, and ``market_push`` separates them.
    beat_market: bool | None
    market_push: bool | None

    sagarin_predictor_margin: float | None
    sagarin_abs_error: float | None


class ScoredWeek(BaseModel):
    """The document written to ``scored/season=2026/week=04/<ts>.json`` (§5.3)."""

    model_config = _STRICT

    schema_version: int = Field(ge=1)
    season: int = Field(ge=1869)
    week: str = Field(min_length=1)
    generated_at: datetime
    #: Which generation of the week's predictions was graded. They are write-once
    #: and a week can have several, so a scored week that cannot name one is not
    #: auditable.
    predictions_generated_at: datetime
    #: When the results were captured. **A model input, not a log field**: it is
    #: what decides whether a prediction with no result is an unplayed game or a
    #: failed join (§5.2), so a re-run against a different capture can reach a
    #: different verdict on the same week -- and a document that did not record it
    #: could not say which capture it had been.
    results_fetched_at: datetime
    #: Carried through from the prediction log (§4.4). Set when that log covered
    #: only part of its week, so these figures describe fewer games than the week
    #: they are filed under -- and §6.4 has to be able to say so. ``None`` on any
    #: week forecast in full, which is every ordinary week.
    forecast_from: datetime | None = None

    games: list[ScoredGame]
    #: Predictions with no result that had not been played. Not an error (§5.2),
    #: and not silent either: "nothing was dropped" is only checkable if the
    #: document says how many were left out.
    unplayed: int = Field(ge=0)

    texas: Accuracy
    full_slate: Accuracy
    calibration: list[CalibrationBucket]
    #: §3.6's series. ``None`` when fewer than two games carry a benchmark, or
    #: when either side has no variance -- a correlation over one point is not a
    #: number, and publishing one would retire a disclosure on nothing.
    sagarin_r: float | None


def score_week(
    predictions: PredictionLog,
    results: list[RawGame],
    *,
    results_fetched_at: datetime,
    now: datetime,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> ScoredWeek:
    """Grade one week. Raises on any of §5.2's three join failures.

    **The signature departs from §5.2's sketch in two ways, both forced.**
    ``predictions`` is a ``PredictionLog`` rather than a bare dict because the
    third failure mode compares the prediction's teams against the result's, which
    a mapping of margins cannot answer; §5.2 was written before §4 gave the log a
    type at all.

    ``results_fetched_at`` is the addition, and it is what makes the second
    failure mode decidable. A prediction with no result is fine while the game is
    unplayed and an error once it has been played, and the ``/games`` shape
    carries no ``completed`` flag -- only nullable scores, which is exactly the
    state an unplayed game and a failed join share. So the boundary is the
    evidence: a game that kicked off before the results capture was taken should
    have a score in it. That is a fact about the data rather than about when this
    ran, which is the same rule §3.3's HFA selection settled on and for the same
    reason -- a wall clock cannot be replayed.

    ``now`` stamps the document and nothing else.
    """
    resolver = crosswalk or load_crosswalk(predictions.season, data_dir=crosswalk_dir)

    predicted_by_id = {game.cfbd_game_id: game for game in predictions.games}
    results_by_id = {game.id: game for game in results}

    _refuse_unpredicted_results(results, predicted_by_id, predictions)

    scored: list[ScoredGame] = []
    unplayed = 0
    for prediction in predictions.games:
        outcome = results_by_id.get(prediction.cfbd_game_id)
        if outcome is None or not outcome.is_complete:
            # The result's own kickoff wins when there is one: a game that moved
            # is played when it was actually played, not when it was scheduled.
            kickoff = outcome.start_date if outcome is not None else prediction.kickoff
            if kickoff < results_fetched_at:
                raise UnscoredGameError(
                    f"game {prediction.cfbd_game_id} ({prediction.away} at "
                    f"{prediction.home}) kicked off at {kickoff.isoformat()}, before the "
                    f"results capture was taken at {results_fetched_at.isoformat()}, and "
                    f"came back with no score. A game that has been played and has no "
                    f"result is a join that failed (SPEC-phase1 5.2); scoring the week "
                    f"without it would drop it from every mean on the accuracy page"
                )
            unplayed += 1
            continue

        _refuse_mismatched_teams(prediction, outcome, resolver)
        scored.append(_score_game(prediction, outcome))

    return ScoredWeek(
        schema_version=SCHEMA_VERSION,
        season=predictions.season,
        week=predictions.week,
        generated_at=now,
        predictions_generated_at=predictions.generated_at,
        results_fetched_at=results_fetched_at,
        forecast_from=predictions.forecast_from,
        games=scored,
        unplayed=unplayed,
        texas=accuracy_of(
            [game for game in scored if TEXAS in (game.home, game.away)]
        ),
        full_slate=accuracy_of(scored),
        calibration=calibration_of(scored),
        sagarin_r=_sagarin_correlation(scored),
    )


def scored_key(
    *, season: int, week: str, generated_at: datetime, prefix: str = "scored"
) -> str:
    """``scored/season=2026/week=04/2026-09-21T123000Z.json`` (§5.3).

    ``prefix`` exists for one caller: `cfb backtest` writes the same document
    shape under ``backtest/``. **A separate prefix rather than a flag inside the
    document**, because the thing that must never happen is a retrospective week
    reaching the published season-to-date record, and a prefix cannot be
    overlooked by a reader the way a boolean can.
    """
    week_position(week)  # rejects a partition value that would open a second prefix
    return (
        f"{prefix}/season={season}/week={week}/"
        f"{generated_at.strftime(_STAMP_FORMAT)}.json"
    )


def write_scored(store: SnapshotStore, week: ScoredWeek, *, prefix: str = "scored") -> str:
    """Store one scored week write-once. Returns the key.

    ``put_bytes``, so an existing key raises rather than being replaced -- §5.3
    gives this document the same rules as ``predictions/``, and for a sharper
    reason. A prediction is a claim about the future and a rescore is a claim
    about the past, so a scored week that could be overwritten would let a run
    that did not like Sunday's numbers replace them with Monday's and leave no
    trace that it had. A rescore writes a second key beside the first.
    """
    key = scored_key(
        season=week.season, week=week.week, generated_at=week.generated_at, prefix=prefix
    )
    store.put_bytes(key, week.model_dump_json(indent=2).encode("utf-8"), "application/json")
    return key


def read_scored(store: SnapshotStore, key: str) -> ScoredWeek:
    """One stored scored week, validated at the boundary.

    Written by an earlier run rather than by the code reading it, so nothing
    guarantees it still matches this reader's schema -- the same reason
    ``elo.state.load_state`` and ``predict.read_predictions`` validate.
    """
    with validating(f"scored week at {key}"):
        return ScoredWeek.model_validate_json(store.get_bytes(key))


def scored_weeks(
    store: SnapshotStore, *, season: int, prefix: str = "scored"
) -> list[ScoredWeek]:
    """Every scored week of a season, in season order, newest generation of each.

    **Newest generation, not every generation.** A rescore writes a second key and
    keeps the first (§5.3), so a season-to-date figure built over all of them
    would count a rescored week twice -- which is invisible in a mean and obvious
    only in a denominator nobody checks.

    An empty list is the ordinary answer on the Friday before the season's first
    Sunday, and publishing has to survive it: the accuracy page opening with no
    results is a true statement, and refusing to publish would fail the one
    deadline §8 calls the SLO.
    """
    newest: dict[str, str] = {}
    for key in store.list_keys(f"{prefix}/season={season}/"):
        parsed = _parse_scored_key(key, prefix=prefix)
        if parsed is None:
            continue
        parsed_season, week, _ = parsed
        if parsed_season != season:
            continue
        # Lexicographic ascending from `list_keys`, fixed-width UTC stamps, so the
        # last sighting of a week is its newest generation.
        newest[week] = key
    return [
        read_scored(store, newest[week])
        for week in sorted(newest, key=lambda value: week_position(value))
    ]


def _parse_scored_key(key: str, *, prefix: str = "scored") -> tuple[int, str, datetime] | None:
    """``(season, week, generated_at)`` from a scored key, or ``None``.

    ``None`` rather than a raise, matching ``predict._parse_prediction_key``: this
    walks a prefix, and a listing is not the place to fail over a stray object
    someone put there by hand.
    """
    if not key.startswith(f"{prefix}/season=") or not key.endswith(".json"):
        return None
    try:
        _, season_part, week_part, stamp = key.split("/")
        season = int(season_part.removeprefix("season="))
        week = week_part.removeprefix("week=")
        generated_at = datetime.strptime(stamp.removesuffix(".json"), _STAMP_FORMAT)
    except ValueError:
        return None
    return season, week, generated_at.replace(tzinfo=UTC)


def _refuse_unpredicted_results(
    results: list[RawGame],
    predicted_by_id: dict[int, PredictedGame],
    predictions: PredictionLog,
) -> None:
    """§5.2's first mode. Played or not -- the prediction was meant to cover the slate.

    Either the slate changed after generation or the prediction run missed a game,
    and both are worth a red run: the first means the published predictions no
    longer describe the week, the second means they never did.
    """
    # A game that kicked off before this log began forecasting was already played
    # when the log was written, so no run could have predicted it. That is a fact
    # about when the pipeline came online, not a join that failed -- and the
    # distinction only exists because CFBD's week 1 of 2026 was ten days long and
    # this project went live in the middle of it. `forecast_from` is `None` for a
    # log covering a whole slate, which is every ordinary week.
    covered = [
        game
        for game in results
        if predictions.forecast_from is None or game.start_date >= predictions.forecast_from
    ]
    missing = [game for game in covered if game.id not in predicted_by_id]
    if not missing:
        return
    listed = ", ".join(
        f"{game.id} ({game.away_team} at {game.home_team})" for game in missing[:5]
    )
    more = f" and {len(missing) - 5} more" if len(missing) > 5 else ""
    raise UnscoredGameError(
        f"{len(missing)} result{'' if len(missing) == 1 else 's'} for season "
        f"{predictions.season} week {predictions.week} have no prediction: {listed}{more}.\n"
        f"Either the slate changed after the predictions were generated or the run missed "
        f"a game. Both leave the published predictions describing a different week from the "
        f"one that was played, so neither is something to score around (SPEC-phase1 5.2)."
    )


def _refuse_mismatched_teams(
    prediction: PredictedGame, outcome: RawGame, resolver: Crosswalk
) -> None:
    """§5.2's third mode, and the one that would never announce itself.

    Compared as canonical ids, because the prediction stores ids and the result
    carries CFBD names -- string equality between the two would fail on every
    correctly matched game instead.

    A straight home/away swap is the case that makes this necessary rather than
    tidy. Scored, it produces a complete game with the margin, the error and the
    ATS verdict all sign-inverted, and no downstream check could tell. §5.1
    records that the sources really do disagree about who is nominally home at a
    neutral site, which is why this raises rather than quietly reordering: one of
    the two is wrong and this module cannot know which.
    """
    home = resolver.from_cfbd(outcome.home_team)
    away = resolver.from_cfbd(outcome.away_team)
    if (home, away) == (prediction.home, prediction.away):
        return

    swapped = (home, away) == (prediction.away, prediction.home)
    note = (
        "\nThe teams are the same two, the other way round. Scored, that would invert "
        "the margin, the error and the against-the-spread verdict and look entirely "
        "normal."
        if swapped
        else ""
    )
    raise UnscoredGameError(
        f"game {prediction.cfbd_game_id} matched on id and disagrees on teams.\n"
        f"  prediction: {prediction.away} at {prediction.home}\n"
        f"  result:     {away} at {home}  (CFBD: {outcome.away_team!r} at "
        f"{outcome.home_team!r})"
        f"{note}\n"
        f"One of the two is wrong and this cannot tell which (SPEC-phase1 5.2)."
    )


def _score_game(prediction: PredictedGame, outcome: RawGame) -> ScoredGame:
    actual = outcome.home_points - outcome.away_points
    home_won = actual > 0
    error = prediction.predicted_margin - actual

    market_margin = (
        None if prediction.market_line is None else market_home_margin(prediction.market_line)
    )
    pick, beat, push = _settle(prediction.predicted_margin, market_margin, actual)

    return ScoredGame(
        cfbd_game_id=prediction.cfbd_game_id,
        kickoff=prediction.kickoff,
        home=prediction.home,
        away=prediction.away,
        neutral_site=prediction.neutral_site,
        predicted_margin=prediction.predicted_margin,
        win_probability=prediction.win_probability,
        actual_margin=actual,
        home_won=home_won,
        error=error,
        abs_error=abs(error),
        brier=(prediction.win_probability - (1.0 if home_won else 0.0)) ** 2,
        market_line=prediction.market_line,
        market_line_source=prediction.market_line_source,
        market_margin=market_margin,
        market_abs_error=None if market_margin is None else abs(market_margin - actual),
        market_pick=pick,
        beat_market=beat,
        market_push=push,
        sagarin_predictor_margin=prediction.sagarin_predictor_margin,
        sagarin_abs_error=(
            None
            if prediction.sagarin_predictor_margin is None
            else abs(prediction.sagarin_predictor_margin - actual)
        ),
    )


def _settle(
    predicted_margin: float, market_margin: float | None, actual: int
) -> tuple[str | None, bool | None, bool | None]:
    """``(pick, beat, push)`` for one game against the spread.

    The model takes whichever side its margin sits on relative to the line, and
    the bet settles on which side the *result* fell. Both comparisons are against
    ``market_margin`` -- this project's convention -- and never against the stored
    vendor value; §4.3 has the sign detail, and getting it wrong inverts the
    verdict rather than merely shifting a number.

    Three ways there is nothing to settle, and they are kept distinct:

    * no line at all -> ``(None, None, None)``
    * the model equals the line, so there is no side -> ``(None, None, None)``
    * the result lands exactly on the line -> a push, which *is* a settled bet
    """
    if market_margin is None or predicted_margin == market_margin:
        return None, None, None
    if actual == market_margin:
        return ("home" if predicted_margin > market_margin else "away"), None, True
    if predicted_margin > market_margin:
        return "home", actual > market_margin, False
    return "away", actual < market_margin, False


def _mean(values: list[float]) -> float | None:
    """``None`` rather than ``0.0`` on an empty population -- see ``Accuracy``."""
    return statistics.fmean(values) if values else None


def accuracy_of(games: list[ScoredGame]) -> Accuracy:
    """§5.3's figures over any set of scored games.

    Public because §6.4's season-to-date record is the same computation over the
    union of every scored week, and **it cannot be an average of the weekly
    means**: the weeks have different denominators, and averaging averages would
    weight a three-game Tuesday equally with a sixty-game Saturday. Publishing
    recomputes from the rows for that reason, through this function rather than
    through a second copy of it.
    """
    priced = [game for game in games if game.market_abs_error is not None]
    benchmarked = [game for game in games if game.sagarin_abs_error is not None]

    return Accuracy(
        games=len(games),
        mae=_mean([game.abs_error for game in games]),
        brier=_mean([game.brier for game in games]),
        market_games=len(priced),
        market_mae=_mean([game.market_abs_error for game in priced]),
        sagarin_games=len(benchmarked),
        sagarin_mae=_mean([game.sagarin_abs_error for game in benchmarked]),
        ats=AtsRecord(
            wins=sum(1 for game in games if game.beat_market is True),
            losses=sum(1 for game in games if game.beat_market is False),
            pushes=sum(1 for game in games if game.market_push is True),
            excluded_no_line=sum(1 for game in games if game.market_margin is None),
            excluded_no_edge=sum(
                1
                for game in games
                if game.market_margin is not None and game.market_pick is None
            ),
        ),
    )


def calibration_of(games: list[ScoredGame]) -> list[CalibrationBucket]:
    """Predicted probability against observed win rate, in ten-point bands (§5.3).

    Empty bands are omitted rather than published as zero: a bucket nothing landed
    in has no observed rate, and a ``0.0`` would draw the curve through a point no
    game supports.
    """
    bands: dict[int, list[ScoredGame]] = {}
    for game in games:
        # 1.0 belongs in the top band rather than one of its own.
        index = min(int(game.win_probability / _BUCKET), int(1 / _BUCKET) - 1)
        bands.setdefault(index, []).append(game)

    return [
        CalibrationBucket(
            label=f"{index * 10}-{index * 10 + 10}%",
            predicted=statistics.fmean([game.win_probability for game in members]),
            observed=statistics.fmean([1.0 if game.home_won else 0.0 for game in members]),
            n=len(members),
        )
        for index, members in sorted(bands.items())
    ]


def _sagarin_correlation(games: list[ScoredGame]) -> float | None:
    """§3.6's weekly Pearson r between our margins and Sagarin's.

    Over the *predictions*, not the errors: §3.6 is about whether the two still
    say the same thing, which is what the seed disclosure claims and what it
    needs to be able to stop claiming.

    ``None`` when it cannot be computed -- fewer than two benchmarked games, or no
    variance on either side. A correlation over one point is not a number, and
    this one decides when a published disclosure retires.
    """
    pairs = [
        (game.predicted_margin, game.sagarin_predictor_margin)
        for game in games
        if game.sagarin_predictor_margin is not None
    ]
    if len(pairs) < 2:
        return None
    try:
        return statistics.correlation([ours for ours, _ in pairs], [theirs for _, theirs in pairs])
    except statistics.StatisticsError:
        # Constant on one side, so the correlation is undefined rather than zero.
        return None

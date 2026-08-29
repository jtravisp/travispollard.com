"""Building the documents the site fetches (SPEC-phase1 6).

``/cfb/data/*`` is **page-shaped, not resource-shaped** (§6.1): one document per
route, each rendered by exactly one fetch. The cost is duplication between
documents and a generator that changes when a page does, which is the right trade
at three routes and the wrong one at thirty.

Nothing here computes a rating, a margin or a mean. Every number in these
documents was written to the bucket by an earlier run and is read back out --
``predictions/`` for the forecast, ``scored/`` for the record, ``elo/`` for the
ratings the forecast used. **Publishing that recomputed anything would be a
second implementation of the model living on the read path**, where no replay
check looks, and the first sign of it would be a page disagreeing with the
prediction log it was built from.

Two things do happen here and nowhere else, both of them presentational:

    the clamp        §3.7's [0.001, 0.999], applied on the way out and never in
                     storage, so the Brier scores stay computed on what the model
                     actually said
    rendered names   §6.3: canonical ids are the pipeline's business, and the
                     crosswalk's job ends at this boundary

**These are the only mutable objects the pipeline writes besides
``predictions/index.json``,** and for the same reason: they are derived, they are
rebuildable from the evidence at any time, and a page that had to list a prefix
to find the newest one would be doing the composition the PRD forbids it.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cfb.crosswalk import Crosswalk
from cfb.crosswalk import load as load_crosswalk
from cfb.elo import SCHEMA_VERSION, EloState
from cfb.elo.scoring import (
    TEXAS,
    CalibrationBucket,
    ScoredGame,
    ScoredWeek,
    accuracy_of,
    calibration_of,
    scored_weeks,
)
from cfb.elo.state import load_state
from cfb.errors import ReplayError
from cfb.models import validating
from cfb.predict import (
    PredictedGame,
    PredictionLog,
    index_entries,
    prediction_generations,
    read_predictions,
)
from cfb.sources import week_position
from cfb.storage import SnapshotStore

__all__ = [
    "ACCURACY_KEY",
    "CACHE_CONTROL",
    "NEXT_GAME_KEY",
    "SLATE_KEY",
    "PROBABILITY_CEILING",
    "PROBABILITY_FLOOR",
    "SEED_DISCLOSURE_THRESHOLD",
    "AccuracyDocument",
    "AsOf",
    "AtsSummary",
    "Backtest",
    "NextGameDocument",
    "PublishedGame",
    "Record",
    "SlateDocument",
    "SlateGame",
    "SeedDisclosure",
    "WeekPoint",
    "build_accuracy",
    "build_next_game",
    "build_slate",
    "clamp",
    "publish",
]

#: §6.1. The keys match the URL path exactly -- ``cfb/data/next-game.json`` is
#: served at ``/cfb/data/next-game.json`` with no origin_path stripping, which is
#: what ``cfb/terraform/main.tf`` says the bucket layout exists for.
NEXT_GAME_KEY = "cfb/data/next-game.json"
ACCURACY_KEY = "cfb/data/accuracy.json"
SLATE_KEY = "cfb/data/slate.json"

#: §3.7. A model that prints 100% claims a certainty no model has, and the first
#: time it is wrong the page had no way to have been right.
PROBABILITY_FLOOR = 0.001
PROBABILITY_CEILING = 0.999

#: §6.5. Set at upload because the `/cfb/data/*` behaviour runs on
#: CachingOptimized, which takes its freshness from the origin's header rather
#: than from a TTL in Terraform. Five minutes at the browser, an hour at the
#: edge -- and the edge hour is what the publish invalidation exists to cut short
#: on the one day a week the number changes.
CACHE_CONTROL = "public, max-age=300, s-maxage=3600"

#: §3.6. The correlation against Sagarin PREDICTOR below which the seed
#: disclosure retires, because the ratings have stopped being a restatement of
#: the page they were seeded from.
SEED_DISCLOSURE_THRESHOLD = 0.90

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)


def clamp(win_probability: float) -> float:
    """§3.7's presentational clamp.

    **Applied here and never in storage.** The stored probability is what the
    model said and §5.3's Brier scores are computed on it; clamping on the way in
    would grade the model on what the page displayed instead.
    ``test_predict.py::test_probabilities_are_not_clamped_here`` pins the storage
    half of that rule, and this is the other half.
    """
    return min(max(win_probability, PROBABILITY_FLOOR), PROBABILITY_CEILING)


# --- next-game.json -----------------------------------------------------------


class PublishedGame(BaseModel):
    """§6.3's ``game`` block: one team's next game, from that team's perspective."""

    model_config = _STRICT

    kickoff: datetime
    #: **The week this game belongs to, which is not always the run's week.**
    #: `/cfb` shows the next unplayed game wherever it is, so a run during a long
    #: week can legitimately feature a game from an earlier week than the one
    #: being published. The page prints this beside the kickoff; printing the
    #: envelope's week there labelled a week 1 game "Week 2".
    week: str = Field(min_length=1)
    #: A rendered name, not a canonical id (§6.3).
    opponent: str = Field(min_length=1)
    home: bool
    #: **Needed because ``home`` alone is misleading at a neutral site.** CFBD
    #: nominates one team as home for a game played on neither campus, and the
    #: page was saying "X is at home" about it. §5.1 records that the two sources
    #: can even disagree about which team that is.
    neutral_site: bool
    #: **Signed for the subject team, not for the home team.** Everything in
    #: ``predictions/`` is from the home team's perspective (§4.2); this document
    #: is read by a page about one team, and an away game whose margin was left in
    #: the other convention is the kind of sign error that renders perfectly.
    predicted_margin: float
    #: Clamped (§3.7), and for the subject team.
    win_probability: float
    #: **As the book published it**, negative favouring the home team (§4.3).
    #: Left in the vendor's convention because §6.3's contract says so and because
    #: a quoted line is a fact about the market; the page prints it beside
    #: ``line_source``, which is what makes the convention readable.
    market_line: float | None
    line_source: str | None


class AsOf(BaseModel):
    """§6.3's ``as_of``: which ratings the forecast above was made from.

    Not "the current ratings". It is the state the prediction run actually read,
    named by that prediction's own model block, so the two halves of the page
    cannot come from different weeks.
    """

    model_config = _STRICT

    week: str = Field(min_length=1)
    elo: float
    #: Among FBS teams. The Elo state rates all 266 teams Sagarin covers,
    #: including 128 FCS ones, and "national rank" on a college football page
    #: means the FBS table -- a rank counting FCS teams in its denominator is a
    #: different number wearing the same word.
    national_rank: int = Field(ge=1)
    #: The denominator, for the same reason §5.3 makes every sample size travel
    #: with its mean.
    fbs_teams: int = Field(ge=1)


class NextGameDocument(BaseModel):
    """``cfb/data/next-game.json`` (§6.3), rendered by ``/cfb``."""

    model_config = _STRICT

    schema_version: int = Field(ge=1)
    generated_at: datetime
    season: int = Field(ge=1869)
    week: str = Field(min_length=1)

    #: The rendered name of the team this document is about.
    team: str = Field(min_length=1)
    #: ``None`` on a bye. §6.3 gives no shape for one, and a bye is an ordinary
    #: week, so the page has to be told rather than left to infer it from an
    #: absence. ``as_of`` is still populated: the ratings are true whether or not
    #: there is a fixture, and blanking the whole page for a bye would be a worse
    #: statement than the missing game.
    game: PublishedGame | None
    as_of: AsOf


class SlateGame(BaseModel):
    """One game on the week's board.

    **Home perspective, unlike ``next-game.json``.** That document is about one
    team and re-signs everything to it; this one is a list of games with no
    subject, so it keeps the storage convention (§4.2) and the page renders the
    sign against the home team's name. Mixing the two conventions in one contract
    is how a page ends up drawing a favourite as an underdog.
    """

    model_config = _STRICT

    cfbd_game_id: int
    kickoff: datetime
    #: Rendered names (§6.3), home first in the field order the page reads.
    home: str = Field(min_length=1)
    away: str = Field(min_length=1)
    neutral_site: bool
    #: Positive favours the home team.
    predicted_margin: float
    #: The home team's, clamped (§3.7).
    win_probability: float
    #: As the book published it: negative favours the home team (§4.3).
    market_line: float | None
    line_source: str | None
    #: ``True`` when this game involves the team ``next-game.json`` is about, so
    #: the page can mark it without knowing who that is.
    featured: bool


class SlateDocument(BaseModel):
    """``cfb/data/slate.json`` (this project's addition to §6.1), for ``/cfb/slate``.

    §6.1 named three routes and none of them showed the other 119 games the model
    forecasts every week. The document exists because the pipeline was already
    computing every row and publishing one of them.

    Its own route rather than a section of ``/cfb``, so §6.1's one-fetch-per-page
    rule survives: the front page stays a small document that loads fast, and the
    full board is a page you choose to open.
    """

    model_config = _STRICT

    schema_version: int = Field(ge=1)
    generated_at: datetime
    season: int = Field(ge=1869)
    week: str = Field(min_length=1)
    #: Which team's games are flagged ``featured``.
    team: str = Field(min_length=1)
    #: How many of the slate a book had priced when this was generated. Carried
    #: because a week where it collapses is a `/lines` pull that did not happen,
    #: and the page should be able to say so rather than showing blanks.
    priced: int = Field(ge=0)
    #: The earliest kickoff forecast, when the run covered less than the whole
    #: week (§4.4). ``None`` on an ordinary week. Carried so the page can say why
    #: a slate is shorter than the week it names, rather than leaving a reader to
    #: conclude the model missed games.
    forecast_from: datetime | None
    games: list[SlateGame]


# --- accuracy.json ------------------------------------------------------------


class AtsSummary(BaseModel):
    """§6.4 prints ``ats`` as a bare string; §5.3 says the sample size always
    travels with it. **§5.3 wins**, so this is an object.

    A bare ``"2-2"`` cannot distinguish four priced games from forty where
    thirty-six had no line, and that difference is the whole claim the page makes.
    ``record`` is kept so the page still has the string to print.
    """

    model_config = _STRICT

    record: str = Field(min_length=1)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    pushes: int = Field(ge=0)
    excluded_no_line: int = Field(ge=0)
    excluded_no_edge: int = Field(ge=0)


class Record(BaseModel):
    """One population's season-to-date figures (§6.4): Texas, or the full slate.

    Every mean carries its own denominator and every one is ``None`` rather than
    ``0.0`` on an empty population -- §5.3's rule, unchanged on the way out,
    because a zero here draws a point on the accuracy page claiming a perfect
    prediction that was never made.
    """

    model_config = _STRICT

    games: int = Field(ge=0)
    mae: float | None
    brier: float | None
    #: §6.4 calls this ``line_mae``. Its denominator is ``line_games``, which is
    #: smaller than ``games``: the market prices a subset of the slate, and
    #: averaging it over games no book quoted would flatter the benchmark.
    line_games: int = Field(ge=0)
    line_mae: float | None
    sagarin_games: int = Field(ge=0)
    sagarin_mae: float | None
    ats: AtsSummary


class WeekPoint(BaseModel):
    """One point of §6.4's ``by_week`` series."""

    model_config = _STRICT

    week: str = Field(min_length=1)
    games: int = Field(ge=0)
    mae: float | None
    #: §3.6's weekly correlation. ``None`` when the week had fewer than two games
    #: Sagarin's page covered.
    sagarin_r: float | None
    #: Set when the week was only partly forecast (§4.4), so its figures cover
    #: less than the week they are filed under. **A partial week that reads as
    #: complete is the seed-disclosure problem in a new place**: the number is
    #: right and the thing it describes is smaller than the label suggests.
    forecast_from: datetime | None


class SeedDisclosure(BaseModel):
    """§6.4's ``seed_disclosure``, which is what §3.6 renders.

    **It never disappears.** Once the correlation has fallen below the threshold,
    ``active`` goes false and ``retired_week`` records where -- and the page keeps
    showing that it retired, because a disclosure that vanishes without trace is
    worse than one that never appeared.
    """

    model_config = _STRICT

    active: bool
    threshold: float
    #: The newest week that produced one. ``None`` before any week has two
    #: benchmarked games, which is not the same as a correlation of zero.
    current_r: float | None
    retired_week: str | None


class Backtest(BaseModel):
    """Weeks scored retrospectively, kept apart from the live record (§6.4).

    **This is not the model's record and the page must never present it as one.**
    A backtested week was scored after its games were played, so it carries none
    of the evidence `predictions/` exists to provide -- SPEC-phase1 1.1 gives up
    git specifically to keep "written before kickoff" true, and folding these
    into `full_slate` would spend that.

    For week 1 in particular the figures measure something else entirely. The
    seed is ``1500 + (rating - mean) * 28`` and the preseason page's rating
    columns are identical (§1.2), so a week 1 forecast reproduces Sagarin's
    PREDICTOR exactly and ``sagarin_r`` opens at 1.0. What a week 1 backtest
    reports is the accuracy of Sagarin's preseason page. ``measures_the_seed``
    says so in the document rather than leaving the page to know it.
    """

    model_config = _STRICT

    through_week: str | None
    #: True while every backtested week is one whose forecast is arithmetically
    #: the seed -- which is week 1, and only week 1.
    measures_the_seed: bool
    texas: Record
    full_slate: Record
    by_week: list[WeekPoint]


class AccuracyDocument(BaseModel):
    """``cfb/data/accuracy.json`` (§6.4), rendered by ``/cfb/accuracy``."""

    model_config = _STRICT

    schema_version: int = Field(ge=1)
    generated_at: datetime
    season: int = Field(ge=1869)
    #: The publish run's week, matching ``next-game.json`` so the two documents on
    #: the site are visibly one run (§6.2's envelope).
    week: str = Field(min_length=1)
    #: The newest week this document actually has results for, which is **not**
    #: the envelope's week: a Friday publish is for a week nobody has played yet.
    #: ``None`` before the season's first Sunday.
    through_week: str | None

    texas: Record
    full_slate: Record
    calibration: list[CalibrationBucket]
    by_week: list[WeekPoint]
    seed_disclosure: SeedDisclosure
    #: ``None`` when no week has been backtested, which is the ordinary case.
    backtest: Backtest | None


# --- building them ------------------------------------------------------------


def build_next_game(
    *,
    store: SnapshotStore,
    season: int,
    week: str,
    now: datetime,
    team: str = TEXAS,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> NextGameDocument:
    """§6.3, from the newest predictions stored for ``week``.

    **The newest generation, unlike scoring.** ``predictions_to_score`` refuses a
    generation written after its slate started, because grading one would claim a
    forecast that had the results in hand. Publishing has the opposite duty: the
    page should show the most recent thing the model said, and a regenerate exists
    precisely because someone wanted the newer number on the site.

    **And the next *unplayed* game, wherever it is** -- not the featured game of
    the week being published. Those are the same thing on an ordinary week and
    they came apart badly in 2026: CFBD week 1 ran ten days across two Saturdays,
    the run published week 2, and `/cfb` showed a game a fortnight out while the
    team was idle and its actual next opponent sat unforecast in week 1. A page
    whose headline is "next game" has to mean it.

    Raises when the week has no predictions at all. That is the Friday SLO failing
    (§8) -- the publish run exists to put a forecast on the page before kickoff,
    and one that quietly published a page without one would have removed the only
    signal that it did not happen.
    """
    resolver = crosswalk or load_crosswalk(season, data_dir=crosswalk_dir)
    log, fixture = _next_fixture(store, season=season, week=week, team=team, now=now)
    state = load_state(store, log.model.elo_state)

    return _next_game_document(log, fixture, state, resolver, team=team, now=now)


def build_slate(
    *,
    store: SnapshotStore,
    season: int,
    week: str,
    now: datetime,
    team: str = TEXAS,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> SlateDocument:
    """Every game the model forecast this week, in kickoff order.

    Reads the same generation ``build_next_game`` does, so the featured game on
    ``/cfb`` and its row here can never be two different forecasts.
    """
    resolver = crosswalk or load_crosswalk(season, data_dir=crosswalk_dir)
    log = _newest_predictions(store, season=season, week=week)

    games = [
        SlateGame(
            cfbd_game_id=game.cfbd_game_id,
            kickoff=game.kickoff,
            home=resolver.display_name(game.home),
            away=resolver.display_name(game.away),
            neutral_site=game.neutral_site,
            predicted_margin=game.predicted_margin,
            win_probability=clamp(game.win_probability),
            market_line=game.market_line,
            line_source=game.market_line_source,
            featured=team in (game.home, game.away),
        )
        for game in sorted(log.games, key=lambda g: (g.kickoff, g.cfbd_game_id))
    ]

    return SlateDocument(
        schema_version=SCHEMA_VERSION,
        generated_at=now,
        season=season,
        week=log.week,
        team=resolver.display_name(team),
        priced=sum(1 for game in games if game.market_line is not None),
        forecast_from=log.forecast_from,
        games=games,
    )


def build_accuracy(
    *,
    store: SnapshotStore,
    season: int,
    week: str,
    now: datetime,
) -> AccuracyDocument:
    """§6.4, from every scored week of the season.

    **Season-to-date is recomputed over the union of the rows, not averaged over
    the weekly means.** The weeks have different denominators -- a three-game
    Tuesday and a sixty-game Saturday -- so a mean of means would weight them
    equally and quietly publish a different number from the one the rows support.
    ``scoring.accuracy_of`` is that computation, imported rather than restated.

    An empty season is legal and produces a document saying so: zero games, every
    mean ``None``, ``through_week`` ``None``. The Friday before the season's first
    Sunday is exactly that, and refusing to publish would fail §8's SLO over the
    absence of results nobody could have had.
    """
    weeks = scored_weeks(store, season=season)
    games = [game for scored in weeks for game in scored.games]

    return AccuracyDocument(
        schema_version=SCHEMA_VERSION,
        generated_at=now,
        season=season,
        week=week,
        through_week=weeks[-1].week if weeks else None,
        texas=_record([game for game in games if TEXAS in (game.home, game.away)]),
        full_slate=_record(games),
        calibration=calibration_of(games),
        by_week=[
            WeekPoint(
                week=scored.week,
                games=len(scored.games),
                mae=scored.full_slate.mae,
                sagarin_r=scored.sagarin_r,
                forecast_from=scored.forecast_from,
            )
            for scored in weeks
        ],
        seed_disclosure=_seed_disclosure(weeks),
        backtest=_backtest(scored_weeks(store, season=season, prefix="backtest")),
    )


def publish(
    *,
    store: SnapshotStore,
    season: int,
    week: str,
    now: datetime,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> dict[str, str]:
    """Build both documents and write them. Returns ``{key: what it describes}``.

    **Both are built before either is written.** They are read by two routes of
    one site and they name the same season and week, so a run that wrote the
    forecast and then failed on the record would leave the site showing a new
    prediction beside last week's accuracy -- two documents from two runs, with
    nothing on either page saying so.

    ``put_json``, not ``put_bytes``: these are the derived, mutable end of the
    pipeline. Everything they are derived *from* is write-once, which is what
    makes overwriting them safe -- any version can be rebuilt from the evidence,
    and the evidence cannot be rewritten to change what a rebuild would say.
    """
    next_game = build_next_game(
        store=store,
        season=season,
        week=week,
        now=now,
        crosswalk=crosswalk,
        crosswalk_dir=crosswalk_dir,
    )
    slate = build_slate(
        store=store,
        season=season,
        week=week,
        now=now,
        crosswalk=crosswalk,
        crosswalk_dir=crosswalk_dir,
    )
    accuracy = build_accuracy(store=store, season=season, week=week, now=now)

    store.put_json(
        NEXT_GAME_KEY, next_game.model_dump(mode="json"), cache_control=CACHE_CONTROL
    )
    store.put_json(SLATE_KEY, slate.model_dump(mode="json"), cache_control=CACHE_CONTROL)
    store.put_json(ACCURACY_KEY, accuracy.model_dump(mode="json"), cache_control=CACHE_CONTROL)
    return {NEXT_GAME_KEY: "next-game", SLATE_KEY: "slate", ACCURACY_KEY: "accuracy"}


# --- the pieces ---------------------------------------------------------------


def _next_fixture(
    store: SnapshotStore, *, season: int, week: str, team: str, now: datetime
) -> tuple[PredictionLog, PredictedGame | None]:
    """The log to describe, and the team's next unplayed game in it.

    Searches **every** week of the season that has stored predictions and takes
    the earliest kickoff still ahead of ``now``.

    An earlier draft fenced this to weeks at or after the one being published, on
    the reasoning that a week before it is finished business. That is false during
    a long week and it was six days from reintroducing the bug it was written to
    fix: `calendar.coming_week` returns "02" from 2026-08-30 onward, so the Friday
    publish targets week 2 while Texas's next game sits in week 1 on 09-05. The
    fence would have skipped it.

    Searching backwards is safe because the ``kickoff >= now`` filter already
    excludes anything played. An earlier week's games are either behind us --
    dropped -- or genuinely still ahead, in which case they *are* the next game
    and the week they are filed under is beside the point.

    Returns the requested week's log with ``None`` when the team has nothing
    ahead of it anywhere -- a bye, or a season that has run out. The document
    still needs a log to name the ratings it was built from, and §6.3's ``as_of``
    is true either way.
    """
    weeks = sorted(
        {entry.week for entry in index_entries(store) if entry.season == season},
        key=week_position,
    )
    if week not in weeks:
        # The requested week has no predictions at all. `_newest_predictions`
        # raises with the message naming `cfb predict`, which is the right
        # failure for a Friday and the one SPEC 8 calls the SLO.
        return _newest_predictions(store, season=season, week=week), None

    here = _newest_predictions(store, season=season, week=week)
    best: tuple[datetime, PredictionLog, PredictedGame] | None = None
    for candidate in weeks:
        log = (
            here
            if candidate == week
            else _newest_predictions(store, season=season, week=candidate)
        )
        for game in log.games:
            if team not in (game.home, game.away) or game.kickoff < now:
                continue
            if best is None or game.kickoff < best[0]:
                best = (game.kickoff, log, game)

    # Every week is read rather than stopping at the first with a fixture. Weeks
    # do not overlap in kickoff order *today*, so stopping early would usually be
    # right -- and "usually right about the calendar" is exactly the assumption
    # that produced the bug above. A season is fifteen small documents.
    return (best[1], best[2]) if best else (here, None)


def _newest_predictions(store: SnapshotStore, *, season: int, week: str) -> PredictionLog:
    generations = prediction_generations(store, season=season, week=week)
    if not generations:
        raise ReplayError(
            f"no predictions are stored for week {week} of season {season} under "
            f"predictions/season={season}/week={week}/, so there is nothing to publish "
            f"to /cfb. Generate them first:\n"
            f"  uv run cfb predict --season {season} --week {int(week) if week.isdigit() else week}"
        )
    return read_predictions(store, generations[-1][1])


def _next_game_document(
    log: PredictionLog,
    fixture: PredictedGame | None,
    state: EloState,
    resolver: Crosswalk,
    *,
    team: str,
    now: datetime,
) -> NextGameDocument:
    rank, fbs_teams = _fbs_rank(state, resolver, team=team)
    same_week = [game for game in log.games if team in (game.home, game.away)]
    if len(same_week) > 1:
        raise ReplayError(
            f"{team} appears in {len(same_week)} games on the week {log.week} slate of "
            f"season {log.season}: {sorted(g.cfbd_game_id for g in same_week)}. One team plays "
            f"once a week, so this is a slate holding the same game twice or two teams "
            f"resolving to one canonical id -- either way `/cfb` would render whichever "
            f"came first"
        )

    with validating(f"next-game document for season {log.season} week {log.week}"):
        return NextGameDocument(
            schema_version=SCHEMA_VERSION,
            generated_at=now,
            season=log.season,
            week=log.week,
            team=resolver.display_name(team),
            game=(
                _published_game(fixture, resolver, team=team, week=log.week)
                if fixture is not None
                else None
            ),
            as_of=AsOf(
                week=state.week,
                elo=state.ratings[team],
                national_rank=rank,
                fbs_teams=fbs_teams,
            ),
        )


def _published_game(
    prediction: PredictedGame, resolver: Crosswalk, *, team: str, week: str
) -> PublishedGame:
    """One prediction row, re-signed from the home team's view to the subject's."""
    at_home = prediction.home == team
    opponent = prediction.away if at_home else prediction.home
    return PublishedGame(
        kickoff=prediction.kickoff,
        week=week,
        opponent=resolver.display_name(opponent),
        home=at_home,
        neutral_site=prediction.neutral_site,
        predicted_margin=(
            prediction.predicted_margin if at_home else -prediction.predicted_margin
        ),
        win_probability=clamp(
            prediction.win_probability if at_home else 1 - prediction.win_probability
        ),
        # Not re-signed. `market_line` is the book's own quote and §6.3 carries it
        # verbatim beside the book's name; converting it here would publish a
        # number no book ever posted under a name that says one did.
        market_line=prediction.market_line,
        line_source=prediction.market_line_source,
    )


def _fbs_rank(state: EloState, resolver: Crosswalk, *, team: str) -> tuple[int, int]:
    """``(rank, fbs_teams)`` for one team among the FBS, by rating, 1-based.

    Standard competition ranking: two teams on the same rating share a rank. Our
    Elo is a float and an exact tie is vanishingly unlikely, but the project's own
    convention is that ratings tie and ranks are the join key (`cfb/CLAUDE.md`),
    so the tie is handled rather than assumed away.
    """
    if team not in state.ratings:
        raise ReplayError(
            f"the Elo state at week {state.week} of season {state.season} has no rating for "
            f"{team!r}, so `/cfb` has no rank to publish for it"
        )
    fbs = {
        canonical: rating
        for canonical, rating in state.ratings.items()
        if resolver.division(canonical) == "FBS"
    }
    if team not in fbs:
        raise ReplayError(
            f"{team!r} is {resolver.division(team)} in the season {resolver.season} "
            f"crosswalk, and `national_rank` is a rank among the FBS"
        )
    ahead = sum(1 for rating in fbs.values() if rating > fbs[team])
    return ahead + 1, len(fbs)


def _backtest(weeks: list[ScoredWeek]) -> Backtest | None:
    """§6.4's retrospective block, or ``None`` when nothing has been backtested."""
    if not weeks:
        return None
    games = [game for scored in weeks for game in scored.games]
    return Backtest(
        through_week=weeks[-1].week,
        # Week 1 is the only week whose forecast is arithmetically the seed. A
        # backtest reaching week 2 is measuring a model that has folded results,
        # and the caveat stops applying.
        measures_the_seed=all(scored.week == "01" for scored in weeks),
        texas=_record([game for game in games if TEXAS in (game.home, game.away)]),
        full_slate=_record(games),
        by_week=[
            WeekPoint(
                week=scored.week,
                games=len(scored.games),
                mae=scored.full_slate.mae,
                sagarin_r=scored.sagarin_r,
                forecast_from=scored.forecast_from,
            )
            for scored in weeks
        ],
    )


def _record(games: list[ScoredGame]) -> Record:
    """§5.3's `Accuracy` in §6.4's page-shaped names."""
    figures = accuracy_of(games)
    return Record(
        games=figures.games,
        mae=figures.mae,
        brier=figures.brier,
        line_games=figures.market_games,
        line_mae=figures.market_mae,
        sagarin_games=figures.sagarin_games,
        sagarin_mae=figures.sagarin_mae,
        ats=AtsSummary(
            record=figures.ats.record,
            wins=figures.ats.wins,
            losses=figures.ats.losses,
            pushes=figures.ats.pushes,
            excluded_no_line=figures.ats.excluded_no_line,
            excluded_no_edge=figures.ats.excluded_no_edge,
        ),
    )


def _seed_disclosure(weeks: list[ScoredWeek]) -> SeedDisclosure:
    """§3.6's disclosure, walked forward through the season.

    **Retirement is a one-way door.** The first week whose correlation falls below
    the threshold retires it, and a later week climbing back above does not
    un-retire it: the claim being retired is "these ratings are still a
    restatement of Sagarin's page", and once that has been false for a week it is
    no longer a thing the page can assert.

    A ``None`` correlation is not a low one and never retires anything -- it is a
    week Sagarin's page covered fewer than two of, and §5.3 is explicit that a
    correlation over one point is not a number.
    """
    retired_week = next(
        (
            scored.week
            for scored in weeks
            if scored.sagarin_r is not None and scored.sagarin_r < SEED_DISCLOSURE_THRESHOLD
        ),
        None,
    )
    measured = [scored.sagarin_r for scored in weeks if scored.sagarin_r is not None]
    return SeedDisclosure(
        active=retired_week is None,
        threshold=SEED_DISCLOSURE_THRESHOLD,
        current_r=measured[-1] if measured else None,
        retired_week=retired_week,
    )

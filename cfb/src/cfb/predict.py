"""The prediction log (SPEC-phase1 4).

One object per week holding every game on that week's slate, written before
kickoff and never replaced. SPEC-phase1 1.1 reversed the PRD's plan to commit
these to git; what survives the reversal is the property, not the mechanism:

    write-once keys      a regenerate is a new object, the first one stays
    IfNoneMatch on PUT   two runs racing cannot clobber each other
    no s3:DeleteObject   the pipeline has no verb that removes one

So a prediction written Thursday at 12:00 cannot become a different prediction on
Sunday at 18:00. Both exist, both are timestamped, and the accuracy page is
computed from whichever one preceded the game.

**The ``model`` block is the point of the document.** §4.2: "a prediction that
cannot be re-derived is an assertion, not a record." It names the exact Sagarin
manifest the HFA came from, the exact page the season was seeded from, and the
exact Elo state object the run started from -- so any number in here can be
recomputed from ``raw/`` months later, by someone who does not trust it.

**Everything the model produces is from the home team's perspective**, including
at neutral sites where "home" is whatever CFBD says (§4.2). One convention,
stated once, so nothing downstream carries sign-flipping logic.

**The one exception is ``market_line``, and it is deliberate.** CFBD signs a
spread the other way -- negative favours the home team -- and the value is stored
exactly as published rather than converted on the way in, so the document records
what the vendor said. ``sources.market_home_margin`` is the single place the two
conventions meet.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cfb.crosswalk import Crosswalk
from cfb.crosswalk import load as load_crosswalk
from cfb.elo import ELO_PER_POINT, SCHEMA_VERSION, Game, K
from cfb.elo import predict as forecast
from cfb.elo.state import previous_state
from cfb.errors import ReplayError, UnmappedTeamError
from cfb.models import SagarinSnapshot, validating
from cfb.sources import (
    HFA_COLUMN,
    hfa_at,
    hfa_manifests,
    market_line_for,
    sagarin_manifests,
    sagarin_snapshot,
    week_lines,
    week_position,
    week_slate,
)
from cfb.storage import SnapshotStore

__all__ = [
    "INDEX_KEY",
    "ModelBlock",
    "PredictedGame",
    "PredictionIndex",
    "PredictionLog",
    "index_entries",
    "predict_week",
    "prediction_generations",
    "prediction_key",
    "predictions_to_score",
    "read_predictions",
    "rebuild_index",
    "write_predictions",
]

#: SPEC-phase1 4.1. The one mutable object in the layout, so the publish step and
#: the site do not have to list a prefix.
INDEX_KEY = "predictions/index.json"

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)

#: Second resolution and no colons, matching every other key this project builds.
_STAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"


class ModelBlock(BaseModel):
    """What produced the numbers, in enough detail to reproduce them (§4.2)."""

    model_config = _STRICT

    name: Literal["elo"]
    elo_per_point: int = Field(gt=0)
    k: int = Field(gt=0)
    #: The value used for every game in this slate, and the manifest it came from.
    #: One per run rather than one per game -- see ``predict_week``.
    hfa: float
    hfa_source: str = Field(min_length=1)
    seeded_from: str = Field(min_length=1)
    elo_state: str = Field(min_length=1)
    #: The Sagarin page the benchmark margins were read off. Not in §4.2's example,
    #: and it belongs: ``sagarin_predictor_margin`` is a number from a source, and a
    #: number whose source the document cannot name is the thing the model block
    #: exists to prevent.
    sagarin_predictions_from: str = Field(min_length=1)
    #: The ``/lines`` capture the market lines came from, or ``None`` when the week
    #: has none stored. Same reasoning as the field above.
    market_lines_from: str | None = None


class PredictedGame(BaseModel):
    """One game's forecast (§4.2). Home perspective throughout."""

    model_config = _STRICT

    cfbd_game_id: int
    kickoff: datetime
    #: Canonical ids, never vendor names. ``cfbd_game_id`` is the one vendor
    #: identifier in the document, and §5.1 explains why it has to be.
    home: str = Field(min_length=1)
    away: str = Field(min_length=1)
    neutral_site: bool
    predicted_margin: float
    #: Unclamped. §3.7's ``[0.001, 0.999]`` is presentational and applied at
    #: publish; the Brier scores of §5.3 are computed on what the model said.
    win_probability: float
    #: Full precision, not the rounded values §4.2's example shows. Rounding here
    #: would make the row unable to reproduce its own margin.
    elo_home: float
    elo_away: float
    #: The market spread **exactly as CFBD published it**, which is the opposite
    #: sign convention to ``predicted_margin``: negative here means the home team
    #: is favoured. Stored verbatim so the document records what the vendor said;
    #: ``sources.market_home_margin`` is the only place the two are reconciled.
    #:
    #: Named ``market_line`` rather than ``closing_line`` because there is no
    #: closing line to have. The response carries ``spread`` (the price at the
    #: moment of capture) and ``spreadOpen``, and nothing else -- a Thursday fetch
    #: cannot know a number that does not exist until kickoff.
    #:
    #: ``None`` when no book priced the game. **Never zero**: zero is a pick'em,
    #: which is a real and very different claim.
    market_line: float | None
    #: Which book ``market_line`` came from, resolved through
    #: ``sources.PROVIDERS``. ``None`` exactly when ``market_line`` is. This is
    #: what makes §6.3's ``line_source`` a fact rather than a guess.
    market_line_source: str | None
    #: Sagarin PREDICTOR, home perspective, benchmark only and an input to
    #: nothing (§1.2). ``None`` when the game is not on the page.
    sagarin_predictor_margin: float | None


class PredictionLog(BaseModel):
    """One week's predictions, as stored (§4.2)."""

    model_config = _STRICT

    schema_version: int = Field(ge=1)
    season: int = Field(ge=1869)
    week: str = Field(min_length=1)
    generated_at: datetime
    model: ModelBlock
    games: list[PredictedGame]


class IndexEntry(BaseModel):
    """One season-week's newest prediction object."""

    model_config = _STRICT

    season: int
    week: str = Field(min_length=1)
    key: str = Field(min_length=1)
    generated_at: datetime


class PredictionIndex(BaseModel):
    """``predictions/index.json`` -- newest generation per week (§4.1).

    A pure projection of a key listing: every field is derivable from the keys
    themselves, so rebuilding it reads no prediction objects at all. That is what
    "derived and rebuildable from a listing" has to mean for it to be safe to
    overwrite -- an index built from the objects could disagree with them, and then
    the site would be serving one and the accuracy page computing from the other.
    """

    model_config = _STRICT

    schema_version: int = Field(ge=1)
    generated_at: datetime
    weeks: list[IndexEntry]


def prediction_key(*, season: int, week: str, generated_at: datetime) -> str:
    """``predictions/season=2026/week=04/2026-09-17T120000Z.json`` (§4.1)."""
    week_position(week)  # rejects a partition value that would open a second prefix
    return (
        f"predictions/season={season}/week={week}/"
        f"{generated_at.strftime(_STAMP_FORMAT)}.json"
    )


def predict_week(
    *,
    store: SnapshotStore,
    season: int,
    week: str,
    now: datetime,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> PredictionLog:
    """Forecast every game on a week's slate. Does not write.

    **One HFA for the whole slate, not one per game.** ``sources.hfa_for`` takes a
    game's own kickoff as the boundary, which is right for scoring a game that has
    already been played. A prediction run is different: it happens once, before any
    of the week's games, and it cannot use a snapshot that lands mid-week without
    claiming knowledge it did not have. So the boundary here is the slate's
    *first* kickoff, which is what §4.2's single ``hfa`` field describes and what
    §3.3 means by "the current snapshot" on a Thursday.

    The two rules agree in the ordinary week -- the Sagarin cron is Tuesday and
    games run Thursday to Saturday, so the newest capture before the first kickoff
    is also the newest before every later one.

    **The Elo state is the one before this week**, exactly as §4.2's example shows
    (a week 04 prediction naming ``elo/.../week=03/``). Nothing here advances the
    ratings: predicting a week must not depend on results from it.
    """
    resolver = crosswalk or load_crosswalk(season, data_dir=crosswalk_dir)
    target = week_position(week, label="--week")

    state = previous_state(store, season=season, week=week)
    if state is None:
        raise ReplayError(
            f"no stored Elo state before week {week} of season {season}, so there are no "
            f"ratings to predict from. Seed the season and bring the state up to date:\n"
            f"  uv run cfb elo seed --season {season}\n"
            f"  uv run cfb elo advance --season {season} --week <each completed week>"
        )

    slate, _ = week_slate(store, season, lambda raw: raw.order == target)
    if not slate:
        fetch_it = (
            f"\n  uv run cfb fetch cfbd --resource games --season {season} "
            f"--week {int(week)}"
            if week.isdigit()
            else ""
        )
        raise ReplayError(
            f"no games on the week {week} slate for season {season} under "
            f"raw/cfbd/season={season}/. An empty slate would write an empty, permanent, "
            f"write-once object rather than a prediction; fetch the week first:{fetch_it}"
        )

    # Sorted by kickoff so the document reads in the order the week happens. Elo
    # is path-dependent but nothing here folds anything, so this is presentational
    # -- unlike the identical sort in `replay`, which is load-bearing.
    slate.sort(key=lambda pair: (pair[0].start_date, pair[0].id))
    first_kickoff = slate[0][0].start_date

    lines, lines_keys = week_lines(store, season, lambda record: record.order == target)

    manifests = hfa_manifests(sagarin_manifests(store, season))
    hfa_manifest = hfa_at(
        manifests,
        before=first_kickoff,
        season=season,
        what=f"the week {week} slate, whose first kickoff is {first_kickoff.isoformat()}",
    )
    hfa = hfa_manifest.hfa[HFA_COLUMN]

    benchmark = _sagarin_margins(sagarin_snapshot(store, hfa_manifest), resolver)
    ratings = state.state.ratings

    games = []
    for raw, _ in slate:
        home = resolver.from_cfbd(raw.home_team)
        away = resolver.from_cfbd(raw.away_team)
        game = Game(
            cfbd_game_id=raw.id,
            home=home,
            away=away,
            neutral_site=raw.neutral_site,
            kickoff=raw.start_date,
        )
        prediction = forecast(ratings, game, hfa=hfa)
        # Joined on the game id, for SPEC-phase1 5.1's reasons: a game moves week
        # for weather and the two sources disagree about who is home at a neutral
        # site, and the id survives both. A game no book priced is simply absent.
        market = market_line_for(lines[raw.id]) if raw.id in lines else None
        games.append(
            PredictedGame(
                cfbd_game_id=raw.id,
                kickoff=raw.start_date,
                home=home,
                away=away,
                neutral_site=raw.neutral_site,
                predicted_margin=prediction.predicted_margin,
                win_probability=prediction.win_probability,
                elo_home=ratings[home],
                elo_away=ratings[away],
                market_line=market[0] if market else None,
                market_line_source=market[1] if market else None,
                sagarin_predictor_margin=_benchmark_for(benchmark, home, away),
            )
        )

    with validating(f"prediction log for season {season} week {week}"):
        return PredictionLog(
            schema_version=SCHEMA_VERSION,
            season=season,
            week=week,
            generated_at=now,
            model=ModelBlock(
                name="elo",
                elo_per_point=ELO_PER_POINT,
                k=K,
                hfa=hfa,
                # The `.meta.json`, not the `.txt`: the HFA was read from the
                # manifest, and naming the page would point at bytes this run
                # never opened for that number.
                hfa_source=_manifest_key(hfa_manifest.snapshot_key),
                seeded_from=state.state.seeded_from,
                elo_state=state.key,
                sagarin_predictions_from=hfa_manifest.snapshot_key,
                market_lines_from=lines_keys[0] if lines_keys else None,
            ),
            games=games,
        )


def write_predictions(store: SnapshotStore, log: PredictionLog) -> str:
    """Store one week's predictions write-once. Returns the key.

    ``put_bytes``, so an existing key raises rather than being replaced (§4.1).
    That is the mechanism the whole integrity story rests on, and it is the same
    one ``raw/`` runs under.
    """
    key = prediction_key(season=log.season, week=log.week, generated_at=log.generated_at)
    store.put_bytes(key, log.model_dump_json(indent=2).encode("utf-8"), "application/json")
    return key


def read_predictions(store: SnapshotStore, key: str) -> PredictionLog:
    """One stored prediction log, validated at the boundary.

    These bytes were written by an earlier run rather than by the code reading
    them, so nothing guarantees they still match the schema this reader was built
    against -- the same reason ``elo.state.load_state`` validates.
    """
    with validating(f"prediction log at {key}"):
        return PredictionLog.model_validate_json(store.get_bytes(key))


def prediction_generations(
    store: SnapshotStore, *, season: int, week: str
) -> list[tuple[datetime, str]]:
    """Every generation stored for one season-week, oldest first.

    Every one of them, not the newest. §4.1 makes these write-once precisely so a
    regenerate leaves both, and something has to be able to see both to choose
    between them -- which is what ``predictions_before`` does.

    Read from the keys, like ``index_entries``: the stamp in the key is what
    ordered the writes, and reading ``generated_at`` out of the objects to sort
    them would let a document's contents disagree with its own name.
    """
    found = []
    for key in store.list_keys(f"predictions/season={season}/week={week}/"):
        parsed = _parse_prediction_key(key)
        if parsed is None:
            continue
        _, parsed_week, generated_at = parsed
        if parsed_week == week:
            found.append((generated_at, key))
    return sorted(found)


def predictions_to_score(
    store: SnapshotStore, *, season: int, week: str
) -> PredictionLog:
    """The generation a scoring run is allowed to grade: the newest one written
    before its own slate had started.

    **Not simply the newest.** A week can hold several generations -- write-once
    means a regenerate adds a key rather than replacing one (§4.1) -- and some of
    them can have been written after the games were played. Grading one of those
    would publish an accuracy figure for a forecast made with the results in
    hand, which is the single overclaim SPEC-phase1 1.1 gives up git to avoid.

    **The boundary comes from each document's own slate, not from the week's
    results.** Both are "the earliest kickoff that week" in the ordinary case,
    and they come apart in exactly the case that matters: a game moved *into* the
    week from an earlier one is already played by the time the week is predicted,
    so a boundary taken from the results would sit in the past and reject a
    perfectly honest Thursday generation. Judging each candidate against the
    slate it actually claimed asks the only question worth asking -- did this
    forecast precede the games it forecast -- and it is the same check
    SPEC-phase1 11 step 1 runs from the bucket side.

    Strictly before, because a generation stamped at the kickoff second knew the
    game had started.
    """
    generations = prediction_generations(store, season=season, week=week)
    if not generations:
        raise ReplayError(
            f"no predictions are stored for week {week} of season {season} under "
            f"predictions/season={season}/week={week}/, so there is nothing to score "
            f"the week against. A week with results and no prediction is a `cfb predict` "
            f"run that never happened, not an empty scoring run"
        )

    rejected = []
    for generated_at, key in reversed(generations):
        candidate = read_predictions(store, key)
        if not candidate.games:
            raise ReplayError(
                f"{key} holds no games. An empty prediction log would score as a week "
                f"in which nothing was forecast and nothing was missed, which is the "
                f"one shape §5.2's join failures cannot see"
            )
        first_kickoff = min(game.kickoff for game in candidate.games)
        if generated_at < first_kickoff:
            return candidate
        rejected.append(f"{key} (slate opened {first_kickoff.isoformat()})")

    listed = "\n  ".join(rejected)
    raise ReplayError(
        f"every generation stored for week {week} of season {season} was written after "
        f"its own slate had started, so none of them can be scored:\n  {listed}\n"
        f"Grading one would publish accuracy for a forecast made with the results in "
        f"hand; run `cfb predict` before kickoff, not after"
    )


def index_entries(store: SnapshotStore) -> list[IndexEntry]:
    """Newest generation per season-week, newest week first (§4.1).

    Reads keys only. Every field comes out of the key itself, which is what makes
    the index safe to overwrite: it can never disagree with the objects it
    describes, because it never looked at them.
    """
    newest: dict[tuple[int, str], str] = {}
    for key in store.list_keys("predictions/"):
        parsed = _parse_prediction_key(key)
        if parsed is None:
            continue
        season, week, _ = parsed
        # Lexicographic ascending from `list_keys`, and the stamps are fixed-width
        # UTC, so the last sighting of a season-week is its newest generation.
        newest[(season, week)] = key

    entries = [
        IndexEntry(
            season=season,
            week=week,
            key=key,
            generated_at=_parse_prediction_key(key)[2],
        )
        for (season, week), key in newest.items()
    ]
    return sorted(entries, key=lambda e: (e.season, week_position(e.week)), reverse=True)


def rebuild_index(store: SnapshotStore, *, now: datetime) -> PredictionIndex:
    """Rebuild ``predictions/index.json`` from a listing and write it.

    The one mutable object (§4.1), and ``put_json`` is deliberate: this is the
    manifest-shaped exception, derived rather than evidence, and rebuildable at any
    time from the keys that are evidence.
    """
    index = PredictionIndex(
        schema_version=SCHEMA_VERSION, generated_at=now, weeks=index_entries(store)
    )
    store.put_json(INDEX_KEY, index.model_dump(mode="json"))
    return index


def _sagarin_margins(
    snapshot: SagarinSnapshot, resolver: Crosswalk
) -> dict[frozenset[str], tuple[str, float]]:
    """Sagarin's PREDICTOR margins, keyed by the unordered pair of canonical ids.

    **Unordered on purpose.** §5.1 records that the two sources can disagree about
    which team is nominally home at a neutral site, and Sagarin's ``@`` marker is
    its own view rather than CFBD's. Keying on the pair and re-signing the margin
    to CFBD's home team is what makes the join survive that; keying on
    ``(home, away)`` would silently miss every neutral-site game, which is
    disproportionately the interesting ones.
    """
    margins: dict[frozenset[str], tuple[str, float]] = {}
    for row in snapshot.predictions:
        home = resolver.from_sagarin(row.home)
        away = resolver.from_sagarin(row.away)
        pair = frozenset({home, away})
        if pair in margins:
            raise UnmappedTeamError(
                f"two prediction rows on the Sagarin page resolve to the same pair "
                f"{sorted(pair)}: rank {row.rank} collides. One matchup cannot carry two "
                f"benchmark margins"
            )
        margins[pair] = (home, row.predicted_margin)
    return margins


def _benchmark_for(
    margins: dict[frozenset[str], tuple[str, float]], home: str, away: str
) -> float | None:
    """Sagarin's margin re-signed to CFBD's home team, or ``None`` if absent.

    ``None`` is ordinary: the page carries about 106 rows against a ~130-game FBS
    slate, so most weeks have games it does not cover. §4.2 says as much, and the
    benchmark being partial is why §5.3 reports it beside the market line rather
    than instead of it.
    """
    found = margins.get(frozenset({home, away}))
    if found is None:
        return None
    sagarin_home, margin = found
    return margin if sagarin_home == home else -margin


def _manifest_key(snapshot_key: str) -> str:
    """The ``.meta.json`` beside a snapshot. Mirrors ``cfb.manifest.manifest_key``."""
    head, _, _ = snapshot_key.rpartition(".")
    return f"{head}.meta.json" if head else snapshot_key


def _parse_prediction_key(key: str) -> tuple[int, str, datetime] | None:
    """``(season, week, generated_at)`` from a prediction key, or ``None``.

    ``None`` rather than a raise: this walks a prefix that holds ``index.json``
    alongside the week objects, and a listing is not the place to fail over a
    stray key someone put there by hand.
    """
    if not key.startswith("predictions/season=") or not key.endswith(".json"):
        return None
    try:
        _, season_part, week_part, stamp = key.split("/")
        season = int(season_part.removeprefix("season="))
        week = week_part.removeprefix("week=")
        generated_at = datetime.strptime(
            stamp.removesuffix(".json"), _STAMP_FORMAT
        ).replace(tzinfo=UTC)
    except ValueError:
        return None
    return season, week, generated_at

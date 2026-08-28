"""Rebuild a season's Elo state from ``raw/`` (SPEC-phase1 3.5).

Elo is a pure function of the seed and the completed games, and both are already
in ``raw/``. This module is that function, spelled out: it reads snapshots, never
the network, and never the stored state it exists to check.

    seed ......... the *first* preseason Sagarin snapshot of the season
    games ........ the newest CFBD /games capture of each week partition
    hfa .......... per game, from the newest Sagarin manifest before its kickoff
    order ........ every completed game by kickoff, across weeks

**Why this exists.** SPEC-phase1 3.5 keeps a state object under
``elo/season=2026/week=04/<ts>.json`` to give the write-up a visible ratings
history and to make a run cheap. A state file that could drift from the snapshots
it was derived from would be a second source of truth; one that can be
regenerated and checked is a cache. ``verify`` is what makes the difference real
rather than asserted, and it is step 5 of SPEC-phase1 11.

**Kickoff order is the whole correctness argument.** Elo is path-dependent: the
rating a team carries into a game is the sum of everything before it, so applying
a week's games in the order ``/games`` happens to return them produces a season
that is wrong in a way nothing downstream can see. ``/games`` is not sorted by
``startDate``, the sort here is global rather than per-week -- a game moved for
weather is filed under the week it was scheduled in and played after games in the
following one (SPEC-phase1 5.1) -- and ``tests/test_replay.py`` fails if the sort
is dropped.

**Nothing here reads ``elo/`` to compute a rating.** ``replay`` takes the store
and produces ratings from ``raw/`` alone; ``verify`` is a separate call that
loads the stored object afterwards and compares. Folding the two together would
make it possible for a stored value to leak into the rebuild, which would leave
the check comparing a number against itself.
"""

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from cfb.collectors.sagarin import decode_page
from cfb.crosswalk import Crosswalk
from cfb.crosswalk import load as load_crosswalk
from cfb.elo import SCHEMA_VERSION, EloState, Game, Ratings, state_prefix, update
from cfb.elo.seed import seed
from cfb.errors import ReplayError, StateMismatchError
from cfb.models import Manifest, SagarinSnapshot, validating
from cfb.parsers.sagarin_predictions import parse_predictions
from cfb.parsers.sagarin_ratings import (
    parse_hfa,
    parse_page_date_stamp,
    parse_page_state,
    parse_ratings,
)
from cfb.storage import SnapshotStore

__all__ = ["HFA_COLUMN", "Replay", "load_state", "newest_state_key", "replay", "verify"]

#: SPEC-phase1 3.3. The margin-oriented column, matching the one SPEC-phase0 4.4
#: says to benchmark forecasts against. Read from the snapshot, never a constant.
HFA_COLUMN = "predictor"

#: How many rating disagreements a mismatch report lists before it stops. Enough
#: to see whether one team drifted or the whole season did; a full 266-line diff
#: in an Actions log is not read by anyone.
_MISMATCH_SAMPLE = 10


class _RawGame(BaseModel):
    """One row of a stored CFBD ``/games`` response.

    ``extra="ignore"``, matching ``CalendarEntry``: these bytes came from a vendor
    that adds fields, and a snapshot in ``raw/`` cannot be re-fetched to match a
    stricter reader. The fields named here are the ones the model uses, and every
    one of them is required -- a ``/games`` row missing ``startDate`` or
    ``neutralSite`` is a shape change worth a red run, not a value to default.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: int
    season: int
    week: int = Field(ge=1)
    season_type: str = Field(min_length=1, alias="seasonType")
    start_date: datetime = Field(alias="startDate")
    neutral_site: bool = Field(alias="neutralSite")
    home_team: str = Field(min_length=1, alias="homeTeam")
    away_team: str = Field(min_length=1, alias="awayTeam")
    home_points: int | None = Field(default=None, alias="homePoints")
    away_points: int | None = Field(default=None, alias="awayPoints")

    @property
    def is_postseason(self) -> bool:
        return self.season_type.lower() == "postseason"

    @property
    def partition(self) -> str:
        """The ``week=`` value this game belongs to (SPEC-phase0 3.2)."""
        return "postseason" if self.is_postseason else f"{self.week:02d}"

    @property
    def order(self) -> tuple[int, int]:
        """Sortable season position, for the ``--through-week`` cut.

        Postseason week numbers restart at 1, so the raw number cannot be compared
        across the two. This makes the season type the leading term.
        """
        return (1 if self.is_postseason else 0, self.week)

    @property
    def is_complete(self) -> bool:
        return self.home_points is not None and self.away_points is not None

    @property
    def is_partially_scored(self) -> bool:
        """One score present and the other missing.

        Not an unplayed game and not a completed one. Whatever produced it, the
        row is wrong, and skipping it as "not played" would drop a real result.
        """
        return not self.is_complete and (
            self.home_points is not None or self.away_points is not None
        )


class _Applied(NamedTuple):
    """One game in the replay, with the provenance the run has to be able to name."""

    game: Game
    kickoff: datetime
    partition: str
    #: The game's position in the season, ``(0|1, week)``. Not the same ordering
    #: as ``kickoff``: a game postponed out of its week is played after games in
    #: the following one, so the last game by kickoff is not the furthest week.
    order: tuple[int, int]
    hfa: float
    #: The ``raw/cfbd/`` key the row was read from, and the ``raw/sagarin/``
    #: manifest the HFA came from. SPEC-phase1 4.2 requires a prediction to name
    #: the exact snapshot behind every number; a replay owes the same.
    games_key: str
    hfa_key: str


@dataclass(frozen=True)
class Replay:
    """A season rebuilt from ``raw/``, and the evidence it was rebuilt from."""

    season: int
    #: The partition the rebuild ends at, and the one whose stored state it is
    #: comparable to. ``through_week`` when the caller named one -- a week with no
    #: completed games is still that week -- otherwise the last applied game's, or
    #: ``"preseason"`` when the season has none yet.
    week: str
    ratings: Ratings
    #: The ``raw/sagarin/`` snapshot key the season was seeded from.
    seeded_from: str
    applied: tuple[_Applied, ...]
    #: Every ``raw/cfbd/`` games key read, newest capture first.
    games_keys: tuple[str, ...]

    @property
    def games_applied(self) -> int:
        return len(self.applied)

    def as_state(self, *, generated_at: datetime) -> EloState:
        """The state document this rebuild would write (SPEC-phase1 3.5).

        ``replay`` does not write it -- SPEC-phase1 8 gives that to the Sunday
        scoring run -- but the document has one definition, and it is this one, so
        a writer and this reader cannot drift into two shapes of the same object.
        """
        return EloState(
            schema_version=SCHEMA_VERSION,
            season=self.season,
            week=self.week,
            generated_at=generated_at,
            seeded_from=self.seeded_from,
            games_applied=self.games_applied,
            ratings=dict(self.ratings),
        )


def replay(
    *,
    store: SnapshotStore,
    season: int,
    through_week: str | None = None,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> Replay:
    """Rebuild ``season``'s Elo ratings from stored snapshots. No network, no state.

    ``through_week`` is a partition value (``"04"``, ``"postseason"``) and cuts the
    season off *inclusively* at that week, so the result is comparable to
    ``elo/season=2026/week=04/``. ``None`` replays everything ``raw/`` holds.

    The crosswalk is injected for the same reason the collectors inject it: the
    committed one is what production uses, and a test that could not substitute
    another could not exercise a mapping gap at all.
    """
    resolver = crosswalk or load_crosswalk(season, data_dir=crosswalk_dir)

    manifests = store.list_manifests(f"raw/sagarin/season={season}/")
    seed_manifest = _seed_manifest(manifests, season)
    ratings = seed(_snapshot(store, seed_manifest), resolver)
    hfa_manifests = _hfa_manifests(manifests)

    games, games_keys = _completed_games(store, season, through_week)

    applied: list[_Applied] = []
    for raw_game, games_key in games:
        hfa_manifest = _hfa_for(hfa_manifests, raw_game, season)
        applied.append(
            _Applied(
                game=Game(
                    cfbd_game_id=raw_game.id,
                    # Canonical ids, never vendor names, and an unmapped one raises
                    # here exactly as it does in the collector (SPEC-phase0 6.4).
                    home=resolver.from_cfbd(raw_game.home_team),
                    away=resolver.from_cfbd(raw_game.away_team),
                    home_points=raw_game.home_points,
                    away_points=raw_game.away_points,
                    neutral_site=raw_game.neutral_site,
                    kickoff=raw_game.start_date,
                ),
                kickoff=raw_game.start_date,
                partition=raw_game.partition,
                order=raw_game.order,
                hfa=hfa_manifest.hfa[HFA_COLUMN],
                games_key=games_key,
                hfa_key=hfa_manifest.snapshot_key,
            )
        )

    # The sort, and the reason this module exists as more than a loop. Elo is
    # path-dependent, `/games` does not return kickoff order, and an out-of-order
    # replay is wrong in a way that looks exactly like a correct one.
    #
    # The tie-break is cosmetic rather than load-bearing: two games kicking off at
    # the same instant cannot share a team, and `update` reads and writes only the
    # two teams named in its game, so simultaneous games commute exactly -- in
    # floating point too, not merely in principle. It is here so that the sequence
    # a run applied is reproducible when someone comes to read it.
    applied.sort(key=lambda entry: (entry.kickoff, entry.game.cfbd_game_id))

    for entry in applied:
        ratings = update(ratings, entry.game, hfa=entry.hfa)

    return Replay(
        season=season,
        # The furthest week reached, not the last game by kickoff -- see
        # `_Applied.order`. A season whose week 1 finished late still ran through
        # week 2, and naming it "01" would compare against the wrong stored state.
        week=through_week
        or (max(applied, key=lambda e: e.order).partition if applied else "preseason"),
        ratings=ratings,
        seeded_from=seed_manifest.snapshot_key,
        applied=tuple(applied),
        games_keys=tuple(games_keys),
    )


def newest_state_key(store: SnapshotStore, *, season: int, week: str) -> str | None:
    """The most recent stored state for one season-week, or ``None`` if there is none.

    ``None`` is an ordinary answer. SPEC-phase1 8 has the Sunday scoring run write
    these and nothing orders a replay after it, so a replay before the first
    scored week finds an empty prefix -- and treating that as a failure would turn
    the season's opening weeks red for the absence of a cache.
    """
    keys = store.list_keys(state_prefix(season=season, week=week))
    # Lexicographic ascending, and the stamps are fixed-width UTC, so the last is
    # the newest. Write-once means the earlier ones stay; the newest is the one a
    # publish would have read.
    return keys[-1] if keys else None


def load_state(store: SnapshotStore, key: str) -> EloState:
    """One stored state document, validated at the boundary."""
    with validating(f"elo state at {key}"):
        return EloState.model_validate_json(store.get_bytes(key))


def verify(rebuilt: Replay, stored: EloState, *, key: str) -> None:
    """Raise ``StateMismatchError`` unless the rebuild reproduces the stored state.

    **Exact equality, not a tolerance.** The replay is the same arithmetic over the
    same inputs, so agreement is bit-for-bit or the inputs differ -- and a
    tolerance would hide precisely the drift this check exists to find. The
    comparison is what SPEC-phase1 11 step 5 means by "byte-identical ratings";
    Python's ``float`` repr round-trips exactly through JSON, so a stored value
    that was ever equal still is.

    A legitimate cause of failure is a corrected re-pull: CFBD backfills scores,
    and a week re-fetched after the state was written is new evidence rather than
    a bug. The state is then stale and should be regenerated -- which is the check
    doing its job, not a false alarm, and the message says so.
    """
    if stored.season != rebuilt.season:
        raise StateMismatchError(
            f"{key} is season {stored.season} and the replay rebuilt {rebuilt.season}"
        )
    if stored.week != rebuilt.week:
        raise StateMismatchError(
            f"{key} is the state through week {stored.week!r} and the replay ran through "
            f"{rebuilt.week!r}. Comparing two different points of the season would report a "
            f"drift that is only a difference of scope"
        )

    problems = list(_rating_differences(rebuilt.ratings, stored.ratings))
    if stored.games_applied != rebuilt.games_applied:
        problems.insert(
            0,
            f"games_applied: stored {stored.games_applied}, replayed "
            f"{rebuilt.games_applied}",
        )
    if not problems:
        return

    shown = problems[:_MISMATCH_SAMPLE]
    more = len(problems) - len(shown)
    raise StateMismatchError(
        f"the replay of season {rebuilt.season} through week {rebuilt.week} does not "
        f"reproduce {key}: {len(problems)} disagreement"
        f"{'' if len(problems) == 1 else 's'}.\n"
        + "\n".join(f"  {line}" for line in shown)
        + (f"\n  ... and {more} more" if more else "")
        + f"\n\nThe replay read {len(rebuilt.games_keys)} /games snapshot"
        f"{'' if len(rebuilt.games_keys) == 1 else 's'} and seeded from "
        f"{rebuilt.seeded_from}. A corrected re-pull of a week after this state was "
        f"written is the benign cause and still makes the state stale: regenerate it. "
        f"Anything else means the stored object and raw/ disagree about what happened."
    )


def _rating_differences(rebuilt: Ratings, stored: Ratings) -> Iterator[str]:
    """Every way two rating sets can disagree, worst first.

    Missing and extra teams come before value drift because they are a different
    failure: a team the replay rates and the state does not means the two ran
    against different crosswalks, and reporting it as "a rating differs" would
    send whoever reads it to the arithmetic instead of to the mapping.
    """
    for canonical in sorted(set(stored) - set(rebuilt)):
        yield f"{canonical}: stored at {stored[canonical]!r}, not replayed at all"
    for canonical in sorted(set(rebuilt) - set(stored)):
        yield f"{canonical}: replayed at {rebuilt[canonical]!r}, absent from the stored state"

    drifted = [
        (abs(rebuilt[canonical] - stored[canonical]), canonical)
        for canonical in sorted(set(rebuilt) & set(stored))
        if rebuilt[canonical] != stored[canonical]
    ]
    for delta, canonical in sorted(drifted, reverse=True):
        yield (
            f"{canonical}: stored {stored[canonical]!r}, replayed {rebuilt[canonical]!r} "
            f"({delta:+.6f})"
        )


def _seed_manifest(manifests: list[Manifest], season: int) -> Manifest:
    """The snapshot the season is seeded from (SPEC-phase1 3.2).

    The **first** preseason capture, not the newest. §3.2 makes seeding a
    once-per-season operation that runs from the first preseason snapshot, so that
    is what a rebuild has to reproduce -- and it is the only choice that stays
    stable, because a second preseason fetch later in August would otherwise
    silently re-seed the whole season.
    """
    preseason = [m for m in manifests if m.page_state == "preseason"]
    if not preseason:
        raise ReplayError(
            f"no parsed preseason Sagarin snapshot for season {season} under "
            f"raw/sagarin/season={season}/. Seeding is preseason-only (SPEC-phase1 3.2) and "
            f"there is nothing to replay from -- a snapshot whose manifest has no page_state "
            f"is a run that fetched and never got through its parse (SPEC-phase0 4.3)"
        )
    # `list_manifests` is newest first, so the earliest capture is the last one.
    return preseason[-1]


def _snapshot(store: SnapshotStore, manifest: Manifest) -> SagarinSnapshot:
    """Re-parse a stored Sagarin page. The bytes are the source of truth, not the manifest.

    The manifest carries counts and an ``hfa``, but not the ratings, so seeding
    has to go back to the page. Doing that rather than trusting a summary is also
    what makes a replay a replay: the parser that runs here is today's, so a
    parser fix reaches the whole season's history without re-fetching anything.
    """
    text, _ = decode_page(store.get_bytes(manifest.snapshot_key))
    with validating(f"replay of {manifest.snapshot_key}"):
        return SagarinSnapshot(
            fetched_at=manifest.fetched_at,
            page_date_stamp=parse_page_date_stamp(text),
            page_state=parse_page_state(text),
            hfa=parse_hfa(text),
            teams=parse_ratings(text),
            predictions=parse_predictions(text),
        )


def _hfa_manifests(manifests: list[Manifest]) -> list[Manifest]:
    """Sagarin manifests carrying an HFA, oldest first.

    Only the manifest is read, never the page: SPEC-phase0 2.2 captures ``hfa``
    per snapshot precisely so nothing downstream has to re-parse or invent one.
    """
    return sorted(
        (m for m in manifests if m.hfa and HFA_COLUMN in m.hfa),
        key=lambda m: (m.fetched_at, m.snapshot_key),
    )


def _hfa_for(manifests: list[Manifest], game: _RawGame, season: int) -> Manifest:
    """The snapshot a game's HFA comes from: the newest one captured before kickoff.

    **A function of the data, not of when a run happened.** A live Sunday scoring
    run reads "the current snapshot" (SPEC-phase1 3.3), which on the SPEC-phase1 8
    schedule is that week's Tuesday capture -- taken before the Saturday games.
    Stating the rule as "newest strictly before kickoff" reproduces exactly that,
    while staying stable as later snapshots arrive. A rule anchored to run time
    could not be replayed at all, because a replay has no run time to anchor to.

    It also gives §3.3's staleness fallback for free: a week whose Tuesday fetch
    failed falls back to the newest capture that did happen, which is last week's,
    because that is simply the newest one before kickoff.

    **Never a default.** If no snapshot precedes the game, this raises rather than
    reaching forward to a later one -- reading a value captured after the game to
    predict it is worse than failing -- and ``cfb/CLAUDE.md`` forbids a constant
    outright.
    """
    for manifest in reversed(manifests):
        if manifest.fetched_at < game.start_date:
            return manifest
    raise ReplayError(
        f"no Sagarin snapshot for season {season} carrying hfa[{HFA_COLUMN!r}] was captured "
        f"before game {game.id} ({game.away_team} at {game.home_team}, "
        f"{game.start_date.isoformat()}). Home-field advantage is read from the source "
        f"snapshot and never hardcoded (cfb/CLAUDE.md), so there is no value to proceed with"
    )


def _completed_games(
    store: SnapshotStore, season: int, through_week: str | None
) -> tuple[list[tuple[_RawGame, str]], list[str]]:
    """Every completed game in ``raw/cfbd/`` for the season, at most once each.

    **The newest capture of a week is that week's slate**, and an older capture of
    the same week is a superseded view rather than extra evidence. Merging both
    would resurrect a game a later pull had dropped -- a cancellation, a schedule
    correction -- which is the one way a replay could apply a game that never
    happened.

    Across weeks the newer capture still wins per game id, because a game moved for
    weather appears under both the week it was scheduled in and the week it was
    played in (SPEC-phase1 5.1).
    """
    cutoff = _cutoff(through_week)
    seen: set[int] = set()
    found: list[tuple[_RawGame, str]] = []
    read_keys: list[str] = []

    for manifest in _newest_games_manifest_per_week(store, season):
        key = manifest.snapshot_key
        read_keys.append(key)
        for raw_game in _rows(store.get_bytes(key), key):
            if raw_game.season != season:
                # A `/games` response filed under this season but describing
                # another is a mis-partitioned capture, and folding it in would
                # apply real games from a season this replay is not rebuilding.
                raise ReplayError(
                    f"{key} is filed under season {season} and holds game {raw_game.id} "
                    f"from season {raw_game.season}"
                )
            if cutoff is not None and raw_game.order > cutoff:
                continue
            if raw_game.is_partially_scored:
                raise ReplayError(
                    f"game {raw_game.id} ({raw_game.away_team} at {raw_game.home_team}) in "
                    f"{key} has one score and not the other: home={raw_game.home_points} "
                    f"away={raw_game.away_points}. That is a malformed row, not an unplayed "
                    f"game, and skipping it would drop a result that was played"
                )
            if not raw_game.is_complete:
                # Unplayed, postponed, or simply not yet scored. Ordinary: the
                # update step applies completed games (SPEC-phase1 3.4), and
                # SPEC-phase1 5.2 makes an unplayed game explicitly not an error.
                continue
            if raw_game.id in seen:
                continue
            seen.add(raw_game.id)
            found.append((raw_game, key))

    # A game with no kickoff never reaches here: `_RawGame.start_date` is
    # required, so `/games` omitting it fails at the boundary with the key and the
    # row named, rather than as an unorderable game three frames later.
    return found, read_keys


def _newest_games_manifest_per_week(store: SnapshotStore, season: int) -> list[Manifest]:
    """One ``/games`` manifest per week partition, newest capture of each.

    Returned newest-capture-first across weeks so that when the same game id
    appears under two partitions, the first sighting -- which
    ``_completed_games`` keeps -- is from the later pull.
    """
    newest: dict[str, Manifest] = {}
    # `list_manifests` is newest first, so the first sighting of a week is its
    # newest capture.
    for manifest in store.list_manifests(f"raw/cfbd/season={season}/"):
        if manifest.resource == "games" and manifest.week not in newest:
            newest[manifest.week] = manifest
    return sorted(newest.values(), key=lambda m: (m.fetched_at, m.snapshot_key), reverse=True)


def _rows(data: bytes, key: str) -> Iterable[_RawGame]:
    try:
        rows = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ReplayError(f"{key} is not valid JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise ReplayError(
            f"{key} holds {type(rows).__name__}, expected the list of games CFBD /games "
            f"returns; an error body stored with a 200 looks exactly like this"
        )
    with validating(f"games in {key}"):
        return [_RawGame.model_validate(row) for row in rows]


def _cutoff(through_week: str | None) -> tuple[int, int] | None:
    """``--through-week`` as a sortable position, or ``None`` for the whole season."""
    if through_week is None:
        return None
    if through_week == "postseason":
        # Everything, and the postseason too. Kept expressible so that the state
        # written after a bowl slate has a week value a replay can target.
        return (1, 99)
    if len(through_week) == 2 and through_week.isdigit() and 1 <= int(through_week) <= 15:
        return (0, int(through_week))
    raise ReplayError(
        f"--through-week {through_week!r} is not a legal partition value: expected "
        f"'01'-'15' zero-padded, or 'postseason'"
    )

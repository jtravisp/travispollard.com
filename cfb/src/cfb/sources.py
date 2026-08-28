"""Reading model inputs out of ``raw/`` (SPEC-phase1 3.3, 3.5, 4).

Three consumers need the same things out of the bucket and must not disagree
about any of them:

    replay    the seed page, every completed game of a season, an HFA per game
    advance   the seed page, one week's completed games, an HFA per game
    predict   a week's whole slate played or not, an HFA per game

**This module exists because that agreement is load-bearest where it is least
visible.** SPEC-phase1 11 step 5 compares a replayed season against an
incrementally accumulated one, and the comparison is only meaningful if both
sides selected the same games, resolved the same names and read the same HFA. Two
copies of "the newest Sagarin manifest before kickoff" is how step 5 starts
failing for a reason that has nothing to do with the model -- or worse, stops
failing when it should.

Nothing here computes a rating. It selects and parses; ``cfb.elo`` does the
arithmetic and ``cfb.replay`` decides what to do with it.
"""

import json
from collections.abc import Callable, Iterable
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cfb.collectors.sagarin import decode_page
from cfb.errors import ReplayError
from cfb.models import Manifest, SagarinSnapshot, validating
from cfb.parsers.sagarin_predictions import parse_predictions
from cfb.parsers.sagarin_ratings import (
    parse_hfa,
    parse_page_date_stamp,
    parse_page_state,
    parse_ratings,
)
from cfb.storage import SnapshotStore

__all__ = [
    "HFA_COLUMN",
    "RawGame",
    "completed_games",
    "hfa_at",
    "hfa_for",
    "hfa_manifests",
    "sagarin_manifests",
    "sagarin_snapshot",
    "seed_manifest",
    "week_position",
    "week_slate",
]

#: SPEC-phase1 3.3. The margin-oriented column, matching the one SPEC-phase0 4.4
#: says to benchmark forecasts against. Read from the snapshot, never a constant.
HFA_COLUMN = "predictor"


class RawGame(BaseModel):
    """One row of a stored CFBD ``/games`` response.

    ``extra="ignore"``, matching ``CalendarEntry``: these bytes came from a vendor
    that adds fields, and a snapshot in ``raw/`` cannot be re-fetched to match a
    stricter reader. The fields named here are the ones the pipeline uses, and
    every one of them is required -- a ``/games`` row missing ``startDate`` or
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
        """Sortable season position.

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


def week_position(week: str | None, *, label: str = "week") -> tuple[int, int] | None:
    """A partition value as a sortable position, or ``None`` for the whole season.

    Serves every caller that cuts on a week: ``replay`` compares game positions
    against it with ``<=``, ``advance`` and ``predict`` with ``==``. One
    validation, so a bad week is rejected the same way everywhere rather than by
    each caller restating the rule.

    ``label`` is what the message calls the thing, because the reader of a red run
    typed a flag rather than a partition and "week" would send them looking for
    the wrong argument.
    """
    if week is None:
        return None
    if week == "postseason":
        # Everything, and the postseason too. Kept expressible so that the state
        # written after a bowl slate has a week value a replay can target.
        return (1, 99)
    if len(week) == 2 and week.isdigit() and 1 <= int(week) <= 15:
        return (0, int(week))
    raise ReplayError(
        f"{label} {week!r} is not a legal partition value: expected '01'-'15' zero-padded, "
        f"or 'postseason'"
    )


# --- Sagarin ------------------------------------------------------------------


def sagarin_manifests(store: SnapshotStore, season: int) -> list[Manifest]:
    """Every Sagarin manifest for a season, newest first."""
    return store.list_manifests(f"raw/sagarin/season={season}/")


def seed_manifest(manifests: list[Manifest], season: int) -> Manifest:
    """The snapshot a season is seeded from (SPEC-phase1 3.2).

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


def sagarin_snapshot(store: SnapshotStore, manifest: Manifest) -> SagarinSnapshot:
    """Re-parse a stored Sagarin page. The bytes are the source of truth, not the manifest.

    The manifest carries counts and an ``hfa`` but not the ratings, so anything
    needing those has to go back to the page. Doing that rather than trusting a
    summary is also what makes a replay a replay: the parser that runs here is
    today's, so a parser fix reaches the whole season's history without
    re-fetching anything.
    """
    text, _ = decode_page(store.get_bytes(manifest.snapshot_key))
    with validating(f"snapshot at {manifest.snapshot_key}"):
        return SagarinSnapshot(
            fetched_at=manifest.fetched_at,
            page_date_stamp=parse_page_date_stamp(text),
            page_state=parse_page_state(text),
            hfa=parse_hfa(text),
            teams=parse_ratings(text),
            predictions=parse_predictions(text),
        )


def hfa_manifests(manifests: list[Manifest]) -> list[Manifest]:
    """Sagarin manifests carrying an HFA, oldest first.

    Only the manifest is read, never the page: SPEC-phase0 2.2 captures ``hfa``
    per snapshot precisely so nothing downstream has to re-parse or invent one.
    """
    return sorted(
        (m for m in manifests if m.hfa and HFA_COLUMN in m.hfa),
        key=lambda m: (m.fetched_at, m.snapshot_key),
    )


def hfa_at(
    manifests: list[Manifest], *, before: datetime, season: int, what: str
) -> Manifest:
    """The newest snapshot carrying an HFA that was captured before ``before``.

    The single implementation of §3.3's rule. Two boundaries use it: a game's own
    kickoff, when scoring a game that has been played (``hfa_for``), and a slate's
    first kickoff, when generating predictions for a week none of whose games have
    started (``cfb.predict``). Both are "the newest snapshot that existed before
    the thing being reasoned about", and having one function say so is what stops
    the two from drifting -- SPEC-phase1 11 step 5 compares two paths that both
    read an HFA, and a second copy of this rule is how that check starts lying.

    **Never a default.** If no snapshot precedes ``before``, this raises rather
    than reaching forward to a later one: reading a value captured after a game to
    predict it is worse than failing, and ``cfb/CLAUDE.md`` forbids a constant
    outright.
    """
    for manifest in reversed(manifests):
        if manifest.fetched_at < before:
            return manifest
    raise ReplayError(
        f"no Sagarin snapshot for season {season} carrying hfa[{HFA_COLUMN!r}] was captured "
        f"before {what}. Home-field advantage is read from the source snapshot and never "
        f"hardcoded (cfb/CLAUDE.md), so there is no value to proceed with"
    )


def hfa_for(manifests: list[Manifest], game: RawGame, season: int) -> Manifest:
    """The snapshot a game's HFA comes from: the newest one captured before kickoff.

    **A function of the data, not of when a run happened.** §3.3 says to read "the
    current Sagarin snapshot", which a replay cannot do -- a replay has no run time
    to be current at. Stating the rule as "newest strictly before kickoff"
    reproduces what a live run sees on the SPEC-phase1 8 schedule, because both
    the Thursday prediction run and the Sunday scoring run sit after that week's
    Tuesday capture and before the following Tuesday's. And it stays stable as
    later snapshots arrive, which is what makes step 5 reproducible at all.

    It also gives §3.3's staleness fallback for free: a week whose Tuesday fetch
    failed falls back to the newest capture that did happen, which is last week's,
    because that is simply the newest one before kickoff.

    **Never a default.** If no snapshot precedes the game, this raises rather than
    reaching forward to a later one -- reading a value captured after a game to
    predict it is worse than failing -- and ``cfb/CLAUDE.md`` forbids a constant
    outright.
    """
    return hfa_at(
        manifests,
        before=game.start_date,
        season=season,
        what=(
            f"game {game.id} ({game.away_team} at {game.home_team}, "
            f"{game.start_date.isoformat()})"
        ),
    )


# --- CFBD games ---------------------------------------------------------------


def week_slate(
    store: SnapshotStore, season: int, keep: Callable[[RawGame], bool]
) -> tuple[list[tuple[RawGame, str]], list[str]]:
    """Every game ``keep`` accepts, played or not, at most once each.

    Each game comes back paired with the ``raw/cfbd/`` key it was read from.
    SPEC-phase1 4.2 requires a prediction to name the exact snapshot behind every
    number, and a per-run list of keys cannot say which row came from which.

    **The newest capture of a week is that week's slate**, and an older capture of
    the same week is a superseded view rather than extra evidence. Merging both
    would resurrect a game a later pull had dropped -- a cancellation, a schedule
    correction -- which is the one way a run could act on a game that no longer
    exists.

    Across weeks the newer capture still wins per game id, because a game moved
    for weather appears under both the week it was scheduled in and the week it
    was played in (SPEC-phase1 5.1).

    Returned in capture order rather than sorted. Callers that care about ordering
    say so -- ``replay`` and ``advance`` sort by kickoff because Elo is
    path-dependent; ``predict`` sorts for readability.
    """
    seen: set[int] = set()
    found: list[tuple[RawGame, str]] = []
    read_keys: list[str] = []

    for manifest in _newest_games_manifest_per_week(store, season):
        key = manifest.snapshot_key
        read_keys.append(key)
        for raw_game in _rows(store.get_bytes(key), key):
            if raw_game.season != season:
                # A `/games` response filed under this season but describing
                # another is a mis-partitioned capture, and folding it in would
                # act on real games from a season this run is not about.
                raise ReplayError(
                    f"{key} is filed under season {season} and holds game {raw_game.id} "
                    f"from season {raw_game.season}"
                )
            if raw_game.is_partially_scored:
                raise ReplayError(
                    f"game {raw_game.id} ({raw_game.away_team} at {raw_game.home_team}) in "
                    f"{key} has one score and not the other: home={raw_game.home_points} "
                    f"away={raw_game.away_points}. That is a malformed row, not an unplayed "
                    f"game, and skipping it would drop a result that was played"
                )
            if not keep(raw_game):
                continue
            if raw_game.id in seen:
                continue
            seen.add(raw_game.id)
            found.append((raw_game, key))

    # A game with no kickoff never reaches here: `RawGame.start_date` is required,
    # so `/games` omitting it fails at the boundary with the key and the row named,
    # rather than as an unorderable game three frames later.
    return found, read_keys


def completed_games(
    store: SnapshotStore, season: int, keep: Callable[[RawGame], bool]
) -> tuple[list[tuple[RawGame, str]], list[str]]:
    """``week_slate`` restricted to games with a result.

    An unplayed, postponed or not-yet-scored game is ordinary rather than an
    error: the update step applies completed games (SPEC-phase1 3.4), and
    SPEC-phase1 5.2 makes an unplayed game explicitly not a failure.
    """
    games, read_keys = week_slate(store, season, keep)
    return [(game, key) for game, key in games if game.is_complete], read_keys


def _newest_games_manifest_per_week(store: SnapshotStore, season: int) -> list[Manifest]:
    """One ``/games`` manifest per week partition, newest capture of each.

    Returned newest-capture-first across weeks so that when the same game id
    appears under two partitions, the first sighting -- which the callers keep --
    is from the later pull.
    """
    newest: dict[str, Manifest] = {}
    # `list_manifests` is newest first, so the first sighting of a week is its
    # newest capture.
    for manifest in store.list_manifests(f"raw/cfbd/season={season}/"):
        if manifest.resource == "games" and manifest.week not in newest:
            newest[manifest.week] = manifest
    return sorted(newest.values(), key=lambda m: (m.fetched_at, m.snapshot_key), reverse=True)


def _rows(data: bytes, key: str) -> Iterable[RawGame]:
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
        return [RawGame.model_validate(row) for row in rows]

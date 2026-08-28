"""Reading and writing the stored Elo state (SPEC-phase1 3.5).

The document itself is ``EloState`` in ``cfb.elo``; this module is everything
that puts one in a bucket and finds it again. It deliberately knows nothing about
``raw/`` -- deriving ratings is ``cfb.replay``'s job, and keeping the two apart is
what stops a stored value from leaking into the rebuild that checks it.

**Write-once, through ``put_bytes``.** SPEC-phase1 3.5 gives state the same
discipline as ``raw/``: timestamped keys, nothing overwritten. ``put_json`` is the
manifest's mutable path (SPEC-phase0 2.2) and using it here would make a state
object silently replaceable, which is exactly the property §3.5 spends its
argument denying. Regenerating writes a new key beside the old one and
``newest_state_key`` picks it up.

**Partitions are ordered, and the order is not lexicographic.** ``preseason``
sorts after ``postseason`` as a string and before every week as a season. Nothing
should be deriving that ordering inline.
"""

import re

from cfb.elo import EloState, state_prefix
from cfb.errors import ReplayError
from cfb.models import validating
from cfb.storage import SnapshotStore

__all__ = [
    "StoredState",
    "load_state",
    "newest_state_key",
    "partition_position",
    "previous_state",
    "season_states",
    "write_state",
]

#: `elo/season=2026/week=04/2026-09-14T120500Z.json`
_KEY = re.compile(r"^elo/season=(?P<season>\d+)/week=(?P<week>[^/]+)/(?P<stamp>[^/]+)\.json$")

#: Where the two named partitions sit relative to the numbered ones. `preseason`
#: is position 0 because it is the state before any game; `postseason` is past
#: every regular week. The gap to 99 is deliberate -- nothing should be inventing
#: a partition between week 15 and the bowls.
_PRESEASON = 0
_POSTSEASON = 99


class StoredState:
    """One state object and the key it came from.

    A bare ``EloState`` cannot say where it was read, and every message this
    module's callers produce -- a mismatch, a missing predecessor -- has to name
    the object rather than describe it.
    """

    __slots__ = ("key", "state")

    def __init__(self, key: str, state: EloState) -> None:
        self.key = key
        self.state = state

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"StoredState({self.key!r}, week={self.state.week!r})"


def partition_position(week: str) -> int:
    """Where a ``week=`` partition sits in a season, as a sortable integer.

    ``preseason`` < ``01`` < ... < ``15`` < ``postseason``. Raises rather than
    ordering an unknown value: a partition this does not recognise would sort
    somewhere plausible and put a state in the wrong place in the chain.
    """
    if week == "preseason":
        return _PRESEASON
    if week == "postseason":
        return _POSTSEASON
    if len(week) == 2 and week.isdigit() and 1 <= int(week) <= 15:
        return int(week)
    raise ReplayError(
        f"week {week!r} is not a legal state partition: expected '01'-'15' zero-padded, "
        f"'preseason' or 'postseason'"
    )


def season_states(store: SnapshotStore, *, season: int) -> list[StoredState]:
    """Every stored state for a season, in season order, oldest generation first.

    One listing rather than one per partition: a season has 17 possible weeks and
    a real bucket would answer 17 requests to find out that 3 of them exist.

    Keys that do not parse are skipped rather than raised on. This lists a prefix
    that only this module writes to, so an unrecognised key is something a person
    put there by hand -- and refusing to read the season's state because of it
    would be a failure caused entirely by a stray object.
    """
    found: list[tuple[int, str, StoredState]] = []
    for key in store.list_keys(f"elo/season={season}/"):
        match = _KEY.match(key)
        if match is None or match["season"] != str(season):
            continue
        try:
            position = partition_position(match["week"])
        except ReplayError:
            continue
        found.append((position, key, StoredState(key, load_state(store, key))))
    return [stored for _, _, stored in sorted(found, key=lambda row: (row[0], row[1]))]


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


def previous_state(store: SnapshotStore, *, season: int, week: str) -> StoredState | None:
    """The newest state at the closest partition *strictly before* ``week``.

    The nearest one, not week-minus-one. A week whose scoring run never happened
    leaves a hole, and the honest answer to "what did the model believe going into
    week 5" is week 3's state if week 4 is missing -- not a failure, and certainly
    not a fresh seed. Whether that hole matters is for the replay check to say:
    the state that results will disagree with a rebuild, because it is missing a
    week of games, and that is precisely the drift SPEC-phase1 3.5 exists to
    surface.
    """
    target = partition_position(week)
    earlier = [
        stored
        for stored in season_states(store, season=season)
        if partition_position(stored.state.week) < target
    ]
    return earlier[-1] if earlier else None


def load_state(store: SnapshotStore, key: str) -> EloState:
    """One stored state document, validated at the boundary.

    These bytes were written by an earlier run rather than by the code reading
    them, so nothing guarantees they still match the schema this reader was built
    against -- the same reason ``storage._load`` validates manifests.
    """
    with validating(f"elo state at {key}"):
        return EloState.model_validate_json(store.get_bytes(key))


def write_state(store: SnapshotStore, state: EloState) -> str:
    """Store one state object write-once. Returns the key.

    ``put_bytes``, so a key that already exists raises rather than being replaced
    (SPEC-phase1 3.5). Keys carry a second-resolution stamp, so the only way to
    collide is to write the same season-week twice within one second, which is a
    run racing itself.

    ``indent=2`` for the same reason ``storage._encode`` uses it: SPEC-phase1 11's
    verification commands are ``aws s3 cp <key> -`` at a terminal, and a state
    object nobody can read at a glance is a cache nobody checks.
    """
    from cfb.elo import state_key

    key = state_key(
        season=state.season, week=state.week, generated_at=state.generated_at
    )
    store.put_bytes(key, state.model_dump_json(indent=2).encode("utf-8"), "application/json")
    return key

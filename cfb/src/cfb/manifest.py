"""Key construction (SPEC-phase0 2.1).

Every object in the bucket is addressed by a string built here, and the key is
the only thing that says what a snapshot is. Nothing under ``raw/`` is ever
deleted or renamed -- there is no migration, only a copy that leaves the mistake
in place beside it -- so a key built wrong is wrong permanently.

```
raw/sagarin/season=2026/week=04/2026-09-16T110302Z.txt
raw/sagarin/season=2026/week=04/2026-09-16T110302Z.meta.json
raw/cfbd/season=2026/week=04/games/2026-09-14T120117Z.json
raw/cfbd/season=2026/week=season/teams/2026-08-20T120004Z.json
```
"""

from datetime import datetime

from cfb.errors import WeekResolutionError

__all__ = ["MANIFEST_SUFFIX", "manifest_key", "snapshot_key"]

MANIFEST_SUFFIX = ".meta.json"

#: Second resolution, and no colons. Colons are legal in an S3 key and make the
#: object miserable to handle from a shell, which SPEC 11's verification
#: commands are.
_STAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"

#: Sagarin has one resource and omits the segment; CFBD requires one (SPEC 2.1).
_EXTENSIONS = {"sagarin": ".txt", "cfbd": ".json"}
_RESOURCE_REQUIRED = {"sagarin": False, "cfbd": True}

_NAMED_WEEKS = frozenset({"preseason", "postseason", "offseason", "season", "unknown"})


def snapshot_key(
    *,
    source: str,
    season: int,
    week: str,
    fetched_at: datetime,
    resource: str | None = None,
) -> str:
    """The key for one captured snapshot.

    ``resource`` is required for CFBD and rejected for Sagarin. Accepting an
    ignored ``resource`` would be a silent coercion; accepting a missing one
    would put a games pull and a lines pull in the same prefix, where the only
    thing telling them apart is a timestamp.
    """
    if source not in _EXTENSIONS:
        raise ValueError(f"unknown source {source!r}: expected one of {sorted(_EXTENSIONS)}")

    required = _RESOURCE_REQUIRED[source]
    if required and not resource:
        raise ValueError(f"source {source!r} requires a resource segment (SPEC 2.1)")
    if not required and resource is not None:
        raise ValueError(
            f"source {source!r} has one resource and omits the segment (SPEC 2.1); "
            f"got resource={resource!r}"
        )

    _check_week(week)
    stamp = fetched_at.strftime(_STAMP_FORMAT)
    middle = f"{resource}/" if resource else ""
    return f"raw/{source}/season={season}/week={week}/{middle}{stamp}{_EXTENSIONS[source]}"


def manifest_key(snapshot_key: str) -> str:
    """The ``.meta.json`` sitting beside ``snapshot_key``.

    Replaces the extension rather than appending to it, and is idempotent: a
    store listing filters on ``.meta.json``, so a doubled suffix would still be
    found and would still be wrong.
    """
    if snapshot_key.endswith(MANIFEST_SUFFIX):
        return snapshot_key
    head, _, tail = snapshot_key.rpartition(".")
    if not head:
        raise ValueError(f"snapshot key {snapshot_key!r} has no extension to replace")
    return head + MANIFEST_SUFFIX


def _check_week(week: str) -> None:
    """``week`` is a partition value, not a free string (SPEC 3.2).

    ``"4"`` is the dangerous one. It opens a second partition for a week that
    already has one, both halves look plausible in a listing, and every later
    prefix query silently reads half the data.
    """
    if week in _NAMED_WEEKS:
        return
    if len(week) == 2 and week.isdigit() and 1 <= int(week) <= 15:
        return
    raise WeekResolutionError(
        f"week {week!r} is not a legal partition value: expected '01'-'15' zero-padded "
        f"or one of {sorted(_NAMED_WEEKS)}"
    )

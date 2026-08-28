"""The Sagarin collector (SPEC-phase0 section 4).

The order of operations in SPEC 4.3 is the design, and the ordering is the part
that matters:

```
1. fetch bytes                       -> FetchError / EncodingError terminate the run
2. put_bytes(snapshot_key)           -> the irreplaceable artifact is now safe
3. put_json(manifest_key)            -> fetch-only fields
4. parse ratings + predictions       -> ParseError / ValidationError
5. resolve every name via crosswalk  -> UnmappedTeamError    [not implemented]
6. put_json(manifest_key)            -> full manifest, parse_ok=true
7. freshness check                   -> StaleSourceError     [not implemented]
```

Steps 5 and 7 are not wired yet: ``crosswalk/`` and the freshness check do not
exist. Everything else runs in this order, and steps 4-7 failing leaves a
snapshot with an honest partial manifest -- detectable, replayable, and never a
reason to discard bytes.

**Week resolution failing does not abort the fetch.** SPEC 3.3 is the one place
this project prefers a messy artifact to a clean failure. A missing calendar
file, a truncated one, or a date past what the calendar describes all take the
same path: the fetch happens, the bytes land under ``week=unknown``,
``week_resolution`` records ``"unknown"`` so a later re-partition sweep can find
the object, and only then does the run raise so the alert fires. An
implementation that resolved first and bailed would satisfy "the run exits
non-zero" perfectly while destroying the thing the run exists to collect.

``fetch`` is injected rather than built here. The CLI passes the pinned-HTTP
fetcher of SPEC 4.1; the tests pass a lambda over a fixture, which is how the
suite exercises this ordering with no network at all.
"""

import hashlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from cfb.calendar import WeekRef, load_calendar, resolve
from cfb.errors import EncodingError, WeekResolutionError
from cfb.manifest import manifest_key, snapshot_key
from cfb.models import Manifest, SagarinSnapshot
from cfb.parsers.sagarin_predictions import parse_predictions
from cfb.parsers.sagarin_ratings import (
    parse_hfa,
    parse_page_date_stamp,
    parse_page_state,
    parse_ratings,
)
from cfb.storage import SnapshotStore

__all__ = ["SOURCE_URL", "decode_page", "fetch_sagarin"]

SOURCE_URL = "http://sagarin.com/sports/cfsend.htm"

#: SPEC 4.2. Deterministic, in this order, with no detection dependency.
CANDIDATES = ("utf-8", "cp1252", "latin-1")

#: The marker check is load-bearing: latin-1 decodes arbitrary bytes without
#: complaint, so decoding successfully is not evidence of decoding correctly.
MARKERS = ("CONFERENCE AVERAGES", "Hawai")

#: Present only on the post-parse write (SPEC 2.2). ``unmapped`` stays out of
#: both writes until the crosswalk of step 5 exists -- an empty list would claim
#: every name resolved, which is a stronger statement than "nothing checked".
_POST_PARSE = ("parse_ok", "page_date_stamp", "page_state", "team_count", "fbs_count", "hfa",
               "predictions_count")
_NEVER_YET = ("unmapped",)


def decode_page(data: bytes) -> tuple[str, str]:
    """``(text, encoding)`` for the first candidate that decodes *and* looks right.

    Raises ``EncodingError`` when none qualifies, rather than handing back
    mojibake that parses into plausible-looking garbage.
    """
    for candidate in CANDIDATES:
        try:
            text = data.decode(candidate)
        except UnicodeDecodeError:
            continue
        if all(marker in text for marker in MARKERS):
            return text, candidate
    raise EncodingError(
        f"no candidate in {CANDIDATES} decoded the page and contained all of {MARKERS}; "
        f"the page shape or its encoding has changed"
    )


def fetch_sagarin(
    *,
    store: SnapshotStore,
    now: datetime,
    fetch: Callable[[], bytes],
    data_dir: Path | None = None,
) -> SagarinSnapshot:
    """Run one Sagarin collection. See the module docstring for the ordering."""
    week_ref = _resolve_week(now, data_dir=data_dir)

    data = fetch()
    text, encoding = decode_page(data)

    key = snapshot_key(
        source="sagarin",
        season=week_ref.season,
        week=week_ref.week,
        fetched_at=now,
    )
    meta_key = manifest_key(key)

    # Step 2 before anything else can fail. Everything above this line is
    # recoverable by re-running; the bytes are not.
    store.put_bytes(key, data, "text/plain")

    manifest = Manifest(
        schema_version=1,
        source="sagarin",
        resource="ratings",
        source_url=SOURCE_URL,
        # Any non-2xx is a FetchError inside the fetcher (SPEC 4.1), so bytes
        # reaching this function are by construction a 200.
        http_status=200,
        sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data),
        encoding=encoding,
        fetched_at=now,
        season=week_ref.season,
        week=week_ref.week,
        week_resolution=week_ref.how,
        snapshot_key=key,
    )
    store.put_json(meta_key, _dump(manifest, fetch_only=True))

    snapshot = SagarinSnapshot(
        fetched_at=now,
        page_date_stamp=parse_page_date_stamp(text),
        page_state=parse_page_state(text),
        hfa=parse_hfa(text),
        teams=parse_ratings(text),
        predictions=parse_predictions(text),
    )

    store.put_json(
        meta_key,
        _dump(
            manifest.model_copy(
                update={
                    "parse_ok": True,
                    "page_date_stamp": snapshot.page_date_stamp,
                    "page_state": snapshot.page_state,
                    "hfa": snapshot.hfa,
                    "team_count": len(snapshot.teams),
                    "fbs_count": sum(1 for team in snapshot.teams if team.division == "A"),
                    "predictions_count": len(snapshot.predictions),
                }
            ),
            fetch_only=False,
        ),
    )

    if week_ref.how == "unknown":
        # The write is done, the manifest says so, and the object is findable by
        # the re-partition sweep. Now the run goes red (SPEC 3.3).
        raise WeekResolutionError(
            f"season/week could not be resolved for {now.isoformat()}; the snapshot was written "
            f"to {key} with week_resolution='unknown' and is safe, but the calendar needs fixing "
            f"and this object re-partitioned"
        )

    return snapshot


def _resolve_week(now: datetime, *, data_dir: Path | None) -> WeekRef:
    """Resolve, degrading to ``unknown`` rather than propagating.

    ``load_calendar`` raises on an unreadable file and ``resolve`` returns
    ``how="unknown"`` on an unplaceable date (SPEC 3.1). Both end up in the same
    place here, because SPEC 3.3 gives all three of its causes one behaviour.
    """
    season = _season_of(now)
    try:
        calendar = load_calendar(season, data_dir=data_dir)
    except WeekResolutionError:
        return WeekRef(season=season, week="unknown", how="unknown")
    return resolve(now, calendar=calendar)


def _season_of(now: datetime) -> int:
    """Which season a moment belongs to, without a calendar to ask.

    Needed before the calendar is loaded, because the season names the file, and
    needed again when there is no calendar to load. A January date belongs to the
    season that started the previous August. This is a guess, and it is only ever
    the recorded season on a snapshot already flagged ``week=unknown``.
    """
    return now.year if now.month >= 7 else now.year - 1


def _dump(manifest: Manifest, *, fetch_only: bool) -> dict:
    exclude = set(_NEVER_YET) | (set(_POST_PARSE) if fetch_only else set())
    return manifest.model_dump(mode="json", exclude=exclude)

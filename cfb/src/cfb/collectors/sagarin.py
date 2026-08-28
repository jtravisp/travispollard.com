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

``fetch`` defaults to ``fetch_page``, the pinned-HTTP fetcher of SPEC 4.1, and
stays injectable. Production gets a real fetcher without the CLI having to
assemble one; the tests keep passing a lambda over a fixture, which is how the
suite exercises this ordering with no network at all.
"""

import hashlib
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx

from cfb.calendar import WeekRef, in_season, load_calendar, resolve
from cfb.errors import EncodingError, FetchError, StaleSourceError, WeekResolutionError
from cfb.logging import (
    EVENT_FRESHNESS,
    REASON_NO_PAGE_DATE_STAMP,
    REASON_NO_PRIOR_MANIFEST,
    REASON_NOT_IN_SEASON,
    RESULT_OK,
    RESULT_SKIP,
    log,
)
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

__all__ = ["SOURCE_URL", "check_freshness", "decode_page", "fetch_page", "fetch_sagarin"]

SOURCE_URL = "http://sagarin.com/sports/cfsend.htm"

#: SPEC 4.1. Connect and read both 30s; write and pool follow rather than being
#: left at the httpx default, because a stall in either is the same outage.
TIMEOUT = httpx.Timeout(30.0)

#: SPEC 4.1, one rung slept before each retry. The spec's prose says "three
#: attempts" beside a three-rung ladder, which cannot both hold -- three attempts
#: leave room for two backoffs and the 30s rung is never reached. The ladder is
#: taken as authoritative: three retries after the initial request, four requests
#: at worst, and every rung used. See tests/test_sagarin_fetch.py.
BACKOFF = (2, 8, 30)

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


def fetch_page(
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Fetch the Sagarin page (SPEC 4.1). Raw bytes, or ``FetchError``.

    **The scheme is pinned and a redirect is never followed.** sagarin.com 302s
    HTTPS back to HTTP, so a client that upgrades ping-pongs until it exhausts
    its redirect limit -- and the failure it eventually reports names the limit,
    not the cause. ``follow_redirects=False`` turns that into one request and one
    honest error.

    Retries cover the failures a second attempt can actually fix: a timeout, a
    connection that never established, a 5xx. A 4xx is a decision the server has
    already made, and repeating the request earns the same answer three more
    times while delaying the red run by forty seconds.

    ``transport`` and ``sleep`` exist for the tests. The client is built here
    rather than passed in, because the redirect policy and the timeout are this
    function's decisions -- a caller that supplied the client would own them, and
    the tests would be asserting against their own setup.
    """
    last: Exception | None = None

    with httpx.Client(transport=transport, follow_redirects=False, timeout=TIMEOUT) as client:
        for attempt in range(len(BACKOFF) + 1):
            try:
                response = client.get(SOURCE_URL)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                # Exactly what SPEC 4.1 names as retryable. TimeoutException
                # covers connect and read; NetworkError covers a connection that
                # never established or died mid-body.
                last = exc
            except httpx.TransportError as exc:
                # Everything else at the transport layer -- a malformed response,
                # an unsupported scheme, a broken proxy. Another attempt does not
                # fix any of them, but it still has to leave as a FetchError:
                # SPEC 9 maps CfbError to exit 1, and a bare httpx exception
                # escaping to the CLI is a traceback instead of a red run.
                raise FetchError(f"{SOURCE_URL}: {type(exc).__name__}: {exc}") from exc
            else:
                # Any 3xx, not just the ones carrying a Location. httpx's
                # is_redirect is False without that header, and a redirect the
                # client cannot even follow is not a reason to ask three more
                # times.
                if 300 <= response.status_code < 400:
                    raise FetchError(
                        f"{SOURCE_URL} redirected {response.status_code} to "
                        f"{response.headers.get('location')!r}; the scheme is pinned and "
                        f"redirects are not followed (SPEC 4.1) -- sagarin.com 302s HTTPS "
                        f"back to HTTP and a client that upgrades loops forever"
                    )
                if response.is_success:
                    return response.content
                if response.is_client_error:
                    raise FetchError(
                        f"{SOURCE_URL} returned {response.status_code}; 4xx is not retried "
                        f"(SPEC 4.1): {_excerpt(response)}"
                    )
                last = FetchError(
                    f"{SOURCE_URL} returned {response.status_code}: {_excerpt(response)}"
                )

            if attempt < len(BACKOFF):
                sleep(BACKOFF[attempt])

    raise FetchError(
        f"{SOURCE_URL} failed {len(BACKOFF) + 1} times over the {'/'.join(map(str, BACKOFF))}s "
        f"ladder; no snapshot written, this run is red (SPEC 4.1). Last failure: {last}"
    ) from last


def _excerpt(response: httpx.Response, limit: int = 200) -> str:
    """The start of a failed response body.

    Logged on every non-2xx because the body is the only thing that makes a
    failure decidable later, and a run that discarded it leaves nothing to
    decide from. Truncated: this ends up in a workflow log, not a snapshot.
    """
    body = response.content[:limit]
    return f"{body!r}{'...' if len(response.content) > limit else ''}"


def fetch_sagarin(
    *,
    store: SnapshotStore,
    now: datetime,
    fetch: Callable[[], bytes] = fetch_page,
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


def check_freshness(
    *,
    store: SnapshotStore,
    source: str,
    now: datetime,
    data_dir: Path | None = None,
) -> None:
    """Raise ``StaleSourceError`` if the page's internal stamp has not advanced (SPEC 4.6).

    **Every skip logs why.** Three of the four paths through this function are a
    pass, and a pass here is byte-identical to a healthy run from outside the
    process: same exit code, same green workflow, nothing written. The log line is
    the only thing that distinguishes "there was nothing to compare" from "the
    comparison ran and the source is alive", so it is not optional output.

    Previous state comes from the manifests in the store and nowhere else. No
    state file, no SSM parameter, no counter -- anything of that sort can drift out
    of sync with the snapshots it claims to describe, and then the check is
    reporting on its own bookkeeping rather than on the source.

    ``data_dir`` is the one addition to SPEC 4.6's signature, matching
    ``fetch_sagarin``: the ``in_season`` gate needs a calendar, and a function that
    loads its own from a fixed path cannot be tested without one on disk. A
    calendar that will not load raises rather than being skipped past -- not
    knowing whether it is February is not a reason to fall through to the
    comparison, and it is certainly not a reason to stay quiet.
    """
    calendar = load_calendar(_season_of(now), data_dir=data_dir)
    if not in_season(now, calendar=calendar):
        # Sagarin does not update from roughly February through August. A check
        # that ran anyway would raise every week of it, and alerting that cries
        # wolf for six months is alerting nobody reads in September.
        log(EVENT_FRESHNESS, source=source, result=RESULT_SKIP, reason=REASON_NOT_IN_SEASON)
        return

    manifests = store.list_manifests(f"raw/{source}/")
    current = manifests[0] if manifests else None

    # Strictly earlier *date*, and never the current snapshot itself. Same-day
    # manifests are ignored so a manual re-run compares against last Tuesday
    # exactly as the scheduled run did -- otherwise re-running an hour later finds
    # its own stamp unchanged and turns every re-run red.
    prior = next((m for m in manifests[1:] if m.fetched_at.date() < now.date()), None)

    if current is None or prior is None:
        # An empty store lands here too: SPEC 8 makes `fetch` and `check-freshness`
        # separate commands with nothing ordering them, so a check can run before
        # anything has ever been fetched. Passing is the only answer that does not
        # turn an empty bucket into a permanently red workflow.
        log(EVENT_FRESHNESS, source=source, result=RESULT_SKIP, reason=REASON_NO_PRIOR_MANIFEST)
        return

    if current.page_date_stamp is None or prior.page_date_stamp is None:
        # The preseason page carries no stamp at all (SPEC 4.7). Either side being
        # null means there is nothing to compare, not that something is wrong.
        log(
            EVENT_FRESHNESS,
            source=source,
            result=RESULT_SKIP,
            reason=REASON_NO_PAGE_DATE_STAMP,
            key=current.snapshot_key,
        )
        return

    days = (now.date() - prior.fetched_at.date()).days

    if current.page_date_stamp > prior.page_date_stamp:
        log(
            EVENT_FRESHNESS,
            source=source,
            result=RESULT_OK,
            stamp=current.page_date_stamp.isoformat(),
            prior_stamp=prior.page_date_stamp.isoformat(),
            days=days,
        )
        return

    raise StaleSourceError(
        f"{source} page_date_stamp has not advanced: prior stamp "
        f"{prior.page_date_stamp.isoformat()} ({prior.snapshot_key}), current stamp "
        f"{current.page_date_stamp.isoformat()} ({current.snapshot_key}), {days} days "
        f"elapsed. The fetch is working and the source is not updating."
    )


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

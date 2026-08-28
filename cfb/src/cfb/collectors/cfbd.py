"""The CFBD collector: budgeted client and incremental sync (SPEC-phase0 section 5).

Two pieces with one seam between them. ``CfbdClient`` owns the budget and the
retries; ``fetch_cfbd`` owns the snapshot. SPEC 5.1 requires the cap to be
enforced *in the client*, and that split is what makes the requirement true
rather than aspirational: no code path reaches CFBD except through ``get``, and
``get`` counts before it sends.

**Why not the vendor's Python package.** It makes its own requests, which makes
it a budget guard with a hole in it. The bearer contract is one header (see the
``cfbd-api`` skill); the package is not buying anything worth that.

**The budget is the only defence, and the number it defends is not vendor-backed.**
CFBD's current documentation declines to state limits. The 1,000 calls/month
figure in `cfb/CLAUDE.md` is a number this repo copied down once, and SPEC 5.1 is
explicit that it must never become a runtime check. What bounds the month is
``CALL_BUDGET_PER_RUN`` x runs, which holds whatever the tier turns out to be --
for exactly as long as the cap is counted honestly. That is why every request
goes through one place and why the counter lives on the instance: a cross-run
counter would race, and would be wrong after any crash.

**Two ladders.** A 429 is the server asking for room; a 5xx is the server
failing. SPEC 5.3 waits longer for the first, and both stop at three requests --
the initial one plus two retries. Retries are requests and every one of them
spends budget, so a longer ladder would make a bad Sunday cost more of the run
than the data does.

``fetch`` is injected rather than built here, the same seam ``fetch_sagarin``
uses. The credential path of SPEC 5.5 -- read the key from SSM, build the bearer
header -- is not wired yet, so there is no production fetcher in this module
today; the tests pass a callable over synthetic responses, which is how the suite
honours ``cfb/CLAUDE.md``'s absolute ban on calling CFBD from a test.
"""

import hashlib
import time
from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote

import httpx

from cfb.errors import CallBudgetExceeded, FetchError
from cfb.logging import EVENT_CFBD_CALL, EVENT_HTTP_ERROR, log
from cfb.manifest import manifest_key, snapshot_key
from cfb.models import Manifest
from cfb.storage import SnapshotStore

__all__ = [
    "BACKOFF",
    "BACKOFF_429",
    "BASE_URL",
    "CALL_BUDGET_PER_RUN",
    "CfbdClient",
    "fetch_cfbd",
]

#: HTTPS, and that is not a contradiction with Sagarin's pinned HTTP. That pin is
#: about a site that 302s HTTPS down to HTTP; CFBD is a normal JSON API over TLS
#: and a bearer token must never go out over plaintext.
BASE_URL = "https://api.collegefootballdata.com"

#: SPEC 5.1. The 26th request in a run raises.
CALL_BUDGET_PER_RUN = 25

#: SPEC 4.1, which SPEC 5.3 defers to for 5xx and transport failures.
BACKOFF = (2, 8)

#: SPEC 5.3, for 429 only. Longer than the 5xx ladder on purpose.
BACKOFF_429 = (5, 20)

#: SPEC 5.2. The four calls this project makes, and whether each is week-scoped.
_RESOURCES = {
    "games": ("/games", True),
    "lines": ("/lines", True),
    "teams": ("/teams/fbs", False),
    "calendar": ("/calendar", False),
}


class CfbdClient:
    """A CFBD client that counts its own requests and refuses to exceed them.

    ``budget`` is per instance and per run. Nothing here is module-level state:
    SPEC 5.1 asks for a stateless cap precisely so there is no shared counter to
    race, and none to be left wrong by a crashed run.
    """

    def __init__(
        self,
        *,
        fetch: Callable[[str, dict], httpx.Response],
        sleep: Callable[[float], None] = time.sleep,
        budget: int = CALL_BUDGET_PER_RUN,
    ) -> None:
        self._fetch = fetch
        self._sleep = sleep
        self._budget = budget
        self._calls = 0

    @property
    def calls_made(self) -> int:
        """Requests issued by this client, retries included."""
        return self._calls

    def get(self, path: str, **params) -> bytes:
        """One CFBD resource as raw JSON bytes, or an error.

        The budget is checked **before** each request, retries included. Checking
        after would count correctly and still have spent the quota the count
        exists to protect, which is the failure mode with no symptom: the run
        raises either way, and only the vendor's usage page ever knows.
        """
        attempt = 0
        last: Exception | None = None

        while True:
            if self._calls >= self._budget:
                raise CallBudgetExceeded(
                    f"per-run call budget of {self._budget} is spent; refusing to request "
                    f"{path} (SPEC 5.1). Retries count, so a run that hits this has usually "
                    f"been retrying rather than fetching"
                )

            self._calls += 1
            log(
                EVENT_CFBD_CALL,
                path=path,
                call=self._calls,
                budget=self._budget,
            )

            wait: float | None = None
            try:
                response = self._fetch(path, params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                # A connection that never established is the 5xx case by another
                # name: nothing about the request was wrong, so it is worth
                # asking again.
                ladder, last = BACKOFF, exc
            except httpx.TransportError as exc:
                # A malformed response, an unsupported scheme, a broken proxy.
                # Another request does not fix any of them, and it still has to
                # leave as a FetchError so SPEC 9 maps it to exit 1 rather than a
                # traceback.
                raise FetchError(f"{path}: {type(exc).__name__}: {exc}") from exc
            else:
                if response.is_success:
                    return response.content

                # SPEC 5.3: without exception. The vendor has stopped naming the
                # status that means "over quota", so the body of a real one is
                # the only thing that will ever settle what it looks like.
                log(
                    EVENT_HTTP_ERROR,
                    path=path,
                    status=response.status_code,
                    call=self._calls,
                    body=_excerpt(response),
                )

                ladder = _ladder_for(response.status_code)
                if ladder is None:
                    raise FetchError(
                        f"{path} returned {response.status_code}, which is not retryable "
                        f"(SPEC 5.3): {_excerpt(response)}"
                    )
                if ladder is BACKOFF_429:
                    wait = _retry_after(response)
                last = FetchError(f"{path} returned {response.status_code}")

            if attempt >= len(ladder):
                raise FetchError(
                    f"{path} failed {attempt + 1} times over the "
                    f"{'/'.join(map(str, ladder))}s ladder; no snapshot written, this run "
                    f"is red (SPEC 5.3). Last failure: {last}"
                ) from last

            self._sleep(ladder[attempt] if wait is None else wait)
            attempt += 1


def fetch_cfbd(
    *,
    store: SnapshotStore,
    client: CfbdClient,
    resource: str,
    season: int,
    week: str,
    now: datetime,
) -> bytes:
    """Pull one CFBD resource and store it verbatim.

    Same ordering as SPEC 4.3: the bytes land before anything parses them, and a
    failed request writes nothing at all. ``raw/`` is write-once, so a truncated
    object at the right key is permanent -- there is no second chance to store
    this pull, and an empty one would look like a real capture forever.
    """
    path, params = _request_for(resource, season, week)

    # Anything that goes wrong in here raises, which is why no key is built above
    # this line: a snapshot key implies a snapshot.
    data = client.get(path, **params)

    key = snapshot_key(
        source="cfbd",
        season=season,
        week=week,
        fetched_at=now,
        resource=resource,
    )
    store.put_bytes(key, data, "application/json")

    store.put_json(
        manifest_key(key),
        Manifest(
            schema_version=1,
            source="cfbd",
            resource=resource,
            source_url=f"{BASE_URL}{path}",
            # Every non-2xx is a FetchError inside the client, so bytes reaching
            # here are by construction a 200. Same inference as SPEC 2.2 records
            # for Sagarin, and the same caveat: this is control flow, not a
            # status line anyone read.
            http_status=200,
            sha256=hashlib.sha256(data).hexdigest(),
            bytes=len(data),
            # SPEC 2.2: null for CFBD JSON. There is no encoding sniff here --
            # JSON is utf-8 by specification and a guess would only add a way to
            # be wrong.
            encoding=None,
            fetched_at=now,
            season=season,
            week=week,
            # The week came from the CLI, not from resolving a date (SPEC 5.2:
            # "N is the week that just completed"). "calendar" is the closer of
            # the two values SPEC 2.2 allows: it is known, not guessed.
            week_resolution="calendar",
            snapshot_key=key,
        ).model_dump(mode="json", exclude={"unmapped"}),
    )

    return data


def _request_for(resource: str, season: int, week: str) -> tuple[str, dict]:
    """The path and query for one resource (SPEC 5.2)."""
    try:
        path, week_scoped = _RESOURCES[resource]
    except KeyError:
        raise ValueError(
            f"unknown resource {resource!r}: expected one of {sorted(_RESOURCES)}"
        ) from None

    params: dict[str, int] = {"year": season}
    if week_scoped:
        if not week.isdigit():
            raise ValueError(
                f"resource {resource!r} is week-scoped and needs a numbered week, "
                f"got {week!r} (SPEC 3.2)"
            )
        params["week"] = int(week)
    return path, params


def _ladder_for(status: int) -> tuple[int, ...] | None:
    """The backoff for a status, or ``None`` when it must not be retried.

    A whitelist, and deliberately so. SPEC 5.3 says an unrecognised quota or
    entitlement response is non-retryable -- retrying a request the account is not
    entitled to make burns budget to earn the same answer three times. Since the
    vendor no longer documents which status that is, the safe default for an
    unknown code is to stop.
    """
    if status == 429:
        return BACKOFF_429
    if status >= 500:
        return BACKOFF
    return None


def _retry_after(response: httpx.Response) -> float | None:
    """``Retry-After`` in seconds, or ``None`` to fall back to the ladder.

    The server naming a wait is better information than a fixed ladder. Only the
    delta-seconds form is read: the HTTP-date form is legal and this client does
    not parse it, and falling back is a more honest answer than a wrong one. A
    zero or negative value falls back too -- it is not a reason to hammer.
    """
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    return seconds if seconds > 0 else None


def _excerpt(response: httpx.Response, limit: int = 200) -> str:
    """The start of a response body, as one whitespace-free log field.

    Percent-encoded rather than quoted. A vendor body carries spaces and newlines,
    and a log line is one line of ``key=value``: an unencoded body silently turns
    one field into several, and the parser reading the line back gets keys it has
    never heard of. Encoding is lossless, so the evidence SPEC 5.3 asks for
    survives -- which matters, because the response that means "over quota" is one
    nobody here has seen yet.
    """
    body = response.content[:limit].decode("utf-8", errors="replace")
    return quote(body) + ("..." if len(response.content) > limit else "")

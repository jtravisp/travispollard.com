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
uses. ``http_fetch`` is what production injects; the tests pass a callable over
synthetic responses, which is how the suite honours ``cfb/CLAUDE.md``'s absolute
ban on calling CFBD from a test.
"""

import hashlib
import re
import time
from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote

import httpx

from cfb.errors import CallBudgetExceeded, FetchError, optional_import
from cfb.logging import EVENT_CFBD_CALL, EVENT_HTTP_ERROR, log
from cfb.manifest import manifest_key, snapshot_key
from cfb.models import Manifest, validating
from cfb.storage import SnapshotStore

__all__ = [
    "BACKOFF",
    "BACKOFF_429",
    "BASE_URL",
    "CALL_BUDGET_PER_RUN",
    "SSM_PARAMETER",
    "CfbdClient",
    "fetch_cfbd",
    "http_fetch",
    "ssm_secret",
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

#: SPEC 5.5. Not configurable: the publisher IAM policy is scoped to the prefix
#: this sits under, so a different path is a permission failure, not an option.
SSM_PARAMETER = "/travispollard/cfb/cfbd_api_key"

#: SPEC 2: passed explicitly, never inherited from ambient env.
REGION = "us-east-1"

#: Matching SPEC 4.1's fetcher. A stalled connection is a stalled run either way.
TIMEOUT = httpx.Timeout(30.0)

#: SPEC 5.2. The four calls this project makes, and whether each is week-scoped.
_RESOURCES = {
    "games": ("/games", True),
    "lines": ("/lines", True),
    # `/teams`, not `/teams/fbs`. Sagarin rates 266 teams and 128 of them are
    # FCS; `/games` returns those opponents by CFBD name, so the crosswalk needs
    # both divisions or the first FBS-vs-FCS game fails to join (SPEC 6.5).
    "teams": ("/teams", False),
    "calendar": ("/calendar", False),
}


def ssm_secret(parameter: str = SSM_PARAMETER, *, region: str = REGION) -> str:
    """Read the CFBD key from SSM (SPEC 5.5). **The one thing here no test covers.**

    Everything else on this path is exercised offline through an injected
    ``get_secret``. This function is not, and cannot be: whether the parameter
    exists, is a SecureString, is readable by the publisher role and comes back
    decrypted are facts about an AWS account rather than about this code. The
    seam exists so that the untested part is exactly one function whose whole body
    is the call -- read it as unverified until a real run says otherwise.

    ``WithDecryption`` is the point of a SecureString. Without it the call
    succeeds and returns ciphertext, which then goes out as a bearer token and
    comes back 401 -- a failure that looks like a bad key and is not.

    boto3 is imported here, not at module scope, so the offline suite imports this
    module without the optional dependency (``uv sync --extra s3``).

    The import is wrapped for the same reason the store's is. This one fails later
    and worse: not when the CLI resolves a store, but on the *first CFBD request
    of a run*, after the calendar loaded and the week resolved -- so an unwrapped
    ``ModuleNotFoundError`` here looks like a failure of the fetch rather than of
    the environment.
    """
    with optional_import("boto3", extra="s3", needed_for="reading the CFBD key from SSM"):
        import boto3

    client = boto3.client("ssm", region_name=region)
    return client.get_parameter(Name=parameter, WithDecryption=True)["Parameter"]["Value"]


def http_fetch(
    *,
    get_secret: Callable[[], str] = ssm_secret,
    transport: httpx.BaseTransport | None = None,
) -> Callable[[str, dict], httpx.Response]:
    """The production ``fetch`` callable for ``CfbdClient``.

    **HTTPS, and the scheme is checked before every send.** Sagarin is pinned to
    plain HTTP because that site 302s HTTPS down to HTTP and a client that
    upgrades loops forever; carrying that rule here would put a bearer token on
    the wire in the clear. So this pins the other way and refuses to send at all
    if the base URL is ever not https. A refused request costs a Sunday that CFBD
    history can backfill. A transmitted key costs a rotation.

    Redirects are not followed, for the same reason: a 3xx could hand the
    ``Authorization`` header to another host. The response comes back to
    ``CfbdClient``, which does not have 3xx in its retryable whitelist.

    The secret is read once, on the first request, and reused for the rest of the
    run -- a run makes at most ``CALL_BUDGET_PER_RUN`` requests and needs one
    credential. Reading it at construction instead would mean the CLI touched AWS
    while parsing arguments, so ``cfb --help`` would need credentials.
    """
    cached: list[str] = []

    def fetch(path: str, params: dict) -> httpx.Response:
        if not BASE_URL.startswith("https://"):
            raise FetchError(
                f"refusing to send the CFBD bearer token to {BASE_URL!r}: SPEC 5.5 requires "
                f"https. Sagarin's http pin (SPEC 4.1) is about a site that downgrades "
                f"redirects and must not be carried across to an authenticated API"
            )

        if not cached:
            # Stripped: a SecureString set from a file keeps its trailing newline,
            # which makes a malformed header and a 401 that reads as a bad key.
            key = get_secret().strip()
            if not key:
                raise FetchError(
                    f"the CFBD key at {SSM_PARAMETER} is empty; sending 'Bearer ' would "
                    f"spend a request to earn a 401 indistinguishable from a revoked key"
                )
            cached.append(key)

        with httpx.Client(
            transport=transport, follow_redirects=False, timeout=TIMEOUT
        ) as client:
            return client.get(
                f"{BASE_URL}{path}",
                params=params,
                # One header, and the space after Bearer is load-bearing: the
                # vendor names a missing one as the usual cause of a 401 that
                # looks like a bad key.
                headers={"Authorization": f"Bearer {cached[0]}"},
            )

    return fetch


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

    with validating(f"manifest for {key}"):
        manifest = Manifest(
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
        )
    store.put_json(manifest_key(key), manifest.model_dump(mode="json", exclude={"unmapped"}))

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


#: Anything that reads as a bearer token in a response body. SPEC 5.3 requires the
#: body of every non-2xx to be logged, which means an API that echoes the request
#: header into an error payload would put our credential in the Actions log. This
#: is not a general secret scrubber -- it is the one leak this path actually has.
_BEARER = re.compile(r'(?i)\bbearer\s+[^]\s",}]+')


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
    # Redact before encoding: percent-encoding a leaked key would hide it from a
    # careless read and not at all from anyone who decodes the line.
    safe = _BEARER.sub("Bearer [redacted]", body)
    return quote(safe) + ("..." if len(response.content) > limit else "")

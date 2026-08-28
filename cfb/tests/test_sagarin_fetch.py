"""The real Sagarin fetcher (SPEC-phase0 4.1), driven through ``httpx.MockTransport``.

Every other test in this suite injects ``fetch`` as a callable over a fixture,
which is what makes SPEC 4.3's ordering testable offline -- and also why nothing
yet exercises SPEC 4.1 at all. The pinned scheme, the refusal to follow a
redirect, the retry ladder and the timeout are the parts of this project most
likely to be wrong in a way only production notices, and they are exactly the
parts a lambda over a fixture cannot reach.

``httpx.MockTransport`` is the seam. It sits *below* the ``httpx.Client``, so the
client's own behaviour -- redirect policy, timeout, how many requests a retry
actually issues -- is what gets observed, rather than being stubbed out along
with the network. No socket is opened; ``cfb/CLAUDE.md``'s "no network calls in
tests, ever" holds.

**The signature here is a proposal, not spec**, in the idiom of
``test_calendar.py``. SPEC 8 pins only the shape the CLI hands to
``fetch_sagarin``: a zero-argument callable returning bytes. This file assumes::

    fetch_page(*, transport=None, sleep=time.sleep) -> bytes

with the URL, ``follow_redirects=False``, the timeout and the retry ladder all
owned by ``fetch_page``. The two keyword arguments exist only so the tests can
reach them. Building the ``httpx.Client`` inside the function rather than
accepting one is deliberate: if a test constructed the client, the redirect
policy and the timeout would be the test's decisions, and the assertions below
would be checking their own setup.

**One conflict with SPEC 4.1, flagged rather than papered over.** The spec says
"Three attempts, backoff 2s / 8s / 30s", and those cannot both hold: three
attempts leave room for two backoffs and the 30s rung is never reached. These
tests take the ladder as authoritative -- three *retries* after the initial
attempt, so four requests and sleeps of 2, 8, 30. If three requests total was
the intent, ``LADDER`` is the one line to change here and SPEC 4.1 should lose
the 30.
"""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from cfb.collectors.sagarin import SOURCE_URL, fetch_page, fetch_sagarin
from cfb.errors import FetchError
from cfb.storage import FileSnapshotStore

FIXTURES = Path(__file__).parent / "fixtures"

# Bytes, not text: SPEC 2.1 stores what the server sent and the manifest sha256
# hashes those bytes. \x92 is a cp1252 right single quote and invalid UTF-8, so a
# fetcher that decoded and re-encoded anywhere along the way would corrupt it.
PAGE = b"FINAL 2026 COLLEGE FOOTBALL \x92 CONFERENCE AVERAGES \r\n Hawai\x92i"

HTTPS_URL = "https://sagarin.com/sports/cfsend.htm"

#: See the module docstring: the ladder is authoritative, "three attempts" is not.
LADDER = [2, 8, 30]
ATTEMPTS = len(LADDER) + 1

#: Inside week 3 of the synthetic 2026 calendar. Only the snapshot key depends on
#: it, and these tests never get far enough to write one -- but a date the
#: calendar can place keeps a failure here pointing at the fetch.
IN_WEEK_THREE = datetime(2026, 9, 16, 11, 3, 2, tzinfo=UTC)


@pytest.fixture
def calendar_dir(tmp_path) -> Path:
    """A ``data/calendar/`` holding the synthetic 2026 calendar."""
    root = tmp_path / "calendar"
    root.mkdir()
    (root / "2026.json").write_bytes((FIXTURES / "calendar_2026_synthetic.json").read_bytes())
    return root


@pytest.fixture
def sleeps() -> list[float]:
    """Collects what the fetcher would have slept. Nothing here actually waits."""
    return []


@pytest.fixture
def recorder():
    """Builds ``(transport, requests)`` from a handler, recording every request.

    The request list is what separates "did not follow the redirect" from
    "followed it and happened to fail anyway", and "retried" from "looped".
    """

    def build(handler):
        requests: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        return httpx.MockTransport(recording), requests

    return build


def responder(*results):
    """A handler returning/raising ``results`` in order, then repeating the last.

    Repeating rather than running out keeps a fetcher that retries too many times
    visible as an attempt-count assertion, instead of as a ``StopIteration``
    surfacing from inside the transport.
    """
    queue = list(results)

    def handler(request: httpx.Request) -> httpx.Response:
        result = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(result, Exception):
            raise type(result)(str(result), request=request)
        return result

    return handler


def ok() -> httpx.Response:
    return httpx.Response(200, content=PAGE)


#: Everything SPEC 4.1 names as retryable: timeout, connection error, 5xx.
TRANSIENT = {
    "connect_timeout": httpx.ConnectTimeout("connect timed out"),
    "read_timeout": httpx.ReadTimeout("read timed out"),
    "connect_error": httpx.ConnectError("connection refused"),
    "500": httpx.Response(500),
    "502": httpx.Response(502),
    "503": httpx.Response(503, content=b"upstream unavailable"),
}
TRANSIENT_IDS = list(TRANSIENT)


# --- the pinned URL ------------------------------------------------------------


def test_fetches_the_pinned_http_url(recorder, sleeps):
    transport, requests = recorder(responder(ok()))

    fetch_page(transport=transport, sleep=sleeps.append)

    assert [str(request.url) for request in requests] == [SOURCE_URL]
    assert requests[0].url.scheme == "http"


def test_returns_the_response_bytes_verbatim(recorder, sleeps):
    transport, _ = recorder(responder(ok()))

    assert fetch_page(transport=transport, sleep=sleeps.append) == PAGE


def test_a_successful_fetch_does_not_sleep(recorder, sleeps):
    transport, _ = recorder(responder(ok()))

    fetch_page(transport=transport, sleep=sleeps.append)

    assert sleeps == []


def test_timeout_is_thirty_seconds_connect_and_read(recorder, sleeps):
    transport, requests = recorder(responder(ok()))

    fetch_page(transport=transport, sleep=sleeps.append)

    # httpx carries the effective timeout on the request, which is the only place
    # it is observable from below the client.
    timeout = requests[0].extensions["timeout"]
    assert timeout["connect"] == 30
    assert timeout["read"] == 30


# --- the HTTPS redirect --------------------------------------------------------


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_to_https_raises_rather_than_being_followed(recorder, sleeps, status):
    # The trap this guards: sagarin.com 302s HTTPS back to HTTP, so a client that
    # upgrades the scheme ping-pongs until it exhausts its redirect limit. The
    # https branch answers with a plausible 200 on purpose -- a fetcher that
    # followed the redirect would return `sentinel` and quietly pass a weaker
    # test that only checked "some bytes came back".
    sentinel = b"this page was reached over https"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.scheme == "https":
            return httpx.Response(200, content=sentinel)
        return httpx.Response(status, headers={"Location": HTTPS_URL})

    transport, requests = recorder(handler)

    with pytest.raises(FetchError):
        fetch_page(transport=transport, sleep=sleeps.append)

    assert [str(request.url) for request in requests] == [SOURCE_URL]


def test_a_redirect_is_not_retried(recorder, sleeps):
    transport, requests = recorder(responder(httpx.Response(302, headers={"Location": HTTPS_URL})))

    with pytest.raises(FetchError):
        fetch_page(transport=transport, sleep=sleeps.append)

    # A redirect is a decision the server has already made; repeating the request
    # earns the same answer three more times.
    assert len(requests) == 1
    assert sleeps == []


# --- the retry ladder ----------------------------------------------------------


@pytest.mark.parametrize("failure", TRANSIENT_IDS, ids=TRANSIENT_IDS)
def test_transient_failures_retry_on_the_ladder(recorder, sleeps, failure):
    transport, requests = recorder(responder(TRANSIENT[failure]))

    with pytest.raises(FetchError):
        fetch_page(transport=transport, sleep=sleeps.append)

    assert len(requests) == ATTEMPTS
    assert sleeps == LADDER


@pytest.mark.parametrize("failure", TRANSIENT_IDS, ids=TRANSIENT_IDS)
def test_every_retried_request_is_the_same_pinned_url(recorder, sleeps, failure):
    transport, requests = recorder(responder(TRANSIENT[failure]))

    with pytest.raises(FetchError):
        fetch_page(transport=transport, sleep=sleeps.append)

    assert {str(request.url) for request in requests} == {SOURCE_URL}


@pytest.mark.parametrize("failure", TRANSIENT_IDS, ids=TRANSIENT_IDS)
def test_a_recovered_fetch_stops_at_the_rung_it_needed(recorder, sleeps, failure):
    # Proves the ladder is walked rather than merely exhausted: two failures then
    # a 200 should cost exactly the first two rungs and return the real bytes.
    transport, requests = recorder(responder(TRANSIENT[failure], TRANSIENT[failure], ok()))

    assert fetch_page(transport=transport, sleep=sleeps.append) == PAGE
    assert len(requests) == 3
    assert sleeps == LADDER[:2]


# 429 is in this list on purpose. SPEC 5.3 gives CFBD a 429-with-backoff branch;
# SPEC 4.1 gives Sagarin no such exception, and a shared retry helper that grew
# one for CFBD's sake would silently change this collector.
@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 429])
def test_4xx_does_not_retry(recorder, sleeps, status):
    transport, requests = recorder(responder(httpx.Response(status, content=b"nope")))

    with pytest.raises(FetchError):
        fetch_page(transport=transport, sleep=sleeps.append)

    assert len(requests) == 1
    assert sleeps == []


# --- exhaustion writes nothing -------------------------------------------------


@pytest.mark.parametrize("failure", TRANSIENT_IDS, ids=TRANSIENT_IDS)
def test_exhausted_retries_raise_fetch_error(recorder, sleeps, failure):
    transport, _ = recorder(responder(TRANSIENT[failure]))

    with pytest.raises(FetchError):
        fetch_page(transport=transport, sleep=sleeps.append)


@pytest.mark.parametrize("failure", TRANSIENT_IDS, ids=TRANSIENT_IDS)
def test_a_failed_fetch_writes_no_snapshot(tmp_path, recorder, sleeps, calendar_dir, failure):
    """SPEC 4.1: total failure writes no snapshot, not an empty one.

    Asserted through ``fetch_sagarin`` rather than ``fetch_page`` alone, because
    "writes nothing" is a claim about the collector. SPEC 4.3 puts the fetch at
    step 1 precisely so a failure there cannot leave a zero-byte object under a
    key no later run can reuse -- ``raw/`` is write-once, so a bad object at the
    right key is permanent.
    """
    root = tmp_path / "snapshots"
    store = FileSnapshotStore(root)
    transport, _ = recorder(responder(TRANSIENT[failure]))

    with pytest.raises(FetchError):
        fetch_sagarin(
            store=store,
            now=IN_WEEK_THREE,
            fetch=lambda: fetch_page(transport=transport, sleep=sleeps.append),
            data_dir=calendar_dir,
        )

    assert [path for path in root.rglob("*") if path.is_file()] == []

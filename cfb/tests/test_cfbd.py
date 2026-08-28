"""The CFBD client: budget and retries (SPEC-phase0 5.1 and 5.3).

``cfb/CLAUDE.md`` forbids calling CFBD from a test without qualification, and the
reason is not tidiness: every call costs quota a scheduled run needs, and the
quota is the thing this whole section exists to protect. So the seam is the same
one Sagarin uses -- an injected callable standing where the network would be --
and every response below is synthetic.

    fetch(path: str, params: dict) -> httpx.Response

``httpx.Response`` rather than bytes, because unlike Sagarin's fetcher this seam
sits *below* the part being tested: the status code, the ``Retry-After`` header
and the body are the inputs to the budget and retry logic, so a seam that
returned only bytes would hide exactly what these tests are about.

**The budget guard is the one that fails quietly.** A client that counts nothing
passes any test that only asserts "the 26th call raised", if the 26th call
happened to fail for its own reasons -- and passes a test that counts only
logical requests while retries burn quota invisibly. So the assertions here are
about what the *seam* saw: how many requests were actually issued, and when they
stopped. ``test_the_twenty_sixth_call_is_never_issued`` is the load-bearing one.
A guard that counts after the fact rather than before satisfies every other test
in the class.

**Two ladders, not one.** SPEC 5.3 gives 429 its own backoff of 5/20/60 and then
says 5xx "follows §4.1", which is 2/8/30. That is not a typo to normalize: a
429 is the server asking for room and a 500 is the server failing, and they are
worth waiting on differently. Both are asserted separately below.

**Both ladders count requests, the initial one included.** SPEC 5.3 used to say
"maximum 3 attempts" beside a three-rung ladder, which could not hold both ways;
the word was the ambiguity and the spec has dropped it. Three *requests* at
worst, so the initial one plus two retries, and both ladders lost their last
rung: 5/20 here, 2/8 in §4.1. The reason is arithmetic rather than taste -- a
four-request ladder spends 4 of a 25-request budget on one weekly pull, which
would make retries a larger share of the run than the data. Nothing below hard-
codes a rung count; ``ATTEMPTS_429`` and ``ATTEMPTS_5XX`` derive from the
constants.

**Signatures are proposals.** SPEC 5.1 requires the cap to be enforced "in the
client" and SPEC 8 gives the CLI surface, but no names::

    CfbdClient(*, fetch, sleep=time.sleep, budget=CALL_BUDGET_PER_RUN)
    CfbdClient.get(path, **params) -> bytes
    CfbdClient.calls_made -> int
    fetch_cfbd(*, store, client, resource, season, week, now) -> bytes

The client owns the budget and the retries; the collector owns the snapshot. That
split is what SPEC 5.1's "enforced in the client, not a shared counter" asks for,
and it is why the vendor's own Python package is unusable here (per the
``cfbd-api`` skill): a package that makes its own requests is a budget guard with
a hole in it.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from cfb.collectors.cfbd import (
    BACKOFF,
    BACKOFF_429,
    CALL_BUDGET_PER_RUN,
    CfbdClient,
    fetch_cfbd,
)
from cfb.errors import CallBudgetExceeded, FetchError
from cfb.logging import EVENT_CFBD_CALL, EVENT_HTTP_ERROR
from cfb.storage import FileSnapshotStore

FIXTURES = Path(__file__).parent / "fixtures"
GAMES = FIXTURES / "cfbd_games_2026_week04.json"

FETCHED = datetime(2026, 9, 21, 12, 1, 17, tzinfo=UTC)

#: Retries are part of the ladder, so the worst case is one more than the rungs.
ATTEMPTS_429 = len(BACKOFF_429) + 1
ATTEMPTS_5XX = len(BACKOFF) + 1


def ok(body: bytes = b"[]") -> httpx.Response:
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def responder(*results):
    """A fetch callable returning/raising ``results`` in order, repeating the last.

    Repeating rather than running out keeps a client that issues too many requests
    visible as a count assertion rather than as a ``StopIteration`` surfacing from
    inside the seam.
    """
    queue = list(results)

    def fetch(path: str, params: dict) -> httpx.Response:
        result = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(result, Exception):
            raise result
        return result

    return fetch


@pytest.fixture
def sleeps() -> list[float]:
    """What the client would have waited. Nothing here actually sleeps."""
    return []


@pytest.fixture
def issued() -> list[tuple[str, dict]]:
    """Every request the seam actually saw, in order.

    The budget is a claim about this list and nothing else. A counter that agrees
    with itself while the seam sees more requests than it admits to is precisely
    the bug worth catching.
    """
    return []


@pytest.fixture
def client_for(sleeps, issued):
    """Builds a ``CfbdClient`` over a recording seam."""

    def build(fetch, *, budget: int = CALL_BUDGET_PER_RUN) -> CfbdClient:
        def recording(path: str, params: dict) -> httpx.Response:
            issued.append((path, dict(params)))
            return fetch(path, params)

        return CfbdClient(fetch=recording, sleep=sleeps.append, budget=budget)

    return build


def logged(capsys, event: str) -> list[dict[str, str]]:
    """Every ``key=value`` line for one event, parsed."""
    lines = [line for line in capsys.readouterr().out.splitlines() if f"event={event}" in line]
    return [dict(pair.split("=", 1) for pair in line.split() if "=" in pair) for line in lines]


class TestTheCallBudget:
    """SPEC 5.1: a per-run hard cap of 25, enforced in the client.

    The cap is the whole defence. The 1,000/month figure it is protecting is not
    vendor-backed and must never become a runtime check (SPEC 5.1, and the
    ``cfbd-api`` skill), so what actually bounds the month is cap x runs -- which
    holds only for as long as the cap is real.
    """

    def test_the_budget_allows_exactly_the_cap(self, client_for, issued):
        client = client_for(responder(ok()))

        for _ in range(CALL_BUDGET_PER_RUN):
            client.get("/games", year=2026, week=4)

        assert len(issued) == CALL_BUDGET_PER_RUN
        assert client.calls_made == CALL_BUDGET_PER_RUN

    def test_the_call_after_the_cap_raises(self, client_for):
        client = client_for(responder(ok()))
        for _ in range(CALL_BUDGET_PER_RUN):
            client.get("/games", year=2026, week=4)

        with pytest.raises(CallBudgetExceeded):
            client.get("/games", year=2026, week=5)

    def test_the_twenty_sixth_call_is_never_issued(self, client_for, issued):
        """The one that fails against a client that counts nothing.

        A guard that checks the counter *after* sending has already spent the
        quota it exists to protect, and every other assertion in this class is
        satisfied by one -- the exception still raises, the count still reads 26.
        The seam is the only witness that can tell the two apart.
        """
        client = client_for(responder(ok()))
        for _ in range(CALL_BUDGET_PER_RUN):
            client.get("/games", year=2026, week=4)

        with pytest.raises(CallBudgetExceeded):
            client.get("/games", year=2026, week=5)

        assert len(issued) == CALL_BUDGET_PER_RUN, (
            "the over-budget request reached the seam; the guard must refuse before "
            "sending, not count after"
        )

    def test_the_cap_is_twenty_five(self):
        """SPEC 5.1 names the number. The tests above are written against the
        constant so they survive it changing; this one pins what it is today.
        """
        assert CALL_BUDGET_PER_RUN == 25

    def test_every_retry_counts_against_the_budget(self, client_for, issued):
        """SPEC 5.3, and the second way a budget guard passes while leaking.

        A client that counts calls to ``get`` rather than requests to the seam
        reports 25 while having issued far more -- retries are where the quota
        actually goes. One 429-exhausting call costs a full ladder, so the budget
        left afterwards is the cap minus that, not the cap minus one.
        """
        client = client_for(responder(httpx.Response(429), httpx.Response(429), ok()))

        client.get("/games", year=2026, week=4)  # 3 requests: two 429s then a 200

        assert len(issued) == 3
        assert client.calls_made == 3

        for _ in range(CALL_BUDGET_PER_RUN - 3):
            client.get("/lines", year=2026, week=4)
        assert len(issued) == CALL_BUDGET_PER_RUN

        with pytest.raises(CallBudgetExceeded):
            client.get("/teams/fbs", year=2026)

    def test_the_budget_can_run_out_mid_retry(self, client_for, issued, sleeps):
        """Budget beats backoff. A retry is a request like any other.

        With one call left and a server that keeps asking for room, the client
        must stop at the cap rather than finish its ladder -- and the error names
        the budget, because that is what actually stopped it.
        """
        client = client_for(responder(httpx.Response(429)), budget=2)

        with pytest.raises(CallBudgetExceeded):
            client.get("/games", year=2026, week=4)

        assert len(issued) == 2

    def test_the_counter_is_per_run_with_no_cross_run_state(self, client_for, issued):
        """SPEC 5.1: stateless, with no cross-run counter to race or leave wrong.

        A module-level counter would pass every test above and then refuse the
        second client's first call. Nothing about a fresh client may depend on
        what an earlier one did.
        """
        first = client_for(responder(ok()))
        for _ in range(CALL_BUDGET_PER_RUN):
            first.get("/games", year=2026, week=4)
        with pytest.raises(CallBudgetExceeded):
            first.get("/games", year=2026, week=5)

        second = client_for(responder(ok()))
        assert second.calls_made == 0
        for _ in range(CALL_BUDGET_PER_RUN):
            second.get("/games", year=2026, week=6)

        assert len(issued) == 2 * CALL_BUDGET_PER_RUN

    def test_every_call_is_logged_with_a_running_count(self, client_for, capsys):
        """SPEC 5.1: the Actions log is where the real monthly figure is recovered from.

        Without the running count the log says a call happened, which is the part
        already obvious from the run existing.
        """
        client = client_for(responder(ok()))
        for _ in range(3):
            client.get("/games", year=2026, week=4)

        counts = [entry.get("call") for entry in logged(capsys, EVENT_CFBD_CALL)]
        assert counts == ["1", "2", "3"]


class TestRateLimitRetries:
    """SPEC 5.3: 429 respects ``Retry-After``, else backs off 5/20/60."""

    def test_429_walks_its_own_ladder_then_raises(self, client_for, issued, sleeps):
        client = client_for(responder(httpx.Response(429)))

        with pytest.raises(FetchError):
            client.get("/games", year=2026, week=4)

        assert len(issued) == ATTEMPTS_429
        assert sleeps == list(BACKOFF_429)

    def test_429_is_not_given_the_5xx_ladder(self, sleeps):
        """The two ladders are different on purpose; this fails if they are merged."""
        assert list(BACKOFF_429) != list(BACKOFF)

    @pytest.mark.parametrize("after", ["1", "3", "120"])
    def test_retry_after_is_honoured_when_present(self, client_for, sleeps, after):
        """The server naming a wait is better information than a fixed ladder."""
        client = client_for(
            responder(httpx.Response(429, headers={"Retry-After": after}), ok())
        )

        client.get("/games", year=2026, week=4)

        assert sleeps == [float(after)]

    @pytest.mark.parametrize("after", ["", "soon", "-1", "Wed, 21 Oct 2026 07:28:00 GMT"])
    def test_an_unusable_retry_after_falls_back_to_the_ladder(self, client_for, sleeps, after):
        """A header that cannot be read as seconds is not a reason to wait forever,
        or to not wait at all. The HTTP-date form is in here deliberately: it is
        legal, this client does not parse it, and falling back is the honest
        answer until it does.
        """
        client = client_for(
            responder(httpx.Response(429, headers={"Retry-After": after}), ok())
        )

        client.get("/games", year=2026, week=4)

        assert sleeps == [BACKOFF_429[0]]

    def test_a_recovered_429_stops_at_the_rung_it_needed(self, client_for, issued, sleeps):
        """Proves the ladder is walked rather than always exhausted."""
        body = GAMES.read_bytes()
        client = client_for(responder(httpx.Response(429), httpx.Response(429), ok(body)))

        assert client.get("/games", year=2026, week=4) == body
        assert len(issued) == 3
        assert sleeps == list(BACKOFF_429[:2])


class TestWhatIsNotRetryable:
    """The retryable set is a whitelist: 429 and 5xx. Everything else non-2xx stops.

    SPEC 5.3 is explicit that an unrecognised quota or entitlement response is
    non-retryable -- retrying a request the account is not entitled to make burns
    budget to earn the same answer. The safe shape of that rule is a whitelist,
    because the response that ends up meaning "over quota" is one the vendor has
    stopped documenting and nobody here has seen.
    """

    @pytest.mark.parametrize("status", [400, 401, 403, 404])
    def test_documented_4xx_never_retries(self, client_for, issued, sleeps, status):
        client = client_for(responder(httpx.Response(status, content=b'{"message":"nope"}')))

        with pytest.raises(FetchError):
            client.get("/games", year=2026, week=4)

        assert len(issued) == 1
        assert sleeps == []

    @pytest.mark.parametrize("status", [402, 409, 418, 422, 451])
    def test_an_unrecognised_quota_response_is_not_retried(
        self, client_for, issued, sleeps, status
    ):
        """Statuses CFBD does not document, which is the whole point.

        A client whose retry rule is "anything unexpected, try again" spends four
        requests of a 25-request budget learning what one request already said.
        """
        client = client_for(
            responder(httpx.Response(status, content=b'{"message":"quota exceeded"}'))
        )

        with pytest.raises(FetchError):
            client.get("/games", year=2026, week=4)

        assert len(issued) == 1
        assert sleeps == []

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_5xx_follows_the_spec_4_1_ladder(self, client_for, issued, sleeps, status):
        client = client_for(responder(httpx.Response(status)))

        with pytest.raises(FetchError):
            client.get("/games", year=2026, week=4)

        assert len(issued) == ATTEMPTS_5XX
        assert sleeps == list(BACKOFF)

    def test_a_transport_error_retries_and_then_raises_fetch_error(
        self, client_for, issued, sleeps
    ):
        """A connection that never established is the 5xx case by another name."""
        client = client_for(responder(httpx.ConnectError("connection refused")))

        with pytest.raises(FetchError):
            client.get("/games", year=2026, week=4)

        assert len(issued) == ATTEMPTS_5XX
        assert sleeps == list(BACKOFF)


class TestEveryNon2xxIsLogged:
    """SPEC 5.3: log the status and the response body on every non-2xx, without exception.

    The vendor stopped naming the over-quota status, so what that response
    actually looks like is currently unknown and only a real one will settle it.
    A run that discarded the body leaves nothing to decide from -- which makes
    this log line the only path from "the pipeline went red" to "we now know what
    CFBD sends when the account is out of quota".
    """

    @pytest.mark.parametrize("status", [400, 402, 429, 500])
    def test_the_status_and_body_are_both_logged(self, client_for, capsys, status):
        body = b'{"message":"the thing the vendor actually said"}'
        client = client_for(responder(httpx.Response(status, content=body)))

        with pytest.raises(FetchError):
            client.get("/games", year=2026, week=4)

        entries = logged(capsys, EVENT_HTTP_ERROR)
        assert entries, f"{status} was not logged at all"
        assert any(entry.get("status") == str(status) for entry in entries)
        assert any("vendor" in entry.get("body", "") for entry in entries), (
            "the response body is the only evidence of what an undocumented "
            "quota response looks like"
        )

    def test_every_attempt_of_a_retry_is_logged_not_just_the_last(self, client_for, capsys):
        """"Without exception" includes the ones that were about to be retried."""
        client = client_for(responder(httpx.Response(503, content=b"upstream down")))

        with pytest.raises(FetchError):
            client.get("/games", year=2026, week=4)

        assert len(logged(capsys, EVENT_HTTP_ERROR)) == ATTEMPTS_5XX


class TestTheCollector:
    """SPEC 5.3 and 4.3: what reaches the store, and what must not."""

    @pytest.fixture
    def root(self, tmp_path) -> Path:
        return tmp_path / "snapshots"

    def test_a_successful_pull_stores_the_bytes_verbatim(self, client_for, root):
        """SPEC 2.1: the snapshot is what the server sent, byte for byte."""
        body = GAMES.read_bytes()
        store = FileSnapshotStore(root)
        client = client_for(responder(ok(body)))

        fetch_cfbd(
            store=store,
            client=client,
            resource="games",
            season=2026,
            week="04",
            now=FETCHED,
        )

        [written] = [p for p in root.rglob("*.json") if not p.name.endswith(".meta.json")]
        assert written.read_bytes() == body
        assert "/week=04/games/" in written.as_posix()

    def test_exhausted_retries_write_no_snapshot(self, client_for, root):
        """SPEC 4.1's rule, which 5.3 inherits: total failure writes nothing.

        Asserted at the collector because "writes nothing" is a claim about the
        collector. ``raw/`` is write-once, so a truncated or empty object at the
        right key is permanent -- there is no second chance to store that pull.
        """
        store = FileSnapshotStore(root)
        client = client_for(responder(httpx.Response(500)))

        with pytest.raises(FetchError):
            fetch_cfbd(
                store=store,
                client=client,
                resource="games",
                season=2026,
                week="04",
                now=FETCHED,
            )

        assert [p for p in root.rglob("*") if p.is_file()] == []

    def test_a_budget_refusal_writes_no_snapshot(self, client_for, root):
        """The other way a pull ends with nothing to store."""
        store = FileSnapshotStore(root)
        client = client_for(responder(ok()), budget=0)

        with pytest.raises(CallBudgetExceeded):
            fetch_cfbd(
                store=store,
                client=client,
                resource="games",
                season=2026,
                week="04",
                now=FETCHED,
            )

        assert [p for p in root.rglob("*") if p.is_file()] == []


class TestTheFixtureItself:
    """Guards the synthetic capture, so a failure above is never the fixture's fault."""

    def test_the_games_fixture_is_the_cfbd_games_shape(self):
        games = json.loads(GAMES.read_bytes())
        assert len(games) == 3
        assert {"id", "season", "week", "homeTeam", "awayTeam"} <= set(games[0])
        assert {game["week"] for game in games} == {4}

    def test_the_fixture_carries_an_unplayed_game(self):
        """Null scores are the ordinary shape of a week that is not finished, and
        the reason nothing downstream may treat points as required.
        """
        games = json.loads(GAMES.read_bytes())
        assert any(game["homePoints"] is None for game in games)

    def test_the_fixture_carries_a_name_the_crosswalk_has_to_resolve(self):
        """``Texas A&M`` and ``UCF`` are both live crosswalk cases in SPEC 6.1."""
        names = {g["homeTeam"] for g in json.loads(GAMES.read_bytes())}
        assert "UCF" in names
        assert not any(re.search(r"\s{2,}", name) for name in names)

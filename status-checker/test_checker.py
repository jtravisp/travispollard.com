"""Tests for checker.py. Run from this directory: python -m pytest -q

The HTTP cases use a real server on 127.0.0.1, so status codes, redirects,
connection reuse and timing go through http.client exactly as they do in
Lambda. The TLS path needs a real certificate and is covered by `days_until`,
the only part of it that is logic.
"""

import json
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import checker


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive, so redirects can reuse the connection
    connections_seen = set()

    def _send(self, code, headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # noqa: N802 - http.server's naming
        type(self).connections_seen.add(self.client_address)
        if self.path == "/ok":
            self._send(200)
        elif self.path == "/redirect":
            self._send(302, [("Location", "/ok")])
        elif self.path == "/loop":
            self._send(302, [("Location", "/loop")])
        elif self.path == "/slow":
            time.sleep(0.25)
            self._send(200)
        elif self.path == "/very-slow":
            time.sleep((checker.DEGRADED_LATENCY_MS + 150) / 1000)
            self._send(200)
        else:
            self._send(503)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def target(url, id_="svc"):
    return {"id": id_, "name": "Service", "url": url}


# --- classification -----------------------------------------------------------

@pytest.mark.parametrize(
    "code, ms, error, expected",
    [
        (200, 120, None, "operational"),
        (301, 120, None, "operational"),
        (200, checker.DEGRADED_LATENCY_MS + 1, None, "degraded"),
        (200, checker.DEGRADED_LATENCY_MS, None, "operational"),
        (404, 50, "HTTP 404", "down"),
        (503, 50, "HTTP 503", "down"),
        (None, None, "request failed: timed out", "down"),
    ],
)
def test_classify(code, ms, error, expected):
    assert checker.classify(code, ms, error) == expected


def test_overall_status_takes_the_worst():
    assert checker.overall_status(["operational", "operational"]) == "operational"
    assert checker.overall_status(["operational", "degraded"]) == "degraded"
    assert checker.overall_status(["degraded", "down", "operational"]) == "outage"


def test_days_until_counts_whole_days_and_goes_negative():
    now = checker.ssl.cert_time_to_seconds("Jan  1 00:00:00 2030 GMT")
    assert checker.days_until("Jan 11 12:00:00 2030 GMT", now) == 10
    assert checker.days_until("Dec 31 00:00:00 2029 GMT", now) == -1


# --- real HTTP ----------------------------------------------------------------

def test_ok(base_url):
    result = checker.check(target(f"{base_url}/ok"), timeout=5)
    assert result["status"] == "operational"
    assert result["http_code"] == 200
    assert isinstance(result["response_time_ms"], int)
    assert isinstance(result["connect_ms"], int)
    assert result["cert_days_remaining"] is None  # plain http: no certificate
    assert "error" not in result


def test_redirect_reports_the_final_status_on_one_connection(base_url):
    _Handler.connections_seen.clear()
    result = checker.check(target(f"{base_url}/redirect"), timeout=5)
    assert result["http_code"] == 200
    assert result["status"] == "operational"
    # Both hops arrived from the same client socket: the connection was reused.
    assert len(_Handler.connections_seen) == 1


def test_redirect_loop_is_down_not_endless(base_url):
    result = checker.check(target(f"{base_url}/loop"), timeout=5)
    assert result["status"] == "down"
    assert "redirects" in result["error"]


def test_server_error_is_down_with_its_code(base_url):
    result = checker.check(target(f"{base_url}/broken"), timeout=5)
    assert result["status"] == "down"
    assert result["http_code"] == 503
    assert result["error"] == "HTTP 503"


def test_response_time_excludes_connection_setup(base_url):
    result = checker.check(target(f"{base_url}/slow"), timeout=5)
    assert result["response_time_ms"] >= 250
    assert result["connect_ms"] < 250  # localhost connect is near-instant


def test_a_slow_response_is_degraded(base_url):
    result = checker.check(target(f"{base_url}/very-slow"), timeout=5)
    assert result["status"] == "degraded"


def test_unreachable_is_down_not_an_exception():
    # Port 9 on localhost: nothing listens, so the connection is refused.
    result = checker.check(target("http://127.0.0.1:9/"), timeout=2)
    assert result["status"] == "down"
    assert result["http_code"] is None
    assert result["response_time_ms"] is None
    assert result["error"].startswith("request failed")


def test_checks_run_concurrently(base_url):
    started = time.perf_counter()
    checker.run_checks([target(f"{base_url}/slow", str(i)) for i in range(4)], timeout=5)
    assert time.perf_counter() - started < 0.9  # four 0.25 s responses, not 1 s serially


# --- history ------------------------------------------------------------------

def svc(status, ms=100, id_="a"):
    return {"id": id_, "status": status, "response_time_ms": ms}


def test_record_counts_and_daily_status():
    h = checker.empty_history()
    day = date(2026, 9, 24)
    for _ in range(9):
        checker.record(h, [svc("operational", 100)], day)
    checker.record(h, [svc("degraded", 1500)], day)
    c = h["days"]["2026-09-24"]["a"]
    assert c == {"checks": 10, "down": 0, "degraded": 1, "latency_sum_ms": 2400, "latency_n": 10}
    # 1 slow check in 10 is not more than 10%: still operational.
    assert checker.day_status(c) == "operational"
    checker.record(h, [svc("degraded", 1500)], day)
    assert checker.day_status(h["days"]["2026-09-24"]["a"]) == "degraded"
    checker.record(h, [svc("down", None)], day)
    assert checker.day_status(h["days"]["2026-09-24"]["a"]) == "down"


def test_daily_history_is_thirty_days_and_unchecked_days_are_no_data():
    h = checker.empty_history()
    checker.record(h, [svc("operational", 120)], date(2026, 9, 24))
    days = checker.daily_history(h, "a", date(2026, 9, 24))
    assert len(days) == checker.HISTORY_DAYS
    assert days[0]["date"] == "2026-08-26" and days[-1]["date"] == "2026-09-24"
    assert days[-1] == {"date": "2026-09-24", "status": "operational", "avg_latency_ms": 120}
    assert {d["status"] for d in days[:-1]} == {"no_data"}
    assert all(d["avg_latency_ms"] is None for d in days[:-1])


def test_days_outside_the_window_are_dropped():
    h = checker.empty_history()
    checker.record(h, [svc("down")], date(2026, 8, 1))
    checker.record(h, [svc("operational")], date(2026, 9, 24))
    assert list(h["days"]) == ["2026-09-24"]


def test_uptime_percentage():
    h = checker.empty_history()
    assert checker.uptime_percentage(h, "a") is None
    for _ in range(143):
        checker.record(h, [svc("operational")], date(2026, 9, 24))
    checker.record(h, [svc("down", None)], date(2026, 9, 24))
    assert checker.uptime_percentage(h, "a") == 99.31  # 143 of 144


# --- the handler --------------------------------------------------------------

class _ClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _FakeS3:
    def __init__(self, stored=None, get_error=None):
        self.objects = dict(stored or {})
        self.get_error = get_error
        self.puts = []

    def get_object(self, Bucket, Key):
        if self.get_error:
            raise _ClientError(self.get_error)
        if Key not in self.objects:
            raise _ClientError("NoSuchKey")

        class _Body:
            def __init__(self, data):
                self.data = data

            def read(self):
                return self.data

        return {"Body": _Body(self.objects[Key])}

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]


@pytest.fixture
def env(base_url, monkeypatch):
    monkeypatch.setenv(
        "TARGETS",
        json.dumps([target(f"{base_url}/ok", "a"), target(f"{base_url}/broken", "b")]),
    )
    monkeypatch.setenv("BUCKET", "example-bucket")
    monkeypatch.setenv("TIMEOUT_S", "5")


def test_first_run_creates_history_and_writes_status(env):
    s3 = _FakeS3()
    assert checker.handler({}, None, s3_client=s3, today=date(2026, 9, 24)) == {
        "overall_status": "outage"
    }
    assert [p["Key"] for p in s3.puts] == ["status-history.json", "status.json"]
    status = next(p for p in s3.puts if p["Key"] == "status.json")
    assert status["CacheControl"] == "public, max-age=60"
    document = json.loads(status["Body"])
    a, b = document["services"]
    assert document["history_days"] == 30
    assert a["uptime_percentage_30d"] == 100.0 and b["uptime_percentage_30d"] == 0.0
    assert a["daily_history"][-1]["status"] == "operational"
    assert b["daily_history"][-1]["status"] == "down"
    assert a["daily_history"][0]["status"] == "no_data"


def test_history_accumulates_across_runs(env):
    s3 = _FakeS3()
    for _ in range(3):
        checker.handler({}, None, s3_client=s3, today=date(2026, 9, 24))
    history = json.loads(s3.objects["status-history.json"])
    assert history["days"]["2026-09-24"]["a"]["checks"] == 3


def test_unreadable_history_is_never_overwritten(env):
    s3 = _FakeS3(stored={"status-history.json": b'{"days": {"2026-09-01": {}}}'}, get_error="AccessDenied")
    checker.handler({}, None, s3_client=s3, today=date(2026, 9, 24))
    assert [p["Key"] for p in s3.puts] == ["status.json"]
    document = json.loads(s3.puts[0]["Body"])
    assert "daily_history" not in document["services"][0]
    assert s3.objects["status-history.json"] == b'{"days": {"2026-09-01": {}}}'


def test_corrupt_history_starts_over(env):
    s3 = _FakeS3(stored={"status-history.json": b"not json"})
    checker.handler({}, None, s3_client=s3, today=date(2026, 9, 24))
    history = json.loads(s3.objects["status-history.json"])
    assert history["days"]["2026-09-24"]["a"]["checks"] == 1

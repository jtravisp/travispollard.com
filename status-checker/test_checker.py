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
    """An S3 that honours IfMatch / IfNoneMatch the way the real one does.

    Every write gets a fresh ETag; a conditional put whose condition fails
    raises PreconditionFailed. `before_put` runs just before each put, which is
    where a test plays the part of a second, overlapping run.
    """

    def __init__(self, stored=None, get_error=None, put_error=None, before_put=None):
        self.objects = {}
        self.etags = {}
        self._n = 0
        for k, v in (stored or {}).items():
            self._store(k, v)
        self.get_error = get_error
        self.put_error = put_error
        self.before_put = before_put
        self.puts = []

    def _store(self, key, body):
        self._n += 1
        self.objects[key] = body
        self.etags[key] = f'"etag-{self._n}"'

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

        return {"Body": _Body(self.objects[Key]), "ETag": self.etags[Key]}

    def put_object(self, **kwargs):
        if self.before_put:
            self.before_put(self, kwargs)
        key = kwargs["Key"]
        if self.put_error and key == "status-history.json":
            raise _ClientError(self.put_error)
        if "IfMatch" in kwargs and self.etags.get(key) != kwargs["IfMatch"]:
            raise _ClientError("PreconditionFailed")
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise _ClientError("PreconditionFailed")
        self.puts.append(kwargs)
        self._store(key, kwargs["Body"])


class _FakeSNS:
    def __init__(self, fail=False):
        self.published = []
        self.fail = fail

    def publish(self, **kwargs):
        if self.fail:
            raise _ClientError("AuthorizationError")
        self.published.append(kwargs)


@pytest.fixture
def env(base_url, monkeypatch):
    monkeypatch.setenv(
        "TARGETS",
        json.dumps([target(f"{base_url}/ok", "a"), target(f"{base_url}/broken", "b")]),
    )
    monkeypatch.setenv("BUCKET", "example-bucket")
    monkeypatch.setenv("TIMEOUT_S", "5")
    monkeypatch.setenv("ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:111122223333:alerts")
    monkeypatch.setattr(checker.time, "sleep", lambda s: None)  # no real back-off in tests


def run(s3, sns=None):
    return checker.handler({}, None, s3_client=s3, sns_client=sns or _FakeSNS(), today=date(2026, 9, 24))


def history_of(s3):
    return json.loads(s3.objects["status-history.json"])


def test_first_run_creates_history_and_writes_status(env):
    s3 = _FakeS3()
    assert run(s3)["overall_status"] == "outage"
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
        run(s3)
    assert history_of(s3)["days"]["2026-09-24"]["a"]["checks"] == 3


def test_unreadable_history_is_never_overwritten(env):
    s3 = _FakeS3(stored={"status-history.json": b'{"days": {"2026-09-01": {}}}'}, get_error="AccessDenied")
    run(s3)
    assert [p["Key"] for p in s3.puts] == ["status.json"]
    document = json.loads(s3.puts[0]["Body"])
    assert "daily_history" not in document["services"][0]
    assert s3.objects["status-history.json"] == b'{"days": {"2026-09-01": {}}}'


def test_corrupt_history_starts_over(env):
    s3 = _FakeS3(stored={"status-history.json": b"not json"})
    run(s3)
    assert history_of(s3)["days"]["2026-09-24"]["a"]["checks"] == 1


# --- optimistic locking -------------------------------------------------------

def test_first_write_is_create_only_and_later_writes_match_the_etag(env):
    s3 = _FakeS3()
    run(s3)
    run(s3)
    first, second = [p for p in s3.puts if p["Key"] == "status-history.json"]
    assert first["IfNoneMatch"] == "*" and "IfMatch" not in first
    assert second["IfMatch"] == '"etag-1"' and "IfNoneMatch" not in second


def test_a_concurrent_write_is_retried_not_overwritten(env):
    """Another run writes the history between our read and our write."""
    s3 = _FakeS3()
    run(s3)  # one real run first: history has 1 check per service
    interfered = []

    def other_run(fake, kwargs):
        if kwargs["Key"] == "status-history.json" and not interfered:
            interfered.append(True)
            h = json.loads(fake.objects["status-history.json"])
            h["days"]["2026-09-24"]["a"]["checks"] += 1  # the other run's check
            fake._store("status-history.json", json.dumps(h).encode())

    s3.before_put = other_run
    run(s3)
    # 1 (first run) + 1 (the interfering run) + 1 (this run, after its retry):
    # nothing lost, nothing counted twice.
    assert history_of(s3)["days"]["2026-09-24"]["a"]["checks"] == 3


def test_it_gives_up_after_repeated_conflicts_but_still_writes_status(env):
    s3 = _FakeS3(put_error="PreconditionFailed")
    run(s3)
    assert [p["Key"] for p in s3.puts] == ["status.json"]
    assert "daily_history" not in json.loads(s3.puts[0]["Body"])["services"][0]


def test_a_non_conflict_write_error_is_not_retried(env):
    s3 = _FakeS3(put_error="AccessDenied")
    calls = []
    real_get = s3.get_object
    s3.get_object = lambda **kw: calls.append(1) or real_get(**kw)
    run(s3)
    assert len(calls) == 1  # read once, failed once, no retry loop


# --- alerts -------------------------------------------------------------------

def test_transitions_alert_once_per_outage_and_on_recovery():
    down = {"id": "a", "status": "down"}
    up = {"id": "a", "status": "operational"}
    slow = {"id": "a", "status": "degraded"}
    assert checker.transitions({"a": "operational"}, [down]) == [("DOWN", down)]
    assert checker.transitions({"a": "down"}, [down]) == []  # still down: no repeat
    assert checker.transitions({"a": "down"}, [up]) == [("RECOVERED", up)]
    assert checker.transitions({"a": "down"}, [slow]) == [("RECOVERED", slow)]
    assert checker.transitions({}, [down]) == [("DOWN", down)]  # new service, already down
    assert checker.transitions({"a": "operational"}, [slow]) == []  # degraded is not an alert
    assert checker.transitions(None, [down, up]) == [("DOWN", down)]  # unknown past: alert


def test_alert_message_reads_like_the_spec():
    s = {"name": "NCOER Writer", "url": "https://ncoer.travispollard.com", "status": "down",
         "http_code": 502, "error": "HTTP 502"}
    subject, body = checker.alert_message([("DOWN", s)], "2026-09-25T12:00:00Z")
    assert subject == "ALERT: NCOER Writer is DOWN. HTTP 502."
    assert "https://ncoer.travispollard.com" in body
    assert "https://www.travispollard.com/status/" in body

    timeout = {**s, "http_code": None, "error": "request failed: timed out"}
    assert checker.alert_message([("DOWN", timeout)], "t")[0] == "ALERT: NCOER Writer is DOWN. timed out."


def test_a_run_that_takes_a_service_down_publishes_one_alert(env):
    s3, sns = _FakeS3(), _FakeSNS()
    result = run(s3, sns)
    assert result["alerts"] == 1
    (message,) = sns.published
    assert message["TopicArn"] == "arn:aws:sns:us-east-1:111122223333:alerts"
    assert message["Subject"] == "ALERT: Service is DOWN. HTTP 503."
    run(s3, sns)  # still down on the next run: no second email
    assert len(sns.published) == 1


def test_an_unsendable_alert_does_not_stop_the_run(env):
    s3 = _FakeS3()
    run(s3, _FakeSNS(fail=True))
    assert "status.json" in s3.objects


def test_no_topic_means_no_alerts(env, monkeypatch):
    monkeypatch.delenv("ALERT_TOPIC_ARN")
    sns = _FakeSNS()
    run(_FakeS3(), sns)
    assert sns.published == []

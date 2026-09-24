"""Tests for checker.py. Run from this directory: python -m pytest -q

The HTTP cases use a real server on 127.0.0.1, so status codes, redirects and
timing go through urllib exactly as they do in Lambda. The TLS path needs a
real certificate and is covered by `days_until`, the only part that is logic.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import checker


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server's naming
        if self.path == "/ok":
            self.send_response(200)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
        elif self.path == "/slow":
            time.sleep(0.25)
            self.send_response(200)
        else:
            self.send_response(503)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def target(url, id_="svc"):
    return {"id": id_, "name": "Service", "url": url}


# --- classification ---------------------------------------------------------

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


# --- real HTTP --------------------------------------------------------------

def test_ok(base_url):
    result = checker.check(target(f"{base_url}/ok"), timeout=5)
    assert result["status"] == "operational"
    assert result["http_code"] == 200
    assert isinstance(result["response_time_ms"], int)
    assert result["cert_days_remaining"] is None  # plain http: no certificate
    assert "error" not in result


def test_redirect_reports_the_final_status(base_url):
    result = checker.check(target(f"{base_url}/redirect"), timeout=5)
    assert result["http_code"] == 200
    assert result["status"] == "operational"


def test_server_error_is_down_with_its_code(base_url):
    result = checker.check(target(f"{base_url}/broken"), timeout=5)
    assert result["status"] == "down"
    assert result["http_code"] == 503
    assert result["error"] == "HTTP 503"


def test_latency_is_measured(base_url):
    result = checker.check(target(f"{base_url}/slow"), timeout=5)
    assert result["response_time_ms"] >= 250


def test_unreachable_is_down_not_an_exception():
    # Port 9 on localhost: nothing listens, so the connection is refused.
    result = checker.check(target("http://127.0.0.1:9/"), timeout=2)
    assert result["status"] == "down"
    assert result["http_code"] is None
    assert result["response_time_ms"] is None
    assert result["error"].startswith("request failed")


# --- the handler ------------------------------------------------------------

class _FakeS3:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


def test_handler_writes_status_json(base_url, monkeypatch):
    monkeypatch.setenv(
        "TARGETS",
        json.dumps([target(f"{base_url}/ok", "a"), target(f"{base_url}/broken", "b")]),
    )
    monkeypatch.setenv("BUCKET", "example-bucket")
    monkeypatch.setenv("TIMEOUT_S", "5")
    s3 = _FakeS3()

    assert checker.handler({}, None, s3_client=s3) == {"overall_status": "outage"}

    (call,) = s3.calls
    assert call["Bucket"] == "example-bucket"
    assert call["Key"] == "status.json"
    assert call["ContentType"] == "application/json"
    assert call["CacheControl"] == "public, max-age=60"
    document = json.loads(call["Body"])
    assert document["overall_status"] == "outage"
    assert [s["status"] for s in document["services"]] == ["operational", "down"]
    assert document["last_updated"].endswith("Z")

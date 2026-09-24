"""Synthetic checks for the projects travispollard.com links to, plus the site.

Invoked by EventBridge every ten minutes (see ../status-checker.tf). For each
target it requests the URL, following redirects, and records:

    connect_ms        DNS + TCP + TLS for every connection the request needed
    response_time_ms  request sent -> response headers, summed over redirects

They are separate because they measure different things. Connection setup is
dominated by the TLS handshake, which is CPU work *in this Lambda*; timing it
together with the response made a small, cold function report every site as
slow. Only response_time_ms decides "degraded". Connections are reused across
redirects to the same host, and the certificate is read from the same TLS
connection rather than a second one.

It then folds the run into a 30-day history (``status-history.json``: daily
counters per service) and writes ``status.json``, which the /status page
fetches, with each service's current check, 30-day uptime and daily bars.

Standard library plus boto3, which the Lambda Python runtime already ships, so
the deployment package is this one file.

Configuration, from the environment (set by Terraform):
    TARGETS      JSON list of {"id", "name", "url"}
    BUCKET       the site bucket
    KEY          status document key, default "status.json"
    HISTORY_KEY  history key, default "status-history.json"
    TIMEOUT_S    per-connection timeout in seconds, default 10

The thresholds below must match frontend/content/status.ts, which renders what
this decides; the names are the same so a grep finds both.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit

DEGRADED_LATENCY_MS = 1000
HISTORY_DAYS = 30

# A day is "degraded" when more than this share of its checks were slow. One
# slow check in 144 is noise; a tenth of the day is a pattern. Any failed
# check makes the day "down": an outage is an outage, and the uptime
# percentage says how long it lasted.
DEGRADED_DAY_SHARE = 0.10

MAX_REDIRECTS = 5
MAX_BODY_BYTES = 2_000_000

# Served through CloudFront's default behavior, whose cache policy honours the
# origin's Cache-Control and otherwise keeps an object for a day.
CACHE_CONTROL = "public, max-age=60"

USER_AGENT = "travispollard-status-checker/2.0 (+https://www.travispollard.com/status/)"
REDIRECT_CODES = {301, 302, 303, 307, 308}

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# --- classification -----------------------------------------------------------

def classify(http_code: int | None, response_time_ms: int | None, error: str | None) -> str:
    """down on any failure or a non-2xx/3xx final status; degraded if slow."""
    if error or http_code is None or not 200 <= http_code < 400:
        return "down"
    if response_time_ms is not None and response_time_ms > DEGRADED_LATENCY_MS:
        return "degraded"
    return "operational"


def overall_status(statuses: list[str]) -> str:
    """outage if anything is down, degraded if anything is slow, else operational."""
    if "down" in statuses:
        return "outage"
    if "degraded" in statuses:
        return "degraded"
    return "operational"


def days_until(not_after: str, now: float) -> int:
    """Whole days from `now` until an OpenSSL notAfter string. Negative once expired."""
    return int((ssl.cert_time_to_seconds(not_after) - now) // 86400)


# --- one check ----------------------------------------------------------------

def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def measure(url: str, timeout: float) -> dict:
    """Request `url`, following redirects. Never raises: failures are results."""
    context = ssl.create_default_context()
    connections: dict[tuple, http.client.HTTPConnection] = {}
    connect_ms = 0
    response_time_ms = 0
    http_code: int | None = None
    cert_days: int | None = None
    error: str | None = None

    try:
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            https = parts.scheme == "https"
            port = parts.port or (443 if https else 80)
            key = (parts.scheme, parts.hostname, port)

            conn = connections.get(key)
            if conn is None:
                conn = (
                    http.client.HTTPSConnection(parts.hostname, port, timeout=timeout, context=context)
                    if https
                    else http.client.HTTPConnection(parts.hostname, port, timeout=timeout)
                )
                started = time.perf_counter()
                conn.connect()
                connect_ms += _ms(started)
                connections[key] = conn
                if https and cert_days is None:
                    cert_days = days_until(conn.sock.getpeercert()["notAfter"], time.time())

            path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
            started = time.perf_counter()
            conn.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            response = conn.getresponse()
            response_time_ms += _ms(started)
            http_code = response.status

            # Drain the body so the connection can be reused by a redirect to
            # the same host; give up on reuse rather than read something huge.
            body = response.read(MAX_BODY_BYTES)
            if len(body) == MAX_BODY_BYTES or response.will_close:
                conn.close()
                del connections[key]

            location = response.getheader("Location")
            if http_code in REDIRECT_CODES and location:
                url = urljoin(url, location)
                continue
            break
        else:
            error = f"more than {MAX_REDIRECTS} redirects"
    except (OSError, http.client.HTTPException, ssl.SSLError, KeyError, ValueError) as exc:
        # OSError covers timeouts, refused connections, DNS failures and TLS
        # verification failures (an expired certificate lands here).
        http_code = None
        error = f"request failed: {exc}"
    finally:
        for conn in connections.values():
            conn.close()

    if error is None and http_code is not None and http_code >= 400:
        error = f"HTTP {http_code}"

    return {
        "http_code": http_code,
        "response_time_ms": response_time_ms if http_code is not None else None,
        "connect_ms": connect_ms if http_code is not None else None,
        "cert_days_remaining": cert_days,
        "error": error,
    }


def check(target: dict, timeout: float) -> dict:
    """One target's current result, in status.json's per-service shape."""
    m = measure(target["url"], timeout)
    result = {
        "id": target["id"],
        "name": target["name"],
        "url": target["url"],
        "status": classify(m["http_code"], m["response_time_ms"], m["error"]),
        "http_code": m["http_code"],
        "response_time_ms": m["response_time_ms"],
        "connect_ms": m["connect_ms"],
        "cert_days_remaining": m["cert_days_remaining"],
    }
    if m["error"]:
        result["error"] = m["error"]
    return result


def run_checks(targets: list[dict], timeout: float) -> list[dict]:
    """All targets concurrently: a run takes as long as the slowest site."""
    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as pool:
        return list(pool.map(lambda t: check(t, timeout), targets))


# --- history ------------------------------------------------------------------
#
# status-history.json holds counters, not results:
#   {"days": {"2026-09-24": {"<service id>": {"checks": 144, "down": 0,
#     "degraded": 3, "latency_sum_ms": 20160, "latency_n": 144}}}}
# Counters are what a daily status, an average latency and an uptime
# percentage can all be derived from, and they stay the same size however many
# runs a day has.

def empty_history() -> dict:
    return {"days": {}}


def record(history: dict, services: list[dict], today: date) -> dict:
    """Add one run to today's counters and drop days outside the window."""
    day = history["days"].setdefault(today.isoformat(), {})
    for s in services:
        c = day.setdefault(
            s["id"], {"checks": 0, "down": 0, "degraded": 0, "latency_sum_ms": 0, "latency_n": 0}
        )
        c["checks"] += 1
        if s["status"] == "down":
            c["down"] += 1
        elif s["status"] == "degraded":
            c["degraded"] += 1
        if s["response_time_ms"] is not None:
            c["latency_sum_ms"] += s["response_time_ms"]
            c["latency_n"] += 1

    oldest = (today - timedelta(days=HISTORY_DAYS - 1)).isoformat()
    history["days"] = {d: v for d, v in history["days"].items() if d >= oldest}
    return history


def day_status(c: dict | None) -> str:
    if not c or c["checks"] == 0:
        return "no_data"
    if c["down"] > 0:
        return "down"
    if c["degraded"] / c["checks"] > DEGRADED_DAY_SHARE:
        return "degraded"
    return "operational"


def daily_history(history: dict, service_id: str, today: date) -> list[dict]:
    """HISTORY_DAYS entries, oldest first. Days never checked are no_data, not green."""
    out = []
    for offset in range(HISTORY_DAYS - 1, -1, -1):
        d = (today - timedelta(days=offset)).isoformat()
        c = history["days"].get(d, {}).get(service_id)
        avg = round(c["latency_sum_ms"] / c["latency_n"]) if c and c["latency_n"] else None
        out.append({"date": d, "status": day_status(c), "avg_latency_ms": avg})
    return out


def uptime_percentage(history: dict, service_id: str) -> float | None:
    """Share of checks in the window that were not down. None before any check."""
    checks = down = 0
    for day in history["days"].values():
        c = day.get(service_id)
        if c:
            checks += c["checks"]
            down += c["down"]
    if checks == 0:
        return None
    return round(100 * (checks - down) / checks, 2)


def _error_code(exc: Exception) -> str | None:
    return getattr(exc, "response", {}).get("Error", {}).get("Code")


def load_history(s3, bucket: str, key: str) -> dict | None:
    """The stored history, an empty one if none exists yet, or None if unreadable.

    None -- a read that failed for any reason other than "no such key" -- means
    the caller must not write history back: an empty history written over a
    real one because of a transient error would erase 30 days of record.
    """
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except Exception as exc:  # botocore's ClientError, without importing botocore
        if _error_code(exc) in ("NoSuchKey", "404"):
            return empty_history()
        logger.error("could not read %s, history not updated this run: %s", key, exc)
        return None
    try:
        history = json.loads(body)
        if not isinstance(history.get("days"), dict):
            raise ValueError("no days object")
        return history
    except (ValueError, AttributeError) as exc:
        # Unreadable content will never become readable; start again rather
        # than fail every run from now on.
        logger.error("%s is corrupt, starting a new history: %s", key, exc)
        return empty_history()


# --- the run ------------------------------------------------------------------

def build_document(services: list[dict], history: dict | None, today: date) -> dict:
    document = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "overall_status": overall_status([s["status"] for s in services]),
        "services": services,
    }
    if history is not None:
        document["history_days"] = HISTORY_DAYS
        for s in services:
            s["uptime_percentage_30d"] = uptime_percentage(history, s["id"])
            s["daily_history"] = daily_history(history, s["id"], today)
    return document


def handler(event, context, s3_client=None, today: date | None = None):
    """Lambda entry point. `s3_client` and `today` are injectable for tests."""
    targets = json.loads(os.environ["TARGETS"])
    timeout = float(os.environ.get("TIMEOUT_S", "10"))
    bucket = os.environ["BUCKET"]
    key = os.environ.get("KEY", "status.json")
    history_key = os.environ.get("HISTORY_KEY", "status-history.json")
    today = today or datetime.now(timezone.utc).date()

    if s3_client is None:
        import boto3  # in the Lambda runtime; imported late so tests do not need it

        s3_client = boto3.client("s3")

    services = run_checks(targets, timeout)

    history = load_history(s3_client, bucket, history_key)
    if history is not None:
        record(history, services, today)
        s3_client.put_object(
            Bucket=bucket,
            Key=history_key,
            Body=json.dumps(history, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json",
            CacheControl="no-store",
        )

    document = build_document(services, history, today)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(document, indent=2).encode("utf-8"),
        ContentType="application/json",
        CacheControl=CACHE_CONTROL,
    )

    # One structured line per run: enough to graph or alarm on from Logs.
    logger.info(
        json.dumps(
            {
                "overall_status": document["overall_status"],
                "services": {
                    s["id"]: [s["status"], s["response_time_ms"], s["connect_ms"]] for s in services
                },
                "history_updated": history is not None,
            }
        )
    )
    return {"overall_status": document["overall_status"]}

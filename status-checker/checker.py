"""Synthetic checks for the projects travispollard.com links to.

Invoked by EventBridge every ten minutes (see ../status-checker.tf). For each
target it requests the URL, times the response to its headers, follows
redirects to the final status code, and reads the TLS certificate's expiry
over a separate connection. It writes the results to ``status.json`` in the
site bucket, which the /status page fetches.

Standard library plus boto3, which the Lambda Python runtime already ships,
so the deployment package is this one file.

Configuration, all from the environment (set by Terraform):
    TARGETS     JSON list of {"id", "name", "url"}
    BUCKET      the site bucket
    KEY         object key, default "status.json"
    TIMEOUT_S   per-request timeout in seconds, default 10

The thresholds below must match frontend/content/status.ts, which renders
what this decides; the names are the same so a grep finds both.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit

DEGRADED_LATENCY_MS = 1000

# The object is served through CloudFront's default behavior, whose cache
# policy honours the origin's Cache-Control and otherwise keeps an object
# for a day. 60 seconds bounds how stale the edge can be; the browser is
# told to revalidate by the distribution's response headers policy.
CACHE_CONTROL = "public, max-age=60"

USER_AGENT = "travispollard-status-checker/1.0 (+https://www.travispollard.com/status/)"

logger = logging.getLogger()
logger.setLevel(logging.INFO)


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


def cert_days_remaining(host: str, timeout: float) -> int | None:
    """Days left on the certificate `host` presents on 443, or None if unreadable."""
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
        return days_until(cert["notAfter"], time.time())
    except (OSError, ssl.SSLError, KeyError, ValueError) as exc:
        logger.warning("cert check failed for %s: %s", host, exc)
        return None


def check(target: dict, timeout: float) -> dict:
    """One synthetic check. Never raises: a failure is a result, not an exception."""
    url = target["url"]
    http_code: int | None = None
    response_time_ms: int | None = None
    error: str | None = None

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    started = time.perf_counter()
    try:
        # urlopen returns once the headers are in, after following redirects,
        # so this is time-to-headers of the final response.
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_time_ms = round((time.perf_counter() - started) * 1000)
            http_code = response.status
    except urllib.error.HTTPError as exc:
        # A 4xx/5xx is still a response: record it, and how long it took.
        response_time_ms = round((time.perf_counter() - started) * 1000)
        http_code = exc.code
        error = f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        error = f"request failed: {reason}"

    parts = urlsplit(url)
    cert_days = cert_days_remaining(parts.hostname, timeout) if parts.scheme == "https" else None

    result = {
        "id": target["id"],
        "name": target["name"],
        "url": url,
        "status": classify(http_code, response_time_ms, error),
        "http_code": http_code,
        "response_time_ms": response_time_ms,
        "cert_days_remaining": cert_days,
    }
    if error:
        result["error"] = error
    return result


def build_document(targets: list[dict], timeout: float) -> dict:
    """Check every target concurrently and assemble status.json."""
    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as pool:
        services = list(pool.map(lambda t: check(t, timeout), targets))
    return {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "overall_status": overall_status([s["status"] for s in services]),
        "services": services,
    }


def handler(event, context, s3_client=None):
    """Lambda entry point. `s3_client` is injectable for tests."""
    targets = json.loads(os.environ["TARGETS"])
    timeout = float(os.environ.get("TIMEOUT_S", "10"))
    bucket = os.environ["BUCKET"]
    key = os.environ.get("KEY", "status.json")

    document = build_document(targets, timeout)

    if s3_client is None:
        import boto3  # in the Lambda runtime; imported late so tests do not need it

        s3_client = boto3.client("s3")
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
                "services": {s["id"]: s["status"] for s in document["services"]},
            }
        )
    )
    return {"overall_status": document["overall_status"]}

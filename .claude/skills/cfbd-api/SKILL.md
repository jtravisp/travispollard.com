---
name: cfbd-api
description: Request, auth, quota and error-handling rules for the collegefootballdata.com REST API, and how they reconcile with this project's SPEC. Use when writing, debugging or reviewing any code that calls CFBD, handles a CFBD credential, or budgets CFBD calls.
---

# CFBD API

Base URL: `https://api.collegefootballdata.com`. Docs at
`https://api.collegefootballdata.com/getting-started`, `/authentication`, `/usage-and-access`.
Captured 2026-08-28; the vendor moves things, so treat everything below as needing a re-read if a
call starts behaving oddly.

## The scheme is HTTPS, and that is not a contradiction

Sagarin is pinned to HTTP because the site 302s HTTPS down to HTTP and a client that upgrades
loops forever (see the `sagarin-format` skill). **That rule is about Sagarin and nothing else.**
CFBD is a normal modern JSON API over TLS. Do not carry the HTTP pin across; a bearer token over
plaintext HTTP would put the credential on the wire.

## Authentication

One header, on every protected operation:

```http
Authorization: Bearer <key>
```

The space after `Bearer` is load-bearing — the vendor calls it out as the usual cause of a `401`
that looks like a bad key. If a request 401s, check the header shape before regenerating anything.

Request a free key at `https://collegefootballdata.com/key`.

### Where the key lives in this project

The vendor's docs say to `export CFBD_API_KEY=...`. **That is not how this project stores it.**
SPEC §5.5 is stricter and wins:

- The key lives in SSM at `/travispollard/cfb/cfbd_api_key` as a **SecureString**.
- CI reads it after assuming the publisher role via OIDC. Locally it is read with
  `AWS_PROFILE=tp-site` (account `679878703800`, us-east-1 — see SPEC §5.5; a similarly-named
  `jtravisp` profile points at a different account and fails by returning nothing).
- No API key in a GitHub secret. No `.env` file. Not in a URL, not in a browser-side request.

An environment variable is fine for a throwaway `curl` in a terminal you are looking at. It is not
where the pipeline gets its credential. Read from SSM, then build the header — the env var is the
vendor's default, not this project's storage.

A first request, for checking a key by hand:

```bash
curl --get 'https://api.collegefootballdata.com/games' \
  --data-urlencode 'year=2023' \
  --data-urlencode 'team=Michigan' \
  --header "Authorization: Bearer ${CFBD_API_KEY}"
```

## Quota: do not hardcode the number

`cfb/CLAUDE.md` and SPEC §5.1 both cite a 1,000 calls/month free tier. The current docs
deliberately refuse to state limits — the
[API tiers page](https://collegefootballdata.com/api-tiers) is the only source, "those details can
change, so they are not duplicated here." So **1,000 is a number this repo copied down once and the
vendor does not promise.** Do not write it into a runtime check.

What survives the number changing is the design SPEC §5.1 already has: a per-run hard cap
(`CALL_BUDGET_PER_RUN = 25`, the 26th call raises `CallBudgetExceeded`), enforced in our own
client, stateless, with no cross-run counter to race or leave wrong after a crash. That bounds the
month at cap × runs regardless of what the tier says this year.

The `info` operations in the API reference (`/api/info`) report account information and recent
usage. That is a better source for the real monthly figure than the Actions-log reconstruction
SPEC §5.1 describes, and it costs a call.

## Response codes, and the one the SPEC assumes that is not documented

The vendor documents these:

| Code | Meaning | What to do |
|---|---|---|
| `400` | Parameters, or their combination, not acceptable | Fix the request. Never retry unchanged |
| `401` | Not authorized | Check the `Bearer ` prefix first, then the key |
| `404` | Route or resource not found | Check the path and any identifiers |
| quota / entitlement | Account cannot complete that request | Check usage and current tier |
| `500` | Server failed a valid request | Retry later; contact support if it persists |

**`429` does not appear in that list.** SPEC §5.3 builds its whole retry path on it — "429 →
respect `Retry-After` when present, otherwise backoff 5s / 20s / 60s". The current docs describe
the over-quota case only as "a quota or entitlement response" without naming a status. So the
retry logic keys on a code the vendor no longer confirms. Do not assume it is absent either; the
safe implementation handles `429` *and* treats an unrecognised quota response as non-retryable
rather than hammering it. Verify against a real response before trusting either branch.

Per SPEC §4.1 and §5.3: do not retry `4xx`. `5xx` retries with backoff; exhausted attempts raise
`FetchError` and the run goes red. CFBD history is backfillable, so a lost Sunday is an
inconvenience, not a hole — which is exactly why it is not worth retrying hard enough to burn the
budget.

## What this project actually calls

From SPEC §5.2 — about 2 calls per in-season week:

| Call | Frequency | Snapshot partition |
|---|---|---|
| `/calendar?year=2026` | once per season | `week=season/calendar/` |
| `/teams/fbs?year=2026` | once per season | `week=season/teams/` |
| `/games?year=2026&week=N` | weekly | `week=NN/games/` |
| `/lines?year=2026&week=N` | weekly | `week=NN/lines/` |

`/calendar?year=2026` is the one currently blocking work: `cfb/data/calendar/2026.json` is
committed from it once per season and every run resolves locally from that file (SPEC §3.1).
`tests/fixtures/calendar_2026_synthetic.json` stands in for it until the key exists.

## Client choice

There are official Python and TypeScript packages. **Use raw HTTP (httpx) anyway.** SPEC §5.1
requires the call budget to be enforced *in the client*, and a vendor package that makes its own
requests is a budget guard with a hole in it. The bearer contract is one header; the packages are
not buying much here.

## Rules that do not bend

- **Never call CFBD from a test.** `cfb/CLAUDE.md`, and it is absolute — every call costs quota
  that a scheduled run needs. Fixtures only.
- **Snapshot before parsing.** Raw JSON to `raw/cfbd/...` before anything reads it, same as
  Sagarin. Never parse-and-discard.
- **Every invocation fetches for real** (SPEC §5.4). No caching, no "reuse today's copy". Re-parsing
  an existing snapshot is `cfb replay`, which touches no network.
- **An unmapped team name is an error.** Reconciling CFBD names against Sagarin names is the
  crosswalk's job (SPEC §6); no fuzzy matching, no defaults.

## When the docs here are not enough

The [legacy Swagger UI](https://api.collegefootballdata.com/swagger) is still up during the
transition and is the fastest way to see an operation's exact response shape. The new API
reference has a playground that sends live requests — note that **playground requests count
against usage** exactly like any other client, so do not explore with a key whose quota the
pipeline depends on.

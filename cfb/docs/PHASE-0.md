# Phase 0 — the collector

**Goal:** both sources fetched on a schedule, raw snapshots landing in S3, the Sagarin parser passing contract tests, and the crosswalk covering every FBS team.

**No modeling. No pages. No predictions.**

**Why first:** CFBD history can be backfilled at any time. Sagarin's page shows current ratings only — once a week rolls over, that snapshot is gone permanently. Every week without a collector is an unrecoverable hole in a dataset whose whole value is that nobody else has it.

**Done when:** a scheduled run has completed unattended, twice, and `data/raw/` contains snapshots nobody touched by hand.

---

## Where this stands (2026-08-28)

Every module SPEC §1 plans except the crosswalk now exists, both sources have been fetched for
real, and **the stack is applied**. `cfb/terraform` created the data bucket, the publisher role and
the account's GitHub OIDC provider; both collectors then wrote to the real bucket from this machine,
and the full `SnapshotStore` contract passed against S3 rather than skipping. The three §11
workflows are merged and **all three have run**: CI green on the PR, and both collect workflows
dispatched successfully with the publisher role assumed by GitHub Actions rather than by a human.
`cfb-sagarin.yml` wrote a snapshot to the real bucket from CI.

| | |
|---|---|
| Tests | 521 passing, 18 skipped, 2 failing **by design** — the crosswalk coverage tests are the worklist for the 32 undecided names; `ruff check .` clean |
| Landed | `2fa6833..4db2934`. PR #43 merged to `main`; the workflows have run |
| Uncommitted | nothing. `cfb/docs/PRD.md` carries unrelated edits that predate this work and are deliberately left alone |
| Next | the 32 crosswalk decisions (yours), then the two unattended scheduled runs that Phase 0 is "done when" |
| Blocked on a human | an in-season Sagarin capture, the 32 crosswalk decisions — see the bottom of this file |

Re-verified 2026-08-28 by running, in `cfb/`:

| Command | Result |
|---|---|
| `uv run pytest` | `460 passed, 16 skipped in 3.4s` |
| `uv run ruff check .` | `All checks passed!` |
| `terraform -chdir=terraform validate` | `Success! The configuration is valid.` |
| `uv run cfb fetch sagarin --store file://./local-snapshots` | exit 0, `sha256 ba40d836…`, 148793 bytes — the §4.7 hash |
| `uv run cfb fetch cfbd --resource calendar --season 2026` | exit 0, 16 entries, `sha256 94f31795…` |
| `uv run cfb fetch cfbd --resource teams --season 2026` | exit 0, 138 FBS teams, `sha256 15611e4d…` |

Every `[x]` below is backed by one of those four. The rule that decides the marks: a module with
exhaustive offline tests and no live run is `[~]`, not `[x]`. As of today exactly one path has
cleared that bar — the Sagarin fetch — and **nothing has been applied to AWS**, so every item that
needs a bucket, a role or a credential stays `[~]` regardless of how complete the code reads.

Where they sit. The counts are tests *collected*, so they total 476: the 16 that skip are the
S3 parametrization in `test_storage.py`, which needs `CFB_INTEGRATION=1` and a bucket.

| File | Tests | Covers |
|---|---|---|
| `test_cli.py` | 83 | SPEC §8's four commands and §9's error contract |
| `test_storage.py` | 48 | the `SnapshotStore` contract, over three stores (16 skip without AWS) |
| `test_sagarin_fetch.py` | 46 | SPEC §4.1, via `httpx.MockTransport` |
| `test_cfbd.py` | 42 | SPEC §5.1 and §5.3 — budget, both retry ladders |
| `test_manifest.py` | 42 | key construction, SPEC §2.1 and §3.2 |
| `test_sagarin_parser.py` | 40 | the ratings table and the date stamp |
| `test_calendar.py` | 64 | season/week resolution, SPEC §3 — every test over both calendars |
| `test_sagarin_predictions.py` | 30 | the predictions block |
| `test_freshness.py` | 22 | SPEC §4.6, skip paths in full |
| `test_cfbd_auth.py` | 20 | SPEC §5.5 — the bearer header, and that the key never leaks |
| `test_roster_fixtures.py` | 8 | the §6.5 roster contract, as far as it can run without §6 |
| `test_validation_boundary.py` | 20 | SPEC §9's `ValidationError`, at every model boundary |
| `test_models.py` | 11 | the `SagarinSnapshot` validators |

### How much of SPEC §1 exists

Everything except the crosswalk:

```
src/cfb/  __init__.py  calendar.py  cli.py  errors.py  logging.py  manifest.py  models.py
          storage.py   collectors/{sagarin,cfbd}.py    parsers/{sagarin_ratings,sagarin_predictions}.py
```

Absent: `crosswalk/` (both `__init__.py` and `bootstrap.py`), which is §6 and blocks step 5 of
§4.3. `pyproject.toml` now registers the `cfb` console script; it was deliberately absent until
`cli.py` existed, because an entry point naming a missing module breaks `uv sync` itself.

The exception hierarchy is no longer the illustration it was. `errors.py` declares twelve and ten
are now raised somewhere: `ParseError` (26 sites), `WeekResolutionError` (8), `FetchError` (7),
`SnapshotExistsError` and `SnapshotNotFoundError` (6 between them, through the `_exists` /
`_missing` factories), `DuplicateRankError` (3), and one each for `EncodingError`,
`StaleSourceError` and `CallBudgetExceeded`.

One is still declared and unused: `UnmappedTeamError` belongs to `crosswalk/`, which does not
exist. Expected.

`ValidationError` was the other, and it is now used. §9 specifies it as the one that "wraps
pydantic" and nothing wrapped anything, so a model failure escaped as `pydantic_core.ValidationError`
— which is not a `CfbError`, misses the CLI's exit-1 clause entirely, and surfaces as a traceback.
`models.validating()` wraps it at every model boundary: both parsers, the snapshot, both manifest
builds, and the three `list_manifests` implementations.

---

## 1. Repo groundwork

- [~] Delete or archive `www/` — deferred by decision (SPEC §12); the root `CLAUDE.md` marks it dead
- [~] Create `cfb/` with `src/`, `tests/`, `data/`, `terraform/`, `scripts/`, `docs/` — all exist except `data/`, which stays empty until the two committed files below have been generated
- [x] Add `cfb/CLAUDE.md`
- [x] Add `.claude/skills/sagarin-format/SKILL.md` at repo root
- [x] Python project scaffolding (uv, ruff, pytest) — `pyproject.toml`, Python 3.12, `src/cfb/` layout via hatchling, pydantic. No `cfb` console script yet: `cli.py` does not exist, and registering an entry point to a missing module breaks the install
- [x] Root `CLAUDE.md` via `/init`, then pruned

## 2. Golden fixture and tests — before any parser code

Written 2026-08-27, before any parser existed. All 26 ratings tests failed then with
`ModuleNotFoundError: No module named 'cfb'` — the intended red. Checked at the time against a
deliberately naive strawman parser (whole-page regex, no section stop, hardcoded HFA, silent skip
on bad rows): 11 failed on real parsed values, 15 passed. The assertions bite; they are not
passing vacuously.

They now pass against a real parser (§3). The suite is 64 tests: 26 ratings, 30 predictions,
8 snapshot-model.

What the golden capture actually contains — including three traps the skill did not document —
is recorded in SPEC §4.7.

- [x] Save the 2026 preseason page as `tests/fixtures/sagarin_2026_preseason.txt`
- [x] Test: parses exactly the section-1 team count, no duplicates from section 3
- [x] Test: names with spaces, apostrophes, ampersands, and parens survive intact
- [x] Test: duplicate rating values with distinct ranks do not collide
- [x] Test: duplicate ranks raise
- [x] Test: home-field advantage is captured from the page, not constant
- [x] Test: preseason degenerate state parses and is flagged
- [x] Test: FCS teams present and marked
- [x] Test: malformed row raises rather than returning None

Added beyond the list above, from traps found in the real capture:

- [x] Test: conference-average rows and the `***UNRATED***` sentinel are not parsed as teams
- [x] Test: conference is captured per row
- [x] Test: the preseason page carries no internal date stamp

Added since:

- [x] `tests/test_sagarin_predictions.py` — 30 tests. The predictions block is printed **twice**
      (regular, then EXPERIMENTAL), the same duplication trap as section 3. Verified live rather
      than assumed: a whole-page match returns 106 games where the answer is 53
- [x] `tests/test_models.py` — 11 tests over the `SagarinSnapshot` validators. They duplicate
      checks the parsers already make, which is the point (SPEC §4.7 "defence in depth"), but an
      untested defence is not a defence

Still open in this section:

- [ ] An in-season golden page — nothing can test the date stamp, the in-season title flag, or
      freshness until one exists. Two pieces of shipped code are unverified against real bytes
      because of it: the "through games of …" date parsing in `parse_page_date_stamp`, whose
      format list is a guess, and the `"in-season"` branch of `parse_page_state`
  - **The gate is the title line, not a week number.** `parse_page_state` (`sagarin_ratings.py:285`)
    keys on one substring: `STARTING`. Nothing in this project reads a week number off the page.
    So the fixture is capturable the first time the page drops `STARTING`, which is after the
    first games are played — not week 4. The earlier `sagarin_2026_week04.txt` name asserted a
    schedule the code never required; name captures by capture date instead, and let the page's
    own "through games of" stamp say which week it covers

## 3. Sagarin collector

- [x] Fetch with scheme pinned to HTTP, no upgrade
  - Written. `fetch_page()` in `collectors/sagarin.py`: URL pinned, `follow_redirects=False`, 30s
    connect and read, retry on timeout / connection error / 5xx and never on 4xx or 3xx.
    `fetch_sagarin`'s `fetch` argument now defaults to it, so the seam survives for tests and
    production gets a real fetcher. `httpx` is a base dependency
  - 46 tests in `tests/test_sagarin_fetch.py` drive it through `httpx.MockTransport`, which sits
    below the client so the redirect policy, the timeout and the request count are observed rather
    than stubbed. Every 3xx to HTTPS raises with exactly one request issued — the https branch of
    the handler answers a plausible 200 on purpose, so a fetcher that followed it would return
    those bytes instead of raising
  - **Run for real 2026-08-28**, which is what moved this to `[x]`:
    `cfb fetch sagarin --store file://./local-snapshots` fetched the live page over plain HTTP and
    stored 148,793 bytes hashing to `ba40d836…` — the golden fixture's sha256 from §4.7, captured
    by hand the day before. The fetcher reproduces a known-good capture byte for byte
  - One branch of it is still synthetic. The scheme pin exists because sagarin.com 302s HTTPS down
    to HTTP, and the live request went straight to HTTP and got a 200, so no run in this repo has
    ever seen that 302. The redirect refusal is asserted only against a transport we wrote
- [x] Encoding sniff, raise on failure — `decode_page()` in `collectors/sagarin.py`. SPEC §4.2
      order (`utf-8`, `cp1252`, `latin-1`), first candidate that decodes **and** contains both
      markers wins, `EncodingError` when none qualifies. The golden capture resolves to `utf-8`
      because it happens to be pure ASCII, exactly as SPEC §4.7 predicts
- [x] Write raw bytes to `s3://<bucket>/raw/sagarin/<date>/` before parsing
  - The code is complete and the ordering is the tested part: `fetch_sagarin` writes bytes at step
    2 of SPEC §4.3, before anything parses them, and the §3.3 suite asserts the bytes survive a
    resolution failure rather than merely that the run went red
  - **Applied and written to for real, 2026-08-28.** `uv run cfb fetch sagarin` and
    `uv run cfb fetch cfbd --resource calendar --season 2026` both defaulted to the `s3://` store
    and landed objects:

    ```
    raw/cfbd/season=2026/week=season/calendar/2026-08-28T165019Z.json        3386
    raw/cfbd/season=2026/week=season/calendar/2026-08-28T165019Z.meta.json    635
    raw/sagarin/season=2026/week=preseason/2026-08-28T165010Z.txt          148793
    raw/sagarin/season=2026/week=preseason/2026-08-28T165010Z.meta.json       751
    ```

    `week=preseason` rather than `week=unknown`, so the committed calendar is resolving. And
    `uv run pytest tests/test_storage.py` reported **48 passed** — all 48, none skipped, in 30s —
    which means the S3 parametrization ran against the real bucket rather than skipping. The
    `SnapshotStore` contract now holds against S3 and not only against memory and disk
  - [x] `tests/test_storage.py` — the `SnapshotStore` contract, 16 assertions parametrized over
        three stores. Verified 2026-08-28 against a throwaway implementation written outside the
        repo and deleted immediately: **32 passed, 16 skipped** (memory and file run; the S3
        parametrization skips without `CFB_INTEGRATION=1` and `CFB_TEST_BUCKET`). Tests only —
        no implementation landed
  - [x] Implemented 2026-08-28. `uv run pytest` with `CFB_INTEGRATION` unset:
        **`96 passed, 16 skipped in 0.82s`**; `uv run ruff check .` → `All checks passed!`
        Nothing under `cfb/tests/` was touched
    - `errors.py`: `SnapshotExistsError` and `SnapshotNotFoundError`, placed between
      `EncodingError` and `ParseError` so the hierarchy reads in the order of operations of
      SPEC §4.3. First additions since §9 landed, and SPEC §9 was updated in the same commit
    - `models.py`: `Manifest`, strict and frozen like its neighbours, `extra="forbid"` with the
      post-parse fields declared optional — a fetch-only manifest is `parse_ok=None`, not invalid.
      A validator rejects a `week` that is not a SPEC §3.2 partition value, because `week` reaches
      S3 as a literal path segment and a stray `"4"` where `"04"` belongs silently opens a second
      partition for the same week
    - `storage.py`: the `SnapshotStore` Protocol plus all three implementations. `put_bytes` on S3
      is a conditional write (`IfNoneMatch="*"`), not head-then-put: two runs racing on one key
      would both see it absent and the loser would clobber the winner
  - **Module ownership decided:** `Manifest` lives in `models.py`, not `manifest.py`. SPEC §1 said
    "manifest models, key construction" for `manifest.py`; it now reads "key construction, the
    two-phase manifest build (§4.3)" and `models.py` lists `Manifest`. Rationale: `models.py` is
    the one place every pydantic schema lives and every one is validated at a boundary, which is
    exactly what `list_manifests` does to bytes out of the bucket. Splitting schemas across two
    modules gives "where is the model for X" two answers. `manifest.py` keeps real work — key
    construction and the step 3 / step 6 builders — the same schema/behaviour split the package
    already uses for `models.py` and `parsers/`
  - boto3 is an optional extra (`uv sync --extra s3`), not a base dependency, and `storage.py`
    imports it inside `S3SnapshotStore.__init__`. Verified: `boto3 installed: False` in the
    default environment, and `from cfb.storage import S3SnapshotStore` still succeeds. The offline
    suite installs neither boto3 nor botocore
  - Two contract points the suite takes from the spec over the intuitive reading, both worth
    re-reading before implementing:
    - Write-once is a property of `put_bytes` alone. `put_json` **must permit** rewriting a
      manifest key — SPEC §2.2 and steps 3 and 6 of §4.3 write the same `.meta.json` twice on
      every successful run. A store that refused it could not execute the normal path
    - `list_manifests` orders by `fetched_at`, not by key (SPEC §2.3 "newest first by
      fetched_at"). The suite's fixture deliberately reverses the two orders so a store that
      sorts by key fails
  - Deliberate, narrow deviation from `cfb/CLAUDE.md`'s "no network calls in tests, ever": the S3
    parametrization can reach AWS, but only when two env vars are set, so a bare `uv run pytest`
    is still fully offline. Its objects go under a `test/` prefix, never `raw/` — the publisher
    role is denied `s3:DeleteObject`, so an integration run cannot clean up after itself and
    would otherwise leave permanent garbage in the immutable prefix
- [x] Parser passing all tests from step 2 — `parsers/sagarin_ratings.py`. Section 1 only, anchored
      on the `=` and `|` tokens; rank is the identity; HFA read per column from the page; a bad row,
      an unrecognised line, a duplicate rank, or a gap in the rank sequence all raise
- [x] Parse the `Predictions_with_Totals_and_Moneylines` section — `parsers/sagarin_predictions.py`.
      First block only. The `@` marks the nominal home team; a row marking neither side or both
      raises, because a misread `@` silently inverts a prediction
- [~] Freshness check: internal date stamp advanced since last snapshot
  - Written. `check_freshness()` in `collectors/sagarin.py`, 22 tests in `tests/test_freshness.py`.
    Two of the three original blockers are gone: `storage.py` exists, and the skip paths turned out
    to be the testable half all along
  - **The skip paths are covered in full, and they are the ones that fail silently.** A skip that
    should have been a raise is byte-identical to a healthy run from outside the process — same
    exit code, same green workflow, nothing written — so each one logs a machine-readable reason
    and the tests assert on it. Covered: no prior-date manifest, a null stamp on either side,
    same-day manifests ignored, off-season, an unreadable calendar, and the day-with-no-fetch case
    where a naive reading of §4.6 compares the newest snapshot against itself and raises a **false**
    stale alert
  - Still `[~]` because the comparison itself — stamp advanced, stamp unchanged — runs against a
    synthetic in-season page: the golden capture with its title line rewritten, so an in-season
    title sits over preseason data. That drives a real stamp through the real parser into a real
    manifest, which is all §4.6 reads, and it is not evidence about the real stamp format. Those
    two assertions are marked PROVISIONAL in the test file and close when §2's capture lands

**Deviation from SPEC §4.5 to note:** `GamePrediction` carries seven fields, not the five the spec
lists. The additions are `rank` (the row's only stable identity, and rank is the join key
everywhere else in this project) and `site` — the `N`/`C` flag after the rank, which moves the
home/away split columns, so it changes what `home` means. A classic gets a partial home edge
(26.60/25.40 on the preseason page) and a neutral gets none (26.00/26.00): three states, not a
bool. Also unverifiable until an in-season page lands: `predicted_margin` is the PREDICTOR column
signed from the home team's perspective. The row supplies five spread columns and the model has
one field, and SPEC §4.4 names PREDICTOR as the benchmark — but all five are identical in the
preseason, so nothing distinguishes them empirically yet.

This one does *not* clear on the same schedule as the other three. The title flag, the date stamp
and the `"in-season"` branch all flip the moment any games are played. The columns only separate
for teams that have actually played, and they separate by an amount proportional to how much
result data has displaced the preseason prior. On the first in-season page most of the 266 teams
are still 0-0 and still degenerate, and the predictions block is computed off ratings that are
almost entirely prior. So: capture the page anyway — it unblocks the other three — but check the
specific rows an assertion would target before closing this item. If PREDICTOR still agrees with
its neighbours on those rows, the fixture has not settled anything and the item stays open.

### Season/week resolution and key construction — tests written 2026-08-28

Tests only, no implementation, per the session scope. `uv run pytest` now reports
`96 passed, 16 skipped, 2 errors` — the two errors are `test_calendar.py` and `test_manifest.py`
failing at collection on `No module named 'cfb.calendar'` / `'cfb.manifest'`. **58 assertions are
waiting**: 31 in `test_calendar.py`, 27 in `test_manifest.py`.

- [x] `tests/fixtures/calendar_2026_synthetic.json` — a hand-built calendar in the CFBD
      `/calendar` shape, 16 entries: fifteen regular weeks a week apart from 2026-08-29, plus one
      postseason entry running 2026-12-19 to 2027-01-11. Stands in for `data/calendar/2026.json`,
      which is still blocked on a CFBD key. Broken variants (truncated, malformed, wrong season,
      empty) are built by mutating it in memory, following the `test_models.py` idiom
- [x] Every SPEC §3.2 partition value is covered: `preseason`, `01`–`15`, `postseason`,
      `offseason` and `unknown` in `test_calendar.py`; `season` in `test_manifest.py`, because it
      comes from what is being fetched rather than from when, and no date resolves to it
- [x] SPEC §3.3 — seven tests. The class asserts what *survives* the failure, not just that it
      failed: an implementation that resolves first, raises, and never fetches satisfies "the run
      exits non-zero" perfectly while destroying the thing the run exists to collect. So each test
      that expects the raise also asserts the bytes are in the store, the key is partitioned under
      `week=unknown`, and `week_resolution` reads `"unknown"` so a later re-partition sweep can
      find it. One control test proves a resolvable run still lands under `week=04`
- [x] `calendar.py` — `load_calendar`, `resolve`, `in_season`
- [x] `manifest.py` — `snapshot_key`, `manifest_key`
- [x] `collectors/sagarin.py` — `fetch_sagarin`, `decode_page`

Implemented 2026-08-28. `uv run pytest` with `CFB_INTEGRATION` unset:
**`154 passed, 16 skipped in 1.07s`**, no collection errors. `uv run ruff check .` →
`All checks passed!` All four decisions are recorded in SPEC §1, §3.1, §5.1, §5.3 and §8; nothing
under `cfb/tests/` was touched.

An end-to-end run against the golden capture writes a manifest whose counts match SPEC §4.7
independently — `team_count` 266, `fbs_count` 138, `predictions_count` 53, `sha256`
`ba40d836…`, `page_state` `preseason`, `page_date_stamp` null — and the stored bytes compare equal
to the fixture.

**Still not wired, and the collector docstring says so at the top:**

- Step 5 of SPEC §4.3, crosswalk resolution. `crosswalk/` does not exist. `unmapped` is therefore
  omitted from **both** manifest writes rather than written as `[]`; an empty list would claim
  every name resolved, which is a stronger statement than "nothing checked"
- `http_status` is written as `200` without a status line ever being read. Defensible — SPEC §4.1
  makes any non-2xx a `FetchError` inside the fetcher, so bytes reaching `fetch_sagarin` are by
  construction a 200 — but the field records an inference from control flow rather than an
  observation. That is now stated in SPEC §2.2 rather than only here, along with the fix: widen
  the seam to return the response instead of bytes. The CFBD collector writes the same field the
  same way, for the same reason

Two entries that used to sit here have closed. **Step 7, the freshness check**, is written and
tested — see the item above. **The `hfa` five-vs-four gap** is gone: SPEC §2.2's example manifest
now names all five columns `parse_hfa` captures, and §4.7's back-reference went with it.

**A design decision the tests encode, derived rather than stated.** `resolve()` does not raise on a
date it cannot place; it returns `WeekRef(week="unknown", how="unknown")`. SPEC §2.2 types
`week_resolution` as `"calendar" | "unknown"`, and `"unknown"` could never appear if resolution
raised instead of returning. `load_calendar` still raises `WeekResolutionError` on a missing or
malformed file, and the collector still owes the non-zero exit — after the write. This is the one
documented departure from "validation failures raise", and §3.3 carves it out explicitly.

## 4. CFBD collector

**Two real calls have now been made.** `/calendar?year=2026` and `/teams/fbs?year=2026`
both succeeded on 2026-08-28, which is the first time any code in this repo has
authenticated to CFBD. That closes the credential item outright and moves the pull
item halfway. The rest stays `[~]`: the retry ladders have still never seen a real
non-2xx, and every byte so far went to `file://`, not to a bucket that does not
exist.

- [x] API key in SSM, not env files
  - `ssm_secret()` reads the SecureString at `/travispollard/cfb/cfbd_api_key`
    with `WithDecryption=True`, and `http_fetch()` turns whatever it returns into
    `Authorization: Bearer <key>`. The key source is an injected `get_secret`
    callable, so the header-building half is exercised offline —
    `tests/test_cfbd_auth.py`, 20 tests
  - Covered: the header shape (the space after `Bearer` is what the vendor names
    as the usual cause of a 401 that looks like a bad key); a trailing newline
    stripped, because a SecureString set from a file keeps one; a blank key
    refusing to send rather than spending a request to earn a 401; the key never
    appearing in a log line, an exception, a `repr`, or a query string; the secret
    read once per run rather than per request, and never at construction, so
    `cfb --help` needs no credentials
  - **The scheme pin is inverted from Sagarin's, deliberately.** `fetch_page` pins
    to plain HTTP because sagarin.com 302s HTTPS down to HTTP. Carrying that
    across would put a bearer token on the wire in the clear, so `http_fetch`
    refuses to send at all if the base URL is ever not https — a refused request
    costs a Sunday CFBD can backfill, a transmitted key costs a rotation
  - **Verified for real 2026-08-28.** The key is in SSM and `ssm_secret` read it
    twice — once per call below — decrypted it, and the resulting bearer header
    was accepted by CFBD. That is the one function on this path no offline test
    can cover, and the only thing that was ever going to settle it is a 200. Its
    docstring still says it is untested, which remains true of the *test suite*
    and no longer of the code
  - The key never entered this repo, a shell history, or a conversation: it went
    into SSM directly from a file, which is also the case the whitespace-stripping
    test exists for
- [~] Incremental sync with a call-budget guard
  - **Two things, and only one of them is done.** The guard is complete: a per-run
    cap of 25 enforced inside the client, checked before each request, retries
    included, with no cross-run state to race or be left wrong by a crash. 42
    tests in `tests/test_cfbd.py`, and the budget assertions are written against
    what the seam actually saw rather than what the client says it did — three
    mutations confirmed they catch a guard that counts after sending, one that
    lets retries through free, and a process-wide counter
  - **Incremental sync is not written.** `fetch_cfbd` pulls exactly the resource
    and week it is told to; nothing works out which weeks are already in the
    bucket and syncs forward. SPEC 5.2 describes the cadence and SPEC 5.4 forbids
    caching, but the "which week just completed" logic lives in the workflow that
    does not exist yet (§7). This checkbox conflates the two and should probably
    be split
  - The guard has now run for real, twice, and spent 2 of its 25. Nothing about
    that was in doubt, but it is no longer only a claim about a mock
- [~] Backoff on 429
  - `Retry-After` is honoured when it parses as positive seconds, and the ladder
    is the fallback — including for the legal HTTP-date form, which this client
    does not parse and falls back on rather than guessing
  - 429 gets its own ladder (5/20) rather than sharing the 5xx one (2/8), because
    a 429 is the server asking for room and a 5xx is the server failing. A test
    fails if the two are ever merged
  - Both stop at three requests, the initial one plus two retries. That number is
    arithmetic, not taste: at 25 requests a run and ~2 per in-season week, a
    four-request ladder would make retries a larger share of the budget than the
    data
  - `[~]` because no real non-2xx of any kind has been seen. Both real calls
    returned 200 on the first request, so not one line of the retry, backoff or
    error-logging path has executed against the vendor. Every response these tests
    classify was written by us — and the status that actually means "over quota"
    is one the vendor has stopped documenting, so the first real one may not be a
    429 at all. That is exactly why the body of every non-2xx is logged
- [x] Raw JSON to `s3://<bucket>/raw/cfbd/<date>/`
  - `fetch_cfbd` stores the bytes verbatim under
    `raw/cfbd/season=YYYY/week=NN/<resource>/<timestamp>.json` with a `.meta.json`
    beside it, and writes nothing at all when the pull fails — asserted for both
    an exhausted retry and a budget refusal, because `raw/` is write-once and a
    truncated object at the right key is permanent
  - **Reached S3 on 2026-08-28**, alongside the Sagarin write — see §3. `fetch cfbd --resource
    calendar` with no `--store` defaulted to the bucket and landed the JSON and its manifest under
    `week=season/calendar/`
  - One field is weaker than it looks. `week_resolution` reads `"calendar"` on a
    CFBD manifest, but the week came from the CLI rather than from resolving a
    date. SPEC 2.2 allows only `"calendar"` or `"unknown"` and `"calendar"` is the
    closer of the two — it is known, not guessed — so the field now means
    something slightly different for CFBD than for Sagarin. Worth a spec decision
- [~] Pull: teams, games, betting lines
  - All four SPEC 5.2 resources are wired and reachable from the CLI:
    `/games` and `/lines` week-scoped, `/teams/fbs` and `/calendar` season-scoped
    under the `week=season` partition. An unknown resource is an argparse usage
    error rather than a request that finds out from the vendor at the cost of
    quota
  - **Two of the four pulled for real 2026-08-28**, both landing under
    `week=season` with a manifest beside them: `/calendar` (3,386 bytes, sha256
    `94f31795…`) and `/teams/fbs` (202,966 bytes, sha256 `15611e4d…`)
  - `/games` and `/lines` are the two still `[ ]` in substance. Both are
    week-scoped and there is no completed week yet — the season opens 2026-08-29 —
    so the first meaningful pull is the Sunday after week 1
  - The two that ran were the two worth running first. `/calendar` generated
    `data/calendar/2026.json`, which is what stops the Sagarin fetch filing under
    `week=unknown`; `/teams/fbs` generated
    `tests/fixtures/rosters/cfbd-2026.json`, the CFBD half of the §6.5 contract

## 5. Crosswalk

**The FCS question is settled and it changed the shape of this section.** SPEC §6.5's "every Sagarin
name resolves" was unsatisfiable as written: Sagarin rates 266 teams, 128 of them FCS, and
`/teams/fbs` returns none. Scoping the crosswalk to FBS-only does not rescue it — `/games` returns
FCS opponents by CFBD name, so the first FBS-vs-FCS game of September needs the join or the game
vanishes. The season pull is now `/teams?year=2026` and the crosswalk spans both divisions.

- [x] Generate the initial mapping from both sources — `uv run cfb crosswalk bootstrap --season 2026`
      writes 234 exact matches to `data/crosswalk/teams-2026.yaml` and ranks the other 32 in
      `_candidates-2026.yaml`
  - Both roster fixtures are 266 rows and their two 128s were counted independently by two vendors
    who do not talk to each other — the best evidence available that neither side drops rows
  - Similarity scoring orders the 32 and decides none of them (SPEC §6.3). `"Southern California" ~
    USC` scores 0.09, so any threshold low enough to catch it would map half the FCS by accident
- [x] Store as a versioned data file, not code — YAML, one file per season, canonical slug as the
      key. `cfbd_id` rides along and a test checks it against the roster, so an id pasted from the
      wrong row is caught rather than trusted
- [~] Test: every FBS team in either source resolves — **the two coverage tests fail by design until
      the 32 are decided**, and their failure message is the worklist. SPEC §6.4's fix loop ends
      "Then: `uv run pytest cfb/tests/test_crosswalk.py`", so a red run here *is* the interface. The
      other 18 crosswalk tests pass
- [x] Test: an unknown name raises — plus five near-miss cases (`ohio state`, `Ohio  State`,
      leading/trailing space, `OhioState`) that must raise rather than be normalized. Every one is a
      plausible typo *and* a plausible vendor rename; absorbing them silently means the day CFBD
      really renames a team, nobody learns the mapping is wrong
- [x] Bootstrap quarantined from the runtime (SPEC §6.3) — asserted three ways: importing each
      data-path module and checking `bootstrap` did not come with it, grepping those modules for an
      import of it, and asserting the CLI's own import is function-local. The CLI is the one
      sanctioned caller

**Left for a human: the 32 decisions in `data/crosswalk/_candidates-2026.yaml`.** Each carries the
four closest unclaimed CFBD names with scores. Some are near-misses a threshold would catch
(`'Appalachian State'` ~ `'App State'`, 0.69); some are not (`'Central Florida(UCF)'`,
`'Southern California'`) and need someone who knows what those teams are called.

## 6. Infrastructure

- [x] `cfb/terraform/` root with its own backend and state — **applied 2026-08-28.** State in
      `travispollard.com-tf-state` (us-west-2, key `cfb/terraform.tfstate`); the plan it matched was
      8 to add, 0 to change, 0 to destroy, and is kept below for the record
  - **Provider drift closed, and it was not what the earlier note said.** This file previously
    recorded "resolves 5.100.0", and the diagnosis offered this session was a *missing* cfb
    lockfile. Both wrong: `cfb/terraform/.terraform.lock.hcl` was tracked all along, pinned to
    **5.100.0** against the root's **5.82.2**, and it carried hashes for **one platform only**
    (windows_amd64). Two real defects in one file — a version the root does not use, and a lockfile
    that would fail `init` on Linux CI with a missing checksum
  - Regenerated with `terraform providers lock -platform=windows_amd64 -platform=linux_amd64`,
    now `5.82.2` with both platforms, byte-identical to the root on `version` and `constraints`.
    Neither `required_providers` block changed: both said `~> 5.0` already, so the constraint was
    never the problem
- [x] Data bucket, private, versioned — applied. Versioning, public access block, `raw/` lifecycle
      to STANDARD_IA at 90 days, no `s3:DeleteObject` on `raw/`. Holds four real objects and passed
      the full `SnapshotStore` contract against S3 (§3)
- [x] Reads distribution ARN from SSM — **resolved for real during the plan**:
      `data.aws_ssm_parameter.cdn_distribution_arn: Read complete [id=/travispollard/cdn/distribution_arn]`.
      The parameter exists in `679878703800`, so the root stack's `cfb-wiring.tf` has been applied
      at some point — this file said it never had, which was wrong. The apply-order constraint
      (root, then cfb) is therefore already satisfied and no longer blocks the cfb apply
- [x] GitHub OIDC publisher role — applied, with the OIDC provider it depends on.
      **Not yet assumed by anything but a human**: that happens on the first workflow run (§7). `github_repo` default
      corrected to `jtravisp/travispollard.com`; the previous value was an org that does not exist,
      so the trust condition would never have matched and every scheduled run would have failed to
      assume the role
  - **`cfb/terraform` now creates the OIDC provider rather than looking it up.** SPEC §10.1 asserted
    it already existed in the account; `aws iam list-open-id-connect-providers --profile tp-site`
    returns an empty list, so the `data` source could never have resolved and the role could never
    have been created. Now a `resource` — `client_id_list = ["sts.amazonaws.com"]`, no
    `thumbprint_list`, which `validate` and `plan` both accept
  - **It is account-scoped, not cfb-scoped**, and that is the one thing to remember about it. An
    account holds exactly one provider per issuer URL, so a second root creating its own is an
    error rather than a merge. `cfb` owns it because `cfb` is the only consumer today; when a
    second appears it moves to a shared root and both read it back as a data source (SPEC §10.1)
- [ ] Root Terraform: parameterize `modules/cloudfront` for extra origins — deferred to Phase 1
      (SPEC §10.2). There is no JSON to serve yet
- [~] Root Terraform: `/cfb/data/*` behavior, SSM outputs — the two `aws_ssm_parameter` resources
      are written and the root validates with them. The `/cfb/data/*` behavior and its OAC are
      commented out in `cfb-wiring.tf` for Phase 1: left live, the OAC would be created on the next
      root apply, ahead of the behavior that uses it. `modules/cloudfront` gained a
      `cloudfront_distribution_arn` output, which the parameters need

**The plan that was applied, 2026-08-28** — account `679878703800`, profile `tp-site`. Kept because
it is the only record of what the first apply created:

```
data.aws_caller_identity.current: Read complete [id=679878703800]
data.aws_ssm_parameter.cdn_distribution_arn: Read complete [id=/travispollard/cdn/distribution_arn]

  + aws_iam_openid_connect_provider.github
  + aws_iam_role.publisher
  + aws_iam_role_policy.publisher
  + aws_s3_bucket.cfb_data
  + aws_s3_bucket_lifecycle_configuration.cfb_data
  + aws_s3_bucket_policy.cfb_data
  + aws_s3_bucket_public_access_block.cfb_data
  + aws_s3_bucket_versioning.cfb_data

Plan: 8 to add, 0 to change, 0 to destroy.
```

## 7. Schedule and alerting

- [x] GitHub Actions workflow, cron, Sunday and Tuesday — all three written, merged to `main`
      (PR #43) and **dispatched successfully 2026-08-28**
  - Every step is a command a human runs locally (SPEC §8), so a red run is reproducible with one
    copy-paste. No inline Python, no workflow-only branch, no date arithmetic in YAML
  - `cfb-ci.yml` passed on PR #43: `460 passed, 16 skipped in 2.44s` on the runner. Offline **by
    construction** — no `configure-aws-credentials` step, no `id-token` permission, no profile — so
    the 16 S3 tests skip for want of credentials the job was never given
  - `cfb-cfbd.yml` ([run 33194110693](https://github.com/jtravisp/travispollard.com/actions/runs/33194110693)),
    the run that closed the two CLI gaps:

    ```
    Assuming role with OIDC
    Authenticated as assumedRoleId AROAZ4S7NXK4FEO6NNV7Q:GitHubActions
    event=snapshot_written source=cfbd resource=games result=skip reason=no_completed_week
    event=snapshot_written source=cfbd resource=lines result=skip reason=no_completed_week
    ```

    Green with nothing collected, which is the correct answer on 2026-08-28: week 1 does not close
    until 2026-09-08, so the first Sunday with anything to pull is 2026-09-13
  - `cfb-sagarin.yml` ([run 33194175377](https://github.com/jtravisp/travispollard.com/actions/runs/33194175377))
    **wrote to the real bucket from CI** — `raw/sagarin/season=2026/week=preseason/2026-08-28T172006Z.txt`,
    148,793 bytes:

    ```
    Authenticated as assumedRoleId AROAZ4S7NXK4FEO6NNV7Q:GitHubActions
    event=snapshot_written source=sagarin result=ok page_state=preseason teams=266 predictions=53
    event=freshness source=sagarin result=skip reason=no_prior_manifest
    ```

  - **The publisher role has now been assumed by something other than a human**, which was the last
    unproven link in the chain. Both collect workflows use only the session credentials the OIDC
    exchange hands them; neither names `AWS_PROFILE` or `tp-site`
  - Actions bumped to `checkout@v5`, `setup-uv@v6`, `configure-aws-credentials@v5`. GitHub still
    warns that two of them target Node 20 and are being forced onto Node 24 — upstream's to fix
- [~] Failure notification that reaches you — the mechanism is the run failure itself (SPEC §11):
      any `CfbError` is exit 1, which reddens the run and GitHub emails it. **Still unverified: no
      run has gone red.** Every dispatch so far has been green, so the alert path is the one part of
      this section nothing has exercised
- [~] Stale-data alert wired to the freshness check — `cfb check-freshness sagarin` is the second
      step of `cfb-sagarin.yml` and ran, reporting `reason=no_prior_manifest`: every snapshot in the
      bucket is from today, so nothing has a prior *date* to compare against. The skip path is
      confirmed in CI; the raise path waits on two runs a day apart

---

## What closes the remaining §3 items

Two `[~]` items remain, both waiting on a *run* rather than on more code. Two entries have left
this list since it was written: `cli.py`, which landed and immediately turned the fetch item `[x]`
and found a bug — the CLI's `in_season` guard raised on a missing calendar and skipped the fetch
entirely, which is the clean failure SPEC §3.3 prefers a messy artifact to — and
`data/calendar/2026.json`, which is now committed from a real `/calendar?year=2026` call. A Sagarin
fetch today resolves a real week instead of filing under `week=unknown`.

1. **An in-season capture, by hand, once the first weekend's games are played.** Still the only
   real wait, and the gate is the title line rather than a week number — the page becomes usable
   the moment it drops `STARTING`. It closes four things at once: the date formats in
   `parse_page_date_stamp`, the `"in-season"` branch of `parse_page_state`, the two PROVISIONAL
   assertions in `test_freshness.py`, and — only maybe — the PREDICTOR column question in the
   deviation note above, which needs the specific rows checked rather than the file merely
   existing.
2. **`terraform apply`, root stack before `cfb/`.** Unchanged, and the order is still forced:
   `cfb/terraform` reads `/travispollard/cdn/` parameters that the root stack's `cfb-wiring.tf`
   publishes. Until this happens the S3 write stays unit-tested and never run, the 16 skipped
   tests stay skipped, and §7's scheduled job has no role to assume.

§5 is blocked on the human item below, not on §3.

---

## Blocked on a human, not on code

One item is left that cannot be finished by writing code, and it sits on the critical path for §5.
`data/calendar/2026.json` used to be the other; it is committed, generated from a real
`/calendar?year=2026` call now that the key is in SSM.

- **`data/crosswalk/teams-2026.yaml`** — roughly 25 mappings decided by hand. The `/teams/fbs` call
  it needed has been made: `tests/fixtures/rosters/cfbd-2026.json` holds all 138 FBS teams with
  their ids. SPEC §6.3 is explicit that similarity scoring orders those decisions and never makes
  one — `"Southern California" ~ USC (0.09)` — so the machine can rank the list and a person has to
  work down it.
- Two things about the shape of that job are now known rather than assumed. CFBD spells the three
  SPEC §6.1 examples `USC`, `UCF` and `Texas A&M`, pinned by a fixture test so a vendor rename
  shows up there rather than as an `UnmappedTeamError` in a scheduled run. And the 128 FCS names
  Sagarin rates have **no** counterpart in `/teams/fbs`, so §6.5's "every Sagarin name resolves"
  needs either an FCS roster or a decision that the crosswalk is FBS-only. §6 has not made it.

---

## Out of scope for phase 0

Elo. Predictions. Any page under `frontend/app/cfb/`. Historical backfill. The architecture write-up.

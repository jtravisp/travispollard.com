# Phase 0 — the collector

**Goal:** both sources fetched on a schedule, raw snapshots landing in S3, the Sagarin parser passing contract tests, and the crosswalk covering every FBS team.

**No modeling. No pages. No predictions.**

**Why first:** CFBD history can be backfilled at any time. Sagarin's page shows current ratings only — once a week rolls over, that snapshot is gone permanently. Every week without a collector is an unrecoverable hole in a dataset whose whole value is that nobody else has it.

**Done when:** a scheduled run has completed unattended, twice, and `data/raw/` contains snapshots nobody touched by hand.

---

## Where this stands (2026-08-28)

The Sagarin path is complete in code, end to end: pinned-HTTP fetch, snapshot, both parsers,
manifest, freshness check. The CFBD budgeted client is written. **Nothing has run against the
network or against AWS**, so none of it is verified against anything but fixtures, and the two
gaps that keep it that way are an unwritten `cli.py` and an unapplied Terraform stack.

| | |
|---|---|
| Tests | 299 passing, 16 skipped, no collection errors; `ruff check .` clean |
| Landed | `2fa6833..e918907` — scaffolding, both parsers, models, storage, calendar, key construction, the Sagarin collector and fetcher, freshness, `logging.py` |
| Uncommitted | the CFBD client and its 42 tests, the §4.1/§5.3 ladder change, extra freshness coverage. Counted in the 299 above; not yet in a commit |
| Next | `cli.py` (SPEC §8). Nothing in this project can be run end to end today — the fetcher exists and no command drives it |
| Blocked on a human | an in-season Sagarin capture, the CFBD calendar, the crosswalk — see the bottom of this file |

Re-verified 2026-08-28 by running, in `cfb/`:

| Command | Result |
|---|---|
| `uv run pytest` | `299 passed, 16 skipped in 1.67s` |
| `uv run ruff check .` | `All checks passed!` |
| `terraform -chdir=terraform validate` | `Success! The configuration is valid.` |

Every `[x]` below is backed by one of those three. Nothing here has been applied to AWS or run
against the network, so every `[~]` and `[ ]` stays that way regardless of how complete the code
reads — a module with exhaustive offline tests and no live run is `[~]`, not `[x]`.

Where the 299 sit:

| File | Tests | Covers |
|---|---|---|
| `test_storage.py` | 48 | the `SnapshotStore` contract, over three stores (16 skip without AWS) |
| `test_sagarin_fetch.py` | 46 | SPEC §4.1, via `httpx.MockTransport` |
| `test_cfbd.py` | 42 | SPEC §5.1 and §5.3 — budget, both retry ladders |
| `test_manifest.py` | 42 | key construction, SPEC §2.1 and §3.2 |
| `test_sagarin_parser.py` | 40 | the ratings table and the date stamp |
| `test_calendar.py` | 34 | season/week resolution, SPEC §3 |
| `test_sagarin_predictions.py` | 30 | the predictions block |
| `test_freshness.py` | 22 | SPEC §4.6, skip paths in full |
| `test_models.py` | 11 | the `SagarinSnapshot` validators |

### How much of SPEC §1 exists

Everything except the CLI and the crosswalk:

```
src/cfb/  __init__.py  calendar.py  errors.py  logging.py  manifest.py  models.py  storage.py
          collectors/{sagarin,cfbd}.py         parsers/{sagarin_ratings,sagarin_predictions}.py
```

Absent: `cli.py`, and `crosswalk/` (both `__init__.py` and `bootstrap.py`). The CLI is what makes
§8 and every "run it for real" item reachable; the crosswalk is §6 and blocks step 5 of §4.3.

The exception hierarchy is no longer the illustration it was. `errors.py` declares twelve and ten
are now raised somewhere: `ParseError` (26 sites), `WeekResolutionError` (8), `FetchError` (7),
`SnapshotExistsError` and `SnapshotNotFoundError` (6 between them, through the `_exists` /
`_missing` factories), `DuplicateRankError` (3), and one each for `EncodingError`,
`StaleSourceError` and `CallBudgetExceeded`.

Two are still declared and unused, and they are unused for different reasons:

- `UnmappedTeamError` belongs to `crosswalk/`, which does not exist. Expected.
- `ValidationError` is specified in §9 as the one that "wraps pydantic", and nothing wraps
  anything — pydantic's own `ValidationError` propagates from every model boundary instead. That
  is a real gap between §9 and the code, not a module waiting to be written, and it should either
  be used or dropped from the hierarchy.

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

- [~] Fetch with scheme pinned to HTTP, no upgrade
  - Written. `fetch_page()` in `collectors/sagarin.py`: URL pinned, `follow_redirects=False`, 30s
    connect and read, retry on timeout / connection error / 5xx and never on 4xx or 3xx.
    `fetch_sagarin`'s `fetch` argument now defaults to it, so the seam survives for tests and
    production gets a real fetcher. `httpx` is a base dependency
  - 46 tests in `tests/test_sagarin_fetch.py` drive it through `httpx.MockTransport`, which sits
    below the client so the redirect policy, the timeout and the request count are observed rather
    than stubbed. Every 3xx to HTTPS raises with exactly one request issued — the https branch of
    the handler answers a plausible 200 on purpose, so a fetcher that followed it would return
    those bytes instead of raising
  - `[~]` and not `[x]` for one reason: **it has never issued a real request.** The scheme pin
    exists because sagarin.com 302s HTTPS down to HTTP, and no test in this repo has ever seen
    that 302. Everything asserted about it is asserted against a transport we wrote
- [x] Encoding sniff, raise on failure — `decode_page()` in `collectors/sagarin.py`. SPEC §4.2
      order (`utf-8`, `cp1252`, `latin-1`), first candidate that decodes **and** contains both
      markers wins, `EncodingError` when none qualifies. The golden capture resolves to `utf-8`
      because it happens to be pure ASCII, exactly as SPEC §4.7 predicts
- [~] Write raw bytes to `s3://<bucket>/raw/sagarin/<date>/` before parsing
  - The code is complete and the ordering is the tested part: `fetch_sagarin` writes bytes at step
    2 of SPEC §4.3, before anything parses them, and the §3.3 suite asserts the bytes survive a
    resolution failure rather than merely that the run went red
  - Still `[~]` because the bucket in §6 has never been applied. `MemorySnapshotStore` and
    `FileSnapshotStore` are exercised on every run; `S3SnapshotStore` is only reached with
    `CFB_INTEGRATION=1` and `CFB_TEST_BUCKET` set, which is the 16 skips in every count on this
    page. No object has ever been written to the real bucket, because there is no real bucket
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

- [ ] API key in SSM, not env files
- [ ] Incremental sync with a call-budget guard
- [ ] Backoff on 429
- [ ] Raw JSON to `s3://<bucket>/raw/cfbd/<date>/`
- [ ] Pull: teams, games, betting lines

## 5. Crosswalk

- [ ] Generate the initial mapping from both sources
- [ ] Store as a versioned data file, not code
- [ ] Test: every FBS team in either source resolves
- [ ] Test: an unknown name raises

## 6. Infrastructure

- [~] `cfb/terraform/` root with its own backend and state — the `terraform` block now exists
      (S3 backend, key `cfb/terraform.tfstate`, `aws ~> 5.0` to match the root stack). `init
      -backend=false` resolves 5.100.0 and `validate` passes. Never initialised against the real
      backend and never applied
- [~] Data bucket, private, versioned — written in `main.tf` (versioning, public access block,
      `raw/` lifecycle to STANDARD_IA at 90 days, no `s3:DeleteObject` on `raw/`). Never applied
- [~] Reads distribution ARN from SSM — the data source is written; the parameters it reads are in
      the root stack's `cfb-wiring.tf`, also never applied. Apply order is root, then cfb
- [~] GitHub OIDC publisher role — written, never applied. `github_repo` default corrected to
      `jtravisp/travispollard.com`; the previous value was an org that does not exist, so the trust
      condition would never have matched and every scheduled run would have failed to assume the role
- [ ] Root Terraform: parameterize `modules/cloudfront` for extra origins — deferred to Phase 1
      (SPEC §10.2). There is no JSON to serve yet
- [~] Root Terraform: `/cfb/data/*` behavior, SSM outputs — the two `aws_ssm_parameter` resources
      are written and the root validates with them. The `/cfb/data/*` behavior and its OAC are
      commented out in `cfb-wiring.tf` for Phase 1: left live, the OAC would be created on the next
      root apply, ahead of the behavior that uses it. `modules/cloudfront` gained a
      `cloudfront_distribution_arn` output, which the parameters need

## 7. Schedule and alerting

- [ ] GitHub Actions workflow, cron, Sunday and Tuesday — `.github/workflows/` does not exist yet
- [ ] Failure notification that reaches you
- [ ] Stale-data alert wired to the freshness check

---

## What closes the remaining §3 items

Every §3 item is now written. Three are `[~]` rather than `[x]`, and each is waiting on a *run*
rather than on more code — which is a different kind of open than this list used to describe.
`storage.py`, the previous entry here, landed and is gone from it.

1. **`cli.py` — the `cfb` entrypoint (SPEC §8).** The one item startable right now with no
   dependency on anything or anyone. Nothing in this project can be run end to end today: the
   fetcher, the collector, the freshness check and the CFBD client all exist and no command drives
   any of them. It also gates the two `[~]` items below in practice — `cfb fetch sagarin --store
   file://./local-snapshots` needs no AWS and no key, and would turn the first of them `[x]` in a
   single run. `pyproject.toml` still registers no console script, deliberately: an entry point to
   a missing module breaks the install.
2. **An in-season capture, by hand, once the first weekend's games are played.** Still the only
   real wait, and the gate is the title line rather than a week number — the page becomes usable
   the moment it drops `STARTING`. It closes four things at once: the date formats in
   `parse_page_date_stamp`, the `"in-season"` branch of `parse_page_state`, the two PROVISIONAL
   assertions in `test_freshness.py`, and — only maybe — the PREDICTOR column question in the
   deviation note above, which needs the specific rows checked rather than the file merely
   existing.
3. **`terraform apply`, root stack before `cfb/`.** Unchanged, and the order is still forced:
   `cfb/terraform` reads `/travispollard/cdn/` parameters that the root stack's `cfb-wiring.tf`
   publishes. Until this happens the S3 write stays unit-tested and never run, the 16 skipped
   tests stay skipped, and §7's scheduled job has no role to assume.

§4 and §5 are blocked on the two human items below, not on §3.

---

## Blocked on a human, not on code

Two items cannot be finished by writing code, and both sit on the critical path for §4 and §5:

- **`data/calendar/2026.json`** — one CFBD `/calendar?year=2026` call, committed to the repo
  (SPEC §3.1). The key is in SSM at `/travispollard/cfb/cfbd_api_key`. `calendar.py` can be written
  and tested against a synthetic fixture before this exists, but it cannot resolve a real week
  without it.
- **`data/crosswalk/teams-2026.yaml`** — needs a `/teams/fbs` call for the CFBD side, and then
  roughly 25 mappings decided by hand. SPEC §6.3 is explicit that similarity scoring orders those
  decisions and never makes one: `"Southern California" ~ USC (0.09)`. The Sagarin half of the
  roster fixture can be generated from the golden capture today — all 266 names parse clean.

---

## Out of scope for phase 0

Elo. Predictions. Any page under `frontend/app/cfb/`. Historical backfill. The architecture write-up.

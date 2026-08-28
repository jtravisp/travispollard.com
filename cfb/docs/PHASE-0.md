# Phase 0 — the collector

**Goal:** both sources fetched on a schedule, raw snapshots landing in S3, the Sagarin parser passing contract tests, and the crosswalk covering every FBS team.

**No modeling. No pages. No predictions.**

**Why first:** CFBD history can be backfilled at any time. Sagarin's page shows current ratings only — once a week rolls over, that snapshot is gone permanently. Every week without a collector is an unrecoverable hole in a dataset whose whole value is that nobody else has it.

**Done when:** a scheduled run has completed unattended, twice, and `data/raw/` contains snapshots nobody touched by hand.

---

## Where this stands (2026-08-28)

The Sagarin page is fully parsed and the package is importable. Nothing is fetched, stored, or scheduled yet — every line below that touches the network or S3 is still open.

| | |
|---|---|
| Tests | 64 passing (26 ratings, 30 predictions, 8 snapshot-model), `ruff check` clean |
| Landed | `2fa6833..ec5e0a4` — scaffolding + both parsers + models + Terraform fixes |
| Next | `storage.py`, the `SnapshotStore` seam (SPEC §2.3) — everything downstream needs it to stay offline in tests |
| Blocked on a human | the CFBD calendar and the crosswalk — see the bottom of this file |

Re-verified 2026-08-28 by running, in `cfb/`:

| Command | Result |
|---|---|
| `uv run pytest` | `64 passed in 0.25s` |
| `uv run pytest tests/test_sagarin_parser.py -v` | 26 passed, one per §2 item below |
| `uv run ruff check .` | `All checks passed!` |
| `terraform -chdir=terraform validate` | `Success! The configuration is valid.` — Terraform 1.15.3, aws 5.100.0 |

Every `[x]` below is backed by one of those four. Nothing here has been applied to AWS or run
against the network, so every `[~]` and `[ ]` stays that way regardless of how complete the code
reads.

### How much of SPEC §1 exists

Three of the nine planned modules under `src/cfb/`, plus the two parsers:

```
src/cfb/__init__.py  errors.py  models.py  parsers/{sagarin_ratings,sagarin_predictions}.py
```

Absent: `cli.py`, `calendar.py`, `storage.py`, `manifest.py`, `logging.py`, `collectors/`
(both), `crosswalk/` (both). Everything still open in §3, §4, §5 and §7 lives in one of those.

The exception hierarchy is the sharpest illustration: `errors.py` declares nine exceptions and
only two are ever raised — `ParseError` (23 sites) and `DuplicateRankError` (3). `FetchError`,
`EncodingError`, `ValidationError`, `UnmappedTeamError`, `WeekResolutionError`,
`StaleSourceError` and `CallBudgetExceeded` are declared and unused, because each belongs to a
module that has not been written. That is intended — §9 landed as one piece — but it means the
hierarchy is not evidence that the behaviour behind it exists.

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
- [x] `tests/test_models.py` — 8 tests over the `SagarinSnapshot` validators. They duplicate
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

- [ ] Fetch with scheme pinned to HTTP, no upgrade
  - `collectors/sagarin.py` now exists, but `fetch` is an injected zero-argument callable with no
    default: the CLI is meant to pass the pinned-HTTP fetcher of SPEC §4.1 and that fetcher has not
    been written. `httpx` is not a dependency yet. `fetch_sagarin` is therefore complete as a seam
    and not yet runnable in production
- [x] Encoding sniff, raise on failure — `decode_page()` in `collectors/sagarin.py`. SPEC §4.2
      order (`utf-8`, `cp1252`, `latin-1`), first candidate that decodes **and** contains both
      markers wins, `EncodingError` when none qualifies. The golden capture resolves to `utf-8`
      because it happens to be pure ASCII, exactly as SPEC §4.7 predicts
- [ ] Write raw bytes to `s3://<bucket>/raw/sagarin/<date>/` before parsing
  - Blocked twice over: `storage.py` does not exist, and the bucket in §6 has never been applied
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
- [ ] Freshness check: internal date stamp advanced since last snapshot
  - Blocked three ways, and the last one is not a code problem: it needs `storage.py` to have a
    previous snapshot to compare against, it needs the in-season fixture from §2 to have a stamp
    at all, and on the preseason page there is nothing to advance — so per the skill the check
    must be *skipped*, not merely passed, until the first in-season page lands. Whatever gets
    written here needs a test for the skip path, which the current fixture can supply

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
- Step 7, the freshness check. `in_season` exists to gate it but nothing calls it yet
- `http_status` is hardcoded to `200`. Defensible — SPEC §4.1 makes any non-2xx a `FetchError`
  inside the fetcher, so bytes reaching `fetch_sagarin` are by construction a 200 — but it means
  the field records an inference rather than an observation. If the fetch seam ever returns
  `(status, bytes)` instead of `bytes`, this should become the real value
- `hfa` is written with **five** keys (`strong_recent` included) because `parse_hfa` captures all
  five columns the page prints. SPEC §2.2's example manifest names four. Not a bug — §4.7 already
  documents the five-vs-four gap — but §2.2's example is now narrower than what the code writes,
  and one of the two should move

**Signatures the tests propose, none of which SPEC pins.** These are the decision to make before
implementing, and changing them means changing the tests:

- SPEC §3.1 writes `load_calendar(season)`, `resolve(now)`, `in_season(now)`. None can be pointed
  at a fixture, so each grew one keyword argument: `data_dir=` on the loader, `calendar=` on the
  other two
- SPEC §1 assigns "key construction" to `manifest.py` but names no functions. The tests assume
  `snapshot_key(source=, season=, week=, fetched_at=, resource=None)` and `manifest_key(key)`
- SPEC §8 gives the CLI surface and §4.3 the order of operations, but no collector signature that
  runs without a network or a bucket. The tests assume
  `fetch_sagarin(store=, now=, fetch=, data_dir=)`, with `fetch` a zero-argument callable

**A design decision the tests encode, derived rather than stated.** `resolve()` does not raise on a
date it cannot place; it returns `WeekRef(week="unknown", how="unknown")`. SPEC §2.2 types
`week_resolution` as `"calendar" | "unknown"`, and `"unknown"` could never appear if resolution
raised instead of returning. `load_calendar` still raises `WeekResolutionError` on a missing or
malformed file, and the collector still owes the non-zero exit — after the write. This is the one
documented departure from "validation failures raise", and §3.3 carves it out explicitly.

**Left underspecified on purpose.** `in_season` is "preseason start .. postseason end" (SPEC §3.1),
but nothing defines preseason start — the CFBD calendar's first entry is week 1's first game, not
a preseason boundary. The tests assert the unambiguous half (true during the regular season and
the postseason, false in the offseason and the month after) and do not invent a threshold for the
preseason edge. That boundary needs a decision before `in_season` is written.

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

## What blocks §3, the next section with open work

In dependency order. The first two are startable now; the third is the only real wait.

1. **`storage.py` — the `SnapshotStore` protocol (SPEC §2.3, lines 136-145).** Nothing else in §3
   can be written first: "write raw bytes before parsing" is the project's immutability rule, so
   the store is upstream of the fetch, not downstream of it. It is also the only one of these
   that needs no AWS and no new fixture — `MemorySnapshotStore` keeps the collector tests offline,
   which `cfb/CLAUDE.md` requires. Write this next.
2. **An in-season capture, by hand, the first weekend games are played.** Gates the freshness
   check above, and until it exists two already-shipped code paths stay unverified against real
   bytes: the date formats in `parse_page_date_stamp` are a guess, and the `"in-season"` branch of
   `parse_page_state` has never seen a page that takes it. Previously logged here as a four-week
   clock dependency, which was wrong — see §2. One page carries both parsers' input (SPEC §4.7:
   the predictions block is on the same file, printed twice, 53 games each), so a single capture
   unblocks the ratings and the predictions side together.
3. **`terraform apply`, root stack before `cfb/`.** The data bucket, the OIDC publisher role and
   the SSM parameters are all written and all unapplied. The order is forced: `cfb/terraform`
   reads `/travispollard/cdn/` parameters that the root stack's `cfb-wiring.tf` publishes, so the
   root applies first or the cfb data source resolves nothing. Until this happens the S3 write in
   §3 can be unit-tested but never run for real, and §7's scheduled job has no role to assume.

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

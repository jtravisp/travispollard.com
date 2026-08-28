# Phase 0 — the collector

**Goal:** both sources fetched on a schedule, raw snapshots landing in S3, the Sagarin parser passing contract tests, and the crosswalk covering every FBS team.

**No modeling. No pages. No predictions.**

**Why first:** CFBD history can be backfilled at any time. Sagarin's page shows current ratings only — once a week rolls over, that snapshot is gone permanently. Every week without a collector is an unrecoverable hole in a dataset whose whole value is that nobody else has it.

**Done when:** a scheduled run has completed unattended, twice, and `data/raw/` contains snapshots nobody touched by hand.

---

## 1. Repo groundwork

- [~] Delete or archive `www/` — deferred by decision (SPEC §12); the root `CLAUDE.md` marks it dead
- [~] Create `cfb/` with `src/`, `tests/`, `data/`, `terraform/`, `scripts/`, `docs/` — `docs/`, `scripts/`, `terraform/`, `tests/` exist; `src/` and `data/` do not
- [x] Add `cfb/CLAUDE.md`
- [x] Add `.claude/skills/sagarin-format/SKILL.md` at repo root
- [ ] Python project scaffolding (uv, ruff, pytest) — **blocking §2**: with no `pyproject.toml` the `cfb` package is not importable, so the tests below cannot run
- [x] Root `CLAUDE.md` via `/init`, then pruned

## 2. Golden fixture and tests — before any parser code

Written 2026-08-27. All 26 tests currently fail with `ModuleNotFoundError: No module named
'cfb'` — the intended red: no parser exists, and no `pyproject.toml` exists either (§1).
Checked against a deliberately naive strawman parser (whole-page regex, no section stop,
hardcoded HFA, silent skip on bad rows): 11 failed on real parsed values, 15 passed. The
assertions bite; they are not passing vacuously.

What the golden capture actually contains — including three traps the skill did not
document — is recorded in SPEC §4.7.

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

Still open in this section:

- [ ] `tests/test_sagarin_predictions.py` — the predictions block is printed **twice**
      (regular, then EXPERIMENTAL); the same duplication trap as section 3
- [ ] An in-season golden page, `tests/fixtures/sagarin_2026_week04.txt` — nothing can
      test the date stamp, the in-season title flag, or freshness until one exists

## 3. Sagarin collector

- [ ] Fetch with scheme pinned to HTTP, no upgrade
- [ ] Encoding sniff, raise on failure
- [ ] Write raw bytes to `s3://<bucket>/raw/sagarin/<date>/` before parsing
- [ ] Parser passing all tests from step 2
- [ ] Parse the `Predictions_with_Totals_and_Moneylines` section
- [ ] Freshness check: internal date stamp advanced since last snapshot

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

- [ ] `cfb/terraform/` root with its own backend and state
- [ ] Data bucket, private, versioned
- [ ] Reads distribution ARN from SSM
- [ ] GitHub OIDC publisher role
- [ ] Root Terraform: parameterize `modules/cloudfront` for extra origins
- [ ] Root Terraform: `/cfb/data/*` behavior, SSM outputs

## 7. Schedule and alerting

- [ ] GitHub Actions workflow, cron, Sunday and Tuesday
- [ ] Failure notification that reaches you
- [ ] Stale-data alert wired to the freshness check

---

## Out of scope for phase 0

Elo. Predictions. Any page under `frontend/app/cfb/`. Historical backfill. The architecture write-up.

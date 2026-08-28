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

- [ ] An in-season golden page, `tests/fixtures/sagarin_2026_week04.txt` — nothing can test the
      date stamp, the in-season title flag, or freshness until one exists. Two pieces of shipped
      code are unverified against real bytes because of it: the "through games of …" date parsing
      in `parse_page_date_stamp`, whose format list is a guess, and the `"in-season"` branch of
      `parse_page_state`

## 3. Sagarin collector

- [ ] Fetch with scheme pinned to HTTP, no upgrade
  - Needs `collectors/sagarin.py`, which does not exist
- [ ] Encoding sniff, raise on failure
  - `EncodingError` is defined in `errors.py` and never raised anywhere — the hierarchy landed
    ahead of the code that uses it
- [ ] Write raw bytes to `s3://<bucket>/raw/sagarin/<date>/` before parsing
  - Blocked twice over: `storage.py` does not exist, and the bucket in §6 has never been applied
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

In dependency order. Only the first is startable today.

1. **`storage.py` — the `SnapshotStore` protocol (SPEC §2.3, lines 136-145).** Nothing else in §3
   can be written first: "write raw bytes before parsing" is the project's immutability rule, so
   the store is upstream of the fetch, not downstream of it. It is also the only one of these
   that needs no AWS and no new fixture — `MemorySnapshotStore` keeps the collector tests offline,
   which `cfb/CLAUDE.md` requires. Write this next.
2. **`terraform apply`, root stack before `cfb/`.** The data bucket, the OIDC publisher role and
   the SSM parameters are all written and all unapplied. The order is forced: `cfb/terraform`
   reads `/travispollard/cdn/` parameters that the root stack's `cfb-wiring.tf` publishes, so the
   root applies first or the cfb data source resolves nothing. Until this happens the S3 write in
   §3 can be unit-tested but never run for real, and §7's scheduled job has no role to assume.
3. **An in-season capture, `tests/fixtures/sagarin_2026_week04.txt`.** Gates the freshness check
   above, and until it exists two already-shipped code paths stay unverified against real bytes:
   the date formats in `parse_page_date_stamp` are a guess, and the `"in-season"` branch of
   `parse_page_state` has never seen a page that takes it. This one is a clock dependency — the
   2026 season has to reach week 4 — so the collector should not be designed around it landing.

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

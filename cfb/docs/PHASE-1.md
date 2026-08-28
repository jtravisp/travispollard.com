# Phase 1 — the model, the predictions, the pages

Progress against `SPEC-phase1.md`. Phase 0's tracking stays in `PHASE-0.md`; its two
carry-overs are listed at the bottom of this file because they still gate the "one Saturday end to
end" that §11 defines done as, and neither is on the Phase 1 code path.

The rule that decides a mark, unchanged from Phase 0: **a module with exhaustive offline tests and
no live run is `[~]`, not `[x]`.** Nothing in this phase has run against the real bucket yet, so
every item below is at best `[~]` on that axis — the marks record whether the code and its tests
exist, and the "verified by" column says what was actually run.

## Where this stands (2026-08-28)

§3 and §4 are complete. The Elo state loop is closed — something writes state, something rebuilds
it from `raw/` alone, and a command exits 1 when they disagree — and a week's predictions are
generated, written write-once and indexed.

| | |
|---|---|
| Tests | **741 passing, 22 skipped**, `ruff check .` clean, `terraform validate` clean |
| Landed | `fa40c16` (§3.1–§3.5), `c9c1d85` (the state writer). This session's §4 work is uncommitted |
| Next | §5, scoring. It needs predictions to join against, which now exist |
| Blocked | `closing_line` only — no `/lines` capture exists. One CFBD call unblocks it; see below |
| Blocked on a human | nothing in Phase 1. Phase 0's in-season Sagarin capture still stands |

Verified this session, in `cfb/`:

| Command | Result |
|---|---|
| `uv run pytest` | `741 passed, 22 skipped in 13.54s` |
| `uv run ruff check .` | `All checks passed!` |
| `terraform -chdir=terraform validate` | `Success! The configuration is valid.` |
| `uv run cfb elo seed --season 2026 --store file://…` | exit 0, `week=preseason teams=266` |
| `uv run cfb elo advance --season 2026 --week {1,2,3}` | exit 0 each, `season_games=1,2,3` |
| `uv run cfb elo replay --season 2026 --through-week 03` | exit 0, `elo_verify result=ok` — **§11 step 5, green** |
| `uv run cfb elo seed` on a season in progress | exit 1, `SeedStateError` |
| `uv run cfb predict --season 2026 --week 1 --store file://…` | exit 0, `games=3 benchmarked=2 indexed=1` |
| a second `cfb predict` for the same week | exit 0, **second key written, first kept** |

---

## 3. The model

- [x] **§3.1 the scale.** `ELO_PER_POINT = 28`, and the win-probability `elo_diff` is the
      HFA-adjusted gap. The §3.1 table's six rows are pinned by
      `test_the_spec_3_1_calibration_table`.
  - [x] The table's right-hand column was headed "Observed" and claimed a provenance it does not
        have. Relabelled: it is a plausibility check against recalled figures, and §5.3's
        calibration curve is the only calibration number this project can currently defend
- [x] **§3.2 seeding.** `elo/seed.py`. 266 teams, centred on the snapshot's FBS mean.
      `SeedStateError` on an in-season page
- [x] **§3.3 home-field advantage.** Read from the snapshot manifest's `hfa["predictor"]`, per
      game, from the newest snapshot captured **strictly before that game's kickoff**
  - [x] That rule is a decision §3.3 does not make. "The current snapshot" cannot be replayed — a
        replay has no run time to anchor to — so it is stated as a function of the data. It
        reproduces what a Sunday run sees on §8's schedule and stays stable as later snapshots
        land. **`cfb score` must use the same rule or step 5 fails**, which is now structural
        rather than a warning: `sources.hfa_at` is the single implementation, and `hfa_for`
        (a game's kickoff) and `predict` (a slate's first kickoff) are two boundaries into it
- [x] **§3.4 the update step.** `K = 20`, signed `elo_diff_winner`, no HFA at a neutral site, MOV
      denominator floored at 0.25 with a raise if the unclamped value would have crossed it
  - [x] `mov_denominator()` is public because the clamp is unreachable through `update` — the raise
        stands in front of it, so a test that only went through `update` passed with the clamp
        deleted. Confirmed by sabotage before the test was written
- [x] **§3.5 state is a cache, not a source of truth.** Two independent paths, and a command that
      compares them
  - [x] `replay()` — whole season from `raw/`, no network, no state file
  - [x] `advance()` — one week folded onto the previous state. **Not** `replay() -> write`, which
        would make step 5 compare a replay against a replay and verify nothing
  - [x] `elo/state.py` — the document: write-once through `put_bytes`, partition ordering,
        nearest-earlier-state lookup
  - [x] `cfb elo seed`, `cfb elo advance`, `cfb elo replay`
- [ ] **§3.6 the seed contamination series.** The weekly Pearson correlation against Sagarin
      PREDICTOR, and the disclosure that retires the first week `r` falls below 0.90. Needs §5.3's
      scoring output before it has anything to correlate
- [ ] **§3.7 the probability clamp.** `[0.001, 0.999]` applied at publish time, unclamped in
      storage so the Brier scores are computed on what the model said. Needs §6.
      `test_probabilities_are_not_clamped_here` already pins the storage half

### What the state work decided that the spec does not say

Three things came up that §3.5 leaves open, and all three are load-bearing enough to write down.

**An advance's batch is bounded twice: by the week, and by the previous state's kickoff cutoff.**
`EloState.through_kickoff` exists for the second bound. The week cut alone cannot work: a week 1
game postponed past week 2 would be applied in week 1's batch — before week 2's games — while a
replay sorts it after them. Elo is path-dependent, so the two would disagree **permanently, with no
re-run able to reconcile them.** With both bounds, each advance is the next contiguous block of the
season in kickoff order, so the chain composes to exactly the sequence one sorted pass produces.

Two consequences, both tested:

- A missed Sunday and a postponed game **self-heal.** The next advance takes everything after the
  last cutoff, so it absorbs whatever the previous run missed. No intervention.
- **Regeneration must go forward from the latest state, never backward into an earlier week.**
  Re-running week 01 after a postponed week 1 game lands makes its batch `{G1, G3}` and pushes its
  cutoff past week 2's game, stranding it. The replay check catches this, so it is detectable
  rather than silent — but it is a real sharp edge.

**The sharp edge stays, for now.** A time-window partition would remove it and costs more than it
saves today — the decision and its reasoning are recorded under §5 below.

**`cfb elo advance` is not in §9's command list.** §8 gives the Elo update to the Sunday `cfb score`
run, which is §5 and does not exist. Without something writing a week state, `cfb elo replay` has
nothing to check and step 5 verifies nothing — so the command exists now and `cfb score` will call
the same `advance()`. Fold it in or keep it as a debugging verb; either is fine, but do not end up
with two implementations.

---

## 4. The prediction log

- [x] `predictions/season=2026/week=NN/<ts>.json`, write-once through `put_bytes`, one object per
      week. A regenerate writes a second key and the first stays — verified by command, not only
      by test
- [x] The §4.2 shape. Field names match the spec exactly, plus one addition:
      `model.sagarin_predictions_from`, because `sagarin_predictor_margin` is a number from a
      source and the model block exists so no number in the document is unattributed
- [x] `predictions/index.json` — a **pure projection of a key listing**. It reads no prediction
      objects, so it cannot disagree with what it describes; that is what makes it safe as the one
      mutable object
- [x] `cfb predict --season 2026 --week N`, defaulting to `calendar.coming_week`
- [x] IAM: `s3:PutObject` on `predictions/*` with no `s3:DeleteObject`
- [ ] **Closing lines from CFBD `/lines`.** The only unfinished part of §4 — see below

### `closing_line` is null, deliberately, and this is what unblocks it

There is no `/lines` capture anywhere in this project and no fixture, and `cfb/CLAUDE.md` forbids
calling CFBD from a test. Writing a parser against a remembered response shape would put an
unverified reader on the Thursday critical path, where a wrong guess either raises on a shape
mismatch or — worse — returns `None` for every game and silently deletes the headline benchmark the
PRD names. §4.2 makes the field nullable, so a null is a legal document rather than a hole.

To finish it, in order:

1. `uv run cfb fetch cfbd --resource lines --season 2026 --week 1` — one CFBD call, one snapshot
2. Commit the capture as `tests/fixtures/cfbd_lines_2026_week01.json`
3. Implement `predict._closing_line`, which is the single place the join belongs
4. Decide §6.3's `line_source` — it says a provider has to be named, and that decision wants a real
   response in front of it rather than a guess

### What §4 confirmed about §3.6

§3.6 argues that a week 1 prediction *is* Sagarin's prediction, and uses that to justify the seed
disclosure. It is not an approximation: the seed is `1500 + (rating - mean) * 28`, so an Elo gap
over 28 is exactly a Sagarin rating gap, and adding the same HFA reproduces PREDICTOR to the
floating-point bit. The first real generated document shows `predicted_margin` and
`sagarin_predictor_margin` both `10.67` on one game and both `6.2` on a neutral-site one.

So **§3.6's Pearson correlation opens the season at exactly 1.0**, not near it, and
`TestTheWeekOneContamination` pins the identity that makes it so.

## 5. Scoring — not started, and the next session's work

- [ ] `elo/scoring.py`, `score_week()`, joining on `cfbd_game_id` (§5.1)
- [ ] Every §5.2 failure mode raises: `UnscoredGameError` for a result with no prediction, for a
      completed game with no result, and for an id that matched while the teams did not
- [ ] §5.3's figures, for Texas and the full slate separately, with sample sizes attached
- [ ] The Elo advance moves into `cfb score` — see the batch-partition decision below
- [ ] `scored/season=2026/week=NN/<ts>.json`
- [x] **The HFA rule is already shared and cannot drift.** `sources.hfa_at` is the single
      implementation of §3.3, and `hfa_for` (a game's own kickoff) and `predict` (a slate's first
      kickoff) are two boundaries into it. `cfb score` uses `hfa_for` by importing it, not by
      restating it — which is what keeps §11 step 5 honest

### Decision: the batch-partition rule stays week-scoped for now

The open question from last session was whether `advance` should batch by game week or by a
calendar time window. **Keep the week cut.** The kickoff cutoff added with `EloState.through_kickoff`
already fixed the failure that mattered — a missed Sunday and a postponed game both self-heal on the
next run — and the residual sharp edge is narrow: *regeneration must go forward from the latest
state, never backward into an earlier week*, because re-running an earlier week widens its batch and
strands a later game. That is detected by the replay check, not silent, and it is asserted in
`test_elo_state.py::test_regenerating_an_earlier_week_strands_a_later_game_and_is_caught`.

The time-window alternative is still the cleaner design and it is still not free:

- it needs the committed calendar inside `advance`, which currently reads none
- it changes what `elo/week=01` *means*, from "after week 1's games" to "after week 1's window"
- **it contradicts a committed test.** `test_replay.py::test_it_cuts_on_the_week_the_game_belongs_to_not_on_the_clock`
  asserts that `replay --through-week` is week-scoped, and the session rules forbid changing a test
  during an implementation session

So it needs a decision session of its own rather than being smuggled into §5. Revisit if a real
postponed game ever forces a backward regeneration; until then the cost is a documented rule and
one test that enforces it.

## 6. The JSON contract — not started

- [ ] `next-game.json`, `accuracy.json`, `notes/index.json`, `notes/<slug>.json`
- [ ] The §6.2 envelope, and routes that render a "data is newer than this page" state rather than
      throwing on an unknown `schema_version`
- [ ] §3.7's presentational clamp, and `<1%` / `>99%` at the endpoints
- [ ] `Cache-Control`, and the CloudFront invalidation for `/cfb/data/*` — which also needs the
      root-stack work deferred from Phase 0 §10.2

## 7. The weekly note — not started

## 8. Workflows — not started

- [ ] `cfb-score.yml` (Sun 12:30), `cfb-predict.yml` (Thu 12:00), `cfb-publish.yml` (Fri 12:00)
- [ ] The Friday publish is the SLO and its deadline is first kickoff Saturday

## 9. CLI

- [x] `cfb elo replay --season --through-week`
- [x] `cfb elo seed --season [--force]`
- [x] `cfb elo advance --season --week` *(not in §9's list; see the note in §3)*
- [x] `cfb predict --season --week [--force]`
- [ ] `cfb score`, `cfb publish`, `cfb note`
- [x] §9.1 records the five errors this phase adds to Phase 0 §9's hierarchy

## Repo layout, against §2

§2's file list predates this work and two modules are not in it. Both are recorded here rather than
silently added:

- **`src/cfb/sources.py`** — reading model inputs out of `raw/`. Extracted this session because
  `replay`, `advance` and `predict` all select games, resolve names and read an HFA, and §11 step 5
  is only meaningful if they agree on all three. Two copies of "the newest Sagarin manifest before
  kickoff" is how that check starts failing for reasons unrelated to the model.
- **`src/cfb/predict.py`** — §4 has no entry in §2's tree at all. It sits beside `replay.py` for the
  same reason `replay.py` does: a top-level verb, not a piece of the model.

`src/cfb/elo/state.py` is the third, recorded last session.

---

## Found this session

- **A bare `uv sync` prunes boto3, and every S3-backed command then died with a raw
  `ModuleNotFoundError`** from inside `S3SnapshotStore.__init__` — no traceback contract, no mention of
  the extra, no fix named. Both optional-import sites (`S3SnapshotStore.__init__` and
  `cfbd.ssm_secret`) now go through `errors.optional_import` and raise `MissingDependencyError`, which
  is a `CfbError` and so gets SPEC-phase0 §9's exit 1 with a message and no traceback. The sync command
  is `uv sync --extra s3`, now stated in `cfb/CLAUDE.md`.
  - The SSM site had **never** been covered. There was no prior `CredentialError` or anything like it;
    `grep` finds the name nowhere in the repo, so nothing had landed for that path at all.
  - The two `botocore` imports in `storage.py` are deliberately left unwrapped: reaching them means
    `__init__` already imported boto3, and botocore is boto3's own dependency, so a guard would be for a
    state pip cannot produce.

## Also found this session

- **`elo/` was not writable by the publisher role.** The Terraform policy granted `raw/*` and
  `cfb/data/*` and nothing else, so `cfb elo seed` and `cfb elo advance` would have failed with
  `AccessDenied` on the first scheduled Sunday. Nothing was broken in production because both have
  only ever run against `file://` stores. Fixed in the same statement that adds `predictions/*`,
  which now covers `elo/`, `predictions/`, `scored/` and `notes/` — `PutObject` and `GetObject`, no
  `DeleteObject`.
- **`PutObject` alone still permits an overwrite.** The write-once guarantee for `raw/`, `elo/` and
  `predictions/` comes from the conditional `IfNoneMatch` PUT in `S3SnapshotStore.put_bytes`, not
  from IAM; the missing `DeleteObject` is the second layer, not the first. Worth knowing before
  anyone reads the policy as the whole guarantee.
- **`terraform apply` has not been run for this change.** The policy is validated and formatted,
  not applied.

## Carried over from Phase 0

Neither is on the Phase 1 code path, and both still gate §11's "one Saturday end to end".

1. **An in-season Sagarin capture, by hand.** Closes the date formats in
   `parse_page_date_stamp`, the `"in-season"` branch of `parse_page_state`, and the two PROVISIONAL
   assertions in `test_freshness.py`. The gate is the page dropping `STARTING`, not a week number.
2. **The two unattended scheduled runs Phase 0 is "done when",** and `ssm_secret`'s botocore errors
   escaping SPEC-phase0 §9's exit-1 clause as a traceback.

`PHASE-0.md`'s status block is stale — it reports 536 tests and "Uncommitted: nothing", both of
which predate three sessions of work. Its §1–§7 item marks are still accurate.

# Phase 1 — the model, the predictions, the pages

Progress against `SPEC-phase1.md`. Phase 0's tracking stays in `PHASE-0.md`; its two
carry-overs are listed at the bottom of this file because they still gate the "one Saturday end to
end" that §11 defines done as, and neither is on the Phase 1 code path.

The rule that decides a mark, unchanged from Phase 0: **a module with exhaustive offline tests and
no live run is `[~]`, not `[x]`.** Nothing in this phase has run against the real bucket yet, so
every item below is at best `[~]` on that axis — the marks record whether the code and its tests
exist, and the "verified by" column says what was actually run.

## Where this stands (2026-08-28)

§3 is complete and the Elo state loop is closed: something writes state, something rebuilds it from
`raw/` alone, and the two are compared by a command that exits 1 when they disagree.

| | |
|---|---|
| Tests | **695 passing, 22 skipped**, `ruff check .` clean |
| Landed | `fa40c16` (§3.1–§3.5 and the five §3 decisions). This session's state work is uncommitted |
| Next | §4, the prediction log. It is unblocked now: `predict` needs the `elo_state` key §4.2 puts in its model block, and states exist |
| Blocked on a human | nothing in Phase 1. Phase 0's in-season Sagarin capture still stands |

Verified this session, in `cfb/`:

| Command | Result |
|---|---|
| `uv run pytest` | `695 passed, 22 skipped in 12.56s` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run cfb elo seed --season 2026 --store file://…` | exit 0, `week=preseason teams=266` |
| `uv run cfb elo advance --season 2026 --week {1,2,3}` | exit 0 each, `season_games=1,2,3` |
| `uv run cfb elo replay --season 2026 --through-week 03` | exit 0, `elo_verify result=ok` — **§11 step 5, green** |
| `uv run cfb elo seed` on a season in progress | exit 1, `SeedStateError` |

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
        land. **`cfb score` must use the same rule or step 5 fails;** `replay._hfa_for` is the one
        place it lives
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

**The sharp edge is worth removing, and §5 is where.** A cleaner rule exists: partition batches by
*time window* rather than by game week, so week N's state is every game kicking off before week
N+1 opens. That is contiguous by construction, makes backward regeneration safe, and needs the
committed calendar, which `advance` does not currently read. It also changes what
`elo/week=01` means, which is why it was not done here — `replay --through-week` is week-scoped and
`tests/test_replay.py` asserts that. **Decide this when `cfb score` lands.**

**`cfb elo advance` is not in §9's command list.** §8 gives the Elo update to the Sunday `cfb score`
run, which is §5 and does not exist. Without something writing a week state, `cfb elo replay` has
nothing to check and step 5 verifies nothing — so the command exists now and `cfb score` will call
the same `advance()`. Fold it in or keep it as a debugging verb; either is fine, but do not end up
with two implementations.

---

## 4. The prediction log — not started

- [ ] `predictions/season=2026/week=NN/<ts>.json`, write-once, one object per week
- [ ] The §4.2 shape, including the `model` block that names the HFA snapshot, the seed page and
      the `elo_state` key the run started from
- [ ] `predictions/index.json` — the one mutable object, derived and rebuildable from a listing
- [ ] `cfb predict --season 2026 --week N`, defaulting to the week about to be played
- [ ] Closing lines from CFBD `/lines`, home perspective, `null` when not yet posted
- [ ] IAM: `s3:PutObject` on `predictions/*` and **no** `s3:DeleteObject` (§4.1). This is the whole
      of the integrity story §1.1 keeps and it is a Terraform change, not code

## 5. Scoring — not started

- [ ] `elo/scoring.py`, `score_week()`, joining on `cfbd_game_id` (§5.1)
- [ ] Every §5.2 failure mode raises: `UnscoredGameError` for a result with no prediction, for a
      completed game with no result, and for an id that matched while the teams did not
- [ ] §5.3's figures, for Texas and the full slate separately, with sample sizes attached
- [ ] The Elo advance moves into `cfb score` — see the note in §3 above
- [ ] `scored/season=2026/week=NN/<ts>.json`

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
- [ ] `cfb predict`, `cfb score`, `cfb publish`, `cfb note`
- [x] §9.1 records the five errors this phase adds to Phase 0 §9's hierarchy

---

## Carried over from Phase 0

Neither is on the Phase 1 code path, and both still gate §11's "one Saturday end to end".

1. **An in-season Sagarin capture, by hand.** Closes the date formats in
   `parse_page_date_stamp`, the `"in-season"` branch of `parse_page_state`, and the two PROVISIONAL
   assertions in `test_freshness.py`. The gate is the page dropping `STARTING`, not a week number.
2. **The two unattended scheduled runs Phase 0 is "done when",** and `ssm_secret`'s botocore errors
   escaping SPEC-phase0 §9's exit-1 clause as a traceback.

`PHASE-0.md`'s status block is stale — it reports 536 tests and "Uncommitted: nothing", both of
which predate three sessions of work. Its §1–§7 item marks are still accurate.

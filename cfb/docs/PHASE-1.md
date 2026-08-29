# Phase 1 — the model, the predictions, the pages

Progress against `SPEC-phase1.md`. Phase 0's tracking stays in `PHASE-0.md`; its two
carry-overs are listed at the bottom of this file because they still gate the "one Saturday end to
end" that §11 defines done as, and neither is on the Phase 1 code path.

The rule that decides a mark, unchanged from Phase 0: **a module with exhaustive offline tests and
no live run is `[~]`, not `[x]`.** Nothing in this phase has run against the real bucket yet, so
every item below is at best `[~]` on that axis — the marks record whether the code and its tests
exist, and the "verified by" column says what was actually run.

## Where this stands (2026-08-29) — Phase 1 closed, follow-ups landing

Every section of SPEC-phase1 is implemented, live and scheduled. What has landed
since is follow-up work: a wrong constant, a blocked command, and a page that
showed one static number.

| | |
|---|---|
| Tests | **985 passing, 23 skipped** in Python, **7 Playwright** specs, `ruff check .` clean, both `terraform validate` clean, `npm run build` clean |
| Live | `/cfb`, `/cfb/slate`, `/cfb/accuracy` |
| Next | Nothing until the season exercises it. Then the historical backfill, which is what turns the model's constants from conventional numbers into fitted ones |
| Blocked | nothing |
| Blocked on a human | Phase 0's in-season Sagarin capture, and the first weekly note |

### The schedule from here

| | | |
|---|---|---|
| Sun **Aug 30** 12:00 / 12:30 | `cfb-cfbd`, `cfb-score` | First firing of `cfb-score`. Expect a green **skip** — week 1 does not end until 09-08 — and a green `cfb elo replay`, which was the blocker fixed below |
| Tue **Sep 1** | `cfb-sagarin` | The first in-season capture, which is also Phase 0's outstanding carry-over |
| Thu **Sep 3** 12:00 | `cfb-predict` | `coming_week` returns **"02"**, because CFBD's week 1 opened on 08-29 |
| Fri **Sep 4** 12:00 | `cfb-publish` | First firing of the SLO. `/cfb` must still show **Texas State on 09-05**, a week 1 game, which is what the look-ahead exists for |
| Sun **Sep 13** | `cfb-score` | **The one to watch.** First real scoring run, against week 1's partial log, and the first time `forecast_from` does anything outside a test. Also the first `elo/week=NN` state, so the rating chart gets its second point |

### What is left, honestly

Phase 1's deliverable was "one Saturday end to end with no manual intervention".
Every part exists; **it has not yet happened.** Until it does:

- **`cfb score` has never run against real results.** Every scoring test is
  constructed, which §5.2's failure modes require anyway — no vendor publishes a
  game whose id matches a prediction and whose teams do not.
- **The production backtest waits on week 1 closing** (2026-09-07). §5.2 cannot
  distinguish a failed join from a game in progress.
- **No weekly note exists**, so §7's MDX plumbing and `/cfb/notes/[slug]` are
  unbuilt. There is nothing to render until a week has been scored.

---|---|
| Tests | **968 passing, 23 skipped**, `ruff check .` clean, both `terraform validate` clean, `npm run build` clean |
| Landed | §3–§8 through PRs #44–#48 |
| Next | Nothing until the season exercises it. Then Phase 2's backfill — the thing that turns `K`, `ELO_PER_POINT` and `MOV_DENOMINATOR_FLOOR` from conventional numbers into fitted ones |
| Blocked | nothing. The `cfb elo replay` blocker found during §3.1's rescale is fixed — see below |
| Blocked on a human | Phase 0's in-season Sagarin capture, and the first weekly note |

### The schedule from here

The first scheduled runs are **days away, not a week**:

| | | |
|---|---|---|
| Sun **Aug 30** 12:00 / 12:30 | `cfb-cfbd`, `cfb-score` | First firing of `cfb-score`. Expect a green **skip**: week 1 does not end until 09-08, so `last_completed_week` is `None` |
| Tue **Sep 1** | `cfb-sagarin` | The first in-season capture, which is also Phase 0's outstanding carry-over |
| Thu **Sep 3** 12:00 | `cfb-predict` | First firing. `coming_week` returns **"02"**, because CFBD's week 1 opened on 08-29 |
| Fri **Sep 4** 12:00 | `cfb-publish` | First firing of the SLO. `/cfb` must still show **Texas State on 09-05**, a week 1 game, which is what the look-ahead exists for |
| Sun **Sep 13** | `cfb-score` | The first real scoring run, against week 1's **partial** log |

**Sunday Sep 13 is the one to watch.** It is the first time `cfb score` runs
against real results, and the first time `forecast_from` does anything outside a
test: week 1's log covers 150 of its 171 modelled games, and §5.2's first failure
mode has to treat the other 21 as unforecastable rather than as failed joins.

### What is left, honestly

Phase 1's deliverable was "one Saturday end to end with no manual intervention".
Every part exists; **it has not yet happened.** Until it does:

- **`cfb score` has never run against real results.** Every scoring test is
  constructed, which §5.2's failure modes require anyway — no vendor publishes a
  game whose id matches a prediction and whose teams do not.
- **The production backtest waits on week 1 closing** (2026-09-07). §5.2 cannot
  distinguish a failed join from a game in progress.
- **No weekly note exists**, so §7's MDX plumbing and `/cfb/notes/[slug]` are
  unbuilt. There is nothing to render until a week has been scored.

---|---|
| Tests | **931 passing, 23 skipped**, `ruff check .` clean, both `terraform validate` clean, `npm run build` clean |
| Landed | §3–§8 through PRs #44, #45 and #46. This session's §8 workflows, tests and README are uncommitted |
| Next | Phase 2's backfill — the thing that turns `K`, `ELO_PER_POINT` and `MOV_DENOMINATOR_FLOOR` from conventional numbers into fitted ones |
| Blocked | nothing |
| Blocked on a human | Phase 0's in-season Sagarin capture, and the first weekly note |

Verified this session:

| Command | Result |
|---|---|
| `uv run pytest` | `931 passed, 23 skipped in 21.76s` |
| `uv run ruff check .` | `All checks passed!` |
| all six cfb workflows parsed | crons match §8's table exactly |

### What is left, honestly

Phase 1's deliverable was "one Saturday end to end with no manual intervention".
Every part of that now exists, but **it has not yet happened** — the pipeline came
online mid-week-1 and the first fully unattended cycle is the week of September 8.
Until then:

- **`cfb score` has never run against real results.** Every scoring test is
  constructed, which §5.2's failure modes require anyway — no vendor publishes a
  game whose id matches a prediction and whose teams do not.
- **The production backtest is waiting on week 1 to close** (2026-09-07). §5.2
  cannot distinguish a failed join from a game in progress.
- **No weekly note exists**, so §7's MDX plumbing and `/cfb/notes/[slug]` are
  unbuilt. There is nothing to render until a week has been scored.

---|---|
| Tests | **865 passing, 23 skipped**, `ruff check .` clean, both `terraform validate` clean, `npm run build` clean |
| Landed | §3–§7 through PR #44 and #45. This session's slate and backtest work is uncommitted |
| Next | **§8's three workflows.** Everything runs today because a person types the commands; the crons are what make it a pipeline |
| Blocked | nothing |
| Blocked on a human | Phase 0's in-season Sagarin capture |

Live and verified by `curl`:

| URL | |
|---|---|
| `/cfb/` | 200 |
| `/cfb/slate/` | 200 |
| `/cfb/accuracy/` | 200 |
| `/cfb/data/next-game.json` | 200, `cache-control: public, max-age=300, s-maxage=3600`, `server: AmazonS3` |
| `/cfb/data/slate.json` | 200 — week 02, **120 games**, 7 priced, Ohio State at Texas flagged |
| `/cfb/data/accuracy.json` | 200 |

**The deploy pipeline does invalidate CloudFront, and an earlier note here said it does not.**
`travispollardcom-deploy` has four stages: Source (CodeStar on `main`) → Build → Deploy (S3) →
`IndalidateCDN`, a Lambda called `invalidate` with
`{"distributionId": "E30OWLCN533D8K", "objectPaths": ["/*"]}`. `DetectChanges` is `false` but a
**WebhookV2** trigger drives it: PR #45 merged at 04:19:56Z, the pipeline started at 04:20:02Z and
succeeded. The earlier claim came from grepping the repo, and the stage is console-created like the
rest of the pipeline, so the repo could not see it. No manual invalidation is needed after a site
deploy.

Run this session:

| Command | Result |
|---|---|
| `cfb fetch cfbd --resource lines --week 2` | exit 0 — 86 games, 7 with a spread two weeks out |
| `cfb publish --week 2` | exit 0, three keys, `slate_games=120 slate_priced=7` |
| `cfb backtest --season 2026 --week 1` (production) | exit 1, `UnscoredGameError` — **correct**, see §"Backtesting" |
| `cfb backtest` against a completed week | exit 0, `games=3 ats=2-0 sagarin_r=1.0`, written to `backtest/` |

---|---|
| Tests | **865 passing, 23 skipped**, `ruff check .` clean, both `terraform validate` clean, `npm run build` clean |
| Landed | §3-§6 through PR #44, `12afc15` and `4fe2977`. This session's work is uncommitted |
| Next | Deploy the frontend (merge to `main`; CodePipeline builds from there and does **not** invalidate — see the deploy-pipeline note). Then §8's three workflows |
| Blocked | nothing |
| Blocked on a human | the frontend deploy, and Phase 0's in-season Sagarin capture |

Run against **production** this session:

| Command | Result |
|---|---|
| `terraform apply` (root, by hand) | OAC created, distribution updated in place |
| `cfb fetch cfbd --resource games --week 1` | exit 0 — 455 games, which is where the division problem surfaced |
| `cfb predict --week 1` | exit 1, `ReplayError` — **correct**: week 1 opened before the first Sagarin capture existed |
| `cfb fetch cfbd --resource games --week 2` | exit 0 |
| `cfb predict --week 2` | exit 0, `games=120 hfa=2.41 benchmarked=0 priced=0` |
| `cfb publish --week 2` | exit 0, both keys written, **`invalidated ... invalidation=I4VKE563KALNI7LATB9JQX0D90`** |
| `curl https://travispollard.com/cfb/data/next-game.json` | **200**, `server: AmazonS3`, `cache-control: public, max-age=300, s-maxage=3600` |
| `cfb fetch cfbd --resource lines --week 2` | exit 0 — 86 games, **7 carry a spread**; books have not posted most of a slate two weeks out |
| `cfb predict --week 2` again, then `cfb publish` | exit 0, `priced=7`; the regenerate is a second write-once key and `publish` took the newest, which is the designed flow for "a line arrived" |

The live document reads Texas vs Ohio State, week 2, kickoff `2026-09-12T23:30Z`, `national_rank: 5`
of 138, `market_line: -1.5` from DraftKings — the market has Texas by 1.5 and the model has Ohio
State by 2.2, which is the first real disagreement the page has shown — — and `accuracy.json` reads `through_week: null` with every mean `null`, which is the legal
empty-season shape §6.4 requires rather than a page claiming zeros.

Also verified, offline:

| Command | Result |
|---|---|
| `uv run pytest` | `865 passed, 23 skipped in 18.75s` — the division filter disturbed no fixture |
| `cfb note --season 2026 --week 1` | exit 0, `games=3 texas=True ats=2-0` |
| a second `cfb note` for the same week | **two keys under `notes/`**, first kept |
| `cfb note` on an unscored week | exit 1, `ReplayError` naming `cfb score` |

**Not verified: what the pages look like.** `/cfb` and `/cfb/accuracy` build, serve, and carry the
right strings, and the live production documents are staged against a local build — but no browser
was available in either session, so nobody has looked at them.

---|---|
| Tests | **865 passing, 23 skipped**, `ruff check .` clean, both `terraform validate` clean, `npm run build` clean |
| Landed | §3-§5 and §6's generator, merged through PR #44 plus `12afc15`. This session's delivery work is uncommitted |
| Next | Run the root apply, then look at the live pages. After that: the unit tests three sessions have now had to skip, and §7/§8 |
| Blocked | **the root `terraform apply`** — refused by the harness permission classifier, not by AWS. Plan is clean. See §6 |
| Blocked on a decision | §6.1 and §7 still contradict each other about notes |
| Blocked on a human | nothing in Phase 1. Phase 0's in-season Sagarin capture still stands |

Verified this session:

| Command | Result |
|---|---|
| `uv run pytest` | `865 passed, 23 skipped in 17.85s` |
| `uv run ruff check .` | `All checks passed!` |
| `terraform -chdir=terraform validate` (cfb) | `Success! The configuration is valid.` |
| `terraform validate` (root) | `Success! The configuration is valid.` |
| `terraform plan` (root) | `1 to add, 1 to change, 0 to destroy` — OAC created, distribution updated **in place** |
| `./download-tfvars.sh` | `Download complete! 538 bytes.` — after the two fixes below; it could not read the parameter at all from Git Bash before |
| `npm run build` | clean; `/cfb` 1.34 kB and `/cfb/accuracy` 2.17 kB, both prerendered static |
| the built site served locally | `/cfb/` 200, `/cfb/accuracy/` 200, `/cfb/data/next-game.json` 200 |
| the §3.7 endpoints, exercised directly | `0.001 -> <1%`, `0.999 -> >99%`, `0.9899 -> 99%`, `0.4138 -> 41%` |
| a `null` mean vs a real zero | `null -> "—"`, `0.0 -> "0.00"` — §5.3's rule surviving to the last step |

**Not verified: what the pages actually look like.** No browser was available this session, so the
routes are confirmed to build, to serve, to carry the right strings in the shipped bundle, and to
format correctly — but nobody has looked at them. That is the first thing to do after the apply.

**Earlier sessions' verifications, still standing:** the `cfb elo seed` / `predict` / `score` /
`publish` runs and the eleven publish and four scoring command checks, in this file's git history.

---|---|
| Tests | **865 passing, 23 skipped**, `ruff check .` clean, `terraform validate` clean |
| Landed | `fa40c16` (§3), `c9ec3c9`+`03a054a` (§4), `084c6d9`+`931c35a` (§5), `50a4a09` (crosswalk id inheritance), all merged in PR #44. This session's §6 generator is uncommitted |
| Next | §6's delivery half — the root-stack CloudFront work (Phase 0 §10.2) and `frontend/app/cfb/`, which does not exist yet |
| Blocked | nothing technical |
| Blocked on a decision | **§6.1 and §7 contradict each other about notes** — see §6 below |
| Blocked on a human | nothing in Phase 1. Phase 0's in-season Sagarin capture still stands |

Verified this session, in `cfb/`, against three `file://` stores: the seeded 2026 of last session,
a variants store whose weeks 02-05 each exercise one publish rule, and a copy carrying two extra
scored weeks:

| Command | Result |
|---|---|
| `uv run pytest` | `865 passed, 23 skipped in 26.18s` |
| `uv run ruff check .` | `All checks passed!` |
| `terraform -chdir=terraform validate` | `Success! The configuration is valid.` |
| `uv run cfb publish --season 2026 --week 1` | exit 0, both keys, `team=Texas opponent="Ohio State" national_rank=5 scored_through=01` |
| the same run, republished | **2 objects before, 2 after** — these are the mutable end of the pipeline |
| Texas home vs the worst-rated team (2147 Elo gap) | page reads `win_probability 0.999`, `predictions/` still holds `0.9999970913013003` — **§3.7's clamp, publish-side only** |
| Texas *away* at Ohio State | stored `+6.98 / p(home) 0.7549`, published `-6.98 / p(Texas) 0.2451`; the two probabilities sum to `1.0000` |
| a slate with no Texas game | exit 0, `game: null`, `as_of` still populated, `opponent=bye` on the log line |
| a slate with Texas on it twice | exit 1, `ReplayError` naming games 405 and 406 |
| a week with no predictions stored | exit 1, `ReplayError` — the §8 SLO failing loudly |
| a season with nothing scored yet | exit 0, `through_week: null`, every mean `null`, `by_week: []` |
| a season where week 02's `sagarin_r` is 0.85 and week 03's is 0.95 | `active: false, retired_week: "02", current_r: 0.95` — **retirement is one-way** |

`national_rank: 5` of 138 FBS teams is the rank SPEC §1.2's table records off the Sagarin page, so
the seed identity that §4 found in `predicted_margin` shows up in the ranking too.

**Earlier sessions' verifications, still standing:** the `cfb elo seed` / `predict` / `score` /
`elo replay` runs and the four `cfb score` sabotage cases, all listed in the git history of this file.

---|---|
| Tests | **865 passing, 23 skipped**, `ruff check .` clean, `terraform validate` clean |
| Landed | `fa40c16` (§3), `c9ec3c9`+`03a054a` (§4), `084c6d9` (§5's library), `50a4a09` (crosswalk id inheritance). This session's `cfb score` work is uncommitted |
| Next | §6, the JSON contract and the three routes. §3.6's contamination series is now unblocked — `sagarin_r` is in the scored document |
| Blocked | nothing |
| Blocked on a human | nothing in Phase 1. Phase 0's in-season Sagarin capture still stands |

Verified this session, in `cfb/`, against a `file://` store holding a seeded 2026, a week 1 slate
of three games, a `/lines` capture pricing two of them, and a `/games` capture taken after they
were played:

| Command | Result |
|---|---|
| `uv run pytest` | `865 passed, 23 skipped in 31.31s` |
| `uv run ruff check .` | `All checks passed!` |
| `terraform -chdir=terraform validate` | `Success! The configuration is valid.` |
| `uv run cfb elo seed --season 2026` | exit 0, `week=preseason teams=266` |
| `uv run cfb predict --season 2026 --week 1` | exit 0, `games=3 benchmarked=2 priced=2 indexed=1` |
| `uv run cfb score --season 2026 --week 1` | exit 0, `games=3 unplayed=0 ats=2-0 mae=7.23 brier=0.300` |
| `uv run cfb elo replay --season 2026 --through-week 01` | exit 0, `elo_verify result=ok` against the state **`cfb score` wrote** — **§11 step 5, green** |
| a second `cfb score` for the same week | exit 0, **second `scored/` and `elo/` key written, first of each kept** |
| `cfb score` with a post-kickoff regenerate as the newest prediction | exit 0, and it graded the **pre-kickoff** generation |
| `cfb score` when every stored generation postdates its slate | exit 1, `ReplayError`, **nothing written** |
| `cfb score` with a result no prediction covered | exit 1, `UnscoredGameError` naming game 999 |
| `cfb score` with the week's `/games` capture removed | exit 1, `ReplayError`, **nothing written** |
| `cfb score` on a week captured mid-slate | exit 0, `games=1 unplayed=2` — unplayed is counted, not an error |
| `cfb score` with no `--week` before any week completed | exit 0, `result=skip reason=no_completed_week` |

The scored document for that week reads `sagarin_r: 1.0`, `texas.mae: 9.16` on one game and
`texas.market_mae: null` — the first is §3.6's opening correlation arriving at exactly 1.0 as §4
predicted it would, and the last two are §5.3's "every mean carries its own denominator" showing up
in a real document rather than in a test.

**Earlier sessions' verifications, still standing:** `cfb elo advance --week {1,2,3}` exit 0 each,
`cfb elo seed` on a season in progress exit 1 with `SeedStateError`, a second `cfb predict` writing
a second key and keeping the first.

---

## 3. The model

- [x] **§3.1 the scale.** `ELO_PER_POINT = 20` (was 28 — see the follow-up below), and the
      win-probability `elo_diff` is the
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
- [~] **§3.6 the seed contamination series.** The weekly Pearson correlation against Sagarin
      PREDICTOR, and the disclosure that retires the first week `r` falls below 0.90. **No longer
      blocked:** `sagarin_r` is computed and written on every scored week, and week 1 of the
      verification store reads exactly `1.0`, which is the identity §4 predicted. What is left is
      §6's half — reading the series across weeks and publishing the disclosure with it
- [x] **§3.7 the probability clamp.** `[0.001, 0.999]` applied at publish time, unclamped in
      storage so the Brier scores are computed on what the model said.
      `test_probabilities_are_not_clamped_here` pins the storage half and
      `test_publish.py::TestTheClamp` the other, verified against a 2147-Elo mismatch where the
      page reads `0.999` and the stored value is `0.9999970913013003`
  - [x] The justification was stated as "grading on the displayed probability would be circular",
        which is wrong. It is not circular, it is **grading a censored value** — the clamp
        flatters the model at exactly the moments it was most likely to be wrong. The reason is
        simply that a Brier score should measure what the model said, not what the page rendered

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
- [x] **Market lines from CFBD `/lines`**, joined on `cfbd_game_id`, provider-normalized and signed verbatim. See the four findings below

### What the real `/lines` capture changed

The capture is `tests/fixtures/cfbd_lines_2026_week01.json` — a verbatim
`/lines?year=2026&week=1` response, 143 games, 194 line entries. It contradicted the spec in three
places and confirmed a fourth. All four are now in SPEC-phase1 §4.3.

1. **There is no closing line.** The fields are `spread` (the price at capture) and `spreadOpen`;
   nothing in the response has "clos" in its name. §4.2, §5.3 and §6.3 all said "closing line" and
   none of them could have had one — a Thursday generate cannot know a number that does not exist
   until kickoff. Renamed to `market_line` throughout, and the spec now says what it is.
2. **The sign is opposite to `predicted_margin`.** `spread: -29.5` with
   `formattedSpread: "Iowa State -29.5"`, Iowa State home — so negative favours the home team, while
   `predicted_margin` positive favours the home team. Verified across all 194 entries in both
   directions with no exceptions. The value is stored verbatim and `sources.market_home_margin` is
   the **single** conversion site. Without the flip every §5.3 ATS record is complete, plausible and
   backwards.
3. **Providers need normalizing before selection.** One book, two spellings: `DraftKings` (131) and
   `Draft Kings` (12). Selecting first drops the 12 games whose only line uses the second. And
   selection is a real decision — the two books **disagree on 21 of 143 games** — so
   `PROVIDER_PREFERENCE` changes the published number. DraftKings leads on coverage (143 of 143 vs
   Bovada's 51), and the resolved book is carried into the row so §6.3's `line_source` is a fact
   rather than the `"consensus"` guess it used to be. An unrecognised provider raises.
4. **Null stays legal and is never a zero.** In *this* capture every game has a line and no `spread`
   is null, so the null path is the join: a slate game with no entry in the `/lines` response.
   Asserted at both the selection and document level, because zero is a pick'em and conflating them
   would put unpriced games into the ATS record as pushes against a spread nobody quoted.

Verified end to end: `cfb predict` over the real capture produced
`games=4 benchmarked=1 priced=3`, with Portland State reading `model=-12.91, market=+24.5` — both
saying the away team is favoured, which is only true once the sign is converted.

### What §4 confirmed about §3.6

§3.6 argues that a week 1 prediction *is* Sagarin's prediction, and uses that to justify the seed
disclosure. It is not an approximation: the seed is `1500 + (rating - mean) * ELO_PER_POINT`, so an Elo gap
over `ELO_PER_POINT` is exactly a Sagarin rating gap, and adding the same HFA reproduces PREDICTOR to the
floating-point bit. The first real generated document shows `predicted_margin` and
`sagarin_predictor_margin` both `10.67` on one game and both `6.2` on a neutral-site one.

So **§3.6's Pearson correlation opens the season at exactly 1.0**, not near it, and
`TestTheWeekOneContamination` pins the identity that makes it so.

## 5. Scoring

- [x] `elo/scoring.py`, `score_week()`, joining on `cfbd_game_id` (§5.1)
- [x] Every §5.2 failure mode raises `UnscoredGameError`, and **each is confirmed by sabotage**
      rather than by assertion alone: the implementation was broken four ways and the tests that
      should have caught each one did (8, 5, 4 and 3 failures respectively)
- [x] §5.3's figures, for Texas and the full slate separately, every mean carrying its own
      denominator and `null` rather than `0.0` on an empty population
- [x] The Elo advance moves into `cfb score`. **The same `replay.advance`, imported, not restated** —
      a second implementation of "which games, which names, which HFA" is exactly what §11 step 5
      would stop being able to detect, since it would be comparing a rebuild against a cache that
      drifted for reasons the model never saw. `cfb elo advance` stays as the verb for a week with
      nothing to score against: a backfill, or bringing a season's state up to date
- [x] `scored/season=2026/week=NN/<ts>.json` — the write-once document and `cfb score`. Verified by
      command: two runs of the same week leave two `scored/` keys and two `elo/` keys, and
      `cfb elo replay --through-week 01` reproduces the state the scoring run wrote
- [x] **Beating the line goes through `sources.market_home_margin`.** Dropping the conversion fails
      8 tests, and fails them as reversed *verdicts* rather than as different numbers
- [x] **A null `market_line` is excluded and counted**, never scored as a push. Scoring one as a
      push fails 5 tests, every one of them on the denominator

### Two decisions §5 settled

**`score_week`'s signature departs from §5.2's sketch, and both departures are forced.** `predictions`
is a `PredictionLog` rather than a dict because the third failure mode compares teams and a mapping of
margins cannot; the dict predates §4 giving the log a type. `results_fetched_at` is added because the
second failure mode needs to know whether a game was played and `/games` carries no `completed` flag —
so the boundary is the evidence, matching §3.3's HFA rule. SPEC-phase1 §5.2 now records the real
signature.

**A model margin exactly equal to the market's is excluded, not pushed**, counted in its own
`excluded_no_edge`. A push is a position that tied; this is the absence of a position. The ATS record
carries five counters whose sum is the slate, which is the property that makes a game falling out of it
visible at all.
- [x] **The HFA rule is already shared and cannot drift.** `sources.hfa_at` is the single
      implementation of §3.3, and `hfa_for` (a game's own kickoff) and `predict` (a slate's first
      kickoff) are two boundaries into it. `cfb score` uses `hfa_for` by importing it, not by
      restating it — which is what keeps §11 step 5 honest

### What `cfb score` decided that §5 leaves open

Four things, all load-bearing enough to write down.

**Which generation gets graded, and it is not the newest.** A week can hold several prediction
objects — write-once means a regenerate adds a key rather than replacing one — and nothing stops one
of them being written on Sunday. `predictions_to_score` takes the newest generation written
**strictly before its own slate's first kickoff**, and refuses the week if none qualifies. Grading a
post-kickoff regenerate would publish an accuracy figure for a forecast made with the results in
hand, which is the single overclaim SPEC-phase1 1.1 gives up git in order not to make.

**The boundary comes from each candidate document's own slate, not from the week's results.** They
are the same number in the ordinary week and they come apart in the case that matters: a game moved
*into* the week from an earlier one has already been played by the time the week is predicted, so a
boundary taken from the results would sit in the past and reject a perfectly honest Thursday
generation. Asking each candidate whether it preceded the games *it* claimed is the only question
worth asking, and it is the same check §11 step 1 runs from the bucket side — so this is step 1's
property being used rather than only asserted.

Verified by command, not only by construction: with a generation stamped `2026-09-07T00:00Z` sitting
as the newest object for a week whose slate opened `2026-09-03T23:00Z`, `cfb score` graded the
`2026-08-29T02:55:14Z` one. With the pre-kickoff generation deleted, it exits 1 and writes nothing.

**`ScoredWeek` gained `results_fetched_at`, because it is a model input.** §5.2 decides "unplayed, or
a join that failed" against when the results were captured rather than against a clock, so the same
week re-scored against a different capture can legitimately reach a different verdict. A document
that recorded which predictions it graded but not which evidence it graded them against could not
say why. It comes from the manifest of the target week's own `/games` capture — `sources.results_capture`
— and never from `now`, for the reason §3.3's HFA rule gives: a wall clock cannot be replayed.

**Everything is read before anything is written.** Found by sabotage rather than by design: with the
week's `/games` capture deleted, the first version of the command advanced the Elo state (legitimately
folding zero games), wrote it, and *then* went red on the missing capture. The state was harmless — a
replay of the same empty `raw/` reproduces it and the next run absorbs the week — but it is an object
asserting a week happened that nobody has evidence for yet. The command now resolves the capture, the
slate and the prediction generation first, so a run that cannot do its job writes nothing at all.

The two writes stay in §8's order once they start. They are genuinely independent — the advance reads
nothing from `predictions/` and the scoring reads no rating — which is the only reason it is safe for
one command to do both.

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

## 6. The JSON contract — the generator, not yet the delivery

- [x] `next-game.json` and `accuracy.json`, built by `src/cfb/publish/` and written by `cfb publish`
- [x] ~~`notes/index.json`, `notes/<slug>.json`~~ — **dropped, decided 2026-08-29.** §7 wins: the
      finished note is MDX committed to the repo, so the route does zero fetches and the pipeline's
      only note output is §7's scaffold. SPEC §6.1 records it
- [x] The §6.2 envelope on both documents. Both carry the publish run's `season` and `week`, so the
      two pages are visibly one run; `accuracy.json` adds `through_week` because a Friday publish is
      for a week nobody has played
- [x] Routes that render a "data is newer than this page" state rather than throwing on an unknown
      `schema_version`. `frontend/app/cfb/` and `frontend/app/cfb/accuracy/` exist and both build
      into the static export. `components/cfb/useCfbDocument.ts` is the one place the version is
      checked, and it distinguishes newer from older rather than treating any mismatch as an error
- [x] **§3.7's presentational clamp.** Applied on the way out and nowhere else. Verified against a
      2147-Elo mismatch: the page reads `0.999` and `predictions/` still holds
      `0.9999970913013003`, which is the whole point of the rule
- [x] `<1%` / `>99%` at the endpoints. **The clamp and this are one rule in two halves and
      neither works alone:** clamping without this still prints "100%", because `0.999` rounds
      there. Verified across the clamp's own endpoints — `0.001 -> <1%`, `0.999 -> >99%`,
      `0.9899 -> 99%`
- [x] `Cache-Control`, set at upload. `storage.put_json` takes it and only the S3 store honours it
      — the other two are behind no CDN and have no response to put a header on. The value lives in
      `publish.CACHE_CONTROL` because the `/cfb/data/*` behaviour runs on CachingOptimized, which
      takes freshness from the origin rather than from a TTL in Terraform: **one place decides how
      long a document is good for, and it is the place that knows what the document is**
- [x] The CloudFront invalidation, in `src/cfb/cdn.py`. A separate step and a separate log line from
      the upload, because the upload is what makes the numbers exist and this only makes them
      visible sooner — a failure here is a slow page, not a wrong one. Skipped loudly
      (`reason=not_a_cdn_origin`) when the store is not `s3://`, since a `file://` publish has no
      edge cache and a run reporting an invalidation it never made is the one Friday line nobody
      could trust
- [~] The root-stack CloudFront work (Phase 0 §10.2). **Written, validated, planned — not applied.**
      `modules/cloudfront` now takes `extra_origins` and `extra_behaviors`, both defaulting to empty
      so a caller passing neither gets the distribution it already had; `cfb-wiring.tf`'s Phase 0
      sketch is now live code. The plan is **1 to add, 1 to change, 0 to destroy** — the OAC created
      and the distribution updated in place. See the blocker below

### The generator recomputes nothing, and that is the design

Every number in these two documents was written to the bucket by an earlier run and is read back:
`predictions/` for the forecast, `scored/` for the record, `elo/` for the ratings the forecast used.
A publish step that recomputed anything would be a second implementation of the model living on the
**read** path, where no replay check looks — and the first sign of it would be a page disagreeing
with the prediction log it was built from. `scoring.accuracy_of` and `scoring.calibration_of` were
promoted from private for this: season-to-date is that same computation over the union of the rows.

**Season-to-date is recomputed from the rows, never averaged over the weekly means.** The weeks have
different denominators — a three-game Tuesday against a sixty-game Saturday — so a mean of means
would weight them equally and publish a number the rows do not support.

Two things happen here and nowhere else, both presentational: §3.7's clamp, and rendered names.
`Crosswalk.display_name` is new and returns the CFBD spelling, because `southern-california` would
otherwise render as "Southern California" for a team every page in the country calls USC.

### What building the documents decided

- **`next-game.json` publishes the *newest* generation; `cfb score` grades the newest *pre-kickoff*
  one.** The two commands want opposite things and both are right. A regenerate exists because
  someone wanted the newer number on the site, so the page should show it; grading it would claim a
  forecast made with the results in hand.
- **A bye is a nullable `game`, not an absent document.** `as_of` is still populated — the ratings
  are true whether or not there is a fixture, and a blanked page would say less than a stated bye.
- **Everything is re-signed to the subject team except `market_line`.** The line is the book's own
  quote and is printed beside `line_source`; converting it would publish a number no book posted
  under a name saying one did.
- **`national_rank` is among the FBS**, with `fbs_teams` beside it. Texas comes out rank 5 of 138 on
  the preseason seed, which is the rank SPEC §1.2's table records from the Sagarin page — the seed
  identity showing up one more place.
- **A team appearing twice on a slate raises.** One team plays once a week, so it is a duplicated
  game or two names collapsing to one canonical id, and `/cfb` would otherwise render whichever came
  first.
- **An empty season publishes.** Zero games, every mean `null`, `through_week` `null`. The Friday
  before the season's first Sunday is exactly that, and refusing would fail §8's SLO over results
  nobody could have had.
- **SPEC §6.4's `ats` string became an object.** §5.3 requires the sample size to travel with the
  record and §6.4's sketch dropped it; §5.3 governs. Recorded in the spec.

### Blocked: the root apply did not run

The Terraform is written, validated and planned, and the plan is clean:

```
# aws_cloudfront_origin_access_control.cfb_data will be created
# module.cloudfront.aws_cloudfront_distribution.this will be updated in-place
Plan: 1 to add, 1 to change, 0 to destroy.
```

`terraform apply` was **refused by the harness permission classifier**, not by AWS and not by a
problem with the configuration. Nothing was applied, so `/cfb/data/*` is not yet reachable over
the CDN and the two routes have nothing to fetch in production. Re-running the apply is the whole
of what is left:

```bash
export AWS_PROFILE=tp-site
./download-tfvars.sh && terraform init && terraform plan   # expect the three lines above
terraform apply
```

**What the plan settled on the way past.** `terraform-state-ownership` recorded an open question
from 2026-05-14: the Spacelift stack injects an HTTP backend while `provider.tf` declares an S3 one,
and it was unknown which held the live state — the hazard being that a plan against an empty S3
backend would try to *create* the Route 53 zone, the ACM cert and the distribution. It does not.
The plan is an in-place update to an existing distribution with every other resource unchanged, so
**S3 is the live state and is current**. The Spacelift stack presumably still fails at init; that is
a separate problem and not one this phase needs solved.

### Two prerequisites that were broken before this session could plan

Both are repo-root scripts rather than `cfb/`, and both were in the way rather than beside it.

- **`download-tfvars.sh` could not read the parameter from Git Bash.** It passes
  `/projects/cloudresume/terraform/tfvars` as an argument, and MSYS rewrites anything shaped like an
  absolute path into a Windows one before `aws.exe` sees it — so the call asked for
  `C:/Program Files/Git/projects/...` and came back `ParameterNotFound` for a parameter that plainly
  exists. That sends you to IAM, or to the wrong-account trap in `cfb/CLAUDE.md`, and it is neither.
  Fixed with `MSYS_NO_PATHCONV=1`.
- **It also truncated `terraform.tfvars` on failure and reported success.** `> terraform.tfvars`
  is opened by the shell *before* the command runs, so a failed read left an empty file behind and
  the script still printed "Download complete!". The next `terraform plan` then prompts for every
  variable, two commands away from the cause. It now writes through a temp file, refuses an empty
  read, and prints the byte count.
- **`upload-tfvars.sh` had the same path-mangling bug, and worse consequences.** With `--overwrite`,
  a mangled `--name` does not fail — it creates a *second* parameter named after a directory on `C:`
  while the real one goes stale, and the run reports success. Same fix, plus a refusal to upload an
  empty file.

### Resolved: §6.1 and §7 disagreed about notes, and §7 won

§6.1 published `notes/index.json` and `notes/<slug>.json`; §7 said the finished note is MDX committed
under `frontend/app/cfb/notes/`, "because it is prose that ships with the site rather than data the
pipeline owns". Both could not be the source for `/cfb/notes/[slug]`.

**MDX wins and the two JSON documents are dropped.** The route does zero fetches, which satisfies
§6.1's one-fetch rule more completely than a document would have, and the pipeline's only note output
is the scaffold. Recorded in SPEC §6.1 and §7.

## 6b. The slate, and backtesting

Neither is in SPEC §6.1's three routes. Both are recorded here rather than silently added.

- [x] **`cfb/data/slate.json` and `/cfb/slate`.** §6.1 named three routes and none of them showed
      the other 119 games the model forecasts every week — the pipeline was computing every row and
      publishing one. Its own route rather than a section of `/cfb`, so §6.1's one-fetch-per-page
      rule survives and the front page stays small
  - [x] **Home perspective, unlike `next-game.json`.** A slate has no subject team to re-sign
        against, so it keeps the storage convention (§4.2). Mixing the two conventions in one
        contract is how a page draws a favourite as an underdog
  - [x] `featured` marks the rows involving the team `next-game.json` is about, so the page can
        highlight without knowing who that is
  - [x] `priced` travels with the slate, for the reason every denominator in §5.3 does
- [x] **`cfb backtest --season --week`**, and §6.4's `backtest` block

### What the first real read-through of the pages changed

Reading `/cfb` as a visitor rather than as its author found three things, and all three were the
same mistake: **a signed number is not a readable claim.**

- **The two sign conventions run in opposite directions.** `predicted_margin` is positive for the
  team it is about; a market line is *negative* for the team it favours (§4.3). The page printed
  `-2.2 for Texas` beside `Market line -1.5 ... home team's line` and expected a reader to decode
  both, plus work out which team was home. Every number now goes through `format.favorite` and the
  page prints **"Ohio State by 2.2"** and **"Texas by 1.5"**, with the raw quote kept as a footnote
  for anyone checking the book. `marketFavorite` is the single place the market's sign is flipped.
- **A bare "41%" said nothing about whose probability it was.** It is now labelled
  "Texas win probability" with "chance Texas wins outright" under it. The old caption — "never 0%
  or 100%" — was §3.7 explaining itself in the one place a reader wanted the subject, and has moved
  to a footnote.
- **`next-game.json` gained `neutral_site`.** The page said "X is at home" about games played on
  neither campus. §5.1 already records that the two sources can disagree about who is nominally
  home at a neutral site, so the document now carries the flag and the page says "Neutral site — X
  is nominally the home team."

All three apply to every game, not just Texas: `/cfb/slate`'s 120 rows use the same `favorite`
helpers and each row names its own home team.

- [x] **The section has its own theme and its own navigation.** `/cfb` inherited whichever site-wide
      theme the visitor had chosen, which put a college football page in Dracula. A scoped
      `longhorns` daisyUI theme (burnt orange) is applied with `data-theme` on the section's layout
      wrapper rather than on `<html>`, so it cannot fight `HeaderWithTheme`'s selector. `CfbNav`
      replaces the site header inside the section — with the three routes, a current-page marker,
      and a link back — because the site header's theme dropdown would appear to do nothing here.
- [x] **`/cfb` is reachable from the site.** It had no inbound link at all; `HeaderWithTheme` now
      carries "CFB Forecast"

### Backtesting: what it is, and the two things that keep it honest

Week 1 of 2026 opened at `2026-08-27T22:00Z` and the earliest Sagarin capture this project holds is
`2026-08-28T16:50Z`, so §3.3 refuses to read an HFA for it and `cfb predict --week 1` exits 1. That
refusal is correct and stays. The seed, though, contains no week 1 information — it is the preseason
page, which predates every game — so the numbers *are* honestly derivable. What is missing is not the
arithmetic but the evidence of having been written first.

Three things keep it separate, all structural rather than conventions someone has to remember:

- it never writes to `predictions/`, so nothing can grade it as a forecast;
- it writes to `backtest/`, a prefix `scored_weeks` does not read by default, so it cannot reach the
  published season-to-date record;
- §6.4 renders it in its own block, and the page labels it "not a prediction".

**And a week 1 backtest measures Sagarin, not this model.** The seed is `1500 + (rating - mean) * ELO_PER_POINT`
and the preseason page's rating columns are identical (§1.2), so a week 1 forecast reproduces
PREDICTOR to the floating-point bit — `sagarin_r` comes out at exactly `1.0`, confirmed by command.
`Backtest.measures_the_seed` carries that into the document and the page says it in words, because a
figure labelled "backtest" and nothing more would read as the model's own.

- [ ] **The production backtest has not run, and cannot until week 1 ends (2026-09-07).** §5.2's
      second failure mode is "kicked off before the capture and came back with no score", which
      cannot distinguish a failed join from a game **in progress** — CFBD's `/games` carries no
      `completed` flag, which is why `results_fetched_at` exists at all. Week 1 spans 08-27 to 09-07,
      so a capture taken during it almost always catches a live game. Two attempts, two different
      games mid-flight. Relaxing the rule for the backtest would relax it for the Sunday run too, so
      it waits.

## 7. The weekly note

- [x] `src/cfb/publish/notes.py` and `cfb note --season --week`, writing the scaffold from the
      newest scored generation of a week. Verified by command against a three-week store
- [x] §7's content: Texas's game (prediction, result, error, line, verdict), the full-slate figures
      with every denominator attached, and the week's biggest miss by absolute error
- [x] **Team names are rendered, not canonical ids.** Caught by reading the first real scaffold,
      which said "Texas hosted ohio-state" and "north-carolina at tcu" — §6.3's rule broken in the
      most visible place there is, a document written to be published as prose
- [x] The key is `notes/season=YYYY/week=NN/<ts>.md`, not §7's fixed `scaffold.md`. A fixed name
      cannot be written twice under `put_bytes` with no `s3:DeleteObject`, so a rescore or a botched
      first edit would fail on the write. Verified: a second `cfb note` for the same week leaves two
      keys
- [x] `biggest_miss` breaks ties on the game id, so one `ScoredWeek` always produces the same
      scaffold. A note that changed between two runs over nothing would undercut the one property
      the whole prediction log exists to have
- [x] No `in_season` guard, deliberately — this is the only command run by hand rather than by a
      schedule, and skipping over the date would answer a question nobody asked
- [ ] The MDX plumbing and `/cfb/notes/[slug]`. **Not built, and nothing to render yet:** production
      has no scored week, so there is no scaffold and no note. Needs `@next/mdx` wired into
      `next.config.ts`, a note index page, and the first real note

## 8. Workflows

- [x] `cfb-score.yml` (Sun 12:30), `cfb-predict.yml` (Thu 12:00), `cfb-publish.yml` (Fri 12:00).
      All five cfb workflows parse and their crons match §8's table
- [x] The Friday publish is the SLO. No retry loop — a prediction published after kickoff is not a
      prediction — and the job **confirms the site is serving what it just published** rather than
      trusting the upload. `cfb publish` can succeed against the bucket while the CDN serves a stale
      or missing object, and the whole point of Friday is that the site is right before kickoff
- [x] **The Sunday 30-minute gap is the only ordering constraint between any two workflows.**
      `cfb score` reads the `/games` capture `cfb-cfbd.yml` writes, and §5.2 decides "unplayed, or a
      join that failed" against when that capture was taken. Actions cron drifts 5-15 minutes under
      load, so thirty is the margin rather than the interval
- [x] `cfb-score.yml` also runs **§11 step 5 every week** rather than by hand: it replays the season
      from `raw/` and exits 1 if the stored state disagrees. A stored state nobody can regenerate is
      a second source of truth wearing a cache's clothes, and nothing else would ever notice
- [x] `--week` is a `workflow_dispatch` input only. The scheduled path passes nothing and the CLI
      reads the committed calendar, so no workflow contains week arithmetic
  - [x] `cfb elo replay --season` became optional for this. A `--season $(date -u +%Y)` in YAML
        would have been both the arithmetic these files exist to avoid and wrong every January — a
        January date belongs to the season that started the previous August, which `_season_of`
        already knows

## Tests

The gap three sessions had to leave open. **931 passing, up from 865.**

- [x] `tests/test_divisions.py` (18) — `RawGame.is_modelled` and the `week_slate` filter, including
      the exact shape that stopped the first production run: a partially-scored D-II row that must
      not redden a Friday, and an in-scope one that must still raise
- [x] `tests/test_publish.py` (31) — the clamp is publish-side only, away games are re-signed and
      the two probabilities sum to one, `market_line` is *not* re-signed, a bye yields `game: null`
      with `as_of` intact, a team on the slate twice raises, the rank is FBS-only, an empty season is
      publishable with every mean `null`, and the seed disclosure does not un-retire
- [x] `tests/test_commands.py` (17) — `score`, `publish`, `note` and `backtest` driven through
      `cli.main`, so argument parsing, week defaults and the exit-code contract are exercised rather
      than assumed
  - [x] The four discriminating cases: `score` grades the pre-kickoff generation while `publish`
        takes the newest; a week whose every generation postdates its slate writes **nothing**, not
        even the Elo state; a missing `/games` capture leaves `elo/` untouched; `backtest` writes
        only under `backtest/`
  - [x] `fails()` asserts exit 1 and a message on stderr rather than using `pytest.raises`. SPEC-phase0
        §9 makes `main` *return* on a `CfbError`, so a test expecting an exception would have been
        asserting the opposite of the contract — which is how three of them were written first
- [x] A week 1 backtest correlates with Sagarin at exactly **1.0**, pinning the seed identity that
      `measures_the_seed` reports

## 9. CLI

- [x] `cfb elo replay --season --through-week`
- [x] `cfb elo seed --season [--force]`
- [x] `cfb elo advance --season --week` *(not in §9's list; see the note in §3)*
- [x] `cfb predict --season --week [--force]`
- [x] `cfb score --season --week [--force]`, defaulting to `calendar.last_completed_week`
- [x] `cfb publish --season --week [--force]`, defaulting to `calendar.coming_week` — the same
      default `predict` uses, because Thursday's forecast and Friday's page are one week
- [x] `cfb note --season --week`, defaulting to `calendar.last_completed_week`
- [x] `cfb backtest --season --week` *(not in §9's list; see §6b)*
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

§2 gives `publish/__init__.py` an entry and this session filled it. `publish/notes.py` is still
unwritten and stays that way until the notes contradiction above is settled.

§2 does give `elo/scoring.py` an entry, and `cfb score` did not need a fourth module: `scored_key`
and `write_scored` sit beside `score_week` for the same reason `write_predictions` sits beside
`predict_week`, and the three readers `cfb score` needs from the prediction log
(`read_predictions`, `prediction_generations`, `predictions_to_score`) sit in `predict.py`, which
already owns the key format they parse. `sources.results_capture` is the one genuinely new
selector, and it belongs where every other "read this out of `raw/`" does.

---

## What broke: a test harness that passed locally and hung in CI

**The class of failure a local run cannot catch**, and the reason the deploy of
PR #50 never landed. CodeBuild build `5ce40816` ran 969 seconds in POST_BUILD and
was stopped by hand.

```
21:28:09  npx playwright install          20s, no --with-deps
21:29:00  npm run build                   30s, SUCCEEDED -- the export is fine
21:29:00  npx playwright test
          7 failed, 17 passed (31.3s)     ← the tests finished here
          Serving HTML report at http://localhost:9323. Press Ctrl+C to quit.
                                          ← ~938s of nothing
```

**The tests took 31 seconds. The other ~938 was the HTML reporter.** Playwright's
`html` reporter starts a web server and blocks when a run has failures; it
suppresses that when `process.env.CI` is set, and **CodeBuild does not set `CI`**,
so the container behaved exactly like a laptop and waited for a Ctrl+C nobody
could send.

Neither of the two suspects was the hang:

- **`visitor-counter.spec.ts` is exonerated.** It ran in all three projects and
  passed. It uses `request` rather than `page`, so it needs no browser and
  reached the live API fine.
- **`npx playwright install` without `--with-deps` is real, and caused the
  failures rather than the hang.** Only webkit could not launch — missing
  `libicudata.so.66`, `libwoff2dec.so.1.0.2`, `libx264.so` and eleven more.
  Chromium and firefox ran clean. All 7 failures are webkit. The image also warns
  its OS is unsupported and falls back to an ubuntu20.04 build, which is why the
  gap surfaces on webkit first.

So the chain is: missing system libraries → 7 webkit failures → failures trigger
the report server → unbounded block.

### Three fixes, in order of what actually mattered

- [x] **`globalTimeout: 5 * 60 * 1000`** — the guard that was missing. **A per-test
      timeout could not have caught this, because no test was running.** Five
      minutes is roughly ten times the suite's honest runtime, so it bounds a hang
      without failing a slow day. It exists because the next unbounded thing will
      not be a reporter
- [x] **`reporter: [['html', { open: 'never' }], ['line']]`** — the specific
      cause. Writes the report without serving it, whether or not `CI` is set
- [x] **`npx playwright install --with-deps`** in `buildspec.yml`, and `CI=true`
      on the test command as belt to the config's braces — Playwright reads `CI`
      to suppress the server, retry flaky specs, and forbid `test.only`, and
      CodeBuild sets none of it

### Verified by reproducing the failure, not by reading the docs

A local run with a deliberately failing spec:

| | before | after |
|---|---|---|
| Reporter line | `Serving HTML report … Press Ctrl+C to quit.` | `To open last HTML report run:` |
| Wall time | 969s, stopped by hand | **10s** |
| Exit code on failure | — | **1** |
| Exit code when green | — | **0** |

That last pair matters as much as the timing: a fix that stopped the hang by
swallowing the failure would have left CI green on a broken build.

## OUTSTANDING: the v2 documents have not been published

**Deliberate, not forgotten.** PR #50 renamed `national_rank` to `model_rank` and
moved the published contract to version 2. The release order for a breaking
rename is **routes first, then publish**, so that a page never meets a document it
cannot read. The routes were merged at `2026-08-29T21:27Z` and the deploy was
still running when this session ended.

Until the publish runs, `/cfb/data/*` still carries **version 1** documents with
`national_rank`. That is fine and is what the dual-version support is for: the
deployed page accepts `{1, 2}` and reads either spelling, so the site is correct
either way. What is missing is only the *new* content — `history`, `last_result`,
`opponent_model_rank` — which the page renders as absent.

To finish it, once the pipeline shows `Succeeded`:

```bash
export AWS_PROFILE=tp-site
aws codepipeline list-pipeline-executions --pipeline-name travispollardcom-deploy --max-items 1
cd cfb && uv run cfb publish --season 2026 --week 1
```

Then confirm the live document carries `model_rank` and the page shows "Elo rank".
The Friday `cfb-publish` cron would also do it unattended on 09-04; running it by
hand only makes the new sections appear sooner.

**Version 1 support in the page can be dropped after that publish**, and should
be — it exists only to make this one release seamless.

## Follow-up: every rank is labelled as this model's own

A bare "#5" on a college football page reads as **AP** by default, and this model
will disagree with AP visibly and often — it is arithmetic on margins with no
human input.

- [x] **`as_of.national_rank` renamed to `model_rank`**, `opponent_rank` to
      `opponent_model_rank`, `RatingPoint.rank` to `model_rank`. The pages say
      "Elo rank" and "…of 138 FBS teams, by this model", and the opponent reads
      "Texas State is 81st of 138 by this model"
- [x] **A rename is breaking, so §6.2's own rule applies and the version moved.**
      This is the first use of the mechanism as written: a page reading the old
      name off a new document gets `undefined` and renders "#undefined"
  - [x] **The published contract now versions separately from stored documents.**
        `PUBLISHED_SCHEMA_VERSION = 2` in `publish/`, distinct from
        `elo.SCHEMA_VERSION`. They version different things — one is read by a
        deployed page, the other by later runs of this pipeline — and bumping one
        number for both would make every archived prediction log look changed by
        a site edit
  - [x] **The page accepts `{1, 2}`, so the rename ships without an outage.**
        Routes deploy before the pipeline republishes, so the page reads a v1
        document first and a v2 one after; accepting both means neither side ever
        sees "data is newer than this page". Version 1 support is transitional and
        can be dropped after the next publish
  - [x] Verified that widening to a set did not blunt the mechanism: an unknown
        version **still** shows the stale state
- [x] **The Python models can no longer read a v1 document, and that is correct.**
      The pipeline writes published documents and never reads them back, so
      nothing in Python must open one. The page is the only reader that has to
      handle both, and it is checked in a browser rather than by assumption

## Follow-up: §3.1's numbers, before and after

Run against the calibration table:

| Margin | at 28 | at 20 | normal, σ=15 | was off by | now off by |
|---|---|---|---|---|---|
| 1 | 54.0% | 52.9% | 52.7% | +1.4% | +0.2% |
| 3 | 61.9% | 58.5% | 57.9% | +3.9% | +0.6% |
| 7 | 75.6% | 69.1% | 68.0% | **+7.6%** | +1.2% |
| 10 | 83.4% | 76.0% | 74.8% | **+8.6%** | +1.2% |
| 14 | 90.5% | 83.4% | 82.5% | +8.1% | +0.9% |
| 21 | 96.7% | 91.8% | 91.9% | +4.8% | −0.1% |

Mean absolute gap to the reference: **5.7% → 0.7%, 88% closer.**

And what each scale claims about how far college margins scatter:

| Margin | σ implied at 28 | σ implied at 20 |
|---|---|---|
| 7 | 10.1 | 14.0 |
| 14 | 10.7 | 14.5 |
| 21 | 11.4 | 15.1 |

The evidence puts it at **14–16**. The old scale was not slightly off; it was
describing a different sport.

## Follow-up: the page stops being static

Three additions to `/cfb`, all pure projections of documents already in the bucket. No new CFBD calls.

- [x] **(a) Rating and rank over time.** `history` on `next-game.json`, from `season_states` — one
      listing and one read per state, the same walk `advance` already does. Newest generation per
      week, because a re-advanced week writes a second object and both survive (§3.5), so taking every
      state would draw one week twice at two ratings
  - [x] **The chart refuses to draw fewer than two points**, and that refusal is the feature. The
        first `elo/week=NN` state lands **2026-09-13** — `cfb score` grades the last *completed* week
        and CFBD's week 1 runs to 09-08 — so for two weeks the series is the preseason seed alone, and
        a line through one point is indistinguishable from a broken chart. `/cfb` shows the rating and
        says the series has not started. Below four points it says so too: a record, not yet a shape
  - [x] Inline SVG, no chart library. Seventeen points of two numbers is smaller than the dependency
        that would draw it
- [x] **(b) The final score.** `ScoredGame.home_points` / `away_points`, carried from `RawGame` rather
      than re-derived, and `LastResult` on `next-game.json` for the page. It is the only block on
      `/cfb` that says what happened rather than what will — a page that only ever predicts is
      asserting a record it never shows
  - [x] **Both optional, and not cosmetically.** `scored/` is write-once, so every week already stored
        was written before these existed and cannot gain them. A required field would have made the
        whole archive unreadable the moment it shipped. Pinned by two tests that validate the exact
        shapes sitting in the bucket
- [x] **(c) Opponent context.** `opponent_rank` and `opponent_elo` from the same state `as_of` names,
      so the two standings on the page cannot be from different weeks. `null` rank for an FCS
      opponent — the FBS table has no place for one
  - [x] Texas State is **FBS** (Sun Belt), which a first draft of the test assumed otherwise. Real
        data: Texas State is #81 of 138, which is what makes "Texas by 39.3" legible

### `schema_version` is not bumped, and §6.2 now says why

All three are additive optional fields. An older page ignores a key it does not know and a newer page
renders the absence, so nothing is misread and the mechanism has nothing to protect against.

Bumping would have *caused* the outcome it exists to prevent — every visitor in front of "data is
newer than this page" for the window between publish and deploy — in exchange for nothing. Worse, it
would degrade the mechanism: fire it for changes that break nothing and nobody distinguishes the one
time it means something. §6.2 now records the rule: **the version moves for a renamed field, a
removed field, or a changed meaning, and for nothing else.**

- [x] The release rule is ordering instead: **deploy the routes, then publish.**
- [x] **That window is covered by a test rather than an assumption.** A new page reading an old
      document is the *first* thing that happens in production on every such release, and the failure
      it guards type-checks perfectly: `history` is absent rather than empty, so `doc.history.map(...)`
      throws and the page renders nothing while TypeScript is satisfied.
      `frontend/tests/cfb-old-document.spec.ts` renders the real document that was live on 2026-08-29
      against the new build, and the new shape beside it
  - [x] `frontend/tests/serve-out.mjs` serves the export for Playwright — node's `http` and `fs`, no
        dependency — and `playwright.config.ts` gained a `webServer`. The existing visitor-counter
        spec talks to a live API and ignores it

### Candidate, not this session: remaining schedule and projected wins

Summing win probabilities across Texas's remaining games gives an expected-wins number, and the
schedule with per-game odds is the natural payoff of already forecasting all 120 games. It needs a
**season-wide `/games` pull** rather than the week-by-week one the pipeline does now — one extra CFBD
call against a budget currently spending ~30 of 1,000 a month. Everything else it needs already
exists.

## Resolved: the replay bound, and why `cfb elo replay` could not run for 2026

**Fixed. `cfb elo replay --season 2026` exits 0.** It could not before, at any scale:

```
ReplayError: no Sagarin snapshot for season 2026 carrying hfa['predictor'] was captured
before game 401866532 (Maine at Towson, 2026-08-27T22:00:00+00:00).
```

`replay` folds every **completed** game, and week 1's include nineteen that kicked off on 08-27 and
08-28 — before the first Sagarin capture this project ever took (08-28T16:50Z). §3.3 prices a game
from the newest snapshot captured strictly before its kickoff, so those games have no HFA and never
will. `cfb-score.yml` runs `cfb elo replay` as its last step, so **the scheduled Sunday run would have
gone red** on data nobody can retroactively supply.

- [x] **`EloState.folded_from`** — the earliest kickoff an accumulation folded, `null` when it covered
      the season entire. Named to match `PredictionLog.forecast_from`: the same idea on the scoring
      side, and two names for one concept is how the next reader concludes they are different
- [x] **Derived on every run, never stored as a constant.** Computed from the manifests in `raw/`, so
      it restates the evidence rather than becoming the second source of truth §3.5's "state is a
      cache" argument depends on there not being. Pinned by `TestItIsDerivedNotStored`, including a
      case where backfilling an earlier capture moves the bound — which a written-down date could not
      do
- [x] **The skip is provably exactly the unpriceable set.** `hfa_at` fails on one condition only, so
      `kickoff <= earliest` is the complete failure set rather than a heuristic for it, and every
      other missing-HFA case still raises. That is what keeps this from being a catch-all that
      swallows real faults
- [x] **In the state document and compared by `verify`**, exactly rather than tolerantly. Letting
      `null` mean "unbounded, match anything" would have put a permanent hole in the one guarantee
      §3.5 rests on, to paper over a one-time migration
- [x] **SPEC §3.5 records that this is transitional**, with §4.4's corollary carried over: a bound set
      on a season the pipeline was live for is evidence of a **missing capture**, not of a late start
- [x] `tests/test_replay_bound.py` — 11 tests, new file, nothing committed modified

### What a committed test caught, and why it was not obsolete

`test_replay.py::test_no_snapshot_before_a_game_raises_rather_than_defaulting` failed on the first
implementation. It was **not** obsolete-by-design and was not edited.

Its scenario has *one* game and a capture after it, so the bound excluded everything and the replay
quietly returned an empty seed-only state. The test's stated intent — never invent an HFA — was
preserved, but the outcome was materially worse than raising: a store whose only Sagarin capture
postdates the entire season is not "the pipeline came online mid-week", it is a store with no usable
coverage, and reporting "the season has not started" about a season that has is the quiet wrong answer
this module exists to prevent.

So the implementation gained a line the design had not called for: **excluding a season's opening
games is expected; excluding all of them raises.** The test passes unmodified.

### Named step: the state migration, which turned out not to be needed

Planned as a one-time rewrite of stored model state, because a stored state written under the old rule
would disagree with a replay under the new one — correctly, since they folded different game sets.
Recorded here rather than folded into "production work" because a rewrite of stored state should be
findable later.

**It was not necessary, and the check is why that is known rather than assumed.**

| | |
|---|---|
| Before | `elo/season=2026/week=preseason/2026-08-28T223403Z.json`, `elo/season=2026/week=preseason/2026-08-29T194047Z.json` |
| After | unchanged — nothing written, nothing rewritten |

`cfb elo advance` has **never run against the real bucket**: the only stored states are the two
preseason ones (the original, and the re-seed from §3.1's rescale). With no week state stored,
`newest_state_key` returns `None` and `verify` logs a skip rather than comparing — so there was
nothing written under the old rule to migrate.

Two things confirmed along the way, both load-bearing and both now checked rather than believed:

- **`newest_state_key` takes the newest**, `keys[-1]` over a lexicographic listing of fixed-width UTC
  stamps. Write-once means a regenerated state lands beside its predecessor and the newest wins, which
  is what would have made a migration safe.
- **The backward-regeneration hazard did not apply.** §3.5 warns that re-advancing an earlier week
  widens its batch and can strand a later game. Nothing had advanced past week 1 — nothing had
  advanced at all — so the migration would have been safe today and not in general. Had anything been
  downstream, the migration would have been re-advancing every week from the affected one forward, in
  order.

### Verified against production

| Command | Result |
|---|---|
| `cfb elo replay --season 2026` | exit 0, `games=6 snapshots=2 teams=266`, `elo_verify result=skip reason=no_stored_state` |
| `cfb score` (as the schedule runs it, no `--week`) | exit 0, `result=skip reason=no_completed_week` |
| `cfb elo replay` (no `--season`, as `cfb-score.yml` runs it) | exit 0 |

Both steps of tomorrow's `cfb-score.yml` are green.

## Follow-up: ELO_PER_POINT was 28 on reasoning that inverted

§3.1 argued **"28 rather than the conventional 25 because college margins are far wider than the NFL
ones the 25 figure came from."** The observation is right and the inference from it runs backwards.

Hold the 400 divisor fixed: a *higher* `ELO_PER_POINT` maps a margin to a larger Elo gap, and a larger
gap is a *higher* win probability. So raising the constant makes the model **more** confident per
point, and wider scatter argues for a value **below** the NFL figure rather than above it. 28 was on
the wrong side of 25 for a sport with more variance, not less.

**What 28 implied, read back out of its own table.** 7 points → 75.6% → σ 10.1; 14 → 90.5% → 10.7;
21 → 96.7% → 11.4. The model behaved as though college margins scatter with σ ≈ 10.5. The real figure
is 14–16. Concretely: an NFL 7-point favourite wins outright ~70% of the time and a college one
closer to 67%; the model said 75.6%.

- [x] **`ELO_PER_POINT = 20`.** At 20 the logistic tracks a normal with σ = 15 across the range —
      3 pts 58.5 vs 57.9, 7 pts 69.1 vs 68.0, 14 pts 83.4 vs 82.5, 21 pts 91.8 vs 91.9. Verified by
      computation before the change, and pinned in `test_it_tracks_a_normal_with_sigma_15`
- [x] **§3.1 rewritten.** The inverted argument is stated and corrected rather than deleted; the
      "Recalled rate" column is gone. It was approximately the **NFL** curve and the scale had been
      chosen to match it, so the table was the model agreeing with a number imported from the wrong
      sport, presented as corroboration. In its place: the σ 14–16 evidence with its sources
      (FiveThirtyEight's NFL Elo at 25, Staturdays' college Elo at ~20, ~16 vs 13.5 scatter around
      the closing spread, a 12,000-game fit landing on 14.1), and a normal reference curve that is
      labelled as a reference rather than a measurement
- [x] **Only the ratio `ELO_PER_POINT / 400` is meaningful**, stated in §3.1 and pinned by
      `test_only_the_ratio_to_the_divisor_is_meaningful`. The divisor reads like textbook furniture
      and is therefore the one more likely to be left alone while the other is tuned
- [x] **`predicted_margin` is unchanged, and it is asserted rather than assumed.** The constant
      multiplies in `seed` and divides in `predict`, so it cancels: Ohio State 2486 → 2204 while
      every week 1 forecast is bit-identical. §3.6's correlation of exactly 1.0 survives, which is
      what made this safe to change in-season. `test_seed.py::TestTheScaleCancels` checks five scales
      against a formula written out independently of the implementation, plus a control that the Elo
      values *do* move so the test cannot pass on a no-op
  - [x] The invariance holds **at the seed only.** From week 2 on, ratings carry K-scaled deltas
        that do not rescale, so margins genuinely differ — which is the next item
- [x] **`K` is coupled, and the rescale changed responsiveness without changing `K`.** What matters
      is points of margin moved per game, `K / ELO_PER_POINT`: 0.71 at 28, **1.00 at 20 — about 40%
      more responsive.** Probably the right direction for college, given the shorter season and
      greater volatility, but it happened as a *consequence* rather than a decision. Recorded in
      §3.4 and pinned by `test_k_moves_one_point_of_margin_per_unit`, with the note that `K` must not
      be re-tuned without restating it in these units
- [x] **§12 records that 20 is probably still slightly too high.** The σ 14–16 range is scatter
      around *the market's* number, and this model is worse than the market — that is the premise of
      publishing an ATS record — so margins scatter further around our predictions than around a
      book's. Correcting for it points at **17–18**. 20 is used now because §5.3's calibration curve
      is what should settle it, from games this project stored and predicted. Moving to 17 on an
      argument rather than a measurement would repeat the mistake that produced 28

### What the rescale did to the MOV floor, which was not the intent

At 28 the seed spanned 211 to 2486 and **39** of the top team's opponents would have crossed
`MOV_DENOMINATOR_FLOOR` by beating it, 5 of them driving the denominator negative. At 20 the seed
spans 579 to 2204, the widest pairing leaves the denominator at **0.58**, and **none** cross.

Crossing raises rather than clamping silently, so the old scale carried 39 pairings that would have
reddened a run on a legitimate if enormous upset — losing those is good. But a guard that never fires
in production is also a guard nothing exercises there, which is why `mov_denominator` stays public and
directly tested rather than reached only through `update`.

- [x] **§12 now records that the floor is a pure invariant guard rather than a tunable.** Its
      retirement condition was "if the runs it produces turn out to be legitimate upsets rather than
      data faults, it is too high" — and at scale 20 it produces no runs at all, so there is no
      evidence it can ever generate about its own value. A number that cannot be disconfirmed is not
      a tunable.
- [x] **And that it stays anyway**, because §12's own refit expects the calibration curve to push
      `ELO_PER_POINT` toward 17–18, which widens the Elo spread and moves the boundary back toward
      reachable. Removing a guard because the current constant happens to clear it — when the open
      question in that very section is whether the constant should move — would be removing it
      exactly before it is needed.

### Everything that quoted the old numbers

`ELO_PER_POINT` appeared as a literal in seven places beyond its definition — §3.1's table, §3.2's
worked seed values, §3.4's reachability table, §4.2's and §6.3's example documents, the README's
formulas, and three docstrings. All swept, and the derived counts recomputed rather than scaled by
hand.

## Wrap-up: three gaps closed, and one regression caught before it shipped

- [x] **`forecast_from` now reaches the page.** It stopped at `scoring`, which read
      it and threw it away, so a partially-forecast week would have appeared on
      `/cfb/accuracy` as a complete one — the seed disclosure's problem in a new
      place. It is carried into `ScoredWeek`, into §6.4's `by_week`, and rendered
      as a **partial** badge with a note saying the season-to-date count is the
      honest number to read. `SlateDocument` carries it too
- [x] **SPEC §4.4 now says the partial-log path is transitional.** It arises only
      because a pipeline has to come online at some moment, and this one landed
      inside a ten-day week 1. From week 2 every week has snapshots behind it and
      a Thursday run ahead of its whole slate, so `forecast_from` is `null`. The
      spec also records the corollary: if it is ever set on a week the pipeline
      was live for, that is evidence of a **missed run**, not of a start
- [x] **`/cfb/slate` explains its own size.** CFBD's week 1 runs 08-27 to 09-07,
      ten days across both opening Saturdays, so the slate is larger than a normal
      week and its games fall on two weekends. The footnote says that is the
      source's numbering, not a renumbering here, and that games already under way
      are not listed
  - The brief said "the eight games the media calls Week 0". The real number is
    **19**, all FCS, on 08-27 and 08-28 — and they are *not* in the slate at all,
    because they had already kicked off when the forecast was generated. The
    footnote says what is true rather than the count in the brief
- [x] **The look-ahead was six days from reintroducing the bug it fixed.**
      `_next_fixture` searched only weeks at or after the one being published, on
      the reasoning that an earlier week is finished business. `coming_week`
      returns `"02"` from 08-30 onward, so Friday 09-04's publish targets week 2
      while Texas's next game sits in week 1 on 09-05 — and the fence would have
      skipped it. It now searches every week; `kickoff >= now` already drops
      anything played, so looking back is safe and looking only forward was not

## Found this session: /cfb showed the wrong game, and the data was fine

Reported from the live page: it showed *Ohio State at Texas, 9/12* while Texas was
idle that weekend and actually played **Texas State on 9/5**.

**Nothing was mislabelled.** CFBD's `/calendar` puts week 1 at `2026-08-29` to
`2026-09-08` — **ten days, spanning two Saturdays** — so the 9/5 Texas State game
is a CFBD *week 1* game and the 9/12 Ohio State game is week 2. The published
week-2 document was internally correct in every row.

**The bug was three sessions old and mine.** `cfb predict --week 1` had failed, so
week 2 was published instead and called "the honest first week". It failed for
this reason:

```
hfa_at(manifests, before=first_kickoff)   # first_kickoff = 2026-08-27T22:00Z
                                          # earliest Sagarin capture = 2026-08-28T16:50Z
```

`predict_week` bounded the HFA by the **slate's** first kickoff, so one 08-27 FCS
game that predated the first capture this project ever took refused **eight days
of forecastable games with it** — Texas's among them.

### Three fixes, and one option that was wrong

- [x] **A run forecasts only the games that have not kicked off**, and the HFA
      boundary is the first kickoff *among those*. On an ordinary Thursday this
      removes nothing. It matters exactly once a season and it mattered here:
      week 1 now predicts, with 150 games and 122 priced
- [x] **`PredictionLog.forecast_from`** records the boundary when a log is
      partial, and `scoring` reads it. A result that kicked off before the log
      began forecasting was unforecastable, not a failed join — §5.2's first mode
      would otherwise redden week 1's scoring run over the 08-29 games. `None`
      for a whole slate, which is every ordinary week
- [x] **`next-game.json` looks ahead across weeks** for the team's next *unplayed*
      game rather than taking the published week's featured one, and the game
      carries **its own week** so the page cannot label a week 1 game "Week 2".
      This fixes the class rather than the instance: a bye, or any week whose
      game has already been played, would have shown the wrong thing again
- [x] `cfb backtest` passes `retrospective=True` to opt out of the kickoff filter.
      A backtest grades a week that has been played, so the filter would empty its
      slate

**The option originally proposed for this was per-game HFA, and it was wrong.**
`test_predict.py::test_a_snapshot_landing_mid_week_is_not_used` pins a snapshot
captured between two kickoffs and asserts it is *not* used, because "the run never
saw it. §4.2 carries one `hfa` per run for exactly this reason." That test is
right: per-game HFA is correct when reconstructing what was knowable before each
game (`hfa_for`, used by `score` and `replay`) and wrong for predicting, where one
run happens at one moment. Bounding by the first *forecast* kickoff keeps one HFA
per run, keeps that test's guarantee, and fixes the bug.

- [x] Verified live: `/cfb/data/next-game.json` reads `week: "01"`,
      `Texas State`, kickoff `2026-09-05T19:30Z`, model `+39.30`, market `-30.5`
      (DraftKings). `slate.json` went from 120 games and **7** priced to 150 and
      **122**

## Found this session

- **`/games` returns every division, and nothing in this project knew.** The first real capture came
  back with **455 games**: 110 D-III, 109 D-II, 72 FCS-FCS, 51 FBS-FBS, 48 FBS-FCS, 28 FCS-vs-D-II
  and 37 against unclassified NAIA schools. Only **171 have both teams in the crosswalk**, and there
  are **420 distinct unmapped names**. `cfb predict` could never have run against a real response —
  every fixture in the suite is three or four FBS/FCS games. The `/teams` comment in
  `collectors/cfbd.py` shows the project reasoned carefully about FBS+FCS and nobody considered that
  `/games` reaches further down.
  - Fixed by `RawGame.is_modelled` and a filter in `week_slate`. A game is out when either side is
    classified below FCS, or when one side is classified and the other is not — the opponent of an
    NCAA team that the NCAA does not classify is an NAIA school, and there are nine on week 1's
    slate. **Both sides absent means in**, so the crosswalk stays the authority and an unmapped name
    still raises rather than quietly becoming a filter. That is also what keeps every committed
    fixture working: none of them set a classification.
  - The rule selects exactly 171 games — the vendor's classification and this project's crosswalk
    agreeing independently on the same set.
  - **It loses no FBS game, which is what makes it a scope decision rather than a gap.** Week 1: 99
    of 99 games involving an FBS team are kept. Week 2: 86 of 86. Everything excluded is either two
    non-Division-I teams, or an FCS team playing a D-II or NAIA opponent. The deliverable is
    "predictions for every FBS game" and that is at 100%.
  - The residual is a **model-fidelity** point, not a coverage one: an FCS team's game against a
    D-II opponent does not update its Elo, so FCS ratings carry slightly less information into
    FBS-vs-FCS predictions. Roughly 28 games a week league-wide. A Phase 2 idea is a single
    synthetic replacement-level opponent to absorb them; nothing in Phase 1 needs it.
- **The run that found it was stopped by a malformed row in a division that was never ours.**
  `Delta State at Northeastern State`, `home=52 away=None`, on a D-II game that had not kicked off.
  The division filter now runs ahead of the partially-scored check, so a vendor's bookkeeping in
  D-II cannot redden a Friday.
- **Week 1 of 2026 cannot be predicted, and that is correct.** Its slate opens
  `2026-08-27T22:00Z`; the earliest Sagarin snapshot in the bucket is `2026-08-28T16:50Z`. §3.3
  refuses to read an HFA from a page captured after kickoff, so `cfb predict --week 1` exits 1. 17 of
  its games were already final. The pipeline came online mid-week-1 and the honest first week is 02.
- **CFBD's `/calendar` and its `/games` disagree about when week 1 starts.** The calendar says
  `2026-08-29T07:00Z`; `/games` files 55 games before that, the earliest on 08-27. So
  `calendar.coming_week` said "01" while a third of week 1 was already played. Not acted on — the
  calendar is what §9's defaults use and changing that is its own decision — but it is why a
  scheduled Thursday run would have picked the wrong week on the season's first pass.

## Found in earlier sessions

- **There are no real results yet, and there could not be.** The bucket holds no `/games` capture at
  all — only lines, calendar and teams — because the season had not started: week 1's first kickoff is
  `2026-08-29T07:00Z` and `last_completed_week` returns `None`. Every scoring fixture is constructed,
  which the §5.2 failure modes require anyway — no vendor publishes a game whose id matches a
  prediction and whose teams do not. `test_scoring.py::TestARealWeek` is skipped and waiting on the
  first played Saturday.
- **`USC` resolves to `southern-california`, not `usc`.** Found by the team-mismatch check firing on a
  test fixture that had guessed the slug. The check catching its own author is reasonable evidence it
  will catch a vendor.

## Also found in earlier sessions

- **`cfb/lines-wk1.json` is a stray in the repo root.** It is the raw capture, untracked, and it has
  been copied to `tests/fixtures/cfbd_lines_2026_week01.json`. Safe to delete; left alone because it
  is not this session's to remove.
- **A `/lines` response read as *text* on Windows mangles accented team names.** `San José State`
  decodes to `San JosÃ© State` under the cp1252 default and then fails to resolve against a crosswalk
  that has the name correctly. Production was never affected — `sources._rows` is handed bytes and
  `json.loads` detects UTF-8 — but a diagnostic script written the obvious way reports a crosswalk
  gap that does not exist. `_rows` now says why it takes bytes.

## Also found in earlier sessions

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

## Also found in earlier sessions

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

## Found in the §6 generator session

- **`Crosswalk` had no way to render a name.** Publishing needs one — §6.3 puts rendered names in the
  documents — and the only thing available was `entries[id]["cfbd"]` read by hand at the call site.
  `display_name` is now a method, so the "the crosswalk's job ends at this boundary" claim has one
  place to be true in.
- **`scoring._accuracy` and `_calibration` had to become public.** Season-to-date is the same
  computation over the union of every scored week, and the alternative was a second implementation of
  MAE, Brier and the ATS record on the publish path. No test referenced either private name.
- **The root stack has no `/cfb/data/*` behaviour at all.** `modules/cloudfront/main.tf` has one
  origin and no `ordered_cache_behavior`, so Phase 0 §10.2 is not "mostly done" — nothing of it
  exists. cfb's own Terraform is ready and waiting on it: the publisher role already holds
  `cloudfront:CreateInvalidation` and the bucket policy already lets the CDN read `cfb/data/*`.
- **`frontend/app/cfb/` does not exist.** All three routes are unbuilt, so §6's "routes render a
  data-is-newer state rather than throwing" has nothing to hang on yet.
- **`npm run lint` is not configured.** It drops into next's interactive "How would you like to
  configure ESLint?" prompt, so there is no lint gate on the frontend at all. `next build`
  type-checks, which caught nothing this session but is the only static check the routes get.
  Left alone: configuring ESLint is a repo-wide decision, not a §6 one.
- **The frontend routes have no Playwright specs.** The existing suite hits production
  (`tests/visitor-counter.spec.ts` fetches the live API), so a spec for `/cfb` would fail until the
  routes deploy — for the right reason, but noisily. Worth adding in the session that follows the
  first real deploy.
- **The publish generator has no unit tests either**, for the same reason `cfb score` has none: the
  session rules forbid writing under `cfb/tests/`. It is verified by the eleven command runs above,
  four of which are failure cases. **The next session should write them**, and the four worth the
  most are: the clamp is publish-side only, an away game is re-signed and the two probabilities sum
  to one, a bye yields `game: null` with `as_of` intact, and the seed disclosure does not un-retire.

- **The crosswalk's canonical ids were re-derived every season, and now are not.** Found in the
  working tree at the start of this session, reviewed and committed as `50a4a09`. `bootstrap` minted
  every id with `canonical_slug(sagarin_name)`, so a team Sagarin respelled between seasons got a
  different id in each — and 31 of the 266 committed ids are the Sagarin spelling rather than the
  CFBD one, `southern-california` among them. Nothing would have raised: both seasons load, both
  validate, every name resolves, and the team simply has two identities where Phase 2's backfill
  joins. Ids are now inherited by `cfbd_id`. Not Phase 1 work and not on its code path, but it is
  the join Phase 2 is built on.
- **`data/crosswalk/_candidates-2026.yaml` is deleted.** It was scratch, fully absorbed into
  `teams-2026.yaml`, and git history has the similarity scoring if it is ever wanted again.
  `test_crosswalk.py`'s failure message now says so, since it used to point at the file.
- **`cfb/lines-wk1.json` is still a stray in the repo root**, untracked, already copied to
  `tests/fixtures/`. Carried over from last session; still not this session's to remove.
- **`PHASE-0.md`'s status block is still stale**, unchanged from last session's note.
- **The new code has no unit tests, and that is a deliberate gap this session could not close.**
  The session rules forbid writing under `cfb/tests/`, so `cfb score`, `write_scored`,
  `predictions_to_score`, `prediction_generations`, `read_predictions` and
  `sources.results_capture` are verified only by the command runs in the table above — including
  four sabotage runs, which is what the §5.2 modes were held to. The committed suite still passes
  at 865 because it does not reach any of them. **The next session should write them**, and the
  three worth the most are: a post-kickoff regenerate is not the generation graded; a week whose
  every generation postdates its slate exits 1 and writes nothing; and a `/games` capture missing
  for the week leaves `elo/` untouched.

## Carried over from Phase 0

Neither is on the Phase 1 code path, and both still gate §11's "one Saturday end to end".

1. **An in-season Sagarin capture, by hand.** Closes the date formats in
   `parse_page_date_stamp`, the `"in-season"` branch of `parse_page_state`, and the two PROVISIONAL
   assertions in `test_freshness.py`. The gate is the page dropping `STARTING`, not a week number.
2. **The two unattended scheduled runs Phase 0 is "done when",** and `ssm_secret`'s botocore errors
   escaping SPEC-phase0 §9's exit-1 clause as a traceback.

`PHASE-0.md`'s status block is stale — it reports 536 tests and "Uncommitted: nothing", both of
which predate three sessions of work. Its §1–§7 item marks are still accurate.

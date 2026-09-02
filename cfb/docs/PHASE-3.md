# Phase 3 — the challenger, in order

Sequence of work against `SPEC-phase3.md`. Phase 0 and 1 tracking stays in `PHASE-0.md` and
`PHASE-1.md`; Phase 2 never had a file of its own and does not get one retroactively — its record is
the spec, the experiment JSONs, and `git log`.

**This file is a plan, not yet a progress record.** Nothing below has started. The marks follow the
rule the earlier phase files set: **a module with exhaustive offline tests and no live run is `[~]`,
not `[x]`.**

---

## Where this stands (2026-09-01)

| | |
|---|---|
| Phase 2 | Closed and deployed. Elo at 16.0 / 30.0 / 0.05, `models.json` live, `/cfb/models` live |
| Phase 3 | Specified, not started |
| Season | 2026 week 2. Regular season ends **2026-12-12**; postseason runs to 2027-01-28 |
| Target | **A headline switch in 2027, not 2026.** §6.4 needs four weeks of live pre-kickoff evidence after a gate pass, and the only 2026 path lands that switch in the postseason — the worst population to promote a regular-season-fitted model into |
| Urgent | **A1 only.** Everything else can slip without cost |

---

## Which repo does what

> **`travispollard.com/cfb` owns anything that runs unattended or reaches a reader.** Collectors,
> workflows, schemas, the CLI, the published contract, the specs.
>
> **`cfb-model` owns anything that is fitted.** Features, shrinkage constants, estimators,
> evaluation, the experiment record.

**One question decides any item:** does it run on a schedule or reach a page? Production. Does it
produce a number by fitting? Research.

The research side has its own requirements document at `cfb-model/docs/PRD-phase3.md`, in the shape
Phase 2 established: it supersedes SPEC-phase3 §4 in full and §5's implementation, and restates
nothing else.

---

## The three tracks

**A** and **B** are independent and run in parallel. **C** joins them, and cannot start until both
have delivered.

### Track A — production plumbing

Bounded, fully specified, no research risk. **Contains both of the phase's clocks.**

| | Item | Repo | SPEC | Notes |
|---|---|---|---|---|
| `[ ]` | **A1** Roster capture: collector, `raw/roster/` schema, workflow | prod | §3.2 | **Start first.** A clock — see below |
| `[ ]` | **A2** Shadow slot: `models: list[ModelBlock]`, `SCHEMA_VERSION` → 3 | prod | §3.3 | The phase's one schema bump. Blocks C2 |
| `[ ]` | **A3** `cfb fetch roster`, `cfb shadow`, `cfb calibrate` | prod | §8 | `calibrate` reports and never fits |
| `[ ]` | **A4** `RosterBasisError`, `ShadowRoleError`, `CalibrationError` | prod | §9 | Lands with the code that raises each |

**A1 is the only genuinely urgent item in the phase.** Every Thursday that passes uncaptured is a
Thursday the news layer will never cover, and unlike everything else here that cost is
unrecoverable. It is also the cheapest thing in the phase: one collector, one workflow, ~15 CFBD
calls a season.

**A2 is cheap now and expensive later.** If the log cannot hold a second model until after a
challenger passes the gate, C2's four-week clock starts at the worst possible moment. Build the slot
before there is anything to put in it.

### Track B — the model

All of it in `cfb-model`, offline, with no live risk. That separation is what the Phase 2 boundary
bought and this track spends none of it.

| | Item | Repo | SPEC | Notes |
|---|---|---|---|---|
| `[ ]` | **B1** As-of-week feature pipeline + a leakage guard that raises | research | §4.2 | Everything downstream depends on it |
| `[ ]` | **B2** Empirical Bayes shrinkage, `k` fitted per metric | research | §4.3 | Explosiveness wants a much larger `k` than success rate |
| `[ ]` | **B3** Schedule-graph connectivity per week | research | §4.3 | Decides when opponent adjustment is admissible. Also makes the 2020 exclusion quantitative |
| `[ ]` | **B4** Preseason prior, benchmarked against Sagarin's preseason page | research | §4.3 | Pays §4.4's `REGRESSION_TO_MEAN` debt. Wins or loses, it is publishable |
| `[ ]` | **B5** LightGBM two-stage — μ with `init_score`, σ on `log｜residual｜` | research | §4.5 | Fast to iterate. Do this before NGBoost |
| `[ ]` | **B6** NGBoost Student-t | research | §4.5 | The reference implementation |
| `[ ]` | **B7** Serialised artifact production can load | research | PRD-phase3 §3.6 | **Format decided before the estimators, not after** |

**B7 is the item most likely to be discovered late.** A model that only runs inside `cfb-model`
cannot be shadow-run by the live pipeline, and shadow mode is the critical path.

### Track C — evaluation and promotion

| | Item | Repo | SPEC | Notes |
|---|---|---|---|---|
| `[ ]` | **C1** Gate: PIT, 80% coverage, week buckets, on held-out 2024–25 | research | §5 | Criteria are production's; the implementation is research's |
| `[ ]` | **C2** Gate verdict as a committed artifact + the rejected-models section | prod | §6.2 | Publishes a failure as readily as a pass |
| `[ ]` | **C3** Shadow run live | both | §6.1 | Needs A2 + B7 + C1 |
| `[ ]` | **C4** `PROBABILITY_SCALE` — fit in research, pin in production | both | §3.1 | **2027 boundary.** §4.1's freeze; the one-time exception is spent |
| `[ ]` | **C5** Promotion decision | prod | §6.4 | Four weeks of live evidence, or it does not happen |

---

## The order, and what actually blocks what

```
A1 ──────────────────────────────────────────────►  (independent; start now)

A2 ──────────────────────────────┐
                                 ├──► C3 shadow ──► C5 promotion
B1 ─► B2 ─► B5/B6 ─► B7 ─► C1 ───┘
      B3 ─┘
      B4 ─────────────────────────► (independent finding; publishable alone)

C4 ─────────────────────────────────────────────►  (2027 boundary, unblocked)
```

**Only one real dependency chain exists**, and it runs through B1. Everything else is either
independent (A1, B4, C4) or joins late.

---

## Rough shape against the calendar

Dates are the season's, not commitments. Nothing here has a deadline, and that is deliberate —
if the model slips, shadow starts later or in 2027 and nothing breaks.

| When | What |
|---|---|
| **Sept** — weeks 2–5 | A1 live. A2 + A3 + A4. B1 begun |
| **Oct – mid Nov** | B2–B7. Iterating offline; production untouched |
| **~week 12** (mid Nov) | C1 against held-out 2024–25 |
| **Weeks 12–15 + postseason** | C3 shadow-runs. Plumbing proven on real weeks; `cfb backtest` gives the retrospective read |
| **Offseason** | C4 at the 2027 boundary. Refit including the completed 2026 season |
| **2027 week 1** | Challenger shadow-runs from the opener — **switch possible by week 5** if it leads |

**That last row is the argument for starting now.** Without 2026 shadow-running, 2027's four-week
clock begins from a cold plumbing test and the earliest honest switch is deep into the season. With
it, the challenger opens 2027 mechanically proven and the switch can land in September, when it
means something.

---

## What is left, honestly

**Nothing has been built.** The spec is written, the boundary is decided, and the two clocks are
identified. That is the whole of the progress.

Three things that are true now and will be easy to forget:

- **2026 already has a job.** §4.4 reserved it: the live, Sagarin-seeded season that tests whether the
  fitted constants transfer, and "that check is the first thing §11 asks for." Phase 3 must not
  disturb that measurement, which is a second reason the headline switch waits for 2027.
- **Retroactive evidence is not available**, and the word covers two things. `cfb backtest` scores a
  week the model was not live for and is labelled *"not a prediction"* in its own help text — that is
  legitimate and useful. §6.4's four weeks cannot be assembled after the fact, and never will be.
- **`market_line` is not a feature** (§4.4). It would cut MAE immediately and make the whole
  comparison circular. This is the most tempting mistake available in the phase and it is worth
  re-reading the sentence that forbids it before B1 starts.

# SPEC-phase3 — the challenger

**Status:** planning. Nothing in this document has shipped.
**Predecessor:** SPEC-phase2, complete and deployed 2026-09-01.

---

## 1. The one thing to read first

Phase 2 measured the constants and rejected a challenger. Phase 3 has one job: **build a challenger
that beats Elo on the gate, by predicting a distribution instead of a point.**

The Ridge post-mortem found that its failure was structural rather than a bad choice of features.
**Elo predicts a probability and derives a margin; Ridge predicted a margin and derived a
probability.** `ELO_PER_POINT` *is* Elo's calibration parameter and §4.2 fitted it; Ridge's
margin-to-probability map was an afterthought, and a calibration slope of 0.5287 beside an MAE only
5.3% worse is the signature of a bad link rather than bad features.

So the Phase 3 model estimates its own σ. Win probability comes out of a distribution the model
fitted, not from a constant chosen elsewhere. That removes Ridge's defect by construction rather
than patching it.

**Three engineering prerequisites land before any of that, and two of them are clocks that only
start once** (§3). Building them late is the single most expensive mistake available in this phase.

---

## 2. What the phase is for

### 2.1 The gap, stated on one denominator

| System | MAE | Denominator |
|---|---|---|
| The market (Thursday quote) | **11.813** | 2025, 853 shared games |
| This model (Elo) | **13.015** | the same 853 games |
| **Gap** | **1.202** | |

**Both numbers come from the same games, and that is not a formality.** SPEC-phase2 §6.3 forbids
comparing systems across different denominators, and the earlier working figure of "1.27" broke that
rule by differencing 13.08 — the 1,696-game 2024–2025 held-out intersection — against 11.81 from the
853-game 2025 intersection. Two subsets, one subtraction, a number that describes neither. **The gap
is recomputed per season on that season's shared denominator and never carried between them.**

### 2.2 The market line is a Thursday quote, not a close

§7 of Phase 2 is emphatic and it governs here. `market_line` is the price CFBD published when the
Thursday job captured it — between the opening and closing numbers, and closer to the opening. The
literature's ~12.6 MAE figure is for the **closing** line, and its finding is that an ensemble can
beat the opening line while nothing beats the close.

Two consequences, both normative:

- **A win against our `market_line` is a weaker claim than a win against the close**, and any page
  that reports one says which line it beat.
- Our measured 11.813 sits *below* the literature's 12.6. The likely explanation is that the
  intersection is an easier subset than a full slate, not that our capture beats the market's own
  benchmark. **Before 11.813 is treated as a target, that must be checked** — compute the market's
  MAE on the full priced slate and on the intersection, and publish both.

### 2.3 What success means

**The gate is against Elo. The market is a yardstick, not a gate.** A challenger is admitted by
§5, which compares it to this model; the market number says how much of the remaining distance was
covered.

| Level | Criterion |
|---|---|
| **Admission** | §5's gate, in full. Strictly better MAE than Elo, Brier within 2%, calibration in band, and §5.2's distributional checks |
| **Phase target** | MAE ≤ **12.6** on the season's shared denominator — the literature's closing-line figure, and roughly 0.4 better than Elo |
| **Stretch** | Within 0.5 of the season's own measured market number |

**Not "beat the market."** The PRD's position is unchanged and this spec does not revise it:
*landing within a couple of points with well-calibrated probabilities, and saying so plainly, is the
stronger result and the more credible page.* A phase that produced an honest 12.6 with a calibration
slope of 1.00 would be a success. A phase that produced 11.9 with a slope of 0.6 would not.

---

## 3. Engineering prerequisites

These land **before** modelling work, and §3.2 and §3.3 land before anything else in the phase,
because both are clocks that cannot be started retroactively.

### 3.1 `PROBABILITY_SCALE` — one constant is doing two jobs

Elo's held-out calibration slope is **1.1070**, outside the `[0.90, 1.10]` band Phase 2 §5.6 held
the challenger to. §7's own success criterion for that phase was "MAE of roughly 13.6 or better with
a calibration slope inside [0.90, 1.10]"; the shipped model meets the first half decisively and
misses the second by 0.007. The gate is currently asymmetric — the champion is not held to the
criterion the challenger is — and this section closes that.

**The diagnosis: `ELO_PER_POINT` is doing two unrelated jobs.**

| Constant | Job |
|---|---|
| `ELO_PER_POINT` | Elo gap → predicted margin, and the seeding scale |
| `PROBABILITY_SCALE` | predicted margin → log-odds |

§4.2 fitted the pair jointly against **margin** error. That produced a value that serves the first
job well and the second at 1.1070. Decoupling them is the whole fix.

**Isotonic regression is rejected, and the reason is a requirement rather than a preference.** The
PRD requires that margin and probability cannot disagree, pinned by
`test_margin_and_probability_cannot_disagree`, and Phase 1 §3.1 states the identity: win probability
is a deterministic function of predicted margin. Isotonic maps probability to probability with no
expressible relationship back to the margin, so it breaks that identity outright.

**A slope-only Platt scaling does not break it, because it is not a post-hoc transform at all.** The
log-odds are `margin × ELO_PER_POINT / 400`; multiplying log-odds by `a` is arithmetically identical
to using a different scale constant. So the recalibration *is* a second constant, and the identity
survives — probability remains a deterministic function of margin, through its own scale.

```python
# cfb/elo/__init__.py
class ModelConstants(BaseModel):
    ...
    #: None means "the same value as elo_per_point", which is what every document
    #: written before this field existed actually used. A statement about the past,
    #: not a default -- the same distinction PHASE_1 draws.
    probability_scale: float | None = None


def win_probability(margin, *, constants=FITTED):
    scale = constants.probability_scale or constants.elo_per_point
    return 1 / (1 + 10 ** (-(margin * scale) / _LOGISTIC_DIVISOR))
```

Fit it by maximising **held-out log-likelihood** over the single parameter. Expect a value near
`ELO_PER_POINT × 1.1 ≈ 17.6`, and confirm the refit slope lands inside `[0.95, 1.05]` before
shipping. The back-of-envelope is a sanity check on the fit, never a substitute for it.

**Four rules, each with the same reason behind it as its Phase 2 counterpart:**

- **The live pipeline never fits.** Fitting happens in `cfb-model`, writes an experiment JSON, and
  one number crosses into `constants_for(season)`. Identical seam to §4.2's.
- **Frozen within a season** (§4.1), landing at the **2027 boundary**. The one-time in-season
  exception is spent, and unlike the Phase 2 refit nothing forces this one: the cost of waiting is a
  season of slightly hedged probabilities, which is the safe direction to err in.
- **It never touches `predicted_margin`.** MAE is unaffected. This is a Brier and slope fix only,
  and §3.7's `[0.001, 0.999]` clamp stays presentational and applied after.
- **No retroactive recalibration.** The prediction log is append-only. Past predictions keep the
  probabilities they were published with, and the 2026 season is scored on what it actually said.

**No schema bump.** An optional field whose absence reproduces prior behaviour exactly is additive
under Phase 1 §6.2's rule. A test pins `None → elo_per_point` so that stays true.

### 3.2 Thursday-knowable roster capture

Elo's largest single blind spot is that it does not know who is playing. A quarterback change is
worth roughly 5–7 points and Elo cannot see it at all.

**The constraint that shapes the whole design.** This project's credibility rests on forecasts
written before kickoff. Historical data records **who did start**; it does not record **who was
expected to start on Thursday**. Training on actual starters and deploying on Thursday is
retrospective leakage wearing a feature's clothes, and it would produce a backtest that cannot be
reproduced live.

**The resolution is to define the feature so its historical and live versions are the same function
of the same information set.** "Who started the previous game" satisfies that: it was knowable on
Thursday in 2017 and it is knowable on Thursday now, and it is backfillable from `/games/players`
across the whole window with no leakage.

What is *not* backfillable is the **news layer** — who was ruled out on Thursday. That is what
prospective capture buys, and it is the reason this section is a clock: every week it goes
uncaptured is a week it will never cover.

**Storage.** A `raw/` collector like sagarin and cfbd — immutable bytes, date-partitioned, written
before anything parses them, with a `.meta.json` manifest beside it.

```jsonc
// raw/roster/season=2026/week=03/2026-09-17T114500Z.json
{
  "schema_version": 1,
  "source": "cfbd",
  "resource": "roster-status",
  "fetched_at": "2026-09-17T11:45:02.118Z",
  "season": 2026, "week": "03", "week_resolution": "calendar",
  "teams": [
    {
      "team": "texas",                          // canonical id, via the crosswalk
      "expected_qb": {
        "player_id": 4361, "name": "...",
        "basis": "previous-game-starter",       // see below
        "games_started": 3,
        "usage_share": 0.91,
        "last_game_id": 401752913
      },
      "qb_changed_from_last_game": false
    }
  ]
}
```

**`basis` is the load-bearing field.** It records *how* the expectation was formed, and its values
are not interchangeable:

| `basis` | Backfillable | Meaning |
|---|---|---|
| `previous-game-starter` | **yes** | Derived from the last completed game's box score |
| `depth-chart` | no | A published depth chart captured this Thursday |
| `reported-out` | no | The player is reported unavailable |

A consumer filters to the bases that exist for the era it trains on. **A model trained across eras
uses only `previous-game-starter`**, and a model that uses the others declares that it does not
cover the backfill. Without this field a mixed-era training set would silently mean two different
things, which is the failure the whole schema exists to prevent.

**Reading it back uses the rule that already exists.** `sources.hfa_at` is this project's single
implementation of "the newest snapshot captured strictly before the thing being reasoned about," and
Phase 1 §3.3 argues that having one function say so is what stops two copies from drifting.
Roster consumption goes through the same `_at(before=first_kickoff)` rule, and inherits its leakage
guarantee rather than restating it.

**Workflow.** `.github/workflows/cfb-roster.yml`, `cron: "45 11 * * 4"` — fifteen minutes ahead of
`cfb-predict`. Same shape as `cfb-sagarin`: every step a command a human runs locally, the
off-season guard inside `cfb fetch roster` calling `calendar.in_season`, and the failure *is* the
alert.

**Call budget.** One `/games/players` call per week against the **previous** week: ~15 calls a
season against the 1,000/month tier. Written down here because §3.5 of Phase 2 requires the budget
to be measured rather than assumed, and a cheap call is still a call.

### 3.3 Shadow mode, and the schema bump it needs

**§6.4 cannot be satisfied retroactively, and that is the point of it.** A challenger moves to the
front page only when it leads on **live, pre-kickoff games for at least four weeks**. Phase 1 §1.1
gave up git in order to keep one property — that the public record is of forecasts made before
kickoff — and evidence assembled after the fact would spend it.

So there is a mandatory stage between "clears the gate" and "appears anywhere":

> **Shadow mode.** The challenger runs in the Thursday job, writes its forecasts into the
> append-only log beside Elo's, and appears on no page at all. Four weeks later there is a public,
> timestamped record — and only then can §6.4's second row ever fire.

**Build the slot before there is anything to put in it.** If the log cannot hold a second model
until after a challenger passes the gate, the four-week clock starts at the worst possible moment.

**The change.** `PredictionLog.model: ModelBlock` becomes `models: list[ModelBlock]`, one entry per
forecasting system, each carrying its own constants and provenance — the shape `ModelConstants`
already established for `EloState`. Each `PredictedGame` gains a per-model set of forecasts keyed by
model name.

```jsonc
{
  "schema_version": 3,
  "models": [
    { "name": "elo", "elo_per_point": 16.0, "k": 30.0, "probability_scale": null,
      "hfa": 2.41, "hfa_source": "...", "elo_state": "...", "role": "published" },
    { "name": "ngb-t", "version": "2027.1", "base": "elo",
      "fitted_from": "research/experiments/ngb-...json", "role": "shadow" }
  ],
  "games": [
    { "cfbd_game_id": 401752913,
      "forecasts": {
        "elo":   { "predicted_margin": 7.1, "win_probability": 0.68 },
        "ngb-t": { "predicted_margin": 6.4, "win_probability": 0.64, "sigma": 16.8 }
      } }
  ]
}
```

**This is a breaking change to a reader — a field renamed and one whose meaning changed — so
`elo.SCHEMA_VERSION` moves to 3** under Phase 1 §6.2's rule. It is the one bump this phase takes,
which is why §3.1's additive field rides along in the same season rather than costing a second one.

**`role` is normative, not descriptive.** `published` forecasts reach `/cfb/data/*`; `shadow`
forecasts reach the log and nothing else. A reader that does not recognise a role ignores that entry
rather than rendering it, so a shadow model can never leak onto a page by omission.

**`PUBLISHED_SCHEMA_VERSION` is untouched.** No published document gains, loses or renames a field
as a result of this section.

---

## 4. The model

### 4.1 Shape

```
μ(x) = elo_margin(x) + f(x)
σ(x) = exp(g(x))
y    ~ StudentT(ν, μ(x), σ(x))

P(home win) = 1 − F_t(0 | μ, σ, ν)
```

**Three decisions are carried in those four lines.**

**The Elo margin enters as an offset**, not as one feature among many — `init_score` in LightGBM,
the base score in NGBoost. The trees fit only the residual. This is "condition on Elo" in practice:
a challenger that learns nothing reduces to the baseline instead of losing to it, which is the
protection Ridge did not have when it rebuilt team strength from scratch and then had to win on
absolute accuracy.

**σ is a model output.** This is the structural repair. Win probability comes from a distribution
the model estimated, so the defect that produced Ridge's 0.5287 cannot recur in the same form. It
also gives the model a channel it did not have before: it can say "week 3, backup quarterback, I
know less right now" by widening rather than by being wrong confidently.

**Student-t rather than Normal**, because football margins have heavy tails and a Normal
assigns too little density to the blowouts that actually happen. `ν` is fitted, and a fitted `ν`
that comes back large is itself a finding — it says the Normal was adequate and should be reported
as such rather than quietly kept.

### 4.2 Features

| Group | Fields | Notes |
|---|---|---|
| **Baseline** | `elo_diff`, `hfa`, `neutral_site` | `elo_diff` is both the offset and a feature, so the model can learn *where* Elo errs |
| **Sparsity** | `week`, `games_played_home`, `games_played_away` | The channel that lets σ widen in September. Feeds `g(x)` above all |
| **Situational** | `rest_days_home/away`, `travel_km`, `tz_delta`, `altitude_delta` | Elo sees none of it. Derivable from schedule data already held, at no API cost |
| **Efficiency** | opponent-adjusted EPA, success rate, explosiveness differentials | **Shrunk per §4.3.** Raw as-of-week values are what tripped Ridge |
| **Variance** | `pace`, `plays_per_game` | Into `g(x)` only, never `f(x)` — pace moves the spread of the margin, not its centre |
| **Roster** | `qb_changed`, `qb_starts`, `qb_usage_share` | From §3.2, and only at bases the training era supports |

### 4.3 Early-season shrinkage

Every as-of-week metric is shrunk toward a prior before it reaches the model:

```
x̂_shrunk = (n · x̄_observed + k · x_prior) / (n + k)
```

`n` is games observed; `k` is a **fitted pseudo-count**, not a taste parameter. It is the ratio of
between-team variance to within-team game-to-game variance, and the backfill estimates it directly.
**Fit `k` per metric** by minimising walk-forward error — explosiveness will want a much larger `k`
than success rate, because it is far noisier per game, and a single shared `k` would be wrong for
both.

**Shrink the variance, not only the mean.** Shrinking a point estimate toward a prior fixes accuracy
and does nothing for overconfidence. `g(x)` receives `n` directly for exactly this reason.

**Do not opponent-adjust before the schedule graph supports it.** In weeks 1–4 the adjustment is a
ratings solve on a near-disconnected graph across ~136 FBS teams — structurally the same pathology
that justified excluding 2020 under §3.2, except it sits inside the training sample every September.
Compute graph connectivity per week (largest connected component, algebraic connectivity) and either
withhold the adjustment or raise its penalty until the graph connects. **Publishing that diagnostic
also makes the 2020 exclusion argument quantitative rather than asserted**, which it currently is not.

**Where the prior comes from**, and a project that pays a second debt: §4.4 records that
`REGRESSION_TO_MEAN` has no live counterpart at all, because the live model discards the prior season
and takes Sagarin's opinion. So **build a preseason prior from last season's final rating, returning
production, portal net value and recruiting composite, and benchmark it against Sagarin's preseason
page.** If it wins, the live seed changes and §4.4's dangling constant becomes real. If it loses,
that is a publishable negative result and the Sagarin seed is vindicated on evidence rather than on
convenience. Either outcome is worth having and neither needs new collection.

### 4.4 What is excluded, and why

**`market_line` is not a feature.** It would cut MAE immediately and make the entire comparison
circular: a model that has read the line is not an independent forecast of the game, and "we landed
within a point of the market" would become a statement about nothing. It stays a benchmark and never
an input. This is the single most tempting mistake available in this phase and it is forbidden
outright.

**Rivalry and lookahead indicators** are deprioritised as mostly noise at this sample size, and
**coaching-change flags** at four to six per season are not a fittable signal. Neither is banned;
both need to earn a place against §5's gate rather than being assumed useful.

### 4.5 Estimator

**NGBoost with a Student-t head is the reference implementation**, because it produces the two
parameters the gate scores natively rather than through a second stage.

**A two-stage LightGBM is the cross-check** — one model for μ with `init_score`, a second on
`log|residual|` for σ. It is far faster to iterate, and if the two disagree materially that
disagreement is a finding about the fit rather than a tie to break on preference.

Both are prototyped. **The gate decides, not taste**, and the losing architecture's numbers are
recorded either way.

---

## 5. The expanded gate

### 5.1 Phase 2's three criteria are unchanged

```
challenger_mae   <  elo_mae                    strictly
challenger_brier <= elo_brier * 1.02
calibration slope in [0.90, 1.10]
```

Evaluated on held-out seasons, never on training data, on the exact intersection §5.5 regenerates.

**And the band now applies to the incumbent too.** Phase 2 held the challenger to a criterion the
champion missed at 1.1070. §3.1 fixes the champion; from this phase the band is symmetric, and a
champion outside it is a recorded defect rather than an exemption.

### 5.2 σ has to be scored, and slope does not score it

Calibration slope summarises the **centre** of the predictive distribution and says nothing about its
**width**. Once σ is a model output, a model can pass on slope while being systematically too
confident or too vague, and neither shows up. Two additional criteria:

**PIT uniformity.** The probability integral transform `F(y | μ, σ, ν)` over held-out games should be
uniform on `[0, 1]`. Report the histogram and a Kolmogorov–Smirnov statistic.

| PIT shape | Meaning |
|---|---|
| U-shaped | σ too small — outcomes land in the tails more often than claimed |
| Peaked at 0.5 | σ too large — the model is hedging |
| Uniform | The width is honest |

**80% interval coverage.** The 80% predictive interval should contain about 80% of outcomes.
**Reported with `n`**, per Phase 1 §5.3's rule that a sample size always travels with a rate. Gate at
`[0.76, 0.84]`.

A model that fails either is not admitted, and the failure is reported as a width failure rather than
folded into a general "calibration" verdict.

### 5.3 Week-bucketed MAE

**A single season-wide number cannot express the result this phase most expects to produce.** A
challenger that beats Elo from week 6 onward and loses in weeks 1–4 is a useful model with a
cold-start problem, not a failure — and today's gate would reject it wholesale.

So MAE, Brier and coverage are reported **per week bucket**: weeks 1–3, 4–7, 8–12, postseason. The
gate's headline criteria remain season-wide, and the buckets decide something separate: whether a
**week-gated hybrid** — Elo early, challenger late — is the shape that ships. Such a hybrid is a
legitimate architecture and it must declare its switch week as a model constant, frozen within a
season under §4.1 like every other.

### 5.4 Recalibration is a declared component, never a silent one

A challenger may include a post-hoc probability calibration fitted **out of sample**, and if it does,
that step is part of the model: named in its `ModelBlock`, with its fitted parameters recorded, and
its fitting window stated.

Ridge's 0.5287 conflated "the features do not work" with "the link was never calibrated," and those
warrant different verdicts. A challenger is not silently penalised for omitting a step it was never
asked to include — but an undeclared calibration is a model that cannot be reproduced from its own
log, which is the one thing this project does not permit.

---

## 6. Promotion

### 6.1 The path, in order

| Stage | What is true | Where it appears |
|---|---|---|
| **Research** | Fitted and evaluated in `cfb-model` | `research/experiments/*.json` only |
| **Gate** | §5 passed on held-out seasons | `cfb/data/gate/*.json`, and the rejected-models section of `/cfb/models` if it failed |
| **Shadow** | Running live, forecasts logged pre-kickoff | The prediction log only. **No page.** |
| **Published** | ≥ 4 weeks leading Elo on live pre-kickoff games | `slate.json`, `models.json`, and `/cfb/models` |
| **Headline** | §6.4's switch fires | `/cfb`. The week it switched is recorded and never rewritten |

**Clearing the gate does not change `/cfb`**, and §6.4 is unchanged by this document.

### 6.2 A failed challenger is published as a failure

§5.6 of Phase 2 stands: failing the gate is a legitimate outcome, and shipping a model anyway "would
make the rule decorative." Every evaluated challenger gets a committed record in `cfb/data/gate/`
with its criteria, its numbers, its verdict, and a pointer to the experiment artifact that produced
them — and the rejected-models section of `/cfb/models` renders it.

**The rejections are the most credible thing on the site.** A page that only ever showed models that
worked would be a page nobody should believe.

---

## 7. The repo boundary

**Research depends on production. Never the reverse.**

```
cfb-model/                         research; offline; free to churn
  src/cfb_model/phase3/
    features/     as-of-week builders, shrinkage, the leakage guard
    models/       ngboost_t.py, lgbm_two_stage.py
    eval/         walk_forward.py, gate.py, pit.py
  research/experiments/*.json      tracked; every constant traces to one

travispollard.com/cfb/             live; changes only on a gate pass
```

`cfb-model` installs the live package (`uv add --editable ../travispollard.com/cfb`) and imports the
**shipped** Elo rather than reimplementing it. §5.5 requires the baseline be regenerated on identical
games; if the research baseline drifts from production by even one constant the bake-off measures
nothing. A one-way dependency makes that impossible, and it means a change to live Elo correctly
invalidates every research baseline built on it.

**The seam that Phase 2 proved:** an entire grid search, two model architectures and a held-out
evaluation crossed into production as four numbers and one registry entry. Phase 3 uses the same seam
and nothing wider.

---

## 8. CLI additions

```
cfb fetch roster                    §3.2. Immutable capture, off-season guarded
cfb calibrate --season N            §3.1. Reports the measured slope; never writes a constant
cfb shadow --season N --week N      §3.3. Runs registered shadow models, appends to the log
```

`cfb calibrate` **reports and does not fit**. Fitting lives in `cfb-model`; a live command that could
change a constant would put a second source of truth on the deploy path.

---

## 9. Errors this phase adds

| Error | Raised when |
|---|---|
| `RosterBasisError` | A model requests a `basis` the training era does not carry |
| `ShadowRoleError` | A `shadow` forecast reaches a published document |
| `CalibrationError` | A declared calibration step cannot be reproduced from its recorded parameters |

All are `CfbError` subclasses, exit 1, and turn the run red. Consistent with Phase 0 §9: validation
failures raise, they never return `None` or coerce.

---

## 10. Out of scope

- **Beating the closing line.** §2.3, and the PRD's position.
- **Any change to `/cfb`'s headline model.** §6.4 governs that and this phase does not amend it.
- **In-season refits of anything.** §4.1's freeze holds; the one-time exception is spent.
- **Neural architectures.** Not on principle — on sample size. ~8,000 games is not where they win,
  and the phase has better uses for the time.
- **Live injury scraping from non-CFBD sources.** §3.2 captures what CFBD supports. A news feed is a
  separate decision with its own reliability and licensing questions.

---

## 11. End-to-end verification

1. `cfb fetch roster` writes an immutable capture with a manifest, and a second run the same day does
   not overwrite the first.
2. A roster capture taken *after* a kickoff is never selected for that game — the `_at` rule refuses
   it, as it does for HFA.
3. `cfb elo replay --season 2026` still passes after §3.1's field lands, proving the additive change
   left every stored document readable.
4. A prediction log written under `schema_version` 3 carries two models, and a shadow forecast appears
   in no published document.
5. A challenger's gate result reproduces from its experiment JSON, on the identical game set.
6. The PIT histogram and 80% coverage are computed on held-out seasons and reported with `n`.

---

## 12. Open questions

- **Does the intersection flatter the market?** §2.2. Until the market's MAE is measured on the full
  priced slate as well as the intersection, 11.813 is not safely a target.
- **What `ν` does the margin distribution actually want?** A large fitted `ν` would say the Normal was
  adequate and simplify the whole model.
- **Is a week-gated hybrid one model or two?** §5.3 permits it; the log schema, the gate and the page
  copy all read differently depending on the answer, and it should be settled before it is built.
- **Should `PROBABILITY_SCALE` be fitted per season or once?** Phase 2 fitted the constants on a
  window and froze them. Calibration may drift more slowly than that, or faster.

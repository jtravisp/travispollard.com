# Phase 2 — depth: backfill, a fitted model, and the bake-off

Derived from `PRD.md`, `SPEC-phase1.md`, `PHASE-1.md`, and a design interview on 2026-08-30.
Where this spec and those disagree, this spec is the newer decision; where it is silent, they govern.
Phase 1's decisions are **not** restated here — §1.1's no-git rule, §4.3's line conventions, §5.2's
failure modes, §6.1's one-fetch-per-route rule and §6.2's version rule all carry forward unchanged.

**Deliverable:** eight usable seasons of history in `raw/`, `ELO_PER_POINT`, `K`,
`MOV_DENOMINATOR_FLOOR` and HFA fitted from it rather than asserted, a ridge model on
opponent-adjusted efficiency that either beats the Elo baseline on held-out seasons or does not
publish, and a `/cfb/models` page scoring every system against the same games with the market as
the benchmark.

**Not a deliverable:** Kubernetes (Phase 3), player or injury data, in-game probability, or any
change to what `/cfb` shows on a Saturday. The front page keeps showing Elo until a better model
has beaten it on games it forecast *before kickoff* — §6.4.

---

## 1. The one thing to read first

**The refit measures a differently-seeded model than the live one.**

Phase 1 §3.2 seeds every preseason from Sagarin's preseason RATING column. Phase 0 exists because
that page shows *current* ratings only, so there is no 2015 preseason page and there never will be.
Backfilled seasons are therefore seeded a different way (§3.3), which means the constants this phase
fits are fitted for a model whose preseason prior is not the one the live pipeline uses.

This is not a caveat that can be engineered away, and §4.4 says what it costs rather than hiding it.
It is stated here, first, because every number this phase produces inherits it.

Two other consequences of the same fact, both structural:

- **There is no PREDICTOR column before 2026.** Sagarin cannot be a bake-off entrant on historical
  games. It enters the comparison only from 2026 onward, on a denominator of its own (§6.3).
- **The historical HFA has no Sagarin manifest to read.** Phase 1 §3.3 forbids a constant and reads
  `hfa["predictor"]` per snapshot. No snapshot exists, so §4.2 fits HFA instead — which is the
  PRD's own open question answered, a phase later than it asked.

---

## 2. What the phase is for

Phase 1 shipped four numbers that are conventional rather than measured, and said so in §12:

| Constant | Status after Phase 1 | Settled by |
|---|---|---|
| `ELO_PER_POINT = 20` | Defensible from published figures; §12 expects 17–18 | §4.2 |
| `K = 20` | "Probably right", not chosen — its effective value moved when the scale did | §4.2 |
| `MOV_DENOMINATOR_FLOOR = 0.25` | Invented; §12 calls it "the newest number here with no source" | §4.2 |
| HFA | Read per-snapshot from Sagarin, never fitted | §4.2 |

And it shipped a table (§3.1's "Normal, σ = 15") that is explicitly **a reference curve, not a
measurement** — because nothing this project held could produce observed rates. §4.3 replaces it.

The PRD's rule governs the second model: *"Anything more sophisticated added later must beat this
baseline to justify existing. That is the point of starting here."* §5.6 makes that a decision rule
with numbers in it rather than a sentiment.

---

## 3. The backfill

### 3.1 The window: 2015–2025, less 2020

```
fetched:   2015 2016 2017 2018 2019      2021 2022 2023 2024 2025     10 seasons
burn-in:   ---- ----                                                   discarded
usable:              2017 2018 2019      2021 2022 2023 2024 2025      8 seasons
```

**2015 is the floor because of the second model, not the first.** Elo would happily eat 2005. CFBD's
advanced metrics — the features §5.2 needs — are not reliably available that far back, and a
backfill that fetches ten more seasons the ridge model cannot use is spending budget on Elo data
whose marginal value is low. 2015 also predates the transfer portal and NIL, so the window already
reaches back past two structural changes; reaching past a third would be fitting on a game that no
longer exists.

**Burn-in is 2015–2016.** The earliest backfilled season opens at a uniform 1500 (§3.3), which makes
its early ratings meaningless and its late ratings merely young. Two seasons is the cost of a cold
start and those games are excluded from every fit in §4.2 and every training set in §5.5. They are
still fetched, still folded, and still stored — a burn-in season is evidence about the model's
convergence even when it is not evidence about its constants.

### 3.2 2020 is excluded, and it is a structural break rather than an outlier

Not fetched, not folded, not fitted. The reason is that Elo's arithmetic depends on a property 2020
does not have.

- The Big Ten played a nine-game conference-only schedule starting in late October; the Pac-12
  played seven; the MAC played six. Dozens of games were cancelled outright and cross-conference
  play largely vanished.
- **Elo requires the graph of who-played-whom to be connected.** A rating is only meaningful
  relative to opponents, and their opponents, back to a common reference. 2020's graph is nearly
  disjoint by conference, so a Big Ten rating and an SEC rating that season are not on the same
  scale — the arithmetic still produces numbers, and the numbers are not comparable.
- Margins were distorted independently: empty stadiums, depleted rosters, and mid-week roster
  availability that nothing in `raw/` records.

**It is the one season that would corrupt an HFA fit specifically.** Home-field advantage was
measurably smaller without crowds, and §4.2 fits HFA from exactly this window. Including 2020 would
pull the fitted value toward a number that describes a year nobody will play again.

**An outlier gets absorbed; a structural break gets excluded.** The distinction is whether the
process generating the data is the same one. It was not, so no amount of sample size fixes it, and
"let the fit absorb the noise" would be treating a different sport as a noisy version of this one.

### 3.3 Historical seeding: 1500, then carry forward with regression

The live rule is unchanged: **2026 and every future season still seed from Sagarin's preseason page**
(Phase 1 §3.2). This section applies to backfilled seasons only, and `seed_history()` is a separate
function from `seed()` for that reason — one takes a snapshot, the other takes a prior season's final
state, and a single function with a mode flag would be the place the two rules eventually get
confused.

```python
# elo/seed.py
REGRESSION_TO_MEAN = 1 / 3       # fitted in §4.2; 1/3 is the opening value

def seed_history(previous: EloState | None, *, gap_seasons: int = 1) -> Ratings:
    if previous is None:
        return {team: 1500.0 for team in ...}          # cold start
    factor = (1 - REGRESSION_TO_MEAN) ** gap_seasons
    return {t: 1500.0 + (r - 1500.0) * factor for t, r in previous.ratings.items()}
```

- **The earliest backfilled season opens flat**, every team at 1500. Nothing external is required
  and the rule is trivially reproducible, which matters because §11 replays the whole window.
- **Each subsequent season inherits the prior season's final ratings, regressed toward 1500.** One
  third is the opening value — the figure FiveThirtyEight uses for the NFL — and it becomes a fitted
  parameter in its own right (§4.2). Carrying forward unregressed would assert that a roster which
  graduates its entire offence is the team it was in November.
- **A team absent from the previous season's ratings enters at 1500**, not at an error. FBS
  membership changes: teams reclassify up from FCS, and the crosswalk spans both divisions (Phase 0
  §6.5) so most are already rated. One that genuinely is not has no prior and 1500 is the honest
  answer for it.

#### The 2020 hole: 2021 carries from 2019, regressed twice

`gap_seasons` exists for exactly one call site. 2021 inherits 2019's final ratings with the
regression applied twice, so roughly 44% of the 2019 signal survives:

```
1500 + (final_2019 - 1500) * (1 - 1/3)^2      ->  0.444
```

The ratings **step over** the gap rather than through it, which is what "structural break" means
operationally.

**The squaring is an assumption, and it is the weakest arithmetic in this spec.** `(1 - r)^2` says
two years of turnover is one year applied twice — that turnover is independent and identically
distributed year over year. Across 2020 specifically it is not: the NCAA granted every player an
extra year of eligibility, so players who would have graduated stayed, and **rosters turned over
*less* across that gap than a normal two-year span**. The assumption is wrong in a known direction,
and the direction says `(1 - r)^2` over-regresses 2021.

**And `r` is fitted on transitions that are not this one.** There are eight or so gap-1 transitions
in the window and **exactly one gap-2 transition**, so the search in §4.2 learns `r` almost entirely
from normal off-seasons and then extrapolates it, squared, to the single case it could not learn
from. That extrapolation is unvalidated by construction — one observation, and it is inside the
sample being predicted. §12 is where that leads, and it is the strongest argument there for pinning
`r` rather than fitting it.

**It matters less than it looks, because of §4.4.** 2021's seeding affects 2021's predictions, and
the effect is concentrated in 2021's early weeks — which are exactly what the sensitivity fit
excludes. If §4.4's rule fires and the sensitivity fit ships, the games most sensitive to this
question are not in the sample that produced the shipped constants.

Two alternatives to stepping over the gap were considered and both cost more:

- *Fold 2020 into the chain but drop it from every fit.* Keeps continuity, and leaks anyway: 2021's
  early weeks would then be predicted from ratings distorted by a disjoint graph, and 2021's games
  **are** in the fitting sample. The contamination arrives through the back door.
- *Restart 2021 at a uniform 1500.* Cleanest severance, and it buys a second burn-in in the middle
  of the window — eight usable seasons become about six.

Two years of roster turnover is more turnover than one, so more regression is the right direction on
its own terms. That the arithmetic falls out of a constant already needed is a convenience, not the
argument.

### 3.4 The crosswalk declares which sources it covers

Historical seasons have no Sagarin side to map. A CFBD-only crosswalk is **legal**, and the file says
so rather than leaving it to be inferred from absence:

```yaml
# data/crosswalk/teams-2017.yaml
season: 2017
sources: [cfbd]                 # there is no Sagarin page for this season
teams: ...

# data/crosswalk/teams-2026.yaml
season: 2026
sources: [cfbd, sagarin]
```

`resolver.sagarin(name)` on a `cfbd`-only season raises **`SourceNotInCrosswalkError`**, not
`UnmappedTeamError`. The distinction is the same one Phase 1 §9.1 draws for every error it added:
`UnmappedTeamError` sends whoever reads it looking for a missing mapping, and on a historical season
there is no mapping to find and no parser bug behind it. A declared absence and a genuine gap must
not produce the same message.

**"An unmapped team name is an error" survives intact** (`cfb/CLAUDE.md`). Nothing here adds fallback
matching, fuzzy matching or a default. It adds a statement about which sources a season *has*, so
that asking for one it does not have fails for the right reason.

### 3.5 The call budget is measured, not trusted

Estimated cost, with the arithmetic shown so it can be checked rather than believed:

| Per season | Calls | Note |
|---|---|---|
| `/calendar` | 1 | once per season |
| `/teams` | 1 | once per season; both divisions (Phase 0 §6.5) |
| `/games?week=N` | ~16 | 15 regular weeks plus postseason |
| `/lines?week=N` | ~16 | may return nothing for early weeks in older seasons |
| advanced metrics, per week | ~16 | §5.3; the exact endpoint set is §12's first open question |
| talent composite | 1 | §5.2's early-season prior |
| **total** | **~51** | |

**~510 calls for ten seasons.** At Phase 0 §5.1's `CALL_BUDGET_PER_RUN = 25` that is **at least 21
runs**, which is what makes this a resumable job rather than a script (§3.6).

**The estimate is an estimate and the job measures the truth.** Week counts differ by season,
`/lines` coverage in older seasons is unknown, and the advanced-metric endpoint set is unverified.
Every backfill run logs its own call count and the running total across runs, recovered by listing
what is already in the bucket — so the 510 figure is replaced by a measured one as the job proceeds,
and the write-up quotes what happened rather than what was planned.

**No monthly cap is enforced, and that is deliberate.** Phase 0 §5.1 is explicit: *"The 1,000
calls/month figure is not vendor-backed and must never become a runtime check."* It remains a number
this repo copied down once. The per-run cap is the only enforcement, exactly as before, because it
holds whatever the tier turns out to be. This phase adds measurement and a place to read it; it adds
no guard that compares against a remembered total.

### 3.6 Resumability is derived from the bucket, never from a progress file

```
uv run cfb backfill --from 2015 --to 2025 [--dry-run]
```

The job asks the bucket what it already has and fetches the difference:

```python
def outstanding(store, *, seasons, resources) -> list[tuple[int, str, str]]:
    """(season, week, resource) triples with no snapshot under raw/cfbd/."""
```

**The same reasoning as `EloState.folded_from` (Phase 1 §3.5).** A progress file is a second source
of truth about what was fetched, and it can be wrong in both directions: stale after a crash between
the write and the upload, and confidently wrong after a manual `cfb fetch` filled a gap by hand. The
bucket is the thing the rest of the pipeline reads, so it is the thing that decides. A listing is
cheap, it costs no CFBD calls, and it cannot disagree with the objects it describes because it never
looked at anything else.

Three properties follow, and each is a test:

- **Re-running is free and safe.** A run with nothing outstanding fetches nothing and exits 0. The
  twenty-first run is the same code path as the first.
- **`raw/` immutability is untouched.** The job only ever writes keys that do not exist. It has no
  verb that overwrites and, per Phase 1 §4.1's IAM discipline, no permission that would let it.
- **`--dry-run` prints the plan and its cost**, so the budget question is answerable before any call
  is spent.

### 3.7 What the backfill writes, and where it does not write

Historical snapshots land in `raw/cfbd/season=YYYY/...`, indistinguishable in shape from a live pull
and subject to the same immutability. Everything derived from them is kept **out of the live record**:

| Derived from history | Prefix | Why |
|---|---|---|
| Elo states | `elo/season=YYYY/week=NN/` | Same prefix; a historical state is a real state |
| Retrospective predictions | `backtest/season=YYYY/week=NN/` | **Never `predictions/`** |
| Retrospective scoring | `backtest/` | **Never `scored/`** |

**`predictions/` means "written before kickoff" and nothing else.** Phase 1 §1.1 gave up the git
tamper-evidence argument and kept one property: a prediction in that prefix existed before the game
did. A backfilled prediction is generated with the results already in `raw/`, and writing it there
would spend the only integrity claim this project makes. Phase 1 §6.4 already established the
separation and the reason — kept apart *by prefix rather than by a flag, because a prefix cannot be
overlooked the way a boolean can* — and this phase populates it at scale for the first time.

---

## 4. The refit

### 4.1 The constants are per-season, recorded in the state, and frozen within a season

Refitting `ELO_PER_POINT` rescales every rating. A state written at 20 and a state written at 17 are
not comparable, so Phase 1 §11 step 5 — `cfb elo replay` reproducing a stored state — goes red
against every object in `elo/` the moment the constant moves. Two mechanisms are needed and they are
not alternatives:

```jsonc
// elo/season=2017/week=08/<ts>.json
{
  "schema_version": 2,
  "season": 2017,
  "week": "08",
  "model": {
    "elo_per_point": 17.5,        // the scale THIS state was written on
    "k": 24.0,
    "mov_damping": 2.2,
    "mov_denominator_floor": 0.25,
    "regression_to_mean": 0.31,
    "hfa": 2.15,
    "hfa_source": "fitted"        // vs a Sagarin manifest key on a live season
  },
  "ratings": { ... },
  "folded_from": null
}
```

- **Recorded in the document** is what makes a historical season replayable at all. Each backfilled
  season may legitimately carry a different fitted value, and `replay` compares against the
  constants the document it is checking was written under — never against whatever the module
  currently holds. Without this there is one codebase and no way to reproduce two scales.
- **Frozen at a season boundary** is what stops a refit rescaling a live season mid-flight. A
  2026 accuracy record accumulating against ratings on one scale must not have those ratings
  republished on another halfway through; the record would be measuring two models under one label.

`elo.SCHEMA_VERSION` moves for this. It is a field whose meaning changed — a state document that
does not say its scale meant one thing when only one scale existed and means something weaker now —
which is exactly the case Phase 1 §6.2 reserves a version bump for. The site contract
(`PUBLISHED_SCHEMA_VERSION`) is untouched: no published document gains, loses or renames a field.

**A refit lands between seasons and never within one.** In practice that is the off-season, which is
also when Sagarin's preseason page reseeds the live model anyway (Phase 1 §3.2), so both kinds of
discontinuity happen at the same boundary and a reader has one date to understand rather than two.

### 4.2 What is fitted, and how

Four constants and one derived parameter, fitted on the eight usable seasons by grid search
minimising **mean absolute error of predicted margin**, with Brier score reported alongside and
never traded away silently:

| Parameter | Phase 1 value | Search range | Note |
|---|---|---|---|
| `ELO_PER_POINT` | 20 | 12 – 26 | §12 expects 17–18; the range must contain 20 so the fit can decline to move |
| `K` | 20 | 10 – 40 | Reported as `K / ELO_PER_POINT`, per Phase 1 §3.4. The constant §4.4's bias acts on most; the shipping rule there decides it |
| `MOV_DENOMINATOR_FLOOR` | 0.25 | 0.05 – 1.0 | See below — it may not be fittable |
| `REGRESSION_TO_MEAN` | 1/3 | 0.1 – 0.6 | New in this phase (§3.3). Fitted on ~8 gap-1 transitions and extrapolated, squared, to 1 gap-2 case — §12 leans toward pinning it |
| HFA | Sagarin's per-snapshot value | 1.0 – 4.0 | Fitted for history; the live rule is unchanged |

**`K` and `ELO_PER_POINT` are searched jointly, never one at a time.** Phase 1 §3.4 records that the
scale change silently altered the model's responsiveness because what matters is the ratio
`K / ELO_PER_POINT` — points of margin moved per game. A sequential fit would find a local optimum
along one axis of a surface whose gradient runs diagonally, and would then be reported as though two
independent questions had been answered.

**`MOV_DENOMINATOR_FLOOR` probably cannot be fitted, and the fit should be allowed to say so.**
Phase 1 §12 already established that at `ELO_PER_POINT = 20` no seed pairing reaches it — the widest
leaves the denominator at 0.58 against a floor of 0.25 — so the constant may be unreachable across
the whole backfill and therefore generate no gradient. **If the grid is flat in that dimension, the
finding is that it is an invariant guard rather than a tunable, and it stays at 0.25.** A flat
gradient reported as an optimum would be the fit inventing precision it does not have. What the
backfill *can* answer, and should: how many games in eight seasons ever came within reach of it.

**HFA is fitted as a single constant across the window, and per-season values are reported.** The
PRD's open question — *"fit it from data, or take Sagarin's published per-snapshot value"* — is
answered for history only. The live pipeline keeps reading the snapshot (Phase 1 §3.3), because a
fitted historical constant is not evidence about what this Saturday's home advantage is, and Phase 1
§12's open question about per-week versus fixed HFA is settled by the per-season series rather than
by this constant.

**Walk-forward, not in-sample.** The fit uses seasons 2017–2023; 2024 and 2025 are held out and
never touched until the constants are frozen. A constant fitted on the games it is then evaluated on
is a description of those games.

### 4.3 §3.1's plausibility table is replaced with measured rates

Phase 1 §3.1 published this, and was explicit that the right-hand column is **a reference curve, not
a measurement** — what a normal with a defensible σ would say, not an observed rate, *because
nothing this project currently holds can produce observed rates.*

The backfill is what it was waiting for. The table is regenerated with a column that is:

| Margin | Elo gap | Model at fitted scale | **Observed win rate, 2017–2025** | n |
|---|---|---|---|---|
| 1 | | | | |
| 3 | | | | |
| 7 | | | | |
| 10 | | | | |
| 14 | | | | |
| 21 | | | | |

Read as: among games this model predicted by *m* points, what fraction did the favourite actually
win. Bucketed by predicted margin with the count attached, per Phase 1 §5.3's rule that a sample
size always travels with a rate.

**The σ = 15 column is deleted, not kept alongside.** Its whole purpose was to stand in for a
measurement that did not exist. Keeping a reference curve next to the real thing invites the
comparison that produced the original error — Phase 1 §3.1 records that the column this replaces was
once headed "Observed", was approximately the *NFL* curve, and that the scale had been chosen to
match it. A number imported from the wrong sport, presented as corroboration, is the specific failure
this phase closes.

**One published figure to check the fit against.** A college 7-point favourite wins outright roughly
**67%** of the time. If the fitted model's 7-point bucket lands far from that, the fit is wrong
before any of it reaches a page.

### 4.4 What the refit does not measure, stated plainly

**The constants are fitted on a model seeded from a uniform 1500 and carried forward with
regression. The live model is seeded from Sagarin's preseason page.** These are different priors,
and the fitted constants describe the first one.

Where it bites, in order of severity:

- **Early-season weeks are where the two seedings differ most**, and they are in the fitting sample.
  A `K` fitted on a model that starts each season knowing less will be biased toward moving ratings
  faster than the live model needs, because the backfilled model has more to learn in September.
- **`REGRESSION_TO_MEAN` has no live counterpart at all.** The live model discards the prior season
  entirely and takes Sagarin's opinion. The fitted regression coefficient describes a carry-forward
  the live pipeline does not perform.
- **`ELO_PER_POINT` is the least affected**, because Phase 1 §3.2 proves the constant cancels between
  `seed()` and `predict()` — the seeding regime changes the ratings and not the margins they imply.
  This is the one constant the backfill measures cleanly for both models.

**Both fits are reported, and neither is engineered away.** The primary fit uses all non-burn-in
weeks, because the model is used all season and a constant fitted only on October is a constant for
October. A sensitivity fit excluding weeks 1–3 of each season is published beside it, and the shape
of any disagreement says which constant the seeding is contaminating.

#### When they disagree, the sensitivity fit ships

Reporting both is not a decision, and the live pipeline needs one value. So:

> **Material disagreement is a held-out MAE difference of more than 0.25 points between the two
> constant sets. Below that, the primary fit ships. At or above it, the sensitivity fit ships and the
> margin is recorded in `fits/`.**

The threshold is stated in the phase's own metric rather than per-constant, because "materially" has
to be decidable by the run rather than argued each time, and because swapping constant sets is
exactly the comparison a per-constant threshold would be a proxy for.

**The sensitivity fit wins the tie because the live model is Sagarin-seeded.** Excluding weeks 1–3
approximates a model that already knows something in September, and that is the live model's regime
all season — Phase 1 §3.6 puts the week-1 correlation with Sagarin at exactly 1.0. The primary fit's
September is a model with more to learn than the live one ever has, and §4.4's whole argument is that
fitting on it biases `K` upward.

**The cost, stated rather than buried.** `K` does not enter a week-1 *prediction* at all — a week-1
forecast is the seed (Phase 1 §3.6) — so `K`'s first real effect is on week 2, and its influence is
largest across weeks 2–4. The sensitivity fit sees only the last of those. **The shipped `K` is
therefore estimated from the wrong end of the season for the weeks it matters most in**, which is a
worse problem than the one it fixes only if the seeding contamination is small. The primary fit
existing beside it is what makes that checkable.

**One diagnostic falls out of it.** Phase 1 §3.2 proves `ELO_PER_POINT` cancels between `seed()` and
`predict()`, so the seeding regime should barely move it. If it moves a lot between the two fits, the
September contamination is worse than §4.4 models — that is a flag about the fit rather than a number
to ship, and it goes in `fits/` as one.

**The real test arrives for free.** 2026 is a live, Sagarin-seeded season being scored week by week
under Phase 1 §5.3. If the constants fitted here produce a calibration curve on *that* season
matching the one the backfill predicts, the seeding difference did not matter enough to care about.
If they do not, the gap is measured rather than argued. That check is the first thing §11 asks for.

---

## 5. The second model

### 5.1 Ridge regression on opponent-adjusted efficiency

Target is **predicted margin, home perspective** — the same quantity Elo predicts, in the same
units, signed the same way. Win probability is derived from it **exactly as it is now**: the Phase 1
§3.1 logistic, applied to the predicted margin expressed in Elo. Nothing about §3.1's coupling
changes, and margin and probability still cannot disagree, which the PRD forbids outright.

Ridge rather than something larger for two reasons. The sample is roughly 8 seasons × ~1,500 FBS
games, and the features below are strongly collinear — offensive and defensive EPA, success rate and
explosiveness measure overlapping things — which is the situation L2 regularisation exists for.
And a linear model's coefficients are readable, so the write-up can say what the model thinks
matters rather than showing a feature-importance bar chart of a gradient booster.

### 5.2 Features

Per game, each as a home-minus-away difference so the model is symmetric by construction and cannot
learn a home bias separately from the HFA term:

| Feature | Source |
|---|---|
| Adjusted EPA per play, offence | CFBD advanced metrics |
| Adjusted EPA per play, defence | CFBD advanced metrics |
| Success rate, offence and defence | CFBD advanced metrics |
| Explosiveness, offence and defence | CFBD advanced metrics |
| Talent composite | CFBD `/talent`, season-level |
| Neutral site | boolean, from `/games` |
| Home indicator | carries the HFA term |

**Talent composite is an early-season prior and is weighted as one.** In week 2 a team has played
one game and its adjusted efficiency is nearly noise; by week 8 it is the best signal available and
talent is stale. The feature is interacted with games-played so the model can learn that decay rather
than being told it — which is the honest version of the same instinct that made Phase 1 §1.2 seed
Elo from Sagarin instead of from 1500.

### 5.3 Efficiency is aggregated as-of-week, and season-level statistics are disqualified

**A season-level adjusted-efficiency number includes the game being predicted.** CFBD's season
endpoints return the finished season; using them to predict a September game would be handing the
model the answer, and the resulting MAE would be excellent and meaningless.

So the features are built from **per-week game-level metrics, aggregated forward only**: a game in
week *N* sees data from weeks 1 through *N−1* of that season and nothing later. This costs one call
per season-week rather than one per season (§3.5's largest line item) and it is not optional.

**Week 1 of every season has no in-season data at all.** Those games are predicted from talent
composite and the carried-forward prior alone, which is a weaker model and honestly so. They stay in
the evaluation set — a model that cannot forecast week 1 is a model that cannot forecast the weeks
people arrive for.

### 5.4 Validation: walk-forward by season

Train on every season strictly before *N*, predict *N*, roll forward. Never a random split: games
within a season are not independent, a random k-fold would train on November to predict September,
and the resulting figure would describe a model that cannot exist.

```
train 2017-2018        -> predict 2019
train 2017-2019        -> predict 2021        (2020 excluded, §3.2)
train 2017-2021        -> predict 2022
...
train 2017-2024        -> predict 2025
```

The ridge penalty α is selected **inside each training window**, on the last season of that window,
never on the season being predicted. An α chosen against the evaluation set is the same leak as a
season-level feature wearing different clothes.

### 5.5 The Elo baseline is regenerated on the identical games

The comparison is only meaningful if both models saw the same games. Elo's retrospective predictions
for the same seasons are written to `backtest/` (§3.7) under the constants §4.2 fitted, and the
gate below is computed on the intersection — games both models predicted, no exceptions and no
per-model denominators. Phase 1 §5.3's rule that every mean carries its own denominator applies to
*benchmarks with different coverage*; two models over the same slate must not have different ones.

### 5.6 The gate

**All three, on held-out seasons, never on training data:**

```
ridge_mae     <  elo_mae                      strictly
ridge_brier   <= elo_brier * 1.02
calibration slope in [0.90, 1.10]
```

- **MAE is the gate** because it is the PRD's headline metric and the unit the market comparison is
  stated in.
- **Brier is a guard, not a target.** A model can lower MAE while being confidently wrong about
  outcomes, and win probability is half of what every page publishes. The 2% tolerance allows a real
  margin improvement that costs a trivial amount of probability sharpness; it does not allow a trade.
- **Calibration slope** is the regression of observed win rate on predicted probability across
  buckets. 1.0 is perfect; below 0.9 is overconfident, above 1.1 underconfident. Phase 1 §3.7's
  entire argument is that a page about calibration cannot display a certainty, and this is the same
  claim made checkable.

**Against the spread is reported and does not gate.** SP+ runs 51–54% against a 52.4% break-even. At
eight held-out seasons the confidence interval on an ATS rate comfortably spans that whole range, so
an ATS gate would reject good models and accept lucky ones at close to random. It goes on the page
with its sample size, per Phase 1 §5.3, and decides nothing.

**Failing the gate is a legitimate outcome and the phase still stands.** The backfill, the refit and
the bake-off are all delivered whether or not the ridge model publishes. The PRD's rule is a rule; a
second model that does not beat the baseline has told us something worth knowing about the baseline,
and shipping it anyway would make the rule decorative.

---

## 6. The bake-off

### 6.1 A route of its own

```
/cfb/models      <- models.json        every system, same games
/cfb/accuracy    <- accuracy.json      this model vs the market   (unchanged)
```

The comparison is a different question from "how is the model doing", which is what `/cfb/accuracy`
answers, and it has a different shape: a systems-by-metric matrix plus a per-week series, rather than
one model's record over time. A new route keeps Phase 1 §6.1's one-fetch-per-route rule intact and
leaves the accuracy page a single-model story that stays readable.

`/cfb/accuracy` is **not** modified. Its `line_mae` and `sagarin_mae` fields already answer its own
question and duplicating a leaderboard into it would create a second place to keep correct.

### 6.2 `models.json`

```jsonc
{
  "schema_version": 3,
  "generated_at": "...",
  "season": 2026,
  "through_week": "08",
  "shared_denominator": { "games": 402, "description": "games every system priced" },
  "systems": [
    {
      "id": "elo",
      "label": "This model (Elo)",
      "mae": 12.9, "brier": 0.191,
      "ats": { "record": "104-98", "wins": 104, "losses": 98, "pushes": 0,
               "excluded_no_line": 0, "excluded_no_edge": 0 },
      "coverage": { "priced": 402, "of": 402 },
      "is_ours": true
    },
    { "id": "ridge",   "label": "This model (efficiency)", "...": "..." },
    { "id": "market",  "label": "The market",  "is_benchmark": true, "...": "..." },
    { "id": "sagarin", "label": "Sagarin PREDICTOR", "...": "..." },
    { "id": "cfbd-sp", "label": "SP+",  "...": "..." }
  ],
  "by_week": [ { "week": "01", "mae": { "elo": 14.2, "ridge": 13.8, "market": 12.4 } } ]
}
```

`schema_version` moves to 3 for the site contract because this is a new document; existing documents
are untouched and their readers do not change.

### 6.3 The shared denominator is the whole problem

Every system covers a different subset. The market prices a subset of the slate; Sagarin's page
covers a different subset again; SP+ covers FBS only; this model covers everything the crosswalk
rates. Phase 1 §5.3 already forbids averaging a benchmark over games it never priced.

**A leaderboard makes it worse, because the comparison is between rows.** Two systems with different
denominators are not comparable at all, and a table puts them next to each other implying they are.

So `models.json` publishes the headline matrix on the **intersection — games every listed system
priced** — with that count stated on the document and on the page. Each system additionally carries
its own `coverage`, so a system that priced 402 of 402 and one that priced 402 of 900 are visibly
different things even when their MAE is computed on the same 402.

**Sagarin enters from 2026 only.** There is no PREDICTOR column for a backfilled season (§1), so on
historical games the intersection is computed without it rather than with a hole in it.

### 6.4 What the front page shows, and when that changes

**Clearing the gate does not change `/cfb`.**

| Event | Effect |
|---|---|
| Ridge clears §5.6's gate on held-out seasons | It appears in `slate.json` and on `/cfb/models`. `/cfb` still headlines Elo |
| Ridge leads Elo on live, pre-kickoff games for ≥ 4 weeks of a season | `/cfb` switches. The week it switched is recorded and never rewritten |

The gate is cleared on **retrospective** evidence. Phase 1 §1.1 gave up git in order to keep one
property — that the public record is of forecasts made before kickoff — and switching the front page
on the strength of a fit would spend it. §6.4's second row is the same claim tested the way this
project tests everything else: on games the model called in advance, in public, with the timestamp in
the object key.

Four weeks rather than one because a single week is roughly sixty games and decides nothing.

---

## 7. Targets

**From the evidence rather than from ambition.**

| | |
|---|---|
| Vegas line MAE, college football | **~12.6 points**, and usually the smallest MAE of any tracked system |
| SP+ against the spread | **51–54%**, against a break-even of **52.4%** |
| The academic result | An ensemble can beat the **opening** line. Nothing beats the **closing** line |
| Our `market_line` | A **Thursday quote** — between the two, and closer to the opening |

**The success criterion is MAE within about a point of the market, with calibration that holds.**
Not beating it. Concretely: a model MAE of roughly **13.6 or better** with a calibration slope inside
[0.90, 1.10] is the result this phase is trying to produce.

This is the PRD's own position — *"Beating the closing line is not the goal and probably will not
happen — the market is efficient. Landing within a couple of points with well-calibrated
probabilities, and saying so plainly, is the stronger result and the more credible page."* It is
restated here with numbers because a target without one is a mood.

**One honest asymmetry worth stating on the page.** Because our quote is a Thursday price rather than
a closing one, beating it would be a weaker claim than beating the close — the literature says the
opening line is beatable and the closing line is not, and a Thursday number sits between them. If
this model ever does beat it, the page says which line it beat.

---

## 8. CLI additions

```
uv run cfb backfill --from 2015 --to 2025 [--dry-run]     # resumable; §3.6
uv run cfb fit elo --seasons 2017-2023                    # grid search; writes fits/
uv run cfb fit ridge --seasons 2017-2023                  # walk-forward; writes fits/
uv run cfb backtest --season 2019 --week N                # exists; now used at scale
uv run cfb models --season 2026                           # build and upload models.json
```

`cfb fit` writes to a new write-once `fits/` prefix: the search grid, the selected values, the
held-out figures, and the sensitivity fit of §4.4. A fitted constant that cannot be traced to the run
that produced it is an assertion, which is the same standard Phase 1 §4.2's `model` block sets for a
prediction.

---

## 9. Errors this phase adds

Every one is a `CfbError`, so Phase 0 §9's contract holds unchanged: exit 1, a message on stderr, a
red run, nothing caught and demoted to a warning.

| Error | Raised when |
|---|---|
| `SourceNotInCrosswalkError` | a lookup asked for a source the season's crosswalk does not declare (§3.4) |
| `ScaleMismatchError` | a replay compared states written under different constants without reading them from the documents (§4.1) |
| `LeakageError` | a feature window included a game at or after the one being predicted (§5.3) |
| `InsufficientHistoryError` | a fit or a training window was handed fewer seasons than it requires |

`LeakageError` is the one worth arguing for. Leakage does not fail — it produces excellent numbers,
and a model with a leaked feature looks like the best result the project has ever had. It is the
exact shape of failure `cfb/CLAUDE.md` says the whole project is designed to prevent, so it gets a
named check at the boundary rather than a comment asking the next reader to be careful.

---

## 10. Out of scope

- Kubernetes. Phase 3, with its own write-up about why the workload moved
- Player-level data, injuries, roster availability
- Live or in-game win probability
- Any model beyond the two named here — no gradient boosting, no neural nets, no ensembles of more
  than the two. An ensemble of Elo and ridge is a Phase 3 question and only if both earn it
- Betting recommendations, parlays, or anything resembling handicapping
- Backfilling Sagarin. The page shows current ratings only; the history does not exist and no amount
  of engineering creates it
- Changing what `/cfb` shows on the strength of a backtest (§6.4)

---

## 11. End-to-end verification

Phase 2 is done when all six hold:

```bash
# 1. The window is in the bucket, and 2020 is not
aws s3 ls s3://travispollard-cfb-data/raw/cfbd/ --recursive --profile tp-site | grep -c season=2020
#    expect: 0

# 2. The backfill is resumable and idempotent
uv run cfb backfill --from 2015 --to 2025 --dry-run
#    expect: nothing outstanding, zero calls planned

# 3. Every backfilled season replays to its stored state, on its own constants
uv run cfb elo replay --season 2019
#    expect: byte-identical ratings; no ScaleMismatchError

# 4. The fitted constants reproduce on the live season
#    THE ONE THAT MATTERS (§4.4): the constants were fitted on a 1500-seeded model
#    and 2026 is Sagarin-seeded. Compare the calibration curve accuracy.json
#    reports for 2026 against the one the backfill predicts.
curl -s https://travispollard.com/cfb/data/accuracy.json | python -m json.tool

# 5. The gate was evaluated and the answer is recorded either way
aws s3 cp s3://travispollard-cfb-data/fits/ridge/<ts>.json - --profile tp-site
#    expect: held-out MAE, Brier and calibration slope for both models, and a verdict

# 6. The bake-off is live and its denominators are stated
curl -s https://travispollard.com/cfb/data/models.json | python -m json.tool
```

Step 4 is this phase's step 5 — the equivalent of Phase 1 §11's "state is a cache, not a source of
truth". **A constant fitted on history that does not describe the live season is a number that
described a different model, and §4.4 is the reason to expect that it might.**

---

## 12. Open questions

- **The exact CFBD advanced-metric endpoint set is unverified**, and §3.5's budget depends on it.
  Which endpoints expose per-week adjusted EPA, success rate and explosiveness, from which season
  they are populated, and whether any of them is season-level only (§5.3 disqualifies those) is the
  **first thing to establish**, before a season of backfill is fetched. It should cost a handful of
  calls against one season and it changes the shape of the job if the answer is bad. If per-week
  adjusted efficiency is not available historically, §5 needs rewriting rather than adjusting.
- **Whether postseason games belong in the fit.** They are fetched and folded either way — a bowl is
  a game and Elo should know about it. But opt-outs, month-long layoffs and transfer-portal
  departures make bowl margins behave differently from regular-season ones, and a constant fitted
  partly on them is fitted partly on a different sport. Leaning toward including them in the ratings
  chain and excluding them from the constant fit, with both reported. Same shape as §3.2's argument
  and a much smaller effect.
- **Whether `REGRESSION_TO_MEAN` should be fitted at all — leaning toward pinning it at 1/3.** Two
  arguments, and the second is the stronger one.
  - §4.4: the live model has no carry-forward at all. It discards the prior season and takes
    Sagarin's opinion, so a fitted regression coefficient describes a step the live pipeline never
    performs.
  - §3.3: **one parameter is doing two jobs.** `r` describes ordinary year-over-year turnover *and*,
    squared, a two-year gap across a pandemic that suspended the usual turnover. Those are not the
    same quantity, the fit has ~8 observations of the first and **1** of the second, and the
    eligibility waiver says the extrapolation is wrong in a known direction. Searching 0.1–0.6 for a
    value that then gets squared and applied to a case outside the search's evidence is precision
    the data does not support.
  - **The deciding evidence is cheap and should be gathered before choosing.** Run §4.2's grid with
    `r` free and with `r` pinned at 1/3, and compare the *other* constants. If they do not move, pin
    it and say so — which is the outcome to hope for, because it converts a parameter with one
    relevant observation into a stated convention.
  - If it stays fitted, the 2021 factor should be reported as a sensitivity rather than as a fitted
    value: the same backfill at 0.44 (the squaring) and at a higher factor reflecting the waiver,
    checking whether any downstream constant notices.
- **Whether the two 2026 models should both appear on `/cfb/slate` before the gate is cleared.**
  §6.4 governs `/cfb` and is silent about the slate. Two margins per row is a real information gain
  for the reader who wants it and a real cost to a table that is already five columns wide.
- **What happens to `fits/` when a season is refit.** Write-once means a second fit is a second
  object, and something has to say which one the current constants came from. Probably the same
  `index.json` shape `predictions/` uses (Phase 1 §4.1), and probably not worth building until there
  is a second fit.
- **Phase 1 §12's open questions are inherited, not closed.** The cancelled-game case, per-week
  versus fixed HFA, and accuracy-page pagination all survive this phase unchanged. The HFA one is
  *partly* answered — §4.2 produces a per-season series that is evidence about it — but the live
  rule does not change here.

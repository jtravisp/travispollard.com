# Phase 1 — v1: implementation spec

Derived from `PRD.md`, `SPEC-phase0.md`, `../CLAUDE.md`, and a design interview on 2026-08-28.
Where this spec and those disagree, this spec is the newer decision; where it is silent, they govern.
Two PRD decisions are **reversed** here and §1 says which and why.

**Deliverable:** Elo ratings computed from collected results, predictions for every FBS game written to S3
before kickoff, results scored against them on Sunday, JSON published to `/cfb/data/*`, and the three
Next.js routes reading it. One Saturday end to end with no manual intervention.

**Not a deliverable:** any model beyond the Elo baseline, historical backfill, or the write-up.

---

## 1. Two decisions this spec reverses

### 1.1 The prediction log does not go in git

The PRD says predictions are committed to git before kickoff and that "git is the tamper-evident record."
**That is reversed.** Predictions go to S3 like everything else.

The mechanism it would need is the problem: committing from a workflow requires `contents: write` on the
repo, which is a materially larger permission than anything Phase 0 granted, on a repo that also builds and
deploys the site. The tamper-evidence it buys is worth less than that costs, because nobody is auditing
this — the audience is someone who follows Texas football, not a reviewer with an adversarial interest in
whether last week's number was edited.

**The property worth keeping survives without git, and costs nothing extra.** The bucket is versioned and
the publisher role has no `s3:DeleteObject` on the prediction prefix (§4.1), so a prediction written before
kickoff cannot be quietly rewritten afterward: a second write is a new object under a new key, and the
first one stays. That is the same discipline `raw/` already runs under and it is enforced by IAM rather
than by convention.

**The methodology page drops the "tamper-evident record" framing entirely.** It says what is true: every
prediction is written to immutable, versioned storage before kickoff, with the generation timestamp in the
key, and nothing in the pipeline can delete one. Claiming more than that on a page about calibration would
be the one kind of overclaim this project cannot afford.

### 1.2 Sagarin seeds the Elo ratings

The PRD lists Sagarin among things "scored against, not used as inputs in v1". **That is reversed, with a
narrower scope than it sounds.** Sagarin's preseason **RATING** column seeds week-0 Elo state. Sagarin's
**PREDICTOR** column — the per-game predictions the PRD actually names — remains an input to nothing and a
benchmark only.

The reason is that the alternative is worse on the page that matters. Phase 2 owns historical backfill, so
Phase 1 opens with no prior results at all; a uniform 1500 start predicts Texas–Kennesaw State as a coin
flip through September, which is visibly wrong on `/cfb` in exactly the weeks people arrive. The preseason
page carries real information about relative strength:

| | |
|---|---|
| FBS rating spread | **67.2 points** (35.90 Massachusetts → 103.07 Ohio State), sd 15.6 |
| Texas | rank 5, 98.50 |
| FBS–FCS median gap | **25.8 points** |

The page *is* degenerate in the sense §4.5 of the Phase 0 spec means — all four rating columns are
identical within a team, every record is 0-0, schedule strength is 0.00. That is a statement about the
columns, not about the spread across teams, and the spread is where the information is.

§3.6 quantifies what this costs and when the cost expires.

---

## 2. Repo layout

Files this phase creates. Everything under `cfb/` except the routes, the workflow, and the root-stack
CloudFront work deferred from Phase 0 §10.2.

```
cfb/
├── src/cfb/
│   ├── elo/
│   │   ├── __init__.py             # Ratings, seed(), update(), predict()
│   │   ├── seed.py                 # Sagarin RATING -> Elo (§3.2)
│   │   └── scoring.py              # results joined to predictions (§5)
│   ├── publish/
│   │   ├── __init__.py             # build the /cfb/data/* documents (§6)
│   │   └── notes.py                # the weekly note scaffold (§7)
│   └── replay.py                   # rebuild Elo state from raw/ (§3.5)
├── tests/
│   ├── test_elo.py                 # the update step, against hand-worked cases
│   ├── test_seed.py                # scale, ordering, FBS/FCS separation
│   ├── test_scoring.py             # the join, and every way it can fail
│   ├── test_publish.py             # JSON contract, schema_version, shape
│   └── fixtures/
│       └── cfbd_games_2026_week04.json   # exists
└── data/                           # unchanged; no Elo state here (§3.5)

frontend/app/cfb/
├── page.tsx                        # /cfb
├── accuracy/page.tsx               # /cfb/accuracy
└── notes/[slug]/page.tsx           # /cfb/notes/[slug]

.github/workflows/
└── cfb-predict.yml                 # Thu 12:00 UTC + Fri publish (§8)
```

---

## 3. The model

Elo, computed from CFBD game results. The whole model is a rating per team, an update rule, and two
formulas. Anything more sophisticated is Phase 2 and has to beat this to justify existing.

### 3.1 Scale: 16 Elo per point

> **Superseded in part by SPEC-phase2 §4.** This section argued 20 from a reference curve, which
> was the best available before the backfill existed. §4.2's grid search over 2015–2025 returned
> **16.0**, and §4.3 replaces this section's plausibility table with measured win rates. The
> reasoning below is kept because it is the record of how the constant was arrived at twice before
> it was measured — and because §4.3's deletion of the σ = 15 column only makes sense beside the
> argument that column was serving.

A Sagarin rating difference is already a predicted margin in points. Elo is a different unit, so both the
seed and the prediction need a conversion, and one constant does both:

```python
ELO_PER_POINT = 20
```

Predicted margin is `(elo_home - elo_away) / ELO_PER_POINT + hfa`. Win probability is the standard Elo
logistic, `1 / (1 + 10 ** (-elo_diff / 400))`, unchanged from the textbook.

**`elo_diff` in that logistic is the HFA-adjusted gap**, `elo_home + hfa * ELO_PER_POINT - elo_away`, not
the raw rating difference. The table below already forces this: it maps margin 7 to a gap of 140, which is
7 × 20 — so the quantity being turned into a probability is the *predicted margin* expressed in Elo, and
the predicted margin includes HFA. Reading `elo_diff` as the raw gap would let a game's margin and its win
probability describe two different games, which the PRD forbids outright. In practice the probability is
computed from the margin rather than beside it, so the two cannot drift apart.

**Only the ratio `ELO_PER_POINT / 400` is meaningful.** `(20, 400)`, `(10, 200)` and `(40, 800)` are the
same model. The two constants live in different places and read as independent, which they are not: anyone
adjusting one is adjusting the other's meaning. Stated here because the divisor looks like textbook
furniture and is therefore the one more likely to be treated as untouchable while the other is tuned.

#### It was 28, and the reasoning for that inverted

The previous draft argued **"28 rather than the conventional 25 because college margins are far wider than
the NFL ones the 25 figure came from."** The observation is correct and the inference from it runs
backwards.

Hold the 400 divisor fixed. A *higher* `ELO_PER_POINT` maps a given margin to a larger Elo gap, and a
larger gap is a *higher* win probability — so raising the constant makes the model **more** confident per
point. Wider scatter is less information per point, which argues for a value **below** the NFL figure, not
above it. The old number was on the wrong side of 25 for a sport with more variance, not less.

What 28 implied, read back out of its own table:

| Margin | Probability at 28 | Implied σ |
|---|---|---|
| 7 | 75.6% | 10.1 |
| 14 | 90.5% | 10.7 |
| 21 | 96.7% | 11.4 |

The model was behaving as though college football margins scatter with a standard deviation of about
**10.5 points**. They do not.

#### What the evidence says

- **Published systems.** FiveThirtyEight's NFL Elo uses **25** Elo per point. Staturdays' college football
  Elo works out to roughly **20**, and they note that the variability in the college spread is wide enough
  that they do not lean on the conversion.
- **Empirical scatter.** Final margins land around the closing spread with a standard deviation of roughly
  **16 points** in college football, against the NFL's **13.5**. A separate fit over ~12,000 games found
  **14.1** as the minimum-error value. Call the range **14–16**.
- **The concrete miss.** An NFL 7-point favourite wins outright roughly **70%** of the time and a college
  7-point favourite closer to **67%**. At 28 this model said **75.6%**.

#### Why 20

At 20 the logistic tracks a normal with σ = 15 — the middle of the evidence range — closely across the
whole span a football margin occupies:

| Margin | Elo gap | This model | Normal, σ = 15 |
|---|---|---|---|
| 1 | 20 | 52.9% | 52.7% |
| 3 | 60 | 58.5% | 57.9% |
| 7 | 140 | 69.1% | 68.0% |
| 10 | 200 | 76.0% | 74.8% |
| 14 | 280 | 83.4% | 82.5% |
| 21 | 420 | 91.8% | 91.9% |

**The right-hand column is a reference curve, not a measurement**, and the distinction is the same one the
previous draft got wrong. It is what a normal distribution with a defensible σ would say, so agreeing with
it means the model is not asserting a confidence the sport does not support. It is *not* an observed rate.
Nothing this project currently holds can produce observed rates: there is no historical result set in
`raw/`, because Phase 2 owns the backfill (§10).

The column this replaces was headed "Recalled rate" and, before that, "Observed". It was approximately the
**NFL** curve, and the scale had been chosen to match it — so the table was the model agreeing with a
number imported from the wrong sport, presented as corroboration.

**§5.3's calibration curve is what settles the final value.** It is computed from games this project
actually stored and predicted, and it is the only calibration figure here that can be defended. §12 records
the reason to expect 20 is still slightly too high.

### 3.2 Seeding

```python
# elo/seed.py
def seed(snapshot: SagarinSnapshot, crosswalk: Crosswalk) -> Ratings: ...
```

Every team in the preseason snapshot, keyed by canonical id:

```
elo = 1500 + (sagarin_rating - fbs_mean) * ELO_PER_POINT
```

`fbs_mean` is the mean RATING across division-`A` teams **in that snapshot**, not a constant. Centring on
the FBS mean rather than the all-266 mean puts the FBS field either side of 1500 and lets FCS fall where
the ratings put it, which is the behaviour the division gap is supposed to produce.

On the 2026 preseason page this yields Ohio State 2204, Texas 2113, Massachusetts 861, FCS median 929.
That is a wider range than textbook Elo, and it is internally consistent by construction: an Elo gap of
1343 divided by 20 is 67.1 points, which is Sagarin's own rating difference to within rounding.

**Those four numbers moved when §3.1 rescaled and the predicted margins did not.** A seed is
`1500 + (rating - mean) * ELO_PER_POINT` and a margin is an Elo gap divided by the same constant, so it
cancels: at 28 Ohio State was 2486 and at 20 it is 2204, while every week 1 forecast is bit-identical
between the two. §3.6's correlation of exactly 1.0 is unaffected, which is what made the rescale safe to
make in-season. `test_seed.py::TestTheScaleCancels` pins it.

**Seeding is a preseason-only operation.** It runs once, from the first snapshot whose `page_state` is
`preseason`, and never again within a season. A mid-season re-seed would silently discard every result the
model had learned from, so `seed()` refuses a snapshot with `page_state == "in-season"`.

**Every preseason reseeds.** 2027 opens from Sagarin's 2027 preseason page rather than carrying 2026's
final ratings forward. Sagarin's preseason ratings have already absorbed roster turnover, transfers and
coaching changes, which a carried-forward Elo has no way to know about — a team that graduates its entire
offence looks identical to Elo on the first Saturday of the next season. Revisit in Phase 2, when backfilled
history makes a fitted preseason prior possible.

### 3.3 Home-field advantage

Read from the current Sagarin snapshot's manifest, `hfa["predictor"]`. Never a constant, never a default,
consistent with Phase 0 §2.2 — the value is captured per snapshot precisely so that nothing downstream has
to invent one.

**This makes Sagarin a dependency of prediction generation, not only a benchmark**, and that is a real
coupling worth stating rather than discovering. If Thursday's generate runs when the most recent Sagarin
snapshot is stale or missing, it uses the newest manifest that has an `hfa` — the value moves slowly and
last week's is a far better answer than a hardcoded one. If no snapshot has ever carried one, generation
fails rather than substituting a number.

### 3.4 The update step

```python
# elo/__init__.py
K = 20
def update(ratings: Ratings, game: Game, *, hfa: float) -> Ratings: ...
def predict(ratings: Ratings, game: Game, *, hfa: float) -> Prediction: ...
```

`hfa` is a keyword argument rather than a field on `Game`, because it belongs to the Sagarin snapshot the
run read (§3.3) and not to the game. On `Game` it would be a per-run value hanging off a per-fixture
object, and the first thing to serialise a `Game` would carry it into a document with no business
asserting it. `update` returns new ratings rather than mutating: a rating is what the model believed at a
moment, and a replay folding over a season has to be able to stop part-way and compare (§3.5).

Standard Elo with a margin-of-victory multiplier, applied once per completed game in kickoff order:

```
expected  = 1 / (1 + 10 ** (-(elo_home + hfa*ELO_PER_POINT - elo_away) / 400))
actual    = 1.0 if home won else 0.0
mov_mult  = ln(abs(margin) + 1) * (2.2 / (elo_diff_winner * 0.001 + 2.2))
elo_home += K * mov_mult * (actual - expected)
elo_away -= K * mov_mult * (actual - expected)
```

`K = 20` and the multiplier's constants are conventional, not fitted — the same status as `ELO_PER_POINT`
and the same Phase 2 obligation. The multiplier's denominator damps margin: without it a strong team
running up the score against a weak one gains more than the result warrants, and ratings inflate at the
top.

**`K` is coupled to `ELO_PER_POINT`, and §3.1's rescale changed the model's responsiveness without
changing `K`.** What `K` controls is Elo movement, but the quantity anyone reasoning about this model
cares about is *points of predicted margin* moved per game, which is `K / ELO_PER_POINT`:

| Scale | `K / ELO_PER_POINT` | |
|---|---|---|
| 28 (was) | 0.71 points | |
| 20 (now) | 1.00 points | **~40% more responsive** |

That is recorded here rather than left to be rediscovered, because it happened as a *consequence* of
fixing §3.1 rather than as a decision about `K`. The direction is probably right — practitioners raise `K`
for college football given the shorter season and the greater unpredictability, and 12 games is very
little evidence to move a rating on. But "probably right" is the status, not "chosen".

Two things follow. `K` should not be re-tuned without restating it in these units, or the next adjustment
will silently undo this one. And §5.3's calibration curve now has two constants to answer for rather than
one: an over-responsive model and an over-confident one both show up as a curve that is too steep.

#### `hfa` is not applied at a neutral site

In both `update` and `predict`. §4.2 makes home and away at a neutral site "whatever CFBD says", so the
designation is arbitrary — and an edge awarded on an arbitrary label is not a small bias in one direction.
It is ~2.4 points of noise in whichever direction the vendor happened to list the teams, applied to the
games most likely to decide a playoff. Both formulas take it from one function, so a prediction and the
result that scores it are never measured against different versions of the same game.

#### `elo_diff_winner` is signed: the winner's rating minus the loser's

Positive when the favourite won, negative when the underdog did. So an upset shrinks the denominator below
2.2, enlarges the multiplier, and moves ratings further than the same margin would in the expected
direction.

**The reason is informational.** An upset is a low-probability event; a low-probability event carries more
information than a likely one; a result the model did not expect should change it more than one it did.
That argument is about the side of the expectation that was wrong, so it decides the upset case directly.

**The autocorrelation argument does not decide it**, and an earlier draft of this section leaned on it as
though it did. Damping exists so a favourite cannot farm rating off a weak opponent by running up the
score — a statement about what the term does for *favourites*. It is silent on what should happen when the
underdog wins, so it is compatible with both readings and settles neither.

Read as an absolute value the term would damp an upset and a favourite's blowout identically, which would
mean Massachusetts beating Ohio State by 20 taught the model exactly as much as the reverse.

#### The denominator is floored at 0.25

```python
MOV_DENOMINATOR_FLOOR = 0.25
unclamped   = elo_diff_winner * 0.001 + 2.2
denominator = max(unclamped, MOV_DENOMINATOR_FLOOR)   # clamp: the arithmetic can never invert
if unclamped < MOV_DENOMINATOR_FLOOR:                 # raise: and it never happens quietly
    raise EloDomainError(...)
```

Because `elo_diff_winner` is signed, a large enough upset walks the denominator to zero and through it.
Past zero the multiplier is negative and **a bigger win lowers the winner's rating** — the model running
backwards on the most informative result of the season, returning ratings that conserve correctly, cover
every team, and sit in an entirely believable range. Nothing downstream would catch it.

**§3.1's rescale made this unreachable from the preseason seed, which was not the intent and is worth
recording.** At `ELO_PER_POINT = 28` the seed spanned 211 to 2486 and the floor was reachable:

| At the old scale of 28 | |
|---|---|
| Widest possible gap, HFA included | **2342 Elo** → denominator **−0.14** |
| Best FBS team vs the FCS median | 1853 Elo → denominator 0.35 |
| Opponents of the top team that would cross 0.25 by beating it | **39** |

At 20 the seed spans 579 to 2204, the widest pairing leaves the denominator at **0.58**, and **no** seed
pairing crosses the floor. Crossing raises rather than clamping silently, so the old scale carried 39
pairings that would have reddened a run on a legitimate — if enormous — upset. Fewer false alarms is the
right outcome; a guard that never fires in production is also a guard nothing exercises there, which is
why `mov_denominator` is public and tested directly rather than only through `update`.

It remains reachable in principle: ratings diverge as a season runs, and §12's refit moves the boundary
again.
| …that would carry the denominator negative | **5** |

§12's refit of `ELO_PER_POINT` widens that window. It does not open it.

**0.25 rather than something just above zero**, because the sign flip is not the only failure. At 0.25 the
multiplier is 8.8 and a ten-point win moves a rating by up to 422 Elo — 15 Sagarin points from a single
result, on a scale whose entire FBS spread is 67.2. A game worth that much is not a rating update, it is a
reseed, and the model has no business performing one silently.

**Both the clamp and the raise, and the order matters.** The clamp is what makes the inversion
arithmetically impossible; the raise is what stops a clamped update from being applied without anything
going red. Silence there is the failure this project is built to prevent — a rating that degrades over a
season with every run green. It is the same defence-in-depth shape as the model validators of Phase 0
§4.7: if a later phase decides a clamped update is acceptable and drops the raise, what remains is still
correct arithmetic rather than a silent sign flip.

**FCS games count.** An FBS team losing to an FCS opponent is the single most informative result of its
season and dropping it would be the kind of silent filtering the crosswalk exists to prevent. This is why
the crosswalk spans both divisions (Phase 0 §6.5).

### 3.5 State lives in S3, and is reproducible without it

```
elo/season=2026/week=04/2026-09-14T120500Z.json
```

Write-once, timestamped, same discipline as everything else. It exists to give the write-up a visible
ratings history and to make a run cheap, **not because the pipeline depends on it**: Elo is a pure function
of the seed and the completed games, both of which are already in `raw/`. `cfb elo replay` rebuilds the
entire season's state from snapshots with no network and no state file, and a test asserts the replayed
ratings equal the stored ones.

That property is what makes the stored state safe to keep. A state file that could drift from the
snapshots it was derived from would be a second source of truth; one that can be regenerated and checked is
a cache.

The PRD leaned toward committing Elo state to the repo. That reasoning was tied to the git tamper-evidence
argument §1.1 drops, and it carries the same `contents: write` cost.

#### The accumulation can start late, and the state says where

`replay` folds every completed game of a season, and §3.3 prices each one from the newest Sagarin
snapshot captured **strictly before** its kickoff. A game that kicked off before the earliest such
snapshot exists therefore has no HFA and never will — no later capture can be moved in front of it.

`EloState.folded_from` records the earliest kickoff an accumulation actually folded, and is `null`
when it covered the season entire. It is **the same idea as `PredictionLog.forecast_from` (§4.4) on
the scoring side, and deliberately the same shape of name**: a forecast cannot cover a game that has
already kicked off, and an accumulation cannot cover a game that no page can price. Two names for one
concept is how the next reader concludes they are different things.

Three properties keep it from being a hole in §3.5's argument:

- **Derived, never stored as a constant.** `replay` computes it from the manifests in `raw/` the same
  way on every run, so it is a restatement of the evidence rather than a second source of truth —
  which is precisely what "state is a cache" depends on there not being. A written-down date would be
  the second source of truth this section spends its argument denying.
- **Exactly the unpriceable set, not a heuristic for it.** `hfa_at` fails on one condition and one
  only: no manifest precedes the kickoff. Any game after the earliest manifest therefore has at least
  that one available and cannot fail. So `kickoff <= earliest` is the *complete* failure set, and
  every other missing-HFA case still raises the way §3.3 requires. This is what stops the skip being
  a catch-all that swallows real faults.
- **In the document, and compared by `verify`.** A replay and an advance that disagree about which
  games they folded is exactly what §11 step 5 exists to catch, and it cannot catch it if neither says
  what it folded. The comparison is exact: letting `null` mean "unbounded, match anything" would put a
  permanent hole in the one guarantee this section rests on, to paper over a one-time migration.

**Excluding a season's opening games is expected; excluding all of them is not.** If the bound would
leave nothing, `replay` raises. Skipping the first few is a pipeline that came online after the first
kickoffs. Skipping every one means the captures and the games do not overlap at all, and returning a
seed-only state for that would report "the season has not started" about a season that has — the quiet
wrong answer this module exists to prevent.

**This is transitional, exactly as §4.4's path is.** It arises only because the pipeline came online
*after* the season's first kickoffs: CFBD's week 1 of 2026 opened on 08-27 and the first Sagarin
capture is 08-28T16:50Z, so nineteen completed FCS games sit before any page that could price them.
Every future season seeds from a preseason page captured before a single game is played, so nothing is
skipped and `folded_from` is `null`.

§4.4's corollary applies unchanged, and is the reason this is worth writing down rather than
forgetting: **a bound set on a season the pipeline was live for is evidence of a missing capture, not
of a late start.** If `folded_from` is ever non-null on a season that was covered from the start, a
Sagarin fetch did not happen and the field is the thing that says so.

### 3.6 The seed contaminates one benchmark, and the contamination is measured

In week 1 a prediction is Sagarin's rating gap divided by 28, multiplied by 28, plus Sagarin's HFA — which
is Sagarin's prediction. "Elo vs Sagarin PREDICTOR" is therefore Sagarin against itself early in the
season, and it stops being so gradually rather than at a stated week.

**The closing-line benchmark is unaffected**, and it is the one the PRD names as the headline metric. That
comparison is clean from week 1.

So the wash-out is measured rather than asserted:

- Each week, compute the **Pearson correlation between this model's predicted margins and Sagarin
  PREDICTOR's margins** over that week's slate.
- Publish the series. It declines as results accumulate, and the decline is the evidence.
- **The disclosure stays up while `r >= 0.90`.** The first week it falls below, the accuracy page records
  that week and the note comes down.

A caveat with no retirement condition becomes boilerplate nobody reads, and "not independent" is a claim
that should be able to expire. Correlating margins rather than ratings measures the thing the disclosure is
actually about — whether the *predictions* still track Sagarin's — rather than how much seed is left in the
state.

### 3.7 Win probability never prints 100%

`Texas vs the FCS median` on seeded week-0 ratings is a 59-point gap, and the logistic returns 0.99997.
Rendered naively that is **100%**, and a page whose entire argument is calibration cannot display a
certainty. FBS teams lose to FCS teams.

Probabilities are clamped to `[0.001, 0.999]` before they reach a document, and the UI renders the
endpoints as `<1%` and `>99%`. The clamp is presentational and applied at publish time; the stored
prediction keeps the unclamped value so Brier scores are computed on what the model actually said.

---

## 4. The prediction log

### 4.1 Layout

```
predictions/season=2026/week=04/2026-09-17T120000Z.json
```

One object per week holding every game on that week's slate. **Write-once**, timestamped to the second,
under the same IAM discipline as `raw/`: the publisher role gets `s3:PutObject` on `predictions/*` and **no
`s3:DeleteObject`**. A regenerate writes a second object; the first stays forever.

That is the whole of the integrity story §1.1 keeps. A prediction written Thursday at 12:00 cannot be
replaced by one written Sunday at 18:00 — both exist, both are timestamped, and the pipeline has no verb
that removes either.

`predictions/index.json` is the one mutable object: newest generation per week, so the publish step and the
site do not have to list a prefix. It is derived and rebuildable from a listing.

### 4.2 Shape

```jsonc
{
  "schema_version": 1,
  "season": 2026,
  "week": "04",
  "generated_at": "2026-09-17T12:00:00Z",
  "model": {
    "name": "elo",
    "elo_per_point": 28,
    "k": 20,
    "hfa": 2.41,                       // from the Sagarin manifest this run read
    "hfa_source": "raw/sagarin/season=2026/week=03/2026-09-15T120302Z.meta.json",
    "seeded_from": "raw/sagarin/season=2026/week=preseason/2026-08-28T172006Z.txt",
    "elo_state": "elo/season=2026/week=03/2026-09-14T120500Z.json",
    "sagarin_predictions_from": "raw/sagarin/season=2026/week=03/2026-09-15T120302Z.txt",
    "market_lines_from": "raw/cfbd/season=2026/week=04/lines/2026-09-17T120000Z.json"
  },
  "games": [
    {
      "cfbd_game_id": 401752101,
      "kickoff": "2026-09-19T16:00:00Z",
      "home": "ohio-state",            // canonical ids, never vendor names
      "away": "michigan",
      "neutral_site": false,
      "predicted_margin": 9.5,         // home perspective, always
      "win_probability": 0.756,        // home, unclamped
      "elo_home": 2204,
      "elo_away": 2072,
      "market_line": -7.5,             // CFBD verbatim: NEGATIVE favours home. null if unpriced
      "market_line_source": "DraftKings",
      "sagarin_predictor_margin": 8.0  // benchmark only; null if the game is not on the page
    }
  ]
}
```

The `model` block is what makes a prediction reproducible: it names the exact snapshot the HFA came from,
the exact page the season was seeded from, the exact state object it started from, and the exact captures
the benchmark and the market line were read out of. A prediction that cannot be re-derived is an
assertion, not a record.

`predicted_margin` and `win_probability` are always from the **home** team's perspective, including at
neutral sites where "home" is whatever CFBD says. One convention, stated once, and no sign-flipping logic
anywhere downstream.

### 4.3 `market_line`, and the three things the first real capture changed

An earlier draft of this section called this field `closing_line` and described it as "CFBD, home
perspective; null if not yet posted". **All three halves of that were wrong**, and the first verbatim
`/lines?year=2026&week=1` capture — now `tests/fixtures/cfbd_lines_2026_week01.json`, 143 games and 194
line entries — is what settled it.

**There is no closing line.** The response carries `spread`, the price at the moment of capture, and
`spreadOpen`. There is no field with "clos" anywhere in its name. A Thursday generate could not have a
closing line even if one were published, because the closing line does not exist until kickoff. So the
field is `market_line` and it means exactly one thing: *the market price when this run read it*. §5.3 and
§6.3 use the same name for the same reason.

**The sign is the opposite of ours.** `spread: -29.5` with `formattedSpread: "Iowa State -29.5"` and Iowa
State at home, so **negative favours the home team**, while `predicted_margin` positive means the home
team wins by that much. Verified across all 194 entries, both directions, no exceptions.

The vendor value is stored **verbatim**, so the document records what CFBD published rather than an
interpretation of it, and `sources.market_home_margin` is the single place the two conventions are
reconciled. Comparing the two without converting yields an against-the-spread record that is complete,
plausible and exactly backwards — a failure with no symptom, which is why the conversion is a named
function with a test that fails in both directions rather than a minus sign at a call site.

**A book is not a string.** The capture spells one book two ways, `DraftKings` (131) and `Draft Kings`
(12), so providers are normalized through an exact alias table before anything selects among them —
selecting first drops the 12 games whose only line is the second spelling. And selection is a real
decision, not a tidy-up: DraftKings and Bovada disagree on **21 of the 143 games**, so preference order
changes the published number. `PROVIDER_PREFERENCE` is `("DraftKings", "Bovada")`, DraftKings first
because it priced 143 of 143 against Bovada's 51 — a coverage fact rather than a judgement about either
book. An unrecognised provider raises; skipping it would drop a line silently, and a book nobody has seen
before is exactly when a person should look.

**`null` is legal and is never a zero.** A game no book priced has `market_line: null` and
`market_line_source: null`. Zero is a pick'em — a real line saying the market has no favourite — and
anything that conflates the two puts unpriced games into the §5.3 ATS record as pushes against a spread
nobody quoted.

---

## 5. Scoring, and the join

### 5.1 The join key is `cfbd_game_id`

A result joins back to the prediction that anticipated it on CFBD's game id, carried on the prediction when
it is written.

This is the one place the project uses a vendor identifier as a key, and the reason is that the natural
alternative breaks on real games. `(season, week, home, away)` fails when a game moves week for weather,
and it fails at neutral sites where the two sources can disagree about which team is nominally home — both
of which happen every season and neither of which announces itself. The game id survives both.

Canonical slugs remain the identity for *teams* everywhere, including inside the prediction rows. The
vendor id is used for one thing: matching a result to the prediction of the same game.

### 5.2 Failure modes are errors, not filters

```python
# elo/scoring.py
def score_week(
    predictions: PredictionLog,
    results: list[RawGame],
    *,
    results_fetched_at: datetime,
    now: datetime,
) -> ScoredWeek: ...
```

**Both departures from this section's first draft are forced, not stylistic.**

`predictions` is a `PredictionLog` rather than a bare dict because the third failure mode below
compares the prediction's teams against the result's, and a mapping of margins cannot answer that. The
dict was written before §4 existed and gave the log a type at all.

`results_fetched_at` is what makes the *second* failure mode decidable. A prediction with no result is
fine while the game is unplayed and an error once it has been played — and CFBD's `/games` shape carries
no `completed` flag, only nullable scores, which is exactly the state an unplayed game and a failed join
share. So the boundary is the evidence rather than a clock: **a game that kicked off before the results
capture was taken should have a score in it.** That is the same rule §3.3's HFA selection settled on, for
the same reason — a wall clock cannot be replayed, and a scoring run that depended on one could not be
re-derived from `raw/` later.

- A result with no matching prediction → `UnscoredGameError`. Either the slate changed after generation or
  the prediction run missed a game, and both are worth a red run.
- A prediction with no matching result → **not** an error if the game has not been played, an error if it
  has. A postponed game is normal; a completed game with no result is a join that failed.
- A prediction whose `home`/`away` disagree with the result's teams → `UnscoredGameError`. The id matched
  and the teams did not, which means one of them is wrong.

Nothing is dropped, nothing is warned about. A game silently vanishing from the scored set is the exact
failure the accuracy page cannot survive.

### 5.3 What gets computed

Per game: `actual_margin`, `error = predicted_margin - actual_margin`, `abs_error`, whether the pick beat
the market line, and the Brier contribution `(win_probability - outcome)²`.

**Beating the line is computed through `sources.market_home_margin`, never against the stored value.**
`market_line` is CFBD's sign convention and `predicted_margin` is ours; §4.3 has the detail. A comparison
that skips the conversion produces an ATS record that looks entirely normal and is inverted.

A game with `market_line: null` is **excluded from the ATS record and counted as excluded**, rather than
scored against a zero. The sample size travels with the record for this reason.

**A model margin exactly equal to the market's is excluded too, and counted separately.** There is no
side to take, so there was no bet — and a push is a position that tied, not the absence of one. Counting
it as a push would assert a bet that was never made and pull the record toward 50%, which flatters. It
fires almost never, since continuous margins rarely land exactly on a half-point line; that makes it
cheap to get right rather than safe to ignore.

So the record carries five counters and they account for every game scored that week:

```
wins + losses + pushes + excluded_no_line + excluded_no_edge == games
```

That identity is the point. A bare `2-2` cannot distinguish four priced games from forty where
thirty-six had no line, and a game that fell out of the record entirely would be invisible in a
win-loss count — it shows up only in a denominator that no longer adds up.

Per week and per season, for **Texas** and for the **full slate** separately, as the PRD requires:

- MAE against actual margin, and the same figure for the market line and for Sagarin PREDICTOR. **Each
  carries its own denominator**: the market prices a subset of the slate and Sagarin's page covers a
  different subset again, so averaging either over games it never priced would flatter the benchmark
- Every mean is `null` rather than `0.0` when it has nothing to average. Texas has bye weeks, and a zero
  would draw a point on the accuracy page claiming a perfect prediction that was never made
- Brier score and a calibration curve (predicted probability bucket vs observed win rate)
- Record against the spread, **always with the sample size attached**
- The week's Pearson correlation against Sagarin PREDICTOR (§3.6)

Scored weeks are written to `scored/season=2026/week=04/<ts>.json`, write-once, same rules.

### 4.4 A run forecasts what has not happened

§4.1 says a prediction log is "every game on that week's slate", which assumed a
run always precedes the whole week. **CFBD's week 1 of 2026 is ten days long and
spans two Saturdays**, and this pipeline came online between them, so that
assumption is not safe.

A run forecasts the games whose kickoff is at or after the moment it runs, and the
HFA boundary is the first kickoff **among those** rather than the slate's. On any
ordinary week the two are identical. They came apart once, and the earlier
boundary refused eight days of forecastable games because one game on the slate's
first day predated the first Sagarin capture in existence.

`forecast_from` records the boundary when a log is partial and is `null` otherwise.
§5.2's first failure mode reads it: a result that kicked off before the log began
forecasting was never forecastable, which is a fact about when the pipeline
started rather than a join that failed.

**This is a transitional path, not a normal mode.** It exists because a pipeline
has to come online at some moment, and that moment landed inside CFBD's ten-day
week 1 of 2026. From week 2 onward every week has Sagarin snapshots behind it and
a Thursday run that precedes the whole slate, so `forecast_from` is `null` and a
log covers its week entire — which is what §4.1 says and what it will keep saying.

Two things follow, and both matter more than the mechanism:

- **A reader must be told.** A week forecast in part produces figures that are
  correct about fewer games than their label implies, which is the seed
  disclosure's problem wearing different clothes. `forecast_from` is carried from
  the prediction log into `ScoredWeek`, into §6.4's `by_week`, and onto the page,
  which marks the week *partial* and says why.
- **It should stay rare enough to notice.** If `forecast_from` is ever set on a
  week the pipeline was live for, something skipped a scheduled run — the field
  is then evidence of a gap rather than of a start.

This does **not** move to per-game HFA. A prediction run happens at one moment and
cannot use a snapshot that lands later, which is what §4.2's single `hfa` field
means and what `test_a_snapshot_landing_mid_week_is_not_used` pins. Per-game HFA
belongs to `score` and `replay`, which reconstruct what was knowable before each
game.

### 5.4 Which generation is scored, and what the document records

A week can hold several prediction objects — §4.1 makes them write-once precisely so a regenerate adds
a key rather than replacing one — so a scoring run has to choose, and **the newest is the wrong
choice.** One of them can have been written on Sunday. Grading it would publish an accuracy figure for
a forecast made with the results in hand, which is the one overclaim §1.1 gives up git in order not to
make.

**The rule: the newest generation written strictly before its own slate's first kickoff.** If none
qualifies, the week is not scored and the run goes red.

The boundary comes from each candidate document's own slate rather than from the week's results. The
two are the same number in the ordinary week and they come apart in the case that matters: a game
moved *into* the week from an earlier one has already been played by the time the week is predicted,
so a boundary taken from the results would sit in the past and reject an honest Thursday generation.
This is the same property §11 step 1 checks from the bucket side, used rather than only asserted.

**The scored document records `results_fetched_at`.** It is a model input, not a log field: §5.2
decides "unplayed, or a join that failed" against it, so the same week re-scored against a different
capture can legitimately reach a different verdict, and a document that named the predictions it
graded but not the evidence it graded them against could not say why. It comes from the manifest of
the target week's own `/games` capture and never from a wall clock, for the reason §3.3 gives.

---

## 6. The JSON contract

### 6.1 Page-shaped, not resource-shaped

```
/cfb/data/
  next-game.json        -> /cfb
  slate.json            -> /cfb/slate
  accuracy.json         -> /cfb/accuracy
```

**`slate.json` was added in Phase 1 and is not in this section's original three.** The routes above
showed one game a week while the pipeline forecast a hundred and twenty. Its own route rather than a
section of `/cfb`, so the one-fetch rule survives and the front page stays a small document that
loads fast. It is **home perspective**, unlike `next-game.json`: a slate has no subject team to
re-sign against, and mixing the two conventions in one contract is how a page draws a favourite as an
underdog.

**The two `notes/` documents are dropped, resolved 2026-08-29.** This section used to
publish `notes/index.json` and `notes/<slug>.json`, which contradicted §7 — that section says the
finished note is committed to the repo as MDX under `frontend/app/cfb/notes/`, "because it is prose
that ships with the site rather than data the pipeline owns". Both could not be the source for
`/cfb/notes/[slug]`.

§7 wins. The pipeline's only note output is the scaffold it writes to `notes/` in the bucket, which a
person edits and commits; the site build publishes it. The route therefore does *zero* fetches, which
satisfies this section's one-fetch rule more completely than a JSON document would have.

Each route does exactly one fetch and renders. No client-side joining, no request waterfall, and the pages
stay free of composition logic — which matters because they are static-exported and the PRD forbids
prediction logic in them.

The cost is duplication between documents and a generator that has to change when a page does. That is the
right trade at three routes; it would be the wrong one at thirty.

### 6.2 Every document carries the same envelope

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-09-18T12:00:00Z",
  "season": 2026,
  "week": "04",
  ...
}
```

`schema_version` is checked by the routes. A document from a newer generator than the deployed page
renders a plain "data is newer than this page" state rather than throwing — the site and the pipeline
deploy independently (PRD), so the two versions genuinely can differ for a few minutes.

**It moves only for a change that breaks a reader: a renamed field, a removed field, or a field whose
meaning changed.** Adding an optional field is not one of those. An older page ignores a key it does
not know, and a newer page renders the absence, so nothing anywhere is misread and there is nothing
for the mechanism to protect against.

The reason to hold that line is what the mechanism costs when it fires. Showing "data is newer than
this page" replaces a working page with an apology, and **firing it for changes that break nothing is
how it stops meaning anything** — do it often enough and nobody distinguishes the one time it is
real. Reserving it for the three cases above is what keeps the signal worth showing at all.

So the release rule for an additive change is ordering rather than versioning: **deploy the routes
first, then publish.** A page that tolerates a missing optional field is correct for the window in
between; the reverse order would put every visitor in front of the stale state for no gain. That
window is not hypothetical — the new page reading the old document is the *first* thing that happens
in production on every such release, which is why it is covered by a route test
(`frontend/tests/cfb-old-document.spec.ts`) rather than by an assumption.

### 6.3 `next-game.json`

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-09-18T12:00:00Z",
  "game": {
    "kickoff": "2026-09-19T19:30:00Z",
    "opponent": "Oklahoma",
    "home": true,
    "predicted_margin": 9.5,
    "win_probability": 0.78,
    "market_line": -7.5,
    "line_source": "DraftKings"
  },
  "as_of": { "week": "04", "elo": 2113, "national_rank": 5 }
}
```

Rendered team names appear here rather than canonical ids: this document is consumed by a page, and the
crosswalk's job ends at the boundary of the pipeline.

`line_source` is the resolved book from §4.3, carried through from the prediction row. It said
`"consensus"` in an earlier draft, which was a guess — CFBD publishes per-book prices and no consensus,
so the page would have been attributing a DraftKings number to something that does not exist.

**Four things the sketch above leaves out, all of them found by generating the document.**

- **The game shown is the team's next *unplayed* game, wherever it is** — not the
  featured game of the week being published, which are the same thing on an
  ordinary week and came apart in 2026's ten-day week 1. The `game` block carries
  its own `week` for that reason: the envelope's week labelled a week 1 game
  "Week 2".
- **`game` is nullable, and a bye is why.** Texas has bye weeks; a page blanked entirely for one would
  be a worse statement than a missing fixture. `as_of` is populated either way, because the ratings are
  true whether or not there is a game that week.
- **`team` is on the document.** Every other field is *about* a team the sketch never names, and a
  document whose subject is implicit is one the page has to hardcode.
- **`predicted_margin` and `win_probability` are signed for the subject team, not the home team.**
  Everything in `predictions/` is home-perspective (§4.2) and this document is read by a page about one
  team. An away game left in the storage convention renders perfectly and says the opposite thing.
  `market_line` is **not** re-signed: it is the book's own quote, printed beside `line_source`.
- **`history`, `last_result`, `opponent_rank` and `opponent_elo` are later additions**, all optional
  and all pure projections of documents the pipeline had already written. `history` is Texas's rating
  and rank at every stored `elo/` state; `last_result` is the newest scored game the team appears in;
  the opponent's standing comes from the same state `as_of` names, so the two rankings on the page
  cannot be from different weeks.
  - `opponent_rank` is `null` for an FCS opponent. The FBS table has no place for one and a rank on a
    different denominator would be a different number wearing the same word — the same reason
    `national_rank` carries `fbs_teams`.
  - **The page must not draw a chart through one point.** The first `elo/week=NN` state of 2026 lands
    on 09-13, because `cfb score` grades the last *completed* week and CFBD's week 1 runs to 09-08.
    Until then `history` is the preseason seed alone, and a one-point line is indistinguishable from a
    broken chart. `/cfb` shows the rating and says the series has not started rather than drawing it.
- **`as_of` carries `fbs_teams`, and `national_rank` is among the FBS.** The Elo state rates all 266
  teams Sagarin covers, 128 of them FCS, so a rank over the whole table is a different number wearing
  the same word. The denominator travels with it for the reason §5.3 makes every sample size travel.

### 6.4 `accuracy.json`

Carries both records side by side, the calibration curve, the by-week series, and the seed disclosure:

```jsonc
{
  "schema_version": 1,
  "generated_at": "...",
  "texas":      { "games": 4, "mae": 8.1, "line_mae": 7.4, "ats": "2-2", "brier": 0.21 },
  "full_slate": { "games": 231, "mae": 11.9, "line_mae": 10.8, "ats": "118-113", "brier": 0.19 },
  "calibration": [ { "bucket": "70-80%", "predicted": 0.75, "observed": 0.71, "n": 38 } ],
  "by_week": [ { "week": "01", "mae": 14.2, "sagarin_r": 0.98 } ],
  "seed_disclosure": {
    "active": true,
    "threshold": 0.90,
    "current_r": 0.94,
    "retired_week": null
  }
}
```

`backtest` is a fourth block, `null` unless a week has been scored retrospectively by `cfb backtest`.
**It is not the model's record and the page must not present it as one.** A backtested week was
scored after its games were played, so it carries none of the evidence `predictions/` exists to
provide — folding it into `full_slate` would spend the property §1.1 gives up git to keep. It is kept
apart by prefix (`backtest/`, which `scored_weeks` does not read by default) rather than by a flag,
because a prefix cannot be overlooked the way a boolean can.

For week 1 the figures measure something else again: the seed is
`1500 + (rating - mean) * ELO_PER_POINT` and
the preseason page's rating columns are identical (§1.2), so a week 1 forecast reproduces Sagarin's
PREDICTOR exactly and `sagarin_r` opens at 1.0. `measures_the_seed` carries that into the document,
and the page says it in words.

`seed_disclosure` is what §3.6 renders. When `current_r` first falls below `threshold`, `active` goes false
and `retired_week` records the week — and the page keeps showing the fact that it retired, because a
disclosure that vanishes without trace is worse than one that never appeared.

**Retirement is one-way.** A later week climbing back above the threshold does not un-retire it. The
claim being retired is "these ratings are still a restatement of Sagarin's page", and once that has
been false for a week it is not something the page can assert again. `current_r` keeps showing the
newest measurement so both facts are on the page. A `null` correlation — a week Sagarin's page covered
fewer than two games of — is not a low one and retires nothing.

**Three corrections to the sketch above.**

- **`ats` is an object, not the bare string.** §5.3 says the sample size always travels with the
  record, and `"2-2"` cannot distinguish four priced games from forty where thirty-six had no line.
  It carries `record` plus §5.3's five counters. Where §6.4 and §5.3 disagree, §5.3 governs.
- **`line_mae` carries `line_games`**, its own denominator, which is smaller than `games`. Same for
  `sagarin_mae` and `sagarin_games`. Averaging a benchmark over games it never priced flatters it.
- **`through_week` is a separate field from the envelope's `week`.** The envelope's week is the run's
  — a Friday publish is *for* a week nobody has played — and `through_week` is the newest week the
  document actually has results for. `null` before the season's first Sunday, which is also when every
  mean in the document is `null` and both records read zero games. That is a legal, publishable
  document: refusing to publish it would fail §8's SLO over the absence of results nobody could have
  had.

### 6.5 Caching and invalidation

`/cfb/data/*` is served from the data bucket through the existing distribution (Phase 0 §10.2 deferred this
work to Phase 1). Documents are small and change weekly:

- `Cache-Control: public, max-age=300, s-maxage=3600` on the JSON.
- The publish step issues a CloudFront invalidation for `/cfb/data/*` after upload. The site pipeline's
  invalidation is manual today (root `CLAUDE.md`); this one is not, because a stale prediction is the
  failure mode the publish SLO exists to prevent.

**Where the header is set, and why it is not in Terraform.** The behavior runs on the managed
CachingOptimized policy, which honours the origin's `Cache-Control` rather than imposing a TTL. So the
directive is written at upload time (`cfb.publish.CACHE_CONTROL`, passed through
`storage.put_json`) and the distribution has no opinion about it. One place decides how long a
document is good for and it is the place that knows what the document is — a TTL in `cfb-wiring.tf`
would be a second answer, in a file that never sees the JSON, that silently wins.

**The invalidation is a separate step from the upload, and a separate log line.** The upload is what
makes the new numbers exist; the invalidation only makes them visible sooner. A failure of the second
is a slow page and a failure of the first is a wrong one, and a Friday run has to be readable on that
distinction. `cfb publish` therefore writes both documents, logs `published`, and only then
invalidates and logs `invalidated`. When the store is not `s3://` it logs a skip naming the reason
rather than claiming an invalidation it never made.

**The bucket is reached through an Origin Access Control, not a website endpoint.** The site bucket is
public-read behind a custom origin (root `CLAUDE.md`); the data bucket blocks all public access and is
read by CloudFront as a signed principal, with `cfb/terraform` allowing `s3:GetObject` on `cfb/data/*`
only and conditioned on this distribution's ARN. `raw/` is therefore unreachable from the internet
because of a policy rather than because no behavior happens to point at it.

**Where the header is set, and why it is not in Terraform.** The behavior runs on the managed
CachingOptimized policy, which honours the origin's `Cache-Control` rather than imposing a TTL. So the
directive is written at upload time (`cfb.publish.CACHE_CONTROL`, passed through
`storage.put_json`) and the distribution has no opinion about it. One place decides how long a
document is good for and it is the place that knows what the document is — a TTL in `cfb-wiring.tf`
would be a second answer, in a file that never sees the JSON, that silently wins.

**The invalidation is a separate step from the upload, and a separate log line.** The upload is what
makes the new numbers exist; the invalidation only makes them visible sooner. A failure of the second
is a slow page and a failure of the first is a wrong one, and a Friday run has to be readable on that
distinction. `cfb publish` therefore writes both documents, logs `published`, and only then
invalidates and logs `invalidated`. When the store is not `s3://` it logs a skip naming the reason
rather than claiming an invalidation it never made.

**The bucket is reached through an Origin Access Control, not a website endpoint.** The site bucket is
public-read behind a custom origin (root `CLAUDE.md`); the data bucket blocks all public access and is
read by CloudFront as a signed principal, with `cfb/terraform` allowing `s3:GetObject` on `cfb/data/*`
only and conditioned on this distribution's ARN. `raw/` is therefore unreachable from the internet
because of a policy rather than because no behavior happens to point at it.

---

## 7. The weekly note

The pipeline generates the scaffold from `scored/`: predicted margin, actual result, error, the line,
whether the model beat it, season-to-date figures, and the model's biggest national miss that week. Written
to `notes/season=2026/week=04/scaffold.md` in the bucket.

Commentary is added by hand and the finished note is committed to the repo as MDX under
`frontend/app/cfb/notes/`, because it is prose that ships with the site rather than data the pipeline
owns. That is the one thing in this phase that is a human step by design, and the PRD's fifteen-minute
target is what the scaffold exists to protect. §6.1's two `notes/` JSON documents are dropped in
favour of this.

**The key is `notes/season=2026/week=04/<ts>.md`, not the fixed `scaffold.md` named above.** A fixed
name cannot be written twice: `put_bytes` refuses an existing key and the publisher role has no
`s3:DeleteObject`, so the second run of a week — after a rescore, or after the first scaffold was
edited badly — would fail on the write instead of producing a scaffold. Making it the one mutable
non-JSON object in the layout would buy nothing, since it is derived entirely from `scored/` and a
person simply takes the newest.

**Team names in the scaffold are rendered, never canonical ids.** The first scaffold generated said
"Texas hosted ohio-state" and "North Carolina at TCU" appeared as "north-carolina at tcu" — §6.3's
rule broken in the most visible possible place, a document whose entire purpose is to be read by a
person and then published as prose.

`cfb note` has no `in_season` guard, unlike every other command in §9. The others are scheduled and
gate on the calendar so an out-of-season cron is a skip rather than a failure; this one is only run by
hand, by someone who has decided to write about a specific week, and skipping over the date would be
answering a question they did not ask.

---

## 8. Workflows and the weekly rhythm

| When | Workflow | Does |
|---|---|---|
| Sun 12:00 UTC | `cfb-cfbd.yml` *(exists)* | ingest final scores and lines for the completed week |
| Sun 12:30 UTC | `cfb-score.yml` | update Elo, score last week's predictions, write `scored/` |
| Tue 12:00 UTC | `cfb-sagarin.yml` *(exists)* | snapshot, freshness check |
| Thu 12:00 UTC | `cfb-predict.yml` | generate and write `predictions/` for the coming slate |
| Thu 12:30 UTC | `cfb-publish.yml` | build `/cfb/data/*`, upload, invalidate |
| Fri 12:00 UTC | `cfb-publish.yml` | again, for lines that moved |

Every step is a command a human runs locally, per Phase 0 §11. All of them gate on `calendar.in_season`.

**The publish is the SLO**, and its deadline is **first kickoff of the week**. It can genuinely be missed,
which is what makes the alerting mean something. A failed publish is a red run and an email; there is no
retry-until-it-works loop, because a prediction published after kickoff is not a prediction.

### 8.1 Why the deadline is not "first kickoff Saturday"

It said that until it was measured. The wording assumed a Saturday sport, and college football is not one:
week 1 of 2026 has **40 Thursday games and 18 Friday games**, and the season's first kickoff was
**Thu 27 Aug 22:00 UTC**. A single Friday 12:00 UTC publish lands *fourteen hours after* a Thursday
5:00 PM CDT kickoff, so the first publish of the week was already carrying finished games as forecasts —
and because results are only captured Sunday 12:00 UTC, they stayed unmarked until Sunday.

The predictions themselves were never late; that distinction is the whole point of splitting these jobs.
`cfb predict` runs Thursday 12:00 UTC and writes before kickoff, which is the claim §11 step 1 checks. It
was the *publish* that missed, so the fix is a second publish rather than an earlier forecast.

**Thursday 12:30 is now the run that has to make the deadline, and Friday is a refresh.** Half an hour
after `cfb-predict` is the same gap `cfb-score` leaves after `cfb-cfbd`, for the same reason: Actions cron
drifts 5–15 minutes under load.

**The deadline is still not met in every week, and saying so is the point of writing it down.** November
MACtion plays Tuesday and Wednesday nights, inside the same CFBD week and roughly 36 hours *before* the
Thursday run. Meeting "first kickoff of the week" literally in those weeks needs a Monday or Tuesday
publish. An SLO the schedule is known to miss in four weeks of the season is worth stating as such rather
than quietly redefining the deadline to whatever the cron already achieves — which is exactly how
"first kickoff Saturday" came to be written.

---

## 9. CLI additions

```
uv run cfb elo seed --season 2026                    # from the preseason snapshot; refuses in-season
uv run cfb elo replay --season 2026 [--through-week N]   # rebuild state from raw/, no network
uv run cfb predict --season 2026 --week N            # write predictions/; defaults to the coming week
uv run cfb score --season 2026 --week N              # join results, write scored/; defaults to completed
uv run cfb publish --season 2026                     # build and upload /cfb/data/*
uv run cfb note --season 2026 --week N               # write the scaffold
```

`--week` defaults follow the same calendar logic `fetch cfbd` already uses: `predict` takes the week that
is *about to* be played, `score` the week that just completed. No week arithmetic in YAML.

### 9.1 Errors this phase adds to the Phase 0 §9 hierarchy

Every one is a `CfbError`, so the Phase 0 §9 contract holds unchanged: exit 1, a message on stderr, a red
run, and nothing caught and demoted to a warning.

| Error | Raised when |
|---|---|
| `SeedStateError` | `seed()` was handed a snapshot whose `page_state` is not `preseason` (§3.2) |
| `EloDomainError` | `update()` was handed a game it defines no outcome for: no result, a tie, or a gap past the §3.4 floor |
| `UnratedTeamError` | a game named a canonical id the ratings do not hold (§3.4) |
| `ReplayError` | a season cannot be rebuilt from `raw/`: no preseason page, or no snapshot with an HFA before a kickoff (§3.5) |
| `StateMismatchError` | a replay did not reproduce the stored state (§3.5, §11 step 5) |

Each has a name of its own rather than sharing `ParseError`, and the reason is the same in every case:
**nothing was wrong with the source data.** A `ParseError` sends whoever reads it back to the page to find
a malformed row that is not there. These say what actually happened — a command run at the wrong time, a
result outside the model's defined range, a cache that stopped being reproducible.

`SeedStateError` in particular is asserted by name in `tests/test_seed.py`. Asserting `CfbError` would have
passed on any failure at all, including the `UnmappedTeamError` a broken crosswalk raises a few lines
earlier, which is the one thing a test of a refusal must not do.

---

## 10. Out of scope

Explicitly, so none of it creeps in around week three:

- Any model beyond this Elo baseline — no SP+, no efficiency metrics, no ensembles
- Historical backfill of prior seasons (Phase 2, and the thing that unblocks refitting §3.1 and §3.4)
- Fitting `ELO_PER_POINT`, `K`, or HFA from data
- Live or in-game win probability
- Per-team pages, user accounts, any always-on backend
- Server-side rendering of prediction data
- Paginating the accuracy page — defer until there are ten weeks, per the PRD
- Kubernetes

---

## 11. End-to-end verification

Phase 1 is done on **one Saturday** where all of this happened with no manual intervention:

```bash
# 1. Predictions existed before first kickoff, and are immutable
aws s3 ls s3://travispollard-cfb-data/predictions/season=2026/week=04/ --profile tp-site
aws s3api list-object-versions --bucket travispollard-cfb-data \
  --prefix predictions/season=2026/week=04/ --profile tp-site
#    expect: generated_at strictly before the earliest kickoff that week; one version per key

# 2. The site served them
curl -s https://travispollard.com/cfb/data/next-game.json | python -m json.tool

# 3. Sunday scored them, and every game joined
aws s3 cp s3://travispollard-cfb-data/scored/season=2026/week=04/<ts>.json - --profile tp-site
#    expect: games scored == games predicted, no UnscoredGameError in the run

# 4. The accuracy page reflects it with no site deploy
curl -s https://travispollard.com/cfb/data/accuracy.json | python -m json.tool

# 5. State is a cache, not a source of truth
uv run cfb elo replay --season 2026 --through-week 04
#    expect: byte-identical ratings to elo/season=2026/week=04/<ts>.json
```

Step 5 is the one that proves §3.5's claim. A stored state file nobody can regenerate is a second source of
truth wearing a cache's clothes.

---

## 12. Open questions

- **`ELO_PER_POINT = 20` is probably still slightly too high, and the reason is worth stating precisely.**
  The σ 14–16 range §3.1 fits against is scatter around **the market's** number — the closing spread. This
  model is worse than the market, which is the premise of publishing an ATS record at all, so margins
  scatter *further* around our predictions than around a book's. Fitting to the market's σ therefore
  understates our own, and understating σ is exactly the overconfidence §3.1 set out to remove. Correcting
  for it points at **17–18** rather than 20.
  - 20 is used now because it is defensible from published figures, and because §5.3's calibration curve is
    the thing that should settle it — computed from games this project stored and predicted, against its
    own errors rather than a book's. That is the job this section already assigns it. Moving to 17 on the
    strength of an argument rather than a measurement would repeat the mistake that produced 28.
- **`K = 20` and the MOV multiplier constants are conventional, not fitted.** They are the least defensible
  numbers in this spec and Phase 2's backfill is what settles them. Until then the calibration curve in
  §5.3 is the evidence for whether they are wrong. §3.4 records that `K`'s *effective* value moved when
  `ELO_PER_POINT` did, so a refit has to consider the pair rather than either alone.
- **`MOV_DENOMINATOR_FLOOR = 0.25` is invented, and it is the newest number here with no source.** §3.4
  argues the *shape* — a floor has to exist, because without one the multiplier inverts and a win lowers a
  rating — and that argument is sound at any positive value. Where to put it is a judgement about how much
  a single game may move a rating, made with no data: 0.25 caps one result at ~422 Elo, which is chosen for
  being obviously too much rather than for being measured. Phase 2's backfill is what replaces it, and the
  raise beside the clamp is what guarantees the question gets asked rather than silently answered — every
  game that crosses it is a red run naming the gap that got there.
  - **It is now a pure invariant guard rather than a tunable, and §12's retirement condition for it
    can never fire.** That condition was: if the runs it produces turn out to be legitimate FBS-vs-FCS
    upsets rather than data faults, the floor is too high. At `ELO_PER_POINT = 20` it produces no runs
    at all — the widest preseason pairing leaves the denominator at **0.58** against a floor of 0.25 —
    so there is no evidence it can ever generate about its own value. A number that cannot be
    disconfirmed is not a tunable.
  - **It stays anyway, and the reason is §12's own refit.** The argument for the floor is about the
    *shape* of the arithmetic — past zero the multiplier inverts and a bigger win lowers the winner's
    rating — and that argument holds at any positive value. §12 expects the calibration curve to push
    `ELO_PER_POINT` further down, toward **17–18**, which widens the Elo spread again and moves the
    boundary back toward reachable. Removing a guard because the current constant happens to clear it,
    when the open question in this very section is whether that constant should move, would be
    removing it exactly before it is needed.
  - **§3.1's rescale is what made it unreachable.** At 28 the seed spanned 211 to 2486 and 39 of the
    top team's opponents would have crossed the floor by beating it, 5 of them driving the denominator
    negative; at 20 the seed spans 579 to 2204 and none do. That removes 39 potential false alarms on
    legitimate upsets — good — and also removes the only production path that would ever have
    exercised the guard, which is why `mov_denominator` is public and tested directly rather than
    reached only through `update`.
- **What happens when a game is cancelled after prediction and never played.** §5.2 treats it as
  not-an-error while unplayed, which is indefinitely true for a cancelled game. Probably wants an explicit
  cancellation signal from `/games` rather than a timeout.
- **Whether `hfa` should be per-week or fixed at the preseason value.** §3.3 takes the current snapshot's,
  which means HFA moves during the season for reasons unrelated to home field. Cheap to change, worth a
  look once there is a season of data.
- **Whether the accuracy page needs pagination.** Deferred by the PRD until ten weeks exist.

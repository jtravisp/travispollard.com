# CFB forecast pipeline

An Elo model for college football that predicts every FBS game, writes each
prediction to immutable storage **before kickoff**, scores it against the result
on Sunday, and publishes the record — right or wrong — to
[travispollard.com/cfb](https://travispollard.com/cfb).

The interesting part is not the model. It is that the model cannot lie about how
it did. Every number on the site is traceable back to a byte-for-byte copy of
what a vendor served, and nothing in the pipeline has a verb that deletes one.

- **`/cfb`** — Texas's next game
- **`/cfb/slate`** — every game the model forecast this week
- **`/cfb/accuracy`** — how it has actually done

---

## The one idea

**A dropped row is the only failure this project genuinely cannot survive.**

Everything the accuracy page publishes is a mean. A mean over a set that quietly
lost a game is wrong in no way a reader can see — the number renders, the page
looks fine, and the claim is false. So the whole design is arranged so that
losing a row is impossible or loud:

| Rule | Where |
|---|---|
| Raw source bytes are written before anything parses them, and never overwritten | `storage.put_bytes`, conditional `IfNoneMatch` PUT |
| Validation failures **raise**. Never return `None`, log-and-continue, or coerce | everywhere; `models.validating` is the boundary |
| An unmapped team name is an error, never a fuzzy match | `crosswalk/` |
| Three join failures are errors, not filters | `elo/scoring.py`, SPEC §5.2 |
| A mean with nothing to average is `null`, never `0.0` | `elo/scoring.py`, and preserved to the page |
| Every mean carries its own denominator | `Accuracy`, `AtsRecord`, and the JSON contract |

The last two matter more than they look. A bare `2-2` against the spread cannot
distinguish four priced games from forty where thirty-six had no line, and a
`0.0` MAE on a bye week draws a point claiming a perfect prediction nobody made.

---

## Architecture

```
                  Sagarin page            CFBD /games /lines /teams /calendar
                       |                                |
                       v                                v
                   raw/sagarin/                     raw/cfbd/
                       \                                /
                        \___________  ______________/
                                    \/
                            immutable, timestamped,
                            manifest beside every object
                                    |
        +---------------------------+---------------------------+
        |                           |                           |
        v                           v                           v
    elo/  (state)          predictions/  (write-once)      scored/  (write-once)
   a cache, provably                 |                           |
   rebuildable from raw/             +------------+--------------+
        |                                         |
        |                                         v
        +-------------------------------->  cfb/data/*.json   (mutable, derived)
                                                  |
                                                  v
                                    CloudFront -> Next.js routes
```

### Storage layout

One S3 bucket, `travispollard-cfb-data`, with prefixes that differ in exactly one
respect — whether they can be rewritten:

| Prefix | Written by | Mutable? |
|---|---|---|
| `raw/sagarin/`, `raw/cfbd/` | `cfb fetch` | **No.** The evidence. `.meta.json` manifests beside each object are the one exception, and only to append parse results |
| `elo/` | `cfb elo seed`, `cfb score` | No — but it is a **cache**, not a source of truth |
| `predictions/` | `cfb predict` | No. A regenerate writes a new key; the first stays |
| `scored/` | `cfb score` | No. A rescore cannot quietly replace Sunday's numbers |
| `backtest/` | `cfb backtest` | No. Deliberately a separate prefix — see below |
| `notes/` | `cfb note` | No |
| `cfb/data/` | `cfb publish` | **Yes.** Derived, rebuildable, and the only thing the site reads |

Write-once is enforced by a conditional `IfNoneMatch` PUT, *not* by IAM. The
publisher role also has no `s3:DeleteObject`, which is the second layer rather
than the first — worth knowing before reading the policy as the whole guarantee.

### Modules

| Module | Does |
|---|---|
| `collectors/` | Fetch and store raw bytes. Never parse-and-discard |
| `parsers/` | Sagarin's fixed-width page → structured rows |
| `crosswalk/` | Vendor names → canonical ids. A versioned artifact with tests |
| `sources.py` | Read model inputs back out of `raw/`. **The one place** "which games, which names, which HFA" is decided |
| `elo/` | The model: `seed`, `update`, `predict`, `state`, `scoring` |
| `replay.py` | Rebuild a season from `raw/` alone; `advance` one week |
| `predict.py` | The prediction log |
| `publish/` | Build the site's documents; `notes.py` builds the weekly scaffold |
| `cdn.py` | The CloudFront invalidation seam |
| `cli.py` | A thin shell. Every command is one a human runs locally |

`sources.py` exists because three consumers — `replay`, `advance`, `predict` —
must agree on all three of those selections, and §11's replay check is only
meaningful if they do. Two copies of "the newest Sagarin snapshot before kickoff"
is how that check starts failing for reasons unrelated to the model.

---

## The prediction system

### Seeding

Elo starts from Sagarin's **preseason RATING** column, mapped
`1500 + (rating − mean) × ELO_PER_POINT`, centred on the FBS mean. This reverses the PRD,
and the reason is that the alternative is worse on the page that matters: a
uniform 1500 start predicts Texas–Kennesaw State as a coin flip through
September.

The cost is measured rather than waved away. A week-1 prediction is
*arithmetically identical* to Sagarin's PREDICTOR — the preseason page's four
rating columns are the same number, so an Elo gap over ELO_PER_POINT is a Sagarin rating gap
and adding the same HFA reproduces it to the floating-point bit. The correlation
opens at exactly **1.0**, and the site shows a **seed disclosure** saying so until
it falls below 0.90. Once retired, it stays retired: a disclosure that vanishes
without trace is worse than one that never appeared.

### Predicting

```
predicted_margin = (elo_home − elo_away) / 20 + hfa
win_probability  = 1 / (1 + 10^(−(margin × 20) / 400))
```

- **`ELO_PER_POINT = 20`, `K = 20`.** Conventional, not fitted. The calibration
  curve is the evidence for whether they are wrong. 20 rather than the NFL's
  conventional 25 because college margins scatter more widely, and wider scatter
  means *less* certainty per point — the constant was 28 on reasoning that had
  that backwards. Only the ratio to the 400 divisor is meaningful.
- **Home-field advantage is read from the snapshot, never hardcoded** — from the
  newest Sagarin capture taken *strictly before* kickoff. That is a rule about
  the data rather than about when the job ran, so it replays identically forever.
- Probability is derived *from* the margin rather than computed alongside it, so
  the two cannot disagree.
- Storage keeps the unclamped probability; the `[0.001, 0.999]` clamp is applied
  at publish. Grading a model on what the page displayed would be circular.

### The divisions problem

CFBD's `/games` returns **every division** — week 1 of 2026 is 455 games, of
which 110 are D-III and 109 are D-II. Only 171 have both teams in the crosswalk,
because Sagarin rates 266 teams and no more.

`RawGame.is_modelled` selects the model's universe:

- either side classified below FCS → **out**
- one side classified and the other not → **out** (an NCAA team's unclassified
  opponent is an NAIA school)
- neither classified → **in**, so the crosswalk stays the authority and an
  unmapped name still raises rather than becoming a silent drop

**It loses no FBS game** — week 1, 99 of 99; week 2, 86 of 86. This is a scope
decision, not a gap.

---

## The scoring system

Results join predictions on **`cfbd_game_id`**, the one vendor identifier used as
a key. `(season, week, home, away)` fails when a game moves for weather and at
neutral sites where the two sources disagree about who is home — both of which
happen every season and neither of which announces itself.

Three join failures are **errors**:

| | |
|---|---|
| A result with no prediction | The slate changed, or the run missed a game |
| A prediction with no result | Only if the game was **played** — decided against when the results were captured, since `/games` has no `completed` flag |
| Ids match, teams do not | The one with no symptom. Its worst form is a home/away swap: a complete, plausible scored game with every sign inverted |

Per game: `actual_margin`, `error`, `abs_error`, the Brier contribution, and
whether the pick beat the line. Per week and per season, for **Texas** and the
**full slate** separately: MAE (with the market's and Sagarin's own MAEs, each
over its own denominator), Brier score, a calibration curve, and an ATS record.

The ATS record carries five counters that must sum to the slate:

```
wins + losses + pushes + excluded_no_line + excluded_no_edge == games
```

A game with no line is **excluded and counted**, never scored as a push — zero is
a pick'em, absent is not a line at all. A model margin exactly equal to the
market's is excluded too, in its own counter: a push is a position that tied,
this is the absence of a position.

### Which prediction gets graded

**Not the newest.** A week can hold several generations, and one of them can have
been written on Sunday. `cfb score` takes the newest generation written *strictly
before its own slate's first kickoff*, and refuses the week if none qualifies.
`cfb publish` does the opposite — newest, full stop — because a regenerate exists
precisely so the newer number reaches the site. Both are right.

### Backtesting

`cfb backtest` scores a week the model was not live for. It is **not a
prediction**, and three structural things keep it from pretending to be one: it
never writes to `predictions/`, it writes to `backtest/` which the season-to-date
reader does not read, and the site renders it in a block labelled *not a
prediction*.

---

## Automations

Five GitHub Actions workflows. **Every step is a command a human runs locally** —
no inline Python, no workflow-only branches, no date arithmetic in YAML — so a
red run is reproducible with one copy-paste.

| When (UTC) | Workflow | Does |
|---|---|---|
| Sun 12:00 | `cfb-cfbd` | Pull the completed week's games and lines |
| Sun 12:30 | `cfb-score` | Update Elo, score last week, write `scored/`, then verify the state replays |
| Tue 12:00 | `cfb-sagarin` | Snapshot the ratings page, check it is still moving |
| Thu 12:00 | `cfb-predict` | Generate and write `predictions/` for the coming slate |
| Fri 12:00 | `cfb-publish` | Build `/cfb/data/*`, upload, invalidate, confirm the site serves it |

Plus `cfb-ci` on every PR touching `cfb/` — deliberately with **no AWS
credentials at all**, so a test that reached for the network fails there rather
than passing on someone's laptop.

**The Friday publish is the SLO** and its deadline is first kickoff Saturday. It
is the only job that can genuinely be missed, which is what makes the alerting
mean something. There is no retry-until-it-works loop: a prediction published
after kickoff is not a prediction.

Everything gates on the committed calendar. Out of season, and on the season's
first two Sundays when no week has completed, jobs exit 0 with a reason — turning
those red would train a reader to ignore the one that matters.

Authentication is GitHub OIDC into `arn:aws:iam::679878703800:role/cfb-data-publisher`.
No long-lived keys, and no CFBD key in a GitHub secret — it is read from SSM at
run time.

---

## Running it locally

```bash
uv sync --extra s3          # NOT a bare `uv sync` -- it prunes boto3
uv run pytest               # 931 tests, no network
uv run ruff check --fix .
export AWS_PROFILE=tp-site  # every shell; it does not persist
```

```bash
uv run cfb fetch sagarin
uv run cfb fetch cfbd --resource games          # --week defaults from the calendar
uv run cfb elo seed --season 2026               # once, preseason only
uv run cfb predict --season 2026 --week 4       # defaults to the coming week
uv run cfb score   --season 2026 --week 3       # defaults to the completed week
uv run cfb publish --season 2026
uv run cfb note    --season 2026 --week 3       # the scaffold you write over
uv run cfb elo replay --season 2026             # SPEC §11 step 5
```

Every command takes `--store`, defaulting to `s3://travispollard-cfb-data`. Point
it at `file://./scratch` to work offline against a copy.

---

## Maintenance

**The weekly rhythm is nothing.** All five jobs are scheduled; the only human step
by design is turning `cfb note`'s scaffold into prose and committing it as MDX.

**When a run goes red**, the exception class name is on the line and it says which
of a dozen documented failures happened. Re-run the same command locally with the
same arguments — that is the whole point of the thin-shell CLI.

| Symptom | Likely cause |
|---|---|
| `UnmappedTeamError` | A vendor renamed a team. Add it to `data/crosswalk/teams-YYYY.yaml`, then `uv run pytest tests/test_crosswalk.py` |
| `UnscoredGameError` | A join failed, or a game was in progress when the results were captured. Re-fetch and re-run |
| `StateMismatchError` | The stored Elo state no longer replays from `raw/`. **Regenerate forward from the latest state, never backward into an earlier week** |
| `ReplayError: no Sagarin snapshot ... before` | The week opened before a capture existed. Correct, not a bug |
| `MissingDependencyError` | A bare `uv sync` pruned boto3. `uv sync --extra s3` |
| `ParameterNotFound` on an SSM read from Git Bash | MSYS rewrote the `/`-prefixed parameter name. `export MSYS_NO_PATHCONV=1` |

**Annually**, before the season: bootstrap the next year's crosswalk
(`cfb crosswalk bootstrap --season YYYY`) — ids are inherited by `cfbd_id`, so a
vendor rename does not split a team's history — capture the preseason Sagarin
page, and seed. CFBD's free tier is 1,000 calls/month; this pipeline uses fewer
than 30.

**Never**: edit anything under `raw/`, delete a prediction, or hand-edit a
published document. The bucket is versioned and the role cannot delete, so the
worst case is recoverable, but the discipline is the product.

---

## Future enhancements

**Model**
- **Historical backfill (Phase 2).** The single highest-value change. It is what
  turns `K`, `ELO_PER_POINT` and the invented `MOV_DENOMINATOR_FLOOR = 0.25` from
  conventional numbers into fitted ones, and it retires the seed entirely.
- **A replacement-level opponent.** An FCS team's games against D-II and NAIA
  schools currently do not update its Elo, so FCS ratings carry slightly less
  information into FBS-vs-FCS predictions. One synthetic rating absorbs them —
  cheaper than rating seven hundred schools nobody wants predictions for.
- **Preseason regression toward the mean**, and a decay on early-season K.
- **Beyond Elo:** SP+-style efficiency inputs, or an ensemble. Explicitly out of
  scope for v1, and only worth doing once the backfill can measure whether it
  helped.

**Product**
- **The weekly note.** The scaffold generator exists; the MDX plumbing and
  `/cfb/notes/[slug]` do not, because there is nothing to render until a week has
  been scored.
- **Per-team pages**, using the slate document that already exists.
- **A calibration chart** rather than a table, once there are enough weeks to
  make a shape.
- **Conference and playoff projections** — the natural use of a full slate of
  win probabilities.

**Engineering**
- **An in-season Sagarin capture** is still an open Phase 0 carry-over: two date
  formats and one page-state branch are unexercised until the page drops
  `STARTING`.
- **`/games` in-progress detection.** §5.2 cannot distinguish a failed join from
  a game being played right now, which is why a mid-week backtest fails. An
  explicit completion signal would settle it.
- **Playwright coverage for `/cfb`.** The existing suite hits production, so
  route specs need a strategy that does not depend on a deploy having landed.
- **ESLint is unconfigured**, so the frontend has no lint gate; `next build`'s
  type check is the only static analysis the routes get.
- **A cancellation signal.** A game cancelled after prediction and never played is
  "not an error while unplayed" forever.

---

## Documents

- **`docs/PRD.md`** — what this is for, and for whom
- **`docs/SPEC-phase0.md`** — collection, storage, the crosswalk
- **`docs/SPEC-phase1.md`** — the model, the prediction log, scoring, the JSON contract
- **`docs/PHASE-0.md`, `docs/PHASE-1.md`** — progress against those specs, and every
  decision made along the way that the specs do not
- **`CLAUDE.md`** — the hard rules, in the form an agent reads them

The phase documents are the interesting ones. They record what was found by
running the thing — the sign convention that was backwards, the division nobody
expected, the week that could not honestly be predicted — which is most of what
this project actually learned.

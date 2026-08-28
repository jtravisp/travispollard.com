CFB Forecast — v1 product requirements

Status: draft Owner: Travis Pollard Lives at: travispollard.com/cfb Repo: travispollard.com (monorepo)

Summary

A weekly college football forecasting system. It predicts every FBS game, features Texas, scores itself publicly against the closing betting line, and publishes a short note after each Saturday.

The visible product is three pages. The actual deliverable is the pipeline behind them and the operational story it supports.

Why this exists

Two audiences, in priority order.

A hiring reviewer. They will read the architecture, the pipeline config, and the write-up. The football content is the excuse; the infrastructure is the artifact. Specifically it should demonstrate: scheduled ingest against a rate-limited API, a fragile scrape handled defensively, schema validation and contract testing, a publish deadline that functions as a real SLO, and an honest public accuracy record.

Someone who follows Texas football. They want to know what's likely to happen Saturday. If the page is useful to them it will be shared, and a project people actually visit reads differently from a dead repo.

Scope
The three surfaces

All three are Next.js routes under frontend/app/cfb/, sharing the existing layout, header, and theme toggle.

Route	File	Purpose
/cfb	app/cfb/page.tsx	Next Texas game. Prediction, probability, line. One screen.
/cfb/accuracy	app/cfb/accuracy/page.tsx	Full track record, Texas and full-slate.
/cfb/notes/[slug]	app/cfb/notes/[slug]/page.tsx	Weekly post-game note.

Pages fetch JSON from /cfb/data/* at runtime. They contain no prediction logic and no hardcoded results.

Predict everything, feature Texas

The model runs across all FBS games every week and stores all of it. Texas-only would give roughly twelve data points a season, which cannot support any claim about calibration or accuracy. The full slate gives ~800 games and real error bars, at no additional ingest cost.

The /cfb page shows Texas. The /cfb/accuracy page reports both figures side by side — the Texas record, which is the story, and the full-slate record, which is the actual statistical claim.

What the prediction says

Three numbers, always together:

Field	Example	Source
Predicted margin	Texas -9.5	Model
Win probability	Texas 78%	Model
Closing line	Texas -7.5	CFBD betting lines

Margin and probability derive from the same Elo output, so they can never disagree. The line is shown as a benchmark, not a target. Framing throughout is forecasting and calibration, never picks.

The model

Elo, computed from CFBD game results. Roughly fifty lines, well documented, genuinely yours, and a legitimate baseline. Margin comes from the rating difference plus home-field advantage; win probability from the standard Elo logistic.

Benchmarks scored against, not used as inputs in v1: the closing line, and Sagarin PREDICTOR.

Anything more sophisticated added later must beat this baseline to justify existing. That is the point of starting here.

Data sources

CollegeFootballData. Structured backbone — games, scores, betting lines, advanced metrics. Free tier is 1,000 calls/month, which forces incremental sync and rate-limit-aware backoff. This constraint is a feature.

Sagarin. Weekly scrape, benchmark competitor. Raw HTML snapshotted to S3 on every pull, date-partitioned, immutable. Parser is contract-tested in CI against a golden fixture. Freshness check pages if the page's internal date stamp has not advanced by Tuesday. See .claude/skills/sagarin-format/ for the format traps.

Team-name crosswalk. A versioned artifact with tests, not a dict at the bottom of a script. An unmapped team fails loudly. A silent drop means a game vanishes from the training set and the accuracy numbers become fiction.

Publishing integrity

The accuracy record only means anything if a reviewer can verify it was not edited after the fact.

The prediction log is append-only.
Every week's predictions are committed to git before kickoff, timestamped.
History is never rewritten.
The methodology page says all of this plainly and links to the log.

Git is the tamper-evident record. No extra infrastructure required.

The weekly note

Written commitment is the most likely thing to fail. Weekly blogs die around week five.

The pipeline generates the boring 80% automatically: predicted margin, actual result, error, the line, whether the model beat it, season-to-date figures, and the model's biggest national miss that week. Travis adds three paragraphs of commentary.

Target: fifteen minutes, not an hour. Called notes rather than a blog, so a skipped week reads as a gap rather than abandonment.

Non-goals for v1

Written down because these will all feel urgent around week three.

Live in-game win probability
Player-level data of any kind
Injury data
Per-team pages for all 134 FBS teams
User accounts
A live API or any always-on backend
Server-side rendering of prediction data
Any model beyond the Elo baseline
Betting recommendations, parlays, or anything resembling handicapping
Kubernetes

Kubernetes is on this list deliberately. v1 runs on scheduled GitHub Actions. The cluster is a phase-three migration with its own write-up about why the workload moved, which is a better story than having started there.

Architecture

Pages are built. Data is generated. They deploy independently.

The Next.js site static-exports to out/ and syncs to the existing site bucket, exactly as it does today. The /cfb routes ship with it. Nothing about the site build changes except that there are more routes.

The pipeline writes JSON only, to a separate bucket, on a schedule. It never touches the site bucket, never triggers a site build, and cannot deploy anything.

CloudFront routes /cfb/data/* to the data bucket and everything else to the site bucket. That path pattern maps to a real boundary — generated data versus built site — rather than an arbitrary URL prefix.

Consequences worth noting:

No CloudFront Function needed. Next's static export already emits cfb/index.html and cfb/accuracy/index.html, and the default behavior serves them.
No layout duplication. The football pages inherit the site's header, theme, and Tailwind config.
next-sitemap picks up the routes for free.
Prediction data is client-fetched, so it is not in the initial HTML. Acceptable for v1. If it matters later, pre-render from a committed snapshot and hydrate to live data.

The two Terraform roots communicate one-way through SSM parameters. Neither reads the other's remote state.

Repo layout
travispollard.com/
├── CLAUDE.md                       # repo-wide, short
├── .claude/
│   ├── skills/sagarin-format/      # scrape format knowledge
│   └── settings.json               # hooks
├── frontend/
│   └── app/cfb/                    # the three routes
├── modules/cloudfront/             # parameterized for extra origins
├── main.tf, variables.tf, ...      # site Terraform root (existing state)
├── cfb/
│   ├── CLAUDE.md                   # pipeline-scoped instructions
│   ├── docs/                       # PRD, phase plans, decisions
│   ├── src/                        # ingest, model, generation
│   ├── tests/fixtures/             # golden fixtures
│   ├── data/                       # append-only prediction log, Elo state
│   ├── terraform/                  # cfb Terraform root (separate state)
│   └── scripts/publish-data.sh
└── .github/workflows/cfb-*.yml     # scheduled pipeline

www/ is legacy and should be deleted or archived before work starts. Two plausible site roots in one repo will send Claude Code exploring the wrong half.

Why GitHub Actions and not CodeBuild

The site stays on CodeBuild. The pipeline runs on scheduled GitHub Actions because cron on Actions is trivially simple, free at this volume, and the OIDC role is already written. It also means the two deploy paths are genuinely different systems, which is additional isolation for free.

Weekly rhythm
When	What
Sunday	Ingest final scores, update Elo, score last week's predictions
Tuesday	Sagarin snapshot, freshness check, alert if stale
Thursday	Generate predictions for the coming slate, commit to the log
Friday	Publish JSON. Deadline is first kickoff Saturday.
Saturday	Games
Sunday	Note published with generated scaffold

The Friday publish deadline is the SLO. It can genuinely be missed, which is what makes freshness alerting and pipeline monitoring mean something rather than being decoration.

Definition of done for v1

One Saturday where:

Predictions published before first kickoff, with no manual intervention.
Results recorded automatically afterward.
The accuracy page reflects them without a site deploy.

That is the whole bar. Not the cluster, not the architecture diagram, not the historical backfill.

Success metrics

Operational. Publish deadline met, weeks in a row. Pipeline failures caught by alerting rather than by noticing a stale page.

Model. Mean absolute error against actual margin, versus the same figure for the closing line. Brier score and a calibration curve on win probability. Record against the spread, reported with the sample size attached.

Beating the closing line is not the goal and probably will not happen — the market is efficient. Landing within a couple of points with well-calibrated probabilities, and saying so plainly, is the stronger result and the more credible page.

Portfolio. The write-up lives at /projects/cfb-forecast with the architecture diagram, the decisions, the cost breakdown, and what broke. Assume the reviewer reads exactly one page and never clicks through to GitHub.

Phases

Phase 0 — collector. Scheduled fetch of both sources, S3 raw snapshots, parser with golden-fixture tests, crosswalk, freshness alerting. No modeling, no pages. Time-sensitive: Sagarin's page shows current ratings only, so every uncollected week is a permanent hole.

Phase 1 — v1. Elo, JSON generation, the three routes, the publish workflow, the append-only log. Ship in-season.

Phase 2 — depth. Backfill history, add rating systems, the bake-off comparison, better models measured against the baseline.

Phase 3 — platform. Migrate the pipeline to Kubernetes: CronJobs for weekly ingest, Jobs for backfills, resource limits, monitoring on whether the publish actually happened. Cluster does batch, CDN does serving.

Risks

Scope creep. The dominant risk. Mitigated by the non-goals list above, which is binding.

Weekly writing fatigue. Mitigated by generating the scaffold.

Sagarin format change or site disappearing. Mitigated by raw snapshots, contract tests, and the fact that CFBD alone is sufficient for v1. Sagarin is a benchmark, not a dependency.

Late start. The 2026 season is underway. A crude v1 shipped now accumulates a full live season of public predictions. A polished v1 started in January has no track record at all.

Open questions
Elo state between runs: committed to the repo as a versioned artifact, or written to S3? Leaning repo — it is small, it is auditable, and it makes ratings history part of the same tamper-evident record as the predictions.
Home-field advantage: fit it from data, or take Sagarin's published per-snapshot value as a starting constant?
Does the accuracy page need to paginate, or does one season fit comfortably on one screen? Defer until there are ten weeks of data.

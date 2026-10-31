# Observability — v1 product requirements

Status: draft · Owner: Travis Pollard · Started: 2026-10-29 · Repo: travispollard.com (monorepo), `observability/`

## Summary

Monitor every site already on `/status` with the industry-standard open stack: Grafana Alloy
running a blackbox exporter, Prometheus-format metrics in Grafana Cloud, SLOs written by hand
as PromQL recording rules, multi-window burn-rate alerts, and later OpenTelemetry traces and
metrics from Near Mint Radar. All of it is defined as code in this repo.

The goal is **learning**: being able to explain and defend Prometheus, PromQL, Alloy, OTel,
and SLO/error-budget alerting from first-hand work. Uptime visibility is a side effect. The
existing status checker already covers it.

## Why this exists

- Job postings ask for Prometheus, Grafana, OpenTelemetry, and SLOs. The current status page
  is a custom Lambda, which is good engineering but isn't a recognisable tool.
- The status checker answers "is it up?" It does not keep time series, has no query language,
  and cannot express "how fast are we spending our error budget?" Those are the parts worth
  learning.
- It doubles as a portfolio piece: a public dashboard linked from `/status`, plus a short
  architecture write-up.

## Goals

1. Probe the six `/status` targets with blackbox_exporter (via Alloy) every 60 s, covering
   HTTP status, latency per phase, and TLS expiry.
2. Store and query the results as Prometheus metrics in Grafana Cloud.
3. Define availability and latency SLOs, then build the recording rules, error-budget
   dashboard, and burn-rate alerts by hand.
4. Keep everything in code: Terraform (Grafana provider), Alloy config, rule YAML, and
   dashboard JSON. Nothing that matters lives only in the Grafana UI.
5. Instrument Near Mint Radar with OpenTelemetry, with traces in Tempo and custom metrics
   in Mimir.
6. Publish a public dashboard and link it from `/status`.

## Non-goals

- **Replacing the status checker.** It stays the public page's data source and the primary
  alert path until the new alerts have proven themselves (D-006).
- **Self-hosting Prometheus storage or Grafana in the cloud.** Grafana Cloud's free tier
  hosts both, which keeps hosting cost at zero.
- **Forcing Prometheus onto Lambda.** Serverless workloads push via OTel and are never
  scraped.
- **Logs.** Not in v1. Loki is a possible later addition.
- **High availability for the probe host.** One probe location is acceptable. Its blind
  spots are documented and not engineered away.

## Constraints

| Constraint | Value | Consequence |
|---|---|---|
| Budget | **≤ $3/month** total new spend | No t4g.nano with public IPv4 (~$7–8/mo). Spot + IPv6-only, or local. |
| Grafana Cloud free tier | 10k active series, 14-day retention for metrics, logs and traces; 50 GB/mo each for logs and traces; Application Observability 2,232 host-hours/mo (verified from pricing page 2026-10-29) | 7-day SLO window, not 30 (D-004). Watch series count. Check how Phase 3's Lambdas count against App Observability host-hours. |
| Scrape interval | 60 s | 1 data point/min/series. Shorter intervals multiply usage for no learning gain. |
| AWS | Account `679878703800`, profile `tp-site`, `us-east-1` | Same conventions as the root stack. |
| Terraform state | Separate from root (D-002) | Any seam to the root stack is SSM, as with `cfb/`. |

## Architecture

### Target state (end of Phase 2)

```
  ┌──────────────── probe host ────────────────┐
  │  Phase 1a: Docker on dev machine           │
  │  Phase 1b: t4g.nano spot, IPv6-only subnet │
  │                                            │       HTTPS probes
  │  Grafana Alloy                             │ ───────────────────────►  6 /status targets
  │   ├─ prometheus.exporter.blackbox          │                          (CloudFront, Amplify, …)
  │   ├─ prometheus.scrape (60 s)              │
  │   └─ prometheus.remote_write ──────────────┼──┐
  └────────────────────────────────────────────┘  │
                                                  ▼
  ┌──────────────── Grafana Cloud (free) ─────────────────────────────┐
  │  Mimir (Prometheus storage)                                       │
  │   └─ ruler: recording rules (SLIs) + alert rules (burn rate)      │
  │  Grafana: dashboards (JSON in repo), alerting, contact points     │
  │  Tempo (Phase 3)                                                  │
  └──────────────┬────────────────────────────────────────────────────┘
                 │ email (Discord later)
                 ▼
               Travis

  Unchanged, in parallel:
  status-checker Lambda (10 min) ──► status.json ──► /status page
                                └──► SNS email alerts
```

### Phase 3 addition

```
  Near Mint Radar (separate repo)
   FastAPI Lambda + poller ── OTel SDK ── OTLP/HTTP ──► Grafana Cloud OTLP gateway
                                                         ├─ Tempo  (traces)
                                                         └─ Mimir  (custom metrics)
```

The instrumentation code lives in the Near Mint Radar repo. Its dashboards, alerts, and SLOs
live here, so this repo stays the single place where the observability layer is defined.

### Repo layout (proposed, firmed up in Phase 0)

```
observability/
  docs/
    PRD.md            this file
    PHASE-0.md …      per-phase progress, same pattern as cfb/docs
  terraform/          own state; Grafana provider (+ AWS for Phase 1b host)
    dashboards/*.json
  alloy/
    config.alloy
    docker-compose.yml   Phase 1a
  rules/
    slo-recording.yaml   Prometheus rule format, loaded into the Mimir ruler
    slo-alerts.yaml
```

## Phases

Each phase has a progress file in `docs/` once it starts. A phase is done when its exit
criteria have been **observed live**, not just written (the same `[~]` vs `[x]` rule as `cfb/`).

### Phase 0: Grafana Cloud as code · $0

- Create a Grafana Cloud free stack (by hand, once, recorded here).
- Add an `observability/terraform` root with the S3 backend (same bucket, its own key) and the
  Grafana provider. The token goes in SSM SecureString.
- Manage with Terraform: a folder, an email contact point, a notification policy, and one
  placeholder dashboard from JSON.

**Exit:** `terraform plan` is clean. The dashboard is visible in Grafana. A test notification
arrives by email.
**Learn:** Grafana Terraform provider, dashboards as code, Grafana Cloud stack anatomy.

### Phase 1a: Alloy + blackbox, local Docker · $0

- `docker compose up` runs Alloy with blackbox modules for HTTP 2xx (following redirects) and
  TLS expiry, probing the six targets every 60 s and writing remotely to Grafana Cloud.
- Drop or filter Alloy's self-metrics so they don't spend the series budget.
- A probe dashboard covering up/down, latency by phase, status code, and days to cert expiry.

**Exit:** all six targets graphed for 24 h. The series count is recorded in PHASE-1.md.
**Learn:** Alloy components, blackbox modules, `probe_*` metrics, relabeling, remote_write.

### Phase 1b: move the probe host to AWS · target ~$1.50/mo

- t4g.nano spot in an ASG of 1, in a small VPC with an IPv6-only subnet and an egress-only
  internet gateway (no NAT, no public IPv4). Alloy is installed by cloud-init from the same
  `config.alloy`.
- **Gate:** before building, confirm every target and the Grafana Cloud remote_write endpoint
  resolve and answer over IPv6 (R-1). Any that don't change the plan (see D-005).

**Exit:** the host has run 7 days, including at least one spot replacement or a forced
instance refresh, with no lasting data gap. The cost is confirmed in Cost Explorer.
**Learn:** IPv6-only networking, spot + ASG self-healing, config-as-code deployment.

### Phase 2: SLOs, error budgets, burn-rate alerts · $0

- SLIs, per target:
  - Availability: `probe_success` ratio.
  - Latency: share of successful probes with `probe_duration_seconds < 0.8`.
- SLOs on a **7-day rolling window**: availability 99.5% (≈50 min of budget a week) and
  latency 95%. Final numbers are set from Phase 1 data, not guessed.
- Recording rules at 5m / 30m / 1h / 6h / 1d / 7d in Prometheus rule YAML.
- Multi-window, multi-burn-rate alerts. The SRE-workbook multipliers (14.4×, 6×) assume a
  30-day window, so **recompute them for 7 days** from the "% of budget spent" each alert
  should represent. Document the derivation.
- Error-budget dashboard: budget remaining, burn rate, and SLI over time.

**Exit:** a deliberately broken target (a test URL, or a probe pointed at a 500) fires the
fast-burn alert within its expected time and resolves afterwards. The derivation is written
up in PHASE-2.md.
**Learn:** PromQL over ratios, recording rules, the Mimir ruler, burn-rate math, alert design.

### Phase 3: OpenTelemetry on Near Mint Radar · ≈$0

- OTel Python SDK in the FastAPI Lambda and the poller, using OTLP/HTTP directly to Grafana
  Cloud with an explicit `force_flush()` before each handler returns (D-007, still open).
- Traces for request handling and the outbound Mana Pool / SES calls.
- Custom metrics: cards polled, price alerts fired, SES send failures, Mana Pool fetch latency.
- An app dashboard and at least one SLO over real request data, rather than probes.

**Exit:** one end-to-end trace of a poll cycle is visible in Tempo. Custom metrics are graphed.
The cold-start and duration impact is measured and recorded.
**Learn:** OTel SDK, semantic conventions, context propagation, telemetry on Lambda.

### Phase 4: public face · $0

- A public (shared) Grafana dashboard linked from `/status`.
- An architecture write-up on the site, including the "why not just CloudWatch?" answer.
- Optional: a CloudWatch data source in Grafana to show both side by side.

### Side track: kube-prometheus-stack on kind · $0, any time after Phase 2

Run self-hosted Prometheus, Alertmanager, ServiceMonitors, and PrometheusRules locally,
reusing `rules/*.yaml` unchanged. This is how most job postings run Prometheus. It isn't public
and it doesn't gate anything.

## Decisions

| ID | Date | Decision | Why | Status |
|---|---|---|---|---|
| D-001 | 2026-10-29 | Use Grafana Cloud free tier for storage and UI rather than self-hosting | $0, and the skill is the config and queries, not running Mimir | Accepted |
| D-002 | 2026-10-29 | Put it in this repo under `observability/`, with its own Terraform state | Same pattern as `cfb/`. Keeps the root site stack's plans small and its blast radius separate | Accepted |
| D-003 | 2026-10-29 | Run Alloy in local Docker first (1a), then move to an AWS spot box (1b) | Learning starts at $0 today. The host decision waits on the IPv6 check | Accepted |
| D-004 | 2026-10-29 | 7-day SLO window | Free-tier retention is 14 days, so a 30-day window can't be computed | Accepted |
| D-005 | — | Fallback if IPv6-only fails: public IPv4 (~$4.50/mo, over budget), Lightsail, or stay local | Depends on R-1 | Open |
| D-006 | 2026-10-29 | The status checker stays the public source and primary alert path | Proven, and the new alerts need a burn-in period first | Accepted |
| D-007 | — | OTel on Lambda: plain SDK + `force_flush` vs the ADOT layer | SDK is lighter and teaches more. ADOT is simpler. Measure both on cold start | Open |
| D-008 | — | Rule management: `mimirtool` vs Terraform vs Grafana-managed rules | Prometheus rule YAML is the portable artifact. Pick whichever tool can load it from code | Open |
| D-009 | — | Target list: duplicate the six targets or share them with `status-checker.tf` | Two lists will drift. Sharing needs an SSM seam or a common file | Open |

## Risks

| ID | Risk | Mitigation |
|---|---|---|
| R-1 | Some targets (Amplify-hosted especially) or the Grafana Cloud endpoints may not be reachable over IPv6 | A gate check before Phase 1b. D-005 fallback |
| R-2 | Series count creeps toward 10k (Alloy self-metrics, high-cardinality labels) | Filter at the source. Record the count at every phase exit |
| R-3 | One probe per minute from one location is a small sample. A single blip is a 20% error rate in a 5-minute window | The multi-window design needs both long and short windows to fire. Tune in Phase 2 |
| R-4 | A single probe location can't tell "site down" from "probe host's network down" | Alert on the probe host's own `up`/heartbeat separately. Accepted for v1 |
| R-5 | Duplicate alerts from the status checker and Grafana during burn-in | Route Grafana alerts to a separate label or channel until D-006 is revisited |
| R-6 | Free-tier terms change | Everything is code. Configs are portable to self-hosted Prometheus (see side track) |

## Cost tracking

| Item | Phase | Expected | Actual |
|---|---|---|---|
| Grafana Cloud free | 0+ | $0 | |
| Local Docker | 1a | $0 | |
| t4g.nano spot + ~4–8 GB gp3, IPv6-only | 1b | ~$1.50 | |
| Lambda duration from OTel | 3 | < $0.10 | |

---
name: obs-work
description: Start a work session on the observability stack (Grafana Cloud, Alloy/blackbox, SLOs, OTel) under observability/. Loads the PRD and phase ledger, states the working rules, and defines how the session ends.
disable-model-invocation: true
---

Start a work session on phase $ARGUMENTS of the observability project.

Phases are `0`, `1a`, `1b`, `2`, `3`, `4`, and `kind` (the side track). If
$ARGUMENTS is empty, find the earliest phase whose exit criteria are not yet
met and propose working on it.

## Load first

1. Read `observability/docs/PRD.md` in full. It is short, and the Decisions
   and Risks tables decide what is allowed.
2. Read the phase ledger if it exists: `observability/docs/PHASE-<n>.md`,
   where `1a` and `1b` share `PHASE-1.md`. If it does not exist, this is the
   phase's first session: create it from the PRD's phase section, with each
   bullet and exit criterion as a `[ ]` item.
3. Read the earlier phases' ledgers only for carry-overs that gate this one.
4. Work that touches the probe targets also needs `status-checker.tf`, which
   holds the other copy of the target list (D-009).

## Working rules

**Decisions**
- A decision marked Accepted in the PRD is settled. Do not reopen it in
  passing. If the work shows that one is wrong, stop and say so.
- If the work needs an Open decision (D-005, D-007, D-008, D-009, or any
  later one), present the options with a recommendation and wait. Do not
  pick one by building it.
- New choices that a later session would need to know about get a new D-row.
  Choices that only matter to this session do not.

**Scope**
- Work only on phase $ARGUMENTS. If something is broken elsewhere, record
  it in the right ledger rather than fixing it here.
- Phase 1b does not start until the IPv6 gate (R-1) has passed and that
  result is recorded in PHASE-1.md.
- Logs, self-hosted Prometheus or Grafana in AWS, and replacing the status
  checker are non-goals. Raise them; do not build them.

**Everything as code**
- Every Grafana object that matters (folders, dashboards, contact points,
  policies, rules) is in Terraform, rule YAML, or dashboard JSON under
  `observability/`. If something had to be done in the UI (the stack
  itself, a token), record it in the ledger as a manual step, with the date.
- Dashboard JSON exported from the UI is cleaned before commit: strip `id`
  and `version`, and pin the datasource by uid or variable.
- Rules are written in Prometheus rule-file format, so the kind side track
  can load them unchanged.

**State and secrets**
- `observability/terraform` has its own state: the `travispollard.com-tf-state`
  bucket (us-west-2) under its own key. It never reads root or `cfb/` state.
  If it needs something from them, the seam is an SSM parameter.
- Grafana Cloud tokens and remote_write credentials live in SSM SecureString
  or a gitignored `.env`. Never in a tracked file, a tfvars file, or command
  output pasted back into the conversation.
- AWS work uses profile `tp-site`, account `679878703800`. Confirm it with
  `aws sts get-caller-identity --profile tp-site --query Account --output text`
  before trusting an empty result.
- On Git Bash, MSYS rewrites any argument that starts with `/` (for example
  SSM names like `/projects/...`). Use `MSYS_NO_PATHCONV=1` or PowerShell.

**Budget**
- Total new spend is capped at $3/month. Before adding any billable AWS
  resource, state its monthly cost. Public IPv4 addresses ($3.65/mo each)
  and NAT gateways are effectively banned.
- The free tier is 10k active series with 14-day retention. Anything that
  adds series (new targets, labels, Alloy components) gets an estimated
  series count before it is added.
- The scrape and probe interval stays at 60 s unless a D-row changes it.

**Done means observed**
- Mark an item `[x]` only when this session has seen it working live: the
  plan or apply output, a query result, a dashboard rendering, an alert
  arriving. Written but not seen live is `[~]`.
- Do not touch the status checker (`status-checker.tf`,
  `status-checker/`) during this project's sessions, except to share the
  target list under a decision on D-009.

## Before starting

State in two or three sentences:
- what in this phase is done, what is blocked, and on what;
- which Open decisions this session will run into;
- what you plan to do first.

Wait for confirmation.

## Ending the session

When the work is done, or when I say to wrap up:

1. Show the evidence: `terraform plan` (no changes), `terraform validate`,
   `alloy fmt` or a config check, `promtool check rules`, or a query
   result, depending on what changed.
2. Update the phase ledger: mark verified items, add sub-items for anything
   discovered, note new blockers and manual steps, and record the active
   series count whenever it was checked.
3. Update `observability/docs/PRD.md` only for:
   - new or resolved decisions (D-rows: set the status and date, and keep
     the reasoning);
   - new or retired risks;
   - the Actual column in Cost tracking.
   Do not rewrite the phase plans to match what was built. Record any
   deviation as a decision.
4. Summarize in three lines: what changed, what was verified live, and what
   the next session should start with.

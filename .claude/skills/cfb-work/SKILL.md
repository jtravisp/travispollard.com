---
name: cfb-work
description: Start a work session on the CFB forecast pipeline. Loads the phase ledger and spec, states the working rules, and defines how the session ends.
disable-model-invocation: true
---

Start a work session on section $ARGUMENTS of the CFB forecast pipeline.

## Load first

1. Read `cfb/docs/PHASE-0.md` and find section $ARGUMENTS.
2. Read the matching section of `cfb/docs/SPEC-phase0.md`.
3. If the work touches Sagarin fetching, parsing, or team names, use the
   `sagarin-format` skill.
4. Read `cfb/CLAUDE.md` if not already loaded.

Do not read `cfb/docs/PRD.md` unless the task requires a product decision.
It is context we mostly do not need.

## Working rules

- Never modify a file under `cfb/tests/` during an implementation session.
  If a test looks wrong, stop and say so.
- Never mark a PHASE-0 item done without a passing test or command output
  shown in this session.
- Validation failures raise. Never return None, log-and-continue, or coerce.
- Raw snapshots are immutable. Never overwrite or delete anything under
  `raw/`.
- Work only on section $ARGUMENTS. If you find something broken elsewhere,
  note it in PHASE-0 rather than fixing it here.

## Before starting

State in one or two sentences: what is already done in this section, what
is blocked, and what you intend to do first. Wait for confirmation.

## Ending the session

When the work is done or I say to wrap up:

1. Run the tests and show output.
2. Update `cfb/docs/PHASE-0.md` — mark verified items done, add sub-items
   for anything discovered, note new blockers.
3. Summarize in three lines what changed and what the next session should
   pick up.
   
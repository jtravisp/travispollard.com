# CFB forecast pipeline

Python data pipeline that ingests college football data, computes Elo ratings, and writes JSON to S3. It does not build or deploy the website. The Next.js routes under `../frontend/app/cfb/` read the JSON it produces.

## Commands

```bash
uv sync                          # install
uv run pytest                    # all tests
uv run pytest tests/test_sagarin_parser.py   # parser only
uv run ruff check --fix .        # lint
terraform -chdir=terraform plan  # infra
```

## Hard rules

**IMPORTANT: Raw source data is immutable.** Every fetch writes the unmodified bytes to S3, date-partitioned, before anything parses them. Never parse-and-discard.

**Validation failures raise. They never return None, log-and-continue, or coerce.** A dropped row means a game silently vanishes from the training set and the published accuracy numbers become false. This is the one failure mode the whole project is designed to prevent.

**An unmapped team name is an error.** The crosswalk in `src/crosswalk/` is a versioned artifact with tests. Do not add fallback matching, fuzzy matching, or a default.

**Never hardcode home-field advantage.** Read it from the source snapshot. See the `sagarin-format` skill.

**The prediction log at `data/predictions/` is append-only.** Never edit or delete a past prediction. The tamper-evident record is the point of the project.

## Boundaries

- This directory never writes to the site bucket.
- Terraform here has its own state, separate from the repo root. Do not reference the root state.
- The CloudFront distribution is owned by the root Terraform. Read its ID from SSM, never hardcode it.

## Conventions

- Ratings are floats but rank is the join key. Sagarin publishes ties in rating that are not ties in rank.
- All timestamps stored UTC, ISO 8601.
- Season and week are always explicit in filenames and schemas. Never infer "current".

## Gotchas

- CFBD free tier is 1,000 calls/month. Sync incrementally, back off on 429, and never call it from a test.
- Sagarin's page 302s HTTPS to HTTP. Pin the scheme or the fetch loops forever.
- Tests use fixtures in `tests/fixtures/`. No network calls in tests, ever.
- 
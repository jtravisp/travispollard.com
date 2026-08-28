# Phase 0 — the collector: implementation spec

Derived from `PRD.md`, `PHASE-0.md`, `../CLAUDE.md`, and `.claude/skills/sagarin-format/SKILL.md`.
Where this spec and those disagree, this spec is the newer decision; where it is silent, they govern.

**Deliverable:** both sources fetched on a schedule, raw snapshots landing in S3 with provenance, the
Sagarin parser passing contract tests, a season-scoped crosswalk resolving every name in either source,
and a freshness check that turns a workflow red when Sagarin stops updating.

**Not a deliverable:** anything anyone can see. No Elo, no JSON for the site, no pages.

---

## 1. Repo layout

Files this phase creates. Everything under `cfb/` except the workflows and the two root-stack lines.

```
cfb/
├── pyproject.toml                  # 3.12, uv, ruff, pytest, console_script "cfb"
├── src/cfb/
│   ├── cli.py                      # the `cfb` entrypoint, subcommands below
│   ├── calendar.py                 # season/week resolution
│   ├── storage.py                  # SnapshotStore protocol + S3/File/Memory impls
│   ├── manifest.py                 # snapshot_key(), manifest_key(); the two-phase build (§4.3)
│   ├── logging.py                  # key=value structured lines to stdout
│   ├── errors.py                   # the exception hierarchy in §9
│   ├── collectors/
│   │   ├── sagarin.py              # fetch_sagarin(): encoding sniff, snapshot, freshness
│   │   └── cfbd.py                 # budgeted client, incremental sync
│   ├── parsers/
│   │   ├── sagarin_ratings.py      # section 1 only
│   │   └── sagarin_predictions.py  # Predictions_with_Totals_and_Moneylines
│   ├── models.py                   # pydantic: TeamRating, SagarinSnapshot, GamePrediction, Manifest
│   └── crosswalk/
│       ├── __init__.py             # load(season) -> Crosswalk; resolve() raises
│       └── bootstrap.py            # one-off candidate generator, NEVER imported by runtime
├── data/
│   ├── calendar/2026.json          # committed, from CFBD /calendar
│   └── crosswalk/teams-2026.yaml   # committed, hand-reviewed
├── tests/
│   ├── fixtures/
│   │   ├── .gitattributes                  # `* -text`; core.autocrlf must not rewrite a byte-exact capture
│   │   ├── sagarin_2026_preseason.txt      # golden page, raw bytes, original encoding   [exists, §4.7]
│   │   ├── sagarin_2026_week04.txt         # in-season golden page
│   │   ├── sagarin_malformed_row.txt       # a deliberately broken row                   [exists, §4.7]
│   │   └── rosters/{sagarin-2026.txt,cfbd-2026.json}
│   ├── test_sagarin_parser.py
│   ├── test_sagarin_predictions.py
│   ├── test_crosswalk.py
│   ├── test_calendar.py
│   ├── test_storage.py
│   └── test_freshness.py
└── terraform/main.tf               # the cfb Terraform root, see §10

.github/workflows/
├── cfb-ci.yml                      # PRs touching cfb/**: ruff + pytest, offline
├── cfb-sagarin.yml                 # Tue 12:00 UTC
└── cfb-cfbd.yml                    # Sun 12:00 UTC
```

`cfb/terraform/main.tf` exists as a draft. It is not yet a Terraform root — it has no backend block and
has never been initialised. §10.1 lists what it needs before the first apply.

---

## 2. Storage contract

Bucket `travispollard-cfb-data`, us-east-1, private, versioned. boto3 clients are constructed with the
region passed explicitly — never inherited from ambient env.

### 2.1 Key layout

```
raw/sagarin/season=2026/week=04/2026-09-16T110302Z.txt
raw/sagarin/season=2026/week=04/2026-09-16T110302Z.meta.json
raw/cfbd/season=2026/week=04/games/2026-09-14T120117Z.json
raw/cfbd/season=2026/week=04/games/2026-09-14T120117Z.meta.json
raw/cfbd/season=2026/week=04/lines/2026-09-14T120118Z.json
raw/cfbd/season=2026/week=season/teams/2026-08-20T120004Z.json
```

- `week=` takes `preseason`, `01`–`15` zero-padded, `postseason`, `offseason`, `unknown` (§3.3), or the
  literal `season` for season-level CFBD resources.
- CFBD keys carry a resource segment (`games/`, `lines/`, `teams/`, `calendar/`). Sagarin has one resource
  and omits the segment.
- The filename is a UTC timestamp to the second, `%Y-%m-%dT%H%M%SZ`. Two runs on one day are two objects.
  Nothing is ever overwritten and nothing is ever deleted under `raw/` — the publisher IAM policy grants
  no `s3:DeleteObject` on that prefix, so this is enforced, not merely intended.
- Snapshots are stored **verbatim**: the exact bytes off the wire, no gzip, no re-encoding, no
  normalization. The `sha256` in the manifest is therefore a hash of what the server sent, and a re-fetch
  can be checked against it.

### 2.2 Manifest

One `.meta.json` per snapshot, written twice (§4.3): once after the bytes land, once after a successful
parse. The second write is a new S3 version of the same key — the only mutable object in `raw/`, and only
ever in the append-a-field direction.

```jsonc
{
  "schema_version": 1,
  "source": "sagarin",                 // "sagarin" | "cfbd"
  "resource": "ratings",               // cfbd: "games" | "lines" | "teams" | "calendar"
  "source_url": "http://sagarin.com/sports/cfsend.htm",
  "http_status": 200,
  "sha256": "9f2c…",
  "bytes": 184320,
  "encoding": "cp1252",                // null for CFBD JSON
  "fetched_at": "2026-09-16T11:03:02Z",
  "season": 2026,
  "week": "04",
  "week_resolution": "calendar",       // "calendar" | "unknown"
  "snapshot_key": "raw/sagarin/season=2026/week=04/2026-09-16T110302Z.txt",

  // added by the post-parse write only
  "parse_ok": true,
  "page_date_stamp": "2026-09-15",     // Sagarin's internal stamp, ISO; null on a preseason page (§4.7)
  "page_state": "in-season",           // from the title line: "preseason" | "in-season"
  "team_count": 266,
  "fbs_count": 138,                    // division A; 138 on the 2026 page, not 134
  "hfa": { "rating": 2.41, "predictor": 2.41, "golden_mean": 2.41,
           "recent": 2.41, "strong_recent": 2.41 },   // all five columns, §4.7
  "predictions_count": 61,
  "unmapped": []
}
```

`hfa` is captured per rating column from the page, per snapshot. It is never a constant anywhere in the
codebase — there is no default value to fall back to. All five columns are carried: the page prints five
bracketed values and `parse_hfa` raises if it finds any other number (§4.7). They read identically today
and Sagarin does not promise they will.

**`http_status` currently records an inference, not an observation.** The fetch seam of §8 hands
`fetch_sagarin` bytes and nothing else, so no status line ever reaches the code that builds the manifest.
What the field asserts is that the fetcher of §4.1 turned every non-2xx into a `FetchError` before
returning, and therefore that `200` is the only thing bytes at this point could have come from. That is
true, and it is not the same claim as "the server said 200" — a manifest is evidence, and a field inferred
from control flow is weaker evidence than one read off the wire. Widening the seam to carry the response
is the fix; until then, do not read this field as a record of what the server sent.

### 2.3 The storage seam

Collectors never construct a boto3 client. They take a store:

```python
class SnapshotStore(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    def put_json(self, key: str, obj: dict) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def list_manifests(self, prefix: str) -> list[Manifest]: ...   # newest first by fetched_at
```

- `S3SnapshotStore(bucket, region)` — production.
- `FileSnapshotStore(root)` — `--store file://./local-snapshots` for local development.
- `MemorySnapshotStore()` — tests.

This is the only reason the test suite can honour `cfb/CLAUDE.md`'s "no network calls in tests, ever" while
still testing the write path.

---

## 3. Season and week resolution

### 3.1 Source

CFBD's `/calendar?year=YYYY` is authoritative, fetched **once per season** and committed to
`cfb/data/calendar/2026.json`. Every run resolves locally from that file. One API call per season.

```python
# calendar.py
def load_calendar(season: int, *, data_dir: Path | None = None) -> Calendar: ...
def resolve(now: datetime, *, calendar: Calendar) -> WeekRef: ...
def in_season(now: datetime, *, calendar: Calendar) -> bool: ...
```

`data_dir` defaults to the packaged `cfb/data/calendar/`; the tests point it at a fixture. `resolve` and
`in_season` take the calendar rather than loading it, so one run loads once and a test can hand them a
truncated or malformed calendar without touching the filesystem.

**`resolve` does not raise.** A date it cannot place returns `WeekRef(season=…, week="unknown",
how="unknown")`. This is stated here rather than left to be inferred from the `"calendar" | "unknown"`
union in §2.2, because the inference runs backwards: the union is the consequence of this decision, not
the evidence for it. `load_calendar` still raises `WeekResolutionError` on a missing, malformed,
empty, or wrong-season file — the file being unreadable is a different fact from a date being
unplaceable. The non-zero exit §3.3 requires is still owed, and the collector owes it, after the write.

The distinction `resolve` draws: a **complete** calendar (one carrying a postseason entry) places a
March date in `offseason`, because it knows where the season ended. A calendar **truncated** at week 10
says nothing at all about December, so December resolves to `unknown`. Answering `offseason` there
would be a guess dressed as an answer, and a snapshot filed under a confidently wrong partition is
never re-partitioned, while one filed under `unknown` is.

**`in_season` opens 21 days before the first calendar entry's start** and closes at the last entry's
`lastGameStart`, inclusive. Both ends are derived from the loaded calendar; **no date is ever
hardcoded**, because a hardcoded boundary is wrong every year and wrong silently.

21 is arbitrary. It is not a claim about when preseason ratings appear — the CFBD calendar has no
preseason boundary to read, so some number had to be picked. It is chosen for the shape of the two
failure modes, which are not symmetric: opening too early costs one wasted fetch of a page that has not
changed, and §4.6's freshness check already skips rather than alerts when `page_date_stamp` is null,
which is exactly the preseason case. Opening too late loses a snapshot permanently. Given a cheap error
on one side and an unrecoverable one on the other, the boundary belongs on the cheap side, and 21 days
buys three weeks of margin for a guess nobody has to revisit.

### 3.2 Partition values

| Situation | `week=` |
|---|---|
| Before week 1's start | `preseason` |
| Regular season | `01` … `15` |
| Bowls / playoff | `postseason` |
| After postseason, before next preseason | `offseason` |
| Season-level CFBD resource | `season` |
| Resolution failed | `unknown` |

### 3.3 When resolution fails

Missing calendar file, a date past the last known week, a malformed calendar: **the fetch still happens.**
Bytes are written under `week=unknown`, `week_resolution` records `"unknown"`, and the run exits non-zero
after the write so the alert fires.

This is the one place the project prefers a messy artifact to a clean failure: a Sagarin week not captured
is gone permanently, and a calendar bug is not a reason to lose it. Objects under `week=unknown` are
re-partitioned later by copy — nothing under `raw/` is deleted, so the original key stays too.

---

## 4. Sagarin collector

### 4.1 Fetch

- URL pinned to `http://sagarin.com/sports/cfsend.htm`. httpx with `follow_redirects=False`. A redirect to
  HTTPS is a `FetchError`, not something to follow — the site 302s HTTPS to HTTP and a client that upgrades
  loops forever.
- Timeout 30s connect + read. **Three requests at most — the initial one plus two retries — with backoff
  2s then 8s between them.** Retry on timeout, connection error, and 5xx. Do not retry 4xx.
- Total failure: no snapshot written, `FetchError` raised, workflow red. There is a full day of margin
  before the week's data is at risk, so a manual re-run covers a multi-hour outage.

**"Requests", never "attempts".** An earlier draft said "three attempts, backoff 2s / 8s / 30s", and those
two halves cannot both be true: three attempts leave room for only two backoffs and the third rung is
never reached. The word was the ambiguity — "attempt" reads as either the initial request or only the
retries after it, and an implementation can satisfy the sentence with three requests or with four. This
spec counts **requests**, initial one included, everywhere it bounds a retry loop.

The count that survived is three, and the third rung went with it. The margin argument above is the reason:
a full day of slack means a manual re-run covers a multi-hour outage, so a 30s wait buys resilience this
design does not want and delays a red run that should already be red. §5.3 drops its last rung for a
sharper reason — every CFBD retry spends a call from a 25-request budget.

### 4.2 Encoding

Deterministic, no detection dependency:

```python
CANDIDATES = ("utf-8", "cp1252", "latin-1")
MARKERS = ("CONFERENCE AVERAGES", "Hawai")
```

First candidate that decodes without raising **and** contains both markers wins; the winner is recorded in
the manifest. None qualifying raises `EncodingError`. The marker check is load-bearing because `latin-1`
decodes arbitrary bytes without complaint — decoding successfully is not evidence of decoding correctly.

### 4.3 Order of operations

```
1. fetch bytes                       -> FetchError / EncodingError terminate the run
2. put_bytes(snapshot_key)           -> the irreplaceable artifact is now safe
3. put_json(manifest_key)            -> fetch-only fields
4. parse ratings + predictions       -> ParseError / ValidationError
5. resolve every name via crosswalk  -> UnmappedTeamError
6. put_json(manifest_key)            -> full manifest, parse_ok=true
7. freshness check                   -> StaleSourceError
```

Steps 4–7 failing leaves a snapshot with an honest partial manifest (`parse_ok` absent). That is a
detectable state and a replayable one; it is never a reason to discard bytes.

### 4.4 Parsing

Per the `sagarin-format` skill, restated here as requirements the tests enforce:

- Parse **section 1 only**. Section 3 repeats every team, and a whole-page parse silently returns all 266
  teams twice. **Do not stop at the literal `CONFERENCE AVERAGES`** — on the real page that string occurs
  exactly once, in the intro legend *above* section 1, so a parser that stops at it returns zero teams.
  §4.7 has the boundaries that actually hold.
- Anchor on structural tokens — the `=` after the division code and the `|` separators. Never split on
  whitespace, never slice fixed columns.
- Carry the published **rank** as the identity. Never sort, dedupe, or join on the rating value; distinct
  teams print identical ratings. Duplicate ranks raise.
- Capture per-column HFA values, the title-line state flag, and conference per snapshot.
- Keep FCS (`AA`) rows, marked. Filtering to FBS is a modeling decision, not a collection one.
- Parse the `Predictions_with_Totals_and_Moneylines` section into `GamePrediction` rows. That section is
  the actual benchmark competitor and is worth more than the ratings table.

### 4.5 Validation

Pydantic models in `models.py`. Validators raise; they never coerce, default, or return `None`.

```python
class TeamRating(BaseModel):
    rank: int = Field(ge=1)
    name: str = Field(min_length=1)
    rating: float
    predictor: float
    golden_mean: float
    recent: float
    division: Literal["A", "AA"]
    conference: str
    wins: int
    losses: int

class GamePrediction(BaseModel):
    home: str
    away: str
    predicted_margin: float
    total: float | None
    moneyline: int | None

class SagarinSnapshot(BaseModel):
    fetched_at: datetime
    page_date_stamp: date | None               # None on a preseason page — it has no stamp (§4.7)
    page_state: Literal["preseason", "in-season"]
    hfa: dict[str, float]                      # non-empty; no default anywhere
    teams: list[TeamRating]
    predictions: list[GamePrediction]

    @model_validator(mode="after")
    def ranks_are_unique(self): ...            # raises DuplicateRankError
    @model_validator(mode="after")
    def preseason_degeneracy_is_flagged(self): ...
```

Preseason is a legal state, not an error: all four columns identical, records 0-0, schedule strength 0.00.
It parses and is flagged, so Phase 1 cannot treat week-zero ratings as carrying schedule information.

### 4.6 Freshness

```python
# collectors/sagarin.py
def check_freshness(*, store: SnapshotStore, source: str, now: datetime,
                    data_dir: Path | None = None) -> None:
    """Raise StaleSourceError if the page's internal stamp has not advanced."""
```

`data_dir` is the one addition to the signature this section originally gave, and it matches
`fetch_sagarin`: the `in_season` gate needs a calendar, and a function that loads its own from a fixed
path cannot be tested without one on disk. A calendar that will not load **raises** rather than being
skipped past — not knowing whether it is February is not grounds to fall through to the comparison, and
still less to stay quiet.

- Compare this snapshot's `page_date_stamp` against the newest manifest whose `fetched_at` date is
  **strictly earlier than today (UTC)**, and which is not the current snapshot itself. Same-day snapshots
  are ignored, so a manual re-run compares against last Tuesday exactly as the scheduled run did — and a
  check run on a day with no fetch compares the newest snapshot against the one before it, rather than
  against itself.
- Previous state is derived from the manifests in S3. There is no state file, SSM parameter, or counter
  that could drift out of sync with the snapshots.
- No prior-date manifest (first ever run) → pass, and log that the comparison was skipped.
- Either stamp missing (`page_date_stamp` null — the preseason page carries no stamp at all, §4.7) → pass,
  and log that the comparison was skipped. There is nothing to compare until the first in-season page lands.
- Stamp advanced → pass. Stamp unchanged → `StaleSourceError` naming both stamps and the days elapsed.
- The check runs only when `calendar.in_season(now)` is true. Sagarin does not update from roughly February
  through August; alerting through the off-season is how alerting dies.
- **An empty store passes and logs a skip.** §8 makes `fetch` and `check-freshness` separate commands with
  nothing ordering them, so a check can run before anything has ever been fetched. Passing is the only
  answer that does not turn an empty bucket into a permanently red workflow. The *reason* string logged for
  this case is deliberately not contractual — it is outside what this section specifies, and an
  implementation may fold it in with "no prior manifest" or name it separately.

**Every skip logs why, and the vocabulary is fixed.** Three of the four paths through this function are a
pass, and a pass here is byte-identical to a healthy run from outside the process: same exit code, same
green workflow, nothing written. The log line is the only thing separating "there was nothing to compare"
from "the comparison ran and the source is alive", so it is output the check owes, not diagnostics. The
strings live in `logging.py` as constants — a skip logging `reason=no_stamp` in one place and
`reason=missing_date` in another is not a vocabulary — and the tests import them rather than restating
them, because a test that spells the strings out itself passes against an implementation that logs
something else entirely.

| Line | When |
|---|---|
| `event=freshness source=… result=skip reason=not_in_season` | `in_season(now)` is false |
| `event=freshness source=… result=skip reason=no_prior_manifest` | first run, or an empty store |
| `event=freshness source=… result=skip reason=no_page_date_stamp key=…` | either stamp null |
| `event=freshness source=… result=ok stamp=… prior_stamp=… days=…` | the stamp advanced |

The stale case logs nothing: it raises, and §9 puts the message on stderr with exit 1.

### 4.7 The golden fixture, and what the page actually contains

`tests/fixtures/sagarin_2026_preseason.txt` is a verbatim capture of
`http://sagarin.com/sports/cfsend.htm` taken **2026-08-27**: 148,793 bytes, CRLF line endings and the HTML
wrapper intact, sha256 `ba40d83651ea42b961c8042c82831724c4d2c278b187930370f75115897090a2`. It is the 2026
STARTING page, so it is also the preseason degeneracy fixture of §4.5.

`tests/fixtures/.gitattributes` marks the directory `* -text`. This repo has `core.autocrlf=true`; without
that line git normalizes the capture's line endings on commit and hands Linux CI different bytes than the
dev machine, at which point the hash above is a lie and "golden" means nothing.

`sagarin_malformed_row.txt` is derived from the capture: the header block and ranks 1–10, with rank 5's
rating value deleted and the `=` anchor and every other field left in place. That is the shape a lenient
parser turns into `rating=None` rather than an error.

**Counts on this page.** 266 teams in section 1, ranks 1–266 contiguous. Division `A` = 138, `AA` = 128.
The prose states its own total: `266 TEAMS RATED`.

**Section boundaries.** The literal `CONFERENCE AVERAGES` appears **once**, in the intro legend above
section 1 — it is not a terminator (§4.4). Section 1 ends at a rule of underscores after rank 266; the
conference table follows under a `Conference Rankings` heading; section 3 then reprints all 266 teams.

**Four row shapes that a naive "rank name division = rating" regex will swallow.**

| Shape | Example | Handling |
|---|---|---|
| Section-1 team | `   1  Ohio State           A  = 103.07 …  BIG TEN  (A)` | the only rows to parse |
| Section-3 reprint | identical text, later in the file | must not be parsed twice |
| Conference average | `   1  SEC                 (A) =  87.67 …` | not a team |
| UNRATED sentinel | ` 267  ***UNRATED***        __ = -76.07 …` | not a team; division is `__`, and it sits past section 1 under its own header block |

**Repeating headers.** The title / column-header / `HOME ADVANTAGE` block reprints every 10 rows in the
ratings table and every 50 rows in the predictions table. A parser must skip them mid-table, not assume
one header at the top.

**HFA.** The page prints **five** bracketed values (`RATING`, `PREDICTOR`, `GOLDEN_MEAN`, `RECENT`,
`STRONG RECENT`), and the `hfa` dict in §2.2 now names all five. All five read `2.41` on this capture.
Only the ratings header uses the bracketed `[  2.41]` form — the predictions header prints the same
numbers unbracketed.

**No date stamp on a preseason page.** The title line is `2026 College Football STARTING ratings` — season
and state, no date. In-season pages carry a "through games of …" date. Hence `date | None` in §4.5 and the
skip in §4.6.

**The predictions section is printed twice**, exactly like section 3: the regular set, then a second full
copy under `EXPERIMENTAL NUMBERS INVOLVING HOME-AWAY ADJUSTMENTS FOR EACH TEAM`. 53 games each on this
page. `parse_predictions` must take the first block only.

**Encoding.** This capture is pure ASCII — 0 bytes above 0x7F. `Hawai'i` uses an ASCII apostrophe and the
copyright is the `&copy;` entity, so the §4.2 sniff resolves to `utf-8` here. The candidate ladder and the
marker check still stand: the page has changed shape before and the markers both appear (the legend
supplies `CONFERENCE AVERAGES`).

**Parser surface pinned by the tests.** §4.4 did not name functions; `tests/test_sagarin_parser.py` fixes
them as:

```python
# parsers/sagarin_ratings.py
def parse_ratings(text: str) -> list[TeamRating]: ...     # section 1 only; raises on a bad row
def parse_hfa(text: str) -> dict[str, float]: ...         # non-empty or raise; never a default
def parse_page_state(text: str) -> str: ...               # "preseason" | "in-season"
def parse_season(text: str) -> int: ...
def parse_page_date_stamp(text: str) -> date | None: ...  # None on a preseason page
```

`DuplicateRankError` is asserted to come out of `parse_ratings`, not out of the `SagarinSnapshot`
validator in §4.5. Failing at the page is earlier than failing at the model; keep the model validator too
as defence in depth.

---

## 5. CFBD collector

### 5.1 Budget

A per-run hard cap, enforced in the client, not a shared counter:

```python
CALL_BUDGET_PER_RUN = 25          # the 26th call raises CallBudgetExceeded
```

Stateless and testable, and it bounds the month at cap × runs (~200 worst case). There is no cross-run
counter to race or to leave wrong after a crash. Every call is logged with a running count, so the real
monthly figure is recoverable from Actions logs for the write-up.

**The 1,000 calls/month figure is not vendor-backed and must never become a runtime check.** CFBD's
current documentation deliberately declines to state limits, pointing at the API tiers page and noting
that the details change. 1,000 is a number this repo copied down once. The per-run cap above is the
defence precisely because it holds whatever the tier turns out to be; a guard that compared against a
remembered monthly total would be both stale and unenforceable. The `info` operations
(`/api/info`) report account information and recent usage and are the only current source for the real
figure — at the cost of a call.

### 5.2 What Sunday pulls

| Call | Frequency | Snapshot partition |
|---|---|---|
| `/calendar?year=2026` | once per season | `week=season/calendar/` |
| `/teams?year=2026` | once per season | `week=season/teams/` |
| `/games?year=2026&week=N` | weekly | `week=NN/games/` |
| `/lines?year=2026&week=N` | weekly | `week=NN/lines/` |

~2 calls per in-season week, ~20/month. `N` is the week that just completed.

### 5.3 Rate limits and retries

429 → respect `Retry-After` when present, otherwise backoff 5s then 20s. **Three requests at most — the
initial one plus two retries — and every one of them counts against the budget of §5.1.** 5xx follows
§4.1, which is a different and shorter ladder on purpose: a 429 is the server asking for room, a 500 is
the server failing. Exhausted → `FetchError`, red run. CFBD history is backfillable, so a lost Sunday is
an inconvenience, not a hole.

The retry budget is tighter here than anywhere else in this spec for a reason that is arithmetic rather
than taste. §5.1 caps a run at 25 requests and §5.2 spends about 2 of them per in-season week. A four-
request ladder on a bad Sunday turns one weekly pull into 4 of that 25, and two of them into 8 — the
retries would be a larger share of the budget than the data. A third retry buys one more chance at a
source whose history is backfillable anyway, at a price paid from the one resource that is not
replenishable within the month.

**`429` is no longer in CFBD's documented response list**, which names `400`, `401`, `404`, `500` and an
unnamed "quota or entitlement response". Keep the `429` branch — the vendor removing it from a docs page
is not evidence the server stopped sending it — but do not assume it is the only over-quota signal. An
unrecognised quota or entitlement response is **non-retryable**: retrying a request the account is not
entitled to make burns budget to earn the same answer. Log the status and the response body on every
non-2xx, without exception. The one thing that makes this decidable is a real response, and a run that
discarded the body leaves nothing to decide from.

### 5.4 Re-runs

Every invocation fetches for real and writes a new timestamped snapshot. No caching, no "reuse today's
copy" logic. Re-running after a parser fix is not the fetch command's job — `cfb replay` (§8) re-parses an
existing snapshot with no network at all.

### 5.5 Credentials

**The AWS account is `679878703800`, and the profile is `tp-site`.** Nothing in this spec said so until
an hour was spent on it. The trap is that a second account, `100611042748`, is reachable under a
similarly-named profile (`jtravisp`), and every command aimed at it succeeds — it lists buckets, reads
parameters, assumes roles — while pointing at the wrong account. The failure is never an access error;
it is an empty result set, or a parameter that does not exist, or a bucket that is not there. Same
nickname, different account, and no error message distinguishes them.

So: **always name the profile explicitly**, and confirm it before believing an empty result:

```bash
aws sts get-caller-identity --profile tp-site --query Account --output text
# expect: 679878703800
```

Regions are also split, and only in one place. Everything is **us-east-1** — the data bucket, SSM, the
publisher role — except the Terraform state bucket `travispollard.com-tf-state`, which is **us-west-2**
(§10.1). That is the only us-west-2 resource in the project.

`/travispollard/cfb/cfbd_api_key`, SSM **SecureString**. CI reads it after assuming the publisher role via
OIDC; locally it is read with `AWS_PROFILE=tp-site`. No API key in a GitHub secret, no `.env` file.

The publisher policy covers `ssm:GetParameter` on `/travispollard/*` and, as of this spec, a `kms:Decrypt`
statement scoped by `kms:ViaService = ssm.<region>.amazonaws.com` (`DecryptParametersViaSSM` in
`cfb/terraform/main.tf`). The role can therefore use a KMS key only through SSM, never to read anything
else that key protects.

Whether that statement is strictly required depends on the key: the default `alias/aws/ssm` key grants
Decrypt to account principals in its own key policy, so `ssm:GetParameter` alone usually suffices there. A
customer-managed key does not, and the parameter can be re-keyed without anyone remembering this. The
statement makes the read work in both cases.

---

## 6. Crosswalk

### 6.1 Storage

`cfb/data/crosswalk/teams-2026.yaml`, one file per season, committed. YAML because the *why* of a mapping
matters as much as the mapping, and a comment is the only place that fits:

```yaml
# canonical_id: project-owned slug, stable forever, vendor-neutral
usc:
  cfbd: USC
  cfbd_id: 30
  sagarin: Southern California
  division: FBS
ucf:
  cfbd: UCF
  cfbd_id: 2116
  sagarin: Central Florida(UCF)      # no space before the paren
  division: FBS
texas-am:
  cfbd: Texas A&M
  cfbd_id: 245
  sagarin: Texas A&M
  division: FBS
```

- **Canonical id is a project-owned slug**, not a CFBD id. A vendor id change or a source swap must not
  rewrite historical joins. `cfbd_id` rides along for direct joins and as a cross-check on the name mapping.
- **One file per season.** A played season's mapping is frozen; backfill reads that season's file, so a
  2027 realignment cannot retroactively break a 2026 join. The ~134 duplicated rows per season are cheap.
- Conference is **not** in the crosswalk. It is time-varying and belongs in each snapshot's parsed output as
  a slowly-changing dimension.
- Optional `sagarin_aliases` / `cfbd_aliases` lists hold historical spellings. Aliases are exact strings.

### 6.2 Interface

```python
# crosswalk/__init__.py
def load(season: int) -> Crosswalk: ...

class Crosswalk:
    def from_sagarin(self, name: str) -> str: ...   # -> canonical_id, raises UnmappedTeamError
    def from_cfbd(self, name: str) -> str: ...      # -> canonical_id, raises UnmappedTeamError
    def division(self, canonical_id: str) -> Literal["FBS", "FCS"]: ...
```

No fuzzy matching, no normalization pass, no default, no `None` return. Exact lookup against the mapping
and its alias lists, or it raises.

### 6.3 Bootstrap

`src/cfb/crosswalk/bootstrap.py` is a one-off tool, quarantined from the runtime path by module boundary
and by a test asserting nothing under `collectors/` or `parsers/` imports it.

```
uv run cfb crosswalk bootstrap --season 2026
  auto-matched exactly: 241
  needs review -> cfb/data/crosswalk/_candidates-2026.yaml
    "Central Florida(UCF)"  ~ UCF     (0.61)
    "Miami-Florida"         ~ Miami   (0.72)
    "Southern California"   ~ USC     (0.09)   <- scoring is no help; decide by hand
```

Similarity scoring exists **only** here, only to order a human's ~25 decisions, and never to decide one.
`_candidates-*.yaml` is scratch; the reviewed result is hand-merged into `teams-YYYY.yaml`.

### 6.4 The fix loop

An unmapped name fails the run *after* the snapshot is safely written. The error message is the fix:

```
UnmappedTeamError: 1 unmapped Sagarin name in
raw/sagarin/season=2026/week=04/2026-09-16T110302Z.txt

Add to cfb/data/crosswalk/teams-2026.yaml:

  kennesaw-state:
    cfbd: Kennesaw State
    sagarin: "Kennesaw St."
    division: FCS

Then: uv run pytest cfb/tests/test_crosswalk.py
```

This applies to FCS names too. A new cupcake opponent turning the run red for ten minutes is the intended
cost of never letting a game vanish silently. Determining whether an unknown name is FBS or FCS is itself a
crosswalk question, so there is no "warn for FCS" tier.

### 6.5 Tests

**The crosswalk spans FBS and FCS, and the reason is `/games` rather than tidiness.** Sagarin rates 266
teams, 128 of them FCS, and `/teams/fbs` returns none of those — so "every Sagarin name resolves" was
unsatisfiable as this section originally read. Scoping the crosswalk to FBS-only does not rescue it:
`/games` returns FCS opponents by CFBD name, so the first FBS-vs-FCS game of September needs that join to
work or the game vanishes from the training set. That is the failure this whole project is built to
prevent.

So the season-level pull is **`/teams?year=2026`**, not `/teams/fbs` (§5.2), and the roster fixture carries
both divisions.

`/teams` returns 684: 138 FBS, 128 FCS, 171 D-II, 247 D-III. The fixture keeps **FBS and FCS only, 266
rows — exactly the number Sagarin rates, and the two 128s agree independently.** The 418 lower-division
rows are dropped because Sagarin rates none of them, so the crosswalk can never be asked about one. An FBS
team scheduling a D-II opponent raises `UnmappedTeamError` and turns a run red, which is §6.4's fix loop
working as designed rather than a gap to pre-empt with 418 rows nobody would review.

Fixture rosters are the contract: `tests/fixtures/rosters/sagarin-2026.txt` (all 266 names from the golden
capture, one per line, sorted) and `cfbd-2026.json` (266 rows: id, school, conference, classification).
Their exact-name overlap is 234, which is why §6.3's bootstrap has roughly 30 decisions to order and not
zero.

- every Sagarin name in the roster fixture resolves
- every CFBD name in the roster fixture resolves
- no crosswalk entry references a name absent from both rosters (catches typos and orphans, not just gaps)
- no duplicate `canonical_id`; no source name mapped to two canonical ids
- an unknown name raises `UnmappedTeamError`
- runtime modules do not import `bootstrap`

---

## 7. What Phase 0 does *not* write

No parsed or normalized data layer. The collector parses to prove the bytes are good and resolves names to
prove the crosswalk is complete, then discards the objects. The only derived artifact is the post-parse
manifest, whose summary fields (`team_count`, `fbs_count`, `hfa`, `page_state`, `predictions_count`) are
enough to see snapshot health without committing to a schema Phase 1 would only have to change.

Phase 1 replays `raw/` to build whatever it needs.

---

## 8. CLI

One console script, `cfb`, registered in `pyproject.toml`. The workflows call exactly the commands a human
calls locally — that is what makes a red run reproducible.

```
uv run cfb fetch sagarin [--store URL] [--force]
uv run cfb fetch cfbd --resource {games,lines,teams,calendar} [--week N] [--season Y]
uv run cfb check-freshness sagarin [--as-of DATE]
uv run cfb replay <s3-or-file-key>            # parse + validate an existing snapshot, no network, no write
uv run cfb crosswalk bootstrap --season 2026
uv run cfb crosswalk verify --season 2026     # the §6.5 assertions against the live files
```

`--store` accepts `s3://travispollard-cfb-data` (default) or `file://./local-snapshots`.
`--force` bypasses the `in_season` guard for manual testing.

The CLI is a thin shell over functions that take their dependencies as arguments, because a command
that constructs its own client and reads its own credential cannot be tested without both:

```python
# manifest.py
def snapshot_key(*, source: str, season: int, week: str,
                 fetched_at: datetime, resource: str | None = None) -> str: ...
def manifest_key(snapshot_key: str) -> str: ...          # idempotent

# collectors/sagarin.py
def fetch_sagarin(*, store: SnapshotStore, now: datetime,
                  fetch: Callable[[], bytes], data_dir: Path | None = None) -> SagarinSnapshot: ...
```

`fetch` is a zero-argument callable returning the raw response bytes. The CLI passes the real pinned-HTTP
fetcher of §4.1; the tests pass a lambda over a fixture, which is how the suite exercises §4.3's ordering
with no network. Any non-2xx is a `FetchError` inside the fetcher, so bytes reaching `fetch_sagarin` are
by construction a 200.

---

## 9. Errors and exit codes

```python
class CfbError(Exception): ...
class FetchError(CfbError): ...              # network, timeout, redirect, non-2xx after retries
class EncodingError(CfbError): ...
class SnapshotExistsError(CfbError): ...    # a raw key already holds an object; raw is write-once
class SnapshotNotFoundError(CfbError): ...  # a read targeted a key the store does not hold
class ParseError(CfbError): ...
class DuplicateRankError(ParseError): ...
class ValidationError(CfbError): ...         # wraps pydantic
class UnmappedTeamError(CfbError): ...
class WeekResolutionError(CfbError): ...
class StaleSourceError(CfbError): ...
class CallBudgetExceeded(CfbError): ...
```

Any `CfbError` → exit 1, message to stderr, workflow red. There is no exit code meaning "partially ok".
Nothing catches these to log-and-continue; a validation failure demoted to a warning is the exact failure
mode this project exists to prevent.

Logging is structured key=value to stdout —
`event=snapshot_written source=sagarin season=2026 week=04 key=raw/… bytes=184320 sha256=9f2c…` — so an
Actions log is greppable and every failure message carries the source, season/week, and S3 key.

---

## 10. Infrastructure

### 10.1 `cfb/terraform`

**Account `679878703800`, profile `tp-site`** — see §5.5 for why naming it matters and how to confirm
you are in it. Both Terraform roots target that account.

**Two regions, and the split is deliberate.** All resources are **us-east-1**. The remote state bucket
`travispollard.com-tf-state` is **us-west-2**, which is why the `backend "s3"` block below carries a
`region` that disagrees with the provider's. That is not a mistake to normalise: the state bucket predates
this project and both roots already use it. An `init` pointed at us-east-1 finds no bucket and offers to
create one, which is how a project ends up with two state files and no error.

`cfb/terraform/main.tf` is drafted and correct in substance. The `kms:Decrypt` statement (§5.5) is applied;
`terraform validate` passes. Still needed before the first apply — a `terraform` block with both a backend
and a provider constraint:

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"                      # or ~> 5.0 to match the root stack; pick one
    }
  }

  backend "s3" {
    bucket = "travispollard.com-tf-state"     # same bucket as the root stack
    key    = "cfb/terraform.tfstate"          # separate state, separate lifecycle
    region = "us-west-2"
  }
}
```

The provider constraint is not optional bookkeeping. With no constraint, `init` takes the newest provider —
today v6 — while the root stack pins `~> 5.0`, and the two versions disagree on real syntax:
`data.aws_region.current.name` is correct on v5 and deprecated on v6. The drafted config sidesteps this by
using a `region` variable (default `us-east-1`) instead of the data source, but the next resource that
reaches for a provider-versioned attribute will hit it again.

- `github_repo` default → **`jtravisp/travispollard.com`**. The draft says `travispollard/…`, which does not
  exist; the OIDC trust condition would never match and every scheduled run would fail to assume the role.
- ~~The GitHub OIDC provider already exists in the account, so the `data` lookup is correct as drafted.~~
  **Wrong, and an apply proved it.** `aws iam list-open-id-connect-providers --profile tp-site` returns an
  empty list: account `679878703800` has no OIDC provider at all, so the data source could never resolve
  and the publisher role could never be created. `cfb/terraform` now **creates** it —
  `resource "aws_iam_openid_connect_provider" "github"`, url `https://token.actions.githubusercontent.com`,
  `client_id_list = ["sts.amazonaws.com"]`, no `thumbprint_list` (AWS stopped requiring one for its own
  trusted issuers, and a pinned thumbprint is a value that rotates without warning and breaks every
  assume-role when it does).

  **This resource is account-scoped, not cfb-scoped**, and that is a seam worth naming. An account holds
  exactly one provider per issuer URL, so it is a singleton every future GitHub Actions consumer in this
  account will share — a second root creating its own is an error, not a merge. `cfb` owns it because
  `cfb` is the only consumer today and something has to. **When a second consumer appears, this moves to
  a shared root and both read it back as a data source.** Owning it here beats a data source pointing at
  something nothing creates, which is the state this spec described until now.
- ~~Add `kms:Decrypt` to the publisher policy for the SecureString API key (§5.5).~~ Applied.
- Everything else stands: private versioned bucket, `raw/` lifecycle to STANDARD_IA at 90 days, no
  `s3:DeleteObject` on `raw/`, CloudFront read scoped to `cfb/data/*` only.

State is separate from the root stack and stays that way. The seam is SSM in one direction only; neither
root reads the other's remote state.

### 10.2 Root stack

Phase 0 adds **only** the two SSM parameters from `cfb-wiring.tf`:

```
/travispollard/cdn/distribution_id
/travispollard/cdn/distribution_arn
```

Apply order is root, then cfb — the cfb stack reads the ARN at plan time. The CloudFront work in
`cfb-wiring.tf` (module parameterization, OAC, the `/cfb/data/*` behavior) is **deferred to Phase 1**, when
there is JSON to serve. Phase 0 has no reason to touch the live distribution.

Keep `cfb-wiring.tf` in the repo with its comments intact; apply only its `aws_ssm_parameter` resources this
phase.

**Resolved:** the draft referenced `module.cloudfront.distribution_id` and `.distribution_arn`, neither of
which existed — the module exported `cloudfront_distribution_id`, `cloudfront_domain_name`, and
`cloudfront_zone_id`, and no ARN at all. `modules/cloudfront/outputs.tf` now also exports
`cloudfront_distribution_arn`, and `cfb-wiring.tf` uses the module's `cloudfront_`-prefixed names, matching
how `main.tf` already consumes it. `terraform validate` passes at the root with `cfb-wiring.tf` in place.

This mattered more than a typo because of the apply order: the cfb stack reads
`/travispollard/cdn/distribution_arn` at **plan** time, so a root stack that cannot produce the parameter
blocks the cfb stack from planning at all — not just from being correct.

---

## 11. Workflows

One workflow per source. A red X in the Actions tab names the failing source without anyone opening it.

| File | Trigger | Does |
|---|---|---|
| `cfb-ci.yml` | `pull_request`, paths `cfb/**` | `uv sync`, `ruff check`, `pytest`. Offline by construction — no AWS credentials configured for this job at all. |
| `cfb-sagarin.yml` | `schedule` Tue 12:00 UTC, `workflow_dispatch` | OIDC → `cfb fetch sagarin` → `cfb check-freshness sagarin` |
| `cfb-cfbd.yml` | `schedule` Sun 12:00 UTC, `workflow_dispatch` | OIDC → `cfb fetch cfbd` for the completed week |

- Sunday 12:00 UTC is 07:00 CT — hours after the last West Coast game goes final. Tuesday 12:00 UTC gives
  Sagarin's Monday/Tuesday update time to land. Actions cron drifts 5–15 minutes under load; both margins
  absorb that.
- Both collect workflows call `calendar.in_season(now)` as their first step and exit 0 immediately when it
  is false. That is the entire off-season story: no runs to mute, no suppression state, no false alarms from
  February to August.
- Python 3.12 via `astral-sh/setup-uv`. Permissions: `id-token: write`, `contents: read`. Nothing in Phase 0
  writes to the repo.

**Alerting is the workflow failure itself.** A non-zero exit turns the run red and GitHub emails it. No SNS
topic, no bot token, no issue automation — and the failure history stays visible in the Actions tab, which
is itself part of what a reviewer reads. `StaleSourceError` reaches you by the same path as every other
failure, which means the alert path is exercised by every bug, not only by the rare stale week.

---

## 12. Out of scope

Explicitly, so none of it creeps in around week three:

- Elo, ratings, predictions, win probability, any model at all
- Any JSON under `cfb/data/*` in the bucket, and therefore any CloudFront origin, OAC, or cache behavior
- Any route under `frontend/app/cfb/`, and any change to the site build or the CodeBuild pipeline
- Historical backfill of CFBD seasons
- A parsed/normalized data layer in S3 (§7)
- The `/projects/cfb-forecast` write-up and the architecture diagram
- SNS, PagerDuty, issue bots, or any alerting beyond a red workflow
- Deleting or archiving `www/` — deferred by decision; the root `CLAUDE.md` already marks it dead
- Kubernetes

---

## 13. End-to-end verification

Phase 0 is done when **two consecutive unattended scheduled runs succeed** in the same calendar week:

```
Sun 12:00 UTC   cfb-cfbd.yml     green
Tue 12:00 UTC   cfb-sagarin.yml  green
```

with no `workflow_dispatch`, no local run, and no hand-edited object. Then verify:

```bash
# 1. Both snapshots exist, with manifests, under the right partitions
aws s3 ls --recursive s3://travispollard-cfb-data/raw/sagarin/season=2026/ --profile tp-site
aws s3 ls --recursive s3://travispollard-cfb-data/raw/cfbd/season=2026/    --profile tp-site

# 2. The Sagarin manifest shows a completed parse and real HFA read from the page
aws s3 cp s3://travispollard-cfb-data/raw/sagarin/season=2026/week=04/<ts>.meta.json - \
  --profile tp-site | python -m json.tool
#    expect: parse_ok true, page_date_stamp advanced from the prior week,
#            hfa non-empty, team_count 266, fbs_count 138, unmapped []

# 3. Nothing was overwritten: every snapshot object has exactly one version
aws s3api list-object-versions --bucket travispollard-cfb-data \
  --prefix raw/sagarin/season=2026/week=04/ --profile tp-site \
  --query 'Versions[?ends_with(Key, `.txt`)].[Key,VersionId]'

# 4. The snapshot replays offline and still parses
uv run cfb replay raw/sagarin/season=2026/week=04/<ts>.txt

# 5. The freshness check is load-bearing, not decorative:
#    run it as of last week and confirm it raises
uv run cfb check-freshness sagarin --as-of <last week's date>
#    expect: StaleSourceError, exit 1
```

The two green runs prove the cron, the OIDC role, the bucket policy, and the live bytes together — which no
dispatch-triggered run does. Step 5 proves the alert fires; an alert that has never fired is not an alert.

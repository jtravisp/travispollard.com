Parsing rules and known traps for Jeff Sagarin's college football ratings page at sagarin.com. Use when writing, debugging, or reviewing any code that fetches, parses, validates, or stores Sagarin ratings, or when reconciling Sagarin team names against another source.

Sagarin ratings page format

Source: http://sagarin.com/sports/cfsend.htm. Fixed-width text inside a <pre> block on an old page. It can change shape without warning, which is why every rule below exists.

Fetching

The scheme matters. The site 302s HTTPS to HTTP. A client that upgrades HTTP to HTTPS will loop forever. Pin the scheme to HTTP explicitly and do not let the client upgrade. requests and httpx are fine as long as you do not force TLS.

Snapshot before parsing. Write the raw bytes to S3 on every pull, date-partitioned, immutable. Never parse-and-discard. This gives replay when the parser improves and accumulates into a dataset that exists nowhere else.

Do not assume UTF-8. Sniff the encoding and raise on failure — never silently produce mojibake. The 2026-08-27 capture happens to be pure ASCII (Hawai'i uses an ASCII apostrophe, the copyright is a &copy; entity), but the page has carried a typographic apostrophe and a literal © before now, and it changes shape without warning. Decoding successfully is not evidence of decoding correctly: latin-1 decodes arbitrary bytes without complaint, so check for expected marker strings too.

Structure

The page has three sections in order:

Teams sorted by rating
Conference averages
Teams grouped by conference

Section 3 repeats every team. A naive whole-page parse returns all 266 teams twice with no error, and the duplication surfaces only as a quietly wrong model. Parse section 1 only.

Do not stop at the literal CONFERENCE AVERAGES. On the real page that string occurs exactly once, in the intro legend above section 1, so a parser that stops at it returns zero teams. Section 1 ends at a rule of underscores after the last rank; the conference table follows under a Conference Rankings heading.

Three more row shapes match a naive "rank name division = rating" regex and are not teams:

Conference averages, which print as `   1  SEC                 (A) =  87.67` — the division is parenthesised.
An UNRATED sentinel, `267  ***UNRATED***        __ = -76.07`, sitting past section 1 under its own header block, with `__` where the division goes.
The section-3 reprints themselves, byte-identical to the section-1 rows.

Headers repeat mid-table. The title / column-header / HOME ADVANTAGE block reprints every 10 rows in the ratings table and every 50 rows in the predictions table. Do not assume one header at the top.

Row parsing

Never split on whitespace. Team names contain spaces, apostrophes, and parentheses: Texas A&M, Army West Point, Southern California, Hawai'i, and Central Florida(UCF) — which has no space before the paren. Roughly ten of every seventeen teams break whitespace splitting.

Never slice fixed columns either. It breaks the moment a name gets longer.

Anchor on structural tokens: the = following the division code, and the | column separators. This survives name-length changes.

Field rules

Rank is authoritative; rating is not. Ratings are printed to two decimals but carry more internal precision, so distinct teams can display identical values — Virginia Tech and Northwestern both show 77.49, Tulsa and Toledo both show 56.53. Never sort, dedupe, or join on the rating value. Carry the published rank through, and raise on duplicate ranks.

Never hardcode home-field advantage. It is currently 2.41 and Sagarin states explicitly that it varies during the season and that you should use the value in the output. A separate value is printed above each rating column; these are currently identical but can diverge. Capture the per-column values per snapshot. Hardcoding silently degrades every prediction as the season progresses.

There are five HFA values, not four — one per rating column including STRONG RECENT. Only the ratings header brackets them, as `[  2.41]`; the predictions header prints the same numbers bare. Anchoring on the bracketed form picks out the ratings header alone.

Conference is time-varying. In the 2026 preseason snapshot, North Dakota State appears in the Mountain West, and Boise State, Washington State, Fresno State, San Diego State, and Texas State appear in a rebuilt Pac-12. Store conference per season-snapshot as a slowly-changing dimension. A team-level conference attribute will make every historical join wrong on backfill.

FCS teams are mixed in, marked AA in the division column. Keep them — they matter for strength of schedule when a Power 4 team plays a cupcake — but filter to FBS for modeling.

Rating columns

Four variants, each with a different purpose:

Column	Meaning
RATING	Overall synthesis
PREDICTOR	Margin-oriented, built for point-spread prediction
GOLDEN MEAN	Blend
RECENT	Recency-weighted

PREDICTOR is the one to benchmark forecasts against.

Preseason is a degenerate state

Before any games: all records are 0-0, schedule strength is 0.00, and all four rating columns are identical with identical ranks. The parser must handle this and the in-season case. Week-zero ratings carry no schedule information and the model must not treat them as if they do.

The title line is a usable state flag — it reads STARTING preseason and changes in-season. Capture it.

The preseason page has no internal date stamp. Its title line is `2026 College Football STARTING ratings` — season and state, nothing else. In-season pages carry a "through games of <date>" stamp. So the parsed date stamp must be nullable, and a freshness check has nothing to compare until the first in-season page lands.

The predictions section

At the bottom of the page there is a Predictions_with_Totals_and_Moneylines anchor: Sagarin's own game-by-game predictions with totals and moneylines, plus an experimental set adjusted for home/away tendencies.

Capture this section. It is more valuable than the ratings table — it is a published competitor's predictions that can be scored head-to-head against ours and against the closing line, rather than a rating that would have to be converted first.

It is printed twice, exactly like section 3. The regular set comes first, then a second full copy under EXPERIMENTAL NUMBERS INVOLVING HOME-AWAY ADJUSTMENTS FOR EACH TEAM. Take the first block only, or every game is duplicated. On the 2026 preseason page each block holds 53 games.

Row shape is `rank [N|C] [@] FAVORITE  rating pred golden recent strong  [@] UNDERDOG  MONEY WIN% home away TOTAL pct%`. The `@` marks the nominal home team and is present even on neutral-site games; the flag after the rank is blank for a normal game, `N` for neutral, `C` for a classic, and the home/away split columns move with it.

Team-name crosswalk

Sagarin and CFBD disagree on ~266 team names. Examples:

Sagarin	CFBD
Miami-Florida	Miami
Central Florida(UCF)	UCF
Southern California	USC
Mississippi	Ole Miss
Army West Point	Army

The crosswalk is a versioned artifact with its own tests, not a dict at the bottom of a script. An unmapped team must raise. A silent drop means a game vanishes from the training set and the published accuracy numbers become fiction.

Validation posture

Reject loudly, always. A row that does not conform to the schema is an alert, not a null.

Contract-test the parser in CI against a golden fixture of a known-good page, so a format change breaks the build rather than the data. The fixture is the raw bytes off the wire — no re-encoding, no line-ending normalization. Under `core.autocrlf` git will rewrite it on checkout unless the fixture directory is marked `-text` in .gitattributes, and a fixture whose bytes differ between the dev machine and CI is not golden. `cfb/tests/fixtures/` holds the 2026-08-27 capture and the tests that pin it.

Freshness: if the page's internal date stamp has not advanced by Tuesday, page yourself. In the preseason there is no stamp to advance, so skip the check rather than alerting on it.

Copyright

The page is copyrighted. Storing derived data, running comparisons, and displaying "our model vs. Sagarin PREDICTOR" with clear attribution is ordinary analytical use. Republishing the full ratings table as a standalone feature is not. The comparison is the interesting part anyway, so this costs nothing.

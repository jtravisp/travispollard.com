/**
 * The `/cfb/data/*` contract, as the pages see it (SPEC-phase1 6).
 *
 * These types mirror the pydantic models in `cfb/src/cfb/publish/__init__.py`.
 * They are a hand copy, and that is a real cost -- a field renamed there and not
 * here is a `undefined` on the page rather than a build error. `schema_version`
 * is what makes that survivable: the generator bumps it when the shape changes,
 * and a page that does not recognise the number refuses to render rather than
 * guessing. See `useCfbDocument`.
 *
 * Every number here was computed by the pipeline. **The pages do no arithmetic
 * on them beyond formatting** -- no joining, no re-deriving, no averaging. The
 * PRD forbids prediction logic in the site and §6.1 makes each route exactly one
 * fetch, so anything that looks like a calculation belongs in the generator.
 */

/**
 * The contract versions these pages can read (§6.2).
 *
 * **Version 1 was dropped once every published document read 2** — checked
 * against the live site rather than assumed from the fact a publish had run.
 * It existed only to make the `national_rank` → `model_rank` rename seamless:
 * routes deploy before the pipeline republishes, so for that window the page had
 * to read both.
 *
 * Keeping it afterwards would have been worse than pointless. Nothing publishes
 * version 1 now, so a version 1 document means something has gone backwards —
 * a rollback, a stale cache, a hand-edited object — and a page that quietly
 * accepted it would make that look like it worked.
 *
 * **3 is here because `status` landed, and 2 stays for exactly the window 1 once
 * covered.** The pipeline and the site deploy separately, so both directions of
 * the skew are real: a v3 document reaching a page that only knows 2, and a v2
 * document still cached for a page that knows 3. `statusOf` handles the second;
 * this list is what handles the first.
 *
 * **This list is the deploy order, and getting it backwards takes the page down.**
 * On 2026-09-15 the publisher was bumped to 3 and a v3 document was published
 * while every deployed page still read `[2]`, which turned `/cfb` into the stale
 * placeholder — a worse outcome than the bye message the change was fixing. The
 * rule the sequence implies: **widen this list and deploy it before the publisher
 * starts writing the new version**, never after.
 *
 * 2 comes out once every published document reads 3 — checked against the live
 * site, the way 1 was.
 */
export const SUPPORTED_SCHEMA_VERSIONS = [2, 3];

/** Where the documents are served from. Same distribution as the site. */
export const CFB_DATA_BASE = '/cfb/data';

/** The envelope every document carries (§6.2). */
export interface Envelope {
  schema_version: number;
  generated_at: string;
  season: number;
  week: string;
}

/** §6.3's `game` block. Signed for the subject team, not the home team. */
export interface PublishedGame {
  kickoff: string;
  /**
   * When the forecast was written — not when the page was built.
   *
   * The document's own `generated_at` is the publish run's moment, and the two
   * differ by hours. The claim is that a prediction existed *before kickoff*, and
   * only this timestamp carries it.
   */
  forecast_generated_at?: string | null;
  /** The game's own week, which is not always the document's. */
  week: string;
  opponent: string;
  home: boolean;
  /** `home` alone is misleading at a neutral site, where CFBD nominates one. */
  neutral_site: boolean;
  predicted_margin: number;
  win_probability: number;
  /** As the book published it: negative favours the *home* team (§4.3). */
  market_line: number | null;
  line_source: string | null;
  /**
   * The opponent's standing **by this model**, from the same state `as_of` came
   * from. `null` for an FCS opponent — the FBS table has no place for one, and a
   * rank on a different denominator would be a different number wearing the same
   * word.
   *
   * Never render it without saying whose rank it is: a reader on a college
   * football page assumes AP.
   *
   * Optional in TypeScript as well as in the document, because a page deployed
   * before the pipeline republishes reads a document without it. See
   * `tests/cfb-old-document.spec.ts`.
   */
  opponent_model_rank?: number | null;
  opponent_elo?: number | null;
}

/** One week of the subject team's standing, by this model. */
export interface RatingPoint {
  week: string;
  elo: number;
  /** The `elo/` document behind this point. See `AsOf.elo_state`. */
  elo_state?: string | null;
  model_rank: number;
  fbs_teams: number;
}

/**
 * The subject team's most recent scored game.
 *
 * `team_points` and `opponent_points` are nullable: `scored/` is write-once, so
 * weeks graded before the points were carried through exist and cannot gain them.
 */
export interface LastResult {
  week: string;
  kickoff: string;
  opponent: string;
  home: boolean;
  team_points: number | null;
  opponent_points: number | null;
  won: boolean;
  predicted_margin: number;
  actual_margin: number;
  error: number;
  beat_market: boolean | null;
}

export interface AsOf {
  week: string;
  elo: number;
  /**
   * The `elo/` document this rating was read from (SPEC-phase3 3.1a).
   *
   * **A published Elo number could not name its own scale**, and the defect was
   * live. `as_of.elo` is the state the *forecast* named; `history[].elo` is the
   * *newest* state for that week. Both selections are correct, and they resolved
   * to the same object until the 2026-09-01 mid-season reseed wrote a third
   * preseason state no prediction references — after which the same team, in the
   * same document, read 2112.90 on scale 20 and 1990.32 on scale 16 with nothing
   * able to say so. It went unseen only because `RatingChart` renders nothing
   * below two points.
   *
   * Optional: additive, so `PUBLISHED_SCHEMA_VERSION` did not move and this route
   * deploys before the publisher emits it.
   */
  elo_state?: string | null;
  /**
   * **This model's rank, never a poll's**, and the page must say so. Ours will
   * disagree with AP visibly and often, and a bare "#5" on a college football
   * page reads as AP by default.
   */
  model_rank: number;
  fbs_teams: number;
}

/**
 * A scheduled game the model has not forecast yet (schema 3).
 *
 * **No model numbers, deliberately.** The forecast that would produce a margin
 * runs on Thursday; until then the page can name the fixture and nothing else.
 */
export interface UpcomingFixture {
  kickoff: string;
  week: string;
  opponent: string;
  home: boolean;
  neutral_site: boolean;
}

/**
 * Which of four states the document is in (schema 3).
 *
 * Before v3 the page read `game === null` as "on a bye". Three different facts
 * produce that null and only one is a bye — on 2026-09-15 `/cfb` announced a
 * Texas bye while UTSA sat on the week 3 slate for that Saturday. `cfb predict`
 * runs Thursday, so "scheduled but not yet forecast" covers roughly five days in
 * seven, and it was the state being misreported all of them.
 *
 * `schedule_unknown` was added on 2026-09-21, when the live page announced
 * "Texas's season is over" in September. The producer had been deciding that
 * from the stored slate, which only reaches as far as the last capture — so from
 * Sunday's refresh until Monday's, "we have not fetched next week yet" read as
 * "the season ended". The calendar is the authority now, and this is the state
 * for a coming week whose slate is not in hand: `bye` would be a claim the
 * evidence does not support.
 */
export type NextGameStatus =
  | 'forecast'
  | 'awaiting_forecast'
  | 'bye'
  | 'schedule_unknown'
  | 'season_over';

/**
 * The document's state, with the v2 fallback in one place.
 *
 * **A v2 document is not a bug and not rare**: routes deploy before the pipeline
 * republishes, so a new page reading an old document is the first thing that
 * happens in production every time this ships. v2 has no `status` and cannot
 * distinguish the three nulls, so the fallback says only what a v2 document
 * actually knows — there is a game, or there is not. It reproduces the old
 * behaviour for old documents rather than guessing a better answer out of
 * data that does not contain one.
 */
export function statusOf(document: NextGameDocument): NextGameStatus {
  if (document.status) return document.status;
  return document.game === null ? 'bye' : 'forecast';
}

export interface NextGameDocument extends Envelope {
  team: string;
  /**
   * Optional because a v2 document has no `status`, and a v2 document is what a
   * newly deployed route reads until the pipeline republishes. `statusOf()` is
   * the only thing that should read this field — it supplies the v2 fallback.
   */
  status?: NextGameStatus;
  /** `null` unless `status` is `forecast`. `as_of` is populated either way. */
  game: PublishedGame | null;
  /** Present only on `awaiting_forecast`. */
  upcoming?: UpcomingFixture | null;
  as_of: AsOf;
  /**
   * Optional on purpose. **The first thing that happens in production every time
   * this ships is a new page reading an old document** — routes deploy before the
   * pipeline republishes — so `history` is absent, not empty, for that window.
   * `doc.history.map(...)` on `undefined` type-checks and throws.
   */
  history?: RatingPoint[];
  last_result?: LastResult | null;
  /**
   * §3.6's disclosure, on the page where it changes what a number means.
   *
   * While it is active, the model's "edge" over the market is really Sagarin's
   * preseason opinion against a book, not this model against one.
   */
  seed_disclosure?: SeedDisclosure | null;
  season_so_far?: SeasonSoFar | null;
}

/** How the model has done so far, duplicated onto `/cfb` so it needs one fetch. */
export interface SeasonSoFar {
  through_week: string | null;
  texas: Record;
  full_slate: Record;
}

export interface AtsSummary {
  record: string;
  wins: number;
  losses: number;
  pushes: number;
  excluded_no_line: number;
  excluded_no_edge: number;
}

/**
 * One population's season-to-date figures (§6.4).
 *
 * Every mean is `number | null`, and the `null` is load-bearing: §5.3 makes it
 * `null` rather than `0.0` on an empty population, because a zero would draw a
 * point claiming a perfect prediction that was never made. Rendering a `null` as
 * `0` here would undo that at the last step.
 */
export interface Record {
  games: number;
  mae: number | null;
  brier: number | null;
  line_games: number;
  line_mae: number | null;
  sagarin_games: number;
  sagarin_mae: number | null;
  ats: AtsSummary;
}

export interface CalibrationBucket {
  label: string;
  predicted: number;
  observed: number;
  n: number;
}

export interface WeekPoint {
  week: string;
  games: number;
  mae: number | null;
  sagarin_r: number | null;
  /**
   * Set when the week was only partly forecast, so its figures cover fewer
   * games than the week they are filed under. A partial week that reads as
   * complete is the seed-disclosure problem in a new place.
   */
  forecast_from: string | null;
}

export interface SeedDisclosure {
  active: boolean;
  threshold: number;
  current_r: number | null;
  retired_week: string | null;
}

/**
 * Weeks scored retrospectively. **Not the model's record.**
 *
 * A backtested week was scored after its games were played, so it carries none
 * of the evidence a real prediction does. `measures_the_seed` is true while every
 * backtested week is one whose forecast is arithmetically the preseason seed —
 * week 1, and only week 1 — in which case the figures describe Sagarin's
 * preseason page rather than this model.
 */
export interface Backtest {
  through_week: string | null;
  measures_the_seed: boolean;
  texas: Record;
  full_slate: Record;
  by_week: WeekPoint[];
}

export interface AccuracyDocument extends Envelope {
  /** The newest week with results, which is not the envelope's week. */
  through_week: string | null;
  texas: Record;
  full_slate: Record;
  calibration: CalibrationBucket[];
  by_week: WeekPoint[];
  seed_disclosure: SeedDisclosure;
  /** `null` when nothing has been backtested. */
  backtest: Backtest | null;
}

/** One row of `/cfb/slate`. Home perspective, unlike `next-game.json`. */
export interface SlateGame {
  cfbd_game_id: number;
  kickoff: string;
  home: string;
  away: string;
  neutral_site: boolean;
  /** Positive favours the home team. */
  predicted_margin: number;
  /** The home team's, clamped. */
  win_probability: number;
  market_line: number | null;
  line_source: string | null;
  /** Involves the team `next-game.json` is about. */
  featured: boolean;
  /** The game has been played, per the newest results capture. */
  played?: boolean;
  /**
   * The two ratings behind `predicted_margin`, so an expanded row can show its
   * own arithmetic. Optional: a document published before they existed does not
   * carry them, and the row then shows what it has.
   */
  home_elo?: number | null;
  away_elo?: number | null;
}

export interface SlateDocument extends Envelope {
  team: string;
  priced: number;
  /** Set when the run covered less than the whole week; null otherwise. */
  forecast_from: string | null;
  /**
   * Games the model forecast that are not listed, because neither team is FBS.
   * Published so the page can say what it left out rather than quietly showing
   * a smaller number than the model produced.
   */
  excluded_non_fbs?: number;
  /** When the results behind `played` were captured. Not "now". */
  results_known_at?: string | null;
  /**
   * A later week that is already forecast, while this board is deliberately not
   * it. Null on an ordinary week. Set during an overlap, when the week being
   * played still has games ahead and a newer one has been generated.
   */
  next_week_forecast?: string | null;
  games: SlateGame[];
}

/**
 * The versions `/cfb/models` can read (SPEC-phase2 6.2).
 *
 * **Its own line, deliberately not shared with the other three.** `models.json`
 * is a new document and starts at 3, one past what the rest were on when it
 * shipped, so the two numbers are never mistaken for each other in a log. It
 * moves independently from here: nothing this document does can oblige
 * `next-game.json` to bump, and vice versa.
 */
export const MODELS_SCHEMA_VERSIONS = [3];

/** The games every listed system priced (SPEC-phase2 6.3). */
export interface SharedDenominator {
  games: number;
  description: string;
}

/**
 * How much of the scored season one system actually priced.
 *
 * Beside the headline MAE, never instead of it: two systems with the same MAE on
 * the same games are still different things when one reached all of them and the
 * other a third.
 */
export interface SystemCoverage {
  priced: number;
  of: number;
}

/** One row of the leaderboard (SPEC-phase2 6.2). */
export interface SystemRow {
  id: string;
  label: string;
  /** Null only when nothing has been scored yet. */
  mae: number | null;
  /**
   * Null for every system that publishes no win probability, which is all of
   * them except ours. A point spread is not a probability, and the generator
   * refuses to derive one on a vendor's behalf.
   */
  brier: number | null;
  /** Null for the benchmarks: the market has no record against itself. */
  ats: AtsSummary | null;
  coverage: SystemCoverage;
  is_ours?: boolean;
  is_benchmark?: boolean;
}

/** One week of the per-week series, on that week's own intersection. */
export interface WeekMae {
  week: string;
  games: number;
  /**
   * System id to that week's MAE.
   *
   * An index signature rather than `Record<string, number>`: this module exports
   * its own `Record` (the win-loss kind, §6.4), which shadows the built-in here.
   */
  mae: { [id: string]: number };
}

export interface ModelsDocument extends Envelope {
  /** Where the numbers stop, which is not the envelope's `week`. */
  through_week: string | null;
  shared_denominator: SharedDenominator;
  systems: SystemRow[];
  by_week: WeekMae[];
}

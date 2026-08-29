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

/** The version of the contract these pages were written against (§6.2). */
export const SUPPORTED_SCHEMA_VERSION = 1;

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
}

export interface AsOf {
  week: string;
  elo: number;
  national_rank: number;
  fbs_teams: number;
}

export interface NextGameDocument extends Envelope {
  team: string;
  /** `null` on a bye week. `as_of` is still populated. */
  game: PublishedGame | null;
  as_of: AsOf;
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
}

export interface SlateDocument extends Envelope {
  team: string;
  priced: number;
  games: SlateGame[];
}

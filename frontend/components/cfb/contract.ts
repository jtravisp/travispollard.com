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
  opponent: string;
  home: boolean;
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

export interface AccuracyDocument extends Envelope {
  /** The newest week with results, which is not the envelope's week. */
  through_week: string | null;
  texas: Record;
  full_slate: Record;
  calibration: CalibrationBucket[];
  by_week: WeekPoint[];
  seed_disclosure: SeedDisclosure;
}

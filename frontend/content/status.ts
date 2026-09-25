/**
 * The /status page's data contract: the shape of `status.json`, which the
 * status-checker Lambda (`status-checker/checker.py`) writes to the site
 * bucket every ten minutes and the page fetches at runtime.
 *
 * The thresholds live here and in the Lambda, and must agree: the Lambda
 * decides each service's status, and the page only renders it. They are
 * duplicated rather than shared because one side is Python and the other
 * is a static export -- `checker.py` names these constants the same way so a
 * grep finds both.
 */

export type ServiceStatus = 'operational' | 'degraded' | 'down';
export type OverallStatus = 'operational' | 'degraded' | 'outage';
/** A day in the 30-day history. `no_data` is a day nothing was checked. */
export type DayStatus = ServiceStatus | 'no_data';

export type DailyEntry = {
  /** YYYY-MM-DD, UTC. */
  date: string;
  status: DayStatus;
  avg_latency_ms: number | null;
};

export type ServiceCheck = {
  id: string;
  name: string;
  url: string;
  status: ServiceStatus;
  /** Final status after redirects; null when no response came back at all. */
  http_code: number | null;
  /**
   * Request sent to response headers, summed over redirects. Excludes
   * connection setup, which is timed separately. Null when the request failed.
   */
  response_time_ms: number | null;
  /** DNS + TCP + TLS for the connections the check needed. */
  connect_ms?: number | null;
  /** Days until the TLS certificate expires; null when it could not be read. */
  cert_days_remaining: number | null;
  /** Present only when something went wrong: a short, human-readable reason. */
  error?: string;
  /**
   * Share of checks in the last 30 days that were not down; null before the
   * first check. Absent (with daily_history) on a run that could not read its
   * history, or from a checker older than the history feature.
   */
  uptime_percentage_30d?: number | null;
  /** HISTORY_DAYS entries, oldest first. */
  daily_history?: DailyEntry[];
};

export type StatusDocument = {
  /** ISO 8601, UTC. When the checker finished this run. */
  last_updated: string;
  overall_status: OverallStatus;
  services: ServiceCheck[];
  history_days?: number;
};

/** A response slower than this is degraded, not operational. */
export const DEGRADED_LATENCY_MS = 1000;

/** A certificate with fewer days than this left is flagged on the page. */
export const CERT_WARNING_DAYS = 14;

/** Days in the uptime history. */
export const HISTORY_DAYS = 30;

/**
 * The checker runs every 10 minutes. A document older than this means the
 * checker itself has stopped -- a status page that goes quietly stale while
 * still showing green is worse than none, so the page says so.
 */
export const STALE_AFTER_MINUTES = 30;

/**
 * A deterministic 30-day history for the dev sample: the first `startsAfter`
 * days have no data (as a real history does until the checker has run that
 * long), and the listed offsets from today carry a bad day.
 */
function sampleHistory(
  startsAfter: number,
  incidents: Record<number, 'degraded' | 'down'> = {},
  latency = 150,
): DailyEntry[] {
  const today = Date.UTC(2026, 8, 24);
  return Array.from({ length: HISTORY_DAYS }, (_, i) => {
    const offset = HISTORY_DAYS - 1 - i;
    const date = new Date(today - offset * 86_400_000).toISOString().slice(0, 10);
    if (i < startsAfter) return { date, status: 'no_data' as const, avg_latency_ms: null };
    const status = incidents[offset] ?? 'operational';
    return {
      date,
      status,
      avg_latency_ms: status === 'degraded' ? latency * 8 : latency + (i % 5) * 7,
    };
  });
}

/**
 * Sample data for `next dev` only, used when there is no status.json to
 * fetch. It is never used in a production build: a status page must not
 * show invented results as if they were real, so production shows an
 * "unavailable" state instead. Deliberately not a file in public/ either --
 * the deploy copies public/ into the same bucket the Lambda writes to, and
 * would overwrite the real status.json with this on every release.
 */
export const SAMPLE_STATUS: StatusDocument = {
  last_updated: '2026-09-24T19:55:00Z',
  overall_status: 'degraded',
  history_days: HISTORY_DAYS,
  services: [
    {
      id: 'travispollard-com',
      name: 'travispollard.com',
      url: 'https://www.travispollard.com',
      status: 'operational',
      http_code: 200,
      response_time_ms: 46,
      connect_ms: 135,
      cert_days_remaining: 102,
      uptime_percentage_30d: 100,
      daily_history: sampleHistory(8, {}, 45),
    },
    {
      id: 'near-mint-radar',
      name: 'Near Mint Radar',
      url: 'https://nearmintradar.com',
      status: 'degraded',
      http_code: 200,
      response_time_ms: 2155,
      connect_ms: 179,
      cert_days_remaining: 66,
      uptime_percentage_30d: 99.86,
      daily_history: sampleHistory(8, { 0: 'degraded', 3: 'degraded', 11: 'down' }, 160),
    },
    {
      id: 'ncoer-writer',
      name: 'NCOER Writer',
      url: 'https://ncoer.travispollard.com',
      status: 'operational',
      http_code: 200,
      response_time_ms: 173,
      connect_ms: 134,
      cert_days_remaining: 184,
      uptime_percentage_30d: 100,
      daily_history: sampleHistory(8, {}, 170),
    },
    {
      id: 'cfb-forecast',
      name: 'CFB Forecast',
      url: 'https://travispollard.com/cfb',
      status: 'operational',
      http_code: 200,
      response_time_ms: 306,
      connect_ms: 107,
      cert_days_remaining: 102,
      uptime_percentage_30d: 100,
      daily_history: sampleHistory(8, { 17: 'degraded' }, 300),
    },
    {
      id: 'lone-star-ampa',
      name: 'Lone Star AMPA',
      url: 'https://lonestarampa.com',
      status: 'operational',
      http_code: 200,
      response_time_ms: 119,
      connect_ms: 113,
      cert_days_remaining: 87,
      uptime_percentage_30d: 100,
      daily_history: sampleHistory(8, {}, 120),
    },
  ],
};

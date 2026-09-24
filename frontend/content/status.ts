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

export type ServiceCheck = {
  id: string;
  name: string;
  url: string;
  status: ServiceStatus;
  /** Final status after redirects; null when no response came back at all. */
  http_code: number | null;
  /** Time to response headers. Null when the request failed. */
  response_time_ms: number | null;
  /** Days until the TLS certificate expires; null when it could not be read. */
  cert_days_remaining: number | null;
  /** Present only when something went wrong: a short, human-readable reason. */
  error?: string;
};

export type StatusDocument = {
  /** ISO 8601, UTC. When the checker finished this run. */
  last_updated: string;
  overall_status: OverallStatus;
  services: ServiceCheck[];
};

/** A response slower than this is degraded, not operational. */
export const DEGRADED_LATENCY_MS = 1000;

/** A certificate with fewer days than this left is flagged on the page. */
export const CERT_WARNING_DAYS = 14;

/**
 * The checker runs every 10 minutes. A document older than this means the
 * checker itself has stopped -- a status page that goes quietly stale while
 * still showing green is worse than none, so the page says so.
 */
export const STALE_AFTER_MINUTES = 30;

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
  services: [
    {
      id: 'near-mint-radar',
      name: 'Near Mint Radar',
      url: 'https://nearmintradar.com',
      status: 'operational',
      http_code: 200,
      response_time_ms: 142,
      cert_days_remaining: 72,
    },
    {
      id: 'ncoer-writer',
      name: 'NCOER Writer',
      url: 'https://ncoer.travispollard.com',
      status: 'degraded',
      http_code: 200,
      response_time_ms: 1320,
      cert_days_remaining: 65,
    },
    {
      id: 'cfb-forecast',
      name: 'CFB Forecast',
      url: 'https://travispollard.com/cfb',
      status: 'operational',
      http_code: 200,
      response_time_ms: 88,
      cert_days_remaining: 80,
    },
    {
      id: 'lone-star-ampa',
      name: 'Lone Star AMPA',
      url: 'https://lonestarampa.com',
      status: 'operational',
      http_code: 200,
      response_time_ms: 95,
      cert_days_remaining: 110,
    },
  ],
};

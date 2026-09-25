'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import PageIntro from '@/components/PageIntro';
import SiteFooter from '@/components/SiteFooter';
import UptimeBars from '@/components/status/UptimeBars';
import {
  CERT_WARNING_DAYS,
  SAMPLE_STATUS,
  STALE_AFTER_MINUTES,
  type ServiceCheck,
  type ServiceStatus,
  type StatusDocument,
} from '@/content/status';
import { useEffect, useState } from 'react';

/**
 * /status: live checks of the projects this site links to.
 *
 * A static export has no server, so the page fetches /status.json at runtime.
 * The status-checker Lambda rewrites that file every ten minutes; this page
 * polls it every minute so a tab left open keeps up.
 *
 * Four states, and the order of the checks matters:
 *   loading      -- first fetch in flight.
 *   live         -- a real document.
 *   sample       -- `next dev` only, when there is no status.json to fetch.
 *   unavailable  -- production with no document. Never sample data: a status
 *                   page must not present invented results as real ones.
 * A live document older than STALE_AFTER_MINUTES is shown with a warning,
 * because it means the checker has stopped, not that everything is fine.
 */

const POLL_MS = 60_000;
const IS_DEV = process.env.NODE_ENV === 'development';

type State =
  | { kind: 'loading' }
  | { kind: 'live'; doc: StatusDocument }
  | { kind: 'sample'; doc: StatusDocument }
  | { kind: 'unavailable' };

function isStatusDocument(value: unknown): value is StatusDocument {
  const v = value as StatusDocument;
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof v.last_updated === 'string' &&
    typeof v.overall_status === 'string' &&
    Array.isArray(v.services)
  );
}

/** "just now", "4 min ago", "2 h ago". */
function relative(iso: string, now: number): string {
  const minutes = Math.floor((now - Date.parse(iso)) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

const DOT: Record<ServiceStatus, string> = {
  operational: 'bg-success',
  degraded: 'bg-warning',
  down: 'bg-error',
};

const LABEL: Record<ServiceStatus, string> = {
  operational: 'Operational',
  degraded: 'Degraded',
  down: 'Down',
};

/** A status dot. Pulses unless the visitor prefers reduced motion. */
function Dot({ status, size = 'sm' }: { status: ServiceStatus; size?: 'sm' | 'lg' }) {
  const dim = size === 'lg' ? 'h-3 w-3' : 'h-2 w-2';
  return (
    <span aria-hidden="true" className={`relative inline-flex ${dim} shrink-0`}>
      <span
        className={`absolute inline-flex h-full w-full rounded-full opacity-60 motion-safe:animate-ping ${DOT[status]}`}
      />
      <span className={`relative inline-flex ${dim} rounded-full ${DOT[status]}`} />
    </span>
  );
}

function headline(doc: StatusDocument): { text: string; status: ServiceStatus } {
  const down = doc.services.filter((s) => s.status === 'down').length;
  if (doc.overall_status === 'operational') return { text: 'All Systems Operational', status: 'operational' };
  if (doc.overall_status === 'degraded') return { text: 'Degraded Performance', status: 'degraded' };
  return {
    text: down === doc.services.length ? 'Major Outage' : 'Partial Outage',
    status: 'down',
  };
}

function certText(days: number | null): { text: string; warn: boolean } {
  if (days === null) return { text: 'SSL unknown', warn: true };
  if (days < 0) return { text: 'SSL expired', warn: true };
  if (days < CERT_WARNING_DAYS) return { text: `SSL expires in ${days}d`, warn: true };
  return { text: `SSL valid (${days}d remaining)`, warn: false };
}

/** Small uniform pill for the per-service facts. */
function Pill({
  children,
  warn = false,
  title,
}: {
  children: React.ReactNode;
  warn?: boolean;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-xs ${
        warn
          ? 'border-warning/60 text-base-content'
          : 'border-base-300 text-base-content/80 dark:border-white/10'
      }`}
    >
      {children}
    </span>
  );
}

function ServiceCard({ service }: { service: ServiceCheck }) {
  const cert = certText(service.cert_days_remaining);
  return (
    <li className="rounded-xl border border-base-300/70 bg-base-200/30 p-5 dark:border-white/5 dark:bg-white/[0.02]">
      <div className="flex items-start justify-between gap-4">
        <a
          href={service.url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold hover:text-primary"
        >
          {service.name}
          <span aria-hidden="true" className="ml-1.5 text-base-content/70">
            &#8599;
          </span>
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
        <span className="inline-flex items-center gap-2 text-sm">
          <Dot status={service.status} />
          {LABEL[service.status]}
        </span>
      </div>
      <p className="mt-1 truncate font-mono text-xs text-base-content/70">
        {service.url.replace(/^https?:\/\//, '')}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Pill
          warn={service.status === 'degraded'}
          title={
            typeof service.connect_ms === 'number'
              ? `Response ${service.response_time_ms ?? '—'} ms after the request; connection setup (DNS, TCP, TLS) ${service.connect_ms} ms, not counted`
              : undefined
          }
        >
          {service.response_time_ms === null ? 'no response' : `${service.response_time_ms} ms`}
        </Pill>
        <Pill warn={service.http_code === null || service.http_code >= 400}>
          {service.http_code === null ? 'HTTP —' : `HTTP ${service.http_code}`}
        </Pill>
        <Pill warn={cert.warn}>{cert.text}</Pill>
      </div>
      {service.error && <p className="mt-3 text-sm text-base-content/80">{service.error}</p>}
      {service.daily_history && service.daily_history.length > 0 && (
        <UptimeBars days={service.daily_history} uptime={service.uptime_percentage_30d} />
      )}
    </li>
  );
}

export default function Status() {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let alive = true;

    async function load() {
      try {
        const res = await fetch('/status.json', { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body: unknown = await res.json();
        if (!isStatusDocument(body)) throw new Error('unexpected shape');
        if (alive) setState({ kind: 'live', doc: body });
      } catch {
        // Keep showing the last good document if a poll fails; only fall
        // back when there has never been one.
        if (!alive) return;
        setState((prev) =>
          prev.kind === 'live'
            ? prev
            : IS_DEV
              ? { kind: 'sample', doc: SAMPLE_STATUS }
              : { kind: 'unavailable' },
        );
      }
      if (alive) setNow(Date.now());
    }

    load();
    const poll = setInterval(load, POLL_MS);
    const tick = setInterval(() => setNow(Date.now()), 30_000);
    return () => {
      alive = false;
      clearInterval(poll);
      clearInterval(tick);
    };
  }, []);

  const doc = state.kind === 'live' || state.kind === 'sample' ? state.doc : null;
  const head = doc ? headline(doc) : null;
  const stale =
    state.kind === 'live' && now - Date.parse(state.doc.last_updated) > STALE_AFTER_MINUTES * 60_000;

  return (
    <main className="min-h-screen bg-base-100 bg-dot-grid text-base-content">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <HeaderWithTheme />

        <PageIntro
          title="Status"
          lead="Live checks of the projects I run: availability, latency and TLS certificates, every ten minutes."
        />

        {/* Overall banner. aria-live so a screen reader hears a change when a
            poll brings one in. */}
        <section
          aria-live="polite"
          className="mb-10 rounded-xl border border-base-300/70 bg-base-200/40 p-6 dark:border-white/10 dark:bg-white/[0.03]"
        >
          {state.kind === 'loading' && <p className="text-base-content/70">Checking status…</p>}

          {state.kind === 'unavailable' && (
            <>
              <p className="text-lg font-semibold">Status data unavailable</p>
              <p className="mt-1 text-sm text-base-content/70">
                The latest results could not be loaded. This page does not guess: it shows nothing
                rather than a status it cannot back up.
              </p>
            </>
          )}

          {doc && head && (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <Dot status={head.status} size="lg" />
                <p className="text-xl font-semibold tracking-tight">{head.text}</p>
                {state.kind === 'sample' && (
                  <span className="rounded-md border border-warning/60 px-2 py-0.5 text-xs">
                    Sample data (dev only)
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm text-base-content/70">
                {doc.services.length} services &middot; checked{' '}
                <time dateTime={doc.last_updated} title={new Date(doc.last_updated).toUTCString()}>
                  {relative(doc.last_updated, now)}
                </time>
              </p>
              {stale && (
                <p className="mt-3 text-sm">
                  <span className="font-semibold">These results are out of date.</span> The checker
                  runs every ten minutes and has not reported for over {STALE_AFTER_MINUTES} minutes,
                  so the statuses below may no longer be true.
                </p>
              )}
            </>
          )}
        </section>

        {doc && (
          <ul className="mb-16 grid gap-4 sm:grid-cols-2">
            {doc.services.map((service) => (
              <ServiceCard key={service.id} service={service} />
            ))}
          </ul>
        )}

        <details className="group mb-16 rounded-xl border border-base-300/70 bg-base-200/30 p-6 dark:border-white/5 dark:bg-white/[0.02]">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
            How this works
            <span className="text-sm font-normal text-base-content/70">
              <span className="group-open:hidden">show</span>
              <span className="hidden group-open:inline">hide</span>
            </span>
          </summary>
          <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-relaxed text-base-content/80">
            <li>An EventBridge schedule fires every ten minutes.</li>
            <li>
              It invokes a Python Lambda that requests each service, and this site, concurrently,
              following redirects to the final status code and reading the TLS certificate from the
              same connection.
            </li>
            <li>
              Latency is the time from sending the request to receiving the response headers.
              Connection setup (DNS, TCP and the TLS handshake) is timed separately and not counted:
              it measures the checker as much as the site.
            </li>
            <li>
              A service is <em>down</em> on an error or a non-2xx/3xx status, <em>degraded</em> above
              one second, and <em>operational</em> otherwise.
            </li>
            <li>
              Each run is added to 30 days of daily counters. A day is red if any check failed,
              yellow if more than a tenth of its checks were slow, and grey if nothing was checked
              that day. Uptime is the share of all checks in the window that were not down.
            </li>
            <li>
              The Lambda writes the results to <code className="font-mono">status.json</code> in this
              site&apos;s S3 bucket, with a 60-second cache lifetime, and CloudFront serves it.
            </li>
            <li>This page fetches that file on load and again every minute.</li>
            <li>All of it, schedule to permissions, is Terraform in this site&apos;s repository.</li>
          </ol>
          <p className="mt-4 text-sm text-base-content/70">
            Checks run from AWS us-east-1, so latency is measured from Virginia, not from you.
          </p>
        </details>

        <SiteFooter />
      </div>
    </main>
  );
}

import type { DailyEntry, DayStatus } from '@/content/status';

/**
 * Thirty thin bars, one per day, oldest on the left -- the shape GitHub's and
 * Vercel's status pages use. Colour is the day's status; hovering a bar shows
 * its date, status and average latency.
 *
 * A day with no checks is drawn in a darker green than a checked
 * operational day, by the owner's choice, so the row reads as a full month.
 * Its tooltip and the row's accessible summary still say "No data", and it
 * never counts toward the uptime figure, which is computed from real checks
 * only.
 *
 * For assistive tech the row is one image with a summary label ("27 days
 * operational, 1 degraded, ..."). Thirty focusable bars per service would be a
 * hundred and fifty tab stops on this page, so the per-day tooltips are
 * pointer-only and hidden from the accessibility tree.
 *
 * The tooltip is driven by a plain `:hover` selector (the arbitrary variant
 * `[.uptime-bar:hover_&]`), not `group-hover`. Tailwind v4 wraps every hover
 * variant in `@media (hover: hover)`, which a touch screen -- and headless
 * Firefox on the Linux CI runner -- does not match, so the tooltip never
 * appeared there at all. Plain :hover shows it on a mouse as before and on a
 * tap on a phone, where the tapped bar keeps :hover until the next tap.
 */

const BAR: Record<DayStatus, string> = {
  operational: 'bg-success',
  degraded: 'bg-warning',
  down: 'bg-error',
  no_data: 'bg-[color-mix(in_oklab,var(--color-success)_45%,black)]',
};

const WORD: Record<DayStatus, string> = {
  operational: 'Operational',
  degraded: 'Degraded',
  down: 'Down',
  no_data: 'No data',
};

function formatDate(iso: string): string {
  // The dates are UTC calendar days; format them as such, not in local time,
  // or a visitor west of Greenwich sees every bar labelled a day early.
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

function summary(days: DailyEntry[]): string {
  const count = (s: DayStatus) => days.filter((d) => d.status === s).length;
  const parts = [
    `${count('operational')} operational`,
    `${count('degraded')} degraded`,
    `${count('down')} down`,
    `${count('no_data')} with no data`,
  ];
  return `${days.length}-day history: ${parts.join(', ')}.`;
}

export function formatUptime(uptime: number): string {
  return `${uptime === 100 ? '100' : uptime.toFixed(2)}%`;
}

export default function UptimeBars({
  days,
  uptime,
}: {
  days: DailyEntry[];
  uptime: number | null | undefined;
}) {
  return (
    <div className="mt-5">
      <div className="mb-2 flex items-baseline justify-between gap-4">
        <span className="text-xs text-base-content/70">{days.length}-day history</span>
        {typeof uptime === 'number' ? (
          <span className="text-sm font-semibold tabular-nums">
            {formatUptime(uptime)} <span className="font-normal text-base-content/70">uptime</span>
          </span>
        ) : (
          <span className="text-sm text-base-content/70">No data yet</span>
        )}
      </div>

      <div role="img" aria-label={summary(days)} className="flex h-8 gap-[3px]">
        {days.map((day, i) => {
          // Keep the tooltip inside the card at both ends of the row.
          const align =
            i < 5 ? 'left-0' : i > days.length - 6 ? 'right-0' : 'left-1/2 -translate-x-1/2';
          return (
            <div key={day.date} data-status={day.status} className="uptime-bar relative flex-1">
              <div
                className={`h-full rounded-[2px] transition-opacity [.uptime-bar:hover_&]:opacity-70 ${BAR[day.status]}`}
              />
              <div
                aria-hidden="true"
                className={`pointer-events-none absolute bottom-full z-10 mb-2 hidden whitespace-nowrap rounded-md border border-base-300 bg-base-100 px-2.5 py-1.5 text-xs shadow-lg dark:border-white/10 [.uptime-bar:hover_&]:block ${align}`}
              >
                <span className="block font-semibold">{formatDate(day.date)}</span>
                <span className="block text-base-content/80">
                  {WORD[day.status]}
                  {day.avg_latency_ms !== null && <> &middot; avg {day.avg_latency_ms} ms</>}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div
        aria-hidden="true"
        className="mt-1.5 flex justify-between text-[11px] text-base-content/70"
      >
        <span>{days.length - 1} days ago</span>
        <span>Today</span>
      </div>
    </div>
  );
}

'use client';

/**
 * `/cfb/models` -- every system, the same games (SPEC-phase2 6.1).
 *
 * A different question from `/cfb/accuracy`, which is why it is a different
 * route. That page is one model's record over time; this one is a
 * systems-by-metric matrix on a single set of games, plus the per-week series.
 * §6.1 forbids duplicating this into the accuracy page: two places to keep
 * correct is one place to be wrong.
 *
 * **The shared denominator is the whole page, not a footnote** (§6.3). Every
 * system covers a different subset -- the market prices some of the slate,
 * Sagarin's page covers a different set again -- and a leaderboard is a
 * comparison *between rows*, so two rows on different denominators are not
 * comparable at all while a table puts them side by side implying they are. The
 * headline figures are computed on the intersection, the count is stated above
 * the table, and each row carries its own coverage so a system that priced all
 * of them and one that priced a third are visibly different things.
 *
 * The page does no arithmetic. Every number here was computed by the generator.
 */

import CfbNav from '@/components/cfb/CfbNav';
import { DocumentPlaceholder } from '@/components/cfb/DocumentState';
import {
  MODELS_SCHEMA_VERSIONS,
  ModelsDocument,
  SystemRow,
} from '@/components/cfb/contract';
import { formatGeneratedAt, formatMean, formatWeek } from '@/components/cfb/format';
import { useCfbDocument } from '@/components/cfb/useCfbDocument';

export default function ModelsPage() {
  const state = useCfbDocument<ModelsDocument>('models.json', MODELS_SCHEMA_VERSIONS);

  return (
    <main className="px-6 py-10 sm:px-10">
      <div className="max-w-4xl mx-auto">
        <CfbNav />

        <h1 className="text-2xl font-bold mb-1">Model comparison</h1>
        <p className="text-base-content/70 mb-8">
          This model against the market and Sagarin&apos;s PREDICTOR, on the games all three
          priced. Systems that cover different slates are not comparable, so the table is
          computed on the overlap rather than on each system&apos;s own best set.
        </p>

        {state.status !== 'ready' ? (
          <DocumentPlaceholder state={state} what="the model comparison" />
        ) : (
          <Models document={state.document} />
        )}
      </div>
    </main>
  );
}

function Models({ document }: { document: ModelsDocument }) {
  if (document.through_week === null) {
    // Legal and expected before the season's first Sunday. §6.2 publishes the
    // document rather than refusing, so the page has to draw the empty state.
    return (
      <div className="space-y-6">
        <div className="alert max-w-2xl">
          <span>
            No week has been scored yet. The comparison starts after the first Sunday scoring
            run of the {document.season} season.
          </span>
        </div>
        <Generated document={document} />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <p className="text-sm text-base-content/70">
        Through week {formatWeek(document.through_week)}, on{' '}
        <strong>{document.shared_denominator.games}</strong>{' '}
        {document.shared_denominator.description}.
      </p>

      <Leaderboard systems={document.systems} />
      <ByWeek document={document} />
      <Generated document={document} />
    </div>
  );
}

function Leaderboard({ systems }: { systems: SystemRow[] }) {
  return (
    <section>
      <h2 className="text-lg font-semibold mb-3">On the shared games</h2>
      <div className="overflow-x-auto">
        <table className="table table-sm">
          <thead>
            <tr>
              <th>System</th>
              <th className="text-right">MAE</th>
              <th className="text-right">Brier</th>
              <th className="text-right">Against the spread</th>
              <th className="text-right">Priced</th>
            </tr>
          </thead>
          <tbody>
            {systems.map((system) => (
              <tr key={system.id} className={system.is_ours ? 'font-semibold' : undefined}>
                <td>
                  {system.label}
                  {system.is_benchmark ? (
                    <span className="ml-2 badge badge-ghost badge-sm">benchmark</span>
                  ) : null}
                </td>
                <td className="text-right tabular-nums">{formatMean(system.mae)}</td>
                {/*
                  An em dash, never a zero. A system with no win probability has
                  not scored 0.000 at anything -- SPEC-phase1 5.3's rule about
                  nulls, which is why `formatMean` exists rather than `?? 0`.
                */}
                <td className="text-right tabular-nums">{formatMean(system.brier, 3)}</td>
                <td className="text-right tabular-nums">
                  {system.ats ? (
                    <>
                      {system.ats.record}
                      <span className="ml-1 text-base-content/50 text-xs">
                        ({system.ats.wins + system.ats.losses + system.ats.pushes} priced)
                      </span>
                    </>
                  ) : (
                    <span className="text-base-content/40">—</span>
                  )}
                </td>
                <td className="text-right tabular-nums text-base-content/70">
                  {system.coverage.priced} of {system.coverage.of}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-base-content/60 max-w-2xl">
        Lower is better for both. <strong>MAE</strong> is the average error in points of
        predicted margin; <strong>Brier</strong> scores the win probability, which only this
        model publishes — a point spread is not a probability, so the benchmarks have no column
        rather than a derived one. <strong>Priced</strong> is how much of the scored season each
        system covered; the MAE column is the overlap, so a row can have priced far more games
        than its figure is computed on.
      </p>
    </section>
  );
}

function ByWeek({ document }: { document: ModelsDocument }) {
  if (document.by_week.length === 0) return null;

  const ids = document.systems.map((system) => system.id);
  const labels = new Map(document.systems.map((system) => [system.id, system.label]));

  return (
    <section>
      <h2 className="text-lg font-semibold mb-3">Week by week</h2>
      <div className="overflow-x-auto">
        <table className="table table-sm">
          <thead>
            <tr>
              <th>Week</th>
              {ids.map((id) => (
                <th key={id} className="text-right">
                  {labels.get(id)}
                </th>
              ))}
              <th className="text-right">Shared games</th>
            </tr>
          </thead>
          <tbody>
            {document.by_week.map((week) => (
              <tr key={week.week}>
                <td>{formatWeek(week.week)}</td>
                {ids.map((id) => (
                  <td key={id} className="text-right tabular-nums">
                    {formatMean(week.mae[id] ?? null)}
                  </td>
                ))}
                <td className="text-right tabular-nums text-base-content/70">{week.games}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-base-content/60 max-w-2xl">
        Each week is computed on its own overlap, not the season&apos;s. A week where fewer
        games carried a line has a smaller shared set, and narrowing the week is the only way
        to keep its row comparable across systems.
      </p>
    </section>
  );
}

function Generated({ document }: { document: ModelsDocument }) {
  return (
    <p className="text-xs text-base-content/50">
      Generated {formatGeneratedAt(document.generated_at)}.
    </p>
  );
}

'use client';

/**
 * `/cfb/accuracy` -- how the model has actually done (SPEC-phase1 6.4).
 *
 * One fetch of `accuracy.json` and a render. Every figure here was computed by
 * the pipeline over the union of the scored rows; the page does no averaging of
 * its own, because a mean of the weekly means would weight a three-game Tuesday
 * equally with a sixty-game Saturday.
 *
 * **Two rules from the pipeline survive to this page or they were pointless.**
 * A `null` mean prints as an em dash and never as a zero (§5.3), and every
 * record shows the sample size its denominator actually is (§5.3 again) --
 * because a bare "2-2" cannot distinguish four priced games from forty where
 * thirty-six had no line.
 */

import CfbNav from '@/components/cfb/CfbNav';
import { DocumentPlaceholder } from '@/components/cfb/DocumentState';
import { AccuracyDocument, Backtest, Record, SeedDisclosure } from '@/components/cfb/contract';
import {
  formatCorrelation,
  formatGeneratedAt,
  formatMean,
  formatWeek,
} from '@/components/cfb/format';
import { useCfbDocument } from '@/components/cfb/useCfbDocument';

export default function AccuracyPage() {
  const state = useCfbDocument<AccuracyDocument>('accuracy.json');

  return (
    <main className="px-6 py-10 sm:px-10">
      <div className="max-w-4xl mx-auto">
        <CfbNav />

        <h1 className="text-2xl font-bold mb-1">Model accuracy</h1>
        <p className="text-base-content/70 mb-8">
          Every prediction is written before kickoff and scored against the result on Sunday.
          Nothing is dropped: a game that cannot be joined to its prediction fails the run rather
          than quietly leaving the averages.
        </p>

        {state.status !== 'ready' ? (
          <DocumentPlaceholder state={state} what="the accuracy record" />
        ) : (
          <Accuracy document={state.document} />
        )}
      </div>
    </main>
  );
}

function Accuracy({ document }: { document: AccuracyDocument }) {
  if (document.through_week === null) {
    // Legal and expected: the Friday before the season's first Sunday. §6.4
    // publishes this document rather than refusing, so the page has to draw it.
    return (
      <div className="space-y-6">
        <div className="alert max-w-2xl">
          <p>
            No games have been scored yet this season. Figures appear here the first Sunday after
            kickoff.
          </p>
        </div>
        <Disclosure disclosure={document.seed_disclosure} />
        {document.backtest && <BacktestSection backtest={document.backtest} />}
        <GeneratedAt document={document} />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-xl font-semibold mb-3">
          Season to date, through {formatWeek(document.through_week).toLowerCase()}
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          <RecordCard title="Texas" record={document.texas} />
          <RecordCard title="Full slate" record={document.full_slate} />
        </div>
      </section>

      <Disclosure disclosure={document.seed_disclosure} />

      <section>
        <h2 className="text-xl font-semibold mb-3">By week</h2>
        <div className="overflow-x-auto">
          <table className="table table-zebra">
            <thead>
              <tr>
                <th>Week</th>
                <th className="text-right">Games</th>
                <th className="text-right">MAE</th>
                <th className="text-right">Correlation vs Sagarin</th>
              </tr>
            </thead>
            <tbody>
              {document.by_week.map((point) => (
                <tr key={point.week}>
                  <td>{formatWeek(point.week)}</td>
                  <td className="text-right tabular-nums">{point.games}</td>
                  <td className="text-right tabular-nums">{formatMean(point.mae)}</td>
                  <td className="text-right tabular-nums">
                    {formatCorrelation(point.sagarin_r)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-1">Calibration</h2>
        <p className="text-sm text-base-content/70 mb-3">
          When the model says 70%, does it happen 70% of the time? Each row carries its sample
          size, because a point resting on two games looks exactly like one resting on two hundred.
        </p>
        {document.calibration.length === 0 ? (
          <p className="text-base-content/60">Not enough games yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="table table-zebra">
              <thead>
                <tr>
                  <th>Predicted band</th>
                  <th className="text-right">Mean predicted</th>
                  <th className="text-right">Observed</th>
                  <th className="text-right">n</th>
                </tr>
              </thead>
              <tbody>
                {document.calibration.map((bucket) => (
                  <tr key={bucket.label}>
                    <td>{bucket.label}</td>
                    <td className="text-right tabular-nums">
                      {(bucket.predicted * 100).toFixed(1)}%
                    </td>
                    <td className="text-right tabular-nums">
                      {(bucket.observed * 100).toFixed(1)}%
                    </td>
                    <td className="text-right tabular-nums">{bucket.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {document.backtest && <BacktestSection backtest={document.backtest} />}

      <GeneratedAt document={document} />
    </div>
  );
}

function BacktestSection({ backtest }: { backtest: Backtest }) {
  return (
    <section className="border border-warning/40 rounded-box p-4 sm:p-6 bg-warning/5">
      <h2 className="text-xl font-semibold mb-1">
        Backtest
        <span className="badge badge-warning badge-sm ml-2 align-middle">not a prediction</span>
      </h2>
      <p className="text-sm text-base-content/70 mb-4">
        These weeks were scored <em>after</em> their games were played, because the model was not
        running yet. They are kept out of every figure above.
        {backtest.measures_the_seed && (
          <>
            {' '}
            <strong>And they measure something other than this model.</strong> A week 1 forecast is
            arithmetically identical to Sagarin&rsquo;s preseason predictor — the ratings are seeded
            from that page and nothing has updated them yet — so what is below is the accuracy of
            Sagarin&rsquo;s preseason page, not of the Elo model.
          </>
        )}
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <RecordCard title="Texas (backtest)" record={backtest.texas} />
        <RecordCard title="Full slate (backtest)" record={backtest.full_slate} />
      </div>

      <table className="table table-sm mt-4">
        <thead>
          <tr>
            <th>Week</th>
            <th className="text-right">Games</th>
            <th className="text-right">MAE</th>
            <th className="text-right">Correlation vs Sagarin</th>
          </tr>
        </thead>
        <tbody>
          {backtest.by_week.map((point) => (
            <tr key={point.week}>
              <td>{formatWeek(point.week)}</td>
              <td className="text-right tabular-nums">{point.games}</td>
              <td className="text-right tabular-nums">{formatMean(point.mae)}</td>
              <td className="text-right tabular-nums">{formatCorrelation(point.sagarin_r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RecordCard({ title, record }: { title: string; record: Record }) {
  return (
    <div className="card bg-base-200 shadow-sm">
      <div className="card-body">
        <h3 className="card-title text-lg">
          {title}
          <span className="badge badge-ghost">{record.games} games</span>
        </h3>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm mt-2">
          <dt className="text-base-content/70">Mean absolute error</dt>
          <dd className="text-right tabular-nums font-medium">{formatMean(record.mae)}</dd>

          <dt className="text-base-content/70">Brier score</dt>
          <dd className="text-right tabular-nums font-medium">{formatMean(record.brier, 3)}</dd>

          {/* Each benchmark carries its own denominator: the market prices a
              subset of the slate and Sagarin's page covers a different subset,
              so a shared "games" number would flatter whichever is smaller. */}
          <dt className="text-base-content/70">
            Market line MAE
            <span className="opacity-60"> ({record.line_games} priced)</span>
          </dt>
          <dd className="text-right tabular-nums font-medium">{formatMean(record.line_mae)}</dd>

          <dt className="text-base-content/70">
            Sagarin MAE
            <span className="opacity-60"> ({record.sagarin_games} rated)</span>
          </dt>
          <dd className="text-right tabular-nums font-medium">{formatMean(record.sagarin_mae)}</dd>

          <dt className="text-base-content/70">Against the spread</dt>
          <dd className="text-right tabular-nums font-medium">{record.ats.record}</dd>
        </dl>

        {/* The exclusions are the point of the ATS record, not a footnote:
            they are what makes the win-loss line checkable against the slate. */}
        <p className="text-xs text-base-content/60 mt-2">
          {record.ats.wins + record.ats.losses + record.ats.pushes} of {record.games} games priced
          with an edge
          {record.ats.excluded_no_line > 0 && `; ${record.ats.excluded_no_line} had no line`}
          {record.ats.excluded_no_edge > 0 && `; ${record.ats.excluded_no_edge} had no edge`}.
        </p>
      </div>
    </div>
  );
}

function Disclosure({ disclosure }: { disclosure: SeedDisclosure }) {
  return (
    <div className={`alert ${disclosure.active ? 'alert-info' : ''} max-w-3xl`}>
      <div>
        <h2 className="font-semibold">
          {disclosure.active
            ? 'These ratings still reflect their preseason seed'
            : 'The ratings have separated from their preseason seed'}
        </h2>
        <p className="text-sm opacity-90">
          The model is seeded from Sagarin&rsquo;s preseason ratings, so early-season predictions
          are close to restatements of that page rather than independent forecasts. The
          correlation with Sagarin&rsquo;s per-game predictions is{' '}
          <span className="font-mono">{formatCorrelation(disclosure.current_r)}</span>
          {disclosure.active ? (
            <>
              , above the {disclosure.threshold} threshold where this notice retires.
            </>
          ) : (
            <>
              . It first fell below {disclosure.threshold} in{' '}
              {formatWeek(disclosure.retired_week ?? '').toLowerCase()}, so results from then on
              are the model&rsquo;s own.
            </>
          )}
        </p>
      </div>
    </div>
  );
}

function GeneratedAt({ document }: { document: AccuracyDocument }) {
  return (
    <p className="text-xs text-base-content/50">
      Published {formatGeneratedAt(document.generated_at)} &middot; season {document.season}
    </p>
  );
}

'use client';

/**
 * `/cfb` -- the next game (SPEC-phase1 6.3).
 *
 * One fetch of `next-game.json` and a render. No joining, no second request, no
 * arithmetic beyond formatting: §6.1 makes each route exactly one fetch and the
 * PRD forbids prediction logic living in the site.
 */

import HeaderWithTheme from '@/components/HeaderWithTheme';
import Link from 'next/link';

import { DocumentPlaceholder } from '@/components/cfb/DocumentState';
import { NextGameDocument } from '@/components/cfb/contract';
import {
  formatGeneratedAt,
  formatKickoff,
  formatLine,
  formatMargin,
  formatProbability,
  formatWeek,
} from '@/components/cfb/format';
import { useCfbDocument } from '@/components/cfb/useCfbDocument';

export default function CfbPage() {
  const state = useCfbDocument<NextGameDocument>('next-game.json');

  return (
    <main className="min-h-screen bg-base-100 text-base-content px-6 py-10 sm:px-10">
      <div className="max-w-3xl mx-auto">
        <HeaderWithTheme />

        <h1 className="text-3xl font-bold mb-1">Texas football forecast</h1>
        <p className="text-base-content/70 mb-8">
          An Elo model, seeded from preseason ratings and updated each week from results. Every
          prediction is written to immutable storage before kickoff.{' '}
          <Link href="/cfb/accuracy" className="link link-primary">
            See how it has done
          </Link>
          , or{' '}
          <Link href="/cfb/slate" className="link link-primary">
            the whole slate
          </Link>
          .
        </p>

        {state.status !== 'ready' ? (
          <DocumentPlaceholder state={state} what="this week&rsquo;s forecast" />
        ) : (
          <NextGame document={state.document} />
        )}
      </div>
    </main>
  );
}

function NextGame({ document }: { document: NextGameDocument }) {
  const { game, as_of: asOf } = document;

  return (
    <div className="space-y-6">
      <div className="card bg-base-200 shadow-sm">
        <div className="card-body">
          {game === null ? (
            // A bye is a fact, not an absence. §6.3: the document says so
            // explicitly rather than leaving the page to infer it from a gap.
            <>
              <h2 className="card-title">{document.team} is on a bye</h2>
              <p className="text-base-content/70">
                No game on the {formatWeek(document.week)} slate. The ratings below are still
                current.
              </p>
            </>
          ) : (
            <>
              <div className="text-sm uppercase tracking-wide text-base-content/60">
                {formatWeek(document.week)} &middot; {formatKickoff(game.kickoff)}
              </div>
              <h2 className="card-title text-2xl">
                {document.team} {game.home ? 'vs' : 'at'} {game.opponent}
              </h2>

              <div className="stats stats-vertical sm:stats-horizontal bg-base-100 mt-3">
                <div className="stat">
                  <div className="stat-title">Predicted margin</div>
                  <div className="stat-value text-3xl">{formatMargin(game.predicted_margin)}</div>
                  <div className="stat-desc">for {document.team}</div>
                </div>
                <div className="stat">
                  <div className="stat-title">Win probability</div>
                  <div className="stat-value text-3xl">
                    {formatProbability(game.win_probability)}
                  </div>
                  <div className="stat-desc">
                    {/* §3.7. The model is never certain and the page never says it is. */}
                    never 0% or 100%
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Market line</div>
                  <div className="stat-value text-3xl">{formatLine(game.market_line)}</div>
                  <div className="stat-desc">
                    {game.line_source
                      ? // The book is named because the number is its quote, and
                        // because the sign convention is the book's, not ours.
                        `${game.line_source}, home team's line`
                      : 'no book priced this game'}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="card bg-base-200 shadow-sm">
        <div className="card-body">
          <h2 className="card-title text-lg">Ratings this forecast was made from</h2>
          <div className="stats stats-vertical sm:stats-horizontal bg-base-100">
            <div className="stat">
              <div className="stat-title">Elo</div>
              <div className="stat-value text-2xl">{Math.round(asOf.elo)}</div>
              <div className="stat-desc">after {formatWeek(asOf.week).toLowerCase()}</div>
            </div>
            <div className="stat">
              <div className="stat-title">National rank</div>
              <div className="stat-value text-2xl">#{asOf.national_rank}</div>
              <div className="stat-desc">of {asOf.fbs_teams} FBS teams</div>
            </div>
          </div>
        </div>
      </div>

      <p className="text-xs text-base-content/50">
        Published {formatGeneratedAt(document.generated_at)} &middot; season {document.season}
      </p>
    </div>
  );
}

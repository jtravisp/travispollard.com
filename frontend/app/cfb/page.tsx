'use client';

/**
 * `/cfb` -- the next game (SPEC-phase1 6.3).
 *
 * One fetch of `next-game.json` and a render. No joining, no second request, no
 * arithmetic beyond formatting: §6.1 makes each route exactly one fetch and the
 * PRD forbids prediction logic living in the site.
 *
 * **Every number here names the team it is about.** The first version printed
 * "-2.2 for Texas", a bare "41%", and "Market line -1.5, home team's line" --
 * which asked a reader to hold three conventions at once, two of them running in
 * opposite directions: a model margin is positive for the team it favours and a
 * market line is negative for the team it favours (§4.3). Now the page says
 * "Ohio State by 2.2" and "Texas by 1.5", with the raw quote kept as a footnote
 * for anyone checking it against the book.
 */

import Link from 'next/link';

import CfbNav from '@/components/cfb/CfbNav';
import RatingChart, { MINIMUM_POINTS } from '@/components/cfb/RatingChart';
import { DocumentPlaceholder } from '@/components/cfb/DocumentState';
import { LastResult, NextGameDocument } from '@/components/cfb/contract';
import {
  describeFavorite,
  favorite,
  formatGeneratedAt,
  formatKickoff,
  formatLine,
  formatMargin,
  formatProbability,
  formatWeek,
  marketFavorite,
} from '@/components/cfb/format';
import { useCfbDocument } from '@/components/cfb/useCfbDocument';

export default function CfbPage() {
  const state = useCfbDocument<NextGameDocument>('next-game.json');

  return (
    <main className="px-6 py-10 sm:px-10">
      <div className="max-w-3xl mx-auto">
        <CfbNav />

        <p className="text-base-content/70 mb-8">
          An Elo model, seeded from preseason ratings and updated each week from results. Every
          prediction is written to immutable storage before kickoff, then scored against what
          actually happened.
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
  const { game, as_of: asOf, team } = document;

  if (game === null) {
    // A bye is a fact, not an absence. §6.3: the document says so explicitly
    // rather than leaving the page to infer it from a gap.
    return (
      <div className="space-y-6">
        <div className="card bg-base-200">
          <div className="card-body">
            <h2 className="card-title">{team} is on a bye</h2>
            <p className="text-base-content/70">
              No game on the {formatWeek(document.week)} slate. The ratings below are still
              current, and{' '}
              <Link href="/cfb/slate" className="link link-primary">
                the rest of the slate
              </Link>{' '}
              is still forecast.
            </p>
          </div>
        </div>
        <Ratings asOf={asOf} team={team} />
        <Published document={document} />
      </div>
    );
  }

  // `next-game.json` is subject-team perspective (§6.3), so home and away are
  // reconstructed before anything home-signed -- the market line -- is read.
  const opponent = game.opponent;
  const home = game.home ? team : opponent;
  const away = game.home ? opponent : team;

  const model = favorite(game.predicted_margin, team, opponent);
  const market = marketFavorite(game.market_line, home, away);
  const disagree = model !== null && market !== null && model.team !== market.team;

  return (
    <div className="space-y-6">
      <div className="card bg-base-200">
        <div className="card-body">
          <div className="text-sm uppercase tracking-wide text-base-content/60">
            {formatWeek(game.week)} &middot; {formatKickoff(game.kickoff)}
          </div>
          <h2 className="card-title text-2xl">
            {away} <span className="text-base-content/50 font-normal">at</span> {home}
          </h2>
          <p className="text-sm text-base-content/60">
            {game.neutral_site
              ? `Neutral site — ${home} is nominally the home team.`
              : `${home} is at home.`}
            {/* A margin is not legible without the opponent's standing: "Texas by
                39.3" reads differently against the 5th team and the 81st. */}
            {game.opponent_rank != null && (
              <> {game.opponent} is #{game.opponent_rank} of {asOf.fbs_teams}.</>
            )}
            {game.opponent_rank == null && game.opponent_elo != null && (
              <> {game.opponent} is outside the FBS, so it has no national rank.</>
            )}
          </p>

          <div className="grid gap-3 sm:grid-cols-3 mt-4">
            <Figure
              label="Model picks"
              value={describeFavorite(model, 'dead even')}
              note={`the model's margin, from ${team}'s side`}
              emphasis
            />
            <Figure
              label={`${team} win probability`}
              value={formatProbability(game.win_probability)}
              note={`chance ${team} wins outright`}
            />
            <Figure
              label="Market says"
              value={market === null ? 'No line yet' : describeFavorite(market)}
              note={
                market === null
                  ? 'no book has priced this game'
                  : `${game.line_source} · quoted ${formatLine(game.market_line)} on ${home}`
              }
            />
          </div>

          {disagree && (
            <div className="alert alert-warning mt-4">
              <p className="text-sm">
                <strong>The model and the market disagree.</strong> The model likes {model.team}{' '}
                by {model.points.toFixed(1)}; the book has {market.team} by{' '}
                {market.points.toFixed(1)}.
              </p>
            </div>
          )}
        </div>
      </div>

      {document.last_result && (
        <LastGame result={document.last_result} team={team} />
      )}
      <Ratings asOf={asOf} team={team} history={document.history} />
      <Published document={document} />
    </div>
  );
}

function LastGame({ result, team }: { result: LastResult; team: string }) {
  // The scoreline is nullable: weeks graded before the points were carried
  // through are in the archive and cannot gain them.
  const scoreline =
    result.team_points != null && result.opponent_points != null
      ? `${team} ${result.team_points}, ${result.opponent} ${result.opponent_points}`
      : `${team} ${result.won ? 'won' : 'lost'} by ${Math.abs(result.actual_margin)}`;

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <div className="text-sm uppercase tracking-wide text-base-content/60">
          {formatWeek(result.week)} · last result
        </div>
        <h2 className="card-title text-xl">
          {scoreline}
          <span
            className={`badge badge-sm ${result.won ? 'badge-success' : 'badge-error'}`}
          >
            {result.won ? 'W' : 'L'}
          </span>
        </h2>
        <p className="text-sm text-base-content/70">
          {/* The accountability claim, made concrete. Everything else on this
              page is a forecast; this is the line that says how far off it was. */}
          The model said {team} by {formatMargin(result.predicted_margin)} and the game
          finished {formatMargin(result.actual_margin)} — off by{' '}
          {Math.abs(result.error).toFixed(1)} points.
          {result.beat_market === true && ' It beat the closing number.'}
          {result.beat_market === false && ' It lost to the closing number.'}
          {result.beat_market === null && ' There was no line to beat.'}
        </p>
      </div>
    </div>
  );
}

function Figure({
  label,
  value,
  note,
  emphasis = false,
}: {
  label: string;
  value: string;
  note: string;
  emphasis?: boolean;
}) {
  const muted = emphasis ? 'opacity-80' : 'text-base-content/60';
  return (
    <div
      className={`rounded-box p-4 ${emphasis ? 'bg-primary text-primary-content' : 'bg-base-100'}`}
    >
      <div className={`text-xs uppercase tracking-wide ${muted}`}>{label}</div>
      <div className="text-xl font-semibold mt-1">{value}</div>
      <div className={`text-xs mt-1 ${muted}`}>{note}</div>
    </div>
  );
}

function Ratings({
  asOf,
  team,
  history,
}: {
  asOf: NextGameDocument['as_of'];
  team: string;
  // Optional, not merely possibly-empty: a document published before this field
  // existed has no `history` key at all, and `.length` on undefined throws.
  history?: NextGameDocument['history'];
}) {
  const points = history ?? [];

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <h2 className="card-title text-lg">Ratings this forecast was made from</h2>
        <div className="flex flex-wrap gap-8">
          <div>
            <div className="text-xs uppercase tracking-wide text-base-content/60">
              {team} Elo
            </div>
            <div className="text-2xl font-semibold">{Math.round(asOf.elo)}</div>
            <div className="text-xs text-base-content/60">
              after {formatWeek(asOf.week).toLowerCase()}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-base-content/60">
              National rank
            </div>
            <div className="text-2xl font-semibold">#{asOf.national_rank}</div>
            <div className="text-xs text-base-content/60">of {asOf.fbs_teams} FBS teams</div>
          </div>
        </div>

        {points.length >= MINIMUM_POINTS ? (
          <div className="mt-4">
            <RatingChart history={points} />
            <p className="text-xs text-base-content/60 mt-1">
              {points.length} week{points.length === 1 ? '' : 's'} of the season.
              {points.length < 4 &&
                ' Too few to read as a trend yet — it is a record, not a shape.'}
            </p>
          </div>
        ) : (
          // A line through one point is indistinguishable from a broken chart,
          // and the first weekly state does not land until 2026-09-13.
          <p className="text-xs text-base-content/60 mt-3">
            The rating history appears here once the season has been scored for the
            first time. Until then this is the preseason seed.
          </p>
        )}
      </div>
    </div>
  );
}

function Published({ document }: { document: NextGameDocument }) {
  return (
    <p className="text-xs text-base-content/50">
      Published {formatGeneratedAt(document.generated_at)} &middot; season {document.season}{' '}
      &middot; win probabilities are capped at 1% and 99%, because a model that prints a certainty
      has no way to have been right.
    </p>
  );
}

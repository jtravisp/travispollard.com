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
import { LastResult, NextGameDocument, SeasonSoFar } from '@/components/cfb/contract';
import { SeedDisclosure } from '@/components/cfb/contract';
import {
  describeFavorite,
  edgeOver,
  favorite,
  formatGeneratedAt,
  formatKickoff,
  formatLine,
  formatMargin,
  formatMean,
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
  // The one number that distinguishes this page from a scoreboard: a 99% win
  // probability reads the same whether the model is right or badly wrong, but
  // the gap to a book pricing the same game is a claim the record settles.
  const edge = edgeOver(game.predicted_margin, game.market_line, game.home);

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
          {/* Venue only. The opponent's standing is context for the margin and
              belongs beside the margin, not in the sentence about the stadium. */}
          <p className="text-sm text-base-content/60">
            {game.neutral_site
              ? `Neutral site — ${home} is nominally the home team.`
              : `${home} is at home.`}
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

          {/* (1) The edge. Shown whenever a book has priced the game, not only
              when the two disagree about the winner -- most of the information is
              in games where they agree on the side and differ on the number. */}
          {edge !== null && (
            <div className="rounded-box bg-base-100 p-4 mt-3">
              <div className="text-xs uppercase tracking-wide text-base-content/60">
                The model&rsquo;s edge
              </div>
              <div className="text-xl font-semibold mt-1">
                {Math.abs(edge) < 0.05
                  ? 'The model and the market agree'
                  : `${Math.abs(edge).toFixed(1)} points ${edge > 0 ? 'higher' : 'lower'} on ${team}`}
              </div>
              <div className="text-xs text-base-content/60 mt-1">
                the model says {describeFavorite(model, 'dead even')}, the market says{' '}
                {describeFavorite(market)} — this gap is what the{' '}
                <Link href="/cfb/accuracy" className="link">
                  accuracy record
                </Link>{' '}
                settles over a season
              </div>
            </div>
          )}

          {/* (1) Beside the edge, not in a footnote. While this is active the
              "edge" above is Sagarin's preseason opinion against a book rather
              than this model against one -- which changes what the number means,
              so it belongs where the number is. */}
          {document.seed_disclosure?.active && edge !== null && (
            <p className="text-xs text-base-content/70 mt-2">
              <strong>Read that edge carefully.</strong> The ratings are still seeded from
              Sagarin&rsquo;s preseason numbers, so an early-season forecast is close to a
              restatement of his — which makes this a gap between <em>his</em> opinion and the
              book&rsquo;s, more than between this model&rsquo;s and the book&rsquo;s. It stops
              being true as results move the ratings, and this note retires itself when they have.
            </p>
          )}
          {document.seed_disclosure && !document.seed_disclosure.active && (
            <p className="text-xs text-base-content/70 mt-2">
              The ratings separated from their preseason seed in{' '}
              {formatWeek(document.seed_disclosure.retired_week ?? '').toLowerCase()}, so this is
              the model&rsquo;s own disagreement with the market.
            </p>
          )}

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

      <HowItIsDoing record={document.season_so_far} />
      {document.last_result && (
        <LastGame result={document.last_result} team={team} />
      )}
      <Ratings
        asOf={asOf}
        team={team}
        history={document.history}
        opponentName={game.opponent}
        opponentElo={game.opponent_elo}
        opponentRank={game.opponent_model_rank}
      />
      <Published document={document} />
    </div>
  );
}

function HowItIsDoing({ record }: { record?: SeasonSoFar | null }) {
  /**
   * (4) The strongest sentence this project can put on its front page, because
   * it is the claim the whole thing makes. It lights up on its own: the first
   * scoring run is 2026-09-13, and until then this renders the empty state
   * rather than being absent, so a reader knows the record exists and is coming.
   */
  const scored = record && record.through_week !== null;

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <h2 className="card-title text-lg">How the model is doing</h2>
        {scored ? (
          <p className="text-sm">
            Through {formatWeek(record.through_week!).toLowerCase()}, over{' '}
            {record.full_slate.games} games: the model&rsquo;s predictions miss by{' '}
            <strong>{formatMean(record.full_slate.mae)}</strong> points on average
            {record.full_slate.line_mae !== null && (
              <>
                , against the betting market&rsquo;s{' '}
                <strong>{formatMean(record.full_slate.line_mae)}</strong> over the{' '}
                {record.full_slate.line_games} games a book priced
              </>
            )}
            .{' '}
            <Link href="/cfb/accuracy" className="link link-primary">
              The full record
            </Link>
            .
          </p>
        ) : (
          <p className="text-sm text-base-content/70">
            No games have been scored yet. Every prediction is written before kickoff and graded
            against the result on Sunday, so this fills in from the first scored week onward —{' '}
            <Link href="/cfb/accuracy" className="link link-primary">
              the record
            </Link>{' '}
            is empty and will not be quietly backfilled.
          </p>
        )}
      </div>
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

/** 81 -> "81st". Reads better than "#81" inside a sentence. */
function ordinal(value: number): string {
  const rest = value % 100;
  if (rest >= 11 && rest <= 13) return `${value}th`;
  return `${value}${['th', 'st', 'nd', 'rd'][value % 10] ?? 'th'}`;
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
  opponentName,
  opponentElo,
  opponentRank,
}: {
  asOf: NextGameDocument['as_of'];
  team: string;
  opponentName?: string;
  opponentElo?: number | null;
  opponentRank?: number | null;
  // Optional, not merely possibly-empty: a document published before this field
  // existed has no `history` key at all, and `.length` on undefined throws.
  history?: NextGameDocument['history'];
}) {
  const points = history ?? [];
  const gap =
    opponentElo != null ? Math.abs(Math.round(asOf.elo - opponentElo)) : null;

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <h2 className="card-title text-lg">Ratings this forecast was made from</h2>
        {/* (5) "2113" and "a 738-point gap" mean nothing to a football fan.
            The worked example uses this game's own gap rather than a fixed
            number, which would be wrong the moment the opponent changed. */}
        <p className="text-xs text-base-content/60 -mt-1 mb-2">
          An Elo rating is a single number for how strong a team is, and only the gap between two
          of them means anything. Twenty points of Elo is about one point of predicted margin
          {gap != null && (
            <>
              , so this {gap}-point gap is roughly {Math.round(gap / 20)} points before home
              advantage
            </>
          )}
          .
        </p>
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
            {/* Never a bare "#5". A reader on a college football page assumes AP
                unless told otherwise, and this model disagrees with AP visibly. */}
            <div className="text-xs uppercase tracking-wide text-base-content/60">
              Elo rank
            </div>
            <div className="text-2xl font-semibold">#{asOf.model_rank}</div>
            <div className="text-xs text-base-content/60">
              of {asOf.fbs_teams} FBS teams, by this model
            </div>
          </div>
          {/* (2) Without the opponent's rating the arithmetic is not
              reconstructible, and the whole premise is that it is visible:
              the margin is the gap between these two, over 20, plus HFA. */}
          {opponentElo != null && (
            <div>
              <div className="text-xs uppercase tracking-wide text-base-content/60">
                {opponentName} Elo
              </div>
              <div className="text-2xl font-semibold">{Math.round(opponentElo)}</div>
              <div className="text-xs text-base-content/60">
                {/* The opponent's standing belongs with the opponent's rating,
                    beside the gap it explains -- not inside the card showing the
                    margin, where it read as a footnote to the wrong number. */}
                {opponentRank != null
                  ? `${ordinal(opponentRank)} of ${asOf.fbs_teams} by this model`
                  : 'outside the FBS, so this model does not rank it'}
                {' · '}a {gap}-point gap
              </div>
            </div>
          )}
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
  const forecast = document.game?.forecast_generated_at;

  return (
    <div className="space-y-2 text-xs text-base-content/50">
      {/* (5) The week number confuses anyone who follows the sport, and /cfb is
          where people land. The footnote already exists on /cfb/slate; the
          numbering is not ours to change, so the page explains it instead. */}
      <p>
        <strong className="text-base-content/70">On the week number:</strong> the data source
        runs its week 1 from Aug 27 to Sep 7 — ten days, spanning both opening Saturdays — so a
        game the media calls Week 1 is filed here under the same week as games a week earlier.
        It is the source&rsquo;s numbering, not a renumbering here.
      </p>

      <p>
        {/* The timestamp that carries the claim. The document's own generated_at
            is the publish run and says only when the page was rebuilt. */}
        {forecast ? (
          <>
            <strong className="text-base-content/70">Forecast written</strong>{' '}
            {formatGeneratedAt(forecast)}, before kickoff — that is the claim this project
            makes, and it is why the prediction&rsquo;s own timestamp is shown here rather than
            the time the page was last rebuilt ({formatGeneratedAt(document.generated_at)}).
          </>
        ) : (
          <>Page rebuilt {formatGeneratedAt(document.generated_at)}.</>
        )}{' '}
        Season {document.season}.
      </p>

      {/* (4) The old sentence was a riddle: "a model that prints a certainty has
          no way to have been right" is not the reason. This is. */}
      <p>
        Win probabilities are capped at 1% and 99%. Nothing in this sport justifies 100% — FBS
        teams do lose to FCS teams — so the model is not allowed to say it.
      </p>
    </div>
  );
}

'use client';

/**
 * `/cfb/slate` — every game the model forecast this week.
 *
 * `/cfb` shows one game because it is a page about Texas. This is the other 119,
 * and it exists because the pipeline was already computing every row and
 * publishing one of them.
 *
 * **Home perspective throughout, unlike `/cfb`.** A slate has no subject team to
 * re-sign against, so it keeps the storage convention: a positive margin favours
 * the home team, and the page renders the sign against the home team's name.
 */

import { useMemo, useState } from 'react';

import CfbNav from '@/components/cfb/CfbNav';
import { DocumentPlaceholder } from '@/components/cfb/DocumentState';
import { SlateDocument, SlateGame } from '@/components/cfb/contract';
import {
  describeFavorite,
  disagreement,
  eloGapInPoints,
  favorite,
  formatGeneratedAt,
  formatKickoff,
  formatLine,
  formatProbability,
  formatWeek,
  marketFavorite,
} from '@/components/cfb/format';
import { useCfbDocument } from '@/components/cfb/useCfbDocument';

/**
 * How the board is ordered.
 *
 * **`edge` is the default and kickoff order is the option.** Ninety-six rows in
 * chronological order put the most interesting game wherever the schedule happens
 * to put it -- the model reading Idaho State by 19.0 against a market of 34.5 is
 * the best row on the page and sits two thirds of the way down a table nobody
 * scrolls. Sorting by how far the model is from the book puts the rows worth
 * arguing about first, which is the whole reason the page publishes both numbers.
 */
type SortKey = 'edge' | 'kickoff';

/**
 * `games` ordered by `sort`, without mutating the document.
 *
 * Kickoff breaks a tie on disagreement and `cfbd_game_id` breaks that, so the
 * order is total: two games with the same edge and the same kickoff still cannot
 * swap places between renders.
 *
 * **Games no book priced get a defined position rather than an accidental one.**
 * They have no disagreement to sort on -- not a small one, none -- so they go last
 * as a group, in kickoff order. Treating a missing line as an edge of zero would
 * file them among the games where the model and the market genuinely agree, which
 * is a different and far stronger claim than "nobody quoted this".
 */
function sortGames(games: readonly SlateGame[], sort: SortKey): SlateGame[] {
  const byKickoff = (a: SlateGame, b: SlateGame) =>
    new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime() ||
    a.cfbd_game_id - b.cfbd_game_id;

  if (sort === 'kickoff') return [...games].sort(byKickoff);

  return [...games].sort((a, b) => {
    const left = disagreement(a.predicted_margin, a.market_line);
    const right = disagreement(b.predicted_margin, b.market_line);
    if (left === null || right === null) {
      if (left === right) return byKickoff(a, b);
      return left === null ? 1 : -1;
    }
    return right - left || byKickoff(a, b);
  });
}

export default function SlatePage() {
  const state = useCfbDocument<SlateDocument>('slate.json');

  return (
    <main className="px-6 py-10 sm:px-10">
      <div className="max-w-5xl mx-auto">
        <CfbNav />

        <h1 className="text-2xl font-bold mb-1">This week&rsquo;s slate</h1>
        <p className="text-base-content/70 mb-8">
          Every game involving an FBS team, written before kickoff. Each row names the team it
          favours and by how many points, so nothing depends on reading a sign. The model also
          forecasts FCS-only games — their results are what move FCS ratings, which is how an
          FBS-vs-FCS prediction gets a sensible opponent — but they are not listed here.
        </p>

        {state.status !== 'ready' ? (
          <DocumentPlaceholder state={state} what="the slate" />
        ) : (
          <Slate document={state.document} />
        )}
      </div>
    </main>
  );
}

function Slate({ document }: { document: SlateDocument }) {
  // Absent on a document published before the filter existed, which is the
  // window between deploying these routes and the next publish.
  const excluded = document.excluded_non_fbs ?? 0;

  const [sort, setSort] = useState<SortKey>('edge');
  // Which rows are expanded. A set rather than one id, because the obvious thing
  // to do with two disagreements is open both and compare them.
  const [open, setOpen] = useState<ReadonlySet<number>>(() => new Set());

  const rows = useMemo(() => sortGames(document.games, sort), [document.games, sort]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm text-base-content/70">
        <span className="badge badge-ghost">{formatWeek(document.week)}</span>
        <span>{document.games.length} games</span>
        <span aria-hidden>&middot;</span>
        {/* The denominator travels, as it does everywhere else here: a slate with
            three lines on it looks the same as one with a hundred otherwise. */}
        {/* Only a count when it is not all of them. "96 priced by a book" on a
            96-game slate reads as a subset of something larger. */}
        <span>
          {document.priced === document.games.length
            ? 'all priced by a book'
            : `${document.priced} of them priced by a book`}
        </span>
        {excluded > 0 && (
          <>
            <span aria-hidden>&middot;</span>
            {/* Said, not hidden. The model forecast these; the page leaves them
                out because the audience follows one FBS team, and a slate that
                claimed the smaller number would understate the work. */}
            <span>
              {excluded} more forecast, not shown — both teams outside the FBS
            </span>
          </>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-base-content/60">Sort by</span>
        <div className="join">
          <button
            type="button"
            className={`btn btn-xs join-item ${sort === 'edge' ? 'btn-active' : ''}`}
            aria-pressed={sort === 'edge'}
            onClick={() => setSort('edge')}
          >
            Biggest disagreement
          </button>
          <button
            type="button"
            className={`btn btn-xs join-item ${sort === 'kickoff' ? 'btn-active' : ''}`}
            aria-pressed={sort === 'kickoff'}
            onClick={() => setSort('kickoff')}
          >
            Kickoff
          </button>
        </div>
        <span className="text-xs text-base-content/50">
          {sort === 'edge'
            ? 'how far the model is from the book — games no book priced come last'
            : 'the order the games are played in'}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="table table-zebra table-sm">
          <thead>
            <tr>
              <th aria-sort={sort === 'kickoff' ? 'ascending' : 'none'}>Kickoff</th>
              <th>Game</th>
              <th>Model picks</th>
              <th className="text-right">Win prob.</th>
              <th aria-sort={sort === 'edge' ? 'descending' : 'none'}>Market</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((game) => (
              <Row
                key={game.cfbd_game_id}
                game={game}
                team={document.team}
                open={open.has(game.cfbd_game_id)}
                onToggle={() =>
                  setOpen((current) => {
                    const next = new Set(current);
                    if (!next.delete(game.cfbd_game_id)) next.add(game.cfbd_game_id);
                    return next;
                  })
                }
              />
            ))}
          </tbody>
        </table>
      </div>

      {document.forecast_from && (
        <div className="alert alert-info text-sm">
          {/* One child, not two.
              daisyUI's .alert is `display: grid; grid-auto-flow: column`, so each
              direct child becomes a *column*. Two sibling <p> elements rendered
              as a full-width paragraph beside a ribbon about 65px wide down the
              right edge -- and the squeezed one was the paragraph explaining why
              games are missing. Wrapping them makes the alert one column again.
              `tests/cfb-slate.spec.ts` measures the box, because every text
              assertion passes either way. */}
          <div>
            <p>
              <strong>This week is longer than a week.</strong> The data source runs its week 1
              from Aug 27 to Sep 7 — ten days spanning <em>both</em> opening Saturdays — which is
              why this slate is larger than a normal one and why its games fall on two different
              weekends. It is the source&rsquo;s own numbering, not a renumbering here.
            </p>
            <p className="mt-2 opacity-80">
              Games that had already kicked off when this forecast was generated are not listed:
              the model went live mid-week, and predicting a game in progress is not a prediction.
              The first game forecast here starts {formatKickoff(document.forecast_from)}.
            </p>
          </div>
        </div>
      )}

      <p className="text-xs text-base-content/50">
        Published {formatGeneratedAt(document.generated_at)} &middot; season {document.season}
        {document.results_known_at && (
          <>
            {' '}
            &middot; results as of {formatGeneratedAt(document.results_known_at)}, so a game
            played since then is not yet marked
          </>
        )}
      </p>
    </div>
  );
}

function Row({
  game,
  team,
  open,
  onToggle,
}: {
  game: SlateGame;
  team: string;
  open: boolean;
  onToggle: () => void;
}) {
  // Slate rows are home perspective (§4.2), and the market line is home
  // perspective with the opposite sign (§4.3). Both go through `favorite` so the
  // table prints a team name rather than asking a reader to decode two
  // conventions running in opposite directions.
  const model = favorite(game.predicted_margin, game.home, game.away);
  const market = marketFavorite(game.market_line, game.home, game.away);
  const disagree = model !== null && market !== null && model.team !== market.team;

  const detailId = `game-${game.cfbd_game_id}-detail`;

  return (
    <>
      {/* The click target is the whole row, with a real <button> on the matchup
          as the keyboard and screen-reader handle. The button carries no handler
          of its own: its click bubbles to the row, so pressing Enter on it and
          clicking anywhere in the row run the same single toggle. */}
      <tr
        onClick={onToggle}
        className={[
          'cursor-pointer',
          game.featured ? 'bg-primary/10' : '',
          // A played game is history. It keeps its forecast -- that is the point
          // of writing one down -- but it should not compete with the games still
          // to come for the eye.
          game.played ? 'opacity-60' : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <td className="whitespace-nowrap text-xs text-base-content/70">
          {formatKickoff(game.kickoff)}
          {/* A played game keeps its forecast -- that is the point of writing one
              down -- but the row must not read as something still to come. */}
          {game.played && (
            <span className="block text-[0.65rem] uppercase tracking-wide text-base-content/50">
              played
            </span>
          )}
        </td>
        <td>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={detailId}
            className={`link link-hover text-left ${game.featured ? 'font-semibold' : ''}`}
          >
            {game.away} {game.neutral_site ? 'vs' : 'at'} {game.home}
          </button>
          {game.featured && <span className="badge badge-primary badge-sm ml-2">{team}</span>}
          {game.neutral_site && <span className="badge badge-ghost badge-sm ml-2">neutral</span>}
          {!game.neutral_site && (
            <span className="block text-[0.65rem] text-base-content/50">
              {game.home} at home
            </span>
          )}
        </td>
        <td className="whitespace-nowrap">
          <span className="font-medium">{describeFavorite(model, 'dead even')}</span>
        </td>
        <td className="text-right tabular-nums whitespace-nowrap">
          {formatProbability(game.win_probability)}
          <span className="block text-[0.65rem] text-base-content/50">{game.home} wins</span>
        </td>
        <td className="whitespace-nowrap">
          {market === null ? (
            <span className="text-base-content/50">no line</span>
          ) : (
            <>
              <span className={disagree ? 'font-medium text-warning' : 'font-medium'}>
                {describeFavorite(market)}
              </span>
              <span className="block text-[0.65rem] text-base-content/50">
                {game.line_source} · {formatLine(game.market_line)} on {game.home}
              </span>
            </>
          )}
        </td>
      </tr>
      {open && <Detail game={game} id={detailId} />}
    </>
  );
}

/**
 * The expanded row: the same arithmetic `/cfb` shows for the featured game.
 *
 * Every number here was already in `slate.json` or is a conversion of two that
 * were -- no fetch, no second document, and nothing a collapsed row was hiding
 * that the page had to go and get. The PRD's non-goals rule out a live API, and
 * an interaction costing a request per click would be one.
 */
function Detail({ game, id }: { game: SlateGame; id: string }) {
  const edge = disagreement(game.predicted_margin, game.market_line);
  const model = favorite(game.predicted_margin, game.home, game.away);
  const market = marketFavorite(game.market_line, game.home, game.away);
  // Absent on a document published before these fields existed, which is the
  // window between deploying this route and the next publish. The row then shows
  // what it has rather than rendering "NaN-point gap".
  const gap =
    game.home_elo != null && game.away_elo != null
      ? Math.abs(Math.round(game.home_elo - game.away_elo))
      : null;

  return (
    <tr id={id} className="bg-base-200/60">
      <td colSpan={5} className="text-sm">
        <div className="grid gap-4 sm:grid-cols-3">
          {gap !== null && (
            <div>
              <div className="text-xs uppercase tracking-wide text-base-content/60">
                Elo ratings
              </div>
              <div className="mt-1 tabular-nums">
                {game.home} {Math.round(game.home_elo!)}
                <span className="text-base-content/50"> &middot; </span>
                {game.away} {Math.round(game.away_elo!)}
              </div>
              <div className="text-xs text-base-content/60 mt-1">
                a {gap}-point gap, roughly {eloGapInPoints(gap)} points of margin before home
                advantage
              </div>
            </div>
          )}

          <div>
            <div className="text-xs uppercase tracking-wide text-base-content/60">
              The forecast
            </div>
            <div className="mt-1">{describeFavorite(model, 'dead even')}</div>
            <div className="text-xs text-base-content/60 mt-1">
              {formatProbability(game.win_probability)} for {game.home}
              {game.neutral_site ? ' · neutral site' : ' · at home'}
            </div>
          </div>

          <div>
            <div className="text-xs uppercase tracking-wide text-base-content/60">
              Against the market
            </div>
            {edge === null ? (
              <div className="mt-1 text-base-content/50">no book priced this game</div>
            ) : (
              <>
                <div className="mt-1">
                  {edge < 0.05
                    ? 'the model and the market agree'
                    : `${edge.toFixed(1)} points apart`}
                </div>
                <div className="text-xs text-base-content/60 mt-1">
                  {game.line_source} has {describeFavorite(market)}, quoted{' '}
                  {formatLine(game.market_line)} on {game.home}
                </div>
              </>
            )}
          </div>
        </div>
      </td>
    </tr>
  );
}

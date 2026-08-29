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

import CfbNav from '@/components/cfb/CfbNav';
import { DocumentPlaceholder } from '@/components/cfb/DocumentState';
import { SlateDocument, SlateGame } from '@/components/cfb/contract';
import {
  describeFavorite,
  favorite,
  formatGeneratedAt,
  formatKickoff,
  formatLine,
  formatProbability,
  formatWeek,
  marketFavorite,
} from '@/components/cfb/format';
import { useCfbDocument } from '@/components/cfb/useCfbDocument';

export default function SlatePage() {
  const state = useCfbDocument<SlateDocument>('slate.json');

  return (
    <main className="px-6 py-10 sm:px-10">
      <div className="max-w-5xl mx-auto">
        <CfbNav />

        <h1 className="text-2xl font-bold mb-1">This week&rsquo;s slate</h1>
        <p className="text-base-content/70 mb-8">
          Every game the model forecast, written before kickoff. Each row names the team it
          favours and by how many points, so nothing depends on reading a sign.
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
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm text-base-content/70">
        <span className="badge badge-ghost">{formatWeek(document.week)}</span>
        <span>{document.games.length} games</span>
        <span aria-hidden>&middot;</span>
        {/* The denominator travels, as it does everywhere else here: a slate with
            three lines on it looks the same as one with a hundred otherwise. */}
        <span>{document.priced} priced by a book</span>
      </div>

      <div className="overflow-x-auto">
        <table className="table table-zebra table-sm">
          <thead>
            <tr>
              <th>Kickoff</th>
              <th>Game</th>
              <th>Model picks</th>
              <th className="text-right">Win prob.</th>
              <th>Market</th>
            </tr>
          </thead>
          <tbody>
            {document.games.map((game) => (
              <Row key={game.cfbd_game_id} game={game} team={document.team} />
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-base-content/50">
        Published {formatGeneratedAt(document.generated_at)} &middot; season {document.season}
      </p>
    </div>
  );
}

function Row({ game, team }: { game: SlateGame; team: string }) {
  // Slate rows are home perspective (§4.2), and the market line is home
  // perspective with the opposite sign (§4.3). Both go through `favorite` so the
  // table prints a team name rather than asking a reader to decode two
  // conventions running in opposite directions.
  const model = favorite(game.predicted_margin, game.home, game.away);
  const market = marketFavorite(game.market_line, game.home, game.away);
  const disagree = model !== null && market !== null && model.team !== market.team;

  return (
    <tr className={game.featured ? 'bg-primary/10' : undefined}>
      <td className="whitespace-nowrap text-xs text-base-content/70">
        {formatKickoff(game.kickoff)}
      </td>
      <td>
        <span className={game.featured ? 'font-semibold' : undefined}>
          {game.away} {game.neutral_site ? 'vs' : 'at'} {game.home}
        </span>
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
  );
}

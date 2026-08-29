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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm text-base-content/70">
        <span className="badge badge-ghost">{formatWeek(document.week)}</span>
        <span>{document.games.length} games</span>
        <span aria-hidden>&middot;</span>
        {/* The denominator travels, as it does everywhere else here: a slate with
            three lines on it looks the same as one with a hundred otherwise. */}
        <span>{document.priced} priced by a book</span>
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

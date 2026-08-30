/**
 * Turning the pipeline's numbers into strings (SPEC-phase1 3.7, 5.3).
 *
 * Formatting only. Nothing here computes a statistic -- if a value has to be
 * derived, it belongs in `cfb/src/cfb/publish/`, where a replay can check it.
 */

/**
 * §3.7's endpoints. The published probability is already clamped to
 * `[0.001, 0.999]`, so it never *is* 0 or 1 -- but rounding to a whole percent
 * turns 0.999 into "100%" and 0.001 into "0%", which is the exact claim the
 * clamp was added to prevent. So the last percent on each end is rendered as an
 * inequality instead.
 *
 * The clamp and this function are two halves of one rule and neither works
 * alone: clamping without this prints 100%, and this without the clamp would be
 * printing ">99%" for a genuine 1.0.
 */
export function formatProbability(probability: number): string {
  if (probability < 0.01) return '<1%';
  if (probability > 0.99) return '>99%';
  return `${Math.round(probability * 100)}%`;
}

/**
 * The pipeline's `ELO_PER_POINT`, mirrored.
 *
 * Not a second source of truth so much as a second *copy*: the pages convert a
 * rating gap into points to explain themselves, and the conversion has to be the
 * model's own or the explanation describes a different model. If the pipeline's
 * constant ever moves, this moves with it -- §3.1's calibration work is the kind
 * of thing that moves it.
 */
export const ELO_PER_POINT = 20;

/** A rating gap in points of predicted margin, before home advantage. */
export function eloGapInPoints(gap: number): number {
  return Math.round(gap / ELO_PER_POINT);
}

/** A margin with an explicit sign, because "3" and "-3" are opposite claims. */
export function formatMargin(margin: number): string {
  return `${margin > 0 ? '+' : ''}${margin.toFixed(1)}`;
}

/**
 * Who is favoured and by how much.
 *
 * **A signed number is not a readable claim.** "−1.5, home team's line" asks a
 * reader to hold two conventions in their head — which team is home, and which
 * direction the sign runs — and the two conventions here run *opposite* ways:
 * `predicted_margin` is positive for the team it is about, while a market line
 * is negative for the team it favours (§4.3). Anything rendering both as bare
 * signed numbers is asking to be misread.
 *
 * So both go through here, and the caller says which team a positive value
 * favours. The page then prints a team name and a number of points, which is how
 * every other football page in the world states it.
 */
export interface Favorite {
  team: string;
  points: number;
}

export function favorite(
  value: number | null,
  positiveTeam: string,
  negativeTeam: string,
): Favorite | null {
  if (value === null || value === 0) return null;
  return value > 0
    ? { team: positiveTeam, points: value }
    : { team: negativeTeam, points: -value };
}

/** `favorite` as a sentence: "Texas by 1.5", or "pick'em" at exactly zero. */
export function describeFavorite(pick: Favorite | null, whenLevel = "pick'em"): string {
  return pick === null ? whenLevel : `${pick.team} by ${pick.points.toFixed(1)}`;
}

/**
 * A mean, or an em dash.
 *
 * **`null` is never rendered as `0`.** §5.3 makes every mean `null` rather than
 * `0.0` on an empty population precisely so the page cannot claim a perfect
 * prediction nobody made, and this is the last place that rule can be broken.
 */
export function formatMean(value: number | null, digits = 2): string {
  return value === null ? '—' : value.toFixed(digits);
}

/** A correlation, or an em dash. Three digits, because 0.98 and 0.985 differ. */
export function formatCorrelation(value: number | null): string {
  return value === null ? '—' : value.toFixed(3);
}

/**
 * The market line as the book posted it (§4.3), for when the raw quote is wanted
 * alongside the readable version.
 *
 * Negative favours the *home* team, the opposite convention from
 * `predicted_margin`. Never render this on its own — see `favorite`.
 */
export function formatLine(line: number | null): string {
  if (line === null) return 'no line';
  return line > 0 ? `+${line}` : `${line}`;
}

/**
 * The market line as a favourite. `line` is home-perspective and negative
 * favours home, so the sign is flipped before it reaches `favorite`. **This is
 * the only place on the site that flip happens.**
 */
export function marketFavorite(
  line: number | null,
  home: string,
  away: string,
): Favorite | null {
  return line === null ? null : favorite(-line, home, away);
}

/** A kickoff in the reader's own timezone, which is the only one they care about. */
export function formatKickoff(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

/** A generation timestamp, for the "as of" line every page carries. */
export function formatGeneratedAt(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

/** `"04"` -> `"Week 4"`, and the two named partitions read as themselves. */
export function formatWeek(week: string): string {
  if (week === 'preseason') return 'Preseason';
  if (week === 'postseason') return 'Postseason';
  return `Week ${Number(week)}`;
}

/**
 * The market's line as a margin **for the subject team**.
 *
 * `market_line` is home-perspective and negative-favours-home (§4.3), so the
 * conversion depends on whether the subject is at home. This is the only place
 * that flip happens for a subject-team page.
 */
export function marketMarginFor(
  line: number | null | undefined,
  atHome: boolean,
): number | null {
  if (line == null) return null;
  return atHome ? -line : line;
}

/**
 * The size of the model's disagreement with the market, ignoring direction.
 *
 * What `/cfb/slate` sorts on. `edgeOver` answers "which way and by how much for
 * this team"; a slate has no subject team, so the interesting quantity is simply
 * how far apart the two opinions are. `null` when no book priced the game --
 * **never `0`**, which is the specific claim that the model and the market agree.
 */
export function disagreement(
  predictedMargin: number,
  line: number | null | undefined,
): number | null {
  const edge = edgeOver(predictedMargin, line, true);
  return edge === null ? null : Math.abs(edge);
}

/**
 * How much more the model likes the subject team than the market does.
 *
 * **The one number that distinguishes this page from a scoreboard.** A win
 * probability of 99% reads the same whether the model is right or badly wrong;
 * the disagreement with a book that prices the same game is the claim the
 * accuracy record eventually settles.
 *
 * Positive means the model is higher on the subject team than the market.
 * `null` when nothing priced the game.
 */
export function edgeOver(
  predictedMargin: number,
  line: number | null | undefined,
  atHome: boolean,
): number | null {
  const market = marketMarginFor(line, atHome);
  return market === null ? null : predictedMargin - market;
}

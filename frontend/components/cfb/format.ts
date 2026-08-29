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

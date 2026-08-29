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
 * A market line as the book posted it (§4.3).
 *
 * Negative favours the *home* team, which is the opposite convention from
 * `predicted_margin`. It is not converted here for the same reason the pipeline
 * does not convert it: it is a quotation, and it is printed next to the name of
 * the book that quoted it.
 */
export function formatLine(line: number | null): string {
  if (line === null) return 'no line';
  return line > 0 ? `+${line}` : `${line}`;
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

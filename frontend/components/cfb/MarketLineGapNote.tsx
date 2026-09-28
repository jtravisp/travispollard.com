/**
 * Weeks whose forecasts were written before the week's market lines had been
 * captured, and the note that says so wherever a figure compares against the
 * market.
 *
 * **2026 weeks 2 and 3.** Week 2 was forecast from a lines capture taken twelve
 * days early, when books had priced 7 of the 120 games it went on to score. Week 3's lines were
 * never captured before its forecast: the Monday job that fetched them died on
 * its scoring step first (2026-09-14) and the capture steps after it were
 * skipped. Predictions are write-once, so those weeks' market columns stay empty
 * -- see the comment on the lines step in .github/workflows/cfb-predict.yml, and
 * the fix that made Thursday's forecast fetch its own lines.
 *
 * Without this, "260 had no line" reads as if the books had not priced those
 * games, when the pipeline simply never looked. The data documents carry no
 * per-week priced count to detect it from, so the gap is recorded here, as a
 * fact about a past season, rather than inferred.
 */

import { formatWeek } from "./format";

/**
 * Per gap week, how many of its scored games carry a line. Fixed facts: the
 * forecasts are write-once and the weeks are scored, so these never change.
 */
const MARKET_LINE_GAPS: Record<
  number,
  { week: string; priced: number; games: number }[]
> = {
  2026: [
    { week: "02", priced: 7, games: 120 },
    { week: "03", priced: 0, games: 119 },
  ],
};

/** "a, b and c" */
function joinAnd(parts: string[]): string {
  return parts.length === 1
    ? parts[0]
    : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * Renders only for a season with a recorded gap, and only once a gap week has
 * been scored -- before that there is nothing on the page it would qualify.
 */
export default function MarketLineGapNote({
  season,
  throughWeek,
}: {
  season: number;
  throughWeek: string | null;
}) {
  const gaps = (MARKET_LINE_GAPS[season] ?? []).filter(
    (gap) => throughWeek !== null && gap.week <= throughWeek,
  );
  if (gaps.length === 0) return null;

  const weeks = gaps.map((gap) => formatWeek(gap.week).replace(/^Week /, ""));
  const counts = gaps.map(
    (gap, i) =>
      `${gap.priced === 0 ? "none" : `${gap.priced}`} of week ${weeks[i]}’s ${gap.games} games`,
  );
  const one = gaps.length === 1;

  return (
    <p
      className="text-xs text-base-content/70 mt-3"
      data-testid="market-line-gap"
    >
      {one ? "Week" : "Weeks"} {joinAnd(weeks)} {one ? "was" : "were"} forecast
      before {one ? "that week’s" : "those weeks’"} betting lines had been
      captured, so only {joinAnd(counts)} carry a line. The rest are left out of
      every figure that compares against the market, and counted among the games
      with no line.
    </p>
  );
}

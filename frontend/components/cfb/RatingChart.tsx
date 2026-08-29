'use client';

/**
 * Texas's rating and rank across the season, drawn as inline SVG.
 *
 * **Deliberately not a chart library.** The series is at most seventeen points
 * of two numbers; a dependency to draw it would be larger than the data.
 *
 * **It refuses to draw fewer than two points**, and that refusal is the point.
 * The first `elo/week=NN` state lands 2026-09-13, so for the two weeks before it
 * the series is the preseason seed alone — and a line through one point is
 * indistinguishable from a broken chart. The caller shows the current rating
 * instead and says how far in the season is.
 */

import { RatingPoint } from './contract';
import { formatWeek } from './format';

export const MINIMUM_POINTS = 2;

export default function RatingChart({ history }: { history: RatingPoint[] }) {
  if (history.length < MINIMUM_POINTS) return null;

  const width = 560;
  const height = 160;
  const pad = { top: 12, right: 12, bottom: 26, left: 44 };

  const ratings = history.map((point) => point.elo);
  const low = Math.min(...ratings);
  const high = Math.max(...ratings);
  // A flat series would divide by zero and, worse, draw a line at the top of the
  // box as though it had climbed there.
  const span = high - low || 1;

  const x = (index: number) =>
    pad.left +
    (index / Math.max(history.length - 1, 1)) * (width - pad.left - pad.right);
  const y = (elo: number) =>
    pad.top + (1 - (elo - low) / span) * (height - pad.top - pad.bottom);

  const line = history
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(point.elo)}`)
    .join(' ');

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto"
        role="img"
        aria-label={`Elo rating by week, this model’s own, ${history
          .map((p) => `${formatWeek(p.week)} ${Math.round(p.elo)}`)
          .join(', ')}`}
      >
        <line
          x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom}
          className="stroke-base-300" strokeWidth="1"
        />
        <path d={line} fill="none" className="stroke-primary" strokeWidth="2" />
        {history.map((point, index) => (
          <g key={point.week}>
            <circle cx={x(index)} cy={y(point.elo)} r="3.5" className="fill-primary" />
            <text
              x={x(index)} y={height - pad.bottom + 16}
              textAnchor="middle" className="fill-base-content/60 text-[10px]"
            >
              {point.week === 'preseason' ? 'Pre' : point.week}
            </text>
          </g>
        ))}
        <text x={4} y={pad.top + 4} className="fill-base-content/50 text-[10px]">
          {Math.round(high)}
        </text>
        <text x={4} y={height - pad.bottom} className="fill-base-content/50 text-[10px]">
          {Math.round(low)}
        </text>
      </svg>
    </figure>
  );
}

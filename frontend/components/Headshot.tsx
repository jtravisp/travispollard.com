/**
 * The hero portrait.
 *
 * One variant. The cartoon avatar and the `HEADSHOT` switch that chose between
 * them are gone: the switch existed to carry the site from the drawn placeholder
 * to a real photograph, that has happened, and a constant with one reachable
 * value is just a comment that can go out of date.
 *
 * Sizing is the caller's job via `className`, because the two hero layouts want
 * different diameters from the same image.
 */

export default function Headshot({ className = '' }: { className?: string }) {
  return (
    <img
      src="/headshot.jpeg"
      alt="Travis Pollard"
      width={320}
      height={320}
      // The LCP element on the home page. Without the hint the browser
      // discovers it at normal priority behind the CSS and the chunk graph.
      fetchPriority="high"
      // Explicit dimensions against a 1024x1024 source: without them the
      // layout jumps while it loads.
      className={`aspect-square h-auto w-72 rounded-full object-cover ${className}`}
    />
  );
}

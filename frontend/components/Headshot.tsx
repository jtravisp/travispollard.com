/**
 * The hero portrait, behind one switch.
 *
 * The cartoon was a 450px-wide block stacked *under* a centred terminal card,
 * which put every call to action below the fold at 1440x900 -- the visitor had
 * to scroll before the page offered them anything to do. It is now a column
 * beside the text rather than a row under it, and it is capped well below the
 * old width.
 *
 * **To switch to a real photo: drop the file at `public/headshot.jpg` and change
 * `HEADSHOT` to `'photo'`.** That is the whole procedure. It is a constant and
 * not a filesystem check because `output: 'export'` means there is no server to
 * ask at request time, and a build-time `fs.existsSync` would be a silent
 * behaviour change on a file nobody remembers adding.
 *
 * The two variants deliberately differ in shape, not only in source. A drawn
 * avatar reads fine as a soft rectangle; a photograph in the same frame reads
 * like a badge scan, so the photo variant is a circle.
 */

type HeadshotKind = 'cartoon' | 'photo';

/** Flip to 'photo' once public/headshot.jpg exists. */
export const HEADSHOT: HeadshotKind = 'cartoon';

const VARIANTS = {
  cartoon: {
    src: '/images/travis.webp',
    alt: 'Illustrated portrait of Travis Pollard',
    // Intrinsic 900x900. Rendering at 288 keeps it crisp on a 2x display.
    className: 'rounded-box',
  },
  photo: {
    src: '/headshot.jpg',
    alt: 'Travis Pollard',
    className: 'rounded-full object-cover aspect-square',
  },
} as const;

export default function Headshot({ className = '' }: { className?: string }) {
  const variant = VARIANTS[HEADSHOT];

  return (
    <img
      src={variant.src}
      alt={variant.alt}
      width={288}
      height={288}
      // Explicit dimensions plus a fixed box: the intrinsic size is 900x900, and
      // without them the layout jumps by ~600px while it loads.
      className={`w-44 sm:w-56 lg:w-72 h-auto shadow-lg ${variant.className} ${className}`}
    />
  );
}

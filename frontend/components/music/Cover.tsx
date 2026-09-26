import type { ManifestEntry } from '@/lib/music/markdown';

/**
 * Album cover art from its processed WebP variants.
 *
 * A server component: plain <img> with srcset, width and height, so the
 * browser picks a size, reserves the space before it loads, and no script is
 * involved. `priority` is for the post page, where the cover is the largest
 * thing above the fold; cards lazy-load.
 */
export default function Cover({
  entry,
  alt,
  sizes,
  priority = false,
  className = '',
}: {
  entry: ManifestEntry;
  alt: string;
  sizes: string;
  priority?: boolean;
  className?: string;
}) {
  const largest = entry.variants[entry.variants.length - 1];
  const middle = entry.variants[Math.min(1, entry.variants.length - 1)];
  return (
    <img
      src={middle.src}
      srcSet={entry.variants.map((v) => `${v.src} ${v.width}w`).join(', ')}
      sizes={sizes}
      width={largest.width}
      height={largest.height}
      alt={alt}
      loading={priority ? 'eager' : 'lazy'}
      decoding="async"
      fetchPriority={priority ? 'high' : undefined}
      className={`aspect-square w-full rounded-xl object-cover ${className}`}
    />
  );
}

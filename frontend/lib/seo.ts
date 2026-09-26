import type { Metadata } from 'next';
import { site } from '@/content/site';

/**
 * Metadata for a section of the site (/music, /projects, ...): its title and
 * description, and the Open Graph / Twitter tags link previews are built from.
 *
 * Next inherits a parent's openGraph object whole. A section that set only a
 * title and description therefore shipped the home page's link card -- its
 * title, description, image, and og:url pointing at the home page -- so a
 * shared /music/ link previewed as the home page. Every section goes through
 * this instead.
 *
 * `path` sets the canonical and og:url. Leave it out for a section whose
 * layout also covers sub-pages (/cfb): og:url would then name the section on
 * every sub-page, and without it a previewer uses the URL that was shared.
 */

const DEFAULT_IMAGE = { url: '/images/og-card.png', width: 1200, height: 630 };

export function sectionMetadata({
  title,
  description,
  path,
  image = DEFAULT_IMAGE,
  imageAlt,
}: {
  title: string;
  description: string;
  path?: string;
  image?: { url: string; width: number; height: number };
  imageAlt?: string;
}): Metadata {
  const fullTitle = `${title} - ${site.name}`;
  const images = [{ ...image, alt: imageAlt ?? fullTitle }];
  return {
    title,
    description,
    ...(path ? { alternates: { canonical: path } } : {}),
    openGraph: {
      title: fullTitle,
      description,
      ...(path ? { url: path } : {}),
      siteName: site.name,
      locale: 'en_US',
      type: 'website',
      images,
    },
    twitter: {
      card: 'summary_large_image',
      title: fullTitle,
      description,
      images: [image.url],
    },
  };
}

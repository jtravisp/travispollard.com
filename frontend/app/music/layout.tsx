import { sectionMetadata } from '@/lib/seo';
import { site } from '@/content/site';

const music = sectionMetadata({
  title: 'Music',
  description: `Album reviews by Travis Pollard. ${site.musicTagline}`,
  path: '/music/',
  image: { url: '/images/og-music.png', width: 1200, height: 630 },
  imageAlt: 'Music - album reviews by Travis Pollard',
});

export const metadata = {
  ...music,
  alternates: {
    ...music.alternates,
    types: { 'application/rss+xml': [{ url: '/music/feed.xml', title: 'Travis Pollard - Music' }] },
  },
};

export default function MusicLayout({ children }: { children: React.ReactNode }) {
  return children;
}

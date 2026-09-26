export const metadata = {
  title: 'Music',
  description:
    'Album reviews by Travis Pollard -- saxophonist, former band director, and listener to whatever friends recommend.',
  alternates: {
    canonical: '/music/',
    types: { 'application/rss+xml': [{ url: '/music/feed.xml', title: 'Travis Pollard - Music' }] },
  },
};

export default function MusicLayout({ children }: { children: React.ReactNode }) {
  return children;
}

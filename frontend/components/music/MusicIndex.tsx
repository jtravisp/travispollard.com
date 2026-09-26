import HeaderWithTheme from '@/components/HeaderWithTheme';
import PageIntro from '@/components/PageIntro';
import SiteFooter from '@/components/SiteFooter';
import Cover from '@/components/music/Cover';
import { formatDate } from '@/lib/music/format';
import { image, readManifest } from '@/lib/music/markdown';
import { getPosts } from '@/lib/music/posts';
import { site } from '@/content/site';
import Link from 'next/link';

/**
 * /music: every published review as a cover-art card, newest first.
 *
 * Rendered by app/music/[[...slug]]/page.tsx for the empty slug. A server
 * component, unlike the rest of the site's pages: the list is known at build
 * time, so the page ships no script of its own -- the header's theme toggle is
 * the only interactive thing on it.
 */
export default function MusicIndex() {
  const posts = getPosts();
  const manifest = posts.length ? readManifest() : {};

  return (
    <main className="min-h-screen bg-base-100 bg-dot-grid text-base-content">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <HeaderWithTheme />

        <PageIntro
          title="Music"
          lead={site.musicTagline}
          action={
            <a href="/music/feed.xml" className="text-sm text-base-content/70 hover:text-primary">
              RSS feed
            </a>
          }
        />

        {posts.length === 0 ? (
          <p className="mb-24 text-base-content/70">No reviews published yet.</p>
        ) : (
          <ul className="mb-24 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {posts.map((post) => (
              <li key={post.slug}>
                <Link
                  href={`/music/${post.slug}/`}
                  className="group flex h-full flex-col rounded-xl border border-base-300/70 bg-base-200/30 p-4 transition-colors duration-200 hover:border-base-content/20 hover:bg-base-200/60 dark:border-white/5 dark:bg-white/[0.02] dark:hover:border-white/15 dark:hover:bg-white/[0.04]"
                >
                  <Cover
                    entry={image(manifest, post.slug, post.cover)}
                    alt={`Cover of ${post.title} by ${post.artist}`}
                    sizes="(min-width: 1024px) 18rem, (min-width: 640px) 50vw, 100vw"
                  />
                  <div className="mt-4 flex items-start justify-between gap-3">
                    <h2 className="font-semibold leading-snug group-hover:text-primary">
                      {post.title}
                    </h2>
                    <span className="shrink-0 font-mono text-sm tabular-nums text-base-content/80">
                      {post.rating}/10
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-base-content/80">
                    {post.artist} &middot; {post.released}
                  </p>
                  <p className="mt-3 text-sm leading-relaxed text-base-content/70">{post.summary}</p>
                  <p className="mt-auto pt-4 text-xs text-base-content/70">
                    Recommended by {post.recommended_by} &middot;{' '}
                    <time dateTime={post.date}>{formatDate(post.date)}</time>
                    {post.draft && (
                      <span className="ml-2 rounded border border-warning/60 px-1.5 py-0.5 text-[11px] text-base-content">
                        Draft
                      </span>
                    )}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}

        <SiteFooter />
      </div>
    </main>
  );
}

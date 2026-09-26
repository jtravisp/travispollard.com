import HeaderWithTheme from '@/components/HeaderWithTheme';
import SiteFooter from '@/components/SiteFooter';
import Cover from '@/components/music/Cover';
import { site } from '@/content/site';
import { formatDate, streamingLinks } from '@/lib/music/format';
import { image, readManifest, renderPost } from '@/lib/music/markdown';
import { getPost } from '@/lib/music/posts';
import Link from 'next/link';
import { notFound } from 'next/navigation';

/**
 * /music/<slug>/: one review, rendered at build time from its Markdown by
 * app/music/[[...slug]]/page.tsx.
 *
 * Order: cover and the facts (artist, year, rating, date, who recommended it),
 * the review body with its inline images and pull quotes, favourite tracks,
 * the "Musician's notes" block lifted out of the body, then plain streaming
 * links -- links, not embedded players, which would each load a third-party
 * script. Structured data (schema.org Review of a MusicAlbum) goes in the page
 * as JSON-LD for search engines.
 */

/** JSON for a <script> element: `<` escaped so post text cannot close the tag. */
function jsonLd(value: unknown): string {
  return JSON.stringify(value).replace(/</g, '\\u003c');
}

export default function MusicPost({ slug }: { slug: string }) {
  const post = getPost(slug);
  if (!post) notFound();

  const manifest = readManifest();
  const cover = image(manifest, slug, post.cover);
  const { html, notesHtml, text } = renderPost(slug, post.body, manifest);
  const listen = streamingLinks(post.links);
  const url = `${site.url}/music/${slug}/`;

  const structuredData = {
    '@context': 'https://schema.org',
    '@type': 'Review',
    url,
    name: `${post.title} by ${post.artist}`,
    description: post.summary,
    datePublished: post.date,
    author: { '@type': 'Person', name: site.name, url: site.url },
    reviewRating: {
      '@type': 'Rating',
      ratingValue: post.rating,
      bestRating: 10,
      worstRating: 1,
    },
    itemReviewed: {
      '@type': 'MusicAlbum',
      name: post.title,
      byArtist: { '@type': 'MusicGroup', name: post.artist },
      datePublished: String(post.released),
      ...(cover.og ? { image: `${site.url}${cover.og.src}` } : {}),
      ...(listen.length ? { sameAs: listen.map((l) => l.url) } : {}),
    },
    reviewBody: text,
  };

  return (
    <main className="min-h-screen bg-base-100 bg-dot-grid text-base-content">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <HeaderWithTheme />

        <article className="mb-24">
          <header className="mb-12 grid gap-8 border-b border-base-300 pb-10 sm:grid-cols-[14rem_1fr] md:grid-cols-[16rem_1fr]">
            <Cover
              entry={cover}
              alt={`Cover of ${post.title} by ${post.artist}`}
              sizes="(min-width: 768px) 16rem, (min-width: 640px) 14rem, 100vw"
              priority
            />
            <div className="flex flex-col">
              <p className="text-sm text-base-content/70">
                Album review
                {post.draft && (
                  <span className="ml-2 rounded border border-warning/60 px-1.5 py-0.5 text-xs text-base-content">Draft</span>
                )}
              </p>
              <h1 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">{post.title}</h1>
              <p className="mt-2 text-lg text-base-content/80">
                {post.artist} &middot; {post.released}
              </p>

              <dl className="mt-6 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
                <dt className="text-base-content/70">Rating</dt>
                <dd className="font-mono font-semibold tabular-nums">{post.rating}/10</dd>
                <dt className="text-base-content/70">Reviewed</dt>
                <dd>
                  <time dateTime={post.date}>{formatDate(post.date)}</time>
                </dd>
                {post.tags.length > 0 && (
                  <>
                    <dt className="text-base-content/70">Tags</dt>
                    <dd>{post.tags.join(' · ')}</dd>
                  </>
                )}
              </dl>

              <p className="mt-auto pt-6 text-base">
                Recommended by <span className="font-semibold">{post.recommended_by}</span>
              </p>
            </div>
          </header>

          {/* Rendered from the post's own Markdown at build time; raw HTML in
              a post is not enabled, so this is only what the pipeline makes. */}
          <div className="music-prose prose max-w-none" dangerouslySetInnerHTML={{ __html: html }} />

          {post.favorite_tracks.length > 0 && (
            <section className="mt-12" aria-labelledby="favorite-tracks">
              <h2 id="favorite-tracks" className="mb-4 text-xl font-bold tracking-tight">
                Favorite tracks
              </h2>
              <ol className="list-decimal space-y-1.5 pl-6 marker:text-base-content/70">
                {post.favorite_tracks.map((track) => (
                  <li key={track}>{track}</li>
                ))}
              </ol>
            </section>
          )}

          {notesHtml && (
            <section
              className="musicians-notes mt-12 rounded-xl border border-base-300/70 bg-base-200/30 p-6 dark:border-white/5 dark:bg-white/[0.02]"
              aria-labelledby="musicians-notes"
            >
              <h2 id="musicians-notes" className="mb-3 text-xl font-bold tracking-tight">
                Musician&apos;s notes
              </h2>
              <div className="music-prose prose max-w-none" dangerouslySetInnerHTML={{ __html: notesHtml }} />
            </section>
          )}

          {listen.length > 0 && (
            <section className="mt-12" aria-labelledby="listen">
              <h2 id="listen" className="mb-3 text-xl font-bold tracking-tight">
                Listen
              </h2>
              <ul className="flex flex-wrap gap-x-6 gap-y-2">
                {listen.map((l) => (
                  <li key={l.url}>
                    <a
                      href={l.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-base-content/80 hover:text-primary"
                    >
                      {l.label}
                      <span aria-hidden="true" className="ml-1">
                        &#8599;
                      </span>
                      <span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p className="mt-16">
            <Link href="/music/" className="text-sm text-base-content/70 hover:text-primary">
              &larr; All reviews
            </Link>
          </p>
        </article>

        <SiteFooter />
      </div>

      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(structuredData) }} />
    </main>
  );
}

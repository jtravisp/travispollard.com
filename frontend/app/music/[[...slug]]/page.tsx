import MusicIndex from '@/components/music/MusicIndex';
import MusicPost from '@/components/music/MusicPost';
import { site } from '@/content/site';
import { image, readManifest } from '@/lib/music/markdown';
import { getPost, getPosts } from '@/lib/music/posts';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

/**
 * Every /music page: the index at /music/ (empty slug) and each review at
 * /music/<slug>/.
 *
 * One optional catch-all rather than app/music/page.tsx + [slug]/page.tsx,
 * because a static export refuses to build a dynamic route whose
 * generateStaticParams returns nothing -- which is exactly the state of the
 * site whenever every post is a draft. Here the index is always one of the
 * params, so the list is never empty and no placeholder page is needed.
 * /music/feed.xml is its own static route and takes precedence over this one.
 */

type Params = { slug?: string[] };

// Only the pages known at build time exist; anything else under /music/ 404s.
export const dynamicParams = false;

export function generateStaticParams(): Params[] {
  return [{ slug: [] }, ...getPosts().map((p) => ({ slug: [p.slug] }))];
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { slug = [] } = await params;
  if (slug.length === 0) return {}; // the index: app/music/layout.tsx has it
  const post = getPost(slug[0]);
  if (!post) return {};
  const og = image(readManifest(), post.slug, post.cover).og;
  const title = `${post.title} by ${post.artist}`;
  return {
    // Absolute: the /music layout's own title stops the root "%s - Travis
    // Pollard" template reaching this far down, so it is spelled out here.
    title: { absolute: `${title} - ${site.name}` },
    description: post.summary,
    alternates: {
      canonical: `/music/${post.slug}/`,
      types: { 'application/rss+xml': [{ url: '/music/feed.xml', title: 'Travis Pollard - Music' }] },
    },
    robots: post.draft ? { index: false, follow: false } : undefined,
    openGraph: {
      title,
      description: post.summary,
      url: `/music/${post.slug}/`,
      type: 'article',
      publishedTime: post.date,
      images: og ? [{ url: og.src, width: og.width, height: og.height, alt: `Cover of ${title}` }] : [],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description: post.summary,
      images: og ? [og.src] : [],
    },
  };
}

export default async function MusicPage({ params }: { params: Promise<Params> }) {
  const { slug = [] } = await params;
  if (slug.length === 0) return <MusicIndex />;
  if (slug.length === 1) return <MusicPost slug={slug[0]} />;
  notFound();
}

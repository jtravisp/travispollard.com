import { site } from '@/content/site';
import { rfc822 } from '@/lib/music/format';
import { readManifest, renderPost } from '@/lib/music/markdown';
import { getPosts } from '@/lib/music/posts';

/**
 * /music/feed.xml: RSS 2.0 for the reviews, written at build time.
 *
 * force-static makes the static export write this as a plain file,
 * out/music/feed.xml -- not a directory and not an .html page, despite
 * `trailingSlash: true`. tests/music.spec.ts checks exactly that.
 *
 * Each item carries the summary as <description> and the full review as
 * <content:encoded>, with image URLs made absolute so a reader renders them.
 */
export const dynamic = 'force-static';

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/** CDATA cannot contain "]]>"; split it across two sections if it appears. */
function cdata(s: string): string {
  return `<![CDATA[${s.replace(/]]>/g, ']]]]><![CDATA[>')}]]>`;
}

export function GET(): Response {
  const posts = getPosts();
  const manifest = posts.length ? readManifest() : {};
  const feedUrl = `${site.url}/music/feed.xml`;

  const items = posts.map((post) => {
    const url = `${site.url}/music/${post.slug}/`;
    const { html, notesHtml } = renderPost(post.slug, post.body, manifest);
    const full = [
      `<p>${escapeXml(post.artist)} · ${post.released} · ${post.rating}/10 · recommended by ${escapeXml(post.recommended_by)}</p>`,
      html,
      notesHtml ? `<h2>Musician's notes</h2>${notesHtml}` : '',
    ]
      .join('\n')
      // src="/music/..." and each "/music/..." inside srcset -> absolute.
      .replace(/(["\s,])\/music\//g, `$1${site.url}/music/`);
    return [
      '    <item>',
      `      <title>${escapeXml(`${post.title} by ${post.artist}`)}</title>`,
      `      <link>${url}</link>`,
      `      <guid isPermaLink="true">${url}</guid>`,
      `      <pubDate>${rfc822(post.date)}</pubDate>`,
      `      <description>${escapeXml(post.summary)}</description>`,
      `      <content:encoded>${cdata(full)}</content:encoded>`,
      ...post.tags.map((t) => `      <category>${escapeXml(t)}</category>`),
      '    </item>',
    ].join('\n');
  });

  const xml = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">',
    '  <channel>',
    `    <title>${escapeXml(`${site.name} - Music`)}</title>`,
    `    <link>${site.url}/music/</link>`,
    `    <atom:link href="${feedUrl}" rel="self" type="application/rss+xml"/>`,
    `    <description>${escapeXml(`Album reviews by ${site.name}. ${site.musicTagline}`)}</description>`,
    '    <language>en-us</language>',
    posts.length ? `    <lastBuildDate>${rfc822(posts[0].date)}</lastBuildDate>` : '',
    ...items,
    '  </channel>',
    '</rss>',
    '',
  ]
    .filter((line) => line !== '')
    .join('\n');

  return new Response(xml, {
    headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' },
  });
}

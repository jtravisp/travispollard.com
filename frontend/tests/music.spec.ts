import { expect, test } from '@playwright/test';
import matter from 'gray-matter';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

/**
 * /music against the production export in out/.
 *
 * Expectations come from content/music itself: which posts are published and
 * which are drafts is read from their front matter, so the suite stays right
 * as reviews are added. While every post is a draft (the sample), it checks
 * the empty index, the feed file, and that no draft -- page, image, sitemap
 * entry, or feed item -- reached the export. Each published post adds its own
 * template, JSON-LD and image checks.
 */

const ROOT = join(__dirname, '..');
const OUT = join(ROOT, 'out');
const CONTENT = join(ROOT, 'content', 'music');

type Front = { slug: string; title: string; artist: string; rating: number; draft: boolean };

const posts: Front[] = existsSync(CONTENT)
  ? readdirSync(CONTENT)
      .filter((d) => existsSync(join(CONTENT, d, 'index.md')))
      .map((slug) => {
        const { data } = matter(readFileSync(join(CONTENT, slug, 'index.md'), 'utf8'));
        return { slug, title: data.title, artist: data.artist, rating: data.rating, draft: data.draft };
      })
  : [];
const published = posts.filter((p) => !p.draft);
const drafts = posts.filter((p) => p.draft);

test('the index lists every published review, or says there are none', async ({ page }) => {
  await page.goto('/music/');
  await expect(page.getByRole('heading', { level: 1, name: 'Music' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Music', exact: true }).first()).toHaveAttribute(
    'aria-current',
    'page',
  );
  if (published.length === 0) {
    await expect(page.getByText('No reviews published yet.')).toBeVisible();
  } else {
    for (const p of published) {
      await expect(page.getByRole('link', { name: new RegExp(p.title) })).toBeVisible();
    }
  }
});

test('the feed exports as a plain XML file, not a directory or a page', async ({ request }) => {
  const file = join(OUT, 'music', 'feed.xml');
  expect(existsSync(file), 'out/music/feed.xml exists').toBe(true);
  expect(statSync(file).isFile(), 'out/music/feed.xml is a file').toBe(true);
  expect(existsSync(join(OUT, 'music', 'feed.xml', 'index.html'))).toBe(false);
  expect(existsSync(join(OUT, 'music', 'feed.xml.html'))).toBe(false);

  const response = await request.get('/music/feed.xml');
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('xml');
  const xml = await response.text();
  expect(xml.startsWith('<?xml')).toBe(true);
  expect(xml).toMatch(/<rss version="2\.0"/);
  expect((xml.match(/<item>/g) ?? []).length).toBe(published.length);
});

test('no draft reaches the export', async ({ request }) => {
  const sitemap = readFileSync(join(OUT, 'sitemap-0.xml'), 'utf8');
  const feed = readFileSync(join(OUT, 'music', 'feed.xml'), 'utf8');
  for (const d of drafts) {
    expect(existsSync(join(OUT, 'music', d.slug)), `out/music/${d.slug}/`).toBe(false);
    expect((await request.get(`/music/${d.slug}/`)).status()).toBe(404);
    expect(sitemap).not.toContain(`/music/${d.slug}/`);
    expect(feed).not.toContain(`/music/${d.slug}/`);
  }
});

for (const p of published) {
  test(`${p.slug}: template, structured data and images`, async ({ page }) => {
    await page.goto(`/music/${p.slug}/`);
    await expect(page.getByRole('heading', { level: 1, name: p.title })).toBeVisible();
    await expect(page.getByText(`${p.rating}/10`).first()).toBeVisible();
    await expect(page.getByText(/Recommended by/)).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Favorite tracks' })).toBeVisible();
    await expect(page).toHaveTitle(`${p.title} by ${p.artist} - Travis Pollard`);

    const ld = JSON.parse((await page.locator('script[type="application/ld+json"]').textContent()) ?? '');
    expect(ld['@type']).toBe('Review');
    expect(ld.itemReviewed['@type']).toBe('MusicAlbum');
    expect(ld.itemReviewed.byArtist.name).toBe(p.artist);
    expect(ld.reviewRating).toMatchObject({ ratingValue: p.rating, bestRating: 10, worstRating: 1 });

    for (const img of await page.locator('main img').all()) {
      await expect(img).toHaveAttribute('width', /^\d+$/);
      await expect(img).toHaveAttribute('height', /^\d+$/);
      await expect(img).toHaveAttribute('srcset', /\.webp \d+w/);
    }
  });
}

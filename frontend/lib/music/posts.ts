/**
 * The /music posts: one folder per post under content/music/<slug>/, an
 * index.md with front matter, and its images beside it.
 *
 * Read at build time only (server components and the feed route), so none of
 * this reaches the browser. Front matter is validated strictly: a missing or
 * malformed field fails the build and names the file and the field, rather
 * than rendering a post with a hole in it.
 *
 * Drafts are dropped unless this is `next dev` or MUSIC_INCLUDE_DRAFTS=1 (the
 * `npm run preview:music` build). scripts/build-music-images.mjs applies the
 * same rule to images, so a production build carries neither a draft's page
 * nor its pictures.
 */

import matter from 'gray-matter';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

export const MUSIC_DIR = join(process.cwd(), 'content', 'music');

export type StreamingLinks = {
  spotify?: string;
  apple_music?: string;
  bandcamp?: string;
};

export type PostMeta = {
  slug: string;
  title: string;
  artist: string;
  /** Release year. */
  released: number;
  /** Review date, YYYY-MM-DD. */
  date: string;
  /** One sentence: index card, meta description, RSS. */
  summary: string;
  recommended_by: string;
  /** Integer, 1-10. */
  rating: number;
  /** File name of the cover image, in the post's folder. */
  cover: string;
  favorite_tracks: string[];
  tags: string[];
  links: StreamingLinks;
  draft: boolean;
};

export type Post = PostMeta & { body: string };

export function includeDrafts(): boolean {
  return process.env.NODE_ENV === 'development' || process.env.MUSIC_INCLUDE_DRAFTS === '1';
}

class FrontMatterError extends Error {
  constructor(file: string, field: string, problem: string) {
    super(`content/music/${file}: front matter "${field}" ${problem}`);
    this.name = 'FrontMatterError';
  }
}

function toIsoDate(value: unknown, file: string): string {
  // YAML parses an unquoted 2026-09-25 into a Date; accept that or a string.
  const iso =
    value instanceof Date
      ? value.toISOString().slice(0, 10)
      : typeof value === 'string'
        ? value
        : '';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso) || Number.isNaN(Date.parse(iso))) {
    throw new FrontMatterError(file, 'date', 'must be a date written YYYY-MM-DD');
  }
  return iso;
}

function text(data: Record<string, unknown>, field: string, file: string): string {
  const v = data[field];
  if (typeof v !== 'string' || v.trim() === '') {
    throw new FrontMatterError(file, field, 'must be a non-empty string');
  }
  return v.trim();
}

function list(data: Record<string, unknown>, field: string, file: string): string[] {
  const v = data[field];
  if (!Array.isArray(v) || v.some((x) => typeof x !== 'string' || x.trim() === '')) {
    throw new FrontMatterError(file, field, 'must be a list of non-empty strings');
  }
  return v.map((x: string) => x.trim());
}

function links(value: unknown, file: string): StreamingLinks {
  if (value === undefined || value === null) return {};
  if (typeof value !== 'object' || Array.isArray(value)) {
    throw new FrontMatterError(file, 'links', 'must be a map of spotify / apple_music / bandcamp URLs');
  }
  const out: StreamingLinks = {};
  for (const [key, url] of Object.entries(value as Record<string, unknown>)) {
    if (!['spotify', 'apple_music', 'bandcamp'].includes(key)) {
      throw new FrontMatterError(file, `links.${key}`, 'is not one of spotify, apple_music, bandcamp');
    }
    if (typeof url !== 'string' || !/^https:\/\//.test(url)) {
      throw new FrontMatterError(file, `links.${key}`, 'must be an https:// URL');
    }
    out[key as keyof StreamingLinks] = url;
  }
  return out;
}

function parse(slug: string): Post {
  const file = `${slug}/index.md`;
  const { data, content } = matter(readFileSync(join(MUSIC_DIR, slug, 'index.md'), 'utf8'));

  const released = data.released;
  if (!Number.isInteger(released) || released < 1900 || released > 2100) {
    throw new FrontMatterError(file, 'released', 'must be a four-digit year');
  }
  const rating = data.rating;
  if (!Number.isInteger(rating) || rating < 1 || rating > 10) {
    throw new FrontMatterError(file, 'rating', 'must be a whole number from 1 to 10');
  }
  if (typeof data.draft !== 'boolean') {
    throw new FrontMatterError(file, 'draft', 'must be true or false');
  }
  const cover = text(data, 'cover', file).replace(/^\.\//, '');
  if (!existsSync(join(MUSIC_DIR, slug, cover))) {
    throw new FrontMatterError(file, 'cover', `names ${cover}, which is not in the post's folder`);
  }

  return {
    slug,
    title: text(data, 'title', file),
    artist: text(data, 'artist', file),
    released,
    date: toIsoDate(data.date, file),
    summary: text(data, 'summary', file),
    recommended_by: text(data, 'recommended_by', file),
    rating,
    cover,
    favorite_tracks: list(data, 'favorite_tracks', file),
    tags: list(data, 'tags', file),
    links: links(data.links, file),
    draft: data.draft,
    body: content,
  };
}

// Cached for a build, where every page asks for the same list; never in
// `next dev`, where an edited post should show on the next reload.
let cache: Post[] | null = null;

/** Every post this build should publish, newest first. */
export function getPosts(): Post[] {
  if (cache && process.env.NODE_ENV !== 'development') return cache;
  const slugs = existsSync(MUSIC_DIR)
    ? readdirSync(MUSIC_DIR).filter(
        (d) => statSync(join(MUSIC_DIR, d)).isDirectory() && existsSync(join(MUSIC_DIR, d, 'index.md')),
      )
    : [];
  const posts = slugs
    .map(parse)
    .filter((p) => includeDrafts() || !p.draft)
    .sort((a, b) => b.date.localeCompare(a.date) || a.title.localeCompare(b.title));
  cache = posts;
  return posts;
}

export function getPost(slug: string): Post | undefined {
  return getPosts().find((p) => p.slug === slug);
}

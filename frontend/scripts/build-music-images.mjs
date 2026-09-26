/**
 * Resizes and converts the /music posts' images at build time.
 *
 * Originals live beside each post (content/music/<slug>/*.jpg|png|webp|avif)
 * and are the only images committed. For each one this writes WebP at up to
 * three widths into public/music/<slug>/, and for a post's cover also a
 * 1200px JPEG for og:image -- social scrapers handle JPEG more reliably than
 * WebP. It records every output's dimensions in .music/manifest.json, which
 * the pages read to emit width/height (no layout shift) and srcset.
 *
 * Runs as `prebuild` and `predev`, so neither CodeBuild nor CI needs a new
 * step. Drafts are skipped unless --include-drafts is passed: everything in
 * public/ is deployed, so a draft's images would otherwise be published at
 * guessable URLs even though the draft post is not. `next dev` and
 * `npm run preview:music` pass the flag.
 *
 * Outputs newer than their source are left alone, and outputs whose source
 * has gone are deleted, so public/music/ never holds an orphan.
 *
 *     node scripts/build-music-images.mjs [--include-drafts]
 *     MUSIC_INCLUDE_DRAFTS=1 node scripts/build-music-images.mjs
 */

import matter from 'gray-matter';
import sharp from 'sharp';
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(ROOT, 'content', 'music');
const OUT = join(ROOT, 'public', 'music');
const MANIFEST = join(ROOT, '.music', 'manifest.json');

const WIDTHS = [480, 960, 1600];
const OG_WIDTH = 1200;
const IMAGE = /\.(jpe?g|png|webp|avif)$/i;
// The flag for `predev`; the env var for `npm run preview:music`, whose build
// runs this as `prebuild`, where no flag can be passed. Same variable the page
// loader (lib/music/posts.ts) reads, so images and pages always agree.
const includeDrafts =
  process.argv.includes('--include-drafts') || process.env.MUSIC_INCLUDE_DRAFTS === '1';

function newer(output, source) {
  return existsSync(output) && statSync(output).mtimeMs >= statSync(source).mtimeMs;
}

/** Widths to produce for an image `width` px wide: never upscale, always at least one. */
function widthsFor(width) {
  const fit = WIDTHS.filter((w) => w < width);
  const top = Math.min(width, WIDTHS[WIDTHS.length - 1]);
  return [...new Set([...fit, top])].sort((a, b) => a - b);
}

const manifest = {};
const keep = new Set();
let written = 0;

const slugs = existsSync(CONTENT)
  ? readdirSync(CONTENT).filter((d) => statSync(join(CONTENT, d)).isDirectory())
  : [];

for (const slug of slugs) {
  const dir = join(CONTENT, slug);
  const post = join(dir, 'index.md');
  if (!existsSync(post)) continue;
  const { data } = matter(readFileSync(post, 'utf8'));
  if (data.draft === true && !includeDrafts) continue;

  const cover = typeof data.cover === 'string' ? basename(data.cover) : null;
  const outDir = join(OUT, slug);
  mkdirSync(outDir, { recursive: true });

  for (const file of readdirSync(dir).filter((f) => IMAGE.test(f))) {
    const source = join(dir, file);
    const meta = await sharp(source).metadata();
    const stem = basename(file, extname(file));
    const variants = [];

    for (const w of widthsFor(meta.width)) {
      const name = `${stem}-${w}.webp`;
      const target = join(outDir, name);
      keep.add(target);
      if (!newer(target, source)) {
        await sharp(source).rotate().resize({ width: w }).webp({ quality: 80 }).toFile(target);
        written += 1;
      }
      const { width, height } = await sharp(target).metadata();
      variants.push({ src: `/music/${slug}/${name}`, width, height });
    }

    let og = null;
    if (file === cover) {
      const name = `${stem}-og.jpg`;
      const target = join(outDir, name);
      keep.add(target);
      if (!newer(target, source)) {
        await sharp(source)
          .rotate()
          .resize({ width: Math.min(OG_WIDTH, meta.width) })
          .jpeg({ quality: 82, mozjpeg: true })
          .toFile(target);
        written += 1;
      }
      const { width, height } = await sharp(target).metadata();
      og = { src: `/music/${slug}/${name}`, width, height };
    }

    manifest[`${slug}/${file}`] = { width: meta.width, height: meta.height, variants, og };
  }
}

// Delete anything this run did not produce: removed images, removed posts,
// and posts that became drafts.
if (existsSync(OUT)) {
  for (const slug of readdirSync(OUT)) {
    const outDir = join(OUT, slug);
    for (const file of readdirSync(outDir)) {
      const target = join(outDir, file);
      if (!keep.has(target)) rmSync(target);
    }
    if (readdirSync(outDir).length === 0) rmSync(outDir, { recursive: true });
  }
}

mkdirSync(dirname(MANIFEST), { recursive: true });
writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2));
console.log(
  `build-music-images: ${Object.keys(manifest).length} image(s), ${written} file(s) written` +
    (includeDrafts ? ' (drafts included)' : ''),
);

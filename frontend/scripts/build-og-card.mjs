/**
 * Renders public/images/og-card.png from HTML, reproducibly.
 *
 * The card this replaces was a hand-made PNG, which is why it still read
 * "Cloud / DevOps Engineer" months after the site stopped saying that -- the
 * one image nobody can grep and nobody remembers to open. This one is built
 * from `content/site.ts` and the same accent value as the dark theme, so the
 * next title change is a rebuild rather than a design tool.
 *
 * Playwright rather than a canvas library because it is already a dev
 * dependency and the card is a web page: real font shaping, real layout, and
 * the headshot loaded from the same file the site serves.
 *
 * It also draws public/images/og-music.png, the link card for /music: the same
 * frame, "Music" and the section's tagline, and a record in place of the
 * headshot -- drawn, not an album cover, so it never goes stale as reviews are
 * added and carries no one else's artwork.
 *
 * Deliberately NOT wired into `npm run build`. It needs a browser binary that
 * the CodeBuild image installs separately, and the card changes about once a
 * year -- a build step that can fail for a reason unrelated to the diff, in
 * service of an asset that rarely moves, is a bad trade. Run it by hand:
 *
 *     node scripts/build-og-card.mjs          # both cards
 *     node scripts/build-og-card.mjs music    # just og-music.png
 *     node scripts/build-og-card.mjs home     # just og-card.png
 *
 * Rebuild only the card whose text changed: a re-render of an unchanged card
 * differs in a few anti-aliased pixels and shows up as a pointless diff.
 */

import { chromium } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = resolve(ROOT, 'public/images/og-card.png');
const OUT_MUSIC = resolve(ROOT, 'public/images/og-music.png');
const which = process.argv[2] ?? 'all';
if (!['all', 'home', 'music'].includes(which)) {
  throw new Error(`build-og-card: unknown card "${which}" (all, home or music)`);
}

// Read the facts from the same file the site renders, rather than retyping
// them into a design and letting the two drift.
const siteSrc = readFileSync(resolve(ROOT, 'content/site.ts'), 'utf8');
// Deliberately not a regex. The values span lines and contain colons and
// apostrophes, and an escaping slip in a pattern fails by silently matching the
// wrong thing. Find the key, then take the next single-quoted run after it.
const field = (name) => {
  const at = siteSrc.indexOf(`${name}:`);
  if (at === -1) throw new Error(`build-og-card: no ${name} in content/site.ts`);
  const open = siteSrc.indexOf("'", at);
  const close = siteSrc.indexOf("'", open + 1);
  if (open === -1 || close === -1) {
    throw new Error(`build-og-card: could not read ${name} from content/site.ts`);
  }
  return siteSrc.slice(open + 1, close);
};

const NAME = field('name');
const ROLE = field('role');
const VALUE = field('valueStatement');
const MUSIC_TAGLINE = field('musicTagline');

// The dark theme's own values, from app/globals.css.
const BG = '#14161a';
const FG = '#e9e7e4';
const ACCENT = '#d77b64';
const MUTED = '#9a9691';

const photo = readFileSync(resolve(ROOT, 'public/headshot.jpeg')).toString('base64');

const html = `<!doctype html>
<html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width:1200px; height:630px; background:${BG}; color:${FG};
    font-family:Inter,system-ui,sans-serif; display:flex; align-items:center;
    gap:72px; padding:0 84px; position:relative; overflow:hidden;
  }
  /* The accent bar, matching the site's single-accent rule. */
  body::before {
    content:''; position:absolute; left:0; top:0; bottom:0; width:10px;
    background:${ACCENT};
  }
  .text { flex:1; min-width:0; }
  .eyebrow { font-size:26px; color:${MUTED}; margin-bottom:14px; }
  h1 { font-size:76px; font-weight:800; letter-spacing:-0.025em; line-height:1.04; }
  .role { font-size:40px; font-weight:600; color:${ACCENT}; margin-top:10px; }
  .value { font-size:25px; line-height:1.5; color:${MUTED}; margin-top:26px; max-width:33ch; }
  .domain { font-size:23px; color:${MUTED}; margin-top:34px; }
  .photo-wrap {
    width:340px; height:340px; border-radius:50%; padding:5px;
    background:${ACCENT}; flex-shrink:0;
    box-shadow:0 0 90px -16px ${ACCENT};
  }
  .photo { width:100%; height:100%; border-radius:50%; object-fit:cover; display:block; }
</style></head>
<body>
  <div class="text">
    <div class="eyebrow">Hi, I&rsquo;m Travis</div>
    <h1>${NAME}</h1>
    <div class="role">${ROLE}</div>
    <div class="value">${VALUE}</div>
    <div class="domain">travispollard.com</div>
  </div>
  <div class="photo-wrap"><img class="photo" src="data:image/jpeg;base64,${photo}"></div>
</body></html>`;

// The /music card: the same frame and type, with a record where the photo is.
// Grooves are a repeating radial gradient, the label is the accent, and a
// faint conic sheen keeps it from reading as a flat black disc.
const musicHtml = html
  .replace(
    /<body>[\s\S]*<\/body>/,
    `<body>
  <div class="text">
    <div class="eyebrow">travispollard.com/music</div>
    <h1>Music</h1>
    <div class="role">Album reviews</div>
    <div class="value">${MUSIC_TAGLINE}</div>
    <div class="domain">by ${NAME}</div>
  </div>
  <div class="record"><div class="label"><div class="hole"></div></div></div>
</body>`,
  )
  .replace(
    '</style>',
    `  .record {
    width:360px; height:360px; border-radius:50%; flex-shrink:0; position:relative;
    background:
      conic-gradient(from 30deg, transparent 0 40deg, rgba(255,255,255,0.07) 60deg, transparent 80deg 220deg, rgba(255,255,255,0.05) 240deg, transparent 260deg),
      repeating-radial-gradient(circle at center, #1d2025 0 2px, #0c0d10 2px 4px);
    box-shadow:0 0 90px -16px ${ACCENT};
  }
  .label {
    position:absolute; inset:34%; border-radius:50%; background:${ACCENT};
    display:flex; align-items:center; justify-content:center;
  }
  .hole { width:14px; height:14px; border-radius:50%; background:${BG}; }
</style>`,
  );

const cards = [
  ...(which !== 'music' ? [{ path: OUT, markup: html }] : []),
  ...(which !== 'home' ? [{ path: OUT_MUSIC, markup: musicHtml }] : []),
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
for (const card of cards) {
  await page.setContent(card.markup, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  await page.screenshot({ path: card.path });
  console.log(`build-og-card: wrote ${card.path} (1200x630)`);
}
await browser.close();

console.log(`  name:  ${NAME}`);
console.log(`  role:  ${ROLE}`);
console.log(`  value: ${VALUE}`);
console.log(`  music: ${MUSIC_TAGLINE}`);

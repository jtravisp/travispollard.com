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
 * Deliberately NOT wired into `npm run build`. It needs a browser binary that
 * the CodeBuild image installs separately, and the card changes about once a
 * year -- a build step that can fail for a reason unrelated to the diff, in
 * service of an asset that rarely moves, is a bad trade. Run it by hand:
 *
 *     node scripts/build-og-card.mjs
 */

import { chromium } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = resolve(ROOT, 'public/images/og-card.png');

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

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await page.setContent(html, { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(400);
await page.screenshot({ path: OUT });
await browser.close();

console.log(`build-og-card: wrote ${OUT} (1200x630)`);
console.log(`  name:  ${NAME}`);
console.log(`  role:  ${ROLE}`);
console.log(`  value: ${VALUE}`);

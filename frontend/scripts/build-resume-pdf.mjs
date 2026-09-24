/**
 * Renders the resume PDF from the exported /resume page.
 *
 * The PDF in public/ was a separate document kept in sync by hand, and it was
 * not: it still listed a certificate and a job the resume had dropped. This
 * prints `ResumePrint` -- the print-only rendering of `content/resume.ts` --
 * so the download and the page come from the same strings.
 *
 * It prints the built site rather than a dev server, because the export is
 * what ships, and it forces the light theme so nothing depends on which theme
 * the printing browser happened to prefer.
 *
 * Needs `out/` (run `npm run build` first) and a Playwright Chromium.
 *
 *     node scripts/build-resume-pdf.mjs [output.pdf]
 *
 * Defaults to writing into out/, next to the page that links to it.
 */

import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = resolve(process.argv[2] ?? resolve(ROOT, 'out', 'Travis Pollard Resume.pdf'));
// Not 4321: that is Playwright's webServer, which may already be running.
const PORT = 4329;

const server = spawn(process.execPath, ['tests/serve-out.mjs'], {
  cwd: ROOT,
  env: { ...process.env, PORT: String(PORT) },
  stdio: 'ignore',
});

try {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.addInitScript(() => localStorage.setItem('theme', 'light'));

  let lastError;
  for (let attempt = 0; attempt < 40; attempt++) {
    try {
      await page.goto(`http://127.0.0.1:${PORT}/resume/`, { waitUntil: 'load' });
      lastError = null;
      break;
    } catch (error) {
      lastError = error;
      await new Promise((r) => setTimeout(r, 250));
    }
  }
  if (lastError) throw lastError;

  await page.evaluate(() => document.fonts.ready);
  await page.pdf({
    path: OUT,
    format: 'Letter',
    margin: { top: '0.55in', bottom: '0.55in', left: '0.65in', right: '0.65in' },
    printBackground: false,
  });
  await browser.close();
  console.log(`build-resume-pdf: wrote ${OUT}`);
} finally {
  server.kill();
}

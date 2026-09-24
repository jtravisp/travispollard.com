/**
 * Fails a production build if a TODO(travis) marker reached the rendered site.
 *
 * The markers are deliberate: unverified claims render in dev so they stay in
 * front of whoever can answer them, rather than hiding in a comment nobody
 * opens. They must not reach a visitor, and `content/projects.ts` filtering
 * them out in production is easy to break -- a new component that renders
 * `items` without the filter would ship them silently.
 *
 * So this checks the output rather than the intent. It greps the exported HTML,
 * which is the only artifact that matters, and it cannot be fooled by where the
 * string came from.
 *
 * Exits 0 with a note when `out/` is absent, because `next-sitemap` and this
 * both run at postbuild and a missing export is already a louder failure.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'out');
const MARKER = 'TODO(travis)';

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.(html|txt|json|xml)$/i.test(entry)) out.push(full);
  }
  return out;
}

let files;
try {
  files = walk(ROOT);
} catch {
  console.log('check-no-todos: no out/ directory, skipping');
  process.exit(0);
}

const offenders = [];
for (const file of files) {
  const body = readFileSync(file, 'utf8');
  if (!body.includes(MARKER)) continue;
  // Context around the marker, not the line it sits on: exported HTML is
  // minified onto a single line, so "the line" is the whole document and
  // points at nothing.
  const at = body.indexOf(MARKER);
  const excerpt = body
    .slice(Math.max(0, at - 70), at + 90)
    .replace(/\s+/g, ' ')
    .trim();
  offenders.push(`  ${relative(ROOT, file)}\n    ...${excerpt}...`);
}

if (offenders.length > 0) {
  console.error(
    `\ncheck-no-todos: ${offenders.length} file(s) in the export still contain ${MARKER}:\n\n` +
      offenders.join('\n\n') +
      `\n\nThese are meant to render in dev only. Either answer the TODO in ` +
      `content/, or make sure the rendering path strips markers in production.\n`
  );
  process.exit(1);
}

console.log(`check-no-todos: ${files.length} exported files clean`);

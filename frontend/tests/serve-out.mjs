/**
 * A static file server for the exported site, for Playwright.
 *
 * Node's own http and fs, no dependency: the alternative was adding a package to
 * serve seventeen files, and the CI image already has node.
 *
 * Serves `frontend/out`, which means `npm run build` has to have run first. CI
 * already does that — `buildspec.yml` builds and then runs Playwright — and
 * locally the failure is a plain 404 rather than something subtler.
 */

import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, extname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

// `fileURLToPath` rather than `.pathname`: on Windows the latter yields
// "/C:/..." with forward slashes, which then matches nothing `join` or `resolve`
// produces and silently defeats the containment check below.
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'out');
const PORT = Number(process.env.PORT ?? 4321);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.png': 'image/png',
  '.txt': 'text/plain; charset=utf-8',
  '.woff2': 'font/woff2',
};

createServer((request, response) => {
  const url = new URL(request.url, `http://localhost:${PORT}`);

  // Leading and trailing separators are stripped before resolving: "/cfb/" has
  // to become "cfb", not "cfb\", which existsSync rejects on Windows.
  const relative = decodeURIComponent(url.pathname).replace(/^[/\\]+|[/\\]+$/g, '');

  // `resolve` against ROOT collapses any ".." before the containment check below,
  // so a traversal cannot escape out/.
  let file = relative ? resolve(ROOT, relative) : ROOT;

  const contained = file === ROOT || file.startsWith(ROOT + sep);

  // `trailingSlash: true`, so a directory means its index.html.
  if (contained && existsSync(file) && statSync(file).isDirectory()) {
    file = join(file, 'index.html');
  }

  if (!contained || !existsSync(file)) {
    response.writeHead(404, { 'content-type': 'text/plain' });
    response.end(`not found: ${relative}`);
    return;
  }

  response.writeHead(200, {
    'content-type': TYPES[extname(file)] ?? 'application/octet-stream',
  });
  createReadStream(file).pipe(response);
}).listen(PORT, () => {
  console.log(`serving out/ on http://127.0.0.1:${PORT}`);
});

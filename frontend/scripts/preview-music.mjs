/**
 * Local preview of /music, drafts included, as the production build renders it.
 *
 *     npm run preview:music      ->  http://127.0.0.1:4321/music/
 *
 * Runs the normal `npm run build` with MUSIC_INCLUDE_DRAFTS=1 -- which the
 * image step, the page loader and next-sitemap all read -- then serves out/
 * with the same static server the Playwright suite uses. Ctrl+C stops it.
 *
 * The out/ this leaves behind contains drafts. Deploys build their own out/
 * from a clean checkout, so that is harmless, but do not upload this one by
 * hand. A plain `npm run build` afterwards removes the drafts again, images
 * included.
 *
 * For editing, `npm run dev` (http://localhost:3000/music/) is quicker: it
 * shows drafts and reloads on save. This is for seeing the exported result.
 */

import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const env = { ...process.env, MUSIC_INCLUDE_DRAFTS: '1' };

function run(command, args) {
  return new Promise((resolveRun, reject) => {
    const child = spawn(command, args, { cwd: ROOT, env, stdio: 'inherit', shell: process.platform === 'win32' });
    child.on('exit', (code) => (code === 0 ? resolveRun() : reject(new Error(`${command} ${args.join(' ')} exited ${code}`))));
  });
}

await run('npm', ['run', 'build']);
console.log('\npreview-music: drafts included. Open http://127.0.0.1:4321/music/  (Ctrl+C to stop)\n');
await run(process.execPath, ['tests/serve-out.mjs']);

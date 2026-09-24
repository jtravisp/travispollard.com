/**
 * Flat config, because `next lint` had none.
 *
 * `npm run lint` used to drop into `next lint`'s interactive "how would you
 * like to configure ESLint?" prompt, which in CI is a job that hangs until the
 * timeout rather than one that fails -- which is why `frontend-ci.yml` skipped
 * linting entirely and said so in a comment. This is that comment's fix.
 *
 * `FlatCompat` rather than a native flat export: `eslint-config-next` is still
 * published in eslintrc shape, so the compat bridge is how it loads at all.
 */

import { FlatCompat } from '@eslint/eslintrc';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const compat = new FlatCompat({
  baseDirectory: dirname(fileURLToPath(import.meta.url)),
});

const config = [
  {
    // Build output and vendored assets. `out/` in particular holds the
    // exported site, which is minified and not ours to lint.
    ignores: [
      '.next/**',
      'out/**',
      'node_modules/**',
      'playwright-report/**',
      'test-results/**',
      'next-env.d.ts',
    ],
  },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    rules: {
      // The site is a static export with no image optimizer, so `next/image`
      // cannot do its job and every `<img>` would be flagged forever. Turning
      // it off is honest; leaving it on and ignoring the output is not.
      '@next/next/no-img-element': 'off',

      // Underscore-prefixed means "deliberately unused" and rest-sibling
      // destructuring is how the Playwright specs omit a key from a fixture
      // (`({ elo_state, ...rest }) => rest`). Both are intent, not oversight.
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
          ignoreRestSiblings: true,
        },
      ],
    },
  },
];

export default config;

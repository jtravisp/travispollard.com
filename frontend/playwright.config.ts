import { defineConfig, devices } from '@playwright/test';

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
// import dotenv from 'dotenv';
// import path from 'path';
// dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: './tests',

  /* The whole run, not one test.
   *
   * A CodeBuild run hung for 969 seconds on 2026-08-29 and had to be stopped by
   * hand. The tests themselves finished in 31 seconds; everything after that was
   * the HTML reporter serving a report and waiting for a Ctrl+C that never comes
   * in CI. Per-test timeouts could not have caught it, because no test was
   * running.
   *
   * Five minutes is roughly ten times the suite's honest runtime, so it bounds a
   * hang without failing a merely slow day. The specific cause is fixed below;
   * this exists because the next unbounded thing will not be a reporter. */
  globalTimeout: 5 * 60 * 1000,

  /* Per test, so one wedged assertion cannot consume the whole budget. */
  timeout: 30 * 1000,
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Opt out of parallel tests on CI. */
  workers: process.env.CI ? 1 : undefined,
  /* `open: 'never'` is the fix for the hang described above.
   *
   * Playwright's html reporter starts a web server and blocks when a run has
   * failures. It suppresses that when `process.env.CI` is set -- and CodeBuild
   * does not set `CI`, so the container behaved exactly like a laptop and waited
   * for someone to press Ctrl+C. Writing the report without serving it keeps the
   * artifact and removes the block, whether or not `CI` is set. */
  reporter: [['html', { open: 'never' }], ['line']],
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: 'http://127.0.0.1:4321',

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },

    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },

    /* webkit is deliberately absent.
     *
     * It cannot launch on this CI image -- Amazon Linux 2023 supplies none of
     * libicudata.so.66, libwoff2dec.so.1.0.2, libx264.so and eleven more, and
     * the usual remedy (`playwright install --with-deps`) shells out to apt-get,
     * which this image does not have either. On 2026-08-29 all 7 CI failures
     * were webkit; chromium and firefox ran clean.
     *
     * Dropping it costs nothing this project was actually getting. **webkit on
     * Linux is not what tests Safari on iOS** -- different rendering stack,
     * different fonts, different media support, and no touch or viewport
     * behaviour of an actual phone. It reads like Safari coverage and is not.
     *
     * If cross-browser coverage matters later, the fix is a **different
     * CodeBuild image** with the libraries -- an Ubuntu-based one, or
     * Playwright's own container -- not a dependency flag on this one. */

    /* Test against mobile viewports. */
    // {
    //   name: 'Mobile Chrome',
    //   use: { ...devices['Pixel 5'] },
    // },
    // {
    //   name: 'Mobile Safari',
    //   use: { ...devices['iPhone 12'] },
    // },

    /* Test against branded browsers. */
    // {
    //   name: 'Microsoft Edge',
    //   use: { ...devices['Desktop Edge'], channel: 'msedge' },
    // },
    // {
    //   name: 'Google Chrome',
    //   use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    // },
  ],

  /* Serve the exported site so route specs run against the real build.
   *
   * `next start` cannot be used: next.config.ts sets `output: 'export'`, so
   * there is no server to start. tests/serve-out.mjs is node's http and fs and
   * nothing else.
   *
   * This requires `npm run build` to have run. CI already builds before running
   * Playwright (buildspec.yml), and locally a missing build fails as a plain 404
   * rather than something subtler. The visitor-counter spec talks to a live API
   * and ignores this server entirely. */
  webServer: {
    command: 'node tests/serve-out.mjs',
    url: 'http://127.0.0.1:4321/cfb/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});

import { expect, test } from '@playwright/test';

/**
 * `/cfb/slate` — which week the reader is looking at.
 *
 * The generator holds the board on a week that still has games ahead, even when
 * a later one is forecast. That is the right call and it is invisible: two boards
 * render identically, and the only thing separating "week 1, deliberately" from
 * "the pipeline is stuck on week 1" is what the page says.
 */

const BASE = {
  schema_version: 2,
  generated_at: '2026-09-04T12:30:00Z',
  season: 2026,
  team: 'Texas',
  priced: 1,
  forecast_from: null,
  excluded_non_fbs: 0,
  results_known_at: '2026-08-30T12:00:00Z',
  games: [
    {
      cfbd_game_id: 13,
      kickoff: '2026-09-05T19:30:00Z',
      home: 'Texas',
      away: 'Texas State',
      neutral_site: false,
      predicted_margin: 39.3,
      win_probability: 0.9893,
      market_line: -30.5,
      line_source: 'DraftKings',
      featured: true,
      played: false,
      home_elo: 2113.0,
      away_elo: 1375.0,
    },
  ],
};

test('the week is in the heading, not only in a badge', async ({ page }) => {
  await page.route('**/cfb/data/slate.json*', (route) =>
    route.fulfill({ json: { ...BASE, week: '01', next_week_forecast: null } }),
  );
  await page.goto('/cfb/slate/');

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Week 1 slate');
});

test('a held board says it is held, and names the week waiting', async ({ page }) => {
  await page.route('**/cfb/data/slate.json*', (route) =>
    route.fulfill({ json: { ...BASE, week: '01', next_week_forecast: '02' } }),
  );
  await page.goto('/cfb/slate/');

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Week 1 slate');
  await expect(page.getByText(/this is week 1, and it is still being played/i)).toBeVisible();
  await expect(page.getByText(/Week 2 is already forecast/)).toBeVisible();
});

test('an ordinary week says nothing about being held', async ({ page }) => {
  await page.route('**/cfb/data/slate.json*', (route) =>
    route.fulfill({ json: { ...BASE, week: '04', next_week_forecast: null } }),
  );
  await page.goto('/cfb/slate/');

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Week 4 slate');
  await expect(page.getByText(/still being played/)).toHaveCount(0);
});

test('a document without the field renders, and claims nothing', async ({ page }) => {
  /** The window between deploying this route and the next publish. */
  await page.route('**/cfb/data/slate.json*', (route) =>
    route.fulfill({ json: { ...BASE, week: '01' } }),
  );
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/cfb/slate/');

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Week 1 slate');
  await expect(page.getByText(/still being played/)).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('the held notice is laid out at full width, not in a ribbon', async ({ page }) => {
  /**
   * daisyUI's `.alert` is `display: grid; grid-auto-flow: column`, so each direct
   * child becomes a column. This notice is a second alert on the page and the
   * first one already shipped that bug once — see `cfb-slate.spec.ts`. Measuring
   * the box is the only check that catches it.
   */
  await page.route('**/cfb/data/slate.json*', (route) =>
    route.fulfill({ json: { ...BASE, week: '01', next_week_forecast: '02' } }),
  );
  await page.goto('/cfb/slate/');

  const notice = page.getByText(/Week 2 is already forecast/);
  const box = await notice.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThan(400);
});

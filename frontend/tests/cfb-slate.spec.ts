import { expect, test } from '@playwright/test';

/**
 * `/cfb/slate` — layout and scope.
 *
 * The width assertion here is unusual and deliberate. daisyUI's `.alert` is
 * `display: grid; grid-auto-flow: column`, so every *direct child* becomes a
 * column. Two sibling `<p>` elements rendered as a full-width paragraph beside a
 * ribbon about ten characters wide down the right edge — and the squeezed one was
 * the paragraph explaining why games are missing from the slate.
 *
 * Nothing else would have caught it. The markup is valid, the text is present,
 * every `getByText` passes, and the build is clean. It is only wrong once it has
 * been laid out, which is why the test measures a box rather than reading a
 * string.
 */

const SLATE = {
  schema_version: 2,
  generated_at: '2026-08-29T22:12:38.188325Z',
  season: 2026,
  week: '01',
  team: 'Texas',
  priced: 96,
  forecast_from: '2026-08-29T18:00:00Z',
  excluded_non_fbs: 48,
  games: [
    {
      cfbd_game_id: 1,
      kickoff: '2026-09-05T19:30:00Z',
      home: 'Texas',
      away: 'Texas State',
      neutral_site: false,
      predicted_margin: 39.3,
      win_probability: 0.9893,
      market_line: -30.5,
      line_source: 'DraftKings',
      featured: true,
    },
    {
      cfbd_game_id: 2,
      kickoff: '2026-09-05T23:00:00Z',
      home: 'Stanford',
      away: "Hawai'i",
      neutral_site: false,
      predicted_margin: 6.1,
      win_probability: 0.62,
      market_line: null,
      line_source: null,
      featured: false,
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route('**/cfb/data/slate.json*', (route) => route.fulfill({ json: SLATE }));
});

test('the footnote paragraphs are laid out at full width, not in a ribbon', async ({
  page,
}) => {
  await page.goto('/cfb/slate/');

  const explanation = page.getByText(/Games that had already kicked off/);
  await expect(explanation).toBeVisible();

  const box = await explanation.boundingBox();
  expect(box).not.toBeNull();

  // The container is max-w-5xl on a 1280-wide viewport, so a healthy paragraph
  // is many hundreds of pixels. The bug rendered this one at roughly 80.
  expect(box!.width).toBeGreaterThan(400);

  // And about as wide as the paragraph above it, since they are siblings in the
  // same block. `getByText` resolves to the smallest element containing the
  // string, which for the first paragraph is its leading <strong> -- so match the
  // paragraph itself rather than the phrase inside it.
  const first = page.locator('p', { hasText: /This week is longer than a week/ }).last();
  const firstBox = await first.boundingBox();
  expect(Math.abs(box!.width - firstBox!.width)).toBeLessThan(40);
});

test('the slate is FBS games only, and says how many it left out', async ({ page }) => {
  await page.goto('/cfb/slate/');

  await expect(page.getByText('2 games')).toBeVisible();
  await expect(
    page.getByText(/48 more forecast, not shown — both teams outside the FBS/),
  ).toBeVisible();
});

test('a document without the count still renders', async ({ page }) => {
  /** The window between deploying these routes and the next publish. */
  const { excluded_non_fbs: _dropped, ...withoutCount } = SLATE;
  await page.route('**/cfb/data/slate.json*', (route) =>
    route.fulfill({ json: withoutCount }),
  );

  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/cfb/slate/');
  await expect(page.getByText('2 games')).toBeVisible();
  await expect(page.getByText(/more forecast, not shown/)).toHaveCount(0);
  expect(errors).toEqual([]);
});

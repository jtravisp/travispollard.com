import { expect, test } from '@playwright/test';

/**
 * `/cfb/slate` — the board is browsable.
 *
 * Both behaviours here are the kind that regress silently. A default sort is one
 * word in one `useState`; get it wrong and the page still renders ninety-six
 * correct rows, in the order that buries the interesting ones. An expanded row is
 * conditional markup; break the toggle and nothing throws, the detail simply
 * never appears.
 */

/** Deliberately out of both orders, so neither sort can pass by accident. */
const SLATE = {
  schema_version: 2,
  generated_at: '2026-08-29T22:12:38.188325Z',
  season: 2026,
  week: '01',
  team: 'Texas',
  priced: 2,
  forecast_from: null,
  excluded_non_fbs: 0,
  results_known_at: null,
  games: [
    {
      // First to kick off, and the model and the book nearly agree.
      cfbd_game_id: 1,
      kickoff: '2026-09-05T16:00:00Z',
      home: 'Michigan',
      away: 'Purdue',
      neutral_site: false,
      predicted_margin: 14.2,
      win_probability: 0.88,
      market_line: -14.5,
      line_source: 'DraftKings',
      featured: false,
      played: false,
      home_elo: 1920.5,
      away_elo: 1637.1,
    },
    {
      // No book priced it, so it has no edge at all -- not a small one.
      cfbd_game_id: 2,
      kickoff: '2026-09-05T18:00:00Z',
      home: 'Stanford',
      away: "Hawai'i",
      neutral_site: false,
      predicted_margin: 6.1,
      win_probability: 0.62,
      market_line: null,
      line_source: null,
      featured: false,
      played: false,
      home_elo: 1502.0,
      away_elo: 1380.0,
    },
    {
      // Last to kick off, and the biggest disagreement on the board: 15.5.
      cfbd_game_id: 3,
      kickoff: '2026-09-05T23:00:00Z',
      home: 'Idaho State',
      away: 'Nevada',
      neutral_site: false,
      predicted_margin: 19.0,
      win_probability: 0.91,
      market_line: -34.5,
      line_source: 'DraftKings',
      featured: false,
      played: false,
      home_elo: 1610.0,
      away_elo: 1230.0,
    },
  ],
};

/** The matchup text of each body row, top to bottom, ignoring detail rows. */
async function order(page: import('@playwright/test').Page) {
  return page.locator('tbody tr td:nth-child(2) button').allInnerTexts();
}

test.beforeEach(async ({ page }) => {
  await page.route('**/cfb/data/slate.json*', (route) => route.fulfill({ json: SLATE }));
  await page.goto('/cfb/slate/');
});

test('the default sort is disagreement, not kickoff', async ({ page }) => {
  // Idaho State is 15.5 points from the book and kicks off last; Michigan is 0.3
  // from it and kicks off first. Chronological order is exactly backwards.
  expect(await order(page)).toEqual([
    'Nevada at Idaho State',
    'Purdue at Michigan',
    "Hawai'i at Stanford",
  ]);

  await expect(page.getByRole('button', { name: 'Biggest disagreement' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('a game no book priced sorts last rather than as an agreement', async ({ page }) => {
  // Stanford has no line, so it has no disagreement -- and lands below Michigan,
  // which the book is within half a point of. An unpriced game read as an edge of
  // zero would be making the much stronger claim that the two sides agree.
  const rows = await order(page);
  expect(rows.indexOf("Hawai'i at Stanford")).toBe(rows.length - 1);
});

test('kickoff order is still available, and is a different order', async ({ page }) => {
  await page.getByRole('button', { name: 'Kickoff' }).click();

  expect(await order(page)).toEqual([
    'Purdue at Michigan',
    "Hawai'i at Stanford",
    'Nevada at Idaho State',
  ]);
});

test('a row expands to the same detail the featured game gets', async ({ page }) => {
  const matchup = page.getByRole('button', { name: 'Nevada at Idaho State' });
  await expect(matchup).toHaveAttribute('aria-expanded', 'false');

  await matchup.click();
  await expect(matchup).toHaveAttribute('aria-expanded', 'true');

  const detail = page.locator('#game-3-detail');
  await expect(detail).toBeVisible();
  await expect(detail.getByText('Idaho State 1610')).toBeVisible();
  await expect(detail.getByText('Nevada 1230')).toBeVisible();
  // 380 Elo / 20 per point = 19 points of margin before home advantage.
  await expect(detail.getByText(/380-point gap, roughly 19 points/)).toBeVisible();
  await expect(detail.getByText(/15\.5 points apart/)).toBeVisible();

  await matchup.click();
  await expect(page.locator('#game-3-detail')).toHaveCount(0);
});

test('two rows can be open at once, so they can be compared', async ({ page }) => {
  await page.getByRole('button', { name: 'Nevada at Idaho State' }).click();
  await page.getByRole('button', { name: 'Purdue at Michigan' }).click();

  await expect(page.locator('#game-3-detail')).toBeVisible();
  await expect(page.locator('#game-1-detail')).toBeVisible();
});

test('an unpriced row says so rather than showing an edge of zero', async ({ page }) => {
  await page.getByRole('button', { name: "Hawai'i at Stanford" }).click();

  const detail = page.locator('#game-2-detail');
  await expect(detail.getByText('no book priced this game')).toBeVisible();
  await expect(detail.getByText(/points apart/)).toHaveCount(0);
});

test('a document without the ratings still expands', async ({ page }) => {
  /** The window between deploying this route and the next publish. */
  await page.route('**/cfb/data/slate.json*', (route) =>
    route.fulfill({
      json: {
        ...SLATE,
        games: SLATE.games.map(({ home_elo: _h, away_elo: _a, ...game }) => game),
      },
    }),
  );
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/cfb/slate/');
  await page.getByRole('button', { name: 'Nevada at Idaho State' }).click();

  const detail = page.locator('#game-3-detail');
  await expect(detail.getByText(/15\.5 points apart/)).toBeVisible();
  await expect(detail.getByText(/point gap/)).toHaveCount(0);
  expect(errors).toEqual([]);
});

import { expect, test } from '@playwright/test';

/**
 * `/cfb/models` — the bake-off route (SPEC-phase2 6.1).
 *
 * The assertions here are about the two things the page exists to keep honest,
 * not about its layout:
 *
 * **The shared denominator has to be on the page** (§6.3). The whole document is
 * a comparison between rows, and a leaderboard whose rows were computed on
 * different sets of games is not a comparison at all. The count is what tells a
 * reader the rows are commensurable, so a page that dropped it would look right
 * and mean nothing.
 *
 * **A null is an em dash and never a zero** (SPEC-phase1 5.3). The benchmarks
 * publish no win probability, so their Brier cell is empty on purpose. Rendered
 * as `0` it would read as a perfect score for the market — the single most
 * misleading thing this page could print.
 */

const MODELS = {
  schema_version: 3,
  generated_at: '2026-10-05T12:30:00Z',
  season: 2026,
  week: '06',
  through_week: '05',
  shared_denominator: { games: 402, description: 'games every system priced' },
  systems: [
    {
      id: 'elo',
      label: 'This model (Elo)',
      mae: 12.94,
      brier: 0.1912,
      ats: {
        record: '104-98',
        wins: 104,
        losses: 98,
        pushes: 0,
        excluded_no_line: 12,
        excluded_no_edge: 4,
      },
      coverage: { priced: 402, of: 402 },
      is_ours: true,
    },
    {
      id: 'market',
      label: 'The market',
      mae: 11.81,
      brier: null,
      ats: null,
      coverage: { priced: 402, of: 900 },
      is_benchmark: true,
    },
    {
      id: 'sagarin',
      label: 'Sagarin PREDICTOR',
      mae: 13.02,
      brier: null,
      ats: null,
      coverage: { priced: 500, of: 900 },
      is_benchmark: true,
    },
  ],
  by_week: [
    { week: '01', games: 80, mae: { elo: 14.2, market: 12.4, sagarin: 14.9 } },
    { week: '05', games: 92, mae: { elo: 12.1, market: 11.2, sagarin: 12.6 } },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route('**/cfb/data/models.json*', (route) => route.fulfill({ json: MODELS }));
});

test('the shared denominator is stated, because the rows mean nothing without it', async ({
  page,
}) => {
  await page.goto('/cfb/models/');

  await expect(page.getByText(/402/).first()).toBeVisible();
  await expect(page.getByText(/games every system priced/)).toBeVisible();
});

/**
 * Scoped to the leaderboard, because the week-by-week table below it carries the
 * same system labels as *column headers* -- so an unscoped row lookup matches
 * both and Playwright's strict mode rejects it. Naming the section is the right
 * fix rather than `.first()`: the two tables answer different questions and a
 * test should say which one it is asserting about.
 */
function leaderboard(page: import('@playwright/test').Page) {
  return page.locator('section').filter({ hasText: 'On the shared games' });
}

test('a benchmark with no win probability shows a dash, not a zero', async ({ page }) => {
  await page.goto('/cfb/models/');

  const market = leaderboard(page).getByRole('row').filter({ hasText: 'The market' });
  await expect(market).toBeVisible();

  // The Brier cell specifically: a `0` here would read as the market scoring
  // perfectly at something it never published.
  const cells = market.getByRole('cell');
  await expect(cells.nth(2)).toHaveText('—');
  await expect(cells.nth(2)).not.toHaveText(/0/);
});

test('coverage is shown beside the headline, so reach and accuracy are not confused', async ({
  page,
}) => {
  await page.goto('/cfb/models/');

  // Sagarin priced 500 of 900 while its MAE is computed on the shared 402. The
  // page has to be able to say both without implying the figure covers 500.
  await expect(
    leaderboard(page).getByRole('row').filter({ hasText: 'Sagarin PREDICTOR' }),
  ).toContainText('500 of 900');
  await expect(
    leaderboard(page).getByRole('row').filter({ hasText: 'This model (Elo)' }),
  ).toContainText('402 of 402');
});

test('the ridge model is absent, because it failed the gate', async ({ page }) => {
  await page.goto('/cfb/models/');

  // SPEC-phase2 6.4 makes clearing 5.6's gate the condition for appearing here,
  // and it did not clear. Asserted on the page as well as in the generator: a row
  // arriving later should be a decision somebody argued, not a diff nobody read.
  await expect(page.getByText(/efficiency/)).toHaveCount(0);
  await expect(
    leaderboard(page).getByRole('row').filter({ hasText: 'This model (Elo)' }),
  ).toBeVisible();
});

test('an unscored season says so rather than printing an empty table', async ({ page }) => {
  await page.route('**/cfb/data/models.json*', (route) =>
    route.fulfill({
      json: {
        ...MODELS,
        through_week: null,
        shared_denominator: { games: 0, description: 'games every system priced' },
        systems: MODELS.systems.map((system) => ({ ...system, mae: null, brier: null })),
        by_week: [],
      },
    }),
  );
  await page.goto('/cfb/models/');

  await expect(page.getByText(/No week has been scored yet/)).toBeVisible();
});

test('a document from a newer generator refuses rather than rendering', async ({ page }) => {
  // §6.2's whole point: the site and the pipeline deploy independently, so this
  // is an ordinary few minutes rather than a bug — and the page must not read
  // fields whose meaning may have changed.
  await page.route('**/cfb/data/models.json*', (route) =>
    route.fulfill({ json: { ...MODELS, schema_version: 4 } }),
  );
  await page.goto('/cfb/models/');

  await expect(page.getByText(/402/)).toHaveCount(0);
});

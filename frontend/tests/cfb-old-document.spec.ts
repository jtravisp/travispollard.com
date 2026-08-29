import { expect, test } from '@playwright/test';

/**
 * `/cfb` rendering a document published before its newest fields existed.
 *
 * **This is guaranteed, not an edge case.** The routes deploy before the
 * pipeline republishes — deliberately, so that a page never meets a document
 * from a newer generator and shows "data is newer than this page" to every
 * visitor. The cost of that ordering is the mirror case: for the window between
 * deploy and publish, the new page reads the *old* document.
 *
 * The failure it guards is specific and type-checks fine. `history` is absent
 * rather than empty on such a document, so `doc.history.map(...)` throws
 * `Cannot read properties of undefined`, the page renders nothing at all, and
 * TypeScript is perfectly happy because the interface said `RatingPoint[]`.
 *
 * The document below is the real one that was live on 2026-08-29, before
 * `history`, `last_result`, `opponent_rank` and `opponent_elo` were added.
 */

const OLD_DOCUMENT = {
  schema_version: 1,
  generated_at: '2026-08-29T19:41:00.000000Z',
  season: 2026,
  week: '01',
  team: 'Texas',
  game: {
    kickoff: '2026-09-05T19:30:00Z',
    week: '01',
    opponent: 'Texas State',
    home: true,
    neutral_site: false,
    predicted_margin: 39.3,
    win_probability: 0.9893,
    market_line: -30.5,
    line_source: 'DraftKings',
  },
  as_of: { week: 'preseason', elo: 2113.0, national_rank: 5, fbs_teams: 138 },
};

/** The same document as the pipeline publishes it now: version 2, `model_rank`. */
const NEW_DOCUMENT = {
  ...OLD_DOCUMENT,
  schema_version: 2,
  as_of: { week: 'preseason', elo: 2113.0, model_rank: 5, fbs_teams: 138 },
};

test.describe('/cfb against a document written before the new fields', () => {
  test.beforeEach(async ({ page }) => {
    // One route, and no catch-all beside it: Playwright matches the most
    // recently registered handler first, so a `**/cfb/data/*.json` fallback
    // registered after this one would swallow next-game.json and serve `{}` --
    // which reads as an unknown schema_version and renders the stale state,
    // failing these tests for a reason that has nothing to do with them.
    // `/cfb` fetches exactly this document and nothing else (SPEC-phase1 6.1).
    await page.route('**/cfb/data/next-game.json*', (route) =>
      route.fulfill({ json: OLD_DOCUMENT }),
    );
  });

  test('renders the game rather than throwing on the absent fields', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/cfb/');

    await expect(page.getByRole('heading', { name: /Texas State.*at.*Texas/ })).toBeVisible();
    await expect(page.getByText('Texas by 39.3')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('shows the placeholder instead of a chart, and no rank it does not have', async ({
    page,
  }) => {
    await page.goto('/cfb/');

    await expect(
      page.getByText(/rating history appears here once the season has been scored/i),
    ).toBeVisible();
    // The rank must render from the version 1 spelling rather than "#undefined".
    await expect(page.getByText('#5')).toBeVisible();
    await expect(page.getByText(/Elo rank/)).toBeVisible();
    await expect(page.getByText(/#undefined|NaN/)).toHaveCount(0);
  });

  test('does not show a last result it was never given', async ({ page }) => {
    await page.goto('/cfb/');
    await expect(page.getByText(/last result/i)).toHaveCount(0);
  });
});

test.describe('/cfb against a document carrying the new fields', () => {
  test('draws the chart and the opponent rank once there is a series', async ({ page }) => {
    await page.route('**/cfb/data/next-game.json*', (route) =>
      route.fulfill({
        json: {
          ...NEW_DOCUMENT,
          game: {
            ...NEW_DOCUMENT.game,
            opponent_model_rank: 81,
            opponent_elo: 1375.0,
          },
          history: [
            { week: 'preseason', elo: 2113.0, model_rank: 5, fbs_teams: 138 },
            { week: '01', elo: 2131.0, model_rank: 4, fbs_teams: 138 },
          ],
          last_result: {
            week: '01',
            kickoff: '2026-09-05T19:30:00Z',
            opponent: 'Texas State',
            home: true,
            team_points: 45,
            opponent_points: 14,
            won: true,
            predicted_margin: 39.3,
            actual_margin: 31,
            error: 8.3,
            beat_market: true,
          },
        },
      }),
    );

    await page.goto('/cfb/');

    await expect(page.getByText(/Texas State is 81st of 138 by this model/)).toBeVisible();
    await expect(page.getByRole('img', { name: /Elo rating by week/ })).toBeVisible();
    await expect(page.getByText('Texas 45, Texas State 14')).toBeVisible();
    await expect(page.getByText(/It beat the closing number/)).toBeVisible();
  });
});

test.describe('the version 2 rename', () => {
  test('a version 1 document still renders its rank', async ({ page }) => {
    /**
     * The reason both versions are accepted. Routes deploy before the pipeline
     * republishes, so this page reads a v1 document first — and v1 spells the
     * field `national_rank`. Refusing it would show "data is newer than this
     * page" to every visitor for a change that renamed one key.
     */
    await page.route('**/cfb/data/next-game.json*', (route) =>
      route.fulfill({ json: OLD_DOCUMENT }),
    );
    await page.goto('/cfb/');
    await expect(page.getByText('#5')).toBeVisible();
  });

  test('a version 2 document renders the same rank from the new name', async ({ page }) => {
    await page.route('**/cfb/data/next-game.json*', (route) =>
      route.fulfill({ json: NEW_DOCUMENT }),
    );
    await page.goto('/cfb/');
    await expect(page.getByText('#5')).toBeVisible();
    await expect(page.getByText(/of 138 FBS teams, by this model/)).toBeVisible();
  });

  test('an unknown version still shows the stale state', async ({ page }) => {
    /** The mechanism must not have been widened into uselessness. */
    await page.route('**/cfb/data/next-game.json*', (route) =>
      route.fulfill({ json: { ...NEW_DOCUMENT, schema_version: 99 } }),
    );
    await page.goto('/cfb/');
    await expect(page.getByText(/This data is newer than this page/)).toBeVisible();
  });
});

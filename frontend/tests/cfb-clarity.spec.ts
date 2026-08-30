import { expect, test } from '@playwright/test';

/**
 * The four things on `/cfb` and `/cfb/slate` that can regress without anything
 * else noticing — each of them a case where the page is *wrong* rather than
 * broken, so a build, a type check and every other spec stay green.
 *
 *   the seed disclosure   absent, it makes the edge mean something it does not
 *   a played game         unmarked, history reads as forecast
 *   the record line       missing its empty state, the page looks unfinished
 *   the default sort      wrong, and the interesting rows stay buried
 */

const EMPTY_RECORD = {
  games: 0,
  mae: null,
  brier: null,
  line_games: 0,
  line_mae: null,
  sagarin_games: 0,
  sagarin_mae: null,
  ats: { record: '0-0', wins: 0, losses: 0, pushes: 0, excluded_no_line: 0, excluded_no_edge: 0 },
};

const SCORED_RECORD = {
  ...EMPTY_RECORD,
  games: 231,
  mae: 11.9,
  line_games: 198,
  line_mae: 10.8,
  ats: { record: '118-113', wins: 118, losses: 113, pushes: 0, excluded_no_line: 33, excluded_no_edge: 0 },
};

const NEXT_GAME = {
  schema_version: 2,
  generated_at: '2026-08-29T22:12:38.188325Z',
  season: 2026,
  week: '01',
  team: 'Texas',
  game: {
    kickoff: '2026-09-05T19:30:00Z',
    forecast_generated_at: '2026-08-29T19:40:59.782438Z',
    week: '01',
    opponent: 'Texas State',
    home: true,
    neutral_site: false,
    predicted_margin: 39.3,
    win_probability: 0.9893,
    market_line: -30.5,
    line_source: 'DraftKings',
    opponent_model_rank: 81,
    opponent_elo: 1375.0,
  },
  as_of: { week: 'preseason', elo: 2113.0, model_rank: 5, fbs_teams: 138 },
  history: [],
  last_result: null,
  seed_disclosure: { active: true, threshold: 0.9, current_r: 1.0, retired_week: null },
  season_so_far: { through_week: null, texas: EMPTY_RECORD, full_slate: EMPTY_RECORD },
};

function serve(page: import('@playwright/test').Page, json: unknown) {
  return page.route('**/cfb/data/next-game.json*', (route) => route.fulfill({ json }));
}

test.describe('the seed disclosure, on the page where it changes a reading', () => {
  test('appears beside the edge while it is active', async ({ page }) => {
    await serve(page, NEXT_GAME);
    await page.goto('/cfb/');

    await expect(page.getByText(/The model.s edge/i)).toBeVisible();
    await expect(page.getByText(/Read that edge carefully/)).toBeVisible();
    await expect(page.getByText(/seeded from Sagarin/)).toBeVisible();
  });

  test('is replaced once it has retired, and says when', async ({ page }) => {
    /** Retirement is one-way, so the page keeps saying it happened. */
    await serve(page, {
      ...NEXT_GAME,
      seed_disclosure: { active: false, threshold: 0.9, current_r: 0.84, retired_week: '04' },
    });
    await page.goto('/cfb/');

    await expect(page.getByText(/Read that edge carefully/)).toHaveCount(0);
    await expect(page.getByText(/separated from their preseason seed in week 4/i)).toBeVisible();
  });

  test('a document without one renders nothing rather than throwing', async ({ page }) => {
    const { seed_disclosure: _dropped, ...without } = NEXT_GAME;
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await serve(page, without);
    await page.goto('/cfb/');

    await expect(page.getByText(/Read that edge carefully/)).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

test.describe('how the model is doing', () => {
  test('says so explicitly when nothing has been scored', async ({ page }) => {
    await serve(page, NEXT_GAME);
    await page.goto('/cfb/');

    await expect(page.getByText('How the model is doing')).toBeVisible();
    await expect(page.getByText(/No games have been scored yet/)).toBeVisible();
    await expect(page.getByText(/will not be quietly backfilled/)).toBeVisible();
  });

  test('lights up on its own once a week is scored', async ({ page }) => {
    await serve(page, {
      ...NEXT_GAME,
      season_so_far: { through_week: '04', texas: SCORED_RECORD, full_slate: SCORED_RECORD },
    });
    await page.goto('/cfb/');

    await expect(page.getByText(/Through week 4, over 231 games/)).toBeVisible();
    await expect(page.getByText(/11\.90/)).toBeVisible();
    await expect(page.getByText(/10\.80/)).toBeVisible();
  });
});

test.describe('a played game is marked as played', () => {
  const SLATE = {
    schema_version: 2,
    generated_at: '2026-08-29T22:12:38.188325Z',
    season: 2026,
    week: '01',
    team: 'Texas',
    priced: 2,
    forecast_from: null,
    excluded_non_fbs: 0,
    results_known_at: '2026-08-30T12:00:00Z',
    games: [
      {
        cfbd_game_id: 1,
        kickoff: '2026-08-29T21:30:00Z',
        home: 'North Dakota State',
        away: 'Jacksonville State',
        neutral_site: false,
        predicted_margin: 3.2,
        win_probability: 0.55,
        market_line: -2.5,
        line_source: 'DraftKings',
        featured: false,
        played: true,
      },
      {
        cfbd_game_id: 2,
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
      },
    ],
  };

  test('the played row is marked and the upcoming one is not', async ({ page }) => {
    await page.route('**/cfb/data/slate.json*', (route) => route.fulfill({ json: SLATE }));
    await page.goto('/cfb/slate/');

    const played = page.getByRole('row', { name: /Jacksonville State/ });
    await expect(played.getByText('played')).toBeVisible();

    const upcoming = page.getByRole('row', { name: /Texas State/ });
    await expect(upcoming.getByText('played')).toHaveCount(0);
  });

  test('the page says when results were last known, rather than implying live', async ({
    page,
  }) => {
    await page.route('**/cfb/data/slate.json*', (route) => route.fulfill({ json: SLATE }));
    await page.goto('/cfb/slate/');

    await expect(page.getByText(/results as of/)).toBeVisible();
    await expect(page.getByText(/not yet marked/)).toBeVisible();
  });

  test('a fully priced slate does not read as a subset', async ({ page }) => {
    await page.route('**/cfb/data/slate.json*', (route) => route.fulfill({ json: SLATE }));
    await page.goto('/cfb/slate/');

    await expect(page.getByText('all priced by a book')).toBeVisible();
    await expect(page.getByText(/2 of them priced/)).toHaveCount(0);
  });
});

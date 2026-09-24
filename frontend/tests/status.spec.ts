import { expect, test, type Page } from '@playwright/test';

/**
 * `/status` — the public status page.
 *
 * Every case supplies its own /status.json through route interception, so the
 * suite never depends on the checker having run. The export under test is a
 * production build, which is what makes the last case meaningful: with no
 * document, production must say so rather than show sample data.
 */

const FRESH = new Date(Date.now() - 3 * 60_000).toISOString();

const SERVICE = {
  id: 'near-mint-radar',
  name: 'Near Mint Radar',
  url: 'https://nearmintradar.com',
  status: 'operational',
  http_code: 200,
  response_time_ms: 142,
  cert_days_remaining: 72,
};

function doc(overrides: Record<string, unknown> = {}) {
  return {
    last_updated: FRESH,
    overall_status: 'operational',
    services: [
      SERVICE,
      { ...SERVICE, id: 'ncoer-writer', name: 'NCOER Writer', url: 'https://ncoer.travispollard.com' },
    ],
    ...overrides,
  };
}

async function serve(page: Page, body: unknown, status = 200) {
  await page.route('**/status.json', (route) =>
    status === 200 ? route.fulfill({ json: body }) : route.fulfill({ status, body: 'not found' }),
  );
}

test('all operational reads as such, with each service and its checks', async ({ page }) => {
  await serve(page, doc());
  await page.goto('/status/');

  await expect(page.getByText('All Systems Operational')).toBeVisible();
  await expect(page.getByText(/2 services · checked 3 min ago/)).toBeVisible();

  const card = page.locator('li', { has: page.getByRole('link', { name: /Near Mint Radar/ }) });
  await expect(card.getByText('Operational')).toBeVisible();
  await expect(card.getByText('142 ms')).toBeVisible();
  await expect(card.getByText('HTTP 200')).toBeVisible();
  await expect(card.getByText('SSL valid (72d remaining)')).toBeVisible();
});

test('a down service makes a partial outage and shows why', async ({ page }) => {
  await serve(
    page,
    doc({
      overall_status: 'outage',
      services: [
        SERVICE,
        {
          ...SERVICE,
          id: 'ncoer-writer',
          name: 'NCOER Writer',
          status: 'down',
          http_code: 503,
          response_time_ms: 88,
          error: 'HTTP 503',
        },
      ],
    }),
  );
  await page.goto('/status/');

  await expect(page.getByText('Partial Outage')).toBeVisible();
  const card = page.locator('li', { has: page.getByRole('link', { name: /NCOER Writer/ }) });
  await expect(card.getByText('Down', { exact: true })).toBeVisible();
  await expect(card.getByText('HTTP 503', { exact: true }).first()).toBeVisible();
});

test('a slow service is degraded, and an expiring certificate is flagged', async ({ page }) => {
  await serve(
    page,
    doc({
      overall_status: 'degraded',
      services: [{ ...SERVICE, status: 'degraded', response_time_ms: 1320, cert_days_remaining: 9 }],
    }),
  );
  await page.goto('/status/');

  await expect(page.getByText('Degraded Performance')).toBeVisible();
  await expect(page.getByText('1320 ms')).toBeVisible();
  await expect(page.getByText('SSL expires in 9d')).toBeVisible();
});

test('results older than half an hour are called out as stale', async ({ page }) => {
  await serve(page, doc({ last_updated: new Date(Date.now() - 2 * 3600_000).toISOString() }));
  await page.goto('/status/');

  await expect(page.getByText('These results are out of date.')).toBeVisible();
});

test('with no status.json, production says so instead of showing sample data', async ({ page }) => {
  await serve(page, null, 404);
  await page.goto('/status/');

  await expect(page.getByText('Status data unavailable')).toBeVisible();
  await expect(page.getByText('Sample data')).toHaveCount(0);
  await expect(page.getByText('All Systems Operational')).toHaveCount(0);
});

// --- 30-day history -----------------------------------------------------------

function history(statuses: string[]) {
  // Oldest first, ending on 2026-09-24.
  const end = Date.UTC(2026, 8, 24);
  return statuses.map((status, i) => ({
    date: new Date(end - (statuses.length - 1 - i) * 86_400_000).toISOString().slice(0, 10),
    status,
    avg_latency_ms: status === 'no_data' ? null : 140 + i,
  }));
}

test('each service shows 30 daily bars, its uptime, and a readable summary', async ({ page }) => {
  const days = [
    ...Array(8).fill('no_data'),
    ...Array(19).fill('operational'),
    'degraded',
    'down',
    'operational',
  ];
  await serve(
    page,
    doc({
      history_days: 30,
      services: [{ ...SERVICE, uptime_percentage_30d: 99.86, daily_history: history(days) }],
    }),
  );
  await page.goto('/status/');

  const bars = page.locator('[data-status]');
  await expect(bars).toHaveCount(30);
  await expect(page.locator('[data-status="no_data"]')).toHaveCount(8);
  await expect(page.locator('[data-status="degraded"]')).toHaveCount(1);
  await expect(page.locator('[data-status="down"]')).toHaveCount(1);

  await expect(page.getByText('99.86%')).toBeVisible();
  await expect(
    page.getByRole('img', {
      name: '30-day history: 20 operational, 1 degraded, 1 down, 8 with no data.',
    }),
  ).toBeVisible();
});

test('hovering a bar shows its date, status and average latency', async ({ page }) => {
  const days = [...Array(28).fill('operational'), 'down', 'operational'];
  await serve(
    page,
    doc({ services: [{ ...SERVICE, uptime_percentage_30d: 99.31, daily_history: history(days) }] }),
  );
  await page.goto('/status/');

  const down = page.locator('[data-status="down"]');
  await down.hover();
  await expect(down.getByText('Sep 23, 2026')).toBeVisible();
  await expect(down.getByText(/Down · avg 168 ms/)).toBeVisible();
});

test('a day with no data never reads as operational', async ({ page }) => {
  await serve(
    page,
    doc({
      services: [
        { ...SERVICE, uptime_percentage_30d: null, daily_history: history(Array(30).fill('no_data')) },
      ],
    }),
  );
  await page.goto('/status/');

  await expect(page.locator('[data-status="operational"]')).toHaveCount(0);
  await expect(page.getByText('No data yet')).toBeVisible();
  const bar = page.locator('[data-status="no_data"]').first();
  await bar.hover();
  await expect(bar.getByText('No data', { exact: true })).toBeVisible();
});

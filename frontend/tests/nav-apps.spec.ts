import { expect, test } from '@playwright/test';

/**
 * The header's "Apps" disclosure, against the production export in out/.
 *
 * It replaced two top-level links when a third app would have overflowed the
 * 848px header row (see the comment in components/HeaderWithTheme.tsx), so
 * these pin down both halves of that decision: the bar fits, and the apps are
 * still reachable by mouse and by keyboard.
 */

const APPS = ['CFB Forecast', 'NCOER Writer', 'Austin Food Scores'];

test.describe('desktop header', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('the bar fits on one row', async ({ page }) => {
    await page.goto('/');
    const row = page.locator('header > div').first();
    const box = await row.boundingBox();
    // One line of header is well under 60px tall; a wrapped one is not.
    expect(box?.height).toBeLessThan(60);
  });

  test('Apps opens, lists the apps, and external ones open in a new tab', async ({ page }) => {
    await page.goto('/');
    const nav = page.getByRole('navigation', { name: 'Main' });
    const button = nav.getByRole('button', { name: 'Apps' });

    await expect(button).toHaveAttribute('aria-expanded', 'false');
    await button.click();
    await expect(button).toHaveAttribute('aria-expanded', 'true');

    for (const name of APPS) {
      await expect(nav.getByRole('link', { name: new RegExp(name) })).toBeVisible();
    }
    for (const name of ['NCOER Writer', 'Austin Food Scores']) {
      const link = nav.getByRole('link', { name: new RegExp(name) });
      await expect(link).toHaveAttribute('target', '_blank');
      await expect(link).toHaveAttribute('rel', /noopener/);
    }
  });

  test('Escape closes the list and returns focus to the button', async ({ page }) => {
    await page.goto('/');
    const button = page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Apps' });
    await button.click();
    await page.keyboard.press('Tab');
    await expect(
      page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'CFB Forecast' }),
    ).toBeFocused();

    await page.keyboard.press('Escape');
    await expect(button).toHaveAttribute('aria-expanded', 'false');
    await expect(button).toBeFocused();
  });

  test('a click outside closes the list', async ({ page }) => {
    await page.goto('/');
    const button = page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Apps' });
    await button.click();
    await page.mouse.click(10, 400);
    await expect(button).toHaveAttribute('aria-expanded', 'false');
  });
});

test('mobile drawer lists the apps as a labelled group', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Open menu' }).click();
  const apps = page.getByRole('list', { name: 'Apps' });
  for (const name of APPS) {
    await expect(apps.getByRole('link', { name: new RegExp(name) })).toBeVisible();
  }
});

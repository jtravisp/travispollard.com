import { expect, test } from '@playwright/test';

test('Visitor counter API increments and returns count', async ({ request }) => {
  const response = await request.get('https://29mh2e7a07.execute-api.us-east-1.amazonaws.com/prod/count');
  
  expect(response.status()).toBe(200);

  const json = await response.json();
  expect(json).toHaveProperty('count');
  expect(typeof json.count).toBe('number');
});

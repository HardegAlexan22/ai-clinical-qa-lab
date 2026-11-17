// @ts-check
const { test, expect } = require('@playwright/test');
const { AUTH, summarize } = require('./helpers');

test.describe('authentication', () => {
  test('health check is public', async ({ request }) => {
    const res = await request.get('/health');
    expect(res.status()).toBe(200);
    expect(await res.json()).toMatchObject({ status: 'ok' });
  });

  test('missing API key returns 401', async ({ request }) => {
    const res = await request.post('/summarize', { data: { study_id: 'study_001' } });
    expect(res.status()).toBe(401);
  });

  test('wrong API key returns 401', async ({ request }) => {
    const res = await request.post('/summarize', {
      headers: { 'x-api-key': 'not-the-key' },
      data: { study_id: 'study_001' },
    });
    expect(res.status()).toBe(401);
  });

  test('auth is checked before validation (no key + bad body is 401, not 422)', async ({
    request,
  }) => {
    // A 422 here would tell an unauthenticated caller about the request format.
    const res = await request.post('/summarize', { data: {} });
    expect(res.status()).toBe(401);
  });

  test('traces require the API key', async ({ request }) => {
    const res = await request.get('/traces/anything');
    expect(res.status()).toBe(401);
  });
});

test.describe('input validation', () => {
  const invalidBodies = [
    { name: 'missing study_id', data: {} },
    { name: 'study_id wrong format', data: { study_id: 'abc' } },
    { name: 'study_id wrong type', data: { study_id: 123 } },
    { name: 'study_id with injection characters', data: { study_id: "study_001'; DROP TABLE x;--" } },
    { name: 'include_trace wrong type', data: { study_id: 'study_001', include_trace: 'maybe' } },
  ];

  for (const { name, data } of invalidBodies) {
    test(`${name} returns 422`, async ({ request }) => {
      const res = await request.post('/summarize', { headers: AUTH, data });
      expect(res.status()).toBe(422);
    });
  }

  test('malformed JSON returns 422', async ({ request }) => {
    const res = await request.post('/summarize', {
      headers: { ...AUTH, 'content-type': 'application/json' },
      data: '{"study_id": ',
    });
    expect(res.status()).toBe(422);
  });
});

test.describe('not found and wrong method', () => {
  test('unknown study returns 404 and names the study', async ({ request }) => {
    const res = await request.post('/summarize', { headers: AUTH, data: { study_id: 'study_999' } });
    expect(res.status()).toBe(404);
    expect((await res.json()).detail).toContain('study_999');
  });

  test('unknown trace id returns 404', async ({ request }) => {
    const res = await request.get('/traces/00000000-0000-0000-0000-000000000000', { headers: AUTH });
    expect(res.status()).toBe(404);
  });

  test('GET /summarize returns 405', async ({ request }) => {
    const res = await request.get('/summarize', { headers: AUTH });
    expect(res.status()).toBe(405);
  });
});

test.describe('fault injection', () => {
  test('is rejected with 403 unless explicitly enabled', async ({ request }) => {
    // Faults exist for testing only; a normal deployment must refuse them.
    const res = await request.post('/summarize', {
      headers: AUTH,
      data: { study_id: 'study_001', fault: 'stale_retrieval' },
    });
    expect(res.status()).toBe(403);
  });
});


test('health check reports the fake model', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.model.adapter).toBe('fake');
});

test('adverse event count is correct and cited to the right passage', async ({ request }) => {
  const res = await summarize(request);
  expect(res.status()).toBe(200);
  const body = await res.json();

  expect(body.facts.adverse_event_count).toBe(38);

  const cite = body.citations.find((c) => c.fact === 'adverse_event_count');
  expect(cite.passage_id).toBe('P7');
});


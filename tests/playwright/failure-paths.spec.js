// @ts-check
const { test, expect } = require('@playwright/test');
const { AUTH, summarize, testId } = require('./helpers');

test.describe('authentication', () => {
  test('AUTH-01: health check is public', async ({ request }) => {
    const res = await request.get('/health');
    expect(res.status()).toBe(200);
    expect(await res.json()).toMatchObject({ status: 'ok' });
  });

  test('AUTH-02: missing API key returns 401', async ({ request }) => {
    const res = await request.post('/summarize', { data: { study_id: 'study_001' } });
    expect(res.status()).toBe(401);
  });

  test('AUTH-03: wrong API key returns 401', async ({ request }) => {
    const res = await request.post('/summarize', {
      headers: { 'x-api-key': 'not-the-key' },
      data: { study_id: 'study_001' },
    });
    expect(res.status()).toBe(401);
  });

  test('AUTH-04: auth is checked before validation (no key + bad body is 401, not 422)', async ({
    request,
  }) => {
    // A 422 here would tell an unauthenticated caller about the request format.
    const res = await request.post('/summarize', { data: {} });
    expect(res.status()).toBe(401);
  });

  test('AUTH-05: traces require the API key', async ({ request }) => {
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

  // VAL-01 to VAL-05, in list order. Add new cases at the end so existing IDs don't shift.
  invalidBodies.forEach(({ name, data }, i) => {
    test(`${testId('VAL', i + 1)}: ${name} returns 422`, async ({ request }) => {
      const res = await request.post('/summarize', { headers: AUTH, data });
      expect(res.status()).toBe(422);
    });
  });

  test('VAL-06: malformed JSON returns 422', async ({ request }) => {
    const res = await request.post('/summarize', {
      headers: { ...AUTH, 'content-type': 'application/json' },
      data: '{"study_id": ',
    });
    expect(res.status()).toBe(422);
  });
});

test.describe('not found and wrong method', () => {
  test('ERR-01: unknown study returns 404 and names the study', async ({ request }) => {
    const res = await request.post('/summarize', { headers: AUTH, data: { study_id: 'study_999' } });
    expect(res.status()).toBe(404);
    expect((await res.json()).detail).toContain('study_999');
  });

  test('ERR-02: unknown trace id returns 404', async ({ request }) => {
    const res = await request.get('/traces/00000000-0000-0000-0000-000000000000', { headers: AUTH });
    expect(res.status()).toBe(404);
  });

  test('ERR-03: GET /summarize returns 405', async ({ request }) => {
    const res = await request.get('/summarize', { headers: AUTH });
    expect(res.status()).toBe(405);
  });
});

test.describe('fault injection', () => {
  test('GATE-01: faults are rejected with 403 unless explicitly enabled', async ({ request }) => {
    // Faults exist for testing only; a normal deployment must refuse them.
    const res = await request.post('/summarize', {
      headers: AUTH,
      data: { study_id: 'study_001', fault: 'stale_retrieval' },
    });
    expect(res.status()).toBe(403);
  });
});


test('CON-04: health check reports the fake model', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.model.adapter).toBe('fake');
});

test('FACT-09: adverse event count is correct and cited to the right passage', async ({ request }) => {
  const res = await summarize(request);
  expect(res.status()).toBe(200);
  const body = await res.json();

  expect(body.facts.adverse_event_count).toBe(38);

  const cite = body.citations.find((c) => c.fact === 'adverse_event_count');
  expect(cite.passage_id).toBe('P7');
});


// @ts-check
const { test, expect } = require('@playwright/test');
const { API_KEY, AUTH, groundTruth, validateSummarize, summarize, testId } = require('./helpers');

const { facts: expectedFacts, authoritative_source: authoritative } = groundTruth;

test.describe('POST /summarize: contract', () => {
  test('CON-01: returns 200 with a response that matches the JSON schema', async ({ request }) => {
    const res = await summarize(request);
    expect(res.status()).toBe(200);
    const body = await res.json();
    const valid = validateSummarize(body);
    expect(validateSummarize.errors ?? [], 'schema errors').toEqual([]);
    expect(valid).toBe(true);
  });

  test('CON-02: reports the model adapter and settings used', async ({ request }) => {
    const body = await (await summarize(request)).json();
    expect(body.model).toMatchObject({ adapter: 'fake', temperature: 0 });
    expect(body.model.version).toMatch(/^\d+\.\d+\.\d+$/);
  });

  // BUG-002: sources used to come from the manifest, so it said v2.0 even when v1.0 text was used.
  test('CON-03: lists only the current document version as a source', async ({ request }) => {
    const body = await (await summarize(request)).json();
    expect(body.sources).toEqual([authoritative]);
  });
});

test.describe('POST /summarize: facts match ground truth', () => {
  // One test per fact, so the report shows exactly which fact is wrong.
  // FACT-01 to FACT-06, in ground-truth file order.
  Object.entries(expectedFacts).forEach(([name, expected], i) => {
    test(`${testId('FACT', i + 1)}: ${name} matches ground truth`, async ({ request }) => {
      const body = await (await summarize(request)).json();
      expect(body.facts[name]).toEqual(expected.value);
    });
  });

  test('FACT-07: known wrong values from the superseded report never appear', async ({ request }) => {
    const body = await (await summarize(request)).json();
    for (const [name, wrongValues] of Object.entries(groundTruth.known_wrong_values)) {
      for (const wrong of wrongValues) {
        expect(body.facts[name], `${name} must not be ${wrong}`).not.toBe(wrong);
        expect(body.summary).not.toMatch(new RegExp(`\\b${wrong}\\b`));
      }
    }
  });

  test('FACT-08: summary text states the enrolled count (checked by value, not exact wording)', async ({
    request,
  }) => {
    const body = await (await summarize(request)).json();
    expect(body.summary).toMatch(new RegExp(`\\b${expectedFacts.enrolled_patients.value}\\b`));
  });
});

test.describe('POST /summarize: citations', () => {
  test('CITE-01: every fact is cited to the authoritative source and the expected passage', async ({
    request,
  }) => {
    const body = await (await summarize(request)).json();
    for (const [name, expected] of Object.entries(expectedFacts)) {
      const cite = body.citations.find((c) => c.fact === name);
      expect(cite, `citation for ${name}`).toBeDefined();
      expect(cite).toMatchObject({ ...authoritative, passage_id: expected.passage_id });
    }
  });

  test('CITE-02: each cited passage actually contains the fact it supports', async ({ request }) => {
    // A valid-looking citation ID is not enough; the passage text must back the claim.
    const body = await (await summarize(request, { include_trace: true })).json();
    for (const cite of body.citations) {
      const passage = body.trace.retrieved_passages.find(
        (p) =>
          p.source_id === cite.source_id &&
          p.version === cite.version &&
          p.passage_id === cite.passage_id,
      );
      expect(passage, `passage for ${cite.fact}`).toBeDefined();

      const value = body.facts[cite.fact];
      const needles = Array.isArray(value)
        ? value.flatMap((arm) => [arm.name, String(arm.patients)])
        : [String(value)];
      for (const needle of needles) {
        expect(passage.text, `${cite.fact} -> ${cite.passage_id}`).toContain(needle);
      }
    }
  });
});

test.describe('POST /summarize: traces', () => {
  test('TRACE-01: retrieval used only current-version passages', async ({ request }) => {
    const body = await (await summarize(request, { include_trace: true })).json();
    const versions = new Set(body.trace.retrieved_passages.map((p) => p.version));
    expect([...versions]).toEqual([authoritative.version]);
  });

  test('TRACE-02: trace is stored and retrievable by request_id', async ({ request }) => {
    const body = await (await summarize(request)).json();
    const res = await request.get(`/traces/${body.request_id}`, { headers: AUTH });
    expect(res.status()).toBe(200);
    const trace = await res.json();
    expect(trace.request_id).toBe(body.request_id);
    expect(trace.final_response.facts).toEqual(body.facts);
    for (const stage of ['extracted_passages', 'retrieved_passages', 'model_request', 'raw_model_response']) {
      expect(trace, `trace stage ${stage}`).toHaveProperty(stage);
    }
  });

  test('TRACE-03: trace records a SHA-256 digest for every document', async ({ request }) => {
    const body = await (await summarize(request, { include_trace: true })).json();
    for (const doc of body.trace.documents) {
      expect(doc.sha256).toMatch(/^[0-9a-f]{64}$/);
    }
  });

  test('TRACE-04: trace does not leak the API key', async ({ request }) => {
    const body = await (await summarize(request, { include_trace: true })).json();
    expect(JSON.stringify(body.trace)).not.toContain(API_KEY);
  });
});

test.describe('POST /summarize: regressions', () => {
  test('REG-01: BUG-001 treatment arm names have no leading separator', async ({ request }) => {
    // Found in S1: the arm parser returned ", placebo" instead of "placebo".
    const body = await (await summarize(request)).json();
    for (const arm of body.facts.treatment_arms) {
      expect(arm.name).toBe(arm.name.trim());
      expect(arm.name).not.toMatch(/^[,;\s]/);
    }
  });

  test('REG-02: identical requests give identical facts (deterministic baseline)', async ({ request }) => {
    const first = await (await summarize(request)).json();
    const second = await (await summarize(request)).json();
    expect(second.facts).toEqual(first.facts);
    expect(second.request_id).not.toBe(first.request_id);
  });
});

test('FACT-10: treatment arm sizes add up to the enrolled total', async ({ request }) => {
  const body = await (await summarize(request)).json();
  const armTotal = body.facts.treatment_arms.reduce((sum, arm) => sum +  arm.patients, 0);
  expect(armTotal).toBe(body.facts.enrolled_patients);
})

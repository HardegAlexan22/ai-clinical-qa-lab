# AI Clinical Document QA Lab

A reproducible lab for testing an AI document-summary service: factual accuracy against ground truth, citation support, stale-document retrieval, and tracing a wrong answer to the pipeline stage that caused it.

**Synthetic documents only. This is a testing demo, not a clinical product.**

## What this demonstrates

- **Testing AI output, not just the API.** Every fact in the summary is checked against independently written ground truth, and every citation must point to a passage that actually contains the claimed value.
- **Telling a model defect from an application defect.** Each request records a stage-by-stage trace. When an answer is wrong, the eval code compares each stage's output to the expected value and reports the first stage where it changes (extraction, retrieval, model, or postprocessing).
- **Catching hallucinations and stale data.** Six switchable faults (stale document retrieved, invented endpoint, wrong citation, missing fact, and others) each produce a distinct failure signature.
- **Two real defects found while building it,** each now covered by a regression test (see BUG-001 and BUG-002 below).

The model is a deterministic **mock**, which keeps results repeatable. The point is the test strategy around the model, not the model itself.

**Stack:** Python, FastAPI, pytest, Playwright (API testing), JSON Schema (ajv), GitHub Actions.

## Status

Done: the service, synthetic fixtures, ground truth, the Playwright API suite (37 tests), the pytest evaluation suite with seeded faults and stage localization (20 tests), and CI running both suites on every push. Next: repeated-run variability, document integrity checks and release-gate metrics.

## Run the Python evaluation suite

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

It calls the app in-process, so no server is needed. `evals/checks.py` holds the two pieces of logic:

- **`evaluate()`** checks a response against several oracles: ground truth (`incorrect_value`, `missing_fact`), the retrieved text (`unsupported_claim`, i.e. hallucination; `citation_unsupported`), the authoritative version (`non_authoritative_citation`), and a consistency rule (`inconsistent_facts`).
- **`localize()`** walks the trace (source → extraction → retrieval → prompt → model → postprocess) and returns the first stage where the expected value is lost.

### Seeded faults and the triage matrix

Faults can be switched on per request with `"fault": "<name>"`, but only when `QA_LAB_ENABLE_FAULTS=1`. Otherwise the API returns 403, so a normal deployment can't be made to misbehave. The pytest suite enables them.

| Fault | Simulates | Caught by | Localized to |
|---|---|---|---|
| `extraction_corruption` | Bad text conversion turns 250 into 275 | `incorrect_value`, `inconsistent_facts` | extraction |
| `stale_retrieval` | Superseded v1.0 retrieved | `non_authoritative_citation` on every fact, `incorrect_value` | retrieval |
| `hallucinated_endpoint` | Model invents a plausible endpoint | `unsupported_claim`, `citation_unsupported`, `incorrect_value` | model |
| `wrong_citation` | Right value, cited to the wrong passage | `citation_unsupported` only | model (citation) |
| `missing_fact` | Model omits the adverse event count | `missing_fact` | model |
| `postprocess_change` | App code changes 250 to 275 after the model | `incorrect_value`, `unsupported_claim`, `citation_unsupported`, `inconsistent_facts` | postprocess |

## Run the API tests

Playwright starts and stops the service on its own:

```powershell
npx.cmd playwright test
npx.cmd playwright show-report
```

In PowerShell, use `npx.cmd` rather than `npx`. Plain `npx` runs `npx.ps1`, which Windows' default script policy blocks. The `.cmd` version does the same thing without changing any security settings.

The suite covers the contract (JSON schema, model metadata), every fact against ground truth, citation support (the cited passage must actually contain the claimed value), traces, auth/validation/404/405 paths, and regressions for defects found while building:

| ID | Defect | How it was found |
|---|---|---|
| BUG-001 | Treatment-arm parser returned `", placebo"` | Smoke test compared facts to ground truth |
| BUG-002 | `sources` reported v2.0 even when v1.0 text had been retrieved | Deliberately broke retrieval; this was the only test that stayed green |

## How it works

`POST /summarize` runs a five-stage pipeline and records each stage in a trace:

1. **Extract:** read passages (`[P1]`, `[P2]`, ...) from each document version.
2. **Retrieve:** keep only passages from the `current` version (the manifest marks v1.0 as `superseded`).
3. **Build prompt:** assemble instructions plus retrieved passages.
4. **Model:** a deterministic fake model reads facts from the prompt's passages. If a stale passage gets in, it repeats the stale number, just as a real LLM would.
5. **Postprocess:** parse the model output into `summary`, `facts`, and `citations`.

The seeded conflict: the current report says **250** patients were enrolled, and the superseded report says **275**. The correct answer is 250, cited to `SYN-001-CSR` v2.0, passage P3.

## Setup (Windows, PowerShell)

Prerequisites: Git, Node.js LTS, Python 3.11+.

```powershell
npm install
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS/Linux, use `python3 -m venv .venv` and `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.

## Run the service

```powershell
.\.venv\Scripts\python.exe -m uvicorn service.app:app --reload
```

The API key is a local test value (`local-dev-key` by default, override with `QA_LAB_API_KEY`). Example call:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/summarize `
  -Headers @{ "x-api-key" = "local-dev-key" } -ContentType "application/json" `
  -Body '{"study_id": "study_001", "include_trace": true}'
```

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | No key needed. Returns model metadata. |
| POST | `/summarize` | Body: `{"study_id": "study_001", "include_trace": false}`. Returns 401 for a bad key, 422 for an invalid body, and 404 for an unknown study. |
| GET | `/traces/{request_id}` | Full stage-by-stage trace for an earlier request. |

`POST /summarize` also accepts `"fault"` for testing; see the triage matrix above.

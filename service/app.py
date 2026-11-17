"""Synthetic clinical-study summary service, built as a target for AI QA tests.

This is a testing demo that uses synthetic documents only. It is not a clinical product.
"""
import os
import uuid
from collections import OrderedDict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from service.adapters.fake_model import FakeModel
from service.pipeline import FAULTS, UnknownStudyError, run_pipeline

# Local test value only; override with QA_LAB_API_KEY. Never put a real key here.
API_KEY = os.environ.get("QA_LAB_API_KEY", "local-dev-key")
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json"}
MAX_TRACES = 200

app = FastAPI(title="AI Clinical Document QA Lab", version="0.1.0")
model = FakeModel()
traces: OrderedDict[str, dict] = OrderedDict()


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    # Runs before body validation, so a bad key returns 401 even when the body is also invalid.
    if request.url.path not in PUBLIC_PATHS and request.headers.get("x-api-key") != API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid API key"})
    return await call_next(request)


class SummarizeRequest(BaseModel):
    study_id: str = Field(pattern=r"^study_\d{3}$")
    include_trace: bool = False
    fault: str | None = None


def faults_enabled() -> bool:
    # Read per request so test suites can switch it on without restarting the app.
    return os.environ.get("QA_LAB_ENABLE_FAULTS") == "1"


@app.get("/health")
def health():
    return {"status": "ok", "model": model.metadata}


@app.post("/summarize")
def summarize(req: SummarizeRequest):
    if req.fault is not None:
        if not faults_enabled():
            raise HTTPException(status_code=403, detail="Fault injection is disabled")
        if req.fault not in FAULTS:
            raise HTTPException(status_code=422, detail=f"Unknown fault: {req.fault}")
    try:
        response, trace = run_pipeline(req.study_id, model, req.fault)
    except UnknownStudyError:
        raise HTTPException(status_code=404, detail=f"Unknown study_id: {req.study_id}")

    request_id = str(uuid.uuid4())
    trace["request_id"] = request_id
    traces[request_id] = trace
    while len(traces) > MAX_TRACES:
        traces.popitem(last=False)

    response = {"request_id": request_id, **response}
    if req.include_trace:
        response["trace"] = trace
    return response


@app.get("/traces/{request_id}")
def get_trace(request_id: str):
    if request_id not in traces:
        raise HTTPException(status_code=404, detail="Trace not found")
    return traces[request_id]

"""Shared pytest fixtures. pytest loads this file automatically before the tests."""
import os

import pytest
from fastapi.testclient import TestClient

from evals.checks import load_ground_truth
from service.app import app

API_KEY = os.environ.get("QA_LAB_API_KEY", "local-dev-key")


@pytest.fixture
def client(monkeypatch):
    # Calls the app in-process, so no server needs to be running.
    monkeypatch.setenv("QA_LAB_ENABLE_FAULTS", "1")
    return TestClient(app, headers={"x-api-key": API_KEY})


@pytest.fixture(scope="session")
def ground_truth():
    return load_ground_truth()


@pytest.fixture
def run(client):
    """Summarize study_001 with an optional injected fault; returns (response, trace)."""

    def _run(fault=None):
        body = {"study_id": "study_001", "include_trace": True}
        if fault:
            body["fault"] = fault
        res = client.post("/summarize", json=body)
        assert res.status_code == 200, res.text
        data = res.json()
        return data, data["trace"]

    return _run

"""Triage matrix: each seeded fault must be detected, then traced to the stage that caused it."""
import pytest

from evals.checks import evaluate, localize, localize_citation

# fault injected, check that must catch it, fact it shows up on, stage the evidence must point to
TRIAGE_MATRIX = [
    ("extraction_corruption", "incorrect_value", "enrolled_patients", "extraction"),
    ("stale_retrieval", "non_authoritative_citation", "enrolled_patients", "retrieval"),
    ("hallucinated_endpoint", "unsupported_claim", "primary_endpoint", "model"),
    ("missing_fact", "missing_fact", "adverse_event_count", "model"),
    ("postprocess_change", "incorrect_value", "enrolled_patients", "postprocess"),
]
IDS = [row[0] for row in TRIAGE_MATRIX]


@pytest.mark.parametrize("fault, check, fact, stage", TRIAGE_MATRIX, ids=IDS)
def test_fault_is_detected(run, ground_truth, fault, check, fact, stage):
    response, trace = run(fault)
    found = [(f["check"], f["fact"]) for f in evaluate(response, trace, ground_truth)]
    assert (check, fact) in found


@pytest.mark.parametrize("fault, check, fact, stage", TRIAGE_MATRIX, ids=IDS)
def test_fault_is_localized(run, ground_truth, fault, check, fact, stage):
    _, trace = run(fault)
    assert localize(fact, trace, ground_truth) == stage


def test_wrong_citation_is_detected_and_localized(run, ground_truth):
    response, trace = run("wrong_citation")
    found = [(f["check"], f["fact"]) for f in evaluate(response, trace, ground_truth)]
    assert ("citation_unsupported", "enrolled_patients") in found
    # The value is right at every stage; only the evidence behind it is wrong.
    assert localize("enrolled_patients", trace, ground_truth) is None
    assert localize_citation("enrolled_patients", trace, ground_truth) == "model"


def test_faults_are_rejected_when_disabled(client, monkeypatch):
    monkeypatch.setenv("QA_LAB_ENABLE_FAULTS", "0")
    res = client.post("/summarize", json={"study_id": "study_001", "fault": "stale_retrieval"})
    assert res.status_code == 403


def test_unknown_fault_is_rejected(client):
    res = client.post("/summarize", json={"study_id": "study_001", "fault": "not_a_fault"})
    assert res.status_code == 422

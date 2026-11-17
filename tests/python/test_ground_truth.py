"""Baseline: with no fault injected, every check passes and every fact survives every stage."""
import pytest

from evals.checks import evaluate, load_ground_truth, localize

FACTS = list(load_ground_truth()["facts"])
# Test case IDs BASE-02 to BASE-07, one per fact in ground-truth file order.
FACT_IDS = [f"BASE-{n:02d}-{fact}" for n, fact in enumerate(FACTS, start=2)]


def test_base01_baseline_has_no_findings(run, ground_truth):
    response, trace = run()
    assert evaluate(response, trace, ground_truth) == []


@pytest.mark.parametrize("fact", FACTS, ids=FACT_IDS)
def test_fact_survives_every_stage(run, ground_truth, fact):
    _, trace = run()
    assert localize(fact, trace, ground_truth) is None

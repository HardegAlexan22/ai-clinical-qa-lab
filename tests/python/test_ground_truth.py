"""Baseline: with no fault injected, every check passes and every fact survives every stage."""
import pytest

from evals.checks import evaluate, load_ground_truth, localize

FACTS = list(load_ground_truth()["facts"])


def test_baseline_has_no_findings(run, ground_truth):
    response, trace = run()
    assert evaluate(response, trace, ground_truth) == []


@pytest.mark.parametrize("fact", FACTS)
def test_fact_survives_every_stage(run, ground_truth, fact):
    _, trace = run()
    assert localize(fact, trace, ground_truth) is None

"""AI output checks and defect localization.

evaluate() answers "is this answer acceptable?" using several oracles:
ground truth, the retrieved source text, and consistency rules.

localize() answers "which pipeline stage first got this fact wrong?" by walking
the trace stage by stage, the same way you would debug it by hand.
"""
import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PASSAGE_RE = re.compile(r"^\[(P\d+)\]\s+(.+)$", re.M)
STAGES = ["source", "extraction", "retrieval", "prompt", "model", "postprocess"]


def load_ground_truth(study_id: str = "study_001") -> dict:
    return json.loads((FIXTURES / f"{study_id}_ground_truth.json").read_text(encoding="utf-8"))


def needles(value) -> list[str]:
    """Text that must appear in a passage for that passage to support the value."""
    if value is None:
        return []
    if isinstance(value, list):
        return [s for arm in value for s in (arm["name"], str(arm["patients"]))]
    return [str(value)]


def supports(text: str, value) -> bool:
    found = needles(value)
    return bool(found) and all(s in text for s in found)


def passage_key(p: dict) -> tuple:
    return (p["source_id"], p["version"], p["passage_id"])


def finding(check: str, fact: str, detail: str) -> dict:
    return {"check": check, "fact": fact, "detail": detail}


def evaluate(response: dict, trace: dict, gt: dict) -> list[dict]:
    """Every problem found in one response. An empty list means it passed."""
    facts = response["facts"]
    retrieved = trace["retrieved_passages"]
    authority = gt["authoritative_source"]
    findings = []

    for name, expected in gt["facts"].items():
        value = facts.get(name)
        if value is None:
            findings.append(finding("missing_fact", name, "required fact not reported"))
            continue
        if value != expected["value"]:
            findings.append(
                finding("incorrect_value", name, f"expected {expected['value']!r}, got {value!r}")
            )
        # Hallucination check: needs no ground truth, only the text the model was given.
        if not any(supports(p["text"], value) for p in retrieved):
            findings.append(
                finding("unsupported_claim", name, f"{value!r} is not in any retrieved passage")
            )

    for cite in response["citations"]:
        name = cite["fact"]
        passage = next((p for p in retrieved if passage_key(p) == passage_key(cite)), None)
        if passage is None or not supports(passage["text"], facts.get(name)):
            findings.append(
                finding("citation_unsupported", name, f"{cite['passage_id']} does not support {facts.get(name)!r}")
            )
        if (cite["source_id"], cite["version"]) != (authority["source_id"], authority["version"]):
            findings.append(
                finding(
                    "non_authoritative_citation",
                    name,
                    f"cites v{cite['version']}, authoritative is v{authority['version']}",
                )
            )

    arms, enrolled = facts.get("treatment_arms"), facts.get("enrolled_patients")
    if arms and enrolled is not None:
        arm_total = sum(a["patients"] for a in arms)
        if arm_total != enrolled:
            findings.append(
                finding("inconsistent_facts", "treatment_arms", f"arms sum to {arm_total}, enrolled is {enrolled}")
            )

    return findings


def source_passages(gt: dict) -> dict[str, str]:
    """Passages read straight from the authoritative file: the reference point for localization."""
    authority = gt["authoritative_source"]
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    doc = next(
        d
        for d in manifest["documents"]
        if d["doc_id"] == authority["source_id"] and d["version"] == authority["version"]
    )
    return dict(PASSAGE_RE.findall((FIXTURES / doc["path"]).read_text(encoding="utf-8")))


def localize(fact: str, trace: dict, gt: dict) -> str | None:
    """First stage where the expected value for `fact` is lost, or None if no stage lost it."""
    authority = gt["authoritative_source"]
    value = gt["facts"][fact]["value"]
    pid = gt["facts"][fact]["passage_id"]
    key = (authority["source_id"], authority["version"], pid)

    def find(passages: list[dict]) -> dict | None:
        return next((p for p in passages if passage_key(p) == key), None)

    if not supports(source_passages(gt).get(pid, ""), value):
        return "source"

    extracted = find([p for doc in trace["extracted_passages"].values() for p in doc])
    if extracted is None or not supports(extracted["text"], value):
        return "extraction"

    retrieved = find(trace["retrieved_passages"])
    if retrieved is None or not supports(retrieved["text"], value):
        return "retrieval"

    prompt_line = f"[{key[0]} v{key[1]} {pid}] "
    if not any(
        line.startswith(prompt_line) and supports(line, value)
        for line in trace["model_request"].splitlines()
    ):
        return "prompt"

    if json.loads(trace["raw_model_response"])["facts"].get(fact) != value:
        return "model"

    if trace["final_response"]["facts"].get(fact) != value:
        return "postprocess"

    return None


def localize_citation(fact: str, trace: dict, gt: dict) -> str | None:
    """Like localize(), for the citation instead of the value. Assumes the earlier stages are clean."""
    expected = gt["facts"][fact]["passage_id"]

    def cited(citations: list[dict]) -> str | None:
        return next((c["passage_id"] for c in citations if c["fact"] == fact), None)

    if cited(json.loads(trace["raw_model_response"])["citations"]) != expected:
        return "model"
    if cited(trace["final_response"]["citations"]) != expected:
        return "postprocess"
    return None

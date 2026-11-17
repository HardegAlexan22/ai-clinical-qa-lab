"""Deterministic stand-in for an LLM.

It reads facts out of the passages in the prompt with regexes, so its output
depends on what retrieval supplied, the same way a real model's would. If a
stale passage reaches the prompt, this model will repeat the stale number.
"""
import json
import re

PASSAGE_RE = re.compile(r"^\[(\S+) v(\S+) (P\d+)\] (.*)$", re.M)
STUDY_RE = re.compile(r"^Study: (\S+)$", re.M)

FACT_PATTERNS = {
    "enrolled_patients": (re.compile(r"(\d+) patients were enrolled"), int),
    "start_date": (re.compile(r"first patient was enrolled on (\d{4}-\d{2}-\d{2})"), str),
    "completion_date": (re.compile(r"study completed on (\d{4}-\d{2}-\d{2})"), str),
    "primary_endpoint": (re.compile(r"primary endpoint was the (.+?)\.?$"), str),
    "adverse_event_count": (re.compile(r"(\d+) treatment-emergent adverse events"), int),
}
ARMS_RE = re.compile(r"treatment arms: (.+?)\.?$")
ARM_SPLIT_RE = re.compile(r",\s*|\s+and\s+")
ARM_RE = re.compile(r"(.+?) \((\d+) patients\)")


class FakeModel:
    metadata = {
        "adapter": "fake",
        "name": "fake-deterministic-summarizer",
        "version": "1.0.0",
        "temperature": 0,
    }

    def generate(self, prompt: str, fault: str | None = None) -> str:
        facts = {name: None for name in [*FACT_PATTERNS, "treatment_arms"]}
        citations = []

        for source_id, version, passage_id, text in PASSAGE_RE.findall(prompt):
            cite = {"source_id": source_id, "version": version, "passage_id": passage_id}
            for name, (pattern, cast) in FACT_PATTERNS.items():
                match = pattern.search(text)
                if match and facts[name] is None:
                    facts[name] = cast(match.group(1))
                    citations.append({"fact": name, **cite})
            arms = ARMS_RE.search(text)
            if arms and facts["treatment_arms"] is None:
                parts = (ARM_RE.fullmatch(p.strip()) for p in ARM_SPLIT_RE.split(arms.group(1)))
                facts["treatment_arms"] = [
                    {"name": m.group(1), "patients": int(m.group(2))} for m in parts if m
                ]
                citations.append({"fact": "treatment_arms", **cite})

        self._inject_fault(fault, facts, citations)
        study = STUDY_RE.search(prompt)
        summary = self._summarize(study.group(1) if study else "unknown study", facts)
        return json.dumps({"summary": summary, "facts": facts, "citations": citations})

    @staticmethod
    def _inject_fault(fault: str | None, facts: dict, citations: list[dict]) -> None:
        """Model-stage defects: the prompt was correct, the model's answer is not."""
        if fault == "hallucinated_endpoint":
            # Plausible-sounding, but not in any passage.
            facts["primary_endpoint"] = "change from baseline in diastolic blood pressure at Week 8"
        elif fault == "wrong_citation":
            # Right value, but cited to a passage that doesn't contain it.
            for cite in citations:
                if cite["fact"] == "enrolled_patients":
                    cite["passage_id"] = "P2"
        elif fault == "missing_fact":
            # The passage was in the prompt, but the model left the fact out.
            facts["adverse_event_count"] = None
            citations[:] = [c for c in citations if c["fact"] != "adverse_event_count"]

    @staticmethod
    def _summarize(study_id: str, facts: dict) -> str:
        def show(value):
            return "not reported" if value is None else value

        arms = facts["treatment_arms"]
        arms_text = (
            ", ".join(f"{a['name']} ({a['patients']})" for a in arms) if arms else "not reported"
        )
        return (
            f"Study {study_id} enrolled {show(facts['enrolled_patients'])} patients, "
            f"randomized to: {arms_text}. "
            f"The study ran from {show(facts['start_date'])} to {show(facts['completion_date'])}. "
            f"The primary endpoint was {show(facts['primary_endpoint'])}. "
            f"{show(facts['adverse_event_count'])} treatment-emergent adverse events were reported."
        )

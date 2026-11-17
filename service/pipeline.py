"""Summary pipeline: extract -> retrieve -> build prompt -> model -> postprocess.

Every stage's output is kept in a trace, so a wrong fact in the final response
can be traced back to the first stage where it went wrong.

FAULTS lists defects that can be switched on per request (only when
QA_LAB_ENABLE_FAULTS=1) so the test suites can prove they detect and localize them.
"""
import hashlib
import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PASSAGE_RE = re.compile(r"^\[(P\d+)\]\s+(.+)$", re.M)

# fault name -> pipeline stage it is injected into
FAULTS = {
    "extraction_corruption": "extraction",
    "stale_retrieval": "retrieval",
    "hallucinated_endpoint": "model",
    "wrong_citation": "model",
    "missing_fact": "model",
    "postprocess_change": "postprocess",
}


class UnknownStudyError(Exception):
    pass


def load_documents(study_id: str) -> list[dict]:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    docs = [d for d in manifest["documents"] if d["study_id"] == study_id]
    if not docs:
        raise UnknownStudyError(study_id)
    return docs


def extract_passages(doc: dict) -> tuple[list[dict], str]:
    raw = (FIXTURES / doc["path"]).read_bytes()
    passages = [
        {
            "source_id": doc["doc_id"],
            "version": doc["version"],
            "passage_id": pid,
            "text": text.strip(),
        }
        for pid, text in PASSAGE_RE.findall(raw.decode("utf-8"))
    ]
    return passages, hashlib.sha256(raw).hexdigest()


def corrupt_extraction(passages: list[dict]) -> list[dict]:
    """Simulates a bad PDF/text conversion that turns 250 into 275."""
    return [{**p, "text": p["text"].replace("250 patients", "275 patients")} for p in passages]


def retrieve(docs: list[dict], extracted: dict, status: str = "current") -> list[dict]:
    """Only passages from the current version of each document are eligible."""
    return [p for d in docs if d["status"] == status for p in extracted[d["path"]]]


def build_prompt(study_id: str, passages: list[dict]) -> str:
    lines = [
        "You are summarizing a synthetic clinical study report.",
        "Use only the passages below. Cite the passage for every fact.",
        "If a fact is not in the passages, say it is not reported. Do not give medical advice.",
        "",
        f"Study: {study_id}",
        "Passages:",
    ]
    lines += [f"[{p['source_id']} v{p['version']} {p['passage_id']}] {p['text']}" for p in passages]
    return "\n".join(lines)


def postprocess(raw_response: str, fault: str | None = None) -> dict:
    data = json.loads(raw_response)
    if fault == "postprocess_change":
        data["facts"]["enrolled_patients"] = 275
    return {
        "summary": data["summary"],
        "facts": data["facts"],
        "citations": data["citations"],
    }


def run_pipeline(study_id: str, model, fault: str | None = None) -> tuple[dict, dict]:
    docs = load_documents(study_id)
    extracted, hashes = {}, {}
    for doc in docs:
        extracted[doc["path"]], hashes[doc["path"]] = extract_passages(doc)
        if fault == "extraction_corruption" and doc["status"] == "current":
            extracted[doc["path"]] = corrupt_extraction(extracted[doc["path"]])

    status = "superseded" if fault == "stale_retrieval" else "current"
    retrieved = retrieve(docs, extracted, status)
    prompt = build_prompt(study_id, retrieved)
    raw_response = model.generate(prompt, fault=fault)
    final = postprocess(raw_response, fault)

    # Report what was actually retrieved, not what should have been (BUG-002).
    sources = [
        {"source_id": s, "version": v}
        for s, v in dict.fromkeys((p["source_id"], p["version"]) for p in retrieved)
    ]
    response = {"study_id": study_id, **final, "sources": sources, "model": model.metadata}
    trace = {
        "study_id": study_id,
        "documents": [
            {
                "source_id": d["doc_id"],
                "version": d["version"],
                "status": d["status"],
                "sha256": hashes[d["path"]],
            }
            for d in docs
        ],
        "extracted_passages": extracted,
        "retrieved_passages": retrieved,
        "model_request": prompt,
        "raw_model_response": raw_response,
        "final_response": final,
        "model": model.metadata,
    }
    return response, trace

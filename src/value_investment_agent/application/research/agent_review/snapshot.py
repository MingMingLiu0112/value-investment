"""Load a bounded, byte-verified ResearchCase snapshot without granting write tools."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ...decision.artifact_bundle import ReadOnlyArtifactBundleRepository
from ...product.common import load_json_object, require_inside, sha256_file
from ....research_artifact_codecs import ResearchCaseCodec


@dataclass(frozen=True)
class ResearchSnapshot:
    symbol: str
    as_of: date
    input_fingerprint: str
    workbench_sha256: str
    evidence: tuple[dict[str, Any], ...]
    positives: tuple[dict[str, Any], ...]
    counter_evidence: tuple[dict[str, Any], ...]
    next_events: tuple[dict[str, Any], ...]
    thesis_breakers: tuple[dict[str, Any], ...]

    def evidence_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(ref["id"]): ref for ref in self.evidence}


def load_research_snapshot(*, root: Path, workbench: Path, expected_sha256: str,
                           symbol: str) -> ResearchSnapshot:
    root = root.resolve()
    path = require_inside(root / "runtime", workbench, "agent research workbench")
    if sha256_file(path) != expected_sha256:
        raise ValueError("Agent research workbench hash mismatch")
    payload = load_json_object(path, "agent research workbench")
    if payload.get("symbol") != symbol or payload.get("action") != "no_order":
        raise ValueError("Agent research workbench identity/action mismatch")
    verification = payload.get("source_verification")
    if not isinstance(verification, dict) or verification.get("status") != "LOCAL_BYTES_VERIFIED":
        raise ValueError("Agent research requires locally verified original bytes")
    repository = ReadOnlyArtifactBundleRepository(payload["artifact_bundle"])
    candidates = [row for row in payload["artifact_bundle"]["artifacts"]
                  if row["identity"]["artifact_type"] == "research_case"]
    if len(candidates) != 1:
        raise ValueError("Agent research requires one ResearchCase")
    stored = repository.load_by_id(candidates[0]["artifact_id"])
    if stored.envelope.verify_payload() != stored.envelope.payload_sha256:
        raise ValueError("ResearchCase artifact hash mismatch")
    case = stored.envelope.payload_object()
    ResearchCaseCodec().from_payload(case)
    if case.get("symbol") != symbol or case.get("evidence_status") != "verified":
        raise ValueError("ResearchCase source scope is not verified")
    as_of = date.fromisoformat(case["as_of"])
    evidence = case.get("evidence_refs")
    if not isinstance(evidence, list) or not evidence or len(evidence) > 100:
        raise ValueError("ResearchCase evidence set is empty or unbounded")
    source_hashes = []
    verified_sources = {
        (str(item["path"]).replace("\\", "/"), item["sha256"])
        for item in verification.get("sources") or ()
    }
    ids = set()
    for ref in evidence:
        if not isinstance(ref, dict) or not isinstance(ref.get("id"), str):
            raise ValueError("Invalid ResearchCase evidence reference")
        if ref["id"] in ids:
            raise ValueError("Duplicate ResearchCase evidence id")
        ids.add(ref["id"])
        if (str(ref["path"]).replace("\\", "/"), ref["sha256"]) not in verified_sources:
            raise ValueError("ResearchCase source is absent from workbench verification")
        if ref.get("available_at") is not None:
            available = datetime.fromisoformat(ref["available_at"])
            if available.utcoffset() is None or available.astimezone(
                    ZoneInfo("Asia/Shanghai")).date() > as_of:
                raise ValueError("ResearchCase evidence is future-dated")
        original = require_inside(root, root / ref["path"], "agent research original")
        if sha256_file(original) != ref["sha256"]:
            raise ValueError("ResearchCase original bytes changed")
        source_hashes.append((ref["id"], ref["sha256"]))
    for key in ("positives", "counter_evidence", "next_events", "thesis_breakers"):
        for statement in case.get(key) or ():
            if not isinstance(statement, dict) or not set(statement.get("evidence_refs") or ()).issubset(ids):
                raise ValueError("ResearchCase statement cites unknown evidence")
    canonical = json.dumps({"case_sha256": stored.envelope.payload_sha256,
                            "sources": sorted(source_hashes), "workbench_sha256": expected_sha256},
                           sort_keys=True, separators=(",", ":")).encode("utf-8")
    return ResearchSnapshot(
        symbol=symbol, as_of=as_of,
        input_fingerprint=hashlib.sha256(canonical).hexdigest(),
        workbench_sha256=expected_sha256,
        evidence=tuple(dict(ref) for ref in evidence),
        positives=tuple(dict(item) for item in case.get("positives") or ()),
        counter_evidence=tuple(dict(item) for item in case.get("counter_evidence") or ()),
        next_events=tuple(dict(item) for item in case.get("next_events") or ()),
        thesis_breakers=tuple(dict(item) for item in case.get("thesis_breakers") or ()),
    )

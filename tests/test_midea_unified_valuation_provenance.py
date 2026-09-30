import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "runtime" / "valuation-results" / "000333-fcff-stage-b"
RESULT_PATH = RESULT_DIR / "evidence.json"
RESULT_POINTER = ROOT / "runtime" / "valuation-results" / "000333-fcff-stage-b-latest.json"
RESEARCH_POINTER = ROOT / "runtime" / "excel-mvp-research-cases-latest.json"
APPLICABILITY_POINTER = (
    ROOT / "runtime" / "company-research" / "midea-valuation-applicability-latest.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def under_root(path: Path) -> Path:
    resolved = path.resolve()
    assert resolved.is_relative_to(ROOT.resolve())
    return resolved


def pinned_payload(pointer: Path) -> dict:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = under_root(ROOT / pin["path"] / "evidence.json")
    assert sha256(evidence) == pin["sha256"]
    return json.loads(evidence.read_text(encoding="utf-8"))


@pytest.fixture
def midea_provenance_case(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    result_dir = root / "runtime" / "valuation-results" / "000333-fcff-stage-b"
    result_path = result_dir / "evidence.json"
    result_pointer = root / "runtime" / "valuation-results" / "000333-fcff-stage-b-latest.json"
    research_pointer = root / "runtime" / "excel-mvp-research-cases-latest.json"
    applicability_pointer = (
        root / "runtime" / "company-research" / "midea-valuation-applicability-latest.json"
    )

    research_path = root / "runtime" / "research-cases" / "midea-case" / "evidence.json"
    write_json(
        research_path,
        {"symbol": "000333", "case_id": "synthetic-midea-case", "version": 1},
    )
    write_json(
        research_pointer,
        {
            "path": research_path.parent.relative_to(root).as_posix(),
            "sha256": sha256(research_path),
        },
    )

    applicability_path = (
        root / "runtime" / "company-research" / "midea-applicability" / "evidence.json"
    )
    applicability = {
        "symbol": "000333",
        "model_route": "shared_residual_income",
        "fcff_applicable": False,
    }
    write_json(applicability_path, applicability)
    write_json(
        applicability_pointer,
        {
            "path": applicability_path.parent.relative_to(root).as_posix(),
            "sha256": sha256(applicability_path),
        },
    )

    result = {
        "research_case_ref": {
            "path": research_path.relative_to(root).as_posix(),
            "sha256": sha256(research_path),
        },
        "valuation_applicability": {
            "path": applicability_path.relative_to(root).as_posix(),
            "sha256": sha256(applicability_path),
            "policy": applicability,
        },
        "result": {
            "status": "not_ready",
            "bear_value": None,
            "base_value": None,
            "bull_value": None,
        },
        "price_bridge": {"bridge_status": "PENDING_EXTERNAL_DATA"},
        "formal_fair_value": None,
        "trade_approved": False,
        "live_eligible": False,
    }
    write_json(result_path, result)
    write_json(
        result_pointer,
        {
            "path": result_path.parent.relative_to(root).as_posix(),
            "sha256": sha256(result_path),
        },
    )

    module = sys.modules[__name__]
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "RESULT_DIR", result_dir)
    monkeypatch.setattr(module, "RESULT_PATH", result_path)
    monkeypatch.setattr(module, "RESULT_POINTER", result_pointer)
    monkeypatch.setattr(module, "RESEARCH_POINTER", research_pointer)
    monkeypatch.setattr(module, "APPLICABILITY_POINTER", applicability_pointer)
    return result


def test_midea_unified_result_pins_its_research_and_applicability_snapshot(
    midea_provenance_case,
):
    result_pin = json.loads(RESULT_POINTER.read_text(encoding="utf-8"))
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    assert result_pin["path"] == RESULT_PATH.parent.relative_to(ROOT).as_posix()
    assert sha256(RESULT_PATH) == result_pin["sha256"]

    research_pin = json.loads(RESEARCH_POINTER.read_text(encoding="utf-8"))
    assert result["research_case_ref"]["sha256"] == research_pin["sha256"]
    assert under_root(ROOT / result["research_case_ref"]["path"]) == under_root(
        ROOT / research_pin["path"] / "evidence.json"
    )

    applicability_path = under_root(ROOT / result["valuation_applicability"]["path"])
    assert sha256(applicability_path) == result["valuation_applicability"]["sha256"]
    pinned_snapshot = json.loads(applicability_path.read_text(encoding="utf-8"))
    assert result["valuation_applicability"]["policy"] == pinned_snapshot

    # The current pointer may advance; immutable valuation results keep their own snapshot.
    current_applicability = pinned_payload(APPLICABILITY_POINTER)
    assert current_applicability["symbol"] == "000333"


def test_midea_unified_result_remains_fail_closed_after_provenance_repair(
    midea_provenance_case,
):
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    assert result["result"]["status"] == "not_ready"
    assert (
        result["result"]["bear_value"],
        result["result"]["base_value"],
        result["result"]["bull_value"],
    ) == (None, None, None)
    assert result["price_bridge"]["bridge_status"] == "PENDING_EXTERNAL_DATA"
    assert result["formal_fair_value"] is None
    assert result["trade_approved"] is False
    assert result["live_eligible"] is False

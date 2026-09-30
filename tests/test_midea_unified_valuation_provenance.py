import hashlib
import json
from pathlib import Path


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


def pinned_payload(pointer: Path) -> dict:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = ROOT / pin["path"] / "evidence.json"
    assert sha256(evidence) == pin["sha256"]
    return json.loads(evidence.read_text(encoding="utf-8"))


def test_midea_unified_result_pins_its_research_and_applicability_snapshot():
    result_pin = json.loads(RESULT_POINTER.read_text(encoding="utf-8"))
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    assert sha256(RESULT_PATH) == result_pin["sha256"]

    research_pin = json.loads(RESEARCH_POINTER.read_text(encoding="utf-8"))
    assert result["research_case_ref"]["sha256"] == research_pin["sha256"]
    assert (ROOT / result["research_case_ref"]["path"]).resolve() == (
        ROOT / research_pin["path"] / "evidence.json"
    ).resolve()

    applicability_path = (
        ROOT / result["valuation_applicability"]["path"]
    ).resolve()
    assert sha256(applicability_path) == result["valuation_applicability"]["sha256"]
    pinned_snapshot = json.loads(applicability_path.read_text(encoding="utf-8"))
    assert result["valuation_applicability"]["policy"] == pinned_snapshot

    # The current pointer may advance; immutable valuation results keep their own snapshot.
    current_applicability = pinned_payload(APPLICABILITY_POINTER)
    assert current_applicability["symbol"] == "000333"


def test_midea_unified_result_remains_fail_closed_after_provenance_repair():
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

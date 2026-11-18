"""TEST_ONLY F2 registration and retained successor cold replay."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest

from value_investment_agent.application.research import parent_remaining_year_alignment as alignment
from value_investment_agent.application.research import pending_candidate_alignment as shared


NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
RETAINED = ROOT / "runtime/remaining-q4-successor-20261118/20261118T000059574371Z/compiled/receipt.json"


def _binding(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value), encoding="utf-8")
    return dict(path=path, sha256=sha256(target.read_bytes()).hexdigest())


def _retained():
    return dict(path=RETAINED.relative_to(ROOT).as_posix(),
                sha256=sha256(RETAINED.read_bytes()).hexdigest())


def test_retained_successor_cold_replay_has_real_missing_config():
    if not RETAINED.is_file():
        pytest.skip("retained official successor absent")
    row = alignment.read_parent_remaining_year_alignment(
        root=ROOT, receipt_binding=_retained(), now=NOW)
    assert row["status"] == "BLOCKED"
    assert row["reason_codes"] == ["EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING"]
    assert row["action"] == "no_order" and row["formal_eligibility"] is False
    assert row["currentpricecomparison"] is False


def test_retained_receipt_hash_tampering_fails_before_alignment():
    if not RETAINED.is_file():
        pytest.skip("retained official successor absent")
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        alignment.read_parent_remaining_year_alignment(
            root=ROOT, receipt_binding=dict(_retained(), sha256="0" * 64), now=NOW)


def test_old_config_cannot_be_borrowed_and_exact_test_config_enters_shared_checks(tmp_path, monkeypatch):
    if not RETAINED.is_file():
        pytest.skip("retained official successor absent")
    tmp_path = Path("\\\\?\\" + str(tmp_path))
    receipt_ref = _retained()
    receipt = json.loads(RETAINED.read_text(encoding="utf-8"))
    result = json.loads((ROOT / receipt["result_binding"]["path"]).read_text(encoding="utf-8"))
    spec = json.loads((ROOT / receipt["spec_binding"]["path"]).read_text(encoding="utf-8"))
    predecessor = json.loads((ROOT / receipt["predecessor_binding"]["path"]).read_text(encoding="utf-8"))
    predecessor_spec = json.loads((ROOT / predecessor["spec_binding"]["path"]).read_text(encoding="utf-8"))
    reads = {receipt_ref["sha256"]: receipt,
             receipt["spec_binding"]["sha256"]: spec,
             receipt["predecessor_binding"]["sha256"]: predecessor,
             predecessor["spec_binding"]["sha256"]: predecessor_spec}
    monkeypatch.setattr(alignment, "_read", lambda _root, ref: deepcopy(reads[ref["sha256"]]))
    monkeypatch.setattr(alignment, "replay_parent_remaining_year_successor",
                        lambda **_: deepcopy(result))
    monkeypatch.setattr(alignment, "_official_catalog", lambda *_: [])
    monkeypatch.setattr(alignment, "_capital_anchor", lambda *_: [])
    config_dir = "config/pending-candidate-alignments-v1"
    old = dict(schema_version=alignment.INPUT_SCHEMA,
               candidate_binding=receipt["predecessor_binding"],
               input_descriptor_sha256=receipt["input_descriptor_sha256"])
    _binding(tmp_path, f"{config_dir}/{receipt['predecessor_binding']['sha256']}.json", old)
    missing = alignment.read_parent_remaining_year_alignment(
        root=tmp_path, receipt_binding=receipt_ref, now=NOW)
    assert missing["reason_codes"] == ["EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING"]
    calls = []
    real_shared = shared._load_bound_alignment
    def checked_shared(*, root, analysis, now, input_schema):
        calls.append((analysis["review_binding"]["candidate_binding"], input_schema))
        return real_shared(root=root, analysis=analysis, now=now, input_schema=input_schema)
    monkeypatch.setattr(alignment, "_load_bound_alignment", checked_shared)
    exact = dict(old, candidate_binding=receipt_ref)
    _binding(tmp_path, f"{config_dir}/{receipt_ref['sha256']}.json", exact)
    entered = alignment.read_parent_remaining_year_alignment(
        root=tmp_path, receipt_binding=receipt_ref, now=NOW)
    assert calls[-1] == (receipt_ref, alignment.INPUT_SCHEMA)
    assert entered["status"] == "BLOCKED" and entered["formal_eligibility"] is False
    assert entered["reason_codes"] != ["EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING"]

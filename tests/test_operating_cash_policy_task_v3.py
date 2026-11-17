"""v9 paid-call admission must ignore only the evaluation clock."""
import hashlib
import json

import pytest

from value_investment_agent.application.research.agent_review.operating_cash_policy_task_v3 import (
    OperatingCashPolicyTaskServiceV3,
)


def _seal(root, name, value):
    path = root / "runtime" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(raw)
    return {"path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest()}


def test_same_evidence_different_asof_has_one_paid_source_identity(tmp_path):
    service = OperatingCashPolicyTaskServiceV3(tmp_path, test_provider=object())
    receipt = _seal(tmp_path, "official.json", {"source_sha256": "a" * 64})
    stable = {"schema_version": "operating-horizon-sources-v9", "symbol": "600887",
              "selection": {"choice_id": "DAIRY_FUNDING_PRESSURE"},
              "selected_from": {"sha256": "b" * 64},
              "implementation_sha256": {"module": "c" * 64}, "action": "no_order"}
    first = _seal(tmp_path, "first.json", dict(stable, as_of="2026-11-11T01:00:00+00:00",
        base_context_sha256="d" * 64, base_binding=receipt))
    later = _seal(tmp_path, "later.json", dict(stable, as_of="2026-11-11T02:00:00+00:00",
        base_context_sha256="e" * 64, base_binding=receipt))
    assert first != later
    assert service._stable_source_identity(first) == service._stable_source_identity(later)
    changed_receipt = _seal(tmp_path, "changed-official.json", {"source_sha256": "f" * 64})
    changed = _seal(tmp_path, "changed.json", dict(stable, as_of="2026-11-11T02:00:00+00:00",
        base_context_sha256="e" * 64, base_binding=changed_receipt))
    assert service._stable_source_identity(first) != service._stable_source_identity(changed)
    (tmp_path / first["path"]).write_bytes(b"TAMPERED")
    with pytest.raises(ValueError, match="Task binding hash mismatch"):
        service._stable_source_identity(first)

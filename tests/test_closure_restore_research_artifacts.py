from hashlib import sha256
import json
from pathlib import Path

import pytest

from value_investment_agent.operations.closure_restore_drill import (
    _current_research_artifacts,
)


def _write(root: Path, relative: str, payload: dict) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return sha256(raw).hexdigest()


def test_research_pointer_and_bound_outputs_are_selected(tmp_path):
    output = _write(tmp_path, "artifacts/current/w7/report.md.json", {"report": "ok"})
    manifest = _write(
        tmp_path,
        "artifacts/current/w7/manifest.json",
        {"outputs": {"report.md.json": {"path": "artifacts/current/w7/report.md.json", "sha256": output}}},
    )
    _write(
        tmp_path,
        "config/current-hotspot-structure-validation.json",
        {
            "action": "no_order",
            "manifest_path": "artifacts/current/w7/manifest.json",
            "manifest_sha256": manifest,
        },
    )
    draft = _write(tmp_path, "artifacts/current/midea/draft.json", {"status": "DRAFT_NOT_APPROVED"})
    _write(
        tmp_path,
        "config/current-research-drafts.json",
        {
            "action": "no_order",
            "drafts": {"000333": {"path": "artifacts/current/midea/draft.json", "sha256": draft}},
        },
    )

    assert _current_research_artifacts(tmp_path) == [
        "config/current-research-drafts.json",
        "config/current-hotspot-structure-validation.json",
        "artifacts/current/w7/manifest.json",
        "artifacts/current/w7/report.md.json",
        "artifacts/current/midea/draft.json",
    ]


def test_research_output_hash_mismatch_fails_closed(tmp_path):
    _write(tmp_path, "artifacts/current/w7/report.md.json", {"report": "tampered"})
    manifest = _write(
        tmp_path,
        "artifacts/current/w7/manifest.json",
        {
            "outputs": {
                "report.md.json": {
                    "path": "artifacts/current/w7/report.md.json",
                    "sha256": "a" * 64,
                }
            }
        },
    )
    _write(
        tmp_path,
        "config/current-hotspot-structure-validation.json",
        {
            "action": "no_order",
            "manifest_path": "artifacts/current/w7/manifest.json",
            "manifest_sha256": manifest,
        },
    )

    with pytest.raises(ValueError, match="output hash mismatch"):
        _current_research_artifacts(tmp_path)

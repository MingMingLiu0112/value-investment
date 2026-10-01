"""Build a symbol-neutral current-workbench request from shared research output."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import (
    ACTION_NO_ORDER,
    normalize_symbol,
    receipt,
    require_inside,
    sha256_file,
    write_new_json,
)
from .company_research import run_company_research_for_symbol
from .existing_valuation import read_existing_research_result
from .common import load_json_object


def load_existing_workbench_for_presentation(
    *, root: Path, path: Path, expected_sha256: str,
) -> dict[str, Any]:
    """Recheck result and original bytes at the presentation boundary."""
    path = require_inside(root, path, "existing workbench")
    if sha256_file(path) != expected_sha256:
        raise ValueError("existing workbench hash mismatch")
    payload = load_json_object(path, "existing workbench")
    if (payload.get("schema_version") != "product-existing-research-workbench-v1"
            or payload.get("action") != ACTION_NO_ORDER
            or payload.get("suggested_state") != "NOT_READY"
            or payload.get("position_guidance") is not None):
        raise ValueError("existing workbench presentation scope mismatch")
    records = payload["research"]["source_records"]
    if not records:
        raise ValueError("existing workbench requires original evidence")
    for record in records:
        original = require_inside(root, root / record["path"], "workbench original")
        if sha256_file(original) != record["sha256"]:
            raise ValueError("workbench original hash mismatch")
    return payload


def build_current_workbench_for_symbol(
    *,
    root: Path,
    symbol: str,
    package_path: Path | None = None,
    output_path: Path,
    existing_manifest_path: Path | None = None,
    existing_manifest_sha256: str | None = None,
    arithmetic_input_path: Path | None = None,
    arithmetic_input_sha256: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    target = require_inside(root, output_path, "current workbench output")
    if existing_manifest_path is not None or existing_manifest_sha256 is not None:
        if existing_manifest_path is None or existing_manifest_sha256 is None or package_path is not None:
            raise ValueError("existing workbench requires manifest and hash and excludes package")
        existing = read_existing_research_result(
            root=root, symbol=normalized, manifest_path=existing_manifest_path,
            manifest_sha256=existing_manifest_sha256,
            arithmetic_input_path=arithmetic_input_path,
            arithmetic_input_sha256=arithmetic_input_sha256,
        )
        payload = {
            "schema_version": "product-existing-research-workbench-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbol": normalized, "action": ACTION_NO_ORDER,
            "scope": "EXISTING_RESEARCH_ONLY_NOT_CURRENT_ADVICE",
            "research": existing,
            "suggested_state": "NOT_READY", "position_guidance": None,
            "canonical_workbook_written": False,
        }
        write_new_json(target, payload)
        return {"result": payload, "receipt": {
            "command": "current_workbench", "symbol": normalized,
            "input_sha256": {"existing_manifest": existing_manifest_sha256,
                             "arithmetic_input": arithmetic_input_sha256},
            "output_path": str(target.relative_to(root.resolve())),
            "output_sha256": sha256_file(target), "action": ACTION_NO_ORDER,
        }}
    if arithmetic_input_path is not None or arithmetic_input_sha256 is not None:
        raise ValueError("arithmetic input requires existing-result mode")
    research = run_company_research_for_symbol(
        root=root,
        symbol=normalized,
        package_path=package_path,
        output_path=None,
    )
    payload = {
        "schema_version": "product-current-workbench-request-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": "current_workbench",
        "symbol": normalized,
        "action": ACTION_NO_ORDER,
        "research_status": research["result"]["status"],
        "research_blockers": research["result"]["blockers"],
        "current_status": research["result"]["current_status"],
        "valuation": research["result"]["valuation"],
        "price_bridge": research["result"]["price_bridge"],
        "requires_product_renderer": True,
        "research_receipt": research["receipt"],
    }
    write_new_json(target, payload)
    return {
        "result": payload,
        "receipt": receipt(
            command="current_workbench",
            symbol=normalized,
            input_hashes=research["receipt"]["input_sha256"],
            output_path=target,
            output_bytes=None,
        )
        | {"output_sha256": sha256_file(target)},
    }

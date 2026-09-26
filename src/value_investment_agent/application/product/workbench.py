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


def build_current_workbench_for_symbol(
    *,
    root: Path,
    symbol: str,
    package_path: Path | None = None,
    output_path: Path,
) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    target = require_inside(root, output_path, "current workbench output")
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

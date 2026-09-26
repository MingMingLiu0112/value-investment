"""Build one symbol-specific valuation result through the shared router."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..valuation import build_company_valuation_result
from .common import (
    normalize_symbol,
    receipt,
    require_inside,
    sha256_file,
    write_new_json,
)


def build_company_valuation_for_symbol(
    *,
    root: Path,
    symbol: str,
    case_path: Path,
    facts_path: Path,
    model: str,
    output_path: Path,
    profile_id: str | None = None,
    applicability_path: Path | None = None,
) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    case = require_inside(root, case_path, "valuation case input")
    facts = require_inside(root, facts_path, "valuation facts input")
    applicability = (
        require_inside(root, applicability_path, "valuation applicability input")
        if applicability_path is not None
        else None
    )
    target = require_inside(root, output_path, "valuation output")
    payload = build_company_valuation_result(
        root=root,
        symbol=normalized,
        case_path=case,
        facts_path=facts,
        model=model,
        profile_id=profile_id,
        applicability_path=applicability,
    )
    write_new_json(target, payload)
    return {
        "result": payload,
        "receipt": receipt(
            command="company_valuation",
            symbol=normalized,
            input_hashes={
                "case": sha256_file(case),
                "facts": sha256_file(facts),
                **(
                    {"applicability": sha256_file(applicability)}
                    if applicability is not None
                    else {}
                ),
            },
            output_path=target,
            output_bytes=None,
        )
        | {"output_sha256": sha256_file(target)},
    }

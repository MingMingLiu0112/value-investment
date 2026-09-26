"""Extract and validate one symbol-specific ResearchCase from public input."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ...m1_valuation_package_builder import build_research_case
from .common import (
    load_json_object,
    normalize_symbol,
    receipt,
    require_inside,
    sha256_bytes,
    sha256_file,
    write_new_json,
)


def _candidate_cases(payload: Mapping[str, Any], symbol: str) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    if isinstance(payload.get("symbol"), str):
        candidates.append(payload)
    research_case = payload.get("research_case")
    if isinstance(research_case, Mapping):
        candidates.append(research_case)
    records = payload.get("records")
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, Mapping):
                continue
            case = record.get("case")
            if isinstance(case, Mapping):
                candidates.append(case)
            elif isinstance(record.get("symbol"), str):
                candidates.append(record)
    return [item for item in candidates if item.get("symbol") == symbol]


def build_research_case_for_symbol(
    *,
    root: Path,
    symbol: str,
    source_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    source = require_inside(root, source_path, "research case source")
    if not source.is_file():
        raise ValueError("research case source must be an existing file")
    payload = load_json_object(source, "research case source")
    matches = _candidate_cases(payload, normalized)
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one research case for symbol {normalized}, found {len(matches)}"
        )
    case = build_research_case(matches[0])
    case_payload = json.loads(case.to_json())
    target = (
        require_inside(root, output_path, "research case output")
        if output_path is not None
        else None
    )
    if target is not None:
        write_new_json(target, case_payload)
        output_hash = sha256_file(target)
    else:
        output_hash = sha256_bytes(case.to_json().encode("utf-8"))
    return {
        "case": case_payload,
        "receipt": receipt(
            command="research_case",
            symbol=normalized,
            input_hashes={"research_case_source": sha256_file(source)},
            output_path=target,
            output_bytes=None if target is not None else case.to_json().encode("utf-8"),
        )
        | {"output_sha256": output_hash},
    }

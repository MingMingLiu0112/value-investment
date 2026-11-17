"""Check a registered close against a cold-replayed E2 research version.

The older quote bridge may bind an unrelated historical candidate. This read
model verifies its archived market bytes but uses the E2 receipt's own research
cutoff. It never changes the old registration or grants a current valuation.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import load_json_object, sha256_file
from .quote_bridge import POINTER_PATH, POINTER_SCHEMA, admit_quote_for_research, _resolve_under_runtime


def read_first_input_quote_alignment(*, root: Path, symbol: str, first_input: dict,
                                     now: datetime) -> dict:
    result = dict(schema_version="first-input-quote-alignment-v1", symbol=symbol,
                  status="UNASSESSABLE", reason=None, quote_date=None, display_price=None,
                  quote_binding=None, e2_receipt_binding=first_input.get("receipt_binding"),
                  research_as_of=first_input.get("research_as_of"),
                  input_computed_at=first_input.get("input_computed_at"),
                  quote_source_verified=False,
                  quote_usable_for_e2_research=False, current_valuation_comparable=False,
                  condition_price=None, formal_eligibility=False, action="no_order")
    try:
        if (now.utcoffset() is None or first_input.get("symbol") != symbol
                or first_input.get("status") != "SOURCE_BOUND_FIRST_INPUT_COMPILED"
                or first_input.get("action") != "no_order"
                or first_input.get("formal_eligibility") is not False
                or not first_input.get("receipt_binding")):
            raise ValueError("VERIFIED_E2_FIRST_INPUT_REQUIRED")
        pointer_path = root / POINTER_PATH
        pointer_raw = pointer_path.read_bytes()
        pointer = load_json_object(pointer_path, "quote bridge pointer")
        if (pointer.get("schema_version") != POINTER_SCHEMA or pointer.get("action") != "no_order"
                or not isinstance(pointer.get("quotes"), dict)):
            raise ValueError("QUOTE_POINTER_INVALID")
        entry = pointer["quotes"].get(symbol)
        if not isinstance(entry, dict):
            raise ValueError("QUOTE_NOT_REGISTERED")
        path = _resolve_under_runtime(root, entry.get("quote_bundle"), "first input quote")
        expected = entry.get("quote_bundle_sha256")
        if not isinstance(expected, str) or sha256_file(path) != expected:
            raise ValueError("QUOTE_BINDING_HASH_MISMATCH")
        _, _, verdict = admit_quote_for_research(
            root, path, symbol, first_input["research_as_of"][:10], today=now)
        if pointer_path.read_bytes() != pointer_raw or sha256_file(path) != expected:
            raise ValueError("QUOTE_CHANGED_DURING_READ")
        result.update(status=verdict["status"], reason=verdict.get("reason"),
                      quote_date=verdict.get("quote_date"),
                      display_price=verdict.get("display_price"),
                      quote_binding={"path": path.relative_to(root).as_posix(), "sha256": expected},
                      quote_source_verified=verdict.get("status") in {
                          "QUOTE_VERIFIED_FOR_RESEARCH_INPUT",
                          "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
                          "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY"})
        if verdict.get("price_admitted") is True:
            computed = datetime.fromisoformat(first_input["input_computed_at"])
            collected = datetime.fromisoformat(verdict["collected_at"])
            if computed.utcoffset() is None or collected.utcoffset() is None:
                raise ValueError("E2_OR_QUOTE_CLOCK_UNVERIFIED")
            if computed < collected:
                result.update(status="QUOTE_AFTER_E2_RESEARCH_SNAPSHOT",
                              reason="收盘报价取得时间晚于 E2 研究快照；须以该报价时点重新复核研究与事件。")
            else:
                result["quote_usable_for_e2_research"] = True
        if result["quote_usable_for_e2_research"]:
            result["reason"] = (
                "E2研究日期覆盖已核验收盘；财务更新、股本连续性、期间分配和重大事件"
                "仍须分别复核，不能据此比较当前估值或生成买价。")
    except (ValueError, OSError, KeyError, TypeError) as error:
        result["status"] = "UNASSESSABLE"
        result["quote_usable_for_e2_research"] = False
        result["reason"] = str(error) if isinstance(error, ValueError) else type(error).__name__
    return result

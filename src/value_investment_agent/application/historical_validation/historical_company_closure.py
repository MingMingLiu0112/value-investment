"""Build a readable single-company historical closure from pinned artifacts."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ..product.common import load_json_object, load_json_value, require_inside, sha256_file


INPUT_SCHEMA = "historical-company-closure-input-v1"
OUTPUT_SCHEMA = "historical-company-closure-v1"
ACTION_NO_ORDER = "no_order"
_ACCEPTED_EXECUTION_CONTRACTS = {
    "moutai-real-execution-input-v1",
    "moutai-real-execution-input-v5",
}
_PINNED_KEYS = (
    "m3_replay",
    "m3_manifest",
    "execution_input",
    "execution_summary",
    "execution_journal",
    "execution_manifest",
    "range_result",
    "range_manifest",
    "range_journal",
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field} must be SHA-256 hex")
    return text


def _decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} must be a decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def _binding(root: Path, value: object, label: str) -> tuple[Path, str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} binding is required")
    path = require_inside(root, root / _required_text(value.get("path"), f"{label}.path"), label)
    expected = _sha256(value.get("sha256"), f"{label}.sha256")
    if sha256_file(path) != expected:
        raise ValueError(f"{label} hash mismatch")
    return path, expected, load_json_value(path, label)


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _verify_source_receipts(root: Path, payload: Mapping[str, Any]) -> None:
    for key, receipt in payload.get("source_receipt", {}).items():
        if not isinstance(receipt, Mapping):
            raise ValueError(f"m3 source receipt {key} is invalid")
        if "path" not in receipt and "sha256" not in receipt:
            continue
        path = require_inside(root, root / _required_text(receipt.get("path"), f"{key}.path"), key)
        if sha256_file(path) != _sha256(receipt.get("sha256"), f"{key}.sha256"):
            raise ValueError(f"m3 source receipt {key} hash mismatch")
    refs = [*payload.get("then_known_filings", []), payload["then_known_quote"]["source_ref"]]
    for ref in refs:
        path = require_inside(root, root / _required_text(ref.get("path"), "reference.path"), "reference")
        if sha256_file(path) != _sha256(ref.get("sha256"), "reference.sha256"):
            raise ValueError("m3 evidence reference hash mismatch")


def _execution_metrics(*, input_payload: Mapping[str, Any], journal: list[Any], opening_cash: Decimal) -> dict[str, Any]:
    sessions = input_payload.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("execution input sessions are required")
    if input_payload.get("decisions") != {}:
        raise ValueError("execution clock closure requires a no-decision input")
    if len(journal) != len(sessions):
        raise ValueError("execution journal does not cover every supplied session")
    if journal[0].get("date") != sessions[0].get("date") or journal[-1].get("date") != sessions[-1].get("date"):
        raise ValueError("execution journal session boundary mismatch")
    declared_cash_events = input_payload.get("cash_events")
    if not isinstance(declared_cash_events, list):
        raise ValueError("execution input cash_events are required")
    orders = fills = rejected = 0
    journal_cash_event_rows = 0
    for row in journal:
        if row.get("created_order") is not None or row.get("pending_order_id") is not None:
            orders += 1
        if row.get("fill") is not None:
            fills += 1
        if row.get("rejected_order_reason") is not None:
            rejected += 1
        cash_events = row.get("cash_events", [])
        if not isinstance(cash_events, list):
            raise ValueError("execution journal cash_events must be a list")
        journal_cash_event_rows += len(cash_events)
        if int(row.get("holding_shares", -1)) != 0 or _decimal(row.get("cash_cny"), "cash_cny") != opening_cash:
            raise ValueError("no-decision execution clock changed holdings or cash")
        if _decimal(row.get("nav_cny"), "nav_cny") != opening_cash:
            raise ValueError("no-decision execution clock changed NAV")
    return dict(sessions=len(sessions), first_session=sessions[0]["date"], last_session=sessions[-1]["date"],
        orders=orders, fills=fills, rejected_orders=rejected,
        declared_cash_events=len(declared_cash_events),
        journal_cash_event_rows=journal_cash_event_rows,
        cash_event_rows=journal_cash_event_rows,
        opening_cash_cny=str(opening_cash), ending_cash_cny=str(opening_cash), ending_nav_cny=str(opening_cash))


def _range_metrics(result: Mapping[str, Any], journal: list[Any]) -> dict[str, Any]:
    if (result.get("trade_approved") is not False or result.get("valuation_approved") is not False
            or result.get("live_eligible") is not False or result.get("strategy_backtest_complete") is not False
            or result.get("formal_fair_value") is not None):
        raise ValueError("historical range diagnostics must remain research-only")
    scenarios = result.get("results")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("historical range scenarios are required")
    compact = []
    for row in scenarios:
        compact.append(dict(scenario=_required_text(row.get("scenario"), "scenario"),
            endpoint=_required_text(row.get("endpoint"), "endpoint"), safety_margin=str(row.get("safety_margin")),
            fills=int(row.get("fills", 0)), ending_nav_cny=str(row.get("ending_nav_cny")),
            gross_research_return=str(row.get("gross_research_return")),
            maximum_drawdown=str(row.get("maximum_drawdown")), periods=row.get("periods", [])))
    if len(journal) != int(result.get("sessions", -1)):
        raise ValueError("range journal session count mismatch")
    orders = sum(1 for row in journal if row.get("created_order") is not None)
    fills = sum(1 for row in journal if row.get("fill") is not None)
    rejected = sum(1 for row in journal if row.get("rejected_order_reason") is not None)
    events = []
    for row in journal:
        if row.get("created_order") is not None or row.get("fill") is not None:
            events.append(dict(date=row.get("date"), decision=row.get("decision"),
                created_order=row.get("created_order"), fill=row.get("fill"),
                execution_state_reason=row.get("execution_state_reason")))
    return dict(sessions=len(journal), first_session=journal[0].get("date"), last_session=journal[-1].get("date"),
        scenarios=compact, orders=orders, fills=fills, rejected_orders=rejected, execution_events=events,
        validation_classification=result.get("validation_classification"),
        validation_admission_status=result.get("validation_admission_status"),
        limitations=list(result.get("limitations", [])))


def build_historical_company_closure(*, root: Path, input_path: Path, input_sha256: str) -> dict[str, Any]:
    root = root.resolve()
    recipe_path = require_inside(root, input_path, "historical closure input")
    if sha256_file(recipe_path) != _sha256(input_sha256, "input_sha256"):
        raise ValueError("historical closure input hash mismatch")
    recipe = load_json_object(recipe_path, "historical closure input")
    if (recipe.get("schema_version") != INPUT_SCHEMA or recipe.get("scope") != "READ_ONLY_HISTORICAL_RESEARCH_CLOSURE"
            or recipe.get("action") != ACTION_NO_ORDER):
        raise ValueError("historical closure input scope mismatch")
    symbol = _required_text(recipe.get("symbol"), "symbol")
    if len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("historical closure symbol must contain six digits")
    if set(_PINNED_KEYS) - set(recipe):
        raise ValueError("historical closure input is incomplete")

    _, m3_hash, m3 = _binding(root, recipe["m3_replay"], "m3 replay")
    _, m3_manifest_hash, m3_manifest = _binding(root, recipe["m3_manifest"], "m3 manifest")
    if (m3.get("schema_version") != "m3-historical-research-replay-v1" or m3.get("symbol") != symbol
            or m3.get("action") != ACTION_NO_ORDER or m3.get("valuation_approved") is not False
            or m3.get("trade_approved") is not False or m3.get("future_facts_used") is not False
            or m3.get("future_rule_version_used") is not True or m3.get("final_decision") == "BUY_REVIEW"):
        raise ValueError("M3 replay cannot enter the historical closure")
    if m3_manifest.get("replay_sha256") != _canonical_sha256(m3):
        raise ValueError("M3 replay manifest digest mismatch")
    _verify_source_receipts(root, m3)

    execution_input_path, execution_input_hash, execution_input = _binding(root, recipe["execution_input"], "execution input")
    _, execution_summary_hash, execution_summary = _binding(root, recipe["execution_summary"], "execution summary")
    _, execution_journal_hash, execution_journal = _binding(root, recipe["execution_journal"], "execution journal")
    _, execution_manifest_hash, execution_manifest = _binding(root, recipe["execution_manifest"], "execution manifest")
    if (execution_input.get("contract_version") not in _ACCEPTED_EXECUTION_CONTRACTS
            or execution_input.get("input_scope") != "authenticated_historical_OHLC_and_reviewed_cash_distributions"
            or execution_input.get("symbol") != symbol
            or execution_input.get("valuation_approved") is not False or execution_input.get("trade_approved") is not False
            or execution_input.get("formal_fair_value") is not None):
        raise ValueError("execution input is not an authenticated research-only contract")
    if (execution_summary.get("symbol") != symbol or execution_summary.get("input_sha256") != execution_input_hash
            or execution_summary.get("filled_orders") != [] or execution_summary.get("pending_order") is not None
            or execution_summary.get("trade_approved") is not False or execution_summary.get("live_eligible") is not False):
        raise ValueError("execution summary does not match the no-decision contract")
    for output_name, expected in (("summary.json", execution_summary_hash), ("journal.json", execution_journal_hash)):
        if execution_manifest.get("outputs", {}).get(output_name) != expected:
            raise ValueError("execution manifest output hash mismatch")
    journal = execution_journal
    if not isinstance(journal, list):
        raise ValueError("execution journal must be a list")
    execution = _execution_metrics(input_payload=execution_input, journal=journal,
        opening_cash=_decimal(execution_summary.get("opening_cash_cny"), "opening_cash_cny"))

    _, range_result_hash, range_result = _binding(root, recipe["range_result"], "range result")
    _, range_manifest_hash, range_manifest = _binding(root, recipe["range_manifest"], "range manifest")
    _, range_journal_hash, range_journal = _binding(root, recipe["range_journal"], "range journal")
    if (range_result.get("symbol") != symbol or range_result.get("run_type") != "historical_research_range_sensitivity"):
        raise ValueError("historical range result scope mismatch")
    if range_manifest.get("outputs", {}).get("result.json") != range_result_hash:
        raise ValueError("range manifest result hash mismatch")
    range_journal_name = _required_text(recipe["range_journal"].get("filename"), "range_journal.filename")
    if range_manifest.get("outputs", {}).get(range_journal_name) != range_journal_hash:
        raise ValueError("range manifest journal hash mismatch")
    if not isinstance(range_journal, list) or not range_journal:
        raise ValueError("range journal must be a nonempty list")
    range_diagnostics = _range_metrics(range_result, range_journal)

    sources = [
        dict(role="m3_replay", path=recipe["m3_replay"]["path"], sha256=m3_hash),
        dict(role="m3_manifest", path=recipe["m3_manifest"]["path"], sha256=m3_manifest_hash),
        dict(role="execution_input", path=recipe["execution_input"]["path"], sha256=execution_input_hash),
        dict(role="execution_summary", path=recipe["execution_summary"]["path"], sha256=execution_summary_hash),
        dict(role="execution_journal", path=recipe["execution_journal"]["path"], sha256=execution_journal_hash),
        dict(role="execution_manifest", path=recipe["execution_manifest"]["path"], sha256=execution_manifest_hash),
        dict(role="range_result", path=recipe["range_result"]["path"], sha256=range_result_hash),
        dict(role="range_manifest", path=recipe["range_manifest"]["path"], sha256=range_manifest_hash),
        dict(role="range_journal", path=recipe["range_journal"]["path"], sha256=range_journal_hash),
    ]
    return dict(schema_version=OUTPUT_SCHEMA, generated_at=datetime.now(timezone.utc).isoformat(),
        symbol=symbol, company_name=recipe.get("company_name"), action=ACTION_NO_ORDER,
        engineering_delivery="DELIVERED", current_research_admission="NOT_READY",
        historical_execution_validated=False, strict_pit_admitted=False,
        performance_claim_allowed=False, price_review_eligible=False,
        m3_replay=dict(replay_id=m3.get("replay_id"), replay_date=m3.get("replay_date"),
            final_decision=m3.get("final_decision"), rule=m3.get("rule"),
            then_known_facts=m3.get("then_known_facts"), then_known_quote=m3.get("then_known_quote"),
            blockers=list(m3.get("blockers", []))),
        execution_clock=execution, range_diagnostics=range_diagnostics,
        blockers=["relative_pe_research_only_not_intrinsic_valuation", "retrospective_rule_not_contemporaneous",
            "historical_range_not_pit_safe", "current_price_bridge_not_admitted", "no_order"],
        source_bindings=sources, recipe_sha256=sha256_file(recipe_path))

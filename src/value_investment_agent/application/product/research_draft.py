"""Load a hash-bound, read-only research draft for the product surface.

Research drafts are deliberately separate from the formal publication chain.
They may explain conditional work in progress, but cannot carry price
admission, eligibility, position sizing or execution fields.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from .common import normalize_symbol, sha256_file


POINTER_PATH = Path("config/current-research-drafts.json")
ARTIFACT_ROOT = Path("artifacts/current")
POINTER_SCHEMA = "current-research-drafts-v1"
DRAFT_SCHEMA = "public-research-draft-v1"
BOUND_DRAFT_SCHEMA = "public-research-draft-v2"
DRAFT_STATUS = "RESEARCH_DRAFT_NOT_APPROVED"
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_KEYS = {
    "action_eligibility",
    "buy_quantity",
    "cash_impact",
    "formal_eligibility",
    "holdings",
    "order",
    "order_intent",
    "portfolio_eligibility",
    "position_guidance",
    "position_size",
    "quantity",
    "sell_quantity",
    "target_weight",
    "trade_eligible",
}


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _aware_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("available_at is required")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("available_at must include a timezone")
    return parsed


def _reject_execution_fields(value: object) -> None:
    if isinstance(value, dict):
        overlap = _FORBIDDEN_KEYS.intersection(value)
        if overlap:
            raise ValueError(
                "research draft contains forbidden execution fields: "
                + ", ".join(sorted(overlap))
            )
        for child in value.values():
            _reject_execution_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_execution_fields(child)


def _validate_draft(payload: dict[str, Any], symbol: str, now: datetime) -> None:
    if payload.get("schema_version") not in {DRAFT_SCHEMA, BOUND_DRAFT_SCHEMA}:
        raise ValueError("unknown research draft schema")
    if payload.get("action") != "no_order":
        raise ValueError("research draft must remain no_order")
    if payload.get("symbol") != symbol:
        raise ValueError("research draft symbol mismatch")
    if payload.get("status") != DRAFT_STATUS:
        raise ValueError("research draft is not in the unapproved state")
    _reject_execution_fields(payload)

    if _aware_timestamp(payload.get("available_at")) > now:
        raise ValueError("research draft is not yet available")
    research_as_of = payload.get("research_as_of")
    if not isinstance(research_as_of, str):
        raise ValueError("research_as_of is required")
    if date.fromisoformat(research_as_of[:10]) > now.astimezone(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("research_as_of is in the future")

    valuation = payload.get("valuation")
    if not isinstance(valuation, dict) or valuation.get("status") != "conditional_research_only":
        raise ValueError("research draft valuation is not conditional")
    scenarios = valuation.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("research draft scenarios are required")
    scenario_names = {
        row.get("scenario")
        for row in scenarios
        if isinstance(row, dict) and isinstance(row.get("per_share_value"), str)
    }
    if scenario_names != {"bear", "base", "bull"}:
        raise ValueError("research draft must expose bear, base and bull values")

    bridge = payload.get("price_bridge")
    if not isinstance(bridge, dict) or bridge.get("price_admitted") is not False:
        raise ValueError("research draft cannot admit price")
    quote = payload.get("quote_fact")
    if not isinstance(quote, dict) or quote.get("status") != "VERIFIED_CLOSE_NOT_ADMITTED":
        raise ValueError("research draft quote must remain unadmitted")
    gates = payload.get("gates")
    results = gates.get("results") if isinstance(gates, dict) else None
    if not isinstance(results, dict) or results.get("G3_估值门") is not False:
        raise ValueError("research draft cannot bypass G3")


def _verify_bound_draft(root: Path, payload: dict[str, Any], now: datetime) -> dict:
    from ...m1_valuation_package_builder import build_descriptor
    from ...model_validity import evaluate_model_validity
    from ...valuation_models.residual_income import ResidualIncomeEquityValuationModel
    from .source_bound_inputs import CONSUMED_FACT_CONTRACT_SCHEMA

    binding = payload.get("model_input_binding")
    if not isinstance(binding, dict) or set(binding) != {"package", "input_sha256"}:
        raise ValueError("bound draft requires an exact model input binding")
    package_binding = binding["package"]
    if not isinstance(package_binding, dict) or set(package_binding) != {"path", "sha256"}:
        raise ValueError("bound draft requires an exact package binding")
    if (not isinstance(package_binding["path"], str)
            or not isinstance(package_binding["sha256"], str)
            or not _HASH_RE.fullmatch(package_binding["sha256"])):
        raise ValueError("invalid bound draft package reference")
    relative = Path(package_binding["path"])
    target = (root / relative).resolve()
    if (relative.is_absolute() or ".." in relative.parts
            or not target.is_relative_to((root / ARTIFACT_ROOT).resolve())
            or sha256_file(target) != package_binding["sha256"]):
        raise ValueError("bound draft package path/hash mismatch")
    package = _json_object(target)
    contract = package.get("source_contract")
    if (not isinstance(contract, dict)
            or contract.get("schema_version") != CONSUMED_FACT_CONTRACT_SCHEMA
            or package.get("requested_model") != "residual_income_or_equity_value"
            or package.get("symbol") != payload["symbol"]):
        raise ValueError("bound draft requires matching consumed-fact contract")
    descriptor = build_descriptor(package, root=root)
    if descriptor.input_sha256 != binding["input_sha256"]:
        raise ValueError("bound draft input fingerprint mismatch")
    timing = descriptor.point_in_time
    if (timing.computed_at > now or timing.available_at > now
            or _aware_timestamp(payload["available_at"]) < timing.available_at
            or payload["research_as_of"] != timing.research_as_of.isoformat()
            or payload["financial_facts"] != package["research_case"]["financial_summary"]):
        raise ValueError("bound draft dates or financial display differ from inputs")
    result = ResidualIncomeEquityValuationModel().value(descriptor.facts, descriptor.research_case)
    valuation = payload["valuation"]
    assumption_fields = ("name", "unit", "bear", "base", "bull", "basis", "rationale", "confidence")
    expected_assumptions = [
        {key: row.as_policy()[key] for key in assumption_fields}
        for row in descriptor.assumptions.assumptions
    ]
    if valuation.get("assumptions") != expected_assumptions:
        raise ValueError("bound draft assumptions differ from model inputs")
    if any(valuation.get(field) != getattr(result, field) for field in ("model_type", "model_version", "confidence")):
        raise ValueError("bound draft model identity/confidence mismatch")
    if valuation.get("valuation_date") != result.valuation_date.isoformat():
        raise ValueError("bound draft valuation date mismatch")
    rows = valuation["scenarios"]
    if len(rows) != 3:
        raise ValueError("bound draft requires three unique scenarios")
    sensitivities = {row["scenario"]: row for row in result.sensitivities}
    for row in rows:
        value = Decimal(row["per_share_value"])
        if not value.is_finite() or value != getattr(result, row["scenario"] + "_value"):
            raise ValueError("bound draft scenario differs from shared model")
        for field in ("terminal_residual_contribution_ratio", "basis_to_valuation_factor",
                      "dividend_crosscheck_difference"):
            if field in row:
                expected = sensitivities[row["scenario"]].get(field)
                displayed = Decimal(row[field])
                if expected is None or not displayed.is_finite() or displayed != Decimal(expected):
                    raise ValueError("bound draft derivation differs from shared model")
    quote = descriptor.quote
    displayed_quote = payload["quote_fact"]
    if (quote is None or quote.status != "verified_close"
            or displayed_quote.get("quote_date") != quote.quote_date.isoformat()
            or Decimal(displayed_quote["current_price"]) != quote.current_price):
        raise ValueError("bound draft quote differs from source-bound input")
    validity_input = descriptor.model_validity_input
    if validity_input is None:
        raise ValueError("bound draft requires model validity evidence")
    validity = evaluate_model_validity(
        model_id=validity_input.model_id, symbol=descriptor.symbol,
        model_as_of=result.valuation_date, valid_from=validity_input.valid_from,
        quote_date=quote.quote_date, events=list(validity_input.events),
        event_scan_evidence_refs=list(validity_input.event_scan_evidence_refs),
        blockers=list(validity_input.blockers), event_scan=validity_input.event_scan,
    )
    validity_policy = json.loads(validity.to_json())
    validity_fields = ("model_id", "model_as_of", "last_material_event_check", "status", "blockers")
    if payload.get("model_validity") != {key: validity_policy[key] for key in validity_fields}:
        raise ValueError("bound draft model validity differs from evidence")
    bridge = payload["price_bridge"]
    if (bridge.get("status") != "INVALID"
            or any(value is not None for key, value in bridge.items() if key.startswith("margin_to_"))):
        raise ValueError("bound research draft must not admit price assessment")
    anchors = {row["field"]: row for row in contract["fact_anchors"]}
    capital = []
    for mapping in contract["consumed_fact_bindings"]:
        row = anchors[mapping["anchor_field"]]
        derivation = row.get("derivation", {})
        capital.append(dict(field=mapping["field_path"].split(".")[-1], value=row["source_value"],
            unit=row["unit"], scope=row["scope"], period_end=row["period_end"],
            source_id=row["source_id"], physical_page=row["physical_page"],
            normalization_rule=derivation.get("rule", "DIRECT"),
            component_values=[anchors[field]["source_value"] for field in derivation.get("component_fields", [])]))
    return dict(status="SOURCE_AND_MODEL_INPUTS_MATCH", input_sha256=descriptor.input_sha256,
        computed_at=timing.computed_at.isoformat(), cutoff_at=contract["cutoff_at"],
        basis_date=capital[0]["period_end"], share_basis=contract["share_basis"],
        capital_inputs=capital, economic_approval=False)


def load_current_research_draft(
    root: Path,
    symbol: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return a verified draft, or ``None`` when it is absent or invalid."""

    try:
        normalized = normalize_symbol(symbol)
        pointer = _json_object(root / POINTER_PATH)
        if pointer.get("schema_version") != POINTER_SCHEMA or pointer.get("action") != "no_order":
            raise ValueError("unknown research draft pointer")
        drafts = pointer.get("drafts")
        entry = drafts.get(normalized) if isinstance(drafts, dict) else None
        if entry is None:
            return None
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ValueError("invalid research draft binding")
        relative_value = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(relative_value, str) or not isinstance(digest, str):
            raise ValueError("invalid research draft binding fields")
        if not _HASH_RE.fullmatch(digest):
            raise ValueError("invalid research draft digest")

        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("invalid research draft path")
        approved_root = (root / ARTIFACT_ROOT).resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(approved_root) or not target.is_file():
            raise ValueError("research draft outside approved artifacts")
        if sha256_file(target) != digest:
            raise ValueError("research draft hash mismatch")

        payload = _json_object(target)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must include a timezone")
        _validate_draft(payload, normalized, current)
        # Verification is derived locally, never accepted from a draft author.
        payload.pop("input_verification", None)
        if payload["schema_version"] == BOUND_DRAFT_SCHEMA:
            payload["input_verification"] = _verify_bound_draft(root, payload, current)
        return payload
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError, json.JSONDecodeError, UnicodeError):
        return None

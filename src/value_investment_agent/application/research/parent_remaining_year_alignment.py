"""Read-only F2 projection of an exact, cold-replayed remaining-year receipt."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .direct_owner_cash_research_v1 import _read
from .direct_owner_cash_alignment_v1 import _official_catalog, _capital_anchor
from .parent_remaining_year_successor import RECEIPT_SCHEMA, replay_parent_remaining_year_successor
from .pending_candidate_alignment import CONFIG_DIRECTORY, _load_bound_alignment
from ...research_artifact_codecs import ValuationResultCodec
from ..product.common import load_json_object, require_inside


INPUT_SCHEMA = "parent-remaining-year-alignment-input-v1"
SCHEMA = "parent-remaining-year-alignment-v1"


def read_parent_remaining_year_alignment(*, root: Path, receipt_binding: dict,
                                         now: datetime) -> dict:
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("SUCCESSOR_ALIGNMENT_AWARE_CLOCK_REQUIRED")
    receipt = _read(root, receipt_binding)
    if receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("action") != "no_order":
        raise ValueError("SUCCESSOR_ALIGNMENT_EXACT_RECEIPT_REQUIRED")
    result = replay_parent_remaining_year_successor(
        root=root, receipt_binding=receipt_binding, now=now)
    spec = _read(root, receipt["spec_binding"])
    predecessor = _read(root, receipt["predecessor_binding"])
    predecessor_spec = _read(root, predecessor["spec_binding"])
    valuation = ValuationResultCodec().from_payload(result["valuation"])
    symbol = result["symbol"]
    valuation_date = predecessor_spec["valuation_date"]
    if (result.get("schema_version") != RECEIPT_SCHEMA
            or result.get("action") != "no_order"
            or result.get("formal_eligibility") is not False
            or result.get("main_range_adopted") is not False
            or result.get("successor_adopted") is not False
            or receipt.get("symbol") != symbol
            or receipt.get("predecessor_binding") != result.get("predecessor_binding")
            or spec.get("predecessor_binding") != receipt["predecessor_binding"]
            or receipt.get("spec_binding") != result.get("spec_binding")
            or receipt.get("input_descriptor_sha256") != result.get("input_descriptor_sha256")
            or receipt.get("source_bindings") != result.get("source_bindings")
            or result.get("compiled", {}).get("valuation_date") != valuation_date
            or result.get("compiled", {}).get("symbol") != symbol
            or result.get("research_case", {}).get("symbol") != symbol
            or result.get("package", {}).get("symbol") != symbol
            or predecessor_spec.get("symbol") != symbol
            or predecessor_spec.get("currency") != "CNY"
            or any(row.get("currency") != "CNY" or row.get("symbol") != symbol
                   for row in result.get("package", {}).get("facts", {}).get(
                       "scenario_inputs", {}).values())
            or valuation.symbol != symbol
            or valuation.valuation_date.isoformat() != valuation_date
            or valuation.status != "conditional_research_only"
            or result.get("package", {}).get("source_contract", {}).get(
                "quarterly_source_context", {}).get("report_period") != spec.get("period_end")):
        raise ValueError("SUCCESSOR_ALIGNMENT_COLD_RESULT_IDENTITY_CHANGED")
    bindings = [dict(ref) for ref in result["source_bindings"]]
    for ref in (receipt_binding, receipt["spec_binding"], receipt["result_binding"],
                receipt["predecessor_binding"]):
        if ref not in bindings:
            bindings.append(dict(ref))
    catalog = _official_catalog(result["package"], result["source_bindings"], symbol)
    anchors = _capital_anchor(result["compiled"], catalog, symbol)
    analysis = dict(status="CONDITIONAL_ANALYSIS_VERIFIED", action="no_order",
        event_pdf_byte_limit=128 * 1024 * 1024, arithmetic_complete=True,
        symbol=symbol, valuation_date=valuation_date,
        research_as_of=spec["research_as_of"],
        input_descriptor_sha256=result["input_descriptor_sha256"],
        review_binding=dict(candidate_binding=dict(receipt_binding)),
        valuation=result["valuation"], source_bindings=bindings,
        source_catalog=catalog, official_fact_anchors=anchors,
        consumed_operating_inputs=dict(ordinary_shares=result["compiled"]["ordinary_shares"]),
        joint_capital_review=dict(economic_path=dict(currency="CNY")))
    materiality = dict(status="INPUT_ADAPTER_REQUIRED_IF_AUTHENTICATED_MATERIALITY",
                       reason="No exact successor model review envelope is bound.")
    config_path = root / CONFIG_DIRECTORY / (receipt_binding["sha256"] + ".json")
    if config_path.is_file():
        config_path = require_inside(root, config_path, "successor alignment configuration")
        config_ref = dict(path=config_path.relative_to(root).as_posix(),
                          sha256=sha256(config_path.read_bytes()).hexdigest())
        config = load_json_object(config_path, "successor alignment configuration")
        envelope_ref = config.get("materiality_envelope_binding")
        if envelope_ref is not None:
            if (config.get("schema_version") != INPUT_SCHEMA
                    or config.get("candidate_binding") != receipt_binding
                    or config.get("input_descriptor_sha256") != result["input_descriptor_sha256"]):
                raise ValueError("SUCCESSOR_MATERIALITY_ALIGNMENT_IDENTITY_MISMATCH")
            envelope = _read(root, envelope_ref)
            if envelope.get("receipt_binding") != receipt_binding:
                raise ValueError("SUCCESSOR_MATERIALITY_RECEIPT_MISMATCH")
            from ..product.research_materiality_reviews import _direct_review_original
            _direct_review_original(root=root, envelope=envelope)
            analysis["review_binding"]["package_binding"] = dict(envelope_ref)
            for ref in (config_ref, envelope_ref, envelope["package_binding"]):
                if ref not in bindings:
                    bindings.append(dict(ref))
            materiality = dict(status="EXACT_SUCCESSOR_REVIEW_ENVELOPE_BOUND",
                               envelope_binding=dict(envelope_ref), approval_granted=False)
    aligned = _load_bound_alignment(root=root, analysis=analysis, now=now,
                                    input_schema=INPUT_SCHEMA)
    return dict(aligned, schema_version=SCHEMA,
                research_artifact_kind="PARENT_REMAINING_YEAR_SUCCESSOR_RECEIPT",
                receipt_binding=dict(receipt_binding), formal_eligibility=False,
                action="no_order", materiality_input_adapter=materiality,
                ordinary_shares_fact_anchor_status=("MATCHED_CONSUMED_OFFICIAL_SOURCE"
                    if anchors else "NO_MATCHED_OFFICIAL_SOURCE_ANCHOR"))

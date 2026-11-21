"""Read-only F2 alignment projection for an exact direct-owner-cash receipt.

The receipt remains a direct research artifact. This adapter supplies only
verified fields to the shared alignment checks; it never creates a pending
candidate, a materiality package, or an approved/current price.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
from urllib.parse import urlsplit

from .direct_owner_cash_research_v1 import (
    RECEIPT_SCHEMA, _read, replay_direct_owner_cash_receipt,
)
from .pending_candidate_alignment import CONFIG_DIRECTORY, _load_bound_alignment
from ...research_artifact_codecs import ValuationResultCodec
from ..product.common import load_json_object, require_inside


INPUT_SCHEMA = "direct-owner-cash-alignment-input-v1"
SCHEMA = "direct-owner-cash-alignment-v1"
KIND = "DIRECT_OWNER_CASH_RECEIPT"


def _official_catalog(package: dict, source_bindings: list[dict], symbol: str) -> list[dict]:
    bound = {(row["path"], row["sha256"]) for row in source_bindings}
    catalog = []
    for source in package["sources"]:
        row = deepcopy(source)
        url = urlsplit(row.get("location", ""))
        issuer = row.get("issuer_identity") or {}
        official = (url.scheme == "https" and url.hostname == "static.cninfo.com.cn"
                    and re.fullmatch(r"/finalpage/\d{4}-\d{2}-\d{2}/\d+\.PDF", url.path) is not None
                    and row.get("id") == "cninfo:" + url.path.rsplit("/", 1)[1][:-4]
                    and issuer.get("security_code") == symbol
                    and (row.get("local_path"), row.get("sha256")) in bound)
        row["native_kind"] = row.get("kind")
        if official:
            row["kind"] = "official_issuer_filing"
        row["source_available_at"] = row.get("retrieved_at")
        catalog.append(row)
    return catalog


def _capital_anchor(compiled: dict, catalog: list[dict], symbol: str) -> list[dict]:
    statements = [row for row in compiled["evidence"]["statements"]
                  if row.get("period_end") == compiled["valuation_date"]]
    if len(statements) != 1:
        raise ValueError("DIRECT_ALIGNMENT_EXACT_PARENT_BASIS_REQUIRED")
    proof = statements[0].get("ordinary_shares_evidence") or {}
    if proof.get("classification") != "FACT":
        return []
    if (proof.get("unit") != "shares"
            or proof.get("scope") != "TOTAL_ISSUED_ORDINARY_SHARES"
            or proof.get("period_end") != compiled["valuation_date"]
            or proof.get("count") != compiled["ordinary_shares"]
            or not proof.get("source_refs")):
        raise ValueError("DIRECT_ALIGNMENT_CONSUMED_SHARE_FACT_INVALID")
    refs = proof["source_refs"]
    if isinstance(refs, dict):
        refs = [refs]
    if not isinstance(refs, list):
        raise ValueError("DIRECT_ALIGNMENT_SHARE_SOURCE_REFS_INVALID")
    anchors = []
    for source in catalog:
        if source.get("kind") != "official_issuer_filing":
            continue
        for ref in refs:
            if (isinstance(ref, dict) and ref.get("path") == source.get("local_path")
                    and ref.get("sha256") == source.get("sha256")
                    and isinstance(ref.get("physical_page"), int)
                    and isinstance(ref.get("excerpt"), str) and ref["excerpt"].strip()):
                anchors.append(dict(source_id=source["id"], field="ordinary_shares",
                                    source_value=proof["count"],
                                    unit=proof["unit"], period_end=proof["period_end"],
                                    physical_page=ref["physical_page"],
                                    excerpt=ref["excerpt"],
                                    binding=dict(path=ref["path"], sha256=ref["sha256"])))
    return anchors


def read_direct_owner_cash_alignment(*, root: Path, receipt_binding: dict,
                                     now: datetime) -> dict:
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("DIRECT_ALIGNMENT_AWARE_CLOCK_REQUIRED")
    receipt = _read(root, receipt_binding)
    if receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("action") != "no_order":
        raise ValueError("DIRECT_ALIGNMENT_EXACT_DIRECT_RECEIPT_REQUIRED")
    result = replay_direct_owner_cash_receipt(
        root=root, receipt_binding=receipt_binding, now=now)
    spec = _read(root, receipt["spec_binding"])
    valuation = ValuationResultCodec().from_payload(result["valuation"])
    if (result.get("action") != "no_order" or result.get("formal_eligibility") is not False
            or result.get("main_range_adopted") is not False
            or result.get("input_descriptor_sha256") != receipt.get("input_descriptor_sha256")
            or valuation.symbol != result["symbol"]
            or valuation.valuation_date.isoformat() != spec["valuation_date"]
            or spec.get("currency") != "CNY" or spec.get("symbol") != result["symbol"]):
        raise ValueError("DIRECT_ALIGNMENT_COLD_RESULT_IDENTITY_CHANGED")
    source_bindings = [dict(ref) for ref in result["source_bindings"]]
    for ref in (receipt_binding, receipt["spec_binding"], receipt["result_binding"]):
        if ref not in source_bindings:
            source_bindings.append(dict(ref))
    catalog = _official_catalog(result["package"], result["source_bindings"], result["symbol"])
    anchors = _capital_anchor(result["compiled"], catalog, result["symbol"])
    analysis = dict(status="CONDITIONAL_ANALYSIS_VERIFIED", action="no_order",
        event_pdf_byte_limit=128 * 1024 * 1024,
        arithmetic_complete=True, symbol=result["symbol"],
        valuation_date=spec["valuation_date"], research_as_of=spec["research_as_of"],
        input_descriptor_sha256=result["input_descriptor_sha256"],
        review_binding=dict(candidate_binding=dict(receipt_binding)),
        valuation=result["valuation"], source_bindings=source_bindings,
        source_catalog=catalog, official_fact_anchors=anchors,
        consumed_operating_inputs=dict(ordinary_shares=result["compiled"]["ordinary_shares"]),
        joint_capital_review=dict(economic_path=dict(currency="CNY")))
    materiality_adapter = dict(
        status="INPUT_ADAPTER_REQUIRED_IF_AUTHENTICATED_MATERIALITY",
        reason="No exact direct model review envelope is bound.")
    config_path = root / CONFIG_DIRECTORY / (receipt_binding["sha256"] + ".json")
    if config_path.is_file():
        config_path = require_inside(root, config_path, "direct alignment configuration")
        config_ref = dict(path=config_path.relative_to(root).as_posix(),
                          sha256=sha256(config_path.read_bytes()).hexdigest())
        config = load_json_object(config_path, "direct alignment configuration")
        envelope_ref = config.get("materiality_envelope_binding")
        if envelope_ref is not None:
            if (config.get("schema_version") != INPUT_SCHEMA
                    or config.get("candidate_binding") != receipt_binding
                    or config.get("input_descriptor_sha256") != result["input_descriptor_sha256"]):
                raise ValueError("DIRECT_MATERIALITY_ALIGNMENT_IDENTITY_MISMATCH")
            envelope = _read(root, envelope_ref)
            if envelope.get("receipt_binding") != receipt_binding:
                raise ValueError("DIRECT_MATERIALITY_RECEIPT_MISMATCH")
            from ..product.research_materiality_reviews import _direct_review_original
            _direct_review_original(root=root, envelope=envelope)
            analysis["review_binding"]["package_binding"] = dict(envelope_ref)
            for ref in (config_ref, envelope_ref, envelope["package_binding"]):
                if ref not in source_bindings:
                    source_bindings.append(dict(ref))
            materiality_adapter = dict(status="EXACT_DIRECT_REVIEW_ENVELOPE_BOUND",
                envelope_binding=dict(envelope_ref), approval_granted=False,
                reason="Bound review inputs only; authenticated event decisions remain required.")
    aligned = _load_bound_alignment(root=root, analysis=analysis, now=now,
                                    input_schema=INPUT_SCHEMA)
    return dict(aligned, schema_version=SCHEMA, research_artifact_kind=KIND,
                receipt_binding=dict(receipt_binding), formal_eligibility=False,
                action="no_order", materiality_input_adapter=materiality_adapter,
                ordinary_shares_fact_anchor_status=("MATCHED_CONSUMED_OFFICIAL_SOURCE"
                    if anchors else "NO_MATCHED_OFFICIAL_SOURCE_ANCHOR"))

"""D1 projection of previously admitted, independently replayed income facts."""

from datetime import datetime
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from ....financial_quality import _accepted
from ....infrastructure.screening.financial_export_v2 import load_retained_financial_export
from ....infrastructure.screening.value_evidence_enrichment_v1 import RetainedAnnualSource
from ..income_source_correlation import FIELDS, PREFIX, VERSION, reverify_income_inputs
from ..value_research_queue import _load_bound
from .operating_sources_v1 import _public_adoption, build_operating_source_context, encode
from .web_research import _binding


def _existing_parent_profit(root, source, points, cutoff):
    candidates = [
        point for point in points
        if point.get("symbol") == source.symbol and point.get("period_label") == source.period
        and point.get("field_name") == "net_income"
        and (str(point.get("data_point_id", "")).startswith(PREFIX)
             or (point.get("metadata") or {}).get("income_source_version") == VERSION)
    ]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError("D1_EXISTING_PARENT_PROFIT_AMBIGUOUS")
    point = candidates[0]
    meta = point["metadata"]
    if (not _accepted(point) or point["unit"] != "CNY" or meta["currency"] != "CNY"
            or meta["statement_scope"] != "consolidated" or point["sha256"] != source.sha256
            or meta["income_official_source"] != asdict(source)
            or meta["secondary_item_field"] != FIELDS["net_income"]
            or meta["secondary_report_period"] != source.period):
        raise ValueError("D1_EXISTING_PARENT_PROFIT_NOT_ADMITTED")
    # Regenerates the exact fact from the original PDF, independent structured
    # response and its acquisition receipt. Saved admission flags grant no trust.
    reverify_income_inputs(root, source, [point], evaluation_at=cutoff, write_cache=False)
    stamp = datetime.fromisoformat(point["available_at"])
    if stamp.utcoffset() is None or stamp > cutoff:
        raise ValueError("D1_EXISTING_PARENT_PROFIT_AFTER_CUTOFF")
    secondary = meta["income_secondary"]
    refs = [
        dict(path=source.path, sha256=source.sha256, page=meta["official_page"],
             excerpt=meta["official_excerpt"]),
        {key: secondary[key] for key in ("path", "sha256")},
        secondary["receipt"],
    ]
    return dict(id=point["data_point_id"], source_id=point["source_id"], pdf_sha256=source.sha256,
                available_at=point["available_at"], period=source.period, scope="consolidated",
                unit="CNY", value=point["value"], field="net_income", period_basis="FY",
                profit_basis="attributable_to_parent", text=meta["official_excerpt"],
                physical_page=meta["official_page"], evidence_refs=refs,
                verification_method=meta["verification_method"],
                kind="VERIFIED_ADOPTED_FINANCIAL_FACT")


def build_d1_source_context(*, root, symbol, now, binding=None):
    root = Path(root)
    context = build_operating_source_context(root=root, symbol=symbol, now=now, binding=binding)
    # This field is emitted only by the verified public-adoption legacy path.
    if "statement_basis_status" not in context:
        return context
    if any(row.get("field") == "net_income" and row.get("period") == context["financial_basis"]
           for row in context["evidence"]):
        return context
    adoption = _public_adoption(root, symbol, now, context["source_binding"])
    pin = adoption["result_binding"]
    result = _load_bound(_binding(root, pin), pin["sha256"])
    export = adoption["financial_export"]
    if export not in context["source_bindings"]:
        raise ValueError("D1_FINANCIAL_EXPORT_BINDING_CHANGED")
    path = _binding(root, export)
    _load_bound(path, export["sha256"])
    cutoff = datetime.fromisoformat(result["evaluation_at"])
    source = RetainedAnnualSource(**result["source_extraction"]["identity"]["source"])
    if cutoff.utcoffset() is None or cutoff > now or source.symbol != symbol or source.period != context["financial_basis"]:
        raise ValueError("D1_EXISTING_PARENT_PROFIT_BINDING_MISMATCH")
    points, _ = load_retained_financial_export(path, evaluation_at=cutoff)
    fact = _existing_parent_profit(root, source, points, cutoff)
    _load_bound(path, export["sha256"])
    if fact is None:
        return context

    evidence = [*context["evidence"], fact]
    if len(evidence) > 100 or any(row["id"] == fact["id"] for row in context["evidence"]):
        raise ValueError("D1_EXISTING_PARENT_PROFIT_EVIDENCE_LIMIT_OR_DUPLICATE")
    refs = list(context["source_bindings"])
    for ref in fact["evidence_refs"]:
        binding = {key: ref[key] for key in ("path", "sha256")}
        if binding not in refs:
            refs.append(binding)
    updated = dict(context, evidence=evidence, source_bindings=refs,
                   d1_projection_version="existing-parent-profit-v2")
    del updated["snapshot_fingerprint"]
    updated["snapshot_fingerprint"] = sha256(encode(updated)).hexdigest()
    if len(encode(updated)) > 100000:
        raise ValueError("OPERATING_SOURCE_CONTEXT_TOO_LARGE")
    return updated

"""Evidence-aware scheduling; no research admission or investment ranking."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any

from .value_research_queue import _canonical_hash, _load_bound, build_value_research_queue
from ...financial_quality import GENERAL_FIELDS, _accepted
from ...m2_discovery_engine import _point_available_at
from ...m2_opportunity_discovery import discovery_receipt_from_payload
from ...infrastructure.screening.evidence_screen_v3 import VERSION, evaluate_financial_quality, selected_period
from ...infrastructure.screening.financial_export_v2 import adopt_annual_export

SCHEMA_VERSION = "value-research-priority-v2"


def reuse_durable_income_export(*, root, export, export_sha256, points, sources, symbols, evaluation_at):
    """Replay checkpoint-bound income inputs into a separate immutable export."""
    from .income_source_correlation import PREFIX, VERSION as INCOME_VERSION, reverify_income_inputs
    from .value_enrichment_batch import _verified_registered_adoption
    from ..product.common import require_inside, write_new_json
    from ...infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress
    from ...infrastructure.screening.financial_export_v2 import load_retained_financial_export
    from ...infrastructure.screening.value_evidence_enrichment_v1 import RetainedAnnualSource

    root = root.resolve()
    payload = _load_bound(export, export_sha256)
    origin = payload.get('value_enrichment_base_export')
    if origin:
        base_path = require_inside(root / 'runtime', root / origin['path'], 'base financial export')
        base_payload = _load_bound(base_path, origin['sha256'])
        if base_payload.get('points') != payload.get('points'):
            raise ValueError('Reused income export replaced base points')
    else:
        origin = dict(path=export.relative_to(root).as_posix(), sha256=export_sha256)
    identities = {p['data_point_id']: p for p in points if p.get('data_point_id')}
    added, reused = [], []
    progress = ValueEnrichmentProgress(root)
    eligible_sources = {}
    for source in sources:
        symbol = source['symbol']
        if symbol not in symbols:
            continue
        identity = (symbol, source['period'])
        if identity in eligible_sources and eligible_sources[identity] != source:
            raise ValueError('Conflicting durable income source declarations')
        eligible_sources[identity] = source
    for source in eligible_sources.values():
        symbol = source['symbol']
        binding = progress.registered_adoption(symbol, cutoff=evaluation_at)
        if binding is None:
            continue
        saved_export = binding['financial_export']
        path = require_inside(root / 'runtime', root / saved_export['path'], 'durable income export')
        _load_bound(path, saved_export['sha256'])
        saved_points, _ = load_retained_financial_export(path, evaluation_at=evaluation_at)
        income = [p for p in saved_points if p.get('symbol') == symbol and (
            str(p.get('data_point_id', '')).startswith(PREFIX)
            or (p.get('metadata') or {}).get('income_source_version') == INCOME_VERSION)]
        if not income:
            continue
        verified = _verified_registered_adoption(root, symbol, evaluation_at, binding=binding)
        if verified[2]['source_extraction']['identity']['source'] != source:
            raise ValueError('Durable income source differs from current official source')
        saved_ids = {p.get('data_point_id'): p for p in saved_points if p.get('symbol') == symbol}
        income_ids = {p['data_point_id'] for p in income}
        current_ids = {p['data_point_id'] for p in points
                       if p.get('symbol') == symbol and p.get('data_point_id')}
        if set(saved_ids) - income_ids != current_ids - income_ids:
            raise ValueError('Durable income base company input identities changed')
        for point in points:
            if point.get('symbol') == symbol and point.get('data_point_id'):
                if saved_ids.get(point['data_point_id']) != point:
                    raise ValueError('Durable income base company inputs changed')
        reverify_income_inputs(root, RetainedAnnualSource(**source), income, evaluation_at=evaluation_at)
        for point in income:
            identity = point['data_point_id']
            if identity in identities:
                if identities[identity] != point:
                    raise ValueError('Conflicting durable income input identity')
            else:
                identities[identity] = point
                added.append(point)
        reused.append(dict(symbol=symbol, source=source, financial_export=saved_export,
                           result_binding=binding['result_binding'], input_fact_ids=[p['data_point_id'] for p in income]))
    if not added:
        return export, export_sha256, points, reused
    combined = deepcopy(payload)
    combined.setdefault('annual_points', []).extend(added)
    combined['value_enrichment_base_export'] = origin
    combined['value_enrichment_sources'] = sources
    target = require_inside(root / 'runtime', root / 'runtime/value-evidence-enrichment/inputs' /
        (_canonical_hash(combined) + '.json'), 'reused income export')
    if target.exists():
        if _load_bound(target, hashlib.sha256(target.read_bytes()).hexdigest()) != combined:
            raise ValueError('Existing reused income export differs from replay')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        write_new_json(target, combined)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return target, digest, [*points, *added], reused


def build_value_research_priority_v2(
    *, root: Path, report_path: Path, report_sha256: str,
    receipt_path: Path, receipt_sha256: str, budget: int,
    financial_export_path: Path, financial_export_sha256: str,
    enrichment_budget: int = 10,
    previous_path: Path | None = None, previous_sha256: str | None = None,
) -> dict[str, Any]:
    if isinstance(enrichment_budget, bool) or not isinstance(enrichment_budget, int) or enrichment_budget < 0:
        raise ValueError("enrichment budget must be a nonnegative integer")
    # Delegate all discovery identity, raw-source, lead and legacy continuity checks.
    legacy = build_value_research_queue(
        root=root, report_path=report_path, report_sha256=report_sha256,
        receipt_path=receipt_path, receipt_sha256=receipt_sha256, budget=budget,
        previous_path=previous_path, previous_sha256=previous_sha256)
    receipt = discovery_receipt_from_payload(_load_bound(receipt_path, receipt_sha256))
    export = financial_export_path.resolve()
    if not export.is_relative_to((root / "runtime").resolve()):
        raise ValueError("financial export must remain inside runtime")
    payload = _load_bound(export, financial_export_sha256)
    submitted_overlay = None
    if payload.get('value_enrichment_base_export'):
        from ..product.common import require_inside
        submitted_overlay = (export, financial_export_sha256)
        origin = payload['value_enrichment_base_export']
        export = require_inside(root / 'runtime', root / origin['path'], 'base financial export')
        financial_export_sha256 = origin['sha256']
        original = _load_bound(export, financial_export_sha256)
        if original.get('value_enrichment_base_export') or original.get('points') != payload.get('points'):
            raise ValueError('Invalid reused income base export binding')
        payload = original
    financial_refs = [ref for ref in receipt.evidence_refs if ref.id == "financial"]
    if len(financial_refs) != 1:
        raise ValueError("receipt requires one financial reference")
    ref = financial_refs[0]
    retained = _load_bound(root / ref.path, ref.sha256)
    base = retained.get("points")
    if not isinstance(base, list) or payload.get("points") != base:
        raise ValueError("financial export base points differ from retained snapshot")
    adoption = None
    points = base
    if "annual_points" in payload:
        points, adoption = adopt_annual_export(export, sha256=financial_export_sha256,
            evaluation_at=receipt.generated_at, base_points=base)
    enrichment_adoption = []
    from ...infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress
    candidate_symbols = {entry['symbol'] for entry in legacy['entries']}
    declarations = {}
    sources = [*payload.get('value_enrichment_sources', []),
               *ValueEnrichmentProgress(root).completed_sources(cutoff=receipt.generated_at)]
    for source in sources:
        if source['symbol'] not in candidate_symbols:
            continue
        identity = (source['symbol'], source['period'])
        if identity in declarations and declarations[identity] != source:
            raise ValueError('conflicting declared and completed enrichment source')
        declarations[identity] = source
    export, financial_export_sha256, points, income_reuse = reuse_durable_income_export(
        root=root, export=export, export_sha256=financial_export_sha256, points=points,
        sources=list(declarations.values()), symbols=candidate_symbols,
        evaluation_at=receipt.generated_at)
    if submitted_overlay and submitted_overlay != (export, financial_export_sha256):
        raise ValueError('Reused income export differs from source-replayed inputs')
    from .value_evidence_enrichment_v1 import consume_retained_enrichment
    points, enrichment_adoption = consume_retained_enrichment(root, points,
        list(declarations.values()), evaluation_at=receipt.generated_at)
    grouped = defaultdict(list)
    excluded = defaultdict(int)
    identities = {}
    for point in points:
        identity = point.get("data_point_id")
        if identity:
            if identity in identities:
                if identities[identity] != point:
                    raise ValueError("conflicting retained financial identity")
                continue
            identities[identity] = point
        if _point_available_at(point, receipt.generated_at) is None:
            excluded[point["symbol"]] += 1
        else:
            grouped[point["symbol"]].append(point)
    companies = {row.symbol: row for row in receipt.universe.records}
    pool = receipt.candidate_pool()
    deep, enrichment = [], []
    for entry in legacy["entries"]:
        symbol = entry["symbol"]
        company = companies[symbol]
        rows = grouped[symbol]
        quality = evaluate_financial_quality(symbol, company.name, company.official_industry,
            rows, evaluation_date=receipt.generated_at.date())
        period = selected_period(rows)
        required = list(quality.calculation_details.get("required_fields", GENERAL_FIELDS))
        selected = [p for p in rows if str(p["period_label"]) == (quality.calculation_details.get("period") or period)]
        accepted = sorted({p["field_name"] for p in selected if p["field_name"] in required and _accepted(p)})
        missing = sorted(set(required) - set(accepted))
        profiles = sorted({row.profile_status for row in pool[symbol]})
        supported = profiles == ["SUPPORTED"] and quality.model_type == "general_enterprise"
        score = quality.total_score if supported else None
        item = {key: entry[key] for key in ("symbol", "company_name", "channels", "evidence_ids", "screening_reasons")}
        item.update({
            "research_state": "DATA_CHECK", "profile_statuses": profiles,
            "model_type": quality.model_type, "supported_quality_profile": supported,
            "quality_status": quality.quality_status,
            "quality_score": str(score) if score is not None else None,
            "evidence_completeness": {"required_fields": required, "accepted_fields": accepted,
                "missing_fields": missing, "coverage_ratio": str(quality.coverage_ratio)},
            "economic_data": quality.calculation_details,
            "field_observations": [{key: p.get(key) for key in (
                "data_point_id", "field_name", "value", "unit", "period_label",
                "source_id", "source_name", "available_at", "fetched_at", "validation_status")}
                | {"accepted_by_existing_quality_policy": _accepted(p)}
                for p in selected if p["field_name"] in required],
            "quality_reasons": quality.reasons,
            "timing": {"evaluation_at": receipt.generated_at.isoformat(),
                "financial_period": quality.calculation_details.get("period") or period or None,
                "unavailable_point_count": excluded[symbol], "quote_date": receipt.quote_date,
                "quote_date_verification": "UNVERIFIED_PROVIDER_TRADE_DATE",
                "assurance": "RETAINED_AVAILABILITY_FILTER_ONLY_NOT_STRICT_PIT_ADMISSION"},
            "unknown_factors": ["BUSINESS_DURABILITY_NOT_ASSESSED", "CAPITAL_ALLOCATION_NOT_ASSESSED",
                "DIVIDEND_SUSTAINABILITY_NOT_ASSESSED", "VALUATION_NOT_ASSESSED",
                "EVENT_MATERIALITY_NOT_ASSESSED", "STRICT_PIT_NOT_ADMITTED"],
            "gaps": entry["gaps"] + ([] if supported else ["QUALITY_PROFILE_UNSUPPORTED"]),
        })
        if score is not None:
            item["scheduling_basis"] = "EXISTING_VERIFIED_ANNUAL_QUALITY_SCORE_DESCENDING"
            deep.append(item)
        else:
            item["scheduling_basis"] = "ACCEPTED_FIELD_COUNT_DESCENDING_NOT_ECONOMIC_RANK"
            enrichment.append(item)
    deep.sort(key=lambda row: (-Decimal(row["quality_score"]), row["symbol"]))
    enrichment.sort(key=lambda row: (-len(row["evidence_completeness"]["accepted_fields"]), row["symbol"]))
    for queue, limit in ((deep, budget), (enrichment, enrichment_budget)):
        for index, row in enumerate(queue):
            row["queue_status"] = "SELECTED_FOR_RESEARCH" if index < limit else "BUDGET_DEFERRED"
    result = {"schema_version": SCHEMA_VERSION, "quality_version": VERSION,
        "action": "no_order", "admission": "RESEARCH_QUEUE_ONLY",
        "as_of": legacy["as_of"], "run_id": legacy["run_id"],
        "evaluation_at": receipt.generated_at.isoformat(),
        "budget": budget, "enrichment_budget": enrichment_budget,
        "deep_research_priority": deep, "evidence_enrichment_work_queue": enrichment,
        "selected_deep_research_count": min(budget, len(deep)),
        "selected_enrichment_count": min(enrichment_budget, len(enrichment)),
        "tie_break": "SYMBOL_ASCENDING_ADMINISTRATIVE_ONLY_NO_ORDINAL_RANK",
        "new_verification_or_approval_count": 0, "annual_evidence_adoption": adoption,
        "retained_enrichment_adoption": enrichment_adoption,
        "durable_income_reuse": income_reuse,
        "retained_adoption_metadata_unverified": retained.get("annual_evidence_adoption"),
        "inputs": dict(legacy["inputs"], financial_export_path=export.relative_to(root.resolve()).as_posix(),
            financial_export_sha256=financial_export_sha256),
        "removed_symbols": legacy["removed_symbols"]}
    origin = _load_bound(export, financial_export_sha256).get('value_enrichment_base_export')
    if origin:
        result['inputs']['base_financial_export'] = origin
    result["content_sha256"] = _canonical_hash(result)
    return result

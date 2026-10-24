"""Bridge real retained income sources into existing annual/enrichment contracts."""
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path

from ..product.common import load_json_object, require_inside, sha256_file, write_new_json
from ...financial_quality import _accepted
from ...infrastructure.screening.evidence_screen_v3 import evaluate_financial_quality
from ...infrastructure.screening.financial_export_v2 import adopt_annual_export
from ...infrastructure.screening.value_evidence_enrichment_v1 import RetainedAnnualSource
from ...m2_discovery_engine import _point_available_at
from .income_source_correlation import correlate_income_inputs, reverify_income_inputs
from .value_evidence_enrichment_v1 import consume_retained_enrichment


def _bound_export(root, binding):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("Exact financial export binding required")
    relative = Path(binding["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Financial export must be project relative")
    path = require_inside(root / "runtime", root / relative, "financial export")
    if sha256_file(path) != binding["sha256"]:
        raise ValueError("Base financial export hash mismatch")
    return path


def build_retained_income_financial_export(*, root: Path, base_export_binding: dict,
        sources: list[dict], output_dir: Path, evaluation_at: datetime) -> dict:
    """Reverify real sources, preserve base observations, and consume annual facts.

    No acquisition, registration, model selection or approval is performed.
    Saved correlated points and saved PASS results are never accepted as inputs.
    """
    root = root.resolve()
    if evaluation_at.utcoffset() is None or not isinstance(sources, list) or not 1 <= len(sources) <= 2:
        raise ValueError("Aware cutoff and one or two explicit retained sources required")
    output = require_inside(root / "runtime", output_dir, "retained income output")
    if output.exists():
        raise FileExistsError("Retained income adaptation requires a fresh output directory")
    base_path = _bound_export(root, base_export_binding)
    payload = load_json_object(base_path, "base financial export")
    if not isinstance(payload.get("points"), list) or not isinstance(payload.get("annual_points", []), list):
        raise ValueError("Existing points/annual_points contract required")
    if payload.get("value_enrichment_base_export"):
        raise ValueError("Durable-progress overlay must use its existing replay consumer")
    declarations = payload.get("value_enrichment_sources", [])
    if not isinstance(declarations, list):
        raise ValueError("Existing enrichment source declarations must be a list")
    declared = {}
    for declaration in declarations:
        key = (declaration["symbol"], declaration["period"])
        if key in declared:
            raise ValueError("Duplicate existing enrichment source identity")
        declared[key] = declaration
    original = [*payload["points"], *payload.get("annual_points", [])]
    identities = {}
    for point in original:
        identity = point.get("data_point_id")
        if identity:
            if identity in identities and identities[identity] != point:
                raise ValueError("Conflicting retained financial identity")
            identities[identity] = point
    fresh, selected, seen = [], [], set()
    for descriptor in sources:
        if not isinstance(descriptor, dict) or set(descriptor) != {"official", "secondary"}:
            raise ValueError("Official and secondary source descriptors required, not saved facts")
        source = RetainedAnnualSource(**descriptor["official"])
        key = (source.symbol, source.period)
        if key in seen:
            raise ValueError("Duplicate selected official source")
        seen.add(key)
        if key in declared and declared[key] != asdict(source):
            raise ValueError("Selected source conflicts with retained declaration")
        actual = correlate_income_inputs(root, source, descriptor["secondary"], evaluation_at=evaluation_at)
        reverify_income_inputs(root, source, actual, evaluation_at=evaluation_at)
        for point in actual:
            existing = [p for p in original if p.get("symbol") == source.symbol
                and p.get("field_name") == point["field_name"] and p.get("period_label") == point["period_label"]
                and _point_available_at(p, evaluation_at) is not None]
            if any(p.get("unit") != "CNY" or Decimal(str(p["value"])) != Decimal(point["value"])
                   or (p.get("metadata") or {}).get("statement_scope") == "parent" for p in existing):
                raise ValueError("Source correlation conflicts with retained income input")
            accepted = [p for p in existing if _accepted(p)]
            if len(accepted) > 1:
                raise ValueError("Ambiguous existing accepted income input")
            if point["data_point_id"] in identities:
                if identities[point["data_point_id"]] != point:
                    raise ValueError("Correlated identity differs from retained input")
            elif not accepted:
                fresh.append(point)
                identities[point["data_point_id"]] = point
        declared[key] = asdict(source)
        selected.append((source, actual))
    # Preserve the original full-market points and all their assurance fields.
    # Only the existing correlator's actual return objects enter annual_points.
    adapted = dict(payload, annual_points=[*payload.get("annual_points", []), *fresh],
                   value_enrichment_sources=list(declared.values()))
    _bound_export(root, base_export_binding)
    path = output / "financial-export.json"
    write_new_json(path, adapted)
    digest = sha256_file(path)
    merged, adoption = adopt_annual_export(path, sha256=digest, evaluation_at=evaluation_at,
                                          base_points=payload["points"])
    symbols = {source.symbol for source, _ in selected}
    # Keep the bounded research calculation bounded, not a 50k-point deep copy.
    relevant = [point for point in merged if point.get("symbol") in symbols
                and _point_available_at(point, evaluation_at) is not None]
    enriched, reports = consume_retained_enrichment(root, relevant,
        [asdict(source) for source, _ in selected], evaluation_at=evaluation_at)
    changes = {}
    for source, actual in selected:
        before = evaluate_financial_quality(source.symbol, None, None,
            [p for p in original if p.get("symbol") == source.symbol
             and _point_available_at(p, evaluation_at) is not None], evaluation_date=evaluation_at.date())
        after = evaluate_financial_quality(source.symbol, None, None,
            [p for p in enriched if p.get("symbol") == source.symbol], evaluation_date=evaluation_at.date())
        changes[source.symbol] = dict(before=json.loads(json.dumps(asdict(before), default=str)),
            after=json.loads(json.dumps(asdict(after), default=str)),
            correlated_input_ids=[point["data_point_id"] for point in actual],
            accepted_quality_fields=after.calculation_details.get("accepted_fields", []))
        reverify_income_inputs(root, source, actual, evaluation_at=evaluation_at)
    _bound_export(root, base_export_binding)
    if sha256_file(path) != digest:
        raise ValueError("Adapted export changed during consumption")
    return dict(financial_export_binding=dict(path=path.relative_to(root).as_posix(), sha256=digest),
        base_export_binding=base_export_binding, annual_evidence_adoption=adoption,
        retained_enrichment_adoption=reports, quality_changes=changes,
        research_input_points=[p for p in enriched if _accepted(p)],
        evaluation_at=evaluation_at.isoformat(), action="no_order", formal_eligibility=False,
        current_registry_updated=False, economic_approval=False, historical_pit_admission="NOT_ADMITTED")

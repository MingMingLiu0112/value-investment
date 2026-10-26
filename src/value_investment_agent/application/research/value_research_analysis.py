"""Recompute source-bound pending research for reading, without granting admission."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import localcontext
from pathlib import Path

from ...m1_valuation_package_builder import build_descriptor
from ...research_artifact_codecs import artifact_payload
from ...valuation_models.residual_income import QualityCompounderFacts
from ...valuation_router import route_profile
from ..product.common import load_json_object, normalize_symbol, require_inside, sha256_file
from ..product.pending_candidate_supplement import load_current_pending_candidate_supplement
from ..product.pending_replay_publication import load_current_pending_replay
from ..product.research_review_packet import project_research_review_packet


SCHEMA = "value-research-analysis-v1"
SCENARIOS = ("bear", "base", "bull")


def _bound(root: Path, binding: dict) -> Path:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("Value analysis requires an exact path/hash binding")
    relative = Path(binding["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Value analysis binding must be project relative")
    path = require_inside(root, root / relative, "value analysis input")
    if sha256_file(path) != binding["sha256"]:
        raise ValueError("Value analysis source hash mismatch: " + binding["path"])
    return path


def _available(value: str, now: datetime) -> None:
    stamp = datetime.fromisoformat(value)
    if now.utcoffset() is None or stamp.utcoffset() is None or stamp > now:
        raise ValueError("Value analysis input is not available at requested cutoff")


def _sensitivity(descriptor, model) -> dict:
    """Use only registered endpoints; a one-factor stress is not a joint forecast."""
    facts = descriptor.facts
    if not isinstance(facts, QualityCompounderFacts) or not facts.scenario_inputs:
        return dict(status="NOT_SUPPORTED", rows=[], blockers=["NO_REGISTERED_SENSITIVITY_ADAPTER"])
    base = facts.scenario_inputs["base"]
    baseline = model.value(facts, descriptor.research_case).base_value
    rows = []
    for assumption in descriptor.assumptions.assumptions:
        mappings = [item for item in descriptor.assumption_bindings
                    if item.assumption_name == assumption.name]
        paths = {item.field_path for item in mappings}
        if len(paths) != 1 or {item.scenario for item in mappings} != set(SCENARIOS):
            raise ValueError("Sensitivity requires exact scenario consumption bindings")
        field_path = next(iter(paths))
        points = []
        for name in SCENARIOS:
            value = getattr(assumption, name)
            try:
                if field_path.startswith("forecast_roes."):
                    forecasts = list(base.forecast_roes)
                    forecasts[int(field_path.split(".")[1])] = value
                    changed = replace(base, forecast_roes=tuple(forecasts))
                elif field_path.startswith("forecast_retentions."):
                    forecasts = list(base.forecast_retentions)
                    forecasts[int(field_path.split(".")[1])] = value
                    changed = replace(base, forecast_retentions=tuple(forecasts))
                elif field_path in {"cost_of_equity", "terminal_roe", "terminal_growth", "retention"}:
                    changed = replace(base, **{field_path: value})
                else:
                    raise ValueError("Unsupported sensitivity field: " + field_path)
                stressed = replace(facts, scenario_inputs={key: changed for key in SCENARIOS})
                result = model.value(stressed, descriptor.research_case)
                if result.base_value is None or not result.base_value.is_finite():
                    raise ValueError("Sensitivity has no finite model result")
                with localcontext() as context:
                    context.prec = 48
                    delta = str(result.base_value - baseline)
                points.append(dict(bound=name, input_value=str(value), status="ARITHMETIC_COMPLETE",
                    per_share_value=str(result.base_value), delta_from_base=delta,
                    diagnostics=result.sensitivities[1]))
            except (ValueError, ArithmeticError, IndexError) as error:
                points.append(dict(bound=name, input_value=str(value), status="NOT_ASSESSABLE",
                    per_share_value=None, reason=str(error)))
        rows.append(dict(assumption_name=assumption.name, field_path=field_path,
            basis=assumption.basis, rationale=assumption.rationale,
            evidence_refs=assumption.evidence_refs, points=points))
    return dict(status="COMPLETE" if all(point["status"] == "ARITHMETIC_COMPLETE"
        for row in rows for point in row["points"]) else "PARTIAL", rows=rows,
        method="ONE_FACTOR_AT_REGISTERED_ENDPOINTS_OTHER_INPUTS_FIXED_AT_BASE",
        economic_consistency_reviewed=False,
        limitation="Independent stresses can break joint economic assumptions; they are not approved scenarios.")


def project_value_research_analysis(*, root: Path, package_binding: dict,
        workbench_binding: dict, now: datetime) -> dict:
    """Verify consumed inputs and replay the existing model; perform no writes."""
    root = root.resolve()
    package_path, workbench_path = _bound(root, package_binding), _bound(root, workbench_binding)
    package = load_json_object(package_path, "value research package")
    workbench = load_json_object(workbench_path, "value research workbench")
    for stamp in (package["point_in_time"]["available_at"], package["point_in_time"]["computed_at"],
                  workbench["generated_at"]):
        _available(stamp, now)
    if package.get("schema_version") != "m1-valuation-package-v2" or not package.get("source_contract"):
        raise ValueError("Value analysis requires a source-bound package")
    packet = project_research_review_packet(root=root, package_path=package_path,
        package_sha256=package_binding["sha256"], workbench_path=workbench_path,
        workbench_sha256=workbench_binding["sha256"])
    if packet["gate"]["results"].get("G3_估值门") is not False:
        raise ValueError("Pending analysis cannot replace the approved research path")
    effective = {**package, "facts": dict(package["facts"]),
        "recommendation_schema_version": workbench["decision_recommendation"]["schema_version"]}
    effective["facts"].setdefault("kind", effective["facts"].get("facts_type"))
    descriptor = build_descriptor(effective, root=root)
    if descriptor.input_sha256 != packet["input_descriptor_sha256"]:
        raise ValueError("Value analysis descriptor differs from consumed inputs")
    route = route_profile(descriptor.profile_id, descriptor.requested_model)
    model = route.build_model()
    result = model.value(descriptor.facts, descriptor.research_case)
    valuation = artifact_payload(result)[1]
    if valuation != workbench.get("valuation"):
        raise ValueError("Value analysis recomputation differs from consumed valuation")
    if (result.status != "conditional_research_only"
            or any(getattr(result, name + "_value") is None
                   or not getattr(result, name + "_value").is_finite() for name in SCENARIOS)):
        raise ValueError("Value analysis has no complete conditional arithmetic")
    case = package["research_case"]
    blockers = list(dict.fromkeys([*case.get("blockers", []), *packet["decision_blockers"]]))
    analysis = dict(schema_version=SCHEMA, symbol=descriptor.symbol, company_name=descriptor.name,
        action="no_order", status="CONDITIONAL_ANALYSIS_VERIFIED",
        joint_capital_review=None,
        arithmetic_complete=True, economic_assumptions_reviewed=False,
        economic_review_status="PENDING_EXACT_VERSION_REVIEW",
        strategy_admitted=False, action_admitted=False, price_comparison_eligible=False,
        approval_changed=False, research_as_of=packet["research_as_of"],
        research_version=descriptor.research_case.research_version,
        valuation_date=result.valuation_date.isoformat(),
        available_at=descriptor.point_in_time.available_at.isoformat(),
        computed_at=descriptor.point_in_time.computed_at.isoformat(),
        input_descriptor_sha256=descriptor.input_sha256,
        source_verification=dict(status=packet["source_contract_status"],
            assurance="SOURCE_BYTES_AND_CONSUMED_INPUTS_VERIFIED_NOT_ECONOMIC_APPROVAL",
            strict_contemporaneous_pit=package["source_contract"].get("strict_contemporaneous_pit", "NOT_PROVEN")),
        official_fact_anchors=packet["official_fact_anchors"],
        source_catalog=package["sources"],
        consumed_operating_inputs=packet["consumed_operating_inputs"],
        financial_summary=packet["financial_summary"],
        valuation=valuation,
        scenarios=[dict(scenario=name, per_share_value=str(getattr(result, name + "_value")),
                        inputs=package["facts"]["scenario_inputs"][name]) for name in SCENARIOS],
        sensitivity=_sensitivity(descriptor, model), assumptions=packet["assumptions"],
        model_applicability=dict(route=route.as_policy(), status="CONDITIONAL_NOT_ECONOMICALLY_APPROVED",
            scope=result.assumptions.get("scope"), formula=result.assumptions.get("formula"),
            financial_scope_review=packet["limited_financial_acceptance"],
            limitations=case.get("financial_summary", {}).get("pending_model_limits", []),
            blockers=blockers), model_validity=packet["model_validity"],
        thesis=case.get("thesis"), return_driver=case.get("return_driver"),
        supporting_evidence=case.get("positives", []),
        counter_evidence=packet["strongest_counterevidence"],
        thesis_breakers=case.get("thesis_breakers", []), next_events=packet["next_triggers"],
        human_review_items=packet["human_review_items"], blockers=blockers,
        source_bindings=packet["source_bindings"],
        assurance_limits=packet["assurance_limits"])
    # Recheck after arithmetic so a concurrent source change cannot publish mixed inputs.
    for binding in analysis["source_bindings"]:
        _bound(root, binding)
    return analysis


def load_current_value_research_analysis(*, root: Path, symbol: str, now: datetime) -> dict | None:
    """Use the existing candidate precedence; invalid current input never falls back."""
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    current = load_current_pending_candidate_supplement(root=root, symbol=symbol)
    if current is not None:
        bindings = current
    else:
        current = load_current_pending_replay(root=root, symbol=symbol)
        if current is None:
            return None
        bindings = current["publication"]
        _available(bindings["generated_at"], now)
    candidate = current["candidate"]
    _available(candidate["generated_at"], now)
    analysis = project_value_research_analysis(root=root, now=now,
        package_binding=bindings["package_binding"], workbench_binding=bindings["workbench_binding"])
    if (analysis["symbol"] != symbol or analysis["input_descriptor_sha256"] !=
            candidate["model_context"]["input_descriptor_sha256"]):
        raise ValueError("Value analysis differs from the exact review candidate")
    analysis["review_binding"] = dict(candidate_binding=bindings["candidate_binding"],
        package_binding=bindings["package_binding"], workbench_binding=bindings["workbench_binding"],
        review_packet_binding=bindings["review_packet_binding"], model_context=candidate["model_context"])
    analysis["human_review_groups"] = candidate.get("review_groups", [])
    from ..product.economic_review_materials import project_joint_capital_review
    joint = project_joint_capital_review(root=root, binding=bindings["candidate_binding"],
        symbol=symbol, model_context=candidate["model_context"], now=now)
    if joint is not None:
        if (joint["input_descriptor_sha256"] != analysis["input_descriptor_sha256"]
                or any(row["valuation_per_share"] != analysis["valuation"][row["scenario"] + "_value"]
                       for row in joint["scenarios"])):
            raise ValueError("Joint review differs from public consumed analysis")
        analysis["joint_capital_review"] = joint
    from ..product.source_native_candidate_v2 import SCHEMA as NATIVE_SCHEMA, project_source_native_review_materials
    if candidate['schema_version'] == NATIVE_SCHEMA:
        native = project_source_native_review_materials(root=root,
            candidate_binding=bindings['candidate_binding'], now=now)
        if (native['symbol'] != symbol or any(native['scenarios'][name]['per_share_value'] !=
                analysis['valuation'][name + '_value'] for name in ('bear', 'base', 'bull'))):
            raise ValueError('Native cash materials differ from public consumed analysis')
        analysis['source_native_cash_review'] = dict(native,
            candidate_binding=dict(bindings['candidate_binding']), model_context=candidate['model_context'],
            cash_branch='TIMING_DELAY', authenticated_consumption_supported=False)
        closure = {ref['path']: ref['sha256'] for ref in analysis['source_bindings']}
        for ref in native['source_bindings']:
            if ref['path'] in closure and closure[ref['path']] != ref['sha256']:
                raise ValueError('Native cash source conflicts with public analysis')
            if ref['path'] not in closure:
                analysis['source_bindings'].append(dict(ref))
                closure[ref['path']] = ref['sha256']
    for binding in (current["registry_binding"], current.get("publication_binding"),
                    bindings["candidate_binding"], bindings["review_packet_binding"]):
        if binding is not None:
            _bound(root, binding)
            if binding not in analysis["source_bindings"]:
                analysis["source_bindings"].append(binding)
    for binding in analysis["source_bindings"]:
        _bound(root, binding)
    return analysis

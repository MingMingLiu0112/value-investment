"""ValueActionPlan adapters over existing replay and published research contracts."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from ...domain.decision.value_action_plan import (
    RegisteredValueActionPolicy, ValuePriceRule, build_value_action_plan,
)
from ...price_bridge import price_bridge_from_payload
from ...research_artifact_codecs import decode_artifact
from ...research_artifacts import ARTIFACT_VALUATION_RESULT
from ..product.publication_chain import bound_object, load_current_chain, STRUCTURE_ERRORS
from ..product.quote_bridge import execute_quote_bridge_for_symbol
from ..product.value_decision_explanation import project_value_decision_explanation
from .restore_decision_recommendation import RestoredDecisionRecommendation
from .value_model_identity import project_catalog_identity

CHINA = ZoneInfo("Asia/Shanghai")


def load_value_action_policy(*, root: Path, binding: dict, symbol: str,
                             now: datetime) -> RegisteredValueActionPolicy | None:
    """Read an explicitly supplied, registered policy; create no registry/default.

    The binding must come from the existing verified publication's
    product_extensions.value_action_policy_registry. A code price-attractiveness
    rule, research valuation band, corporate dividend plan or legacy percentage
    experiment does not satisfy this contract.
    """
    if now.utcoffset() is None:
        raise ValueError("Policy cutoff requires a timezone")
    registered_binding = (load_current_chain(root)["model"].get("product_extensions") or {}).get("value_action_policy_registry")
    if binding != registered_binding:
        raise ValueError("Policy is not registered in the current publication")
    registered = bound_object(root, binding)
    if (registered.get("schema_version") != "registered-value-action-policies-v1"
            or registered.get("action") != "no_order"
            or registered.get("status") != "REGISTERED"
            or not isinstance(registered.get("policies"), list)):
        raise ValueError("Not a registered investment action policy")
    matches = [row for row in registered["policies"] if row.get("symbol") == symbol]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("Ambiguous registered value policy")
    row = matches[0]
    stamp = datetime.fromisoformat(row["registered_at"])
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("Investment policy not available at plan cutoff")
    return RegisteredValueActionPolicy(
        policy_id=row["policy_id"], rule_version=row["rule_version"], symbol=symbol,
        profile_id=row["profile_id"], model_id=row["model_id"], model_version=row["model_version"],
        effective_from=date.fromisoformat(row["effective_from"]),
        effective_through=date.fromisoformat(row["effective_through"]), registered_at=stamp,
        rules=tuple(ValuePriceRule(action=rule["action"], scenario=rule["scenario"],
            value_fraction=Decimal(rule["value_fraction"]), comparison=rule["comparison"],
            rationale=rule["rationale"]) for rule in row["rules"]), source_binding=dict(binding),
        currency=row["currency"], share_basis=row["share_basis"])


def project_value_action_plan(verified_decision: RestoredDecisionRecommendation, *,
                              evidence_scope: str,
                              policy: RegisteredValueActionPolicy | None = None) -> dict:
    """A full-replay adapter. Recommendations are still human review candidates."""
    explanation = project_value_decision_explanation(verified_decision, evidence_scope=evidence_scope)
    explanation["research_as_of"] = verified_decision.dependency_objects["research_case"].as_of.isoformat()
    explanation["model_id"] = verified_decision.recommendation.input_model_id
    explanation = project_catalog_identity(explanation)
    return build_value_action_plan(explanation=explanation, policy=policy,
        repository_replayed=True,
        verified_predecision=verified_decision.dependency_objects.get("pre_decision")).as_policy()


def _check_retained_evidence(root: Path, explanation: dict) -> list[dict]:
    bindings = []
    valuation = decode_artifact(ARTIFACT_VALUATION_RESULT, explanation["valuation"])
    bridge = (explanation.get("price_context") or {}).get("price_bridge")
    if bridge is not None:
        price_bridge_from_payload(valuation, bridge)
    for reference in (explanation.get("valuation") or {}).get("evidence_refs", []):
        if reference.get("path") is None:
            continue
        name, expected = reference["path"], reference.get("sha256")
        path = (root / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root.resolve()) or not expected:
            raise ValueError("Retained valuation source escapes repository or lacks hash")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Retained valuation evidence hash mismatch")
        binding = dict(path=name, sha256=expected)
        if binding not in bindings:
            bindings.append(binding)
    return bindings


def load_registered_value_action_plans(root: Path, *, now: datetime,
                                       symbols: list[str] | tuple[str, ...] | None = None) -> dict:
    """Read-only current publication projection, never a new financial approval.

    Hash-bound explanations retain their existing replay receipt, but this
    published read does not itself restore a live artifact repository. Therefore
    it cannot mint security or portfolio action qualification. Call the typed
    project_value_action_plan with a freshly restored decision for review
    qualification. Root owns packet/API and publication identity integration.
    """
    root = Path(root).resolve()
    if now.utcoffset() is None:
        raise ValueError("Value plan clock must be timezone-aware")
    if symbols is not None and (isinstance(symbols, str) or len(set(symbols)) != len(symbols)
            or any(not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isdigit() for symbol in symbols)):
        raise ValueError("Explicit unique six-digit value symbols required")
    day = now.astimezone(CHINA).date()
    try:
        chain = load_current_chain(root)
    except STRUCTURE_ERRORS as error:
        return dict(status="BLOCKED", items=[], blockers=["VALUE_PUBLICATION_CHAIN_UNAVAILABLE:" + str(error)],
                    source_bindings=[], action="no_order")
    model = chain["model"]
    registered_binding = (model.get("product_extensions") or {}).get("value_action_policy_registry")
    explanation_bindings = {}
    errors = {}
    selected = set(symbols) if symbols is not None else None
    for binding in model.get("additional_evidence_bindings", []):
        name = binding.get("path", "")
        if not name.endswith("-value-decision-explanation.json"):
            continue
        symbol = Path(name).name.partition("-")[0]
        if selected is not None and symbol not in selected:
            continue
        prior = explanation_bindings.get(symbol)
        if prior is not None and prior["sha256"] != binding.get("sha256"):
            errors[symbol] = "CONFLICTING_PUBLISHED_VALUE_EXPLANATIONS"
        explanation_bindings[symbol] = binding
    items, blockers, bindings = [], [], []
    for symbol, binding in sorted(explanation_bindings.items()):
        try:
            if symbol in errors:
                raise ValueError(errors[symbol])
            explanation = bound_object(root, binding)
            if (explanation.get("schema_version") != "public-value-decision-explanation-v1"
                    or explanation.get("symbol") != symbol or explanation.get("action") != "no_order"
                    or explanation.get("evidence_scope") != "RETAINED_RESEARCH"
                    or explanation.get("verification", {}).get("repository_replay") is not True
                    or explanation.get("verification", {}).get("semantic_revalidation") is not True):
                raise ValueError("Published value explanation contract invalid")
            sources = [binding, *_check_retained_evidence(root, explanation)]
            explanation = project_catalog_identity(explanation)
            policy = None
            if registered_binding is not None:
                sources.append(registered_binding)
                try:
                    policy = load_value_action_policy(root=root, binding=registered_binding, symbol=symbol, now=now)
                except STRUCTURE_ERRORS as error:
                    explanation = {**explanation, "blockers": [*explanation.get("blockers", []),
                        "VALUE_POLICY_REGISTRY_UNAVAILABLE:" + str(error)]}
            execution = execute_quote_bridge_for_symbol(root, symbol, today=now)
            close = execution.get("quote") or {}
            compatibility = execution.get("compatibility") or {}
            current_verified = (
                (compatibility.get("verified_quote") or {}).get("eligible") is True
                and close.get("latest_completed_session") is not None
                and close.get("quote_date") == close.get("latest_completed_session"))
            historical_blockers = list(explanation.get("blockers") or [])
            resolved_quote_blockers = [reason for reason in historical_blockers
                if current_verified and reason in {
                    "等待已验证收盘行情", "price_bridge_pending_external_data"}]
            if resolved_quote_blockers:
                explanation = {**explanation, "blockers": [reason for reason in historical_blockers
                    if reason not in resolved_quote_blockers]}
            quote = {}
            if close.get("display_price") is not None:
                quote = dict(symbol=symbol, price=close["display_price"], quote_date=close["quote_date"],
                    status="verified_close" if current_verified else "not_current_verified",
                    scope=(close.get("display_scope") or execution["status"] if current_verified
                           else "RETAINED_QUOTE_DISPLAY_ONLY_NOT_CURRENT_VERIFIED"),
                    comparison_eligible=current_verified and
                        (compatibility.get("comparison_eligible") or {}).get("eligible") is True)
                sources.append(dict(path=close["bundle_path"], sha256=close["bundle_sha256"]))
            if execution.get("pointer"):
                sources.append(execution["pointer"])
            plan = build_value_action_plan(explanation=explanation, policy=policy,
                reference_quote=quote, source_bindings=tuple(sources), decision_as_of=day).as_policy()
            plan["quote_bridge_status"] = execution["status"]
            plan["historical_research_blockers"] = historical_blockers
            plan["resolved_historical_quote_blockers"] = resolved_quote_blockers
            plan["current_quote_verified"] = current_verified and bool(quote)
            plan["current_quote_blockers"] = ([] if plan["current_quote_verified"] else
                ["VALUE_LATEST_COMPLETED_QUOTE_NOT_VERIFIED"])
            plan["current_pricing_blockers"] = [reason for reason in plan["blockers"]
                if reason.startswith("VALUE_")]
            next_step = execution.get("next_step") or execution.get("reason")
            if next_step:
                plan["required_confirmations"].append(next_step)
            plan["verification_scope"] = "HASH_BOUND_PUBLISHED_RESEARCH_NOT_NEW_APPROVAL"
            items.append(plan)
            for source in sources:
                if source not in bindings:
                    bindings.append(source)
        except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
            blockers.append(f"VALUE_PLAN_UNAVAILABLE:{symbol}:{error}")
    registry_path = root / "config/current-company-research-registry.json"
    if registry_path.is_file():
        try:
            raw = registry_path.read_bytes()
            registry = json.loads(raw)
            if registry.get("schema_version") != "current-company-research-registry-v1" or registry.get("action") != "no_order":
                raise ValueError("Invalid company research registry")
            registry_binding = dict(path=registry_path.relative_to(root).as_posix(), sha256=hashlib.sha256(raw).hexdigest())
            bindings.append(registry_binding)
            for symbol, entry in sorted(registry["companies"].items()):
                if symbol in explanation_bindings or (selected is not None and symbol not in selected):
                    continue
                explanation = dict(symbol=symbol, company_name=entry["name"], decision_as_of=day.isoformat(),
                    action="no_order", blockers=list(entry.get("missing_inputs", [])), candidate_action="NO_ACTION")
                sources = [registry_binding]
                for evidence in entry.get("evidence", []):
                    path = (root / evidence["path"]).resolve()
                    if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]:
                        raise ValueError("Registered company evidence changed")
                    sources.append(dict(path=evidence["path"], sha256=evidence["sha256"]))
                plan = build_value_action_plan(explanation=explanation, source_bindings=tuple(sources)).as_policy()
                plan["research_as_of"] = None
                plan["verification_scope"] = "REGISTERED_RESEARCH_GAPS_ONLY"
                items.append(plan)
                bindings.extend(source for source in sources if source not in bindings)
        except (ValueError, OSError, KeyError, TypeError) as error:
            blockers.append("VALUE_RESEARCH_REGISTRY_UNAVAILABLE:" + str(error))
    return dict(status="VALUE_RESEARCH_OBSERVATION" if items else "BLOCKED", items=items,
                blockers=blockers, source_bindings=bindings,
                policy_inventory=dict(registered_investment_policy_binding=registered_binding,
                    implicit_safety_margin_policy=None,
                    quality_compounder_price_rule="RESEARCH_ATTRACTIVENESS_ONLY_NOT_ACTION_POLICY",
                    fcff_price_rule="NOT_REGISTERED", cyclical_price_rule="NOT_REGISTERED"),
                action="no_order")

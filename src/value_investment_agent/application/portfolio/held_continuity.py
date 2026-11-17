"""Private, read-only held-security review independent of candidate retention.

Call only behind the existing private authorization boundary. Never attach this
result to a public packet. Price providers must return existing engine plans,
not user-supplied price flags. No provider failure may remove a held security.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
from uuid import uuid4

from .private_portfolio_service import PrivatePortfolioService, JournalConflict, JournalValidationError
from .private_risk_projection import review_private_risk_rehearsal
from ..hotspot.price_action_case import project_current_price_action_plan
from ...infrastructure.hotspot.current_price_case import load_current_price_case, collect_current_price_case
from ...quote_session_collection import collect_session_bundle
from ...quote_sessions import parse_quote, evaluate_quote_session
from ..hotspot.current_registry import load_price_conditions
from ..decision.current_value_plan import load_current_value_action_plans


def evaluate_owned_held_advisory(root, *, context, plan, now, allow_test_only=False):
    """Review each original; a multi-entry readout never grants aggregate action."""
    if context.get("symbol") != plan.get("symbol") or context.get("sleeve") != _plan_sleeve(plan):
        raise ValueError("Owned per-entry plan scope mismatch")
    contexts = context.get("entry_contexts")
    if contexts is None:
        return _evaluate_owned_single_entry(root, context=context, plan=plan, now=now,
            allow_test_only=allow_test_only)
    if (not isinstance(contexts, list) or len(contexts) < 2 or not context.get("ownership_verified")
            or any(not part.get("ownership_verified") or not part.get("advisory_dependencies_valid")
                or part.get("blockers") or any(part.get(key) != context.get(key) for key in
                    ("account_scope", "journal_revision", "symbol", "sleeve", "namespace")) for part in contexts)
            or sum((Decimal(part["held_quantity"]) for part in contexts), Decimal(0)) != Decimal(context["held_quantity"])):
        raise ValueError("Incomplete owned per-entry review context")
    originals = [part["entry_artifact"].artifact_id for part in contexts]
    if len(set(originals)) != len(originals):
        raise ValueError("Duplicate owned entry review")
    expected = [b["record_sha256"] for b in context["bindings"]]
    observed = [b["record_sha256"] for part in contexts for b in part["bindings"]]
    if len(observed) != len(set(observed)) or sorted(expected) != sorted(observed):
        raise ValueError("Owned entry review does not cover every surviving binding")
    from .personal_entry_thesis import owned_entry_display
    rows = []
    for part in contexts:
        row = owned_entry_display(part)["entry_thesis_bindings"][0]
        try:
            action, blockers, evidence = _evaluate_owned_single_entry(root, context=part, plan=plan,
                now=now, allow_test_only=allow_test_only)
        except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
            action, blockers, evidence = "NO_ACTION", ["OWNED_ENTRY_REVIEW_INVALID:" + str(error)[:200]], {}
        rows.append({**row, "research_action": action, "blockers": list(blockers),
            "current_consistency_status": evidence.get("current_consistency_status"),
            "evidence": evidence, "action": "no_order", "review_quantity": None,
            "formal_eligibility": False, "broker_execution_permission": False})
    assessed = [row for row in rows if not row["blockers"]]
    actions = {row["research_action"] for row in assessed}
    status = ("INCOMPLETE" if len(assessed) != len(rows) else
              "CONFLICTING_ENTRY_ACTIONS" if len(actions) != 1 else "CONSISTENT_ENTRY_ACTIONS")
    return "NO_ACTION", ["MULTIPLE_OWNED_ENTRY_THESES_REQUIRE_SEPARATE_REVIEW"], {
        "schema_version": "owned-per-entry-research-review-v1", "action": "no_order",
        "scope": "PER_ENTRY_RESEARCH_REVIEW_ONLY", "entry_review_status": status,
        "entry_reviews": rows, "current_consistency_status": None,
        "aggregate_authority": "NONE", "formal_eligibility": False,
        "broker_execution_permission": False}


def _evaluate_owned_single_entry(root, *, context, plan, now, allow_test_only=False):
    """Use existing typed advisory rules and publication replay, never UI flags."""
    from ..decision.build_advisory_decision_recommendation_v3 import (
        build_advisory_decision_recommendation_v3, derive_recommendation_rule_inputs,
    )
    from ...domain.decision.recommendation_rules import evaluate_recommendation_action
    from ...domain.decision.advisory_dependency_admission import validate_advisory_dependencies
    from ...domain.decision.decision_recommendation import DECISION_RECOMMENDATION_V3_SCHEMA
    day = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
    from .personal_entry_thesis import resolve_current_entry_consistency
    current = resolve_current_entry_consistency(root, entry_artifact=context["entry_artifact"], as_of=now)
    entry, review = current["entry_thesis"], current["investment_consistency_review"]
    if entry != context["entry_thesis"]:
        raise ValueError("Owned original entry changed")
    if review.as_of < context["investment_consistency_review"].as_of:
        raise ValueError("Current consistency review predates confirmed review")
    validate_advisory_dependencies(symbol=plan["symbol"], decision_as_of=day,
        recommendation_schema_version=DECISION_RECOMMENDATION_V3_SCHEMA,
        entry_thesis=entry, investment_consistency_review=review)
    # Current event/model coverage below determines validity; an unchanged
    # thesis review must not be rejected solely because a calendar day rolled.
    if _plan_sleeve(plan) == "HOTSPOT_SATELLITE":
        from ..hotspot.independent_admission import load_independent_admission
        if type(allow_test_only) is not bool or (allow_test_only and context.get("namespace") != "TEST_ONLY"):
            raise ValueError("Isolated hotspot admission requires a TEST_ONLY owned context")
        # A held review is independent of a new-entry trigger or today's ranking.
        # Re-read the case and signed release instead of trusting plan flags.
        verified_plan = load_held_price_plan(root, plan["symbol"], plan, now=now)
        for key in ("market_trade_date", "signal_state", "model_or_rule_version",
                    "add_condition", "price_behavior",
                    "opportunity_quality", "current_reference_price", "invalidation_price"):
            if plan.get(key) != verified_plan.get(key):
                raise ValueError("Held hotspot plan differs from its verified case")
        from ..hotspot.independent_price_conditions import INDEPENDENT_OPEN_RULE
        original_rules = verified_plan.get("conditional_action_rules")
        projected_rules = deepcopy(original_rules)
        if isinstance(projected_rules, dict) and isinstance(projected_rules.get("OPEN"), dict):
            projected_rules["OPEN"]["rule"] = INDEPENDENT_OPEN_RULE
        if plan.get("conditional_action_rules") not in (original_rules, projected_rules):
            raise ValueError("Held hotspot action rules differ from their verified case")
        from .owned_hotspot_lifecycle import resolve_owned_hotspot_lifecycle
        lifecycle = resolve_owned_hotspot_lifecycle(root=root, context=context,
            confirmed_fill_records=context.get("confirmed_fill_records", []),
            current_plan=verified_plan, now=now)
        admission = load_independent_admission(root, symbol=plan["symbol"], now=now,
            allow_test_only=allow_test_only)
        case_binding = {"path": plan["case_path"], "sha256": plan["case_sha256"]}
        if (not admission.get("risk_review_eligible") or admission.get("blockers")
                or admission.get("rule_version") != verified_plan.get("model_or_rule_version")
                or case_binding not in admission.get("gate_source_bindings", {}).get("price_structure", [])):
            raise ValueError("HELD_HOTSPOT_INDEPENDENT_ADMISSION_REQUIRED")
        sources = admission.get("gate_source_bindings") or {}
        verified = (admission.get("review_status") == "VERIFIED"
                    and admission.get("risk_review_eligible") is True
                    and not admission.get("blockers"))
        validation_current = verified and bool(sources.get("strategy_validation"))
        event_current = verified and bool(sources.get("event_risk"))
        rules = derive_recommendation_rule_inputs(entry_thesis=entry, consistency_review=review,
            base_positive=admission["risk_review_eligible"] and validation_current and event_current,
            model_validity_status="VALID" if validation_current else "UNKNOWN",
            event_review_current=event_current)
        result = evaluate_recommendation_action(rules)
        # A separately verified broken thesis can still warrant an exit review;
        # it is not a price-structure exit or proof of entry-time continuity.
        broken_thesis_exit = (result.action == "SELL_CANDIDATE" and review.status == "BROKEN"
            and "thesis_broken" in result.reason_codes)
        if (lifecycle.get("pretrade_proven") is not True or lifecycle.get("blockers")) and not broken_thesis_exit:
            return None, ["OWNED_HOTSPOT_EXECUTION_CONTINUITY_UNPROVEN"], {
                "current_consistency_status": review.status,
                "current_consistency_review": current["consistency_ref"],
                "independent_admission": admission,
                "owned_hotspot_lifecycle": lifecycle,
                "reason_codes": ["OWNED_HOTSPOT_EXECUTION_CONTINUITY_UNPROVEN"]}
        return result.action, list(result.blockers), {"rule_version": result.rule_version,
            "owned_hotspot_lifecycle": lifecycle,
            "review_basis": "VERIFIED_THESIS_BREAKER" if broken_thesis_exit else "OWNED_PRICE_CONTINUITY",
            "current_consistency_status": review.status,
            "reason_codes": list(result.reason_codes), "independent_admission": admission,
            "current_consistency_review": current["consistency_ref"]}
    from .personal_entry_thesis import registered_entry_workbenches
    from ..product.decision_surface import verify_current_decision_workbench
    from ..product.research_reviews import verify_human_approval_transport_provenance
    from ..decision.restore_decision_recommendation import _restore_optional_payload_inputs
    candidates = registered_entry_workbenches(root)
    matching = [item for item in candidates if item.get("symbol") == plan["symbol"]]
    if len(matching) != 1:
        raise ValueError("CURRENT_OWNED_SECURITY_WORKBENCH_UNAVAILABLE_OR_AMBIGUOUS")
    workbench = matching[0]
    if datetime.fromisoformat(workbench["generated_at"]) > now:
        raise ValueError("Future advisory workbench")
    restored = verify_current_decision_workbench(workbench,
        human_approval_provenance_verifier=lambda approval:
            verify_human_approval_transport_provenance(root, approval))
    if restored.recommendation.symbol != plan["symbol"]:
        raise ValueError("Published advisory security mismatch")
    objects = restored.dependency_objects
    event = objects.get("event_materiality")
    if event is None or not event.covers(day) or event.review_blockers:
        raise ValueError("CURRENT_EVENT_MATERIALITY_REVIEW_REQUIRED")
    artifacts = {**restored.dependencies, "entry_thesis": context["entry_artifact"],
                 "investment_consistency_review": current["consistency_artifact"]}
    payload_inputs = _restore_optional_payload_inputs(restored.recommendation, restored.dependencies, objects)
    recommendation = build_advisory_decision_recommendation_v3(
        run_id=restored.recommendation.run_id, research_case=objects["research_case"],
        valuation=objects["valuation"], model_validity=objects.get("model_validity"),
        price_bridge=objects.get("price_bridge"), price_attractiveness=objects.get("price_attractiveness"),
        pre_decision=objects.get("pre_decision"), human_approval=objects.get("human_approval"),
        entry_thesis=entry, investment_consistency_review=review, event_materiality=event,
        dependency_artifacts=artifacts, decision_as_of=day,
        model_id=restored.recommendation.input_model_id,
        **payload_inputs,
        additional_blockers=restored.recommendation.input_additional_blockers)
    evidence = recommendation.as_policy()
    evidence["current_consistency_status"] = review.status
    return recommendation.recommendation_action, list(recommendation.blockers), evidence


SELL_REVIEW_SCHEMA = "private-held-sell-review-request-v1"


def _concentration_alert(code):
    """Known measured exposure alerts, never missing-input or execution gaps."""
    if not isinstance(code, str):
        return False
    if code in {"aggregate:single_security_concentration", "aggregate:industry_concentration",
                "aggregate:cyclical_exposure"}:
        return True
    parts = code.split(":")
    return (len(parts) >= 3 and bool(":".join(parts[2:]).strip())
        and ((parts[0] in {"CORE_VALUE", "HOTSPOT_SATELLITE"} and parts[1] in {
            "single_security_concentration", "industry_concentration", "factor_concentration"})
            or (parts[0] == "shared" and parts[1] in {"single_security_cap", "industry_cap"})))


def _held_risk_blockers(risk, engine):
    blockers = []
    for source in (risk, engine):
        codes = source.get("blockers")
        if codes is None:
            continue
        if not isinstance(codes, (list, tuple)):
            blockers.append("PRIVATE_RISK_BLOCKERS_INVALID")
            continue
        for code in codes:
            blockers.append(code if isinstance(code, str) and code.strip() else "PRIVATE_RISK_BLOCKERS_INVALID")
    return list(dict.fromkeys(blockers))


def _sell_review_request(payload):
    import re
    required = {"schema_version", "action", "expected_revision", "account_scope", "symbol", "exchange",
                "sleeve", "requested_action", "requested_quantity", "entry_thesis_record_sha256",
                "read_and_confirmed"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise JournalValidationError("Exact private sell-review request fields required")
    if (payload["schema_version"] != SELL_REVIEW_SCHEMA or payload["action"] != "no_order"
            or payload["read_and_confirmed"] is not True
            or payload["requested_action"] not in {"REDUCE", "EXIT"}
            or payload["sleeve"] not in {"CORE_VALUE", "HOTSPOT_SATELLITE"}
            or payload["exchange"] not in {"SSE", "SZSE", "BSE"}
            or not isinstance(payload["symbol"], str) or not re.fullmatch(r"[0-9]{6}", payload["symbol"])
            or not isinstance(payload["account_scope"], str) or not payload["account_scope"].strip()
            or type(payload["expected_revision"]) is not int or payload["expected_revision"] < 1
            or type(payload["requested_quantity"]) is not int or payload["requested_quantity"] <= 0
            or not isinstance(payload["entry_thesis_record_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", payload["entry_thesis_record_sha256"])):
        raise JournalValidationError("Invalid explicit private sell-review request")
    return deepcopy(payload)


def owned_held_action(*, context, plan, risk, sleeve_position, advisory_provider, sell_review_request=None):
    """Join owned thesis, evaluated strategy and actual risk with strict quantities."""
    import re
    blockers = list(context.get("blockers", []))
    output = dict(action="no_order", decision_action="UNASSESSABLE", review_quantity=None,
        namespace=context.get("namespace", "ACTUAL"),
        ownership_verified=context.get("ownership_verified") is True,
        held_quantity=sleeve_position["quantity"],
        sellable_quantity=sleeve_position.get("sellable_quantity"),
        decision_layer="PERSONAL_ACTION_REVIEW",
        decision_reason="原投资逻辑、当前策略依据或个人风险条件不足，无法评价持仓动作。",
        entry_thesis_record_sha256=context.get("entry_thesis_record_sha256"),
        formal_eligibility=False, personal_sell_permission=False, position_guidance=None,
        trade_eligible=False, broker_execution_permission=False, advisory=None)
    entry = context.get('entry_thesis')
    review = context.get('investment_consistency_review')
    if context.get("sleeve") != sleeve_position["sleeve"]:
        blockers.append("OWNED_ENTRY_STRATEGY_MISMATCH")
    output.update(original_thesis=entry.thesis if entry is not None else None,
                  consistency_status=review.status if review is not None else None)
    multi_entry = context.get("entry_contexts") is not None
    if multi_entry:
        from .personal_entry_thesis import owned_entry_display
        output.update(owned_entry_display(context))
        if (context.get("ownership_verified") and plan is not None
                and context.get("blockers") == ["MULTIPLE_OWNED_ENTRY_THESES_REQUIRE_SEPARATE_REVIEW"]):
            try:
                _, _, evidence = advisory_provider()
                if (evidence.get("scope") != "PER_ENTRY_RESEARCH_REVIEW_ONLY"
                        or evidence.get("aggregate_authority") != "NONE"):
                    raise ValueError("Per-entry review cannot grant aggregate authority")
                output.update(advisory=evidence, entry_reviews=evidence["entry_reviews"],
                              entry_review_status=evidence["entry_review_status"])
                labels = {"HOLD": "支持持有研究复核", "ADD_CANDIDATE": "支持加仓研究复核",
                          "TRIM_CANDIDATE": "需减仓研究复核", "SELL_CANDIDATE": "需退出研究复核"}
                reasons = [f"{row['entry_date']} 批次：" + ("证据不足" if row["blockers"] else
                    labels.get(row["research_action"], "尚不支持行动")) for row in evidence["entry_reviews"]]
                output["decision_reason"] = "；".join(reasons) + "。各批次独立保留；尚未形成整仓动作或数量授权，卖出需逐批确认。"
            except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
                blockers.append("HELD_PER_ENTRY_REVIEW_INVALID:" + str(error)[:200])
    if (not output["ownership_verified"] or not context.get("advisory_dependencies_valid")
            or not re.fullmatch(r"[0-9a-f]{64}", output["entry_thesis_record_sha256"] or "")
            or Decimal(sleeve_position["quantity"]) <= 0
            or Decimal(context.get("held_quantity", "0")) != Decimal(sleeve_position["quantity"])):
        blockers.append("OWNED_ENTRY_DEPENDENCIES_REQUIRED")
    engine = risk.get("engine") or {}
    risk_blockers = _held_risk_blockers(risk, engine)
    # A confirmed sell intent can reduce an already measured concentration.
    # Keep those alerts visible; the current advisory and quantity checks below
    # must still independently support the same REDUCE/EXIT, never HOLD/ADD.
    reduction_review = (isinstance(sell_review_request, dict)
        and sell_review_request.get("requested_action") in ("REDUCE", "EXIT")
        and engine.get("namespace") == "ACTUAL" and engine.get("status") == "REVIEW_REQUIRED"
        and risk.get("status", "REVIEW_REQUIRED") == "REVIEW_REQUIRED")
    warnings = [code for code in risk_blockers if reduction_review and _concentration_alert(code)]
    blockers.extend(code for code in risk_blockers if code not in warnings)
    output.update(personal_risk_status=engine.get("status"), risk_warnings=warnings,
                  risk_reduction_only=bool(warnings), risk_resolution_verified=False)
    if (engine.get("namespace") != "ACTUAL" or (engine.get("status") != "RISK_REVIEW_CALCULATED"
            and not (reduction_review and warnings))):
        blockers.append("ACTUAL_RISK_REVIEW_REQUIRED")
    if (risk.get("policy") or {}).get("confirmation_status") != "HUMAN_CONFIRMED":
        blockers.append("CONFIRMED_IPS_REQUIRED")
    facts = risk.get("facts") or {}
    if (context.get("journal_revision") is not None
            and (facts.get("revision") != context["journal_revision"]
                 or facts.get("account_scope") != context["account_scope"])):
        blockers.append("OWNED_ENTRY_RISK_REVISION_MISMATCH")
    if facts.get("reconciliation_status") != "RECONCILED" or facts.get("reconciliation", {}).get("scope") != "EXTERNAL_ACCOUNT_STATEMENT":
        blockers.append("EXTERNAL_ACCOUNT_RECONCILIATION_MISSING")
    if plan is None:
        blockers.append("CURRENT_STRATEGY_PLAN_UNAVAILABLE")
    else:
        plan_blockers = list(plan.get("blockers") or [])
        output["strategy_plan_blockers"] = plan_blockers
        # The value projection reports missing rules for every action, including
        # actions not requested. Typed v3 dependencies decide thesis actions;
        # ADD still requires its explicit observed condition below.
        display_requirements = {
            "VALUE_ADD_PRICE_POLICY_MISSING_OR_INAPPLICABLE",
            "VALUE_REDUCE_PRICE_POLICY_MISSING_OR_INAPPLICABLE",
            "VALUE_EXIT_PRICE_POLICY_MISSING_OR_INAPPLICABLE",
            "VALUE_DECISION_REQUIRES_HUMAN_CONFIRMATION",
        } if _plan_sleeve(plan) == "CORE_VALUE" else set()
        blockers.extend(code for code in plan_blockers if code not in display_requirements)
        output["requires_human_review"] = True
        if (context.get("symbol") is not None and plan.get("symbol") != context["symbol"]
                or _plan_sleeve(plan) != sleeve_position["sleeve"]
                or plan.get("signal_state") in {
                    "BLOCKED", "STALE", "EXPIRED", "HISTORICAL_OBSERVATION_NOT_ADMITTED"}):
            blockers.append("CURRENT_STRATEGY_PLAN_UNAVAILABLE")
        output.update(data_trade_date=plan.get('market_trade_date'),
            plan_expiry=plan.get('expires_after_session') or plan.get('valid_until'),
            entry_condition=deepcopy(plan.get('entry_condition')),
            add_condition=deepcopy(plan.get('add_condition')),
            reduce_condition=deepcopy(plan.get('reduce_condition')),
            exit_condition=deepcopy(plan.get('exit_condition')),
            invalidation_condition=deepcopy(plan.get('invalidation_condition')))
    action, quantity = None, None
    if not blockers:
        try:
            selected, rejected, evidence = advisory_provider()
            output["advisory"] = evidence
            if evidence.get("owned_hotspot_lifecycle") is not None:
                output["owned_hotspot_lifecycle"] = evidence["owned_hotspot_lifecycle"]
            output["entry_consistency_status"] = output["consistency_status"]
            output["consistency_status"] = evidence.get("current_consistency_status")
            blockers.extend(rejected)
            action = {"ADD_CANDIDATE": "ADD", "HOLD": "HOLD", "TRIM_CANDIDATE": "REDUCE",
                      "SELL_CANDIDATE": "EXIT"}.get(selected)
            if warnings and action not in {"REDUCE", "EXIT"}:
                blockers.extend(warnings)
            if action is None:
                blockers.append("HELD_ADVISORY_ACTION_NOT_SUPPORTED")
            elif action == "ADD":
                sizing = engine.get("core_quantity_review" if sleeve_position["sleeve"] == "CORE_VALUE"
                                    else "hotspot_quantity_review") or {}
                quantity = sizing.get("review_quantity")
                blockers.extend(sizing.get("blockers") or [])
                condition = plan.get("add_condition") or {}
                if plan.get("action_intent") != "ADD" or not (condition.get("observed") is True or condition.get("triggered") is True):
                    blockers.append("CURRENT_ADD_CONDITION_NOT_CONFIRMED")
            elif action in {"REDUCE", "EXIT"}:
                if sell_review_request is None:
                    blockers.append("EXPLICIT_PRIVATE_SELL_REVIEW_REQUIRED")
                else:
                    request = _sell_review_request(sell_review_request)
                    output["private_sell_request"] = request
                    if (request["expected_revision"] != facts.get("revision")
                            or request["account_scope"] != facts.get("account_scope")
                            or request["symbol"] != plan.get("symbol")
                            or request["sleeve"] != sleeve_position["sleeve"]
                            or request["entry_thesis_record_sha256"] != output["entry_thesis_record_sha256"]):
                        blockers.append("PRIVATE_SELL_REQUEST_IDENTITY_MISMATCH")
                    if request["requested_action"] != action:
                        blockers.append("PRIVATE_SELL_ACTION_DIFFERS_FROM_CURRENT_ADVISORY")
                    positions = [p for p in facts.get("positions", []) if p.get("symbol") == request["symbol"]
                                 and p.get("exchange") == request["exchange"]]
                    allocations = [p for p in (engine.get("sleeves") or {}).get(request["sleeve"], {}).get("holdings", [])
                                   if p.get("symbol") == request["symbol"]]
                    if len(positions) != 1 or len(allocations) != 1:
                        blockers.append("ACTUAL_SLEEVE_SELL_ALLOCATION_REQUIRED")
                    else:
                        allocation = allocations[0]
                        held = Decimal(sleeve_position["quantity"])
                        sellable = Decimal(sleeve_position["sellable_quantity"])
                        if (Decimal(allocation["quantity"]) != held
                                or Decimal(allocation["sellable_quantity"]) != sellable):
                            blockers.append("ACTUAL_SLEEVE_SELL_ALLOCATION_MISMATCH")
                        quantity = request["requested_quantity"]
                        if quantity > sellable or quantity > held:
                            blockers.append("SELL_QUANTITY_MUST_BE_INTEGER_WITHIN_SELLABLE")
                        if action == "EXIT" and quantity != held:
                            blockers.append("EXIT_REQUIRES_FULL_SLEEVE_QUANTITY")
                        if action == "REDUCE" and quantity >= held:
                            blockers.append("REDUCE_REQUIRES_PARTIAL_SLEEVE_QUANTITY")
            if action != "HOLD" and (type(quantity) is not int or quantity <= 0):
                blockers.append("POSITIVE_INTEGER_REVIEW_QUANTITY_REQUIRED")
        except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
            blockers.append("HELD_ADVISORY_DEPENDENCY_INVALID:" + str(error)[:200])
    blockers = list(dict.fromkeys(blockers))
    output.update(blockers=blockers, status="UNASSESSABLE" if blockers else "CONDITIONAL_MANUAL_REVIEW")
    if not blockers:
        output.update(decision_action=action, review_quantity=quantity,
            formal_eligibility=True, personal_sell_permission=action in {"REDUCE", "EXIT"},
            decision_reason={
                "HOLD": "已绑定原投资逻辑；当前研究一致性、策略和风险支持继续持有复核。",
                "ADD": "原投资逻辑未破坏，新增仓条件与当前个人风险允许加仓复核。",
                "REDUCE": "原投资逻辑一致性或当前策略与风险提示减仓复核；以可卖数量为限。",
                "EXIT": "原投资逻辑或当前策略退出条件已形成退出复核依据；以可卖数量为限。",
            }[action])
        if warnings:
            output["decision_reason"] += " 当前集中度警告仍然有效；本次仅复核减少既有持仓，不代表减仓后风险已解除。"
    return output


def _plan_sleeve(plan: dict) -> str | None:
    sleeve = {
        "value-action-plan-v1": "CORE_VALUE",
        "price-action-plan-current-v1": "HOTSPOT_SATELLITE",
        "price-action-plan-independent-v2": "HOTSPOT_SATELLITE",
    }.get(plan.get("schema_version"))
    if (sleeve is None or plan.get("strategy", sleeve) != sleeve
            or plan.get("sleeve", sleeve) != sleeve):
        return None
    return sleeve


def _case_history(root: Path, symbol: str):
    """Existing immutable case history, not a second membership/quote registry."""
    history = root / "runtime/hotspot-current-price-cases"
    paths = list(history.glob(f"{symbol}-*/case.json"))
    return sorted(paths, key=lambda path: path.stat().st_mtime_ns, reverse=True)[:5]


def refresh_held_continuity(journal, *, repository_root: Path, payload: dict,
                             generated_at: datetime) -> dict:
    """Explicit private POST only; collect public evidence without publishing membership.

    No ledger append, candidate registry, current pointer or publication writes.
    Existing collectors keep their original source/session/size/retry gates.
    """
    if generated_at.utcoffset() is None:
        raise JournalValidationError("Timezone-aware refresh clock required")
    if set(payload) - {"expected_revision", "symbols"}:
        raise JournalValidationError("Unsupported held refresh fields")
    service = PrivatePortfolioService(journal)
    records = service.records()
    revision = len(records)
    if type(payload.get("expected_revision")) is not int or payload["expected_revision"] != revision:
        raise JournalConflict("REVISION_CONFLICT", "Refresh requires the current portfolio revision")
    replayed = service._replay(records)
    symbols = sorted({lot.symbol for lot in replayed.state.lots if lot.quantity > 0}) if replayed else []
    requested = payload.get("symbols", symbols[:5])
    if (not isinstance(requested, list) or len(requested) > 5
            or any(not isinstance(symbol, str) or symbol not in symbols for symbol in requested)
            or len(set(requested)) != len(requested)):
        raise JournalValidationError("Refresh accepts at most five unique actual held symbols")
    items, failures = [], []
    for symbol in requested:
        if not symbol.startswith(("0", "3", "6")):
            failures.append({"symbol": symbol, "reason": "EXISTING_CURRENT_CASE_COLLECTOR_UNSUPPORTED_SECURITY",
                "gap_category": "ENGINEERING", "gap_code": "HELD_SECURITY_COLLECTOR_UNSUPPORTED"})
            continue
        try:
            existing = None
            for path in _case_history(repository_root, symbol):
                try:
                    existing = load_held_price_plan(repository_root, symbol,
                        {"case_path": str(path), "case_sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
                        now=generated_at)
                    break
                except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
                    continue
            if existing is not None:
                items.append({"symbol": symbol, "case_path": existing["case_path"],
                    "case_sha256": existing["case_sha256"], "market_trade_date": existing["market_trade_date"],
                    "evidence_status": "REUSED_VERIFIED_LATEST_COMPLETED_CASE",
                    "observation_scope": existing.get("observation_scope", "SAME_SESSION_B1"),
                    "formal_eligibility": False})
                continue
            bundle = collect_session_bundle([symbol])
            # Generic existing public evidence storage; no held-membership report.
            archive = repository_root / "runtime/hotspot-current-refresh" / uuid4().hex
            archive.mkdir(parents=True)
            bundle_path = archive / "bundle.json"
            with bundle_path.open("x", encoding="utf-8") as stream:
                json.dump(bundle, stream, ensure_ascii=False, indent=2)
            digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
            now = datetime.now(timezone.utc)
            ref = bundle["references"][symbol]
            quote = parse_quote(bundle["documents"][ref["document_refs"]["tencent"]], "tencent", symbol, now)
            checked = evaluate_quote_session(symbol, quote["price"], ref, now, documents=bundle["documents"])
            if not checked["passed"]:
                raise ValueError("B1 rejected: " + checked["status"])
            case = collect_current_price_case(root=repository_root, symbol=symbol,
                as_of=date.fromisoformat(checked["expected_session"]),
                quote_bundle_path=bundle_path, quote_bundle_sha256=digest,
                observation_scope="LAST_COMPLETED_CLOSE_DISPLAY_ONLY")
            # Reverify the collector result; never promote its return flag alone.
            plan = load_held_price_plan(repository_root, symbol, case, now=datetime.now(timezone.utc))
            items.append({"symbol": symbol, "case_path": plan["case_path"],
                          "case_sha256": plan["case_sha256"], "market_trade_date": plan["market_trade_date"],
                          "evidence_status": "COLLECTED_AND_REVERIFIED_LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
                          "observation_scope": "LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
                          "current_pit": False, "price_admitted": False, "formal_eligibility": False})
        except Exception as error:
            # One source failure must not suppress the other held securities.
            timing_gap = "same-session post-close acquisition" in str(error)
            failures.append({"symbol": symbol, "reason": type(error).__name__ + ":" + str(error),
                "gap_category": "ENGINEERING" if timing_gap else "DATA",
                "gap_code": "HELD_NEXT_MORNING_CASE_COLLECTION_UNSUPPORTED" if timing_gap else
                            "HELD_CURRENT_EVIDENCE_UNAVAILABLE"})
    if len(service.records()) != revision:
        raise JournalConflict("REVISION_CONFLICT", "Portfolio changed during refresh; reread holdings")
    pending = [symbol for symbol in symbols if symbol not in requested]
    return {"schema_version": "private-held-continuity-refresh-v1", "action": "no_order",
        "sensitivity": "PRIVATE", "revision": revision, "items": items, "failures": failures,
        "unprocessed_symbols": pending, "status": "PARTIAL" if pending or failures else
        "REFRESHED" if items else "NO_HELD_SECURITIES", "ledger_written": False,
        "public_registry_written": False, "formal_eligibility": False}


def build_held_plan_provider(root: Path, replayed, *, now: datetime):
    """Resolve current evidence, then reverify confirmed recording-time bindings.

    Snapshot observations are never themselves treated as a current plan. Only
    their case path/hash can be reused by the existing current-case verifier.
    """
    try:
        current = load_price_conditions(root, now=now, research_version=None)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
        current = {"items": []}
    plans = {row["symbol"]: row["price_action_plan"] for row in current["items"]}
    selected = {symbol for symbol, plan in plans.items()
                if plan.get("candidate_lifecycle") != "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"}
    # Actual ledger lots, not candidate membership or historical trades, decide
    # which strategy can still supply a held-security review after a full sale.
    state = getattr(replayed, "state", None)
    held_sleeves = None if state is None else {}
    if state is not None:
        for lot in state.lots:
            if lot.quantity > 0:
                held_sleeves.setdefault(lot.symbol, set()).add(lot.sleeve)
    retained = {}
    for trade in reversed(replayed.trades if replayed else []):
        snapshot = trade.get("judgment_snapshot")
        try:
            if not isinstance(snapshot, dict):
                continue
            unsigned = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
            digest = hashlib.sha256(json.dumps(unsigned, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            recorded = datetime.fromisoformat(snapshot["recorded_at"])
            plan = snapshot["plan"]
            symbol = trade["symbol"]
            if (snapshot.get("schema_version") != "private-recording-time-judgment-snapshot-v1"
                    or snapshot.get("action") != "no_order" or digest != snapshot.get("snapshot_sha256")
                    or recorded.utcoffset() is None or recorded > now
                    or snapshot.get("decision_id") != "hotspot-" + symbol
                    or plan.get("symbol") != symbol or plan.get("action") != "no_order"):
                continue
            if plan.get("case_path") and plan.get("case_sha256"):
                retained.setdefault(symbol, []).append(plan)
        except (ValueError, KeyError, TypeError):
            continue

    def strategy_plan(symbol, sleeve=None):
        # Standalone source inspection may have no ledger; the final projection
        # below always enforces actual position sleeves before emitting reasons.
        allowed = held_sleeves.get(symbol, set()) if held_sleeves is not None else {"CORE_VALUE", "HOTSPOT_SATELLITE"}
        if sleeve is not None:
            allowed = allowed.intersection({sleeve})
        hotspot_held = "HOTSPOT_SATELLITE" in allowed
        current_plan = plans.get(symbol) if hotspot_held else None
        # The explicit private refresh writes ordinary immutable current cases.
        # Rediscover/reverify them after restart without publishing a held list.
        try:
            for path in _case_history(root, symbol) if hotspot_held else ():
                try:
                    return load_held_price_plan(root, symbol,
                        {"case_path": str(path), "case_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}, now=now)
                except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
                    continue
        except OSError:
            pass
        if (current_plan and current_plan.get("candidate_lifecycle") != "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"
                and current_plan.get("signal_state") not in {"BLOCKED", "STALE", "EXPIRED"}):
            return current_plan
        # Value plans use a different contract: reconstruct with the existing
        # loader rather than requiring the hotspot data_available_at field.
        value = None
        try:
            result = (load_current_value_action_plans(root, now=now, symbols=[symbol])
                      if "CORE_VALUE" in allowed else {"items": []})
            value = next((row for row in result["items"] if row["symbol"] == symbol), None)
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            pass
        if value is not None and value.get("signal_state") not in {"BLOCKED", "STALE", "EXPIRED"}:
            return value
        for binding in retained.get(symbol, []) if hotspot_held else ():
            try:
                return load_held_price_plan(root, symbol, binding, now=now)
            except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
                continue
        if value is not None:
            return value
        return current_plan

    def provider(symbol, sleeve=None):
        plan = strategy_plan(symbol, sleeve)
        if plan is None:
            return None
        result = {**plan, "announcement_coverage_status": "UNKNOWN"}
        result.pop("announcement_coverage", None)
        result.pop("announcement_coverage_gap", None)
        try:
            from ..product.quote_bridge import POINTER_PATH
            from ..product.incremental_validity import (
                registered_package, read_bound_json, load_incremental_scan_binding,
            )
            from ..product.daily_event_observation import verify_retained_event_coverage

            if not isinstance(plan.get("market_trade_date"), str):
                raise ValueError("Plan has no verified completed-session date for announcement coverage")
            cutoff = date.fromisoformat(plan["market_trade_date"])
            package_ref, package = registered_package(root, symbol)
            pointer = json.loads((root / POINTER_PATH).read_bytes())
            binding_ref = pointer["quotes"][symbol]["incremental_validity_binding"]
            load_incremental_scan_binding(root=root, binding_ref=binding_ref, symbol=symbol,
                package_path=root / package_ref["path"], package_sha256=package_ref["sha256"],
                review_cutoff=cutoff, today=now)
            _, binding = read_bound_json(root, binding_ref, "held announcement binding")
            _, observation = read_bound_json(root, binding["observation_ref"], "held announcement observation")
            coverage = verify_retained_event_coverage(root, observation, symbol=symbol,
                required_from=date.fromisoformat(package["point_in_time"]["research_as_of"]),
                required_to=cutoff, now=now)
            result.update(announcement_coverage_status=coverage["coverage_status"],
                announcement_coverage={**coverage,
                    "scope": "RESEARCH_CUTOFF_TO_PLAN_COMPLETED_SESSION_ONLY",
                    "observation_binding": binding["observation_ref"],
                    "earlier_event_reviews_replaced": False})
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
            result["announcement_coverage_gap"] = {
                "code": "RETAINED_COVERAGE_NOT_VERIFIED",
                "reason": str(error)[:300],
            }
        return result

    provider.for_sleeve = lambda symbol, sleeve: provider(symbol, sleeve)
    return selected, provider


def load_held_price_plan(root: Path, symbol: str, binding: dict, *, now: datetime) -> dict:
    """Revalidate a retained case directly, without a Top5/previous-items lookup."""
    case = load_current_price_case(root=root, symbol=symbol,
        case_path=root / binding["case_path"],
        expected_sha256=binding["case_sha256"], now=now)
    plan = project_current_price_action_plan(case)
    return {**plan, "case_path": case["case_path"], "case_sha256": case["case_sha256"]}


def _held_decision_code_gaps() -> list[dict]:
    """Missing adapters, not external approvals or evidence of thesis ownership.

    Journal decision/version strings and recording-time public plan snapshots
    do not bind an account's opening lot to its original EntryThesisSnapshot.
    Even an ACTUAL public research entry cannot establish that private link.
    """
    return [
        {"code": "HELD_ENTRY_THESIS_IDENTITY_ADAPTER_MISSING", "gap_category": "CODE_GAP",
         "blocks": ["ENTRY_THESIS_REVIEW_REQUIRED"],
         "required_interface": (
             "Read-only authenticated journal resolver: account scope, journal revision, "
             "opening transaction/lot, symbol, exchange and sleeve -> user-confirmed original "
             "EntryThesisSnapshot artifact identity/hash and matching InvestmentConsistencyReview. "
             "Verify ownership, available-at and actual-entry provenance; public examples, "
             "decision_id and research_version alone are insufficient.")},
        {"code": "HELD_ANNOUNCEMENT_REVIEW_ADAPTER_MISSING", "gap_category": "CODE_GAP",
         "blocks": ["ANNOUNCEMENT_REVIEW_REQUIRED"],
         "required_interface": (
             "Resolve and validate existing EventMaterialityReview against the owned entry, "
             "current research version and retained announcement coverage/cutoff. "
             "Coverage COMPLETE alone does not establish reviewed event impact.")},
        {"code": "HELD_ADVISORY_ENGINE_ADAPTER_MISSING", "gap_category": "CODE_GAP",
         "blocks": ["FORMAL_HELD_DECISION_UNAVAILABLE"],
         "required_interface": (
             "Pass verified owned entry/consistency and existing research, valuation, model, "
             "price, approval and event dependencies to build_advisory_decision_recommendation_v3; "
             "join its result with existing private risk at the same journal revision. "
             "Preserve strategy-specific admission, T+1, human review and no_order gates.")},
    ]


def project_held_continuity(positions: list[dict], risk: dict, *,
                            selected_symbols, plan_provider, generated_at: datetime,
                            entry_context_provider=None, advisory_provider=None, sell_review_request=None) -> dict:
    """Join ALL existing ledger positions to existing plans and risk results.

    Ranking membership is descriptive only. Missing held-decision adapters are
    CODE_GAP, independently of known exit triggers or external evidence gaps.
    """
    if generated_at.utcoffset() is None:
        raise ValueError("Timezone-aware review clock required")
    selected = set(selected_symbols)
    rows = []
    for position in positions:
        if Decimal(position["quantity"]) <= 0:
            continue
        symbol = position["symbol"]
        gaps = _held_risk_blockers(risk, risk.get("engine") or {})
        reasons = []
        plan = None
        held_sleeves = {row["sleeve"] for row in position.get("sleeves", ())
                        if Decimal(row["quantity"]) > 0}
        try:
            plan = plan_provider(symbol)
            if plan is not None:
                if plan.get("symbol") != symbol or plan.get("action") != "no_order":
                    raise ValueError("Unbound or future held-security plan")
                if _plan_sleeve(plan) not in held_sleeves:
                    raise ValueError("Strategy plan does not match a positive held sleeve")
                stamp = plan.get("data_available_at")
                if stamp is not None:
                    available = datetime.fromisoformat(stamp)
                    if available.utcoffset() is None or available > generated_at:
                        raise ValueError("Future held-security plan")
                elif plan.get("schema_version") != "value-action-plan-v1":
                    raise ValueError("Missing plan availability")
                # Provider owns existing-engine freshness verification; retirement
                # must never turn stale observations into current exit evidence.
                if plan.get("signal_state") in {"BLOCKED", "STALE", "EXPIRED", "HISTORICAL_OBSERVATION_NOT_ADMITTED"}:
                    gaps.append("CURRENT_STRATEGY_PLAN_UNAVAILABLE")
                else:
                    behavior = plan.get("price_behavior") or {}
                    if (plan.get("action_intent") in {"EXIT", "REDUCE"}
                            or plan.get("signal_state") == "TRIGGER_REJECTED"
                            or behavior.get("structural_invalidation") is True):
                        reasons.append("INVALIDATION_OR_EXIT_REVIEW")
                    if behavior.get("daily_trend") == "DOWNTREND":
                        reasons.append("DAILY_DOWNTREND_REVIEW")
                gaps.extend(plan.get("blockers") or [])
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            plan = None
        if plan is None:
            gaps.append("CURRENT_STRATEGY_PLAN_UNAVAILABLE")
        announcement_coverage = (plan or {}).get("announcement_coverage_status", "UNKNOWN")
        gaps.append("ENTRY_THESIS_REVIEW_REQUIRED")
        if announcement_coverage != "COMPLETE":
            announcement_coverage = "UNKNOWN"
            gaps.append("ANNOUNCEMENT_COVERAGE_UNKNOWN")
        gaps.append("ANNOUNCEMENT_REVIEW_REQUIRED")
        code_gaps = []
        if not risk.get("engine"):
            gaps.append("PORTFOLIO_RISK_REVIEW_UNAVAILABLE")
        valuation_blockers = (risk.get("facts") or {}).get("valuation_blockers") or []
        sleeves = deepcopy(position.get("sleeves") or [])
        sellable = (None if valuation_blockers else
                    str(sum((Decimal(row["sellable_quantity"]) for row in sleeves), Decimal(0))))
        if sellable is None:
            gaps.extend(valuation_blockers)
            for sleeve in sleeves:
                sleeve["sellable_quantity"] = None
        elif Decimal(sellable) < Decimal(position["quantity"]):
            reasons.append("T_PLUS_ONE_OR_SELLABLE_LIMIT")
        rows.append({"symbol": symbol, "exchange": position["exchange"],
            "quantity": position["quantity"], "sleeves": sleeves,
            "sellable_quantity": sellable, "selected_today": symbol in selected,
            "announcement_coverage_status": announcement_coverage,
            "tracking_basis": "ACTUAL_HELD_SECURITY_NOT_RANKING",
            "review_priority": 0 if "INVALIDATION_OR_EXIT_REVIEW" in reasons else 1,
            "review_reasons": reasons, "data_gaps": list(dict.fromkeys(gaps)),
            "decision_assessment_status": "UNASSESSABLE", "code_gaps": code_gaps,
            "strategy_plan": deepcopy(plan), "formal_eligibility": False,
            "personal_sell_permission": False, "position_guidance": None, "action": "no_order"})
        decisions = []
        for sleeve in sleeves:
            context = (entry_context_provider(symbol, sleeve["sleeve"]) if entry_context_provider else
                       {"blockers": ["AUTHENTICATED_PERSONAL_ENTRY_SUBJECT_REQUIRED"]})
            sleeve_plan = plan if plan is not None and _plan_sleeve(plan) == sleeve["sleeve"] else None
            if sleeve_plan is None and hasattr(plan_provider, "for_sleeve"):
                try:
                    sleeve_plan = plan_provider.for_sleeve(symbol, sleeve["sleeve"])
                    if sleeve_plan is not None:
                        if (sleeve_plan.get("symbol") != symbol or sleeve_plan.get("action") != "no_order"
                                or _plan_sleeve(sleeve_plan) != sleeve["sleeve"]
                                or sleeve_plan.get("signal_state") in {
                                    "BLOCKED", "STALE", "EXPIRED", "HISTORICAL_OBSERVATION_NOT_ADMITTED"}):
                            raise ValueError("Invalid sleeve-specific current plan")
                        stamp = sleeve_plan.get("data_available_at")
                        if stamp is not None:
                            available = datetime.fromisoformat(stamp)
                            if available.utcoffset() is None or available > generated_at:
                                raise ValueError("Future sleeve-specific plan")
                        elif sleeve_plan.get("schema_version") != "value-action-plan-v1":
                            raise ValueError("Missing sleeve-specific plan availability")
                except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
                    sleeve_plan = None
            decision = owned_held_action(context=context, plan=sleeve_plan, risk=risk,
                sleeve_position=sleeve, advisory_provider=lambda: advisory_provider(context, sleeve_plan),
                sell_review_request=(sell_review_request if sell_review_request is not None
                    and sell_review_request["symbol"] == symbol and sell_review_request["exchange"] == position["exchange"]
                    and sell_review_request["sleeve"] == sleeve["sleeve"] else None))
            decisions.append({**decision, "symbol": symbol, "strategy": sleeve["sleeve"],
                              "decision_generated_at": generated_at.isoformat()})
        rows[-1]["actionable_decisions"] = decisions
        rows[-1]["data_gaps"] = list(dict.fromkeys([
            gap for gap in gaps if gap not in {"ENTRY_THESIS_REVIEW_REQUIRED", "ANNOUNCEMENT_REVIEW_REQUIRED"}
        ] + [gap for decision in decisions for gap in decision["blockers"]]))
        if len(decisions) == 1:
            rows[-1]["actionable_decision"] = decisions[0]
            if not decisions[0]["blockers"]:
                rows[-1]["decision_assessment_status"] = "CONDITIONAL_MANUAL_REVIEW"
    rows.sort(key=lambda row: (row["review_priority"], row["symbol"], row["exchange"]))
    return {"schema_version": "private-held-continuity-v1", "action": "no_order",
        "sensitivity": "PRIVATE", "generated_at": generated_at.isoformat(),
        "status": "REVIEW_REQUIRED" if rows else "NO_HELD_SECURITIES",
        "items": rows, "risk": deepcopy(risk), "position_guidance": None}


def review_held_continuity(journal, *, repository_root: Path, generated_at: datetime,
                           selected_symbols=(), plan_provider=None, authenticated_subject=None,
                           sell_review_request=None, committed_risk_source=None) -> dict:
    """Read confirmed lots, existing T+1 and the existing risk engine, never write.

    The default resolver uses current value/hotspot engines and confirmed
    judgment-history case bindings even after registry exit. An explicit
    provider remains available for isolated tests and existing consumers.
    """
    if generated_at.utcoffset() is None:
        raise ValueError("Timezone-aware review clock required")
    day = generated_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
    service = PrivatePortfolioService(journal)
    records = service.records()
    if sell_review_request is not None:
        sell_review_request = _sell_review_request(sell_review_request)
        if not isinstance(authenticated_subject, str) or not authenticated_subject.strip():
            raise JournalValidationError("Authenticated sell-review subject required")
        if sell_review_request["expected_revision"] != len(records):
            raise JournalConflict("REVISION_CONFLICT", "Sell review requires current portfolio revision")
        if not records or sell_review_request["account_scope"] != records[0]["body"]["account_scope"]:
            raise JournalValidationError("Sell-review account mismatch")
    replayed = service._replay(records)
    if plan_provider is None:
        selected_symbols, plan_provider = build_held_plan_provider(repository_root, replayed, now=generated_at)
    risk_kwargs = {"committed_risk_source": committed_risk_source} if committed_risk_source is not None else {}
    risk = review_private_risk_rehearsal(journal, repository_root=repository_root,
        generated_at=generated_at, today=day, **risk_kwargs)
    if replayed is None:
        result = project_held_continuity([], risk, selected_symbols=selected_symbols,
            plan_provider=plan_provider, generated_at=generated_at)
        result["status"] = "NOT_CONNECTED"
        result["revision"] = 0
        return result
    if (risk.get("facts") or {}).get("revision") != replayed.revision:
        raise ValueError("Private journal changed during held review; retry")
    positions = service._positions(replayed.state, day)
    from .personal_entry_thesis import owned_entry_context
    def entry_context(symbol, sleeve):
        return owned_entry_context(records=records, symbol=symbol, sleeve=sleeve,
            authenticated_subject=authenticated_subject, as_of=generated_at)
    result = project_held_continuity(positions, risk, selected_symbols=selected_symbols,
        plan_provider=plan_provider, generated_at=generated_at, entry_context_provider=entry_context,
        advisory_provider=lambda context, plan: evaluate_owned_held_advisory(repository_root,
            context=context, plan=plan, now=generated_at), sell_review_request=sell_review_request)
    if len(service.records()) != len(records):
        raise JournalConflict("REVISION_CONFLICT", "Portfolio changed during held review; retry")
    result["revision"] = replayed.revision
    result["sellable_as_of"] = day.isoformat()
    return result


def review_private_held_sell(journal, *, repository_root, generated_at, payload, authenticated_subject,
                             committed_risk_source=None):
    """Read-only private quantity intent; strategy and risk grant no execution permission."""
    request = _sell_review_request(payload)
    report = review_held_continuity(journal, repository_root=repository_root, generated_at=generated_at,
        authenticated_subject=authenticated_subject, sell_review_request=request,
        committed_risk_source=committed_risk_source)
    matches = [decision for row in report["items"] if row["symbol"] == request["symbol"]
        and row["exchange"] == request["exchange"] for decision in row["actionable_decisions"]
        if decision["strategy"] == request["sleeve"] and Decimal(decision["held_quantity"]) > 0]
    if len(matches) != 1:
        raise JournalValidationError("Sell review requires one actual positive held sleeve")
    return {"schema_version": "private-held-sell-review-v1", "action": "no_order", "sensitivity": "PRIVATE",
        "revision": report["revision"], "generated_at": report["generated_at"], "request": request,
        "status": matches[0]["status"], "actionable_decision": matches[0], "risk": report["risk"],
        "ledger_written": False, "trade_eligible": False, "broker_execution_permission": False}

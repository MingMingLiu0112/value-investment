"""Unregistered research thresholds over already source-recomputed analysis."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import re

from ...domain.decision.value_price_policy import (
    draft_value_price_policy, payload_hash, preview_draft_prices,
)
from ..product.common import load_json_object, sha256_file

SCHEMA = "pending-candidate-conditional-price-v1"
CONFIG_SCHEMA = "pending-candidate-price-proposal-config-v1"
CONFIG_DIRECTORY = "config/pending-candidate-price-proposals-v1"


def _stamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("TIMESTAMP_STRING_REQUIRED")
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return stamp


def exact_basis(analysis):
    """Economic identity includes source availability, scenarios and share count."""
    review = analysis["review_binding"]
    joint = analysis["joint_capital_review"]
    valuation = analysis["valuation"]
    return dict(
        symbol=analysis["symbol"],
        candidate_binding=deepcopy(review["candidate_binding"]),
        review_binding=deepcopy(review),
        economic_policy_binding=deepcopy(joint["policy_binding"]),
        valuation_proposal_binding=deepcopy(joint["proposal_binding"]),
        input_descriptor_sha256=analysis["input_descriptor_sha256"],
        research_version=analysis["research_version"],
        valuation_date=analysis["valuation_date"],
        model_version=valuation["model_version"], model_type=valuation["model_type"],
        available_at=analysis["available_at"], computed_at=analysis["computed_at"],
        currency=joint["economic_path"]["currency"],
        ordinary_shares=analysis["consumed_operating_inputs"]["ordinary_shares"],
        confidence=valuation["confidence"], valuation_sha256=payload_hash(valuation),
        scenarios_sha256=payload_hash(analysis["scenarios"]),
        joint_scenarios_sha256=payload_hash(joint["scenarios"]),
        source_catalog_sha256=payload_hash(analysis["source_catalog"]),
        source_bindings_sha256=payload_hash(analysis["source_bindings"]),
        bear=valuation["bear_value"], base=valuation["base_value"], bull=valuation["bull_value"],
    )


def _empty(reason):
    return dict(schema_version=SCHEMA, status="rejected", value=None,
        unit="CNY/share", action="no_order", formal_eligibility=False,
        user_approved=False, formally_prepared=False, registered=False,
        quantities=None, currentpricecomparison=False,
        draft=None, draft_prices=None, sourcebindings=None,
        proposal_validity=dict(status="rejected", current_valid=False,
            available_at=None, expires_at=None, reasons=[reason]),
        price_comparison=dict(status="not_performed", currentpricecomparison=False,
            reasons=["DATED_RESEARCH_ONLY_NO_CURRENT_QUOTE_EVENT_SHARE_ALIGNMENT"]),
        currentqualification=dict(status="not_established",
            reasons=["PENDING_ECONOMIC_REVIEW", "NO_APPROVED_PLAN_OR_PRIVATE_CONTEXT"]),
        explanation="条件价格提案未通过校验或尚无精确候选配置；不提供已批准计划、当前价格资格或交易指令。",
        reason_codes=[reason], reasons=[reason], reopenconditions=[])


def project_pending_candidate_price_proposal(*, analysis, config, now,
                                             policy_artifact_sha256):
    """Pure adapter; caller must verify source recomputation. No fallback rules."""
    result = _empty("PROPOSAL_REJECTED")
    try:
        if not isinstance(config, dict) or not isinstance(analysis, dict):
            raise ValueError("OBJECT_REQUIRED")
        for field in ("schema_version", "action", "draft_id", "policy_id", "rule_version",
                      "currency", "share_basis", "unit", "rationale", "dividend_coverage_risk",
                      "explanation", "expiry_rationale", "available_at", "expires_at"):
            if not isinstance(config.get(field), str) or not config[field].strip():
                raise ValueError("CONFIG_TEXT_REQUIRED: " + field)
        if (not isinstance(config.get("reopenconditions"), list)
                or not config["reopenconditions"]
                or any(not isinstance(item, str) or not item.strip()
                       for item in config["reopenconditions"])):
            raise ValueError("REOPEN_CONDITIONS_STRING_ARRAY_REQUIRED")
        if not isinstance(config.get("rules"), list):
            raise ValueError("RULE_ARRAY_REQUIRED")
        for rule in config["rules"]:
            if not isinstance(rule, dict) or any(
                    not isinstance(rule.get(field), str) or not rule[field].strip()
                    for field in ("action", "scenario", "value_fraction", "comparison", "rationale")):
                raise ValueError("RULE_TEXT_REQUIRED")
        if (config["schema_version"] != CONFIG_SCHEMA or config["action"] != "no_order"
                or config["registered"] is not False or config["user_approved"] is not False):
            raise ValueError("UNAPPROVED_CONFIG_REQUIRED")
        if not re.fullmatch(r"[0-9a-f]{64}", policy_artifact_sha256):
            raise ValueError("POLICY_ARTIFACT_HASH_REQUIRED")
        if (analysis["status"] != "CONDITIONAL_ANALYSIS_VERIFIED"
                or analysis["action"] != "no_order" or analysis["arithmetic_complete"] is not True
                or analysis["strategy_admitted"] is not False
                or analysis["action_admitted"] is not False
                or analysis["price_comparison_eligible"] is not False):
            raise ValueError("VERIFIED_PENDING_ANALYSIS_REQUIRED")
        basis = exact_basis(analysis)
        if basis != config["exact_basis"]:
            raise ValueError("EXACT_CANDIDATE_BASIS_MISMATCH")
        if (basis["currency"] != "CNY" or config["currency"] != "CNY"
                or config["share_basis"] != "ordinary_share_unadjusted"
                or config["unit"] != "CNY/share"):
            raise ValueError("UNSUPPORTED_CURRENCY_OR_SHARE_BASIS")
        for field in ("currency", "share_basis"):
            if field in analysis and analysis[field] != config[field]:
                raise ValueError("ANALYSIS_PRICE_BASIS_MISMATCH")
        shares = Decimal(basis["ordinary_shares"])
        values = [Decimal(basis[key]) for key in ("bear", "base", "bull")]
        if not shares.is_finite() or shares <= 0:
            raise ValueError("INVALID_SHARE_COUNT")
        if (any(not value.is_finite() or value <= 0 for value in values)
                or not values[0] <= values[1] <= values[2]):
            raise ValueError("INVALID_SCENARIO_ORDER_OR_VALUE")
        scenarios = analysis["scenarios"]
        joint = analysis["joint_capital_review"]
        if ([row["scenario"] for row in scenarios] != ["bear", "base", "bull"]
                or [row["scenario"] for row in joint["scenarios"]] != ["bear", "base", "bull"]
                or any(row["per_share_value"] != basis[row["scenario"]] for row in scenarios)
                or any(row["valuation_per_share"] != basis[row["scenario"]] for row in joint["scenarios"])
                or joint["candidate_binding"] != basis["candidate_binding"]
                or joint["input_descriptor_sha256"] != basis["input_descriptor_sha256"]
                or analysis["valuation"]["valuation_date"] != basis["valuation_date"]):
            raise ValueError("CONSUMED_SCENARIO_OR_IDENTITY_MISMATCH")
        context = basis["review_binding"]["model_context"]
        if (context["input_descriptor_sha256"] != basis["input_descriptor_sha256"]
                or context["model_version"] != basis["model_version"]
                or context["model_id"] != basis["model_type"]):
            raise ValueError("MODEL_CONTEXT_MISMATCH")
        if [(r["action"], r["scenario"], r["value_fraction"], r["comparison"])
                for r in config["rules"]] != [
                    ("entry", "bear", "1", "LTE"), ("reduce", "bull", "1", "GTE")]:
            raise ValueError("EXPLICIT_RESEARCH_ENDPOINT_RULES_REQUIRED")
        if not config["reopenconditions"] or not config["expiry_rationale"].strip():
            raise ValueError("EXPIRY_AND_REOPEN_EVIDENCE_REQUIRED")
        available, expires = _stamp(config["available_at"]), _stamp(config["expires_at"])
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("TIMEZONE_REQUIRED")
        if expires <= available:
            raise ValueError("INVALID_FIXED_EXPIRY")
        for field in ("available_at", "computed_at"):
            if _stamp(basis[field]) > available:
                raise ValueError("PROPOSAL_PREDATES_CONSUMED_ANALYSIS")
        if now < available:
            result["proposal_validity"].update(status="not_yet_available",
                available_at=config["available_at"], expires_at=config["expires_at"],
                reasons=["PROPOSAL_NOT_YET_AVAILABLE"])
            result["reason_codes"] = result["reasons"] = ["PROPOSAL_NOT_YET_AVAILABLE"]
            return result
        plan = dict(action="no_order", symbol=basis["symbol"],
            research_version=basis["research_version"],
            valuation_input_version=basis["input_descriptor_sha256"],
            model_id=context["model_id"], model_type=basis["model_type"],
            model_version=basis["model_version"], valuation_date=basis["valuation_date"],
            bear=basis["bear"], base=basis["base"], bull=basis["bull"],
            source_bindings=analysis["source_bindings"])
        draft = draft_value_price_policy(plan, draft_id=config["draft_id"],
            policy_id=config["policy_id"], rule_version=config["rule_version"],
            profile_id=context["profile_id"], effective_from=available.date(),
            effective_through=expires.date(), rationale=config["rationale"],
            dividend_coverage_risk=config["dividend_coverage_risk"], rules=config["rules"])
        state = "expired" if now >= expires else "valid"
        reasons = ["RESEARCH_REVIEW_THRESHOLDS_NOT_ACTION_PLAN",
            "LOW_CONFIDENCE_BEAR_NOT_SUFFICIENT_SAFETY_MARGIN",
            "ADD_EXIT_REQUIRE_ENTRY_THESIS_PRIVATE_CONTEXT"]
        if state == "expired":
            reasons.append("FIXED_PROPOSAL_EXPIRY_REACHED")
        result.update(status="researcher_proposal", draft=draft,
            draft_prices=preview_draft_prices(draft),
            proposal_validity=dict(status=state, current_valid=state == "valid",
                available_at=config["available_at"], expires_at=config["expires_at"],
                reasons=["DATED_PROPOSAL_ONLY"] if state == "valid" else ["FIXED_PROPOSAL_EXPIRY_REACHED"],
                expiry_rationale=config["expiry_rationale"]),
            sourcebindings=dict(candidate_sha256=basis["candidate_binding"]["sha256"],
                candidate_binding=deepcopy(basis["candidate_binding"]),
                policy_artifact_sha256=policy_artifact_sha256,
                research_version=basis["research_version"], model_version=basis["model_version"],
                input_descriptor_sha256=basis["input_descriptor_sha256"],
                valuation_date=basis["valuation_date"], currency=config["currency"],
                share_basis=config["share_basis"], ordinary_shares=basis["ordinary_shares"],
                exact_basis=deepcopy(basis), sources=deepcopy(analysis["source_bindings"])),
            explanation=config["explanation"], reason_codes=reasons, reasons=list(reasons),
            reopenconditions=deepcopy(config["reopenconditions"]))
        return result
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError) as error:
        return _empty("INVALID_PROPOSAL: " + str(error))


def load_pending_candidate_price_proposal(*, root, analysis, now):
    """Candidate-addressed, read-only artifact; never prepare/register/confirm."""
    from .value_research_analysis import _bound
    try:
        binding = analysis["review_binding"]["candidate_binding"]
        digest = binding["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("INVALID_CANDIDATE_HASH")
        path = root / CONFIG_DIRECTORY / (digest + ".json")
        if not path.is_file():
            return _empty("NO_EXPLICIT_CANDIDATE_PRICE_PROPOSAL")
        artifact_hash = sha256_file(path)
        config = load_json_object(path, "pending candidate price proposal")
        _bound(root, binding)
        for source in analysis["source_bindings"]:
            _bound(root, source)
        result = project_pending_candidate_price_proposal(analysis=analysis,
            config=config, now=now, policy_artifact_sha256=artifact_hash)
        _bound(root, binding)
        for source in analysis["source_bindings"]:
            _bound(root, source)
        if sha256_file(path) != artifact_hash:
            raise ValueError("POLICY_ARTIFACT_CHANGED_DURING_READ")
        return result
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as error:
        return _empty("PROPOSAL_SOURCE_VERIFICATION_FAILED: " + str(error))

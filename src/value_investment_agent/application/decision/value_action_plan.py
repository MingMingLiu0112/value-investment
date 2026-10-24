"""ValueActionPlan adapters over existing replay and published research contracts."""
from __future__ import annotations

from datetime import date, datetime
from copy import deepcopy
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
from ..product.quote_bridge import POINTER_PATH as QUOTE_POINTER_PATH, execute_quote_bridge_for_symbol
from ..product.value_decision_explanation import project_value_decision_explanation
from ..product.decision_surface import verify_current_decision_workbench
from ..product.research_reviews import verify_human_approval_transport_provenance
from .restore_decision_recommendation import RestoredDecisionRecommendation
from .value_model_identity import project_catalog_identity

CHINA = ZoneInfo("Asia/Shanghai")


def _review_fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


class CoreValuePublicReviews:
    """Request-local native replay inputs; never serialized approval or account authority.

    This application adapter preserves Domain verdicts. It cannot create or
    change G3, price-policy, personal-risk or order eligibility.
    """

    def __init__(self, root: Path, *, now: datetime):
        if now.utcoffset() is None:
            raise ValueError('Public review requires an aware request clock')
        self.root, self.now = root.resolve(), now
        self._active = False
        self._native, self._plans = {}, {}

    def __enter__(self):
        if self._active:
            raise ValueError('Public review request already active')
        self._active = True
        return self

    def __exit__(self, *errors):
        self._active = False
        self._native.clear()
        self._plans.clear()

    def discard(self, symbol):
        self._native.pop(symbol, None)
        self._plans.pop(symbol, None)

    def _capture(self, *, root, now, chain, restored, policy, published, explanation,
                 quote, domain_plan, plan, sources):
        symbol = plan['symbol']
        self.discard(symbol)
        if (not self._active or root.resolve() != self.root or now != self.now
                or not isinstance(restored, RestoredDecisionRecommendation)
                or domain_plan.get('formal_eligibility') is not True
                or domain_plan.get('formal_eligibility_blockers')):
            return
        raw = (self.root/'config/current-trial-workbook.json').read_bytes()
        if json.loads(raw) != chain['pointer']:
            raise ValueError('Publication changed during native public replay')
        self._native[symbol] = dict(owner=self, root=self.root, now=self.now, restored=restored, policy=policy,
            recommendation=_review_fingerprint(restored.recommendation.as_policy()),
            published=deepcopy(published), explanation=deepcopy(explanation), quote=deepcopy(quote),
            domain_plan=deepcopy(domain_plan), base_plan=deepcopy(plan), sources=deepcopy(sources),
            pointer_sha256=hashlib.sha256(raw).hexdigest())

    def bind_plan(self, plan, *, inherited_from=None):
        """Pin the API plan only if its already-verified native semantics are unchanged."""
        symbol = plan.get('symbol')
        record = self._native.get(symbol)
        if not self._active or record is None:
            return
        basis = inherited_from or plan
        analysis = plan.get('research_analysis')
        if (any(basis.get(key) != value for key, value in record['base_plan'].items())
                or any(plan.get(key) != value for key, value in basis.items()
                       if key not in {'research_analysis', 'research_analysis_status'})
                or analysis is not None and (not isinstance(analysis, dict)
                    or analysis.get('status') == 'SOURCE_OR_REPLAY_UNAVAILABLE'
                    or not isinstance(analysis.get('source_bindings'), list)
                    or not analysis['source_bindings'])):
            self.discard(symbol)
            return
        # Presentation analysis is separately consumed; it is not a Domain input.
        record['analysis'] = deepcopy(analysis)
        record['analysis_sources'] = deepcopy(analysis['source_bindings']) if analysis is not None else []
        self._plans[symbol] = _review_fingerprint(plan)

    def action_for(self, plan, *, now):
        """Recheck existing native authority and bytes; return a review label, not eligibility."""
        try:
            symbol = plan['symbol']
            record = self._native.get(symbol)
            if (not self._active or now != self.now or record is None or record['owner'] is not self
                    or record['root'] != self.root or record['now'] != self.now
                    or self._plans.get(symbol) != _review_fingerprint(plan)
                    or plan.get('decision_as_of') != now.astimezone(CHINA).date().isoformat()
                    or plan.get('signal_state') in {'BLOCKED', 'STALE', 'EXPIRED'}):
                return None
            def verify_bytes():
                if hashlib.sha256((self.root/'config/current-trial-workbook.json').read_bytes()).hexdigest() != record['pointer_sha256']:
                    raise ValueError('Publication changed during public review')
                for ref in [*record['sources'], *record['analysis_sources']]:
                    relative = Path(ref['path'])
                    path = (self.root/relative).resolve()
                    if (relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(self.root)
                            or hashlib.sha256(path.read_bytes()).hexdigest() != ref['sha256']):
                        raise ValueError('Native public review source changed')
            verify_bytes()
            if record['analysis'] is not None:
                from ..product.research_draft import load_current_research_analysis
                analysis = load_current_research_analysis(self.root, symbol, now=now)
                if (not isinstance(analysis, dict)
                        or analysis.get('status') == 'SOURCE_OR_REPLAY_UNAVAILABLE'
                        or _review_fingerprint(analysis) != _review_fingerprint(record['analysis'])):
                    return None
            restored, _ = replay_published_value_decision(self.root, record['published'], now=now)
            if (restored is None or not isinstance(record['restored'], RestoredDecisionRecommendation)
                    or _review_fingerprint(restored.recommendation.as_policy()) != record['recommendation']
                    or _review_fingerprint(record['restored'].recommendation.as_policy()) != record['recommendation']):
                return None
            policy = record['policy']
            if policy is not None:
                policy = load_value_action_policy(root=self.root, binding=dict(policy.source_binding),
                    symbol=symbol, now=now)
                if policy != record['policy']:
                    return None
            rebuilt = build_value_action_plan(explanation=record['explanation'], policy=policy,
                reference_quote=record['quote'], source_bindings=tuple(record['sources']),
                repository_replayed=True, verified_predecision=restored.dependency_objects.get('pre_decision'),
                decision_as_of=now.astimezone(CHINA).date()).as_policy()
            if (rebuilt != record['domain_plan'] or rebuilt.get('formal_eligibility') is not True
                    or rebuilt.get('formal_eligibility_blockers')):
                return None
            verify_bytes()
            return rebuilt.get('action_intent')
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError, AttributeError):
            return None


def replay_published_value_decision(root: Path, explanation: dict, *, now: datetime,
                                  chain: dict | None = None
                                  ) -> tuple[RestoredDecisionRecommendation | None, dict | None]:
    """Restore the explicit publication proof; display flags are never admission."""
    if chain is None:
        try:
            chain = load_current_chain(root)
        except STRUCTURE_ERRORS:
            return None, None
    binding = chain.get("sources", {}).get("decision_workbench_binding")
    if binding is None:
        return None, None
    workbench = bound_object(root, binding)
    stamp = datetime.fromisoformat(workbench["generated_at"])
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("Published decision workbench is unavailable at cutoff")
    restored = verify_current_decision_workbench(
        workbench,
        human_approval_provenance_verifier=lambda approval: (
            verify_human_approval_transport_provenance(root, approval)
        ),
    )
    if restored.recommendation.symbol != explanation.get("symbol"):
        return None, None
    expected = project_value_decision_explanation(restored, evidence_scope="RETAINED_RESEARCH")
    if any(explanation.get(key) != value for key, value in expected.items()):
        raise ValueError("Published explanation differs from replayed decision")
    if explanation.get("model_id", restored.recommendation.input_model_id) != restored.recommendation.input_model_id:
        raise ValueError("Published explanation model differs from replayed decision")
    research_as_of = restored.dependency_objects["research_case"].as_of.isoformat()
    if explanation.get("research_as_of", research_as_of) != research_as_of:
        raise ValueError("Published research date differs from replayed decision")
    return restored, binding


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


def _registered_quote_observation(root: Path, symbol: str, *, now: datetime) -> tuple[dict, dict, list[dict]]:
    """Reuse quote verification without admitting a registry entry to research."""
    execution = {}
    try:
        execution = dict(execute_quote_bridge_for_symbol(root, symbol, today=now))
        pointer = execution.pop("pointer", None)
        close = execution.get("quote") or {}
        compatibility = execution.get("compatibility") or {}
        if ((compatibility.get("verified_quote") or {}).get("eligible") is not True
                or close.get("latest_completed_session") is None
                or close.get("quote_date") != close["latest_completed_session"]):
            return execution, {}, []
        quote_day = date.fromisoformat(close["quote_date"])
        price = Decimal(close["display_price"])
        if quote_day > now.astimezone(CHINA).date() or not price.is_finite() or price <= 0:
            raise ValueError("Registered close identity/availability invalid")
        binding = dict(path=close["bundle_path"], sha256=close["bundle_sha256"])
        bound_object(root, binding)
        if not execution.get("sources"):
            raise ValueError("Registered close lacks verified source evidence")
        # bound_object only accepts runtime bindings; the pointer has one fixed config path.
        if (not isinstance(pointer, dict) or set(pointer) != {"path", "sha256"}
                or pointer["path"] != QUOTE_POINTER_PATH):
            raise ValueError("Registered close lacks its exact quote pointer binding")
        pointer_path = (root / QUOTE_POINTER_PATH).resolve()
        if (not pointer_path.is_relative_to(root)
                or hashlib.sha256(pointer_path.read_bytes()).hexdigest() != pointer["sha256"]):
            raise ValueError("Registered quote pointer hash mismatch")
        return execution, dict(symbol=symbol, price=close["display_price"],
            quote_date=close["quote_date"], status="verified_close",
            scope=close.get("display_scope") or execution["status"],
            comparison_eligible=False), [binding, pointer]
    except (*STRUCTURE_ERRORS, ArithmeticError) as error:
        return {**execution, "status": "NOT_ADMITTED", "reason": str(error),
                "next_step": str(error)}, {}, []


def load_registered_value_action_plans(root: Path, *, now: datetime,
                                       symbols: list[str] | tuple[str, ...] | None = None,
                                       public_reviews: CoreValuePublicReviews | None = None) -> dict:
    """Read-only current publication projection, never a new financial approval.

    Only an explicit hash-bound workbench replay can supply typed admission.
    Legacy display-only explanations remain ineligible for formal review.
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
            restored, replay_binding = replay_published_value_decision(
                root, explanation, now=now, chain=chain)
            if restored is not None:
                sources.append(replay_binding)
                explanation = {**explanation, "model_id": restored.recommendation.input_model_id}
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
                reference_quote=quote, source_bindings=tuple(sources), decision_as_of=day,
                repository_replayed=restored is not None,
                verified_predecision=(None if restored is None else
                    restored.dependency_objects.get("pre_decision"))).as_policy()
            domain_plan = deepcopy(plan)
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
            plan["verification_scope"] = ("REPOSITORY_REPLAYED_PUBLISHED_RESEARCH_NOT_NEW_APPROVAL"
                if restored is not None else "HASH_BOUND_PUBLISHED_RESEARCH_NOT_NEW_APPROVAL")
            if public_reviews is not None:
                public_reviews._capture(root=root, now=now, chain=chain, restored=restored,
                    policy=policy, published=bound_object(root, binding), explanation=explanation,
                    quote=quote, domain_plan=domain_plan, plan=plan, sources=sources)
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
                execution, quote, quote_sources = _registered_quote_observation(root, symbol, now=now)
                sources.extend(quote_sources)
                historical_blockers = list(explanation["blockers"])
                resolved_quote_blockers = [reason for reason in historical_blockers
                    if quote and reason == "等待已验证收盘行情"]
                explanation["blockers"] = [reason for reason in historical_blockers
                    if reason not in resolved_quote_blockers]
                quote_blockers = [] if quote else ["VALUE_LATEST_COMPLETED_QUOTE_NOT_VERIFIED"]
                explanation["blockers"].extend(quote_blockers)
                plan = build_value_action_plan(explanation=explanation, reference_quote=quote,
                    source_bindings=tuple(sources)).as_policy()
                plan["research_as_of"] = None
                plan["research_as_of_basis"] = "REGISTERED_RESEARCH_GAPS_ONLY"
                plan["qualification"] = "REGISTERED_RESEARCH_GAPS_ONLY"
                plan["explanation"] = "仅展示注册研究缺口及通过核验的收盘事实；尚无完整估值情景，不授予价格比较或操作资格。"
                if not quote:
                    plan["reference_price_scope"] = "NO_VERIFIED_CLOSE"
                plan["quote_bridge_status"] = execution["status"]
                plan["current_quote_verified"] = bool(quote)
                plan["current_quote_blockers"] = quote_blockers
                plan["historical_research_blockers"] = historical_blockers
                plan["resolved_historical_quote_blockers"] = resolved_quote_blockers
                plan["current_pricing_blockers"] = [reason for reason in plan["blockers"]
                    if reason.startswith("VALUE_")]
                next_step = execution.get("next_step") or execution.get("reason")
                if next_step:
                    plan["required_confirmations"].append(next_step)
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

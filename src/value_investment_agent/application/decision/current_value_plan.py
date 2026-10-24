"""Read-time revalidation of a frozen value plan without new approvals."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from .value_action_plan import load_registered_value_action_plans, CoreValuePublicReviews
from ...domain.decision.value_action_plan import build_value_action_plan
from ..product.research_draft import load_current_research_analysis


def _pending_plan_can_replace(plan: dict | None) -> bool:
    return plan is None or (
        plan.get('verification_scope') in {
            'HASH_BOUND_PUBLISHED_RESEARCH_NOT_NEW_APPROVAL',
            'REGISTERED_RESEARCH_GAPS_ONLY', 'SOURCE_BOUND_PENDING_ARITHMETIC_NOT_APPROVAL'}
        and plan.get('candidate_action') == 'NO_ACTION'
        and plan.get('action_intent') is None
        and not plan.get('security_review_eligible')
        and not plan.get('formal_eligibility')
        and (plan.get('scenario_validity') or {}).get('status') in {
            'conditional_research_only', 'not_ready'})


def _pending_analysis_plan(analysis: dict, prior: dict | None, now: datetime) -> dict:
    prior = prior or {}
    sources = list(analysis['source_bindings'])
    quote = {}
    if prior.get('current_quote_verified') is True:
        quote = dict(symbol=analysis['symbol'], price=prior['reference_close'],
            quote_date=prior['market_trade_date'], status='verified_close', comparison_eligible=False,
            scope='CURRENT_VERIFIED_CLOSE_NOT_VALUATION_COMPARABLE')
        sources.extend(source for source in prior['source_bindings'] if source not in sources)
    historical_blockers = list(analysis['blockers'])
    resolved = [reason for reason in historical_blockers if quote and reason in {
        '等待已验证收盘行情', 'price_bridge_pending_external_data'}]
    quote_blockers = [] if quote else ['VALUE_LATEST_COMPLETED_QUOTE_NOT_VERIFIED']
    context = analysis['review_binding']['model_context']
    explanation = dict(symbol=analysis['symbol'], company_name=analysis['company_name'], action='no_order',
        research_as_of=analysis['research_as_of'], research_version=analysis['research_version'],
        decision_as_of=now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat(),
        valuation=analysis['valuation'], model_id=context['model_id'], model_validity=analysis['model_validity'],
        candidate_action='NO_ACTION',
        blockers=[reason for reason in historical_blockers if reason not in resolved] + quote_blockers,
        thesis=analysis['thesis'], support=analysis['supporting_evidence'],
        counter_evidence=analysis['counter_evidence'], thesis_breakers=analysis['thesis_breakers'],
        next_events=analysis['next_events'], evidence_refs=analysis['valuation']['evidence_refs'])
    plan = build_value_action_plan(explanation=explanation, reference_quote=quote,
        source_bindings=tuple(sources)).as_policy()
    plan.update(verification_scope='SOURCE_BOUND_PENDING_ARITHMETIC_NOT_APPROVAL',
        profile_id=context['profile_id'], valuation_input_version=analysis['input_descriptor_sha256'],
        current_quote_verified=bool(quote), current_quote_blockers=quote_blockers,
        historical_research_blockers=historical_blockers, resolved_historical_quote_blockers=resolved,
        current_pricing_blockers=[reason for reason in plan['blockers'] if reason.startswith('VALUE_')],
        quote_bridge_status=prior.get('quote_bridge_status', 'NOT_ADMITTED'))
    if not quote:
        plan['reference_price_scope'] = 'NO_VERIFIED_CLOSE'
    return plan


def load_current_value_action_plans(root: Path, *, now: datetime,
        symbols: list[str] | tuple[str, ...] | None = None,
        public_reviews: CoreValuePublicReviews | None = None) -> dict:
    """Extend the byte-bound legacy loader with independently verified analysis."""
    options = {'public_reviews': public_reviews} if public_reviews is not None else {}
    current = load_registered_value_action_plans(root, now=now, symbols=symbols, **options)
    items, blockers, bindings = current['items'], current['blockers'], current['source_bindings']
    analysis_symbols = set(symbols or [item['symbol'] for item in items])
    if symbols is None:
        for name, field in (("user-research-workflow-v1.json", "supplemental_review_candidates"),
                            ("current-pending-candidate-replays-v1.json", "publications")):
            path = root / "config" / name
            if path.exists():
                try:
                    entries = json.loads(path.read_bytes()).get(field, {})
                    if (not isinstance(entries, dict) or any(not isinstance(key, str)
                            or len(key) != 6 or not key.isdigit() for key in entries)):
                        raise ValueError("Invalid pending analysis registry")
                    analysis_symbols.update(entries)
                except (ValueError, OSError, KeyError, TypeError) as error:
                    blockers.append("VALUE_ANALYSIS_REGISTRY_UNAVAILABLE:" + str(error))
    by_symbol = {item['symbol']: item for item in items}
    for symbol in sorted(analysis_symbols):
        analysis = load_current_research_analysis(root, symbol, now=now)
        if analysis is None:
            continue
        plan = by_symbol.get(symbol)
        if (_pending_plan_can_replace(plan) and analysis['arithmetic_complete']
                and (plan is None or not plan.get('research_as_of')
                     or plan['research_as_of'] <= analysis['research_as_of'])):
            replacement = _pending_analysis_plan(analysis, plan, now)
            if plan is None:
                items.append(replacement)
            else:
                items[items.index(plan)] = replacement
            plan = replacement
        elif plan is not None and _pending_plan_can_replace(plan) and not analysis['arithmetic_complete']:
            replacement = _invalidate_current_conditions(plan, plan, analysis['blockers'])
            replacement['signal_state'] = 'BLOCKED'
            items[items.index(plan)] = replacement
            plan = replacement
        if plan is not None:
            plan['research_analysis'] = analysis
            plan['research_analysis_status'] = analysis['status']
        if not analysis['arithmetic_complete']:
            blockers.extend(analysis['blockers'])
        bindings.extend(source for source in analysis['source_bindings'] if source not in bindings)
    if public_reviews is not None:
        for plan in items:
            public_reviews.bind_plan(plan)
    return {**current, 'status': 'VALUE_RESEARCH_OBSERVATION' if items else 'BLOCKED'}


def _with_analysis(plan: dict, analysis: dict | None) -> dict:
    result = dict(plan)
    result.pop('research_analysis', None)
    result.pop('research_analysis_status', None)
    if analysis is not None:
        result['research_analysis'] = analysis
        result['research_analysis_status'] = analysis['status']
    return result


def revalidate_current_value_plan(root: Path, frozen: dict, *, now: datetime,
        public_reviews: CoreValuePublicReviews | None = None) -> dict:
    if frozen.get("schema_version") != "value-action-plan-v1":
        return frozen
    options = {'public_reviews': public_reviews} if public_reviews is not None else {}
    current = load_current_value_action_plans(root, now=now, symbols=[frozen["symbol"]], **options)
    rebuilt = next((row for row in current["items"] if row["symbol"] == frozen["symbol"]), None)
    analysis = (rebuilt.get('research_analysis') if rebuilt is not None else
        load_current_research_analysis(root, frozen['symbol'], now=now))
    if rebuilt is not None and all(frozen.get(key) == value for key, value in rebuilt.items()
            if key not in {'research_analysis', 'research_analysis_status'}):
        result = _with_analysis(frozen, analysis)
        if public_reviews is not None:
            public_reviews.bind_plan(result, inherited_from=rebuilt)
        return result
    if public_reviews is not None:
        public_reviews.discard(frozen['symbol'])
    return _with_analysis(_invalidate_current_conditions(frozen, rebuilt, current['blockers']), analysis)


def _invalidate_current_conditions(frozen: dict, rebuilt: dict | None, blockers: list[str]) -> dict:
    # Retain the immutable prior packet itself for historical review, while the
    # current view must not reuse conditions whose source/date no longer checks.
    result = {**frozen, "signal_state": "STALE" if rebuilt else "BLOCKED", "action_intent": None,
              "action_eligibility": False, "formal_eligibility": False, "portfolio_eligibility": None,
              "price_comparison_eligible": False, "current_reference_price": None, "reference_close": None,
              "current_quote_verified": False,
              "current_quote_blockers": ["CURRENT_VERIFIED_QUOTE_NOT_AVAILABLE_IN_REBUILT_PLAN"],
              "bear": None, "base": None, "bull": None, "conditional_valuation_range": None,
              "invalidation_price": None,
              "blockers": list(dict.fromkeys([*frozen.get("blockers", []), "CURRENT_VALUE_PLAN_CHANGED_OR_STALE", *blockers])),
              "explanation": "本次读取无法重现已发布估值与价格条件；旧方案仅保留在历史版本，当前不作为操作依据。"}
    # A new verified quote remains an observable fact even when old economics
    # cannot be reproduced. Never reuse the frozen quote's verification flag.
    if rebuilt is not None and rebuilt.get("current_quote_verified") is True:
        try:
            price = Decimal(str(rebuilt.get("reference_close")))
            if (not price.is_finite() or price <= 0 or not rebuilt.get("market_trade_date")
                    or not rebuilt.get("source_bindings")):
                raise ValueError('Rebuilt verified quote is incomplete')
        except (InvalidOperation, ValueError):
            pass
        else:
            result.update(reference_close=str(price), current_reference_price=str(price),
                market_trade_date=rebuilt["market_trade_date"], current_quote_verified=True,
                current_quote_blockers=[], reference_price_scope="CURRENT_VERIFIED_CLOSE_NOT_VALUATION_COMPARABLE",
                source_bindings=rebuilt["source_bindings"])
    for action in ("entry", "add", "reduce", "exit"):
        result[action + "_condition"] = None
        result[action + "_trigger_price"] = None
    return result

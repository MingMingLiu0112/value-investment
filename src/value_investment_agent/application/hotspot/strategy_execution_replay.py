"""Read-only retained-source execution experiment; no admission side effects."""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from pathlib import Path

from .event_replay import _bound_bytes
from .retained_source_replay import build_retained_descriptive_validation, _verified_case
from ...historical_fees import SOURCES as FEE_NOTICE_URLS
from ...infrastructure.hotspot.statutory_fee_evidence import inspect_statutory_fee_evidence
from ...domain.hotspot import strategy_execution_replay as engine

OFFICIAL_SOURCES = [
    {"topic": "SELL_STAMP_TAX_HALVED_FROM_20230828", "rate": "0.0005",
     "url": "https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20230827_5725662.shtml"},
    {"topic": "TRANSFER_FEE_DOUBLE_SIDED_FROM_20220429", "rate": "0.00001",
     "url": FEE_NOTICE_URLS["transfer-2022"],
     "retrieval_status": "RETAINED_OFFICIAL_ORIGINAL_VERIFICATION_REQUIRED"},
    {"topic": "EXCHANGE_HANDLING_FEE_INCLUDED_IN_ASSUMED_ALL_IN_COMMISSION",
     "url": "https://www.sse.com.cn/services/tradingservice/charge/ssecharge/"},
    {"topic": "EXCHANGE_TRADING_RULES_T1_AND_DATED_STOCK_LIMITS",
     "url": "https://www.sse.com.cn/lawandrules/sselawsrules2025/fund/trading/c/c_20260424_10817739.shtml"},
]


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def build_strategy_execution_replay(*, root: Path, now: datetime,
                                    manifest_binding: dict | None = None,
                                    commission_rate="0.0003", minimum_commission_cny="5",
                                    slippage_bps="10", initial_cash_cny=engine.DEFAULT_INITIAL_CASH_CNY, quantity=100):
    """Reverify originals, derive all intents, run strict and assumed-state lanes.

    Each security/partition has its own reset account. Aggregate counts are
    descriptive, not a multi-security portfolio return or untouched OOS result.
    Source root is read-only; callers choose a separate output destination.
    """
    root = Path(root).resolve()
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware evaluation time required")
    pointer_binding = None
    if manifest_binding is None:
        name = "config/hotspot-replay-review-v1.json"
        raw = (root / name).read_bytes()
        pointer_binding = dict(path=name, sha256=sha256(raw).hexdigest())
        pointer = json.loads(raw)
        if pointer.get("action") != "no_order":
            raise ValueError("Invalid replay pointer")
        manifest_binding = pointer["retained_manifest_binding"]
    descriptive = build_retained_descriptive_validation(root=root,
        manifest_binding=manifest_binding, now=now)
    manifest = json.loads(_bound_bytes(root, manifest_binding))
    source_root = (root / manifest_binding["path"]).parent / "sources"
    spec = json.loads(_bound_bytes(source_root, manifest["historical_protocol_binding"]))
    parameters = dict(experiment_version=engine.EXPERIMENT_VERSION,
        signal_rule_version=engine.RULE_VERSION, quantity=quantity,
        initial_cash_cny=initial_cash_cny, participation="0.01",
        entry="FROZEN_60M_BREAKOUT_NEXT_BAR_NO_CHASE_ABOVE_SIGNAL_CLOSE",
        exit="COMPLETED_CLOSE_BELOW_ENTRY_INVALIDATION_OR_FIVE_SUBSEQUENT_OBSERVED_SESSIONS",
        exit_retry="RETRY_AT_NEXT_AVAILABLE_BAR_UNTIL_PARTITION_END",
        fill="NEXT_60M_BAR_OPEN_PLUS_ONE_SECOND_ASSUMED_OPEN_PRICE_WITH_SLIPPAGE",
        engine_time="BAR_CLOSE_LABEL_FOR_MARKS_FILL_PRICE_IS_BAR_OPEN",
        account="ISOLATED_SECURITY_AND_PARTITION_FIXED_ROUND_LOTS_NOT_PORTFOLIO",
        historical_registration="RETROSPECTIVE_EXPERIMENT_NO_BACKDATED_REGISTRATION")
    costs = dict(commission_rate=str(commission_rate), minimum_commission_cny=str(minimum_commission_cny),
        sell_tax_rate="0.0005", transfer_fee_rate="0.00001", slippage_bps=str(slippage_bps),
        known_at=now.isoformat(), effective_start="2023-08-28T00:00:00+08:00",
        effective_end="2026-12-31T23:59:59+08:00",
        scope="RETROSPECTIVE_FEE_SENSITIVITY_NOT_PERSONAL_CONFIRMED_SCHEDULE",
        commission_basis="ASSUMED_ALL_IN_INCLUDING_EXCHANGE_HANDLING_AND_REGULATORY_FEES_EXCLUDING_TRANSFER_AND_STAMP",
        official_sources=OFFICIAL_SOURCES)
    fee_evidence = inspect_statutory_fee_evidence(root=root, now=now)
    components = fee_evidence["published_components"] or {}
    fee_evidence["declared_rates_match_notices"] = (
        fee_evidence["source_status"] == "VERIFIED_RETAINED_OFFICIAL_NOTICES"
        and costs["sell_tax_rate"] == components.get("sell_stamp_rate")
        and costs["transfer_fee_rate"] == components.get("transfer_rate"))
    results = []
    for item in spec["cases"]:
        case, available = _verified_case(source_root, item, manifest["namespace"], spec["end_date"], now)
        kwargs = dict(symbol=item["symbol"], bars_by_period=case["bars"], spec=spec,
            costs=costs, initial_cash=initial_cash_cny, quantity=quantity)
        strict = engine.replay_strategy_execution(**kwargs, mode="STRICT")
        scenarios = []
        for multiplier in ("0", "1", "2"):
            result = engine.replay_strategy_execution(**kwargs,
                mode="ASSUMED_REGULAR_TRADING", cost_multiplier=multiplier)
            for fold in result["folds"]:
                initial = Decimal(str(initial_cash_cny))
                gross = Decimal(fold["ending_equity_cny"]) + Decimal(fold["total_fees_cny"]) + Decimal(fold["total_slippage_cny"])
                peak, drawdown = initial, Decimal(0)
                gross_curve = []
                for point in fold["equity_curve"]:
                    impact = sum((Decimal(f["fees_cny"]) + Decimal(f["slippage_cny"])
                        for f in fold["fills"] if f["time"] <= point["time"]), Decimal(0))
                    equity = Decimal(point["equity_cny"]) + impact
                    peak = max(peak, equity)
                    drawdown = max(drawdown, (peak - equity) / peak)
                    gross_curve.append(dict(time=point["time"], equity_cny=str(equity)))
                intentions = {o["id"]: o for o in fold["generated_intentions"]}
                for fill in fold["fills"]:
                    fill["execution_bar_close_label"] = fill["time"]
                    fill["hypothetical_execution_at"] = intentions[fill["order_id"]]["actual_execution_at"]
                    gross_fill = Decimal(fill["price"]) * fill["quantity"]
                    factor = Decimal(multiplier)
                    cents = lambda amount: (amount * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    parts = dict(commission_cny=str(cents(max(Decimal(str(minimum_commission_cny)),
                        gross_fill * Decimal(str(commission_rate))))),
                        transfer_fee_cny=str(cents(gross_fill * Decimal(costs["transfer_fee_rate"]))),
                        sell_stamp_tax_cny=str(cents(gross_fill * Decimal(costs["sell_tax_rate"]))
                            if fill["side"] == "SELL" else Decimal(0)))
                    if sum(map(Decimal, parts.values())) != Decimal(fill["fees_cny"]):
                        raise ValueError("Fee decomposition differs from existing simulator")
                    fill["fee_components"] = parts
                fold.update(same_fills_gross_return=str(gross / initial - 1),
                    same_fills_gross_maximum_drawdown=str(drawdown), same_fills_gross_equity_curve=gross_curve,
                    gross_basis="SAME_EXECUTED_QUANTITIES_BEFORE_FEES_AND_PRICE_SLIPPAGE",
                    net_pnl_cny=str(Decimal(fold["ending_equity_cny"]) - initial))
            scenarios.append(dict(cost_multiplier=multiplier, **result))
        results.append(dict(symbol=item["symbol"], case_binding=item,
            source_available_at=available, strict=strict, scenarios=scenarios))
    code_paths = ["src/value_investment_agent/domain/hotspot/strategy_execution_replay.py",
        "src/value_investment_agent/domain/hotspot/quantitative_validation.py",
        "src/value_investment_agent/domain/hotspot/price_action_plan.py",
        "src/value_investment_agent/domain/hotspot/current_price.py",
        "src/value_investment_agent/domain/execution/exchange_calendar.py",
        "src/value_investment_agent/application/hotspot/strategy_execution_replay.py",
        "src/value_investment_agent/infrastructure/hotspot/statutory_fee_evidence.py",
        "src/value_investment_agent/historical_fees.py"]
    # Imported files belong to the executing checkout, which can differ from
    # the read-only evidence root. Record actual implementation bytes.
    checkout = Path(__file__).resolve().parents[4]
    implementation = [dict(path=p, sha256=sha256((checkout / p).read_bytes()).hexdigest()) for p in code_paths]
    bindings = [manifest_binding, *descriptive["source_bindings"]]
    if pointer_binding:
        bindings.append(pointer_binding)
    for binding in bindings:
        _bound_bytes(root, binding)
    base = [s for row in results for s in row["scenarios"] if s["cost_multiplier"] == "1"]
    summary = dict(security_count=len(results),
        signal_event_count=descriptive["signal_event_count"],
        mature_signal_observation_count=descriptive["mature_five_session_count"],
        right_censored_signal_observations=descriptive["right_censored_count"],
        assumed_state_closed_trade_count=sum(s["trade_count"] for s in base),
        strict_closed_trade_count=sum(r["strict"]["trade_count"] for r in results),
        assumed_state_open_positions=sum(s["right_censored_positions"] for s in base),
        assumed_state_right_censored_intentions=sum(s["right_censored_intentions"] for s in base),
        generated_signal_event_count=sum(s["signal_event_count"] for s in base),
        counts_scope="ISOLATED_SECURITY_AND_PARTITION_COUNTS_NOT_INDEPENDENT_STRATEGY_SAMPLES",
        aggregate_portfolio_return=None)
    if summary["generated_signal_event_count"] != summary["signal_event_count"]:
        raise ValueError("Rule-derived signal count differs from retained descriptive baseline")
    report = dict(schema_version="hotspot-strategy-execution-retrospective-v1",
        evaluated_at=now.isoformat(), status="PARTIAL", namespace=manifest["namespace"],
        metrics_scope="RULE_GENERATED_RETROSPECTIVE_EXECUTION_ASSUMPTIONS",
        manifest_binding=manifest_binding, source_bindings=bindings,
        implementation_bindings=implementation,
        historical_protocol_binding=manifest["historical_protocol_binding"],
        parameters=parameters, parameter_fingerprint=fingerprint(parameters),
        costs=costs, cost_fingerprint=fingerprint(costs),
        statutory_fee_evidence=fee_evidence,
        source_fingerprint=fingerprint(bindings), summary=summary, results=results,
        gaps=["CONTEMPORANEOUS_UNIVERSE_SELECTION_AND_SOURCE_PIT_NOT_PROVEN",
            "UNTOUCHED_OOS_NOT_PROVEN_RETROSPECTIVE_PARTITIONS_ONLY",
            "DATED_ST_STOCK_STATUS_IPO_LIMITS_SUSPENSIONS_AND_LIMIT_PRICES_MISSING",
            "PERSONAL_COMMISSION_AND_MINIMUM_UNCONFIRMED_ALL_IN_COST_ASSUMPTION",
            "CORPORATE_ACTIONS_AND_CASH_DISTRIBUTIONS_NOT_RECONCILED",
            "BAR_TURNOVER_IS_EX_POST_CAPACITY_NOT_ORDER_BOOK_OR_QUEUE",
            "NEXT_OPEN_PLUS_ONE_SECOND_AT_OPEN_IS_AN_ASSUMPTION_NOT_OBSERVED_FILL",
            "EXIT_AND_SIZE_EXPERIMENT_NOT_FROZEN_OR_ADMITTED_STRATEGY",
            "NO_REAL_SHADOW_SESSION_CREDIT"],
        strict_pit_admitted=False, strict_oos_admitted=False, prospective_oos_admitted=False,
        strategy_validation="NOT_PROVEN", actual_sample_accepted=False,
        formal_eligibility=False, portfolio_eligibility=None, performance_claim_allowed=False,
        action="no_order")
    report["content_sha256"] = fingerprint(report)
    return report

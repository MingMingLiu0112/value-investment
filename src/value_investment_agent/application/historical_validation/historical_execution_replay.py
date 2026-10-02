"""Reconstruct a frozen historical execution scenario through the shared ledger.

The service does not recompute investment rules. It extracts dated trade
proposals from a hash-pinned research journal, replays them through the shared
``VirtualAccount`` engine on authenticated historical OHLC data, and fails
closed unless the reconstructed execution matches the frozen journal and
scenario result exactly.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Mapping

from ..product.common import load_json_value, require_inside, sha256_file
from ...virtual_account import VirtualAccount, dated_research_fee, replay
from ...infrastructure.evidence.historical_price_correspondence import verify_price_correspondence
from ...infrastructure.evidence.historical_distribution_correspondence import verify_distribution_correspondence


INPUT_SCHEMA = "historical-execution-replay-input-v1"
OUTPUT_SCHEMA = "historical-execution-replay-v1"
ACTION_NO_ORDER = "no_order"
TRADE_STATES = {
    "proposed_entry",
    "proposed_add",
    "proposed_reduce",
    "proposed_exit",
}
ACCEPTED_EXECUTION_CONTRACTS = {
    "moutai-real-execution-input-v1",
    "moutai-real-execution-input-v5",
}
ACCEPTED_RANGE_EXPERIMENTS = {"moutai-historical-range-experiment-v1"}
_JOURNAL_COMPARE_KEYS = (
    "created_order",
    "fill",
    "rejected_order_reason",
    "cash_cny",
    "holding_shares",
    "sellable_shares",
    "receivable_cny",
    "nav_cny",
    "cash_events",
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field} must be SHA-256 hex")
    return text


def _decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} must be a decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def _relative_path(value: object, field: str) -> Path:
    return Path(_required_text(value, field).replace("\\", "/"))


def _binding(root: Path, value: object, label: str) -> tuple[Path, str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} binding is required")
    path = require_inside(root, root / _relative_path(value.get("path"), f"{label}.path"), label)
    expected = _sha256(value.get("sha256"), f"{label}.sha256")
    if not path.is_file():
        raise ValueError(f"{label} does not exist")
    if sha256_file(path) != expected:
        raise ValueError(f"{label} hash mismatch")
    return path, expected, load_json_value(path, label)


def _verify_references(root: Path, value: object) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("execution input references are required")
    for index, reference in enumerate(value):
        if not isinstance(reference, Mapping):
            raise ValueError(f"execution input reference {index} is invalid")
        path = require_inside(
            root,
            root / _relative_path(reference.get("path"), f"reference[{index}].path"),
            f"reference[{index}]",
        )
        expected = _sha256(reference.get("sha256"), f"reference[{index}].sha256")
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"execution input reference {index} hash mismatch")


def _validate_execution_input(value: Mapping[str, Any], *, root: Path, symbol: str) -> None:
    if value.get("contract_version") not in ACCEPTED_EXECUTION_CONTRACTS:
        raise ValueError("execution input contract version is not supported")
    if value.get("input_scope") != "authenticated_historical_OHLC_and_reviewed_cash_distributions":
        raise ValueError("execution input scope mismatch")
    if value.get("symbol") != symbol:
        raise ValueError("execution input symbol mismatch")
    if value.get("decisions") != {}:
        raise ValueError("execution reconstruction requires a no-decision contract")
    if value.get("formal_fair_value") is not None:
        raise ValueError("execution input cannot contain a formal fair value")
    if value.get("valuation_approved") is not False or value.get("trade_approved") is not False:
        raise ValueError("execution input cannot authorize valuation or trading")
    sessions = value.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("execution input sessions are required")
    dates = []
    for index, session in enumerate(sessions):
        if not isinstance(session, Mapping):
            raise ValueError(f"execution input session {index} is invalid")
        dates.append(_required_text(session.get("date"), f"session[{index}].date"))
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("execution input sessions must be unique and chronological")
    if not isinstance(value.get("cash_events"), list):
        raise ValueError("execution input cash_events are required")
    _verify_references(root, value.get("references"))


def _validate_range_sources(
    *,
    symbol: str,
    scenario: str,
    range_config: Mapping[str, Any],
    range_result: Mapping[str, Any],
    range_manifest: Mapping[str, Any],
    range_result_hash: str,
    range_journal_hash: str,
    range_journal_filename: str,
    range_journal: object,
    sessions: list[Any],
) -> Mapping[str, Any]:
    if range_config.get("version") not in ACCEPTED_RANGE_EXPERIMENTS:
        raise ValueError("range configuration version is not supported")
    if not isinstance(range_config.get("execution"), str) or not range_config["execution"].strip():
        raise ValueError("range configuration execution assumption is required")
    if not isinstance(range_config.get("fee"), str) or not range_config["fee"].strip():
        raise ValueError("range configuration fee assumption is required")

    if range_result.get("symbol") != symbol:
        raise ValueError("range result symbol mismatch")
    if range_result.get("run_type") != "historical_research_range_sensitivity":
        raise ValueError("range result scope mismatch")
    if range_result.get("validation_classification") != "NOT_PIT_SAFE":
        raise ValueError("range result must remain NOT_PIT_SAFE")
    if range_result.get("validation_admission_status") != "NOT_ADMITTED":
        raise ValueError("range result must remain NOT_ADMITTED")
    if range_result.get("approved_value_model_sessions") != 0:
        raise ValueError("range result cannot claim approved valuation sessions")
    if range_result.get("formal_fair_value") is not None:
        raise ValueError("range result cannot contain a formal fair value")
    for field in (
        "valuation_approved",
        "strategy_backtest_complete",
        "simulation_eligible",
        "trade_approved",
        "live_eligible",
    ):
        if range_result.get(field) is not False:
            raise ValueError(f"range result {field} must be false")

    results = range_result.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("range result scenarios are required")
    matches = [row for row in results if isinstance(row, Mapping) and row.get("scenario") == scenario]
    if len(matches) != 1:
        raise ValueError("range result scenario is missing or duplicated")
    scenario_result = matches[0]

    outputs = range_manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ValueError("range manifest outputs are required")
    if outputs.get("result.json") != range_result_hash:
        raise ValueError("range manifest result hash mismatch")
    if outputs.get(range_journal_filename) != range_journal_hash:
        raise ValueError("range manifest journal hash mismatch")

    if not isinstance(range_journal, list) or not range_journal:
        raise ValueError("range journal must be a nonempty list")
    if len(range_journal) != len(sessions):
        raise ValueError("range journal and execution sessions differ in length")
    for index, (row, session) in enumerate(zip(range_journal, sessions)):
        if not isinstance(row, Mapping) or not isinstance(session, Mapping):
            raise ValueError(f"range journal row {index} is invalid")
        if row.get("date") != session.get("date"):
            raise ValueError("range journal and execution session dates differ")
    return scenario_result


def _extract_decisions(
    range_journal: list[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    decisions: dict[str, dict[str, Any]] = {}
    schedule: list[dict[str, Any]] = []
    for index, row in enumerate(range_journal):
        decision = row.get("decision_details")
        if not isinstance(decision, Mapping):
            raise ValueError(f"range journal row {index} decision_details is invalid")
        state = decision.get("state")
        created_order = row.get("created_order")
        if state not in TRADE_STATES:
            if created_order is not None:
                raise ValueError("range journal contains an order without a trade proposal")
            continue
        if not isinstance(created_order, Mapping):
            raise ValueError("trade proposal is missing its frozen created order")
        decision_id = _required_text(decision.get("decision_id"), "decision_id")
        if created_order.get("order_id") != decision_id:
            raise ValueError("trade proposal order_id mismatch")
        session_date = _required_text(row.get("date"), "range journal date")
        if row.get("pending_order_id") not in (None, decision_id):
            raise ValueError("trade proposal pending_order_id mismatch")
        if session_date in decisions:
            raise ValueError("only one trade proposal per session is supported")
        normalized: dict[str, Any] = {"state": state, "decision_id": decision_id}
        if "quantity" in decision:
            normalized["quantity"] = decision["quantity"]
        if "execution_terms" in decision:
            normalized["execution_terms"] = deepcopy(decision["execution_terms"])
        decisions[session_date] = normalized
        schedule.append({
            "decision_date": session_date,
            "state": state,
            "action": decision.get("action"),
            "decision_id": decision_id,
            "requested_quantity": normalized.get("quantity"),
            "side": created_order.get("side"),
            "recorded_context": {
                "close_cny": row.get("close"),
                "value_cny": decision.get("value_cny"),
                "safety_margin": decision.get("safety_margin"),
                "holding_shares": row.get("holding_shares"),
                "nav_cny": row.get("nav_cny"),
                "sizing": deepcopy(decision.get("sizing")),
            },
        })
    if not decisions:
        raise ValueError("frozen range journal contains no trade proposals")
    return decisions, schedule


def _maximum_drawdown(journal: list[Mapping[str, Any]]) -> Decimal:
    if not journal:
        raise ValueError("execution journal is empty")
    navs = [_decimal(row.get("nav_cny"), "nav_cny") for row in journal]
    peak = navs[0]
    maximum = Decimal("0")
    for nav in navs:
        peak = max(peak, nav)
        maximum = min(maximum, (nav - peak) / peak)
    return maximum


def _decision_outcomes(
    schedule: list[dict[str, Any]], journal: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Link execution to its original proposal, never infer an investment thesis."""
    outcomes = []
    for proposal in schedule:
        identity = proposal["decision_id"]
        fills = [row["fill"] for row in journal
                 if isinstance(row.get("fill"), Mapping)
                 and row["fill"].get("order_id") == identity]
        if len(fills) > 1:
            raise ValueError("multiple fills for one frozen proposal are unsupported")
        rejected = [row for row in journal if row.get("rejected_order_reason")
                    and isinstance(row.get("rejected_order"), Mapping)
                    and row["rejected_order"].get("order_id") == identity]
        fill = fills[0] if fills else None
        outcomes.append({
            **proposal,
            "execution_status": "FILLED" if fill else "REJECTED" if rejected else "UNRESOLVED",
            "fill": deepcopy(fill),
            "rejections": [{"date": row["date"], "reason": row["rejected_order_reason"]}
                           for row in rejected],
            "deferred_dates": [row["date"] for row in journal
                               if row.get("deferred_order_id") == identity],
            "investment_rationale_status": "NOT_RECONSTRUCTED",
        })
    return outcomes


def _decision_explanation_bundle(
    outcomes: list[dict[str, Any]], config: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe frozen mechanics; recorded endpoints are not intrinsic-value approval."""
    cards = []
    entry = None
    for outcome in outcomes:
        context = outcome.get("recorded_context", {})
        for field in ("close_cny", "value_cny", "safety_margin", "nav_cny"):
            if context.get(field) is not None:
                _decimal(context[field], f"recorded context {field}")
        sizing = context.get("sizing")
        if sizing is not None and not isinstance(sizing, Mapping):
            raise ValueError("recorded sizing must be an object")
        card = {
            "decision_id": outcome["decision_id"],
            "decision_date": outcome["decision_date"],
            "state": outcome["state"],
            "context": deepcopy(context),
            "execution_status": outcome["execution_status"],
            "fill": deepcopy(outcome["fill"]),
            "linked_entry_id": entry["decision_id"] if entry else None,
            "original_value_cny": entry.get("recorded_context", {}).get("value_cny") if entry else None,
            "thesis_consistency": "NOT_ASSESSABLE",
        }
        cards.append(card)
        if outcome["state"] == "proposed_entry" and outcome["execution_status"] == "FILLED":
            entry = outcome
        elif outcome["state"] == "proposed_exit" and outcome["execution_status"] == "FILLED":
            entry = None
    return {
        "schema_version": "frozen-decision-explanations-v1",
        "scope": "RECORDED_EXPERIMENT_MECHANICS_ONLY",
        "action": ACTION_NO_ORDER,
        "rules_registered_at": config.get("registered_at"),
        "recorded_rules": {key: config.get(key) for key in ("entry", "exit", "sizing")},
        "thesis_consistency": "NOT_ASSESSABLE",
        "missing_research": ["EntryThesisSnapshot", "dated business thesis", "dated counter evidence", "thesis breaker review"],
        "cards": cards,
    }


def _summary(
    *,
    journal: list[Mapping[str, Any]],
    account: VirtualAccount,
    initial_cash: Decimal,
) -> dict[str, Any]:
    fills = [row["fill"] for row in journal if row.get("fill") is not None]
    rejected = [row for row in journal if row.get("rejected_order_reason") is not None]
    ending_nav = account.marked_nav()
    return {
        "opening_nav_cny": str(initial_cash),
        "ending_nav_cny": str(ending_nav),
        "gross_research_return": str((ending_nav / initial_cash) - 1),
        "maximum_drawdown": str(_maximum_drawdown(journal)),
        "fills": len(fills),
        "rejected_orders": len(rejected),
        "ending_shares": account.shares,
        "first_fill_date": fills[0]["filled_on"] if fills else None,
        "last_fill_date": fills[-1]["filled_on"] if fills else None,
    }


def _period_summary(
    journal: list[Mapping[str, Any]],
    scenario_result: Mapping[str, Any],
    initial_cash: Decimal,
) -> list[dict[str, Any]]:
    periods = scenario_result.get("periods")
    if not isinstance(periods, list) or not periods:
        raise ValueError("scenario result periods are required")
    summaries = []
    for index, period in enumerate(periods):
        if not isinstance(period, Mapping):
            raise ValueError(f"scenario period {index} is invalid")
        start = _required_text(period.get("start"), f"period[{index}].start")
        end = _required_text(period.get("end"), f"period[{index}].end")
        if start > end:
            raise ValueError("scenario period dates are invalid")
        positions = [position for position, row in enumerate(journal) if start <= row["date"] <= end]
        if not positions:
            raise ValueError(f"execution journal is missing scenario period {period.get('period')}")
        first = positions[0]
        segment = [journal[position] for position in positions]
        opening = initial_cash if first == 0 else _decimal(journal[first - 1].get("nav_cny"), "previous nav")
        navs = [opening, *[_decimal(row.get("nav_cny"), "nav_cny") for row in segment]]
        peak = navs[0]
        maximum = Decimal("0")
        for nav in navs:
            peak = max(peak, nav)
            maximum = min(maximum, (nav - peak) / peak)
        fills = [row["fill"] for row in segment if row.get("fill") is not None]
        summaries.append({
            "period": period.get("period"),
            "start": start,
            "end": end,
            "sessions": len(segment),
            "opening_nav_cny": str(opening),
            "ending_nav_cny": str(navs[-1]),
            "gross_research_return": str((navs[-1] / opening) - 1),
            "maximum_drawdown": str(maximum),
            "fills": len(fills),
            "rejected_orders": sum(row.get("rejected_order_reason") is not None for row in segment),
        })
    return summaries


def _canonical_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _compare_frozen_journal(
    reconstructed: list[Mapping[str, Any]],
    frozen: list[Mapping[str, Any]],
) -> int:
    compared = 0
    for actual, expected in zip(reconstructed, frozen):
        for key in _JOURNAL_COMPARE_KEYS:
            if _canonical_value(actual.get(key)) != _canonical_value(expected.get(key)):
                date = expected.get("date")
                raise ValueError(f"frozen journal execution mismatch on {date}: {key}")
        compared += 1
    return compared


def _compare_scenario_metrics(
    *,
    summary: Mapping[str, Any],
    periods: list[Mapping[str, Any]],
    scenario_result: Mapping[str, Any],
) -> None:
    decimal_fields = (
        "opening_nav_cny",
        "ending_nav_cny",
        "gross_research_return",
        "maximum_drawdown",
    )
    integer_fields = ("fills", "rejected_orders", "ending_shares")
    optional_text_fields = ("first_fill_date", "last_fill_date")
    for field in decimal_fields:
        if _decimal(summary[field], f"summary.{field}") != _decimal(
            scenario_result.get(field), f"scenario.{field}"
        ):
            raise ValueError(f"scenario result mismatch: {field}")
    for field in integer_fields:
        if summary[field] != scenario_result.get(field):
            raise ValueError(f"scenario result mismatch: {field}")
    for field in optional_text_fields:
        if summary[field] != scenario_result.get(field):
            raise ValueError(f"scenario result mismatch: {field}")

    expected_periods = scenario_result.get("periods")
    if not isinstance(expected_periods, list) or len(periods) != len(expected_periods):
        raise ValueError("scenario result period count mismatch")
    for actual, expected in zip(periods, expected_periods):
        if (
            actual["period"] != expected.get("period")
            or actual["start"] != expected.get("start")
            or actual["end"] != expected.get("end")
        ):
            raise ValueError("scenario result period identity mismatch")
        if actual["sessions"] != expected.get("sessions"):
            raise ValueError("scenario result period sessions mismatch")
        for field in (
            "opening_nav_cny",
            "ending_nav_cny",
            "gross_research_return",
            "maximum_drawdown",
        ):
            if _decimal(actual[field], f"period.{field}") != _decimal(
                expected.get(field), f"scenario period.{field}"
            ):
                raise ValueError(f"scenario result period mismatch: {field}")
        for field in ("fills", "rejected_orders"):
            if actual[field] != expected.get(field):
                raise ValueError(f"scenario result period mismatch: {field}")


def build_historical_execution_replay(
    *,
    root: Path,
    input_path: Path,
    input_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build a normalized execution reconstruction from a hash-pinned recipe."""
    input_path = require_inside(root, input_path, "historical execution replay input")
    expected_input_sha = _sha256(input_sha256, "input_sha256")
    if not input_path.is_file() or sha256_file(input_path) != expected_input_sha:
        raise ValueError("historical execution replay input hash mismatch")
    recipe = load_json_value(input_path, "historical execution replay input")
    if not isinstance(recipe, Mapping):
        raise ValueError("historical execution replay input must be an object")
    if recipe.get("schema_version") != INPUT_SCHEMA or recipe.get("action") != ACTION_NO_ORDER:
        raise ValueError("historical execution replay input schema mismatch")
    symbol = _required_text(recipe.get("symbol"), "symbol")
    if len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("symbol must contain exactly six digits")
    scenario = _required_text(recipe.get("scenario"), "scenario")
    initial_cash = _decimal(recipe.get("initial_cash_cny"), "initial_cash_cny")
    if initial_cash < 0:
        raise ValueError("initial_cash_cny must be nonnegative")

    execution_path, execution_hash, execution_input = _binding(
        root, recipe.get("execution_input"), "execution input"
    )
    config_path, config_hash, range_config = _binding(
        root, recipe.get("range_config"), "range config"
    )
    result_path, result_hash, range_result = _binding(
        root, recipe.get("range_result"), "range result"
    )
    manifest_path, manifest_hash, range_manifest = _binding(
        root, recipe.get("range_manifest"), "range manifest"
    )
    journal_path, journal_hash, range_journal = _binding(
        root, recipe.get("range_journal"), "range journal"
    )
    for label, value in (
        ("execution input", execution_input),
        ("range config", range_config),
        ("range result", range_result),
        ("range manifest", range_manifest),
    ):
        if not isinstance(value, Mapping):
            raise ValueError(f"{label} must be a JSON object")
    if not isinstance(range_journal, list):
        raise ValueError("range journal must be a JSON list")
    journal_binding = recipe.get("range_journal")
    journal_filename = _required_text(
        journal_binding.get("filename") if isinstance(journal_binding, Mapping) else None,
        "range_journal.filename",
    )
    if journal_path.name != journal_filename:
        raise ValueError("range_journal.filename does not match bound path")
    _validate_execution_input(execution_input, root=root, symbol=symbol)
    price_correspondence = verify_price_correspondence(root=root, symbol=symbol,
        sessions=execution_input['sessions'], references=execution_input['references'])
    distribution_correspondence = verify_distribution_correspondence(
        root=root, symbol=symbol, sessions=execution_input["sessions"],
        cash_events=execution_input["cash_events"], references=execution_input["references"],
    )
    scenario_result = _validate_range_sources(
        symbol=symbol,
        scenario=scenario,
        range_config=range_config,
        range_result=range_result,
        range_manifest=range_manifest,
        range_result_hash=result_hash,
        range_journal_hash=journal_hash,
        range_journal_filename=journal_filename,
        range_journal=range_journal,
        sessions=execution_input["sessions"],
    )
    if _decimal(scenario_result.get("opening_nav_cny"), "scenario opening_nav_cny") != initial_cash:
        raise ValueError("initial_cash_cny does not match frozen scenario opening NAV")

    decisions, decision_schedule = _extract_decisions(range_journal)
    account, reconstructed_journal = replay(
        execution_input["sessions"],
        decisions,
        account=VirtualAccount(cash=initial_cash),
        cash_events=execution_input["cash_events"],
        fee_calculator=dated_research_fee,
    )
    session_count = _compare_frozen_journal(reconstructed_journal, range_journal)
    summary = _summary(journal=reconstructed_journal, account=account, initial_cash=initial_cash)
    periods = _period_summary(reconstructed_journal, scenario_result, initial_cash)
    _compare_scenario_metrics(summary=summary, periods=periods, scenario_result=scenario_result)

    execution_events = []
    for row in reconstructed_journal:
        if (
            row.get("created_order") is not None
            or row.get("fill") is not None
            or row.get("rejected_order_reason") is not None
            or row.get("cash_events")
        ):
            execution_events.append({
                "date": row["date"],
                "decision": row.get("decision"),
                "created_order": row.get("created_order"),
                "fill": row.get("fill"),
                "rejected_order_reason": row.get("rejected_order_reason"),
                "cash_cny": row.get("cash_cny"),
                "holding_shares": row.get("holding_shares"),
                "nav_cny": row.get("nav_cny"),
                "cash_events": row.get("cash_events", []),
            })

    decision_outcomes = _decision_outcomes(decision_schedule, reconstructed_journal)
    payload = {
        "schema_version": OUTPUT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "scenario": scenario,
        "company_name": recipe.get("company_name"),
        "action": ACTION_NO_ORDER,
        "engineering_delivery": "DELIVERED",
        "current_research_admission": "NOT_READY",
        "source_scope": "FROZEN_HISTORICAL_RANGE_JOURNAL_RECONSTRUCTED_ON_AUTHENTICATED_OHLC",
        "decision_source": "FROZEN_RANGE_JOURNAL",
        "execution_engine": "shared_virtual_account_replay",
        "fee_engine": "dated_research_fee",
        "execution_assumption": range_config["execution"],
        "fee_assumption": range_config["fee"],
        "decision_rule_recomputed": False,
        "mechanical_reproduction_verified": True,
        "historical_execution_validated": False,
        "strict_pit_admitted": False,
        "investment_rule_validated": False,
        "performance_claim_allowed": False,
        "validation_classification": "NOT_PIT_SAFE",
        "validation_admission_status": "NOT_ADMITTED",
        "initial_cash_cny": str(initial_cash),
        "summary": summary,
        "period_summary": periods,
        "decision_schedule": decision_schedule,
        "decision_outcomes": decision_outcomes,
        "decision_explanations": _decision_explanation_bundle(decision_outcomes, range_config),
        "price_source_correspondence": price_correspondence,
        "distribution_source_correspondence": distribution_correspondence,
        "execution_events": execution_events,
        "comparison": {
            "frozen_journal": {
                "status": "MATCH",
                "rows_compared": session_count,
                "trade_proposals_compared": len(decisions),
                "fills_compared": summary["fills"],
                "rejections_compared": summary["rejected_orders"],
            },
            "range_result": {
                "status": "MATCH",
                "scenario": scenario,
                "summary_metrics_compared": [
                    "opening_nav_cny",
                    "ending_nav_cny",
                    "gross_research_return",
                    "maximum_drawdown",
                    "fills",
                    "rejected_orders",
                    "ending_shares",
                    "first_fill_date",
                    "last_fill_date",
                ],
                "periods_compared": len(periods),
            },
        },
        "limitations": [
            "The frozen journal only supplies dated decisions; this service does not recompute or approve the investment rule.",
            "Daily OHLC data do not prove order-book, queue, suspension, price-limit or liquidity execution.",
            "The scenario remains NOT_PIT_SAFE and NOT_ADMITTED.",
            "Gross research returns exclude dividend tax and an aligned total-return benchmark.",
            "Exact mechanical reproduction is an engineering check, not a performance claim.",
        ],
        "source_bindings": [
            {"role": "execution_input", "path": str(execution_path.relative_to(root)), "sha256": execution_hash},
            {"role": "range_config", "path": str(config_path.relative_to(root)), "sha256": config_hash},
            {"role": "range_result", "path": str(result_path.relative_to(root)), "sha256": result_hash},
            {"role": "range_manifest", "path": str(manifest_path.relative_to(root)), "sha256": manifest_hash},
            {"role": "range_journal", "path": str(journal_path.relative_to(root)), "sha256": journal_hash},
            *[
                {"role": f"execution_original_{index:03d}",
                 "path": reference["path"].replace("\\", "/"),
                 "sha256": reference["sha256"]}
                for index, reference in enumerate(execution_input["references"])
            ],
        ],
        "recipe_sha256": expected_input_sha,
    }
    return payload, reconstructed_journal

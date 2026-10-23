"""Independent evidence audit using existing selection and execution engines.

This report is not a signed gate assessment or a replacement admission policy.
It computes what retained sources can establish without backdating availability.
"""
from collections import Counter
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from .candidate_selection import select_current_hotspot_candidates
from .event_replay import _bound_bytes
from .strategy_execution_replay import build_strategy_execution_replay, fingerprint
from ...domain.hotspot.price_action_plan import RULE_VERSION as SIGNAL_RULE_VERSION

VERSION = "hotspot-independent-evidence-validation-v1"
STRUCTURE_POINTER = "config/current-hotspot-structure-validation.json"
REQUIRED_ADMISSION_CHECKS = frozenset({
    "CURRENT_SOURCE_REPLAY", "HISTORICAL_SOURCE_PIT", "PREDECLARED_UNTOUCHED_OOS",
    "HISTORICAL_UNIVERSE_CLASSIFICATION", "STRICT_TRADABILITY_EXECUTION",
    "COST_ARITHMETIC_AND_SENSITIVITY", "EXECUTABLE_COST_BASIS",
    "WALK_FORWARD_STABILITY", "CORPORATE_ACTION_COMPARABILITY", "REAL_SHADOW",
})


def verify_strategy_admission_sources(*, root: Path, documents: list[dict],
                                      symbol: str, rule_version: str,
                                      cutoff: datetime) -> dict:
    """Recompute a bound audit; signed summaries cannot supply missing proof.

    V1 retained inputs cannot establish WFO or strategy-scoped real Shadow.
    Those checks therefore remain unproven. Supporting future evidence requires
    a versioned verifier, not adding true fields to a signed source document.
    """
    audits = [row for row in documents if isinstance(row, dict)
              and row.get("schema_version") == VERSION]
    if len(audits) != 1:
        raise ValueError("Strategy PASS requires one machine-replayable validation audit")
    claimed = audits[0]
    stamp = _clock(claimed.get("evaluated_at"))
    if stamp > cutoff:
        raise ValueError("Strategy validation audit unavailable at review")
    replayed = validate_current_hotspot_strategy(root=root, now=stamp)
    if fingerprint(claimed) != fingerprint(replayed):
        raise ValueError("Strategy audit differs from independently recomputed evidence")
    current = replayed.get("current_scope") or {}
    if (symbol not in current.get("symbols", []) or current.get("data_status") != "CURRENT"
            or current.get("signal_rule_version") != rule_version
            or replayed.get("sample_comparison", {}).get("applies_to_current_strategy") is not True):
        raise ValueError("Strategy audit does not cover the current security and rule")
    checks = {row["check"]: row["status"] for row in replayed["checks"]}
    missing = sorted(name for name in REQUIRED_ADMISSION_CHECKS if checks.get(name) != "PASS")
    if missing:
        raise ValueError("Strategy evidence remains unproven: " + ",".join(missing))
    if any(replayed.get(name) is not True for name in
           ("strict_pit_admitted", "strict_oos_admitted", "actual_sample_accepted")):
        raise ValueError("Recomputed strategy admission is not proven")
    return replayed


def _check(name, status, reason, evidence=None):
    if status not in {"PASS", "FAIL", "INSUFFICIENT_DATA", "NOT_ASSESSED"}:
        raise ValueError("Unknown independent validation status")
    return dict(check=name, status=status, reason=reason, evidence=evidence or {})


def _clock(value):
    if not isinstance(value, str):
        raise ValueError("Evidence timestamp requires ISO text")
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("Evidence timestamps require timezones")
    return result


def _current_scope(root, now):
    current = select_current_hotspot_candidates(root=root, now=now, limit=30)
    if current.get("status") != "RESEARCH_SELECTION_REPLAYED":
        raise ValueError("Current watch pool failed source revalidation")
    return dict(trade_date=current["trade_date"], data_status=current["data_status"],
        symbols=[r["symbol"] for r in current["items"]], coverage=current["coverage"],
        activity_rule_version=current["activity_rule_version"],
        signal_rule_version=SIGNAL_RULE_VERSION,
        structure_rule_version=current["structure_rule_version"],
        source_bindings=current["source_bindings"], registry_binding=current["registry_binding"],
        watch_binding=current["source_bindings"][0])


def _historical_structure(root, now, current):
    raw = (root / STRUCTURE_POINTER).read_bytes()
    pointer_binding = dict(path=STRUCTURE_POINTER,
                           sha256=sha256(raw).hexdigest())
    pointer = json.loads(raw)
    if (pointer.get("schema_version") != "current-hotspot-structure-validation-v1"
            or pointer.get("action") != "no_order"):
        raise ValueError("Invalid historical structure pointer")
    manifest_binding = dict(path=pointer["manifest_path"], sha256=pointer["manifest_sha256"])
    manifest = json.loads(_bound_bytes(root, manifest_binding))
    output = manifest["outputs"]["validation.json"]
    validation = json.loads(_bound_bytes(root, output))
    if (manifest.get("action") != "no_order" or validation.get("action") != "no_order"
            or _clock(validation["evaluated_at"]) > now):
        raise ValueError("Historical structure evidence context unavailable")
    selection = manifest["source_files"]["selection_report"]
    same = bool(current and selection == current["watch_binding"]
                and validation["selection_trade_date"] == current["trade_date"]
                and validation["rule_version"] == current["activity_rule_version"]
                and validation.get("structure_rule_version") == current["structure_rule_version"])
    return dict(pointer_binding=pointer_binding, manifest_binding=manifest_binding,
        validation_binding=output, selection_binding=selection,
        selection_trade_date=validation["selection_trade_date"],
        activity_rule_version=validation["rule_version"],
        replayed_activity_rule_version=validation["replayed_rule_version"],
        structure_rule_version=validation.get("structure_rule_version"),
        matches_current_scope=same,
        integrity_scope="MANIFEST_AND_VALIDATION_BYTES_NOT_REPLAY_OF_OLD_RUNTIME_SOURCES")


def _execution_evidence(root, now):
    replay = build_strategy_execution_replay(root=root, now=now)
    manifest = json.loads(_bound_bytes(root, replay["manifest_binding"]))
    source_root = (root / replay["manifest_binding"]["path"]).parent / "sources"
    spec = json.loads(_bound_bytes(source_root, manifest["historical_protocol_binding"]))
    registration = _clock(spec["registered_at"])
    if registration > now or replay["action"] != "no_order":
        raise ValueError("Execution evidence unavailable")
    lanes, samples, late, decisions, strict_rejections = [], [], 0, 0, Counter()
    for row in replay["results"]:
        acquired = _clock(row["source_available_at"])
        if acquired > now:
            raise ValueError("Execution source unavailable")
        samples.append(dict(symbol=row["symbol"], case_binding=row["case_binding"],
            source_available_at=row["source_available_at"],
            dated_stock_state_binding=None,
            state_scope="STRICT_REJECTS_MISSING_STATES_ASSUMED_LANE_IS_NOT_OBSERVED_TRADABILITY"))
        for fold in row["strict"]["folds"]:
            strict_rejections.update(fold["rejection_counts"])
            for intention in fold["generated_intentions"]:
                decisions += 1
                late += int(acquired > _clock(intention["decision_at"]))
        for scenario in row["scenarios"]:
            for fold in scenario["folds"]:
                fee_parts = sum((sum(map(Decimal, f["fee_components"].values()))
                                 for f in fold["fills"]), Decimal(0))
                if (fee_parts != Decimal(fold["total_fees_cny"])
                        or Decimal(fold["same_fills_gross_return"]) < Decimal(fold["net_return"])):
                    raise ValueError("Replayed fees fail arithmetic reconciliation")
                lanes.append(dict(symbol=row["symbol"], partition=fold["fold"],
                    cost_multiplier=scenario["cost_multiplier"], trade_count=fold["trade_count"],
                    net_return=fold["net_return"],
                    same_fills_gross_return=fold["same_fills_gross_return"],
                    maximum_drawdown=fold["maximum_drawdown"],
                    total_fees_cny=fold["total_fees_cny"],
                    total_slippage_cny=fold["total_slippage_cny"],
                    right_censored_positions=fold["right_censored_positions"],
                    rejection_counts=fold["rejection_counts"]))
    return dict(summary=replay["summary"], symbols=[r["symbol"] for r in replay["results"]],
        source_bindings=replay["source_bindings"],
        implementation_bindings=replay["implementation_bindings"],
        replay_content_sha256=replay["content_sha256"],
        protocol=dict(registered_at=spec["registered_at"], selection_scope=spec["selection_scope"],
            rule_version=spec["rule_version"],
            start_date=spec["start_date"], development_end=spec["development_end"],
            validation_start=spec["validation_start"], end_date=spec["end_date"],
            registered_before_validation=registration <= _clock(spec["validation_start"] + "T00:00:00+08:00")),
        sample_bindings=samples,
        decision_availability=dict(intention_count=decisions, source_acquired_after_decision=late,
            basis="ACTUAL_ARCHIVED_ACQUISITION_NOT_HYPOTHETICAL_BAR_CLOSE"),
        strict_rejection_counts=dict(strict_rejections),
        parameters=replay["parameters"], parameter_fingerprint=replay["parameter_fingerprint"],
        costs=replay["costs"], cost_fingerprint=replay["cost_fingerprint"],
        costed_partitions=lanes,
        metrics_scope="ISOLATED_SECURITY_PARTITION_ASSUMED_STATE_NOT_PORTFOLIO_OR_OOS_RETURN")


def validate_current_hotspot_strategy(*, root: Path, now: datetime) -> dict:
    """Read-only evidence computation; failures never grant admission or sessions."""
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Timezone-aware validation cutoff required")
    root = Path(root).resolve()
    checks, current, historical, execution = [], None, None, None
    errors = (OSError, ValueError, KeyError, TypeError, ArithmeticError)
    try:
        current = _current_scope(root, now)
        checks.append(_check("CURRENT_SOURCE_REPLAY", "PASS", "Pool original integrity replayed; data_status separately controls freshness", current))
    except errors:
        checks.append(_check("CURRENT_SOURCE_REPLAY", "FAIL", "Current source binding or replay rejected"))
    try:
        historical = _historical_structure(root, now, current)
        checks.append(_check("OLD_STRUCTURE_APPLICABILITY", "PASS" if historical["matches_current_scope"] else "FAIL",
            "Exact current selection and rules required; old VERIFIED is not current admission", historical))
    except errors:
        checks.append(_check("OLD_STRUCTURE_APPLICABILITY", "FAIL", "Old structure bytes or cutoff rejected"))
    try:
        execution = _execution_evidence(root, now)
        availability = execution["decision_availability"]
        protocol = execution["protocol"]
        checks.extend([
            _check("RETAINED_EXECUTION_REPLAY", "PASS", "Existing rule, exits and simulator rerun from verified originals"),
            _check("HISTORICAL_SOURCE_PIT", "FAIL" if availability["source_acquired_after_decision"] else "INSUFFICIENT_DATA",
                "Strict archived PIT not established: actual acquisition follows historical decisions; no claim that public prices were unknowable", availability),
            _check("PREDECLARED_UNTOUCHED_OOS", "FAIL" if not protocol["registered_before_validation"] else "INSUFFICIENT_DATA",
                "Retrospective fixed five conditional cases do not establish unbiased OOS", protocol),
            _check("HISTORICAL_UNIVERSE_CLASSIFICATION", "INSUFFICIENT_DATA",
                "No contemporaneous all-market selection and classification chain for these historical triggers"),
            _check("STRICT_TRADABILITY_EXECUTION", "INSUFFICIENT_DATA",
                "Strict replay rejects missing dated suspension, ST/IPO and price-limit state",
                dict(closed_trades=execution["summary"]["strict_closed_trade_count"],
                     rejection_counts=execution["strict_rejection_counts"])),
            _check("COST_ARITHMETIC_AND_SENSITIVITY", "PASS",
                "0x/1x/2x cost scenarios recomputed; fee components reconcile, not a profitability verdict",
                dict(cost_fingerprint=execution["cost_fingerprint"], partitions=len(execution["costed_partitions"]))),
            _check("EXECUTABLE_COST_BASIS", "INSUFFICIENT_DATA",
                "All-in commission, slippage and next-open fill remain assumptions; transfer-fee reference requires recheck"),
        ])
    except errors:
        checks.append(_check("RETAINED_EXECUTION_REPLAY", "FAIL", "Retained source or numeric replay rejected"))
        for name in ("HISTORICAL_SOURCE_PIT", "PREDECLARED_UNTOUCHED_OOS", "HISTORICAL_UNIVERSE_CLASSIFICATION",
                     "STRICT_TRADABILITY_EXECUTION", "COST_ARITHMETIC_AND_SENSITIVITY", "EXECUTABLE_COST_BASIS"):
            checks.append(_check(name, "NOT_ASSESSED", "Execution dependencies rejected"))
    checks.extend([
        _check("WALK_FORWARD_STABILITY", "NOT_ASSESSED", "Two retrospective partitions are not rolling untouched walk-forward folds"),
        _check("CORPORATE_ACTION_COMPARABILITY", "INSUFFICIENT_DATA", "Corporate actions and cash distributions not reconciled"),
        _check("REAL_SHADOW", "NOT_ASSESSED", "No natural-time session ledger inspected; replay grants zero session credit",
               dict(session_credit_from_this_report=0, required_real_sessions=20)),
        _check("SIGNED_INDEPENDENT_ADMISSION", "NOT_ASSESSED", "Use existing independent_admission verifier; this report creates no signature or gate release"),
    ])
    overlap = sorted(set(current["symbols"]) & set(execution["symbols"])) if current and execution else []
    report = dict(schema_version=VERSION, evaluated_at=now.isoformat(), checks=checks,
        current_scope=current, historical_structure=historical, execution=execution,
        sample_comparison=dict(overlapping_symbols=overlap,
            applies_to_current_strategy=False,
            reason="Identity overlap alone does not bind date, selection, multi-period rule or executable exit policy"),
        status="NOT_ADMITTED", strategy_validation="NOT_PROVEN",
        signed_gate_assessment=False, actual_sample_accepted=False,
        strict_pit_admitted=False, strict_oos_admitted=False,
        elapsed_real_shadow_sessions=None, session_credit_from_this_report=0,
        formal_eligibility=False, portfolio_eligibility=False, trade_eligible=False,
        performance_claim_allowed=False, action="no_order")
    report["validator_binding"] = dict(
        path="src/value_investment_agent/application/hotspot/independent_validation.py",
        sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    report["content_sha256"] = fingerprint(report)
    return report

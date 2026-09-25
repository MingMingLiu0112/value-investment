#!/usr/bin/env python3
"""Build the first 600519 historical-validation admission receipt.

This is an evidence census, not a strategy backtest.  It binds the existing
pre-registered window and blocker map to the new PIT admission contract, then
produces an explicit NOT_PIT_SAFE result when any decision-critical dimension
cannot be proven.  It never reads a live quote, database or broker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.historical_validation import (  # noqa: E402
    ACTION_NO_ORDER,
    NOT_PIT_SAFE,
    PIT_UNSUPPORTED,
    RULE_RETROSPECTIVE,
    SURVIVORSHIP_UNRESOLVED,
    ExecutionContract,
    EvidenceReference,
    HistoricalValidationAdmission,
    PitAssessment,
)


POLICY = ROOT / "config" / "historical-validation-policy-v1.json"
REGISTRATION = (
    ROOT
    / "runtime"
    / "strategy-validation"
    / "moutai-historical-window-registration-20260918T121703Z"
    / "evidence.json"
)
BLOCKER_MAP = (
    ROOT
    / "runtime"
    / "strategy-validation"
    / "moutai-historical-window-blocker-map-20260918T123111Z"
    / "evidence.json"
)
BENCHMARK = (
    ROOT
    / "runtime"
    / "strategy-validation"
    / "moutai-historical-window-benchmark-20260918T123302Z"
    / "evidence.json"
)
FULL_ADMISSION_POINTER = (
    ROOT
    / "runtime"
    / "strategy-validation"
    / "moutai-historical-admission-latest.json"
)
RANGE_POINTER = (
    ROOT
    / "runtime"
    / "strategy-validation"
    / "moutai-historical-range-experiment-latest.json"
)
CONDITIONAL_REPLAY_POINTER = (
    ROOT
    / "runtime"
    / "strategy-validation"
    / "moutai-historical-conditional-replay-latest.json"
)
M3_PIT_POINTER = (
    ROOT / "runtime" / "m3-strict-pit-evidence-audit-latest.json"
)
CASH_DISTRIBUTIONS = ROOT / "docs" / "reviewed-cash-distributions.json"
DAILY_INPUTS = (
    ROOT
    / "runtime"
    / "strategy-validation"
    / "moutai-daily-research-inputs-20260909T161900156334Z"
    / "daily-inputs.json"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _relative(root: Path, path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Evidence escapes project root: {path}")
    return resolved.relative_to(root.resolve()).as_posix()


def _pointer_target(root: Path, pointer_path: Path, filename: str) -> Path:
    pointer = _load_json(pointer_path)
    relative = str(pointer.get("path", "")).replace("\\", "/")
    target_dir = (root / relative).resolve()
    if not target_dir.is_relative_to(root.resolve()):
        raise ValueError(f"Pointer escapes project root: {pointer_path}")
    target = target_dir / filename
    if not target.is_file():
        raise FileNotFoundError(target)
    expected = str(pointer.get("sha256", "")).lower()
    if digest(target) != expected:
        raise ValueError(f"Pinned artifact hash changed: {target}")
    return target


def _evidence(
    root: Path,
    evidence_id: str,
    kind: str,
    path: Path,
    *,
    available_at: str | None = None,
    source_url: str | None = None,
) -> EvidenceReference:
    if not path.is_file():
        raise FileNotFoundError(path)
    return EvidenceReference(
        evidence_id=evidence_id,
        kind=kind,
        path=_relative(root, path),
        sha256=digest(path),
        available_at=available_at,
        source_url=source_url,
    )


def build_admission(root: Path = ROOT) -> tuple[HistoricalValidationAdmission, dict[str, Any]]:
    root = root.resolve()
    policy = _load_json(root / POLICY.relative_to(ROOT))
    registration = _load_json(root / REGISTRATION.relative_to(ROOT))
    blocker_map = _load_json(root / BLOCKER_MAP.relative_to(ROOT))
    benchmark = _load_json(root / BENCHMARK.relative_to(ROOT))
    full_admission = _load_json(
        _pointer_target(root, root / FULL_ADMISSION_POINTER.relative_to(ROOT), "evidence.json")
    )
    range_result = _load_json(
        _pointer_target(root, root / RANGE_POINTER.relative_to(ROOT), "result.json")
    )
    conditional_replay = _load_json(
        _pointer_target(
            root,
            root / CONDITIONAL_REPLAY_POINTER.relative_to(ROOT),
            "summary.json",
        )
    )

    if policy.get("action") != ACTION_NO_ORDER:
        raise ValueError("Historical validation policy must remain action=no_order")
    if registration.get("symbol") != "600519" or blocker_map.get("symbol") != "600519":
        raise ValueError("Unexpected first-case symbol")
    window = registration.get("window") or {}
    if (window.get("start"), window.get("end")) != ("2015-01-05", "2015-01-30"):
        raise ValueError("Unexpected preregistered window")
    if full_admission.get("historical_value", {}).get("approved_sessions") != 0:
        raise ValueError("The approved-value boundary changed; require a new root admission review")
    if range_result.get("strategy_backtest_complete") is not False:
        raise ValueError("The historical experiment must not be promoted to a completed backtest")
    if range_result.get("simulation_eligible") is not False:
        raise ValueError("The historical experiment must not be simulation eligible")

    evidence: list[EvidenceReference] = []

    def add(
        evidence_id: str,
        kind: str,
        path: Path,
        *,
        available_at: str | None = None,
        source_url: str | None = None,
    ) -> str:
        item = _evidence(
            root,
            evidence_id,
            kind,
            path,
            available_at=available_at,
            source_url=source_url,
        )
        evidence.append(item)
        return evidence_id

    policy_id = add("policy", "policy", root / POLICY.relative_to(ROOT))
    registration_id = add(
        "window_registration", "preregistration", root / REGISTRATION.relative_to(ROOT)
    )
    blocker_id = add("blocker_map", "admission_audit", root / BLOCKER_MAP.relative_to(ROOT))
    benchmark_id = add("benchmark_contract", "benchmark", root / BENCHMARK.relative_to(ROOT))
    full_id = add(
        "full_history_admission",
        "historical_admission",
        _pointer_target(root, root / FULL_ADMISSION_POINTER.relative_to(ROOT), "evidence.json"),
    )
    range_id = add(
        "range_experiment",
        "retrospective_experiment",
        _pointer_target(root, root / RANGE_POINTER.relative_to(ROOT), "result.json"),
    )
    conditional_id = add(
        "conditional_replay",
        "retrospective_policy_replay",
        _pointer_target(
            root,
            root / CONDITIONAL_REPLAY_POINTER.relative_to(ROOT),
            "summary.json",
        ),
    )
    cash_id = add("reviewed_cash_actions", "corporate_action_registry", root / CASH_DISTRIBUTIONS.relative_to(ROOT))
    daily_id = add("daily_research_inputs", "historical_input_packet", root / DAILY_INPUTS.relative_to(ROOT))
    fee_id = add(
        "historical_fee_policy",
        "execution_policy",
        root / "docs" / "historical-trading-fees.md",
    )
    corporate_id = add(
        "historical_corporate_action_policy",
        "execution_policy",
        root / "docs" / "historical-corporate-actions.md",
    )
    dividend_tax_id = add(
        "historical_dividend_tax_policy",
        "tax_policy",
        root / "docs" / "historical-dividend-tax.md",
    )
    price_id = add(
        "historical_price_crosscheck",
        "quote_audit",
        root / "docs" / "historical-price-crosscheck.md",
    )
    virtual_account_id = add(
        "virtual_account_execution",
        "execution_implementation",
        root / "src" / "value_investment_agent" / "virtual_account.py",
    )
    contract_id = add(
        "historical_validation_contract",
        "domain_contract",
        root / "src" / "value_investment_agent" / "historical_validation.py",
    )
    builder_id = add(
        "admission_builder",
        "implementation",
        root / "scripts" / "build_moutai_historical_validation_admission.py",
    )

    m3_pointer = root / M3_PIT_POINTER.relative_to(ROOT)
    m3_id: str | None = None
    if m3_pointer.is_file():
        m3_target = _pointer_target(root, m3_pointer, "receipt.json")
        m3_id = add("m3_strict_pit_audit", "strict_pit_audit", m3_target)

    blocker_messages = tuple(
        sorted(
            {
                str(item.get("blocker"))
                for item in blocker_map.get("blocker_mapping", [])
                if item.get("blocker")
            }
            | {
                "approved_historical_value_model_sessions=0",
                "historical_quote_revision_not_pit_proven",
                "historical_fee_contract_unavailable_for_window",
                "historical_execution_and_liquidity_not_pit_proven",
                "historical_benchmark_revision_and_alignment_not_pit_proven",
                "historical_universe_selection_and_survivorship_not_controlled",
                "historical_corporate_action_tax_and_equity_bridge_incomplete",
            }
        )
    )

    facts = PitAssessment(
        PIT_UNSUPPORTED,
        "The model-required historical facts remain incomplete; the blocker map is authoritative.",
        evidence_refs=(registration_id, blocker_id, daily_id),
        blockers=("prior_annual_operating_nwc_incomplete", "cash_tax_scope_incomplete"),
    )
    assumptions = PitAssessment(
        PIT_UNSUPPORTED,
        "No approved historical assumption set exists for this window.",
        evidence_refs=(registration_id, blocker_id, conditional_id),
        blockers=("historical_assumption_set_not_approved",),
    )
    valuation = PitAssessment(
        PIT_UNSUPPORTED,
        "All 2,674 reviewed sessions have zero approved historical value-model sessions.",
        evidence_refs=(full_id, range_id, conditional_id, contract_id),
        blockers=("historical_valuation_not_approved", "approved_value_model_sessions=0"),
    )
    quote = PitAssessment(
        PIT_UNSUPPORTED,
        "The retained historical prices are research inputs fetched later; revision/version PIT is not proven.",
        evidence_refs=(price_id, daily_id),
        blockers=("historical_quote_revision_not_pit_proven",),
    )
    corporate_actions = PitAssessment(
        PIT_UNSUPPORTED,
        "Reviewed gross distributions exist, but investor tax, equity recognition and share-denominator treatment are incomplete.",
        evidence_refs=(cash_id, corporate_id, dividend_tax_id),
        blockers=(
            "historical_corporate_action_tax_and_equity_bridge_incomplete",
            "historical_share_denominator_not_approved",
        ),
    )
    fees = PitAssessment(
        PIT_UNSUPPORTED,
        "The registered 2015-01 window precedes the project's supported early-SSE fee contract and has no full broker invoice basis.",
        evidence_refs=(fee_id, virtual_account_id),
        blockers=("historical_fee_contract_unavailable_for_window",),
    )
    portfolio = PitAssessment(
        PIT_UNSUPPORTED,
        "No frozen, approved historical portfolio context is attached to this window; a synthetic cash account is not a personal portfolio.",
        evidence_refs=(registration_id, virtual_account_id),
        blockers=("historical_portfolio_context_not_frozen",),
    )
    benchmark = PitAssessment(
        PIT_UNSUPPORTED,
        "The archived official total-return levels cover the dates, but historical revision/version and return-convention alignment are not proven.",
        evidence_refs=(benchmark_id,),
        blockers=("historical_benchmark_revision_and_alignment_not_pit_proven",),
    )
    universe = PitAssessment(
        PIT_UNSUPPORTED,
        "The case is a single post-hoc selected security; no PIT universe or selection rule is proven.",
        evidence_refs=(registration_id, blocker_id),
        blockers=("historical_universe_selection_and_survivorship_not_controlled",),
    )
    execution = ExecutionContract(
        signal_to_fill="next_session_open",
        settlement="T+1",
        board_lot=100,
        cash_policy="cash-only, no leverage or shorting; dated fees are applied before fill",
        suspension_policy="absent or stale stock sessions must block the fill",
        price_limit_policy="missing or invalid daily price limits block the fill",
        liquidity_policy="daily bars are a research assumption without order-book or capacity proof",
        corporate_action_policy="record-date entitlement; ex-date and payment-date separate; bonuses locked until listing; no double count",
        fee_policy="dated statutory components plus a declared commission scenario; early-SSE fee basis remains unsupported",
        status=PIT_UNSUPPORTED,
        evidence_refs=(virtual_account_id, fee_id, corporate_id),
        blockers=("historical_execution_and_liquidity_not_pit_proven",),
    )

    rule_version = str(
        conditional_replay.get("rule_version")
        or "moutai-historical-conditional-dcf-v2-shared-cost-only"
    )
    rule_evidence = (conditional_id, range_id)
    if m3_id is not None:
        rule_evidence = (*rule_evidence, m3_id)

    admission = HistoricalValidationAdmission(
        admission_id="600519-historical-validation-admission-v1",
        symbol="600519",
        scope="single_security_historical_validation",
        window_start=str(window["start"]),
        window_end=str(window["end"]),
        information_cutoff_policy=(
            "decision_at=session close; every fact, filing, quote, assumption and rule "
            "must have available_at <= decision_at"
        ),
        rule_version=rule_version,
        rule_registration_status=RULE_RETROSPECTIVE,
        rule_evidence_refs=rule_evidence,
        facts_pit=facts,
        assumptions_pit=assumptions,
        valuation_pit=valuation,
        quote_pit=quote,
        corporate_actions_pit=corporate_actions,
        fees_pit=fees,
        execution_contract=execution,
        portfolio_context=portfolio,
        benchmark_contract=benchmark,
        universe_pit=universe,
        survivorship_status=SURVIVORSHIP_UNRESOLVED,
        approved_value_model_sessions=0,
        blockers=blocker_messages,
        evidence_refs=tuple(evidence),
        action=ACTION_NO_ORDER,
    )
    if admission.classification != NOT_PIT_SAFE:
        raise ValueError("The current first case must fail closed as NOT_PIT_SAFE")
    manifest = _input_manifest(admission, policy_id, builder_id)
    return admission, manifest


def _input_manifest(
    admission: HistoricalValidationAdmission,
    policy_id: str,
    builder_id: str,
) -> dict[str, Any]:
    files = [ref.as_dict() for ref in admission.evidence_refs]
    canonical = json.dumps(
        {
            "admission_id": admission.admission_id,
            "action": admission.action,
            "files": files,
            "policy_evidence_id": policy_id,
            "builder_evidence_id": builder_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": "historical-validation-input-manifest-v1",
        "admission_id": admission.admission_id,
        "action": ACTION_NO_ORDER,
        "files": files,
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def _walk_forward_result(admission: HistoricalValidationAdmission, range_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "historical-validation-walk-forward-result-v1",
        "admission_id": admission.admission_id,
        "status": "NOT_RUN",
        "reason": "NOT_PIT_SAFE_ADMISSION",
        "folds": [],
        "performance": {
            "return": None,
            "drawdown": None,
            "benchmark_return": None,
            "strategy_backtest_complete": False,
        },
        "existing_experiment": {
            "path": next(
                ref.path for ref in admission.evidence_refs if ref.evidence_id == "range_experiment"
            ),
            "status": "RETROSPECTIVE_EXPERIMENT_ONLY",
            "strategy_backtest_complete": range_result.get("strategy_backtest_complete"),
            "simulation_eligible": range_result.get("simulation_eligible"),
        },
        "blocked_by": list(admission.blockers),
        "action": ACTION_NO_ORDER,
    }


def _report(admission: HistoricalValidationAdmission, walk_forward: dict[str, Any]) -> str:
    dimensions = (
        ("Facts", admission.facts_pit),
        ("Assumptions", admission.assumptions_pit),
        ("Valuation", admission.valuation_pit),
        ("Quote", admission.quote_pit),
        ("Corporate actions", admission.corporate_actions_pit),
        ("Fees", admission.fees_pit),
        ("Portfolio context", admission.portfolio_context),
        ("Benchmark", admission.benchmark_contract),
        ("Universe", admission.universe_pit),
    )
    lines = [
        "# 600519 Historical Validation Admission",
        "",
        f"Scope: `{admission.window_start}` to `{admission.window_end}`",
        "",
        f"Classification: **{admission.classification}**",
        "",
        f"Admission status: **{admission.admission_status}**",
        "",
        f"Rule version: `{admission.rule_version}`",
        "",
        "| Dimension | Status | Reason |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {name} | `{item.status}` | {item.detail} |" for name, item in dimensions)
    lines.extend(
        [
            f"| Execution contract | `{admission.execution_contract.status}` | {admission.execution_contract.blockers[0] if admission.execution_contract.blockers else 'no blocker'} |",
            "",
            "## What is not claimed",
            "",
            "- This is not a validated strategy backtest.",
            "- This is not a buy, sell or position signal.",
            "- Approved historical value-model sessions are zero.",
            "- A good or bad historical result cannot authorize production use.",
            f"- Walk-forward status: `{walk_forward['status']}` ({walk_forward['reason']}).",
            "",
            "## Next evidence required",
            "",
            "- A contemporaneous, independently dated rule registration before each decision.",
            "- An approved point-in-time historical value model and assumption set.",
            "- Revision-safe quotes, corporate actions, fees, execution and benchmark evidence.",
            "- A PIT universe/selection rule sufficient to control survivorship bias.",
            "",
            "`action=no_order`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = ROOT
    admission, manifest = build_admission(root)
    range_result = _load_json(
        _pointer_target(root, RANGE_POINTER, "result.json")
    )
    walk_forward = _walk_forward_result(admission, range_result)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output_dir or root / "runtime" / f"historical-validation-600519-{stamp}").resolve()
    if not output.is_relative_to(root):
        raise ValueError("Output directory must remain under the project root")
    output.mkdir(parents=True, exist_ok=False)

    admission_path = output / "admission.json"
    admission_path.write_text(
        json.dumps(admission.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path = output / "input-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    walk_path = output / "walk-forward-result.json"
    walk_path.write_text(
        json.dumps(walk_forward, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path = output / "user-report.md"
    report_path.write_text(_report(admission, walk_forward), encoding="utf-8")
    receipt = {
        "schema_version": "historical-validation-machine-receipt-v1",
        "admission_id": admission.admission_id,
        "classification": admission.classification,
        "admission_status": admission.admission_status,
        "walk_forward_status": walk_forward["status"],
        "action": ACTION_NO_ORDER,
        "admission_sha256": digest(admission_path),
        "input_manifest_sha256": digest(manifest_path),
        "walk_forward_result_sha256": digest(walk_path),
        "user_report_sha256": digest(report_path),
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pointer = root / "runtime" / "historical-validation-600519-latest.json"
    pointer.write_text(
        json.dumps(
            {
                "path": _relative(root, output),
                "sha256": digest(receipt_path),
                "classification": admission.classification,
                "admission_status": admission.admission_status,
                "action": ACTION_NO_ORDER,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "classification": admission.classification,
                "admission_status": admission.admission_status,
                "walk_forward_status": walk_forward["status"],
                "strategy_backtest_complete": False,
                "trade_approved": False,
                "action": ACTION_NO_ORDER,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

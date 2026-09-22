#!/usr/bin/env python3
"""Review the frozen three-company sample through one admission protocol."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from value_investment_agent.distribution import (
    CAPACITY_PARTIAL,
    CAPACITY_UNKNOWN,
    DIVIDEND_ORDINARY,
    DIVIDEND_PAID,
    DIVIDEND_SPECIAL,
    HISTORY_PARTIAL,
    HISTORY_UNKNOWN,
    SUSTAINABILITY_UNKNOWN,
    YIELD_CURRENT,
    YIELD_NORMALIZED,
    YIELD_NORMALIZED_SCENARIO,
    YIELD_NOT_READY,
    YIELD_TRAILING_PAID,
    DividendHistory,
    DividendRecord,
    DividendResearchResult,
    DistributionCapacity,
    DividendSustainabilityAssessment,
    DividendYieldSnapshot,
    build_trailing_paid_yield_snapshot,
)
from value_investment_agent.fixed_sample_admission import (
    DECISION_CONTINUE_CONDITIONAL_MODEL,
    DECISION_PAUSE_PRODUCTION_VALUATION,
    DECISION_RESOLVE_MODEL_INPUTS,
    FixedSampleAdmissionPolicy,
    review_fixed_sample,
)
from value_investment_agent.quote_snapshot import QuoteSnapshot


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_POINTER = ROOT / "runtime/excel-mvp-research-cases-latest.json"
VALUATION_POINTERS = {
    "600519": ROOT / "runtime/valuation-results/600519-current-equity-stage-b-latest.json",
    "000333": ROOT / "runtime/valuation-results/000333-fcff-stage-b-latest.json",
    "601088": ROOT / "runtime/valuation-results/601088-cyclical-stage-b-latest.json",
}
DISTRIBUTION_POINTER = (
    ROOT / "runtime/company-research/600519-distribution-capacity-evidence-latest.json"
)
REVIEWED_DISTRIBUTIONS = ROOT / "docs/reviewed-cash-distributions.json"
REVIEWED_DISTRIBUTIONS_SHA256 = "ab15bdef761774593cd0a8ea96effe1cefa51424643673de492366c9c492312f"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pinned(pointer: Path, filename: str = "evidence.json") -> tuple[dict, dict]:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    path = ROOT / str(pin["path"]).replace("\\", "/") / filename
    path = path.resolve()
    if not path.is_relative_to(ROOT.resolve()) or digest(path) != pin["sha256"].lower():
        raise ValueError(f"Pinned evidence changed: {pointer.name}")
    return (
        json.loads(path.read_text(encoding="utf-8")),
        {
            "id": pointer.relative_to(ROOT).as_posix(),
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": pin["sha256"].lower(),
        },
    )


def policies() -> dict[str, FixedSampleAdmissionPolicy]:
    return {
        "600519": FixedSampleAdmissionPolicy(
            profile_id="quality_compounder",
            decision=DECISION_CONTINUE_CONDITIONAL_MODEL,
            decision_reason="保留低置信度条件估值；正式估值、G3 和当前股本动作仍需完成。",
            cash_return_status="PARTIAL",
            cash_return_explanation="已有历史分配、现金覆盖和注册分红比例证据，但完整 DividendSustainability 未完成。",
            admission_evidence=(
                "六位证券代码与公司名称",
                "quality_compounder 经济画像和已注册模型路由",
                "带证据引用的版本化 ResearchCase",
            ),
            required_evidence=(
                "G3 正式估值通过或明确替代模型",
                "2026 母公司可分配现金与子公司回款范围",
                "当前普通股、股本动作与估值日期绑定",
                "正式估值的独立人工批准",
            ),
        ),
        "000333": FixedSampleAdmissionPolicy(
            profile_id="mature_manufacturing",
            decision=DECISION_RESOLVE_MODEL_INPUTS,
            decision_reason="FCFF 路线已注册，但财务事实、股份分母和模型输入未完成；先解决输入合同，不生成情景。",
            cash_return_status="PARTIAL",
            cash_return_explanation="已有历史派息与现金回报候选材料，但派息可持续性未评估。",
            admission_evidence=(
                "六位证券代码与公司名称",
                "mature_manufacturing 经济画像和已注册模型路由",
                "带证据引用的版本化 ResearchCase",
            ),
            required_evidence=(
                "当前 A/H 估值普通股分母，排除库存股",
                "EBIT、现金税、折旧、营运资本、WACC、净债务和非经营资产输入",
                "财务事实来源独立核验",
                "适用性复核或明确的模型替换/停止决定",
            ),
        ),
        "601088": FixedSampleAdmissionPolicy(
            profile_id="cyclical_cash_return",
            decision=DECISION_PAUSE_PRODUCTION_VALUATION,
            decision_reason="周期正常化模型输入多项缺失且外部价格/成本运输口径未对账；暂停生产估值。",
            cash_return_status="PARTIAL",
            cash_return_explanation="已有派息和周期现金回报候选材料，但可持续性和周期分配能力未评估。",
            admission_evidence=(
                "六位证券代码与公司名称",
                "cyclical_cash_return 经济画像和已注册模型路由",
                "带证据引用的版本化 ResearchCase",
            ),
            required_evidence=(
                "正常化经营利润、现金税、维护资本开支、营运资本、折现率、长期增长、资源寿命、归母净现金和普通股",
                "外部煤价与内部成本运输口径对账",
                "独立成本曲线、资源寿命和谷底偿付能力",
                "模型替换或停止研究决定",
            ),
        ),
    }


def _registry_ref(symbol: str) -> dict:
    return {
        "id": f"reviewed-cash-distributions-{symbol}",
        "path": REVIEWED_DISTRIBUTIONS.relative_to(ROOT).as_posix(),
        "sha256": REVIEWED_DISTRIBUTIONS_SHA256,
        "description": "Reviewed gross cash-entitlement registry",
    }


def _moutai_fiscal_lookup(payout_history: list[dict]) -> dict[tuple[Decimal, str], str]:
    lookup: dict[tuple[Decimal, str], str] = {}
    for row in payout_history:
        fiscal_period = f"FY{row['fiscal_year']}"
        ordinary = Decimal(row["ordinary_cash_per_share_cny"])
        special = Decimal(row["special_or_interim_cash_per_share_cny"])
        if ordinary > 0:
            lookup[(ordinary, DIVIDEND_ORDINARY)] = fiscal_period
        if special > 0:
            lookup[(special, DIVIDEND_SPECIAL)] = fiscal_period
    return lookup


def _event_parts(event: dict) -> list[tuple[str, Decimal]]:
    components = event.get("components") or {}
    if components:
        return [
            (dividend_type, Decimal(components[dividend_type]))
            for dividend_type in (DIVIDEND_ORDINARY, DIVIDEND_SPECIAL)
            if Decimal(components.get(dividend_type, "0")) > 0
        ]
    return [(DIVIDEND_ORDINARY, Decimal(event["cash_per_share"]))]


def _dividend_history(
    symbol: str,
    events: list[dict],
    as_of: date,
    *,
    fiscal_lookup: dict[tuple[Decimal, str], str] | None = None,
    extra_evidence: list[dict] | None = None,
) -> DividendHistory:
    records: list[DividendRecord] = []
    blockers: list[str] = []
    if fiscal_lookup is None:
        blockers.append("fiscal_period attribution is not completed")
    blockers.append("proposal and approval dates are not modeled in the reviewed registry")

    for event_index, event in enumerate(events):
        if event.get("symbol") != symbol:
            continue
        payment_date = date.fromisoformat(event["cash_payment_date"])
        if payment_date > as_of:
            continue
        ex_date = date.fromisoformat(event["ex_date"])
        for dividend_type, dps in _event_parts(event):
            if fiscal_lookup is None:
                fiscal_period = (
                    f"unattributed-{payment_date.isoformat()}-"
                    f"{dividend_type}-{event_index}"
                )
            else:
                fiscal_period = fiscal_lookup.get((dps, dividend_type))
                if fiscal_period is None:
                    continue
            refs = []
            for ref_index, ref in enumerate(event.get("evidence", [])):
                item = dict(ref)
                item.setdefault(
                    "id",
                    f"{symbol}-{dividend_type}-{payment_date.isoformat()}-{ref_index}",
                )
                refs.append(item)
            records.append(
                DividendRecord(
                    symbol=symbol,
                    fiscal_period=fiscal_period,
                    dividend_type=dividend_type,
                    status=DIVIDEND_PAID,
                    dividend_per_share=dps,
                    currency="CNY",
                    announcement_date=None,
                    approval_date=None,
                    ex_date=ex_date,
                    payment_date=payment_date,
                    known_at=payment_date,
                    share_basis="ordinary shares",
                    evidence_refs=refs,
                )
            )

    evidence_refs = [_registry_ref(symbol), *(extra_evidence or [])]
    return DividendHistory(
        symbol=symbol,
        records=tuple(records),
        as_of=as_of,
        evidence_refs=evidence_refs,
        status=HISTORY_PARTIAL if records else HISTORY_UNKNOWN,
        blockers=blockers,
    )


def _unknown_capacity(
    symbol: str,
    profile_id: str,
    as_of: date,
    evidence_refs: list[dict],
    blockers: list[str],
) -> DistributionCapacity:
    return DistributionCapacity(
        symbol=symbol,
        profile_id=profile_id,
        as_of=as_of,
        status=CAPACITY_UNKNOWN,
        confidence="UNKNOWN",
        evidence_refs=evidence_refs,
        blockers=blockers,
    )


def _unknown_sustainability(
    symbol: str,
    profile_id: str,
    as_of: date,
    evidence_refs: list[dict],
    blockers: list[str],
    *,
    cycle_risk: str = "not assessed",
    capital_requirements: str = "not registered",
) -> DividendSustainabilityAssessment:
    return DividendSustainabilityAssessment(
        symbol=symbol,
        profile_id=profile_id,
        as_of=as_of,
        status=SUSTAINABILITY_UNKNOWN,
        coverage_context="only historical distribution observations are available",
        capital_requirements=capital_requirements,
        balance_sheet_pressure="not independently assessed",
        cycle_risk=cycle_risk,
        growth_source="not identified",
        breakers=(),
        confidence="UNKNOWN",
        reasons=(),
        blockers=blockers,
        evidence_refs=evidence_refs,
    )


def _quote_snapshot(symbol: str, payload: dict) -> QuoteSnapshot | None:
    bridge_payload = payload.get("price_bridge") or {}
    if bridge_payload.get("bridge_status") != "READY":
        return None
    quote_date = bridge_payload.get("quote_date")
    current_price = bridge_payload.get("current_price")
    if not quote_date or current_price is None:
        return None
    return QuoteSnapshot(
        symbol=symbol,
        quote_date=date.fromisoformat(quote_date),
        current_price=Decimal(current_price),
        status="verified_close",
        evidence_refs=list(bridge_payload.get("quote_evidence_refs", [])),
    )


def distribution_results(
    research_payload: dict,
    valuation_payloads: dict[str, dict],
    as_of: date,
) -> dict[str, DividendResearchResult]:
    distribution_payload, distribution_ref = load_pinned(DISTRIBUTION_POINTER)
    if digest(REVIEWED_DISTRIBUTIONS) != REVIEWED_DISTRIBUTIONS_SHA256:
        raise ValueError("Reviewed cash-distribution registry changed")
    registry = json.loads(REVIEWED_DISTRIBUTIONS.read_text(encoding="utf-8"))
    records = {
        record["case"]["symbol"]: record
        for record in research_payload["records"]
    }
    events = list(registry["events"])

    moutai_history = _dividend_history(
        "600519",
        events,
        as_of,
        fiscal_lookup=_moutai_fiscal_lookup(distribution_payload["payout_history"]),
        extra_evidence=records["600519"]["case"]["evidence_refs"],
    )
    fy2025 = distribution_payload["parent_cash_capacity"]["fy2025"]
    boundary = distribution_payload["financial_subsidiary_boundary"]
    moutai_capacity = DistributionCapacity(
        symbol="600519",
        profile_id="quality_compounder",
        as_of=as_of,
        earnings_basis={"parent_net_profit_cny": Decimal(fy2025["parent_net_profit_cny"])},
        cash_flow_basis={
            "parent_cfo_cny": Decimal(fy2025["parent_cfo_cny"]),
            "subsidiary_investment_income_received_cny": Decimal(
                fy2025["subsidiary_investment_income_received_cny"]
            ),
        },
        maintenance_reinvestment={"parent_capex_cny": Decimal(fy2025["parent_capex_cny"])},
        restricted_cash_or_upstream_constraints={
            "financial_subsidiary_external_deposits_cny": Decimal(
                boundary["external_deposits_cny"]
            ),
            "disclosed_restricted_cash_subset_cny": Decimal(
                boundary["disclosed_restricted_cash_subset_cny"]
            ),
        },
        capital_allocation_context=distribution_payload["model_payout_assumption"],
        status=CAPACITY_PARTIAL,
        confidence="UNKNOWN",
        evidence_refs=[distribution_ref],
        blockers=list(distribution_payload["blockers"]),
    )
    moutai_sustainability = _unknown_sustainability(
        "600519",
        "quality_compounder",
        as_of,
        records["600519"]["case"]["evidence_refs"],
        list(distribution_payload["blockers"]),
        cycle_risk="moderate industry cyclicality; no probability is assigned",
        capital_requirements="registered payout is a bounded historical policy, not a future commitment",
    )

    midea_history = _dividend_history(
        "000333",
        events,
        as_of,
        extra_evidence=records["000333"]["case"]["evidence_refs"],
    )
    midea_capacity = _unknown_capacity(
        "000333",
        "mature_manufacturing",
        as_of,
        records["000333"]["case"]["evidence_refs"],
        ["FCFF and cash-return inputs are not registered"],
    )
    midea_sustainability = _unknown_sustainability(
        "000333",
        "mature_manufacturing",
        as_of,
        records["000333"]["case"]["evidence_refs"],
        ["future distribution and reinvestment balance is not assessed"],
        capital_requirements="industrial FCFF and buyback/dividend capital-allocation inputs are not complete",
    )

    shenhua_history = _dividend_history(
        "601088",
        events,
        as_of,
        extra_evidence=records["601088"]["case"]["evidence_refs"],
    )
    shenhua_capacity = _unknown_capacity(
        "601088",
        "cyclical_cash_return",
        as_of,
        records["601088"]["case"]["evidence_refs"],
        ["normalized cash generation and maintenance capex are not registered"],
    )
    shenhua_sustainability = _unknown_sustainability(
        "601088",
        "cyclical_cash_return",
        as_of,
        records["601088"]["case"]["evidence_refs"],
        ["normalized distribution capacity is not registered"],
        cycle_risk="current coal-cycle profit cannot be projected as a permanent dividend",
        capital_requirements="through-cycle maintenance capex and debt resilience are not independently reconciled",
    )

    yield_snapshots: dict[str, list[DividendYieldSnapshot]] = {}
    moutai_quote = _quote_snapshot("600519", valuation_payloads["600519"])
    if moutai_quote is not None:
        yield_snapshots["600519"] = [
            build_trailing_paid_yield_snapshot(
                history=moutai_history,
                quote=moutai_quote,
                as_of=as_of,
            )
        ]

    shenhua_refs = records["601088"]["case"]["evidence_refs"]
    yield_snapshots["601088"] = [
        DividendYieldSnapshot(
            symbol="601088",
            basis_type=YIELD_TRAILING_PAID,
            dividend_basis_period="not available without a legal quote",
            dividend_per_share=None,
            dividend_known_at=None,
            quote_date=None,
            current_price=None,
            currency="CNY",
            share_basis="ordinary shares",
            dividend_yield=None,
            yield_type=YIELD_CURRENT,
            evidence_refs=shenhua_refs,
            status=YIELD_NOT_READY,
            blockers=["no verified close quote is available"],
        ),
        DividendYieldSnapshot(
            symbol="601088",
            basis_type=YIELD_NORMALIZED_SCENARIO,
            dividend_basis_period="through-cycle normalized scenario",
            dividend_per_share=None,
            dividend_known_at=None,
            quote_date=None,
            current_price=None,
            currency="CNY",
            share_basis="ordinary shares",
            dividend_yield=None,
            yield_type=YIELD_NORMALIZED,
            evidence_refs=shenhua_refs,
            status=YIELD_NOT_READY,
            blockers=["normalized distribution capacity is not registered"],
        ),
    ]

    return {
        "600519": DividendResearchResult(
            symbol="600519",
            profile_id="quality_compounder",
            history=moutai_history,
            capacity=moutai_capacity,
            sustainability=moutai_sustainability,
            yield_snapshots=tuple(yield_snapshots.get("600519", ())),
            as_of=as_of,
        ),
        "000333": DividendResearchResult(
            symbol="000333",
            profile_id="mature_manufacturing",
            history=midea_history,
            capacity=midea_capacity,
            sustainability=midea_sustainability,
            yield_snapshots=(),
            as_of=as_of,
        ),
        "601088": DividendResearchResult(
            symbol="601088",
            profile_id="cyclical_cash_return",
            history=shenhua_history,
            capacity=shenhua_capacity,
            sustainability=shenhua_sustainability,
            yield_snapshots=tuple(yield_snapshots.get("601088", ())),
            as_of=as_of,
        ),
    }


def build_review() -> dict:
    research, research_ref = load_pinned(RESEARCH_POINTER)
    valuation_payloads: dict[str, dict] = {}
    input_refs = [research_ref]
    for symbol, pointer in VALUATION_POINTERS.items():
        payload, ref = load_pinned(pointer)
        valuation_payloads[symbol] = payload
        input_refs.append(ref)

    as_of = date.today()
    review = review_fixed_sample(
        research_records=research["records"],
        valuation_payloads=valuation_payloads,
        policies=policies(),
        as_of=as_of,
        distribution_results=distribution_results(
            research,
            valuation_payloads,
            as_of,
        ),
    )
    return {
        "version": "fixed-sample-admission-review-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_refs": input_refs,
        **review.as_policy(),
    }


def main() -> None:
    payload = build_review()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "runtime" / f"fixed-sample-admission-review-{stamp}"
    output.mkdir(parents=False, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    pointer = ROOT / "runtime/fixed-sample-admission-review-latest.json"
    pointer.write_text(
        json.dumps(
            {
                "path": str(output.relative_to(ROOT)),
                "sha256": manifest["evidence_sha256"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "engineering_orchestration_status": payload["engineering_orchestration_status"],
                "production_valuation_available": payload["production_valuation_available"],
                "trade_approved": False,
                "human_confirmation_required": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

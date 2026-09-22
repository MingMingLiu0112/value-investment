#!/usr/bin/env python3
"""Review the frozen three-company sample through one admission protocol."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from value_investment_agent.fixed_sample_admission import (
    DECISION_CONTINUE_CONDITIONAL_MODEL,
    DECISION_PAUSE_PRODUCTION_VALUATION,
    DECISION_RESOLVE_MODEL_INPUTS,
    FixedSampleAdmissionPolicy,
    review_fixed_sample,
)


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_POINTER = ROOT / "runtime/excel-mvp-research-cases-latest.json"
VALUATION_POINTERS = {
    "600519": ROOT / "runtime/valuation-results/600519-current-equity-stage-b-latest.json",
    "000333": ROOT / "runtime/valuation-results/000333-fcff-stage-b-latest.json",
    "601088": ROOT / "runtime/valuation-results/601088-cyclical-stage-b-latest.json",
}


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


def build_review() -> dict:
    research, research_ref = load_pinned(RESEARCH_POINTER)
    valuation_payloads: dict[str, dict] = {}
    input_refs = [research_ref]
    for symbol, pointer in VALUATION_POINTERS.items():
        payload, ref = load_pinned(pointer)
        valuation_payloads[symbol] = payload
        input_refs.append(ref)

    review = review_fixed_sample(
        research_records=research["records"],
        valuation_payloads=valuation_payloads,
        policies=policies(),
        as_of=date.today(),
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

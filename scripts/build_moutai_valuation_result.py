"""Export the admitted Moutai model as a bounded Stage-B valuation result."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import json
import argparse
from pathlib import Path

from value_investment_agent.valuation_models.base import ValuationResult

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "valuation-results" / "600519-current-equity-stage-b"
POINTER = ROOT / "runtime" / "valuation-results" / "600519-current-equity-stage-b-latest.json"


def pinned(pointer: str) -> tuple[dict, dict[str, str]]:
    ref = json.loads((ROOT / pointer).read_text(encoding="utf-8"))
    path = ROOT / ref["path"] / "evidence.json"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != ref["sha256"]:
        raise ValueError("Pinned source changed: " + pointer)
    return json.loads(path.read_text(encoding="utf-8")), {"id": pointer, "path": str(path.relative_to(ROOT)), "sha256": digest}


def evidence(path: Path, evidence_id: str) -> tuple[dict, dict[str, str]]:
    path = path.resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("Evidence must remain under the project root")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text(encoding="utf-8")), {
        "id": evidence_id, "path": str(path.relative_to(ROOT)), "sha256": digest,
    }


def build(diagnostic_override: Path | None = None, *, model_evidence: Path | None = None,
          admission_evidence: Path | None = None) -> dict:
    historical = model_evidence is not None
    if historical != (admission_evidence is not None):
        raise ValueError("Archived exports require both model and admission evidence")
    if historical:
        model, model_ref = evidence(model_evidence, "archived_moutai_model")
        admission, admission_ref = evidence(admission_evidence, "archived_moutai_admission")
    else:
        model, model_ref = pinned("runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json")
        admission, admission_ref = pinned("runtime/company-research/600519-current-valuation-admission-latest.json")
    diagnostic_path = diagnostic_override or ROOT / "runtime/company-research/600519-current-assumption-diagnostic-20260917T014020Z/evidence.json"
    diagnostic_path = diagnostic_path.resolve()
    if not diagnostic_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Diagnostic must remain under the project root")
    diagnostic_ref = {"id": "moutai_reverse_valuation_20260914", "path": str(diagnostic_path.relative_to(ROOT)),
                      "sha256": hashlib.sha256(diagnostic_path.read_bytes()).hexdigest()}
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    quote_reports = sorted((ROOT / "runtime/quote-sessions").glob("*/report.json"))
    quote_ref = None
    quote_blocker = "没有与估值日期同日、已验证且可用于价格比较的行情桥接"
    if quote_reports:
        latest_quote = quote_reports[-1]
        quote_report = json.loads(latest_quote.read_text(encoding="utf-8"))
        observation = next((row for row in quote_report.get("observations", [])
                            if row.get("symbol") == "600519"), None)
        if observation:
            quote_ref = {"id": "latest_quote_attempt", "path": str(latest_quote.relative_to(ROOT)),
                         "sha256": hashlib.sha256(latest_quote.read_bytes()).hexdigest()}
            state = observation.get("result", {}).get("status", "unknown")
            quote_blocker += f"；最近一次双源尝试为 {state}，不得用于估值比较"
    scenarios = {row["scenario"]: Decimal(row["conditional_value_per_current_disclosed_share_cny"])
                 for row in model["results"]}
    if set(scenarios) != {"bear", "base", "bull"}:
        raise ValueError("Expected Moutai bear/base/bull scenario model")
    if any(row["status"] != "above_registered_envelope" for row in diagnostic["reverse_valuation"]):
        raise ValueError("Reverse valuation diagnostic scope changed")
    current_price = None
    margin_to_bear = None
    margin_to_base = None
    if diagnostic_override:
        model_input = diagnostic.get("inputs", {}).get("model", {})
        if (model_input.get("path") != model_ref["path"]
                or model_input.get("sha256") != model_ref["sha256"]):
            raise ValueError("Diagnostic does not use the current pinned model")
        if diagnostic.get("reviewed_as_of", "")[:10] != model["valuation_at"][:10]:
            raise ValueError("Diagnostic and current model do not share a valuation date")
        current_price = Decimal(diagnostic["quote_price_cny"])
        margin_to_bear = (scenarios["bear"] - current_price) / scenarios["bear"]
        margin_to_base = (scenarios["base"] - current_price) / scenarios["base"]
    result = ValuationResult(
        symbol="600519", model_type="归母权益剩余收益 / 分配能力",
        valuation_date=date.fromisoformat(model["valuation_at"][:10]),
        bear_value=scenarios["bear"], base_value=scenarios["base"], bull_value=scenarios["bull"],
        current_price=current_price, margin_to_bear=margin_to_bear, margin_to_base=margin_to_base, confidence="低",
        assumptions={
            "scope": ("归档同日条件研究；非正式合理价值" if historical
                      else "冻结的当前日期条件研究；非正式合理价值"),
            "profit_anchor_cny": model["profit_anchor_cny"],
            "income_growth_bear_base_bull": ["-5%", "0%", "+5%"],
            "payout_ratio": model["model_policy"]["payout_ratio"],
            "forecast_years": model["model_policy"]["forecast_years"],
            "franchise_fade_years": model["model_policy"]["fade_years"],
            "terminal_growth": model["model_policy"]["terminal_growth"],
            "confidence_rule": "低：优势持续期、可分配现金与折现率均为关键假设；即使有同日价格桥接也不得升级为研究吸引力。",
            "reverse_valuation": {"quote_date": diagnostic["reviewed_as_of"][:10], "quote_price_cny": diagnostic["quote_price_cny"],
                                  "variable": "未来五年利润增长", "registered_range": ["-5%", "+5%"],
                                  "results": diagnostic["reverse_valuation"],
                                  "interpretation": "归档价格在三个优势衰减期限的登记区间之外；这是当日有界解释，不是唯一市场预期，也不是当前价格判断。"},
        },
        sensitivities=[{"name": row["case"], "value_per_share_cny": row["conditional_value_per_current_disclosed_share_cny"]}
                       for row in model["sensitivity"]],
        evidence_refs=[model_ref, admission_ref, diagnostic_ref] + ([quote_ref] if quote_ref else []),
        blockers=([quote_blocker] if current_price is None else [])
                 + (["该归档准入审查未通过：" + "、".join(admission.get("blocking_gate_ids", []))]
                    if admission.get("p1_current_model_admitted") is not True else [])
                 + ["优势持续期、可分配现金与折现率尚未独立验证", "低置信度不得升级为研究吸引力"],
        status="conditional_research_only")
    return {"version": "moutai-stage-b-valuation-result-v1", "result": json.loads(result.to_json()),
            "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
            "live_eligible": False, "interpretation": "场景值用于审查模型假设，不构成合理价、买卖价、订单或实盘准入。"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", type=Path)
    parser.add_argument("--model-evidence", type=Path)
    parser.add_argument("--admission-evidence", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    payload = build(args.diagnostic, model_evidence=args.model_evidence, admission_evidence=args.admission_evidence)
    output = (args.output_dir or OUT).resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError("Output must remain under the project root")
    output.mkdir(parents=True, exist_ok=True)
    target = output / "evidence.json"; target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if args.output_dir is None:
        POINTER.write_text(json.dumps({"path": str(OUT.relative_to(ROOT)), "sha256": digest}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target), "sha256": digest, "status": payload["result"]["status"]}, ensure_ascii=False))

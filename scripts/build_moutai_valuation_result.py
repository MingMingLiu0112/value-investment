"""Export the admitted Moutai model as a bounded Stage-B valuation result."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import json
import argparse
from pathlib import Path

from value_investment_agent.model_validity import ModelValidity
from value_investment_agent.price_bridge import bridge
from value_investment_agent.research_profile import PROFILES
from value_investment_agent.valuation_confidence import ConfidenceEvidence, evaluate_confidence
from value_investment_agent.valuation_models.base import ValuationResult
from value_investment_agent.valuation_models.residual_income import QualityCompounderFacts
from value_investment_agent.valuation_router import ROUTE_SUPPORTED, ValuationRouter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "valuation-results" / "600519-current-equity-stage-b"
POINTER = ROOT / "runtime" / "valuation-results" / "600519-current-equity-stage-b-latest.json"
FALLBACK_DIAGNOSTIC = (
    ROOT / "runtime" / "company-research"
    / "600519-current-assumption-diagnostic-20260917T014020Z" / "evidence.json"
)


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


def normalized_relative(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def resolve_same_date_diagnostic(model: dict, model_ref: dict) -> Path | None:
    """Resolve the newest diagnostic that reuses the currently pinned model."""
    candidates = sorted(
        (ROOT / "runtime" / "company-research").glob(
            "600519-current-assumption-diagnostic-*/evidence.json"
        )
    )
    model_date = str(model.get("valuation_at", ""))[:10]
    for path in reversed(candidates):
        diagnostic = json.loads(path.read_text(encoding="utf-8"))
        model_input = diagnostic.get("inputs", {}).get("model", {})
        if not isinstance(model_input, dict):
            continue
        if (
            normalized_relative(model_input.get("path", ""))
            == normalized_relative(model_ref["path"])
            and model_input.get("sha256") == model_ref["sha256"]
            and str(diagnostic.get("reviewed_as_of", ""))[:10] == model_date
        ):
            return path
    return None


def build(diagnostic_override: Path | None = None, *, model_evidence: Path | None = None,
          admission_evidence: Path | None = None) -> dict:
    route = ValuationRouter().route(PROFILES["quality_compounder"])
    if (route.status != ROUTE_SUPPORTED
            or route.model_type != "residual_income_or_equity_value"
            or route.facts_contract is not QualityCompounderFacts):
        raise ValueError("Quality-compounder profile rejected the Moutai residual-income model")
    historical = model_evidence is not None
    if historical != (admission_evidence is not None):
        raise ValueError("Archived exports require both model and admission evidence")
    if historical:
        model, model_ref = evidence(model_evidence, "archived_moutai_model")
        admission, admission_ref = evidence(admission_evidence, "archived_moutai_admission")
    else:
        model, model_ref = pinned("runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json")
        admission, admission_ref = pinned("runtime/company-research/600519-current-valuation-admission-latest.json")
    if diagnostic_override is not None:
        diagnostic_path = diagnostic_override
        same_date_diagnostic = True
    else:
        diagnostic_path = resolve_same_date_diagnostic(model, model_ref)
        same_date_diagnostic = diagnostic_path is not None
        if diagnostic_path is None:
            diagnostic_path = FALLBACK_DIAGNOSTIC
    diagnostic_path = diagnostic_path.resolve()
    if not diagnostic_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Diagnostic must remain under the project root")
    diagnostic_ref = {"id": "moutai_reverse_valuation_20260914", "path": str(diagnostic_path.relative_to(ROOT)),
                      "sha256": hashlib.sha256(diagnostic_path.read_bytes()).hexdigest()}
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    quote_reports = sorted((ROOT / "runtime/quote-sessions").glob("*/report.json"))
    quote_ref = None
    quote_blocker = "没有与估值日期同日、已验证且可用于价格比较的行情桥接"
    quote_date = None
    current_price = None
    quote_status = "PENDING_EXTERNAL_DATA"
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
    if same_date_diagnostic:
        model_input = diagnostic.get("inputs", {}).get("model", {})
        if (model_input.get("path") != model_ref["path"]
                or model_input.get("sha256") != model_ref["sha256"]):
            raise ValueError("Diagnostic does not use the current pinned model")
        if diagnostic.get("reviewed_as_of", "")[:10] != model["valuation_at"][:10]:
            raise ValueError("Diagnostic and current model do not share a valuation date")
        quote_input = diagnostic.get("inputs", {}).get("quote")
        if not isinstance(quote_input, dict) or not quote_input.get("path") or not quote_input.get("sha256"):
            raise ValueError("Current diagnostic has no hash-addressed quote report")
        current_quote_path = (ROOT / quote_input["path"]).resolve()
        if not current_quote_path.is_relative_to(ROOT.resolve()):
            raise ValueError("Current diagnostic quote must remain under the project root")
        if hashlib.sha256(current_quote_path.read_bytes()).hexdigest() != quote_input["sha256"]:
            raise ValueError("Current diagnostic quote report changed")
        current_quote = json.loads(current_quote_path.read_text(encoding="utf-8"))
        current_observation = next((row for row in current_quote.get("observations", [])
                                    if row.get("symbol") == "600519"), None)
        if current_observation is None:
            raise ValueError("Current diagnostic quote report has no 600519 observation")
        result_state = current_observation.get("result", {})
        if (result_state.get("status") != "matched_close" or result_state.get("passed") is not True
                or result_state.get("expected_session") != model["valuation_at"][:10]
                or str(current_observation.get("observed_price")) != str(diagnostic.get("quote_price_cny"))):
            raise ValueError("Current diagnostic quote is not a same-date matched close")
        quote_date = date.fromisoformat(result_state["expected_session"])
        current_price = Decimal(str(current_observation["observed_price"]))
        quote_status = "verified_close"
        quote_ref = {"id": "current_diagnostic_quote", "path": str(current_quote_path.relative_to(ROOT)),
                      "sha256": quote_input["sha256"]}
        quote_blocker = ""
    confidence_refs = [model_ref, admission_ref, diagnostic_ref]
    if quote_ref is not None:
        confidence_refs.append(quote_ref)
    base_result = next(
        row for row in model["results"]
        if row["income_growth_assumption"] == "0"
    )
    confidence_evidence = ConfidenceEvidence(
        data_completeness=Decimal("1"),
        business_stability="medium",
        parameter_sensitivity="high",
        cyclicality="unknown",
        forecast_horizon_years=model["model_policy"]["forecast_years"]
        + model["model_policy"]["fade_years"],
        terminal_value_share=Decimal(
            str(base_result["terminal_dividend_value_share"])
        ),
        cross_check_disagreement=Decimal("0"),
        evidence_refs=confidence_refs,
    )
    confidence_assessment = evaluate_confidence(confidence_evidence)
    result = ValuationResult(
        symbol="600519", model_type="归母权益剩余收益 / 分配能力",
        valuation_date=date.fromisoformat(model["valuation_at"][:10]),
        bear_value=scenarios["bear"], base_value=scenarios["base"], bull_value=scenarios["bull"],
        confidence=confidence_assessment.confidence,
        assumptions={
            "scope": ("归档同日条件研究；非正式合理价值" if historical
                      else "冻结的当前日期条件研究；非正式合理价值"),
            "profit_anchor_cny": model["profit_anchor_cny"],
            "income_growth_bear_base_bull": ["-5%", "0%", "+5%"],
            "payout_ratio": model["model_policy"]["payout_ratio"],
            "forecast_years": model["model_policy"]["forecast_years"],
            "franchise_fade_years": model["model_policy"]["fade_years"],
            "terminal_growth": model["model_policy"]["terminal_growth"],
            "confidence_rule": "低：关键预测参数敏感度仍为高，行业周期性和未来优势持续期仍不能按经验值认定为低/高；即使有同日价格桥接也不得升级为研究吸引力。",
            "confidence_assessment": confidence_assessment.as_policy(),
            "reverse_valuation": {"quote_date": diagnostic["reviewed_as_of"][:10], "quote_price_cny": diagnostic["quote_price_cny"],
                                  "variable": "未来五年利润增长", "registered_range": ["-5%", "+5%"],
                                  "results": diagnostic["reverse_valuation"],
                                  "interpretation": "归档价格在三个优势衰减期限的登记区间之外；这是当日有界解释，不是唯一市场预期，也不是当前价格判断。"},
        },
        sensitivities=[{"name": row["case"], "value_per_share_cny": row["conditional_value_per_current_disclosed_share_cny"]}
                       for row in model["sensitivity"]],
        evidence_refs=[model_ref, admission_ref, diagnostic_ref] + ([quote_ref] if quote_ref else []),
        blockers=(["该归档准入审查未通过：" + "、".join(admission.get("blocking_gate_ids", []))]
                    if admission.get("p1_current_model_admitted") is not True else [])
                 + ["优势持续期已审计为有界假设，实际持续时长尚未经验证实",
                    "全年2026母公司可分配现金与子公司回款尚未披露",
                    "折现率为有界研究区间，不是未来实际资本成本",
                    "低置信度不得升级为研究吸引力"],
        status="conditional_research_only", model_version=model.get("model_version", "moutai-current-equity-v1"))
    validity = ModelValidity(
        model_id=model_ref["sha256"], symbol="600519", model_as_of=result.valuation_date,
        valid_from=result.valuation_date, last_material_event_check=result.valuation_date,
        financial_statement_changed=False, capital_structure_changed=False, material_event_found=False,
        status="VALID", blockers=[], evidence_refs=[model_ref, admission_ref])
    price_bridge = bridge(result, validity, quote_date=quote_date, current_price=current_price,
                          quote_status=quote_status, evidence_refs=([quote_ref] if quote_ref else []),
                          blockers=[quote_blocker] if quote_blocker else [])
    return {"version": "moutai-stage-b-valuation-result-v2", "result": json.loads(result.to_json()),
            "model_validity": json.loads(validity.to_json()), "price_bridge": json.loads(price_bridge.to_json()),
            "valuation_route": route.as_policy(),
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

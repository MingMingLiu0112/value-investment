"""Display a bound ResearchCase without admitting research or trade gates."""
from dataclasses import replace
import hashlib
import json
from datetime import date

from ...domain.research.research_case import ResearchCase
from .product_workbench import CompanyCard, StatusView


def company_with_historical_gate_read(
    card: CompanyCard, payload: dict, *, expected_sha256: str,
) -> CompanyCard:
    """Project an application assessment, never re-evaluate or admit its gates."""
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("historical gate read binding mismatch")
    if (payload.get("symbol") != card.symbol
            or payload.get("action") != "no_order"
            or payload.get("mode") != "READ_EXISTING_ONLY"
            or payload.get("suggested_state") != "NOT_READY"):
        raise ValueError("historical gate read identity or scope mismatch")
    gate = payload["historical_research_gate"]
    if gate.get("current_admission") is not False:
        raise ValueError("historical gate read cannot admit current research")
    day = date.fromisoformat(gate["research_as_of"])
    if not gate["results"] or any(type(value) is not bool for value in gate["results"].values()):
        raise ValueError("historical gate results must be explicit booleans")
    summary = "\n".join(
        f"{key}：{'原版本通过' if passed else '原版本未通过'}"
        for key, passed in gate["results"].items()
    )
    rows = (
        ("历史研究门评估", f"研究日期 {day}\n{summary}\n{gate['conclusion']}"),
        ("历史评估边界", "仅复核原研究版本，不代表当前事实、商业质量、PIT 或交易准入；当前门禁保持不变。"),
        ("原版本未解决事项", "\n".join(gate["blockers"]) or "没有记录；不代表当前研究已批准。"),
    )
    return replace(card, decision_review=card.decision_review + rows)


def company_with_research_case(
    card: CompanyCard, case: ResearchCase, *, expected_sha256: str,
) -> CompanyCard:
    if not isinstance(case, ResearchCase):
        raise TypeError("research case must be typed")
    if card.symbol != case.symbol or card.company_name != case.name:
        raise ValueError("research case company identity mismatch")
    if hashlib.sha256(case.to_json().encode("utf-8")).hexdigest() != expected_sha256:
        raise ValueError("research case binding mismatch")
    kinds = {"fact": "事实", "interpretation": "解释", "hypothesis": "假设", "gap": "缺口"}

    def statements(items):
        return "\n".join(f"[{kinds[item['kind']]}] {item['text']}" for item in items) or "尚未提供。"

    refs = tuple(ref["id"] for ref in case.evidence_refs)
    summaries = {
        "business_quality": f"研究论点（{case.as_of}）：{case.thesis}\n回报来源：{case.return_driver}\n尚未独立批准商业质量。",
        "financial_quality": statements(case.positives) + "\n正面证据不抵消反证；不代表财务门通过。",
        "risks_counterevidence": "最强反证：\n" + statements(case.counter_evidence) + "\n失效条件（待验证假设）：\n" + statements(case.thesis_breakers),
    }
    rows = (
        ("研究版本与日期", f"{case.research_version} / {case.as_of}"),
        ("核心研究论点（非买入批准）", case.thesis),
        ("预期回报来源", case.return_driver),
        ("市场可能错在哪里（待证）", case.mispricing_hypothesis),
        ("正面证据与解释", statements(case.positives)),
        ("最强反证", statements(case.counter_evidence)),
        ("什么事实会削弱论点", statements(case.thesis_breakers)),
        ("下一步跟踪", statements(case.next_events)),
        ("研究自身限制", "\n".join(case.blockers) or "无已记录限制；不等于完成准入。"),
    )
    return replace(
        card,
        sections=tuple(replace(section, status=StatusView("PARTIAL", "仍在验证"),
                               summary=summaries[section.key], evidence_refs=refs)
                       if section.key in summaries else section for section in card.sections),
        decision_review=card.decision_review + rows,
        evidence_refs=tuple(dict.fromkeys((*card.evidence_refs, *refs))),
    )

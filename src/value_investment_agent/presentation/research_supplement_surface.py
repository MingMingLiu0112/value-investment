"""Project pinned, unadmitted research context without changing decisions."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..application.product.common import load_json_object, require_inside, sha256_file


def project_research_supplements(payload: dict[str, Any], *, root: Path,
        symbol: str, bindings: list[dict[str, str]]) -> list[dict[str, str]]:
    company = next(card for card in payload["companies"] if card["symbol"] == symbol)
    accepted = []
    for binding in bindings:
        role = binding["role"]
        if role not in {"valuation_proposal", "financial_review", "research_supplement_comparison"}:
            continue
        path = require_inside(root / "runtime", root / binding["path"], "research supplement")
        if sha256_file(path) != binding["sha256"]:
            raise ValueError("research supplement hash mismatch")
        data = load_json_object(path, "research supplement")
        if data.get("status") == "RESEARCH_SUPPLEMENT_UNAVAILABLE":
            continue
        if data.get("symbol") != symbol or data.get("action") != "no_order":
            raise ValueError("research supplement identity/scope mismatch")
        sources = data.get("source_bindings")
        if not isinstance(sources, list) or (not sources and role != 'research_supplement_comparison'):
            raise ValueError("research supplement requires source bindings")
        for source in sources:
            source_path = require_inside(root, root / source["path"], "supplement source")
            if sha256_file(source_path) != source["sha256"]:
                raise ValueError("research supplement source drift")
        if role == 'research_supplement_comparison':
            if (data.get('schema_version') != 'research-supplement-comparison-v1'
                    or data.get('current_admission') is not False
                    or data.get('approval_changed') is not False
                    or data.get('decision_changed') is not False
                    or data.get('research_date_advanced') is not False):
                raise ValueError('research comparison admission boundary mismatch')
            labels = {'valuation_proposal':'条件估值研究', 'financial_review':'财务原件研究'}
            states = {'UNCHANGED':'研究字段未变化', 'CHANGED_RESEARCH_ARTIFACT':'研究内容变化，非新增官方披露',
                'UNAVAILABLE':'缺少前后可比研究补充'}
            summary = '\n'.join(f"{labels[key]}：{states[value['status']]}"
                for key, value in data['roles'].items())
            company.setdefault('decision_review', []).append({'label':'本次研究版本比较','value':summary})
        elif role == "valuation_proposal":
            if data.get("schema_version") != "finite-neutral-valuation-proposal-v1" or any(
                data.get(key) is not False for key in ("assumptions_approved", "g3_approved",
                "model_validity_approved", "price_admitted", "research_date_advanced",
                "decision_changed", "canonical_written")) or data.get("position_guidance") is not None:
                raise ValueError("research proposal admission boundary mismatch")
            for choice in data["choices"]:
                values = choice["valuation"]
                if values.get("symbol") != symbol:
                    raise ValueError("research choice symbol mismatch")
                for key in ("bear_value", "base_value", "bull_value"):
                    try:
                        value = Decimal(str(values[key]))
                    except InvalidOperation as error:
                        raise ValueError('research choice has invalid value') from error
                    if not value.is_finite() or value <= 0:
                        raise ValueError("research choice has invalid value")
            summary = (f"新计算保留研究日期 {data['original_research_as_of']}，估值日期 "
                f"{data['original_valuation_date']}。备选数字见本页条件研究表；尚非批准合理价或买点。")
            preference = data.get("research_preference")
            if preference:
                index = next(i for i, choice in enumerate(data['choices'], 1)
                    if choice['id'] == preference['choice_id'])
                summary += (f" 独立研究优先假设：第{index}项备选，"
                    f"置信度：{preference['confidence']}。{preference['reason']} "
                    f"最强反证：{preference['countercase']}。")
                company.setdefault("decision_review", []).append({"label": "研究假设重开条件",
                    "value": "\n".join(preference["reopen_triggers"])})
            company.setdefault("decision_review", []).append({"label": "条件研究备选", "value": summary})
        else:
            if data.get("scope") != "NOT_ADMITTED" or any(data.get(key) is not False
                    for key in ("model_approved", "strict_pit_admitted", "price_admitted")):
                raise ValueError("financial supplement admission boundary mismatch")
            summary = (f"财务期末 {data['financial_period_end']}。新原件核验只作为研究补充，"
                "没有替换当前决策使用的金融事实。" + "；".join(data["limitations"]))
            company.setdefault("decision_review", []).append({"label": "本次财务研究补充", "value": summary})
        evidence_id = f"daily-{role}-{symbol}-{binding['sha256'][:16]}"
        payload["audit"]["evidence"].append({"evidence_id": evidence_id,
            "title": {'valuation_proposal':'条件估值研究补充', 'financial_review':'财务原件核验补充',
                'research_supplement_comparison':'研究版本比较'}[role],
            "artifact_type": "UNADMITTED_RESEARCH_SUPPLEMENT", "path": binding["path"],
            "sha256": binding["sha256"], "available_at": data["generated_at"][:10], "action": "no_order"})
        company["evidence_refs"].append(evidence_id)
        accepted.append(binding)
    return accepted

"""Read-only exact-candidate event impact drafts, not materiality approval."""
from copy import deepcopy
from decimal import Decimal, localcontext


def build_candidate_event_impact(analysis, events):
    candidate = analysis["review_binding"]["candidate_binding"]
    economic = (analysis.get("joint_capital_review") or {}).get("economic_path") or {}
    if economic.get("candidate_binding") != candidate:
        return dict(status="CANDIDATE_ECONOMIC_PATH_UNAVAILABLE", items=[],
            candidate_binding=deepcopy(candidate), action="no_order", materiality_approved=False)
    items = []
    for event in events:
        if (event.get("status") != "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW"
                or event.get("candidate_binding") != candidate
                or event.get("input_descriptor_sha256") != analysis["input_descriptor_sha256"]):
            continue
        for fact in event["facts"]:
            parsed = fact["terms"]
            affected = set(parsed.get("affected_model_fields", []))
            references = []
            for scenario in economic.get("scenarios", []):
                for year in scenario.get("years", []):
                    for step in year.get("steps", []):
                        if step.get("status") != "available":
                            continue
                        for field, value in step.get("values", {}).items():
                            if field in affected:
                                references.append(dict(scenario=scenario["scenario"],
                                    model_year=year["model_year"], field=field, value=value,
                                    classification=step.get("classification"), unit=step.get("unit"),
                                    input_path=f"economic_path.scenarios[{scenario['scenario']}].years[{year['model_year']}].{step['id']}.{field}"))
            kind = parsed.get("event_type")
            calculations = []
            if kind == "OPERATING_PRICE_CHANGE":
                terms = parsed["terms"]
                for key in ("retail_price", "sales_contract_price"):
                    price = terms[key]
                    before, after = Decimal(price["before"]), Decimal(price["after"])
                    if not before.is_finite() or not after.is_finite() or min(before, after) <= 0:
                        raise ValueError("EVENT_PRICE_NONPOSITIVE_OR_NONFINITE")
                    with localcontext() as context:
                        context.prec = 40
                        calculations.append(dict(field=key, before=str(before), after=str(after),
                            absolute_change=str(after-before), relative_change=str(after/before-1),
                            unit=price["unit"], formula="after / before - 1",
                            classification="DERIVED_ANNOUNCEMENT_PRICE_CHANGE_NOT_PROFIT_CHANGE"))
                judgement = "RECALCULATION_REVIEW_REQUIRED"
                rationale = "公告价格发生变化；现有收入与利润路径需核对产品覆盖、销量和渠道。涨价幅度不能直接作为整体收入或利润增幅。"
                missing = ["该产品实际销量及渠道份额", "税基及净收入确认口径", "模型经营年份与生效日期的期间对应", "现有预测是否已包含此次价格调整"]
            elif kind == "INTERNAL_ASSET_TRANSFER_RESOLUTION":
                judgement = "CASH_ACCESS_AND_CAPITAL_REVIEW_REQUIRED"
                rationale = "内部无偿划转不直接创造合并利润，但可能改变母公司资产和资金可达路径；完成日期和金额尚未证实，不能认定零影响。"
                missing = ["划转实施/完成原件及金额", "母公司与子公司收入、成本和资金上划安排", "模型资金可达假设是否仍适用"]
            elif kind == "ACCOUNTING_POLICY_IMPACT_STATEMENT":
                judgement = "ISSUER_NO_MATERIAL_IMPACT_REQUIRES_REVIEW"
                rationale = "发行人的无重大影响表述作为证据保留，不能替代对当前利润、权益和现金口径的独立复核。"
                missing = ["适用金融资产及现金流口径核对", "当前候选是否需要重分类或重算", "精确候选版本的材料性确认"]
            else:
                judgement = "UNSUPPORTED_EVENT_REVIEW"
                rationale = "当前没有受支持的事件到模型判断规则，不能视为无影响。"
                missing = ["受支持的事件经济语义"]
            items.append(dict(announcement_id=event["announcement_id"], title=event["title"],
                event_type=kind, published_at=event["published_at"],
                evidence_binding=deepcopy(fact["binding"]),
                source_url=fact["source_url"], source_available_at=fact["source_available_at"],
                status=judgement, rationale=rationale,
                affected_model_fields=sorted(affected),
                unmapped_model_fields=sorted(affected - {r["field"] for r in references}),
                consumed_model_values=references, derived_price_changes=calculations,
                unresolved_inputs=missing, quantified_profit_effect=None,
                model_inputs_changed=False, model_recalculation_completed=False,
                formal_decision=False, action="no_order"))
    return dict(schema_version="candidate-event-impact-draft-v1",
        status="UNAPPROVED_RESEARCH_DRAFT" if items else "NO_SUPPORTED_EVENT",
        candidate_binding=deepcopy(candidate), input_descriptor_sha256=analysis["input_descriptor_sha256"],
        assumption_binding=deepcopy(economic.get("assumption_binding")),
        period_basis=economic.get("period_basis"), items=items,
        materiality_approved=False, model_validity_granted=False, action="no_order")

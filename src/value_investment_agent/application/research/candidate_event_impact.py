"""Read-only exact-candidate event impact drafts, not materiality approval."""
from copy import deepcopy
from decimal import Decimal, localcontext


def build_candidate_event_impact(analysis, events):
    candidate = analysis["review_binding"]["candidate_binding"]
    economic = (analysis.get("joint_capital_review") or {}).get("economic_path") or {}
    native = analysis.get("source_native_cash_review") or {}
    mapped = economic.get("candidate_binding") == candidate
    native_bound = (native.get("candidate_binding") == candidate
        and (native.get("model_context") or {}).get("input_descriptor_sha256")
        == analysis.get("input_descriptor_sha256")
        and analysis.get("input_descriptor_sha256") is not None)
    if not mapped:
        if not native_bound:
            return dict(status="CANDIDATE_ECONOMIC_PATH_UNAVAILABLE", items=[],
                candidate_binding=deepcopy(candidate), action="no_order", materiality_approved=False)
        # A replayed native cash ledger is bound to the candidate but does not
        # expose comparable quarterly operating fields. Keep the review facts
        # and leave all scenario mappings empty instead of equating FY and YTD.
        economic = {}
    items = []
    for event in events:
        if (event.get("status") != "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW"
                or event.get("candidate_binding") != candidate
                or event.get("input_descriptor_sha256") != analysis["input_descriptor_sha256"]):
            continue
        for fact in event["facts"]:
            parsed = fact["terms"]
            kind = parsed.get("event_type")
            affected = set(parsed.get("affected_model_fields", []))
            reference_fields = affected
            if kind == "REPORTED_BUYBACK_PROGRESS" and "cash" in affected:
                reference_fields = (affected - {"cash"}) | {"opening_cash", "closing_cash"}
            references = []
            for scenario in economic.get("scenarios", []):
                for year in scenario.get("years", []):
                    for step in year.get("steps", []):
                        if step.get("status") != "available":
                            continue
                        for field, value in step.get("values", {}).items():
                            if field in reference_fields:
                                references.append(dict(scenario=scenario["scenario"],
                                    model_year=year["model_year"], field=field, value=value,
                                    classification=step.get("classification"), unit=step.get("unit"),
                                    input_path=f"economic_path.scenarios[{scenario['scenario']}].years[{year['model_year']}].{step['id']}.{field}"))
            mapped_fields = {r["field"] for r in references}
            if kind == "REPORTED_BUYBACK_PROGRESS":
                if mapped_fields & {"opening_cash", "closing_cash"}:
                    mapped_fields.add("cash")
                shares = (analysis.get("consumed_operating_inputs") or {}).get("ordinary_shares")
                if "ordinary_shares" in affected and shares is not None:
                    verified_shares = Decimal(shares)
                    if not verified_shares.is_finite() or verified_shares <= 0 or verified_shares != verified_shares.to_integral_value():
                        raise ValueError("EVENT_IMPACT_CONSUMED_SHARES_INVALID")
                    references.append(dict(field="ordinary_shares", value=str(shares), unit="shares",
                        classification="CANDIDATE_VALUATION_SHARE_BASIS_NOT_CURRENT",
                        input_path="consumed_operating_inputs.ordinary_shares"))
                    mapped_fields.add("ordinary_shares")
            calculations = []
            financial_changes = []
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
            elif kind == "REPORTED_QUARTERLY_FINANCIAL_UPDATE":
                judgement = "RECALCULATION_REVIEW_REQUIRED"
                update = parsed.get("financial_update", {})
                if (update.get("period_basis") == "YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER"
                        and update.get("comparative_start") and update.get("comparative_end")):
                    for name, row in update["fields"].items():
                        current, prior = Decimal(row["value"]), Decimal(row["comparative_value"])
                        if not current.is_finite() or not prior.is_finite():
                            raise ValueError("EVENT_FINANCIAL_AMOUNT_NONFINITE")
                        with localcontext() as arithmetic:
                            arithmetic.prec = 40
                            financial_changes.append(dict(field=name, current=str(current), comparative=str(prior),
                                absolute_change=str(current-prior), relative_change=str(current/prior-1) if prior > 0 else None,
                                scope=row["scope"], unit=row["unit"], physical_page=row["physical_page"],
                                period_start=update["period_start"], period_end=update["period_end"],
                                comparative_start=update["comparative_start"], comparative_end=update["comparative_end"],
                                classification="REPORTED_YTD_COMPARISON_NOT_FORECAST_CHANGE"))
                rationale = "前三季度实际收入和归母利润用于检验原预测，需按同期和经营口径核对后再重算。"
                missing = ["原候选同期间经营基线", "剩余月份及成本税费假设", "候选现金路径的独立复核"]
            elif kind == "REPORTED_BUYBACK_PROGRESS":
                judgement = "BUYBACK_CASH_AND_SHARE_BASIS_REVIEW_REQUIRED"
                rationale = "公告披露的是同一回购计划的累计股数和付款。只将同计划两个截止日的差额用于期间现金核对；实购股数不等于已注销股数。"
                missing = ["估值截止日前同计划累计付款及原模型是否已计入",
                           "报价日前回购增量与实际现金限制",
                           "注销生效文件和报价日精确普通股股数"]
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
                unmapped_model_fields=sorted(affected - mapped_fields),
                consumed_model_values=references, derived_price_changes=calculations,
                derived_financial_changes=financial_changes,
                unresolved_inputs=missing, quantified_profit_effect=None,
                model_inputs_changed=False, model_recalculation_completed=False,
                formal_decision=False, action="no_order"))
    return dict(schema_version="candidate-event-impact-draft-v1",
        status="UNAPPROVED_RESEARCH_DRAFT" if items else "NO_SUPPORTED_EVENT",
        candidate_binding=deepcopy(candidate), input_descriptor_sha256=analysis["input_descriptor_sha256"],
        assumption_binding=deepcopy(economic.get("assumption_binding")),
        period_basis=economic.get("period_basis"), items=items,
        model_field_mapping="JOINT_ECONOMIC_PATH" if mapped else "NATIVE_CASH_LEDGER_NO_COMPARABLE_OPERATING_FIELDS",
        materiality_approved=False, model_validity_granted=False, action="no_order")

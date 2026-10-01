"""Render the pinned historical company closure for human review."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any, Mapping

from .product_workbench import (
    ACTION_NO_ORDER,
    HISTORICAL_REVIEW_KIND,
    HISTORICAL_REVIEW_STATUS_LABELS,
    EvidenceRecord,
    HistoricalReviewCard,
    ProductWorkbenchReadModel,
    StatusView,
)


_RULE_STATUS_TEXT = {
    "RETROSPECTIVE_RESEARCH_EXTENSION": "事后研究扩展规则，不能代表当时已经知悉",
    "CONTEMPORANEOUS_RULE": "当时已登记规则",
}

_BLOCKER_TEXT = {
    "relative_pe_research_only_not_intrinsic_valuation": "相对PE只用于研究参考，不代表公司内在价值。",
    "retrospective_rule_not_contemporaneous": "规则是在事后补充登记，不能冒充当时已经运行的决策规则。",
    "historical_range_not_pit_safe": "历史区间没有通过严格时点审查，区间结果只能作为工程诊断。",
    "current_price_bridge_not_admitted": "当前价格与估值基准尚未通过一致性审查，不能形成安全边际结论。",
    "valuation_approved_false": "估值尚未获得正式批准。",
    "no_human_research_approval": "尚未完成人工研究批准。",
    "positive_price_review_not_eligible": "当前不允许形成正向价格吸引力结论。",
    "no_order": "系统永远不生成交易订单，最终决定由用户完成。",
}

_DELIVERY_TEXT = {
    "DELIVERED": "已交付",
    "NOT_DELIVERED": "未交付",
}

_ADMISSION_TEXT = {
    "NOT_READY": "尚无交易准入",
    "CONDITIONAL": "有条件研究",
    "ADMITTED": "已准入",
}

_CLASSIFICATION_TEXT = {
    "NOT_PIT_SAFE": "未通过严格时点审查",
    "STRICT_CONTEMPORANEOUS_REPLAY": "当时规则严格时点回放",
}

_DECISION_STATUS_TEXT = {
    "WAIT": "等待",
    "NOT_READY": "尚未就绪",
    "no_decision": "无决策",
    "proposed_entry": "研究性拟入场",
    "paper_hold": "研究性持有",
    "proposed_exit": "研究性拟退出",
    "watch": "观察",
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_CLOSURE_BLOCKERS = {
    "relative_pe_research_only_not_intrinsic_valuation",
    "retrospective_rule_not_contemporaneous",
    "historical_range_not_pit_safe",
    "current_price_bridge_not_admitted",
    "no_order",
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _required_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _decimal_value(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception as error:  # noqa: BLE001 - fail closed on any malformed decimal
        raise ValueError(f"{field} must be a decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def _historical_status(code: object, labels: dict[str, str], field: str) -> StatusView:
    text = _required_text(code, field).upper()
    if text not in labels:
        raise ValueError(f"{field} is not supported: {text}")
    return StatusView(code=text, user_label=labels[text])


def _validate_historical_closure_for_product(
    closure: Mapping[str, Any],
    *,
    model_as_of: date,
) -> dict[str, Any]:
    payload = _required_mapping(closure, "historical closure")
    if payload.get("schema_version") != "historical-company-closure-v1":
        raise ValueError("unsupported historical closure schema")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("historical closure must remain no_order")
    symbol = _required_text(payload.get("symbol"), "historical closure symbol")
    if not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("historical closure symbol must contain six digits")
    company_name = _required_text(payload.get("company_name"), "historical closure company name")
    if payload.get("engineering_delivery") != "DELIVERED":
        raise ValueError("historical closure engineering delivery must be DELIVERED")
    if payload.get("current_research_admission") != "NOT_READY":
        raise ValueError("historical closure cannot promote current research admission")
    for key in (
        "strict_pit_admitted",
        "historical_execution_validated",
        "performance_claim_allowed",
        "price_review_eligible",
    ):
        if payload.get(key) is not False:
            raise ValueError(f"historical closure {key} must be false")
    generated_at = datetime.fromisoformat(
        _required_text(payload.get("generated_at"), "historical closure generated_at")
    )
    if generated_at.utcoffset() is None:
        raise ValueError("historical closure generated_at must be timezone-aware")
    if generated_at.date() > model_as_of:
        raise ValueError("historical closure was generated after the product as_of date")

    m3 = _required_mapping(payload.get("m3_replay"), "historical closure m3_replay")
    m3_symbols: list[str] = []
    if "symbol" in m3:
        m3_symbols.append(_required_text(m3.get("symbol"), "m3 symbol"))
    facts = m3.get("then_known_facts")
    if isinstance(facts, Mapping) and "symbol" in facts:
        m3_symbols.append(_required_text(facts.get("symbol"), "m3 then_known_facts symbol"))
    quote = _required_mapping(m3.get("then_known_quote"), "m3 then_known_quote")
    if "symbol" in quote:
        m3_symbols.append(_required_text(quote.get("symbol"), "m3 then_known_quote symbol"))
    if not m3_symbols or any(item != symbol for item in m3_symbols):
        raise ValueError("historical closure m3 symbol mismatch")
    replay_date = date.fromisoformat(_required_text(m3.get("replay_date"), "m3 replay_date"))
    final_decision = _required_text(m3.get("final_decision"), "m3 final_decision").upper()
    if final_decision not in HISTORICAL_REVIEW_STATUS_LABELS["replay_final_decision"]:
        raise ValueError(f"unsupported m3 final decision: {final_decision}")
    quote_date = date.fromisoformat(_required_text(quote.get("quote_date"), "m3 quote_date"))
    if quote_date > replay_date:
        raise ValueError("historical closure quote is after its replay date")
    rule = _required_mapping(m3.get("rule"), "m3 rule")
    rule_registration = _required_text(
        rule.get("rule_registration_status"), "m3 rule_registration_status"
    ).upper()
    if rule_registration not in HISTORICAL_REVIEW_STATUS_LABELS["rule_registration"]:
        raise ValueError(f"unsupported m3 rule registration: {rule_registration}")

    execution = _required_mapping(
        payload.get("execution_clock"), "historical closure execution_clock"
    )
    sessions = execution.get("sessions")
    if isinstance(sessions, bool) or not isinstance(sessions, int) or sessions <= 0:
        raise ValueError("historical execution clock sessions must be a positive integer")
    first_session = date.fromisoformat(
        _required_text(execution.get("first_session"), "execution clock first_session")
    )
    last_session = date.fromisoformat(
        _required_text(execution.get("last_session"), "execution clock last_session")
    )
    if first_session > last_session:
        raise ValueError("historical execution clock date range is inverted")
    for key in ("orders", "fills", "rejected_orders"):
        if execution.get(key) != 0:
            raise ValueError(f"historical execution clock must have zero {key}")
    opening_cash = _decimal_value(execution.get("opening_cash_cny"), "opening_cash_cny")
    ending_cash = _decimal_value(execution.get("ending_cash_cny"), "ending_cash_cny")
    ending_nav = _decimal_value(execution.get("ending_nav_cny"), "ending_nav_cny")
    if opening_cash != ending_cash or ending_nav != opening_cash:
        raise ValueError("historical execution clock changed cash or nav")

    diagnostics = _required_mapping(
        payload.get("range_diagnostics"), "historical closure range_diagnostics"
    )
    if diagnostics.get("validation_classification") != "NOT_PIT_SAFE":
        raise ValueError("historical range must remain NOT_PIT_SAFE")
    if diagnostics.get("validation_admission_status") != "NOT_ADMITTED":
        raise ValueError("historical range must remain NOT_ADMITTED")
    scenarios = _required_list(diagnostics.get("scenarios"), "range scenarios")
    if not scenarios:
        raise ValueError("historical range requires scenarios")
    range_first = date.fromisoformat(
        _required_text(diagnostics.get("first_session"), "range first_session")
    )
    range_last = date.fromisoformat(
        _required_text(diagnostics.get("last_session"), "range last_session")
    )
    if range_first > range_last:
        raise ValueError("historical range date range is inverted")

    blockers = _required_list(payload.get("blockers"), "historical closure blockers")
    blocker_codes = {str(item) for item in blockers}
    if not _REQUIRED_CLOSURE_BLOCKERS.issubset(blocker_codes):
        missing = sorted(_REQUIRED_CLOSURE_BLOCKERS - blocker_codes)
        raise ValueError("historical closure is missing required blockers: " + ", ".join(missing))

    sources = _required_list(payload.get("source_bindings"), "historical closure source_bindings")
    source_roles: set[str] = set()
    validated_sources: list[dict[str, str]] = []
    for source in sources:
        item = _required_mapping(source, "historical closure source binding")
        role = _required_text(item.get("role"), "historical closure source role")
        path = _required_text(item.get("path"), "historical closure source path")
        digest = _required_text(item.get("sha256"), "historical closure source sha256").lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("historical closure source sha256 must be SHA-256 hex")
        if role in source_roles:
            raise ValueError("historical closure source roles must be unique")
        source_roles.add(role)
        validated_sources.append(dict(role=role, path=path, sha256=digest))

    return {
        "symbol": symbol,
        "company_name": company_name,
        "generated_at": generated_at,
        "replay_date": replay_date,
        "final_decision": final_decision,
        "rule_registration": rule_registration,
        "sessions": sessions,
        "first_session": first_session,
        "last_session": last_session,
        "scenario_count": len(scenarios),
        "range_first": range_first,
        "range_last": range_last,
        "blockers": tuple(str(item) for item in blockers),
        "sources": tuple(validated_sources),
    }


def project_historical_company_closure(
    model: ProductWorkbenchReadModel,
    *,
    closure: Mapping[str, Any],
    closure_path: str,
    closure_sha256: str,
) -> ProductWorkbenchReadModel:
    """Project a verified historical closure into a separate audit-only section."""
    if not isinstance(model, ProductWorkbenchReadModel):
        raise TypeError("model must be ProductWorkbenchReadModel")
    path = _required_text(closure_path, "historical closure path")
    digest = _required_text(closure_sha256, "historical closure sha256").lower()
    if not _SHA256.fullmatch(digest):
        raise ValueError("historical closure sha256 must be SHA-256 hex")
    values = _validate_historical_closure_for_product(closure, model_as_of=model.as_of)
    symbol = values["symbol"]
    review_id = f"historical-closure-{symbol}-{digest[:12]}"
    if any(item.review_id == review_id for item in model.historical_reviews):
        raise ValueError("historical closure review already exists")

    records = list(model.audit_evidence)
    known_ids = {record.evidence_id for record in records}

    def add_record(
        evidence_id: str,
        title: str,
        artifact_type: str,
        record_path: str,
        record_sha256: str,
    ) -> str:
        if evidence_id in known_ids:
            raise ValueError(f"historical closure evidence id conflict: {evidence_id}")
        records.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                title=title,
                artifact_type=artifact_type,
                path=record_path,
                sha256=record_sha256,
                available_at=None,
            )
        )
        known_ids.add(evidence_id)
        return evidence_id

    closure_evidence_id = add_record(
        f"historical-closure-result-{symbol}-{digest[:12]}",
        "历史研究闭环工程产物（非当前决策）",
        "historical_company_closure",
        path,
        digest,
    )
    source_evidence_ids = tuple(
        add_record(
            f"historical-closure-source-{symbol}-{source['role']}-{source['sha256'][:12]}",
            f"历史研究来源：{source['role']}",
            "historical_closure_source",
            source["path"],
            source["sha256"],
        )
        for source in values["sources"]
    )
    card = HistoricalReviewCard(
        review_id=review_id,
        symbol=symbol,
        company_name=values["company_name"],
        review_kind=HISTORICAL_REVIEW_KIND,
        generated_at=values["generated_at"],
        closure_sha256=digest,
        engineering_delivery=_historical_status(
            "DELIVERED",
            HISTORICAL_REVIEW_STATUS_LABELS["engineering_delivery"],
            "historical review engineering_delivery",
        ),
        current_research_admission=_historical_status(
            "NOT_READY",
            HISTORICAL_REVIEW_STATUS_LABELS["current_research_admission"],
            "historical review current_research_admission",
        ),
        strict_pit=_historical_status(
            "NOT_PROVEN",
            HISTORICAL_REVIEW_STATUS_LABELS["strict_pit"],
            "historical review strict_pit",
        ),
        historical_execution=_historical_status(
            "NOT_VALIDATED",
            HISTORICAL_REVIEW_STATUS_LABELS["historical_execution"],
            "historical review historical_execution",
        ),
        performance_claim=_historical_status(
            "NOT_ALLOWED",
            HISTORICAL_REVIEW_STATUS_LABELS["performance_claim"],
            "historical review performance_claim",
        ),
        replay_date=values["replay_date"],
        replay_final_decision=_historical_status(
            values["final_decision"],
            HISTORICAL_REVIEW_STATUS_LABELS["replay_final_decision"],
            "historical review replay_final_decision",
        ),
        rule_registration=_historical_status(
            values["rule_registration"],
            HISTORICAL_REVIEW_STATUS_LABELS["rule_registration"],
            "historical review rule_registration",
        ),
        execution_clock_summary=(
            f"{values['sessions']} 个真实交易日（{values['first_session'].isoformat()} 至 "
            f"{values['last_session'].isoformat()}）；订单 0；成交 0；拒单 0；"
            "期初与期末现金、净值未变化。"
        ),
        range_diagnostic_summary=(
            f"{values['scenario_count']} 组区间敏感性情景（{values['range_first'].isoformat()} 至 "
            f"{values['range_last'].isoformat()}）；分类为未通过严格时点审查；"
            "准入状态为未准入；不形成业绩结论。"
        ),
        blockers=tuple(_blocker_text(item) for item in values["blockers"]),
        evidence_refs=(closure_evidence_id, *source_evidence_ids),
    )
    return replace(
        model,
        audit_evidence=tuple(records),
        historical_reviews=(*model.historical_reviews, card),
    )


def render_historical_reviews(model: ProductWorkbenchReadModel) -> str:
    """Render the historical section separately from current company cards."""
    if not isinstance(model, ProductWorkbenchReadModel):
        raise TypeError("model must be ProductWorkbenchReadModel")
    lines = [
        "# 历史研究闭环（非当前投资建议）",
        "",
        "以下内容来自已经封存的历史研究工程链，只用于解释历史输入和计算边界。",
        "它不是当前估值、价格吸引力、业绩证明或买入建议；系统永远不生成交易订单。",
        "",
    ]
    if not model.historical_reviews:
        lines.append("当前产品数据包未接入历史研究闭环。")
        return "\n".join(lines) + "\n"
    records = {record.evidence_id: record for record in model.audit_evidence}
    for review in model.historical_reviews:
        lines.extend(
            [
                f"## {review.company_name}（{review.symbol}）",
                "",
                f"- 工程交付：{review.engineering_delivery.user_label}",
                f"- 当前研究准入：{review.current_research_admission.user_label}",
                f"- 严格历史时点：{review.strict_pit.user_label}",
                f"- 历史执行有效性：{review.historical_execution.user_label}",
                f"- 业绩结论：{review.performance_claim.user_label}",
                f"- M3 回放日：{review.replay_date.isoformat()}；"
                f"回放结论：{review.replay_final_decision.user_label}",
                f"- 规则状态：{review.rule_registration.user_label}",
                f"- 无决策执行时钟：{review.execution_clock_summary}",
                f"- 区间诊断：{review.range_diagnostic_summary}",
                "",
                "### 为什么仍不能升级为交易结论",
                "",
            ]
        )
        lines.extend(f"- {blocker}" for blocker in review.blockers)
        lines.extend(["", "### 来源审计", ""])
        for evidence_ref in review.evidence_refs:
            record = records.get(evidence_ref)
            if record is None:
                raise ValueError(f"missing historical review evidence: {evidence_ref}")
            lines.append(
                f"- {record.title}：`{record.path}`；SHA256={record.sha256}"
            )
        lines.append("")
    return "\n".join(lines)


def _percent(value: object) -> str:
    return f"{Decimal(str(value)):.1%}"


def _rule_status_text(value: object) -> str:
    return _RULE_STATUS_TEXT.get(str(value), str(value))


def _blocker_text(value: object) -> str:
    code = str(value)
    return _BLOCKER_TEXT.get(code, code)


def _mapped(mapping: dict[str, str], value: object) -> str:
    text = str(value)
    return mapping.get(text, text)


def render_historical_company_closure(payload: dict) -> str:
    if (payload.get("schema_version") != "historical-company-closure-v1"
            or payload.get("action") != "no_order"):
        raise ValueError("invalid historical company closure")
    symbol = payload["symbol"]
    name = payload.get("company_name") or symbol
    m3 = payload["m3_replay"]
    execution = payload["execution_clock"]
    range_diagnostics = payload["range_diagnostics"]
    lines = [
        f"# {name}（{symbol}）历史研究闭环",
        "",
        "这是一份真实历史输入的研究工程回放，不是当前买卖建议，也不是策略有效性的结论。",
        "",
        "| 结论层级 | 状态 |",
        "| --- | --- |",
        f"| 工程交付 | {_mapped(_DELIVERY_TEXT, payload['engineering_delivery'])} |",
        f"| 当前研究准入 | {_mapped(_ADMISSION_TEXT, payload['current_research_admission'])} |",
        f"| 严格PIT | {'通过' if payload['strict_pit_admitted'] else '未通过'} |",
        f"| 历史执行有效性 | {'已验证' if payload['historical_execution_validated'] else '未验证'} |",
        f"| 操作状态 | 不生成交易订单 |",
        "",
        "## 已实现的单票闭环",
        "",
        f"- M3研究回放：{m3['replay_id']}，回放日 {m3['replay_date']}，结论"
        f" {_mapped(_DECISION_STATUS_TEXT, m3['final_decision'])}。",
        f"- 当时可得报价：{m3['then_known_quote']['close_cny']} 元（{m3['then_known_quote']['quote_date']}）。",
        f"- 规则状态：{_rule_status_text(m3['rule']['rule_registration_status'])}；规则版本 `{m3['rule']['rule_version']}`。",
        f"- 无决策执行时钟：覆盖 {execution['sessions']} 个真实交易日；它只核对交易日历、现金事件和期末状态，订单 {execution['orders']}；成交 {execution['fills']}；拒单 {execution['rejected_orders']}。",
        f"- 公司行动：{execution['declared_cash_events']} 项已审核事件，执行账本展开为 "
        f"{execution['journal_cash_event_rows']} 条登记/应收/支付日期行；"
        f"开账现金与期末净值均为 {execution['opening_cash_cny']} 元。",
        "",
        "## 区间诊断（仅研究，不构成策略结论）",
        "",
        "区间诊断使用事后研究假设，只用于检验计算与执行链能否运行，不能与前一段的无决策执行时钟混为一谈。",
        "",
        "| 情景 | 安全边际 | 成交 | 期末净值 | 研究期毛收益 | 最大回撤 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in range_diagnostics["scenarios"]:
        lines.append(
            f"| {row['scenario']} | {_percent(row['safety_margin'])} | {row['fills']} | "
            f"{Decimal(row['ending_nav_cny']):,.2f} | {_percent(row['gross_research_return'])} | "
            f"{_percent(row['maximum_drawdown'])} |"
        )
    lines.extend([
        "",
        f"区间窗口：{range_diagnostics['first_session']} 至 {range_diagnostics['last_session']}；"
        f"验证分类 {_mapped(_CLASSIFICATION_TEXT, range_diagnostics['validation_classification'])}；"
        f"准入状态 {_mapped(_ADMISSION_TEXT, range_diagnostics['validation_admission_status'])}。",
        "",
        "这些数字只能说明历史回放链能够运行，不能说明策略有效、可以照此交易或未来会重复。",
        "",
        "## 为什么仍不能升级为交易结论",
        "",
    ])
    lines.extend(f"- {_blocker_text(item)}" for item in payload["blockers"])
    lines.extend([
        "",
        "## 执行事件抽查",
        "",
        "| 日期 | 状态 | 订单 | 成交 |",
        "| --- | --- | --- | --- |",
    ])
    for event in range_diagnostics["execution_events"][:12]:
        order = event.get("created_order") or {}
        fill = event.get("fill") or {}
        order_text = f"{order.get('side', '')} {order.get('requested_quantity') or 'all'}" if order else "无"
        fill_text = f"{fill.get('quantity', '')} @ {fill.get('price', '')}" if fill else "无"
        lines.append(
            f"| {event['date']} | {_mapped(_DECISION_STATUS_TEXT, event['decision'])} |"
            f" {order_text} | {fill_text} |"
        )
    lines.extend(["", "## 来源审计", ""])
    for source in payload["source_bindings"]:
        lines.append(f"- {source['role']}: `{source['path']}` SHA256={source['sha256']}")
    lines.append("")
    return "\n".join(lines)

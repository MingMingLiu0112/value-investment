"""Render the normalized historical execution replay as readable Markdown."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from .product_workbench import (
    ACTION_NO_ORDER,
    HISTORICAL_EXECUTION_REPLAY_KIND,
    EvidenceRecord,
    HistoricalExecutionReplayCard,
    ProductWorkbenchReadModel,
)


REPLAY_SCHEMA = "historical-execution-replay-v1"
SOURCE_ROLES = (
    "execution_input",
    "range_config",
    "range_result",
    "range_manifest",
    "range_journal",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ROLE_ID = re.compile(r"^[a-z0-9_-]+$")
_LIMITATION_TEXT = {
    "The frozen journal only supplies dated decisions; this service does not recompute or approve the investment rule.":
        "冻结日志只提供带日期的历史决策，不重新计算或批准投资规则。",
    "Daily OHLC data do not prove order-book, queue, suspension, price-limit or liquidity execution.":
        "日线 OHLC 不能证明盘口、排队、停牌、涨跌停或流动性成交。",
    "The scenario remains NOT_PIT_SAFE and NOT_ADMITTED.":
        "该情景仍未通过严格历史时点审查，也未获研究准入。",
    "Gross research returns exclude dividend tax and an aligned total-return benchmark.":
        "研究性毛收益未包含股息税，也没有对齐的总收益基准。",
    "Exact mechanical reproduction is an engineering check, not a performance claim.":
        "精确机械复现只是工程校验，不构成业绩结论。",
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be SHA-256 hex")
    return text


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} must be a decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def _relative_path(value: object, field: str) -> str:
    text = _required_text(value, field).replace("\\", "/")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or re.match(r"^[A-Za-z]:", text)
    ):
        raise ValueError(f"{field} must remain a relative project path")
    return text


def _translated_limitations(values: object) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        raise ValueError("historical execution replay limitations are required")
    translated = []
    for index, value in enumerate(values):
        text = _required_text(value, f"limitations[{index}]")
        translated.append(_LIMITATION_TEXT.get(text, text))
    translated.append("系统不生成交易订单，最终投资决定由用户完成。")
    return tuple(translated)


def _price_correspondence_summary(replay: Mapping[str, Any]) -> str:
    proof = replay.get('price_source_correspondence')
    if proof is None:
        return '行情逐行原件对应未接入；文件 Hash 一致不等于价格逐行对应。'
    if (proof.get('schema_version') != 'historical-price-correspondence-v1'
            or proof.get('action') != ACTION_NO_ORDER
            or proof.get('historical_availability_proven') is not False
            or proof.get('execution_admitted') is not False
            or proof.get('validated_fields') != ['open', 'close']):
        raise ValueError('price correspondence cannot admit execution or historical availability')
    if proof.get('status') != 'MATCH':
        return '行情原件格式或覆盖尚未完成逐行对应；不能宣称价格源验证通过。'
    count = _integer(proof.get('matched_sessions'), 'price matched sessions')
    sources = _integer(proof.get('source_files'), 'price source files')
    if (count == 0 or sources == 0 or count != len(proof.get('rows', []))
            or proof.get('missing_dates') or proof.get('unsupported_sources')
            or proof.get('price_basis') != 'UNADJUSTED_DAY_ROWS'):
        raise ValueError('price correspondence match lacks complete rows')
    return (f'开盘与收盘逐行原件对应：{count} 个交易日，{sources} 个封存未复权日线文件。'
            '未验证最高/最低价、历史当时可得性、停牌涨跌停、流动性或真实成交。')


def _distribution_correspondence_summary(replay: Mapping[str, Any]) -> str:
    proof = replay.get("distribution_source_correspondence")
    if proof is None:
        return "分红执行输入与已审阅登记表逐项对应尚未接入。"
    if (not isinstance(proof, Mapping)
            or proof.get("schema_version") != "historical-distribution-correspondence-v1"
            or proof.get("scope") != "RETAINED_REVIEWED_GROSS_ENTITLEMENT_CORRESPONDENCE_ONLY"
            or proof.get("action") != ACTION_NO_ORDER
            or any(proof.get(key) is not False for key in (
                "complete_historical_coverage_proven", "pdf_semantics_reverified",
                "tax_treatment_verified", "historical_availability_proven", "execution_admitted"))):
        raise ValueError("distribution correspondence cannot admit historical execution")
    if proof.get("status") == "NOT_ASSESSABLE":
        return "没有已绑定审阅登记表，分红字段对应无法判断。"
    count = _integer(proof.get("matched_events"), "matched distribution events")
    if proof.get("status") != "MATCH" or count != len(proof.get("rows", [])):
        raise ValueError("distribution correspondence lacks matching rows")
    return (f"{count} 项分红/送股安排与已审阅登记表及公告绑定一致。"
            "仅核对登记、除息、到账、每股毛现金与送股上市安排；"
            "不代表重新审阅公告语义、历史完整覆盖、税后回报或当时可得性。")


def _decision_explanation_lines(replay: Mapping[str, Any]) -> tuple[str, ...]:
    bundle = replay.get("decision_explanations")
    if bundle is None:
        return ()
    if not isinstance(bundle, Mapping) or bundle.get("schema_version") != "frozen-decision-explanations-v1":
        raise ValueError("unsupported frozen decision explanations")
    if (bundle.get("action") != ACTION_NO_ORDER
            or bundle.get("scope") != "RECORDED_EXPERIMENT_MECHANICS_ONLY"
            or bundle.get("thesis_consistency") != "NOT_ASSESSABLE"):
        raise ValueError("frozen decision explanations cannot approve thesis or trading")
    cards = bundle.get("cards")
    rules = bundle.get("recorded_rules")
    if not isinstance(cards, list) or not isinstance(rules, Mapping):
        raise ValueError("frozen decision explanation cards and rules are required")
    lines = [
        "只解释冻结实验，不是当前交易建议；企业买卖逻辑一致性无法验证。",
        f"规则登记时间：{bundle.get('rules_registered_at') or '未记录'}；不代表规则在历史决策日已存在。",
    ]
    labels = {"entry": "原进入规则", "exit": "原退出规则", "sizing": "原仓位规则"}
    lines.extend(f"{labels[key]}（原文）：{value}" for key, value in rules.items() if value is not None)
    for card in cards:
        if not isinstance(card, Mapping) or card.get("thesis_consistency") != "NOT_ASSESSABLE":
            raise ValueError("frozen decision card cannot approve thesis consistency")
        context = card.get("context")
        if not isinstance(context, Mapping):
            raise ValueError("frozen decision context is required")
        for key in ("close_cny", "value_cny", "safety_margin", "nav_cny"):
            if context.get(key) is not None:
                _decimal(context[key], f"frozen context {key}")
        states = {"proposed_entry": "首次买入实验", "proposed_add": "加仓实验",
                  "proposed_reduce": "减仓实验", "proposed_exit": "退出实验"}
        if card.get("state") not in states:
            raise ValueError("unsupported frozen decision state")
        lines.append(f"{card.get('decision_date')}：{states[card['state']]}，编号 {card.get('decision_id')}。")
        price = context.get("close_cny")
        value = context.get("value_cny")
        margin = context.get("safety_margin")
        lines.append(f"当日收盘 {price if price is not None else '未记录'} 元；实验价值端点 "
                     f"{value if value is not None else '未记录'} 元（未经批准的估值）；"
                     f"日志记录的安全边际 {_percent(margin) if margin is not None else '未记录'}。")
        sizing = context.get("sizing")
        if sizing is not None:
            if not isinstance(sizing, Mapping):
                raise ValueError("frozen sizing must be an object")
            lines.append(f"原实验预算：上限 {sizing.get('cap_cny', '未记录')} 元；本次允许预算 "
                         f"{sizing.get('permitted_budget_cny', '未记录')} 元；已有暴露 "
                         f"{sizing.get('current_exposure_cny', '未记录')} 元；"
                         f"请求 {sizing.get('quantity', '未记录')} 股。不是当前建议仓位。")
        if card.get("linked_entry_id"):
            lines.append(f"关联原买入：{card['linked_entry_id']}；原价值端点 "
                         f"{card.get('original_value_cny') or '未记录'} 元。"
                         "只有日志关联，不能证明原 Thesis 已兑现或被破坏。")
        fill = card.get("fill")
        if isinstance(fill, Mapping):
            lines.append(f"账本执行：{fill.get('filled_on')}，{fill.get('quantity')} 股，"
                         f"价格 {fill.get('price')} 元，费用 {fill.get('fee_cny')} 元；不证明真实可成交。")
        else:
            lines.append("未关联账本成交；不能按成交复盘。")
    lines.append("仍缺买入 Thesis 封存、当时业务判断、当时反证和 Thesis Breaker 复核；不自动补写、不批准买卖一致性。")
    return tuple(lines)


def _validate_historical_execution_replay_for_product(
    replay: Mapping[str, Any],
) -> dict[str, Any]:
    if replay.get("schema_version") != REPLAY_SCHEMA:
        raise ValueError("unsupported historical execution replay schema")
    if replay.get("action") != ACTION_NO_ORDER:
        raise ValueError("historical execution replay must remain no_order")
    symbol = _required_text(replay.get("symbol"), "historical execution replay symbol")
    if not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("historical execution replay symbol must contain six digits")
    company_name = _required_text(
        replay.get("company_name"), "historical execution replay company_name"
    )
    scenario = _required_text(
        replay.get("scenario"), "historical execution replay scenario"
    )
    generated_at = datetime.fromisoformat(
        _required_text(
            replay.get("generated_at"),
            "historical execution replay generated_at",
        )
    )
    if generated_at.utcoffset() is None:
        raise ValueError("historical execution replay generated_at must be timezone-aware")
    recipe_sha256 = _sha256(
        replay.get("recipe_sha256"),
        "historical execution replay recipe_sha256",
    )
    if replay.get("engineering_delivery") != "DELIVERED":
        raise ValueError("historical execution replay engineering delivery must be DELIVERED")
    if replay.get("current_research_admission") != "NOT_READY":
        raise ValueError("historical execution replay cannot promote current research admission")
    for field in (
        "historical_execution_validated",
        "strict_pit_admitted",
        "investment_rule_validated",
        "performance_claim_allowed",
    ):
        if replay.get(field) is not False:
            raise ValueError(f"historical execution replay {field} must be false")
    if replay.get("decision_rule_recomputed") is not False:
        raise ValueError("historical execution replay cannot recompute or approve a decision rule")
    if replay.get("mechanical_reproduction_verified") is not True:
        raise ValueError("historical execution replay mechanical reproduction must be verified")
    if replay.get("validation_classification") != "NOT_PIT_SAFE":
        raise ValueError("historical execution replay must remain NOT_PIT_SAFE")
    if replay.get("validation_admission_status") != "NOT_ADMITTED":
        raise ValueError("historical execution replay must remain NOT_ADMITTED")

    summary = replay.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("historical execution replay summary is required")
    opening_nav = _decimal(summary.get("opening_nav_cny"), "summary.opening_nav_cny")
    ending_nav = _decimal(summary.get("ending_nav_cny"), "summary.ending_nav_cny")
    gross_return = _decimal(
        summary.get("gross_research_return"), "summary.gross_research_return"
    )
    maximum_drawdown = _decimal(
        summary.get("maximum_drawdown"), "summary.maximum_drawdown"
    )
    fills = _integer(summary.get("fills"), "summary.fills")
    rejected_orders = _integer(summary.get("rejected_orders"), "summary.rejected_orders")
    ending_shares = _integer(summary.get("ending_shares"), "summary.ending_shares")

    comparison = replay.get("comparison")
    if not isinstance(comparison, Mapping):
        raise ValueError("historical execution replay comparison is required")
    journal_comparison = comparison.get("frozen_journal")
    range_comparison = comparison.get("range_result")
    if not isinstance(journal_comparison, Mapping) or not isinstance(
        range_comparison, Mapping
    ):
        raise ValueError("historical execution replay comparison objects are required")
    if journal_comparison.get("status") != "MATCH":
        raise ValueError("historical execution replay frozen journal must match")
    if range_comparison.get("status") != "MATCH":
        raise ValueError("historical execution replay range result must match")
    rows_compared = _integer(
        journal_comparison.get("rows_compared"),
        "comparison.frozen_journal.rows_compared",
    )
    proposals_compared = _integer(
        journal_comparison.get("trade_proposals_compared"),
        "comparison.frozen_journal.trade_proposals_compared",
    )
    fills_compared = _integer(
        journal_comparison.get("fills_compared"),
        "comparison.frozen_journal.fills_compared",
    )
    rejections_compared = _integer(
        journal_comparison.get("rejections_compared"),
        "comparison.frozen_journal.rejections_compared",
    )
    periods_compared = _integer(
        range_comparison.get("periods_compared"),
        "comparison.range_result.periods_compared",
    )
    if rows_compared == 0 or periods_compared == 0:
        raise ValueError("historical execution replay comparisons cannot be empty")
    if fills != fills_compared or rejected_orders != rejections_compared:
        raise ValueError("historical execution replay comparison counts differ from summary")

    source_bindings = replay.get("source_bindings")
    if not isinstance(source_bindings, list):
        raise ValueError("historical execution replay source_bindings are required")
    bindings = []
    roles = []
    for index, item in enumerate(source_bindings):
        if not isinstance(item, Mapping):
            raise ValueError(f"source_bindings[{index}] must be an object")
        role = _required_text(item.get("role"), f"source_bindings[{index}].role")
        if not _ROLE_ID.fullmatch(role):
            raise ValueError(f"source_bindings[{index}].role is invalid")
        roles.append(role)
        bindings.append(
            {
                "role": role,
                "path": _relative_path(
                    item.get("path"), f"source_bindings[{index}].path"
                ),
                "sha256": _sha256(
                    item.get("sha256"), f"source_bindings[{index}].sha256"
                ),
            }
        )
    required_roles = [role for role in roles if role in SOURCE_ROLES]
    original_roles = [role for role in roles if role not in SOURCE_ROLES]
    if (set(required_roles) != set(SOURCE_ROLES) or len(required_roles) != len(SOURCE_ROLES)
            or len(set(roles)) != len(roles)
            or any(not re.fullmatch(r"execution_original_[0-9]{3,}", role) for role in original_roles)):
        raise ValueError("historical execution replay source roles are incomplete or duplicated")

    limitations = _translated_limitations(replay.get("limitations"))
    period_summary = replay.get("period_summary")
    if not isinstance(period_summary, list):
        raise ValueError("historical execution replay period_summary is required")
    session_count = 0
    for period in period_summary:
        if not isinstance(period, Mapping):
            raise ValueError("historical execution replay period must be an object")
        session_count += _integer(period.get("sessions"), "period.sessions")
    if session_count <= 0:
        raise ValueError("historical execution replay period sessions are required")

    return {
        "symbol": symbol,
        "company_name": company_name,
        "scenario": scenario,
        "generated_at": generated_at,
        "recipe_sha256": recipe_sha256,
        "summary": {
            "session_count": session_count,
            "opening_nav": opening_nav,
            "ending_nav": ending_nav,
            "gross_return": gross_return,
            "maximum_drawdown": maximum_drawdown,
            "fills": fills,
            "rejected_orders": rejected_orders,
            "ending_shares": ending_shares,
        },
        "comparison": {
            "rows_compared": rows_compared,
            "proposals_compared": proposals_compared,
            "periods_compared": periods_compared,
        },
        "sources": tuple(bindings),
        "limitations": limitations,
        "decision_explanations": _decision_explanation_lines(replay),
    }


def project_historical_execution_replay(
    model: ProductWorkbenchReadModel,
    *,
    replay: Mapping[str, Any],
    replay_path: str,
    replay_sha256: str,
) -> ProductWorkbenchReadModel:
    """Project one execution replay into the secondary audit surface only."""
    if not isinstance(model, ProductWorkbenchReadModel):
        raise TypeError("model must be ProductWorkbenchReadModel")
    path = _required_text(replay_path, "historical execution replay path")
    digest = _sha256(replay_sha256, "historical execution replay sha256")
    values = _validate_historical_execution_replay_for_product(replay)
    if values["generated_at"].date() > model.as_of:
        raise ValueError("historical execution replay was generated after product as_of")
    symbol = values["symbol"]
    replay_id = f"historical-execution-replay-{symbol}-{digest[:12]}"
    if any(item.replay_id == replay_id for item in model.historical_execution_replays):
        raise ValueError("historical execution replay already exists")

    records = list(model.audit_evidence)
    known_ids = {record.evidence_id for record in records}

    def add_record(
        evidence_id: str,
        title: str,
        artifact_type: str,
        record_path: str,
        record_sha256: str,
    ) -> str:
        record = EvidenceRecord(
                evidence_id=evidence_id,
                title=title,
                artifact_type=artifact_type,
                path=record_path,
                sha256=record_sha256,
                available_at=None,
            )
        if evidence_id in known_ids:
            existing = [item for item in records if item.evidence_id == evidence_id]
            if len(existing) == 1 and existing[0] == record:
                return evidence_id
            raise ValueError(f"historical execution replay evidence id conflict: {evidence_id}")
        records.append(record)
        known_ids.add(evidence_id)
        return evidence_id

    result_evidence_id = add_record(
        f"historical-execution-replay-result-{symbol}-{digest[:12]}",
        "历史执行回放工程产物（非当前决策）",
        "historical_execution_replay",
        path,
        digest,
    )
    source_evidence_ids = tuple(
        add_record(
            f"historical-execution-replay-source-{symbol}-{source['role']}-{source['sha256'][:12]}",
            f"历史执行回放来源：{source['role']}",
            "historical_execution_replay_source",
            source["path"],
            source["sha256"],
        )
        for source in values["sources"]
    )
    summary = values["summary"]
    comparison = values["comparison"]
    card = HistoricalExecutionReplayCard(
        replay_id=replay_id,
        symbol=symbol,
        company_name=values["company_name"],
        replay_kind=HISTORICAL_EXECUTION_REPLAY_KIND,
        generated_at=values["generated_at"],
        replay_sha256=digest,
        scenario=values["scenario"],
        decision_source="冻结历史 journal",
        execution_engine="共享虚拟账户回放",
        execution_summary=(
            f"{summary['session_count']} 个交易日；成交 {summary['fills']} 次；"
            f"拒单 {summary['rejected_orders']} 次；期末 NAV "
            f"{_decimal_text(summary['ending_nav'])} 元；研究性总回报 "
            f"{_percent(summary['gross_return'])}；最大回撤 "
            f"{_percent(summary['maximum_drawdown'])}；期末持股 "
            f"{summary['ending_shares']} 股。"
        ),
        comparison_summary=(
            f"冻结 journal 对照一致，覆盖 {comparison['rows_compared']} 个交易日和 "
            f"{comparison['proposals_compared']} 个历史提议；冻结 result 对照一致，"
            f"覆盖 {comparison['periods_compared']} 个预登记时段。"
            + _price_correspondence_summary(replay)
            + _distribution_correspondence_summary(replay)
        ),
        validation_summary=(
            "机械重建已验证；当前研究未准入；严格历史时点未证明；"
            "历史执行有效性未验证；投资规则未验证；业绩结论不允许。"
        ),
        limitations=values["limitations"],
        evidence_refs=(result_evidence_id, *source_evidence_ids),
        decision_explanations=values["decision_explanations"],
    )
    return replace(
        model,
        audit_evidence=tuple(records),
        historical_execution_replays=(
            *model.historical_execution_replays,
            card,
        ),
    )


def render_historical_execution_replays(
    model: ProductWorkbenchReadModel,
) -> str:
    """Render execution replay audit cards separately from current product cards."""
    if not isinstance(model, ProductWorkbenchReadModel):
        raise TypeError("model must be ProductWorkbenchReadModel")
    lines = [
        "# 历史执行回放（非当前投资建议）",
        "",
        "以下内容只证明共享账本可以从冻结决策和真实历史输入重建同一执行序列，",
        "不证明历史可成交、不证明策略有效，也不产生交易指令。",
        "",
    ]
    if not model.historical_execution_replays:
        lines.append("当前产品数据包未接入历史执行回放。")
        return "\n".join(lines) + "\n"
    records = {record.evidence_id: record for record in model.audit_evidence}
    for replay in model.historical_execution_replays:
        lines.extend(
            [
                f"## {replay.company_name}（{replay.symbol}）",
                "",
                f"- 场景：{replay.scenario}",
                f"- 决策来源：{replay.decision_source}",
                f"- 执行引擎：{replay.execution_engine}",
                f"- 工程结论：{replay.validation_summary}",
                f"- 执行汇总：{replay.execution_summary}",
                f"- 对照结果：{replay.comparison_summary}",
                "",
                "### 保留边界",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in replay.limitations)
        if replay.decision_explanations:
            lines.extend(["", "### 冻结决策解释与买卖关联", ""])
            lines.extend(f"- {item}" for item in replay.decision_explanations)
        lines.extend(["", "### 来源审计", ""])
        for evidence_ref in replay.evidence_refs:
            record = records.get(evidence_ref)
            if record is None:
                raise ValueError(f"missing historical execution replay evidence: {evidence_ref}")
            lines.append(f"- {record.title}：`{record.path}`；SHA256={record.sha256}")
        lines.append("")
    return "\n".join(lines)


def _cash_reconciliation_lines(payload):
    lines = []
    cash = payload.get('cash_reconciliation')
    if cash is not None:
        lines.extend(['## 资金与股息应收勾稽', '',
            '逐日核验买卖本金、费用、股息计提与实际到账；税前研究账本，不是个人账户或收益证明。',
            f"核验交易日：{cash['sessions_checked']}；结果：{cash['status']}",
            f"期初现金：{cash['initial_cash_cny']}；期末现金：{cash['ending_cash_cny']}；期末应收股息：{cash['ending_receivable_cny']}", '',
            '| 日期 | 买入本金 | 卖出本金 | 费用 | 股息计提 | 股息到账 | 期末现金 | 期末应收 |',
            '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |'])
        for row in cash['movements']:
            lines.append('| ' + ' | '.join(str(row[key]) for key in
                ('date', 'buy_principal_cny', 'sell_principal_cny', 'fees_cny',
                 'dividend_accrued_cny', 'dividend_paid_cny', 'closing_cash_cny',
                 'closing_receivable_cny')) + ' |')
        lines.append('')
    return lines


def _decimal_text(value: object) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if not number.is_finite():
        return str(value)
    return format(number, "f")


def _percent(value: object) -> str:
    try:
        number = Decimal(str(value)) * Decimal("100")
    except (InvalidOperation, ValueError):
        return str(value)
    return f"{number.quantize(Decimal('0.0001'))}%"


def _binding_line(binding: Mapping[str, Any]) -> str:
    return f"- `{binding.get('role')}`: `{binding.get('path')}` / `{binding.get('sha256')}`"


def _event_rows(payload: Mapping[str, Any]) -> list[str]:
    rows = []
    for event in payload.get("execution_events", []):
        if not isinstance(event, Mapping):
            continue
        created = event.get("created_order")
        fill = event.get("fill")
        rejected = event.get("rejected_order_reason")
        summary = ""
        if isinstance(created, Mapping):
            summary += f"提交 {created.get('side')} 单"
        if isinstance(fill, Mapping):
            if summary:
                summary += "; "
            summary += (
                f"成交 {fill.get('quantity')} 股 @ {_decimal_text(fill.get('price'))}, "
                f"费用 {_decimal_text(fill.get('fee_cny'))} 元"
            )
        if rejected:
            if summary:
                summary += "; "
            summary += f"拒绝: {rejected}"
        if not summary:
            cash_events = event.get("cash_events")
            if isinstance(cash_events, list) and cash_events:
                summary = f"分红/权益事件 {len(cash_events)} 项"
        if not summary:
            continue
        rows.append(
            f"| {event.get('date')} | {event.get('decision') or '-'} | {summary} | "
            f"{_decimal_text(event.get('cash_cny'))} | {event.get('holding_shares')} | "
            f"{_decimal_text(event.get('nav_cny'))} |"
        )
    return rows


def _period_rows(payload: Mapping[str, Any]) -> list[str]:
    rows = []
    for period in payload.get("period_summary", []):
        if not isinstance(period, Mapping):
            continue
        rows.append(
            f"| {period.get('period')} | {period.get('start')} 至 {period.get('end')} | "
            f"{period.get('sessions')} | {period.get('fills')} | "
            f"{_percent(period.get('gross_research_return'))} | "
            f"{_percent(period.get('maximum_drawdown'))} |"
        )
    return rows


def render_historical_execution_replay(payload: Mapping[str, Any]) -> str:
    """Render one source-pinned execution reconstruction without promotion."""
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("summary is required")
    company = payload.get("company_name") or payload.get("symbol")
    lines = [
        f"# {company} {payload.get('symbol')} 历史执行回放",
        "",
        "> 本文只证明共享账本可以从冻结决策和真实历史输入重建同一执行序列；不证明历史可成交，不证明策略有效，也不产生交易指令。",
        "",
        "## 工程结论",
        "",
        f"- 场景：`{payload.get('scenario')}`",
        f"- 决策来源：`{payload.get('decision_source')}`；投资规则未重新计算。",
        f"- 行情原件核验：{_price_correspondence_summary(payload)}",
        f"- 分红输入核验：{_distribution_correspondence_summary(payload)}",
        f"- 执行引擎：`{payload.get('execution_engine')}`；费用引擎：`{payload.get('fee_engine')}`。",
        f"- 冻结 journal 对照：`{payload.get('comparison', {}).get('frozen_journal', {}).get('status')}`；"
        f"覆盖 {payload.get('comparison', {}).get('frozen_journal', {}).get('rows_compared')} 个交易日。",
        f"- 冻结 result 对照：`{payload.get('comparison', {}).get('range_result', {}).get('status')}`；"
        f"覆盖 {payload.get('comparison', {}).get('range_result', {}).get('periods_compared')} 个预登记时段。",
        "- 历史执行验证：未通过；严格 PIT：未证明；业绩结论：不允许。",
        "",
        "## 汇总",
        "",
        f"- 起始 NAV：{_decimal_text(summary.get('opening_nav_cny'))} 元",
        f"- 期末 NAV：{_decimal_text(summary.get('ending_nav_cny'))} 元",
        f"- 研究性总回报：{_percent(summary.get('gross_research_return'))}",
        f"- 最大回撤：{_percent(summary.get('maximum_drawdown'))}",
        f"- 成交：{summary.get('fills')} 次；拒绝：{summary.get('rejected_orders')} 次；期末持股：{summary.get('ending_shares')} 股",
        "",
        "## 执行事件",
        "",
        "| 日期 | 决策 | 执行 | 现金 | 持股 | NAV |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    event_rows = _event_rows(payload)
    lines.extend(event_rows or ["| - | - | 无成交或资金事件 | - | - | - |"])
    lines.extend([
        "", "## 原提议与执行对照", "",
        "成交日没有新决策不等于没有买入理由：执行来自此前冻结提议。下表不重建或批准原投资逻辑。",
        "", "| 提议日期 | 原提议 | 执行状态 | 成交日期 | 股数 / 价格 / 费用 | 投资理由 |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    states = {"proposed_entry": "首次买入提议", "proposed_add": "加仓提议",
              "proposed_reduce": "减仓提议", "proposed_exit": "退出提议"}
    statuses = {"FILLED": "账本成交", "REJECTED": "拒绝", "UNRESOLVED": "尚未关联执行"}
    for outcome in payload.get("decision_outcomes", []):
        fill = outcome.get("fill") or {}
        detail = (f"{fill.get('quantity')} 股 / {_decimal_text(fill.get('price'))} 元 / "
                  f"{_decimal_text(fill.get('fee_cny'))} 元") if fill else "未成交"
        lines.append(f"| {outcome.get('decision_date')} | {states.get(outcome.get('state'), '历史提议')} | "
                     f"{statuses.get(outcome.get('execution_status'), '未知')} | {fill.get('filled_on', '-')} | "
                     f"{detail} | 未重建，不可作为当前买卖依据 |")
        for rejection in outcome.get("rejections", []):
            reason = str(rejection['reason']).replace('|', '/').replace('\n', ' ')
            lines.append(f"\n拒绝记录：{rejection['date']}，{reason}。\n")
        if outcome.get("deferred_dates"):
            lines.append("\n延期而非成交：" + "、".join(outcome["deferred_dates"]) + "。\n")
    lines.extend([
        "",
        "## 分时段对照",
        "",
        "| 时段 | 日期 | 交易日 | 成交 | 研究性回报 | 最大回撤 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    lines.extend(_period_rows(payload))
    explanations = _decision_explanation_lines(payload)
    if explanations:
        lines.extend(["", "## 冻结决策解释与买卖关联", ""])
        lines.extend(f"- {item}" for item in explanations)
    lines.extend([
        "",
        "## 来源绑定",
        "",
    ])
    for binding in payload.get("source_bindings", []):
        if isinstance(binding, Mapping):
            lines.append(_binding_line(binding))
    lines.extend([
        "",
        "## 限制",
        "",
    ])
    for limitation in payload.get("limitations", []):
        lines.append(f"- {limitation}")
    lines.extend([
        "",
        "本报告保持 `historical_execution_validated=false`、`strict_pit_admitted=false`、`performance_claim_allowed=false` 与 `action=no_order`。",
        "",
    ])
    proof = payload.get("distribution_source_correspondence")
    if isinstance(proof, Mapping) and proof.get("status") == "MATCH":
        lines.extend(["## 分红与送股输入逐项追溯", "",
                      "以下为税前权益安排；不是已收到的现金，实际持股权益见执行事件。", ""])
        for row in proof["rows"]:
            lines.append(
                f"- {row['event_id']}：登记 {row['record_date']}；除息 {row['ex_date']}；"
                f"到账 {row['payment_date']}；每股毛现金 {row['cash_per_share']} 元；"
                f"每股送股 {row['bonus_shares_per_share']}；上市日 {row['bonus_listing_date'] or '不适用'}。"
            )
            for original in row["evidence"]:
                lines.append(f"  [公告原件]({original['url']})，页码 {original['pages']}；"
                             f"本地 `{original['path']}`；SHA-256 `{original['sha256']}`。")
        lines.append("")
    lines.extend(_cash_reconciliation_lines(payload))
    return "\n".join(lines)

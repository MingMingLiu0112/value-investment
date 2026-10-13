"""Review whether a registered research version can legally cover a later cutoff.

TL8 work package A1/A2. The review answers, from hash-bound evidence only:

* which research version is registered and what its cutoff is;
* whether official disclosures inside the reviewed window changed anything;
* what the shared model-validity evaluator says today, and what it would say
  once the human event-window review exists;
* whether the registered close may enter the price-comparison ladder;
* which approvals are still missing and the exact conditions to reopen.

It writes one ``research-validity-review-v1`` artifact and never approves,
re-registers, re-prices or orders anything. ``action`` stays ``no_order``.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from .common import (load_json_object, normalize_symbol, require_inside, sha256_file,
                     write_new_json)
from .quote_bridge import quote_compatibility_ladder
from ...event_scan import (COVERAGE_COMPLETE, SCAN_COMPLETE_MATERIAL_EVENTS,
                           SCAN_COMPLETE_NO_MATERIAL_EVENT, SCAN_PENDING_HUMAN_REVIEW,
                           EventScanResult, event_scan_from_payload)
from ...model_validity import ModelValidity, evaluate_model_validity


SCHEMA_VERSION = "research-validity-review-v1"

STATUS_BLOCKED_ON_EVENT_COVERAGE = "BLOCKED_ON_EVENT_COVERAGE"
STATUS_BLOCKED_ON_HUMAN_EVENT_REVIEW = "BLOCKED_ON_HUMAN_EVENT_REVIEW"
STATUS_REQUIRES_MATERIALITY_REVIEW = "REQUIRES_MATERIALITY_REVIEW"
STATUS_BLOCKED_ON_RESEARCH_RE_REGISTRATION = "BLOCKED_ON_RESEARCH_RE_REGISTRATION"
STATUS_SUPPORTS_QUOTE_UNDER_PENDING_GATES = "RESEARCH_SUPPORTS_QUOTE_UNDER_PENDING_GATES"

_FINANCIAL_KINDS = {"financial_statement", "financial_report"}


def _resolve(root: Path, value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return require_inside(root, path, label)


def _required_date(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date string") from error
    return value


def _model_validity_payload(validity: ModelValidity) -> dict[str, Any]:
    return {
        "model_id": validity.model_id,
        "symbol": validity.symbol,
        "model_as_of": validity.model_as_of.isoformat(),
        "valid_from": validity.valid_from.isoformat(),
        "last_material_event_check": (validity.last_material_event_check.isoformat()
                                      if validity.last_material_event_check else None),
        "financial_statement_changed": validity.financial_statement_changed,
        "capital_structure_changed": validity.capital_structure_changed,
        "material_event_found": validity.material_event_found,
        "status": validity.status,
        "blockers": list(validity.blockers),
        "evidence_refs": [dict(ref) for ref in validity.evidence_refs],
    }


def _reviewed_scan(scan_payload: dict[str, Any]) -> EventScanResult | None:
    """Return the counterfactual scan a human reviewer would confirm, or None.

    Only an empty, fully covered window can be counterfactually reviewed here.
    Any announcement keeps the window in human materiality review instead of a
    simulation, so the review never pretends a disclosure was assessed.
    """
    if scan_payload.get("status") != SCAN_PENDING_HUMAN_REVIEW:
        return None
    if scan_payload.get("announcements"):
        return None
    reviewed = dict(scan_payload)
    reviewed["status"] = SCAN_COMPLETE_NO_MATERIAL_EVENT
    return event_scan_from_payload(reviewed)


def _news_rows(scan: EventScanResult) -> list[dict[str, Any]]:
    rows = []
    for item in scan.announcements:
        refs = [dict(ref) for ref in item.evidence_refs]
        rows.append({
            "announcement_id": item.announcement_id,
            "published_at": item.published_at.isoformat(),
            "title": item.title,
            "source_url": item.source_url,
            "rule_kind": item.rule_kind,
            "review_status": item.review_status,
            "materiality_candidate": item.materiality_candidate,
            "pre_model": item.pre_model,
            "sha256": refs[0].get("sha256") if refs else None,
        })
    return rows


def review_research_validity(*, root: Path, symbol: str, package_path: Path,
                             package_sha256: str, review_cutoff: date,
                             event_scan_path: Path, event_scan_sha256: str,
                             quote_bundle: Path | None = None,
                             quote_bundle_sha256: str | None = None,
                             output_path: Path, today: datetime) -> dict[str, Any]:
    """Run one hash-bound validity review; never returns an approval."""
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    package_file = _resolve(root, package_path, "research package")
    if sha256_file(package_file) != package_sha256:
        raise ValueError("研究包 Hash 与登记不一致")
    package = load_json_object(package_file, "research package")
    if package.get("symbol") != symbol:
        raise ValueError("研究包与标的标的不一致")
    point_in_time = package.get("point_in_time")
    if not isinstance(point_in_time, dict):
        raise ValueError("研究包缺少 point_in_time")
    research_day = _required_date(point_in_time.get("research_as_of"),
                                  "point_in_time.research_as_of")
    if date.fromisoformat(research_day) > review_cutoff:
        raise ValueError("研究截止日不能晚于复核截止日")
    validity_input = package.get("model_validity_input")
    if not isinstance(validity_input, dict) or not validity_input.get("model_id"):
        raise ValueError("研究包缺少 model_validity_input.model_id")
    valid_from = date.fromisoformat(_required_date(
        validity_input.get("valid_from") or research_day, "model_validity_input.valid_from"))
    scan_file = _resolve(root, event_scan_path, "event scan")
    if sha256_file(scan_file) != event_scan_sha256:
        raise ValueError("事件扫描 Hash 与登记不一致")
    scan_payload = load_json_object(scan_file, "event scan")
    scan = event_scan_from_payload(scan_payload)
    if scan.symbol != symbol:
        raise ValueError("事件扫描与标的标的不一致")
    if scan.validity_from.isoformat() != research_day:
        raise ValueError("事件扫描的有效期起点必须等于研究截止日")
    if scan.scan_to < review_cutoff:
        raise ValueError("事件扫描未覆盖复核截止日")
    coverage_complete = scan.coverage_status == COVERAGE_COMPLETE
    blockers = list(validity_input.get("blockers") or [])
    current = evaluate_model_validity(model_id=str(validity_input["model_id"]), symbol=symbol,
        model_as_of=date.fromisoformat(research_day), valid_from=valid_from,
        quote_date=review_cutoff, events=[], event_scan_evidence_refs=[],
        blockers=blockers, event_scan=scan)
    reviewed = _reviewed_scan(scan_payload)
    if reviewed is not None:
        reviewed_validity = evaluate_model_validity(model_id=str(validity_input["model_id"]),
            symbol=symbol, model_as_of=date.fromisoformat(research_day), valid_from=valid_from,
            quote_date=review_cutoff, events=[], event_scan_evidence_refs=[],
            blockers=blockers, event_scan=reviewed)
        reviewed_payload = _model_validity_payload(reviewed_validity)
    else:
        reviewed_payload = None
    news = _news_rows(scan)
    financial_news = [row for row in news if row["rule_kind"] in _FINANCIAL_KINDS]
    if not news:
        facts_change = {"status": "NONE",
                        "reason": "复核窗口内官方公告为零，财务事实仍适用最近已披露报告期。",
                        "report_period": point_in_time.get("report_period")}
    else:
        facts_change = {"status": "REVIEW_REQUIRED",
                        "reason": "复核窗口内存在官方公告，需人工材料性复核后才可判断事实是否变化。",
                        "report_period": point_in_time.get("report_period"),
                        "financial_announcements": [row["announcement_id"] for row in financial_news]}
    price_compatibility: dict[str, Any] = {"status": "QUOTE_NOT_PROVIDED",
        "reason": "未提供已登记收盘行情，无法判断价格兼容性。",
        "ladder": quote_compatibility_ladder({}, research_day),
        "comparison_eligible_within_review": {"eligible": False,
            "reason": "未提供已登记收盘行情。"}}
    sources_binding: list[dict[str, Any]] = []
    if quote_bundle is not None:
        if not isinstance(quote_bundle_sha256, str) or not quote_bundle_sha256:
            raise ValueError("行情包 Hash 缺失")
        bundle_file = _resolve(root, quote_bundle, "quote bundle")
        if sha256_file(bundle_file) != quote_bundle_sha256:
            raise ValueError("行情包 Hash 与登记不一致")
        from .quote_bridge import admit_quote_for_research
        _, _, verdict = admit_quote_for_research(root, bundle_file, symbol, research_day,
                                                 today=today)
        verdict = dict(verdict)
        ladder = quote_compatibility_ladder(verdict, research_day)
        comparison_with_validity = bool(ladder["comparison_eligible"]["eligible"]
                                        and current.status == "VALID")
        price_compatibility = {
            "status": verdict.get("status"),
            "reason": verdict.get("reason"),
            "quote_date": verdict.get("quote_date"),
            "display_price": verdict.get("display_price"),
            "collected_at": verdict.get("collected_at"),
            "bundle_path": verdict.get("bundle_path"),
            "bundle_sha256": verdict.get("bundle_sha256"),
            "ladder": ladder,
            "comparison_eligible_within_review": {
                "eligible": comparison_with_validity,
                "reason": ("行情已准入且模型有效性覆盖报价日。"
                           if comparison_with_validity else
                           "价格—估值比较需行情准入且模型有效性为 VALID；当前不满足。"),
                "note": "已发布桥接 READY 仍需在发布层核对，二者一致才可展示价格比较。"},
        }
        for ref in verdict.get("source_evidence") or []:
            sources_binding.append({key: ref.get(key) for key in
                                    ("provider", "source_url", "fetched_at", "sha256")})
    single_missing_approval = None
    if not coverage_complete:
        status = STATUS_BLOCKED_ON_EVENT_COVERAGE
    elif news:
        status = STATUS_REQUIRES_MATERIALITY_REVIEW
        single_missing_approval = "MATERIALITY_REVIEW_PER_ANNOUNCEMENT"
    elif scan.status == SCAN_COMPLETE_MATERIAL_EVENTS:
        status = STATUS_REQUIRES_MATERIALITY_REVIEW
        single_missing_approval = "MATERIALITY_RECALCULATION"
    elif scan.status == SCAN_PENDING_HUMAN_REVIEW:
        status = STATUS_BLOCKED_ON_HUMAN_EVENT_REVIEW
        single_missing_approval = "EVENT_WINDOW_HUMAN_REVIEW"
    elif price_compatibility.get("quote_date") and \
            str(price_compatibility["quote_date"]) > research_day:
        status = STATUS_BLOCKED_ON_RESEARCH_RE_REGISTRATION
        single_missing_approval = "RESEARCH_VERSION_RE_REGISTRATION"
    else:
        status = STATUS_SUPPORTS_QUOTE_UNDER_PENDING_GATES
    approval_required = [
        {"gate": "EVENT_WINDOW_HUMAN_REVIEW", "owner": "human",
         "why": (f"事件扫描有效期 {scan.validity_from}→{scan.validity_to} 仍为人工待复核；"
                 "复核完成前，模型有效性不能由 UNKNOWN 变为 VALID。"),
         "unlocks": f"模型有效性覆盖 {review_cutoff.isoformat()}（当前 "
                    f"{current.status}）"},
        {"gate": "RESEARCH_VERSION_RE_REGISTRATION", "owner": "engine+operator",
         "why": (f"登记研究截止日为 {research_day}，未覆盖更晚的已核验行情；"
                 "重登记只能生成待复核版本，不能代签审批。"),
         "unlocks": "价格桥接从 QUOTE_VERIFIED_BUT_RESEARCH_STALE 进入可判断状态"},
        {"gate": "G3_VALUATION_APPROVAL", "owner": "human",
         "why": "正式估值批准是正式投资决策的前置人工门。",
         "unlocks": "正式决策资格（formal_decision_eligible）"},
        {"gate": "PRIVATE_PORTFOLIO_OR_IPS", "owner": "user",
         "why": "仓位建议必须基于真实组合与约束，当前未接入。",
         "unlocks": "position guidance（在此之前保持 null）"},
    ]
    reopen_conditions = [
        (f"人工完成事件窗口材料性复核（扫描 {event_scan_sha256[:12]}…，"
         f"{scan.validity_from}→{scan.validity_to}，公告数 {len(news)}）。"),
        (f"以覆盖 {review_cutoff.isoformat()} 的研究版本完成有界重登记"
         "（既有引擎 prepare_pending_research_candidate，输出 PENDING_REVIEW，不得代签）。"),
        "重登记后重跑价格桥接登记与执行（pin_current_quote_bridge.py / execute_quote_bridge_for_symbol）。",
        "在产生当日已核验收盘后重跑 run_daily_trade_assistant.py，使报价日为当前交易会话。",
        "G3 人工批准与决策门通过前保持 action=no_order，不产生买入/加仓建议。",
    ]
    evidence_refs = [
        {"id": "review-package", "path": package_file.relative_to(root).as_posix(),
         "sha256": package_sha256},
        {"id": "review-event-scan", "path": scan_file.relative_to(root).as_posix(),
         "sha256": event_scan_sha256},
    ]
    for ref in scan.evidence_refs:
        evidence_refs.append({key: ref.get(key) for key in ("id", "path", "sha256", "source_url")})
    availability = [value for value in (scan.retrieved_at.isoformat(),
                                        price_compatibility.get("collected_at"),
                                        point_in_time.get("available_at")) if isinstance(value, str)]
    review = {
        "schema_version": SCHEMA_VERSION,
        "action": "no_order",
        "symbol": symbol,
        "company_name": package.get("name"),
        "generated_at": today.isoformat(),
        "status": status,
        "previous_research_version": {
            "package_path": package_file.relative_to(root).as_posix(),
            "package_sha256": package_sha256,
            "package_version": package.get("package_version"),
            "research_as_of": research_day,
            "report_period": point_in_time.get("report_period"),
            "model_id": validity_input.get("model_id"),
            "profile_id": package.get("profile_id"),
        },
        "review_cutoff": review_cutoff.isoformat(),
        "source_availability_cutoff": max(availability) if availability else None,
        "window": {"scan_from": scan.scan_from.isoformat(), "scan_to": scan.scan_to.isoformat(),
                   "validity_from": scan.validity_from.isoformat(),
                   "validity_to": scan.validity_to.isoformat(),
                   "coverage_status": scan.coverage_status,
                   "scan_status": scan.status,
                   "parser_version": scan.parser_version},
        "facts_change": facts_change,
        "material_events": {"status": "NONE_FOUND" if not news else "REVIEW_REQUIRED",
                            "announcements": news},
        "assumptions_change": {
            "status": "NONE" if not news else "REVIEW_REQUIRED",
            "reason": ("本轮未重拟合假设；窗口内无新披露时既有假设维持原样。"
                       if not news else "窗口内存在公告，假设是否变化须人工复核。")},
        "model_validity_review": {
            "current": _model_validity_payload(current),
            "if_event_window_reviewed": reviewed_payload,
            "single_missing_approval": single_missing_approval,
            "note": ("if_event_window_reviewed 仅是“人工确认窗口无重大事件”后的计算结果，"
                     "不是批准；不得据此直接形成正式研究版本。" if reviewed_payload else
                     "窗口存在公告或扫描状态不同，不提供反事实结论。"),
        },
        "price_compatibility": price_compatibility,
        "quote_sources": sources_binding,
        "approval_required": approval_required,
        "blockers": [*current.blockers,
                     *([] if price_compatibility.get("status") in
                         (None, "QUOTE_VERIFIED_FOR_RESEARCH_INPUT") else
                       [str(price_compatibility.get("reason"))])],
        "reopen_conditions": reopen_conditions,
        "evidence_refs": evidence_refs,
    }
    write_new_json(_resolve(root, output_path, "review output"), review)
    return review


def render_research_validity_review_markdown(review: dict[str, Any]) -> str:
    """Render the review artifact as a short human-readable report."""
    ladder_labels = {"verified_quote": "报价双源核验", "research_compatible": "研究覆盖报价日",
                     "historical_reconstruction_eligible": "历史重建对比资格",
                     "comparison_eligible": "价格比较准入",
                     "formal_decision_eligible": "正式决策资格"}
    previous = review["previous_research_version"]
    lines = [
        f"# 研究有效性复核：{review.get('company_name') or review['symbol']}（{review['symbol']}）",
        "",
        f"- 结论状态：`{review['status']}`",
        f"- 登记研究版本：`{previous.get('package_version')}`（研究截止日 {previous.get('research_as_of')}）",
        f"- 复核截止日：{review['review_cutoff']}；来源可用截止：{review.get('source_availability_cutoff')}",
        f"- 永久动作边界：`action={review['action']}`",
        "",
        "## 窗口与事实变化",
        f"- 事件窗口：{review['window']['scan_from']} → {review['window']['scan_to']}"
        f"（覆盖 {review['window']['coverage_status']}，扫描状态 `{review['window']['scan_status']}`）",
        f"- 公告数：{len(review['material_events']['announcements'])}"
        f"；事实变化：`{review['facts_change']['status']}`",
        f"- 假设变化：`{review['assumptions_change']['status']}`",
        "",
        "## 模型有效性",
        f"- 当前：`{review['model_validity_review']['current']['status']}`"
        f"（blockers: {'; '.join(review['model_validity_review']['current']['blockers']) or '无'}）",
    ]
    counterfactual = review["model_validity_review"].get("if_event_window_reviewed")
    if counterfactual is not None:
        lines.append(f"- 若人工完成事件窗口复核：`{counterfactual['status']}`（反事实，不是批准）")
    lines.extend(["", "## 价格兼容性阶梯"])
    for key, label in ladder_labels.items():
        row = review["price_compatibility"].get("ladder", {}).get(key, {})
        mark = "通过" if row.get("eligible") else "未通过"
        lines.append(f"- {label}：{mark}。{row.get('reason') or ''}")
    lines.extend(["", "## 待人工审批"])
    for item in review["approval_required"]:
        lines.append(f"- `{item['gate']}`（{item['owner']}）：{item['why']} → 解锁 {item['unlocks']}")
    lines.extend(["", "## 重开条件"])
    lines.extend(f"{index}. {step}" for index, step in enumerate(review["reopen_conditions"], 1))
    lines.extend(["", "## 证据"])
    for ref in review["evidence_refs"]:
        lines.append(f"- {ref.get('id')}：{ref.get('path')}（{(ref.get('sha256') or '')[:12]}…）")
    return "\n".join(lines) + "\n"

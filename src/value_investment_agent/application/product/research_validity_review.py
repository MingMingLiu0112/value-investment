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

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .common import (load_json_object, normalize_symbol, require_inside, sha256_file,
                     write_new_json)
from .quote_bridge import quote_compatibility_ladder
from ...event_scan import (COVERAGE_COMPLETE, COVERAGE_INCOMPLETE, SCAN_COMPLETE_MATERIAL_EVENTS,
                           SCAN_COMPLETE_NO_MATERIAL_EVENT, SCAN_PENDING_HUMAN_REVIEW,
                           REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE,
                           EventScanResult, event_scan_from_payload)
from ...model_validity import ModelValidity, evaluate_model_validity


SCHEMA_VERSION = "research-validity-review-v1"

STATUS_BLOCKED_ON_EVENT_COVERAGE = "BLOCKED_ON_EVENT_COVERAGE"
STATUS_BLOCKED_ON_HUMAN_EVENT_REVIEW = "BLOCKED_ON_HUMAN_EVENT_REVIEW"
STATUS_REQUIRES_MATERIALITY_REVIEW = "REQUIRES_MATERIALITY_REVIEW"
STATUS_BLOCKED_ON_RESEARCH_RE_REGISTRATION = "BLOCKED_ON_RESEARCH_RE_REGISTRATION"
STATUS_SUPPORTS_QUOTE_UNDER_PENDING_GATES = "RESEARCH_SUPPORTS_QUOTE_UNDER_PENDING_GATES"
STATUS_BLOCKED_ON_MODEL_VALIDITY = "BLOCKED_ON_MODEL_VALIDITY"
STATUS_INCREMENTAL_REVIEW_COMPLETE_PRICE_BRIDGE_PENDING = "INCREMENTAL_REVIEW_COMPLETE_PRICE_BRIDGE_PENDING"

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
    if (scan_payload.get("status") != SCAN_PENDING_HUMAN_REVIEW
            or scan_payload.get("coverage_status") != COVERAGE_COMPLETE):
        return None
    if scan_payload.get("announcements"):
        return None
    reviewed = dict(scan_payload)
    reviewed["status"] = SCAN_COMPLETE_NO_MATERIAL_EVENT
    return event_scan_from_payload(reviewed)


def _available_at(value: object, field: str, today: datetime) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} requires a timezone timestamp")
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > today:
        raise ValueError(f"{field} is naive or in the future")
    return stamp


def _audit_scan_sources(root: Path, scan: EventScanResult) -> list[dict[str, Any]]:
    """A pinned scan alone cannot establish retained-original integrity."""
    refs = [*scan.evidence_refs, *(ref for item in scan.announcements for ref in item.evidence_refs)]
    audit = []
    for ref in refs:
        row = {key: ref.get(key) for key in ("id", "path", "sha256")}
        try:
            if not row["path"] or not row["sha256"]:
                raise ValueError("missing source binding")
            source = _resolve(root, row["path"], "event scan source")
            row["observed_sha256"] = sha256_file(source)
            row["status"] = "VERIFIED" if row["observed_sha256"] == row["sha256"] else "HASH_MISMATCH"
        except (ValueError, OSError, TypeError):
            row["status"] = "UNAVAILABLE_OR_UNBOUND"
        if row not in audit:
            audit.append(row)
    return audit


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
                             output_path: Path | None = None, today: datetime) -> dict[str, Any]:
    """Run one hash-bound validity review; never returns an approval."""
    root = root.resolve()
    if today.utcoffset() is None:
        raise ValueError("Review clock requires a timezone")
    if review_cutoff > today.astimezone(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("Review cutoff is in the future")
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
    package_available = _available_at(point_in_time.get("available_at"), "research available_at", today)
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
    if scan.validity_to < review_cutoff:
        raise ValueError("事件有效期未覆盖复核截止日")
    if scan.scan_to > review_cutoff:
        raise ValueError("事件扫描超出复核截止日；请提供对应时点的扫描")
    scan_available = _available_at(scan.retrieved_at.isoformat(), "event scan retrieved_at", today)
    if any(item.published_at > scan.retrieved_at for item in scan.announcements):
        raise ValueError("Announcement is not available at scan retrieval time")
    source_audit = _audit_scan_sources(root, scan)
    source_blockers = ["EVENT_SCAN_SOURCE_NOT_VERIFIED:" + str(row["id"])
                       for row in source_audit if row["status"] != "VERIFIED"]
    if source_blockers:
        scan = replace(scan, coverage_status=COVERAGE_INCOMPLETE,
                       blockers=(*scan.blockers, *source_blockers))
    coverage_complete = scan.coverage_status == COVERAGE_COMPLETE
    blockers = list(validity_input.get("blockers") or [])
    current = evaluate_model_validity(model_id=str(validity_input["model_id"]), symbol=symbol,
        model_as_of=date.fromisoformat(research_day), valid_from=valid_from,
        quote_date=review_cutoff, events=[], event_scan_evidence_refs=[],
        blockers=blockers, event_scan=scan)
    # Do not let an empty later scan erase unresolved registered material events.
    if validity_input.get("events") or validity_input.get("event_materiality"):
        current = replace(current, status="UNKNOWN", material_event_found=None,
                          blockers=[*current.blockers, "REGISTERED_EVENT_CONTEXT_REQUIRES_REVIEW"])
    reviewed = _reviewed_scan(scan.as_policy())
    if validity_input.get("events") or validity_input.get("event_materiality"):
        reviewed = None
    if reviewed is not None:
        reviewed_validity = evaluate_model_validity(model_id=str(validity_input["model_id"]),
            symbol=symbol, model_as_of=date.fromisoformat(research_day), valid_from=valid_from,
            quote_date=review_cutoff, events=[], event_scan_evidence_refs=[],
            blockers=blockers, event_scan=reviewed)
        reviewed_payload = _model_validity_payload(reviewed_validity)
    else:
        reviewed_payload = None
    news = _news_rows(scan)
    pending_news = [row for row in news if row["materiality_candidate"]
                    or row["review_status"] != REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE]
    if pending_news and current.status == "VALID":
        current = replace(current, status="UNKNOWN", material_event_found=None,
                          blockers=[*current.blockers, "ANNOUNCEMENT_REVIEW_INCOMPLETE"])
    financial_news = [row for row in news if row["rule_kind"] in _FINANCIAL_KINDS]
    reusable = coverage_complete and current.status == "VALID" and not current.blockers and not pending_news
    if not coverage_complete:
        facts_change = {"status": "UNKNOWN", "reason": "公告覆盖或引用原件未核验，不能从空列表推断事实未变化。",
                        "report_period": point_in_time.get("report_period")}
    elif not news:
        facts_change = {"status": "NONE",
                        "reason": "复核窗口内官方公告为零，财务事实仍适用最近已披露报告期。",
                        "report_period": point_in_time.get("report_period")}
    elif pending_news:
        facts_change = {"status": "REVIEW_REQUIRED",
                        "reason": "复核窗口内存在官方公告，需人工材料性复核后才可判断事实是否变化。",
                        "report_period": point_in_time.get("report_period"),
                        "financial_announcements": [row["announcement_id"] for row in financial_news]}
    else:
        facts_change = {"status": "REVIEWED_NO_MODEL_INVALIDATION",
                        "reason": "沿用输入扫描中已有的逐条复核结论；不将非重大披露解释为财务事实完全未变化。",
                        "report_period": point_in_time.get("report_period")}
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
                                        and current.status == "VALID" and not current.blockers
                                        and not pending_news)
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
    elif pending_news:
        status = STATUS_REQUIRES_MATERIALITY_REVIEW
        single_missing_approval = "MATERIALITY_REVIEW_PER_ANNOUNCEMENT"
    elif scan.status == SCAN_COMPLETE_MATERIAL_EVENTS:
        status = STATUS_REQUIRES_MATERIALITY_REVIEW
        single_missing_approval = "MATERIALITY_RECALCULATION"
    elif scan.status == SCAN_PENDING_HUMAN_REVIEW:
        status = STATUS_BLOCKED_ON_HUMAN_EVENT_REVIEW
        single_missing_approval = "EVENT_WINDOW_HUMAN_REVIEW"
    elif current.status != "VALID" or current.blockers:
        status = STATUS_BLOCKED_ON_MODEL_VALIDITY
    elif price_compatibility.get("quote_date") and \
            str(price_compatibility["quote_date"]) > research_day:
        status = STATUS_INCREMENTAL_REVIEW_COMPLETE_PRICE_BRIDGE_PENDING
        single_missing_approval = "PRICE_BRIDGE_REVIEW_BINDING_REQUIRED"
    else:
        status = STATUS_SUPPORTS_QUOTE_UNDER_PENDING_GATES
    approval_required = [
        {"gate": "EVENT_WINDOW_HUMAN_REVIEW", "owner": "human",
         "required": not coverage_complete or bool(pending_news) or scan.status == SCAN_PENDING_HUMAN_REVIEW,
         "why": (f"事件扫描有效期 {scan.validity_from}→{scan.validity_to}；"
                 "沿用已有复核状态，不自动批准未完成的材料性复核。"),
         "unlocks": f"模型有效性覆盖 {review_cutoff.isoformat()}（当前 "
                    f"{current.status}）"},
        {"gate": "RESEARCH_VERSION_RE_REGISTRATION", "owner": "engine+operator",
         "required": not reusable,
         "why": (f"登记研究截止日为 {research_day}，未覆盖更晚的已核验行情；"
                 "增量复核可单独证明模型有效性，但不修改该截止日或既有行情准入；"
                 "需按原价格桥合同绑定复核结果，不能仅复制新截止日。"),
         "unlocks": "价格桥接从 QUOTE_VERIFIED_BUT_RESEARCH_STALE 进入可判断状态"},
        {"gate": "G3_VALUATION_APPROVAL", "owner": "human",
         "why": "正式估值批准是正式投资决策的前置人工门。",
         "unlocks": "正式决策资格（formal_decision_eligible）"},
        {"gate": "PRIVATE_PORTFOLIO_OR_IPS", "owner": "user",
         "why": "仓位建议必须基于真实组合与约束，当前未接入。",
         "unlocks": "position guidance（在此之前保持 null）"},
    ]
    reopen_conditions = [
        ("已完成的事件窗口无需重复审核；保留原始研究，绑定本次增量有效性结果。" if reusable else
         f"完成事件窗口与模型适用性复核（扫描 {event_scan_sha256[:12]}…，"
         f"{scan.validity_from}→{scan.validity_to}，公告数 {len(news)}）；不得自动材料性/G3批准。"),
        "仅在失效条件要求时重算模型；日期推进本身不要求重做整份财务研究。",
        "价格桥接仍按原合同核验，复核结果不是 quote_bridge 准入替代品。",
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
    if quote_bundle is not None:
        evidence_refs.append({"id": "review-quote-bundle", "path": bundle_file.relative_to(root).as_posix(),
                              "sha256": quote_bundle_sha256})
    availability = [scan_available, package_available]
    if price_compatibility.get("collected_at"):
        availability.append(_available_at(price_compatibility["collected_at"], "quote collected_at", today))
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
        "source_availability_cutoff": max(availability).isoformat(),
        "incremental_review": {
            "status": "MODEL_VALID_AT_REVIEW_CUTOFF" if reusable else "REVIEW_REQUIRED",
            "research_cutoff_changed": False,
            "model_recalculation_required": False if reusable else True if current.status == "STALE" else None,
            "model_valid_through": review_cutoff.isoformat() if reusable else None,
            "original_model_as_of": research_day,
            "formal_eligibility": False, "g3_approval_granted": False,
            "price_bridge_changed": False, "action": "no_order",
            "note": "仅复核原模型在新时点的有效性；不得改研究截止日冒充覆盖，价格比较与G3仍走原门禁。",
        },
        "event_source_audit": source_audit,
        "window": {"scan_from": scan.scan_from.isoformat(), "scan_to": scan.scan_to.isoformat(),
                   "validity_from": scan.validity_from.isoformat(),
                   "validity_to": scan.validity_to.isoformat(),
                   "coverage_status": scan.coverage_status,
                   "declared_coverage_status": scan_payload["coverage_status"],
                   "scan_status": scan.status,
                   "parser_version": scan.parser_version},
        "facts_change": facts_change,
        "material_events": {"status": ("UNKNOWN" if not coverage_complete else "REVIEW_REQUIRED" if pending_news
                                       else "REVIEWED_NO_MATERIAL_CANDIDATE" if news else "NONE_FOUND"),
                            "announcements": news},
        "assumptions_change": {
            "status": ("UNKNOWN" if not coverage_complete else "REVIEW_REQUIRED" if pending_news
                       else "REVIEWED_NO_MODEL_INVALIDATION" if news else "NONE"),
            "reason": ("覆盖未核验，不能判断假设是否变化。" if not coverage_complete else
                       "公告材料性尚待复核，不自动改写假设。" if pending_news else
                       "本轮未重拟合或改写假设；是否沿用模型见独立增量有效性结果。")},
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
    if output_path is not None:
        write_new_json(_resolve(root, output_path, "review output"), review)
    return review


def review_registered_research_validity(*, root: Path, review_cutoff: date,
        today: datetime, output_path: Path | None = None, symbols: list[str] | None = None,
        incremental_bindings: list[dict] | None = None) -> dict[str, Any]:
    """Review only pointer-bound packages and their declared scans, independently.

    Re-running unchanged results reuses the immutable artifact; a changed result
    requires a new output path. No runtime search can silently rebind evidence.
    """
    from .quote_bridge import POINTER_PATH, POINTER_SCHEMA

    root = root.resolve()
    if today.utcoffset() is None or review_cutoff > today.astimezone(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("Review requires an aware clock and a non-future cutoff")
    target = _resolve(root, output_path, "registered review output") if output_path is not None else None
    pointer_file = root / POINTER_PATH
    pointer = load_json_object(pointer_file, "quote bridge pointer")
    if pointer.get("schema_version") != POINTER_SCHEMA or not isinstance(pointer.get("quotes"), dict):
        raise ValueError("Invalid current quote bridge pointer")
    entries = pointer["quotes"]
    selected = sorted(set(normalize_symbol(s) for s in (symbols if symbols is not None else entries)))
    rows = []
    for symbol in selected:
        row: dict[str, Any] = {"symbol": symbol, "status": "PENDING", "action": "no_order",
            "model_validity_status": "UNKNOWN", "formal_eligibility": False,
            "g3_approval_granted": False, "review": None, "evidence_refs": []}
        try:
            entry = entries.get(symbol)
            if not isinstance(entry, dict):
                raise ValueError("REGISTERED_QUOTE_BINDING_MISSING")
            if entry.get("registration_scope") == "QUOTE_OBSERVATION_ONLY":
                row.update(status="NO_REGISTERED_RESEARCH", reason="仅登记展示行情，尚无完整研究包；不进行模型有效性批准。")
                rows.append(row)
                continue
            package_path = _resolve(root, entry["research_package"], "research package")
            package_sha = entry["research_package_sha256"]
            if sha256_file(package_path) != package_sha:
                raise ValueError("REGISTERED_PACKAGE_HASH_MISMATCH")
            row["evidence_refs"].append({"path": package_path.relative_to(root).as_posix(), "sha256": package_sha})
            package = load_json_object(package_path, "research package")
            if package.get("symbol") != symbol:
                raise ValueError("REGISTERED_PACKAGE_SYMBOL_MISMATCH")
            validity = package.get("model_validity_input") or {}
            from .incremental_validity import read_bound_json, load_incremental_scan_binding

            supplemental = []
            for binding_ref in incremental_bindings or []:
                _, binding = read_bound_json(root, binding_ref, "incremental validity binding")
                if binding.get("symbol") == symbol:
                    supplemental.append(binding_ref)
            if len(supplemental) > 1:
                raise ValueError("Ambiguous explicit incremental bindings")
            # Use the primary reference when present; never substitute a newer,
            # unregistered scan found by filename or filesystem timestamp.
            ref = validity.get("event_scan_ref")
            if supplemental:
                ref = load_incremental_scan_binding(root=root, binding_ref=supplemental[0],
                    symbol=symbol, package_path=package_path, package_sha256=package_sha,
                    review_cutoff=review_cutoff, today=today)
                row["incremental_binding_ref"] = supplemental[0]
                row["evidence_refs"].append(supplemental[0])
            elif ref is None:
                refs = validity.get("event_scan_evidence_refs") or []
                if len(refs) != 1:
                    raise ValueError("EVENT_SCAN_BINDING_MISSING_OR_AMBIGUOUS")
                ref = refs[0]
            if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
                raise ValueError("EVENT_SCAN_BINDING_INCOMPLETE")
            row["evidence_refs"].append(dict(ref))
            scan_path = _resolve(root, ref["path"], "event scan")
            review = review_research_validity(root=root, symbol=symbol,
                package_path=package_path, package_sha256=package_sha,
                review_cutoff=review_cutoff, event_scan_path=scan_path,
                event_scan_sha256=ref["sha256"], quote_bundle=entry.get("quote_bundle"),
                quote_bundle_sha256=entry.get("quote_bundle_sha256"), today=today)
            row.update(status=review["status"], review=review,
                       model_validity_status=review["model_validity_review"]["current"]["status"])
        except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
            row["reason"] = str(error)
        rows.append(row)
    result = {"schema_version": "registered-research-validity-reviews-v1",
        "generated_at": today.isoformat(), "review_cutoff": review_cutoff.isoformat(),
        "action": "no_order", "research_cutoff_changed": False, "g3_approval_granted": False,
        "pointer_ref": {"path": POINTER_PATH, "sha256": sha256_file(pointer_file)}, "reviews": rows}
    if target is None:
        return result
    if target.exists():
        existing = load_json_object(target, "registered validity reviews")

        def comparable(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: comparable(v) for k, v in value.items() if k != "generated_at"}
            if isinstance(value, list):
                return [comparable(v) for v in value]
            return value

        if comparable(existing) != comparable(result):
            raise FileExistsError("Registered validity result changed; use a new audit artifact path")
        return existing
    write_new_json(target, result)
    return result


def replay_registered_review_progress(*, root: Path, binding: dict,
        started_at: str, finished_at: str, now: datetime,
        expected_cutoff: str | None = None, expected_symbols: list[str] | None = None) -> dict[str, Any]:
    """Expose an actual daily check, replayed from its exact current dependencies.

    A completed machine check is not completed materiality research. Missing,
    replaced or unreplayable inputs withhold dates instead of inventing progress.
    """
    unavailable = {"status": "UNVERIFIED", "checked_at": None, "review_cutoff": None,
        "rows": [], "action": "no_order", "formal_eligibility": False}
    try:
        root = root.resolve()
        source = require_inside(root / "runtime", root / binding["path"], "daily research review")
        if source.stat().st_size > 10_000_000 or sha256_file(source) != binding["sha256"]:
            return unavailable
        saved = load_json_object(source, "daily research review")
        started, finished, checked = (datetime.fromisoformat(value) for value in
                                     (started_at, finished_at, saved["generated_at"]))
        if (any(value.utcoffset() is None for value in (started, finished, checked, now))
                or not started <= checked <= finished <= now
                or saved["schema_version"] != "registered-research-validity-reviews-v1"
                or saved["action"] != "no_order" or saved["g3_approval_granted"] is not False
                or saved["research_cutoff_changed"] is not False
                or saved["pointer_ref"]["path"] != "config/current-quote-bridge.json"
                or sha256_file(root / saved["pointer_ref"]["path"]) != saved["pointer_ref"]["sha256"]):
            return unavailable
        rows = saved["reviews"]
        if not isinstance(rows, list) or len(rows) > 100:
            return unavailable
        if (expected_cutoff is not None and expected_cutoff != saved["review_cutoff"]
                or expected_symbols is not None and expected_symbols != [row["symbol"] for row in rows]):
            return unavailable
        replay = review_registered_research_validity(root=root,
            review_cutoff=date.fromisoformat(saved["review_cutoff"]), today=checked,
            symbols=[row["symbol"] for row in rows],
            incremental_bindings=[row["incremental_binding_ref"] for row in rows
                                  if row.get("incremental_binding_ref")])
        if replay != saved or sha256_file(source) != binding["sha256"]:
            return unavailable
        progress = []
        for row in replay["reviews"]:
            review = row["review"] or {}
            window = review.get("window") or {}
            events = review.get("material_events") or {}
            previous = review.get("previous_research_version") or {}
            # A scan can be from a partially elapsed current day. Only the
            # retained official-response verifier proves a complete window.
            coverage_through = None
            validity = (review.get("model_validity_review") or {}).get("current") or {}
            if row.get("incremental_binding_ref"):
                from .incremental_validity import read_bound_json, resolve_incremental_model_validity
                from .daily_event_observation import verify_retained_event_coverage

                _, supplement = read_bound_json(root, row["incremental_binding_ref"], "review supplement")
                _, observation = read_bound_json(root, supplement["observation_ref"], "review observation")
                resolved = resolve_incremental_model_validity(root=root, symbol=row["symbol"],
                    binding_ref=row["incremental_binding_ref"], review_cutoff=date.fromisoformat(replay["review_cutoff"]),
                    today=checked)
                validity = _model_validity_payload(resolved)
                try:
                    coverage = verify_retained_event_coverage(root, observation, symbol=row["symbol"],
                        required_from=date.fromisoformat(supplement["research_as_of"]),
                        required_to=date.fromisoformat(replay["review_cutoff"]), now=checked)
                    coverage_through = coverage["scan_to"]
                except ValueError:
                    pass
            facts_status = (review.get("facts_change") or {}).get("status", "UNKNOWN")
            if coverage_through is None and facts_status in {"NONE", "REVIEWED_NO_MODEL_INVALIDATION"}:
                facts_status = "UNKNOWN"
            validity_status = validity.get("status", "UNKNOWN")
            if validity_status == "VALID" and (validity.get("blockers") or coverage_through is None):
                validity_status = "UNKNOWN"
            progress.append({"symbol": row["symbol"], "status": row["status"],
                "research_as_of": previous.get("research_as_of"),
                "scan_through": window.get("scan_to"),
                "event_coverage_through": coverage_through,
                "event_coverage_status": "COMPLETE" if coverage_through is not None else "UNCONFIRMED",
                "announcement_count": (len(events["announcements"]) if "announcements" in events else None),
                "facts_change_status": facts_status,
                "model_validity_status": validity_status,
                "model_recalculation_required": (True if validity_status == "STALE" else
                                                  False if validity_status == "VALID" else None),
                "materiality_review_required": (("ORIGINAL_EVENT_REVIEW_UNRESOLVED" in validity.get("blockers", [])) or any(item.get("required") is not False
                    and ("EVENT" in item["gate"] or "MATERIALITY" in item["gate"])
                    for item in review.get("approval_required", [])) if review else None),
                "formal_eligibility": False})
        if sha256_file(root / saved["pointer_ref"]["path"]) != saved["pointer_ref"]["sha256"]:
            return unavailable
        return {"status": "SOURCE_REPLAYED", "checked_at": saved["generated_at"],
            "review_cutoff": saved["review_cutoff"], "rows": progress,
            "action": "no_order", "formal_eligibility": False,
            "research_cutoff_changed": False, "scope": "MACHINE_REVIEW_NOT_RESEARCH_APPROVAL"}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return unavailable


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
        if item.get("required") is False:
            continue
        lines.append(f"- `{item['gate']}`（{item['owner']}）：{item['why']} → 解锁 {item['unlocks']}")
    lines.extend(["", "## 重开条件"])
    lines.extend(f"{index}. {step}" for index, step in enumerate(review["reopen_conditions"], 1))
    lines.extend(["", "## 证据"])
    for ref in review["evidence_refs"]:
        lines.append(f"- {ref.get('id')}：{ref.get('path')}（{(ref.get('sha256') or '')[:12]}…）")
    return "\n".join(lines) + "\n"

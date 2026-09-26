"""Project the pinned legacy M7 daily packet into the product workbench payload.

This module performs no investment reasoning. It copies closed M2-M6 states,
fails closed on unsupported or unsafe input, and leaves unsupported product
assessments explicitly unavailable for the presentation read model to render.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping


LEGACY_PACKET_SCHEMA_VERSION = "m7-daily-workbench-v1"
PRODUCT_PAYLOAD_SCHEMA_VERSION = "m7-product-workbench-v1"
ACTION_NO_ORDER = "no_order"

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INTERNAL_STAGE_TOKEN = re.compile(r"\bM[2-6]\b")
_USER_VISIBLE_SECTIONS = (
    "overview",
    "system_health",
    "today_items",
    "opportunities",
    "companies",
    "portfolio",
    "events",
)
_EXECUTION_KEYS = frozenset(
    {
        "trade_approved",
        "target_weight",
        "position_size",
        "order_quantity",
        "order_price",
        "order_id",
        "order",
        "quantity",
        "trade",
        "execute",
        "target_position",
        "proposed_entry",
        "buy",
        "sell",
        "broker",
        "live_eligible",
    }
)
_SIMULATED_PORTFOLIO_KEYS = frozenset(
    {
        "portfolio_summary",
        "portfolio_metrics",
        "portfolio_snapshot",
        "simulated_metrics",
        "total_assets",
        "cash",
        "holdings",
        "industry_exposure",
        "single_stock_concentration",
        "cyclical_exposure",
        "estimated_annual_dividend",
        "normalized_annual_dividend",
        "stock_position",
        "portfolio_risk",
    }
)
_STAGE_STATUS_CODES = {
    "m2": frozenset(
        {
            "DONE",
            "HUMAN_PASS",
            "ENGINEERING_DONE",
            "PENDING_HUMAN_REVIEW",
            "PARTIAL",
            "NOT_STARTED",
            "WAIT",
            "BLOCKED",
        }
    ),
    "m3": frozenset(
        {
            "DONE",
            "ENGINEERING_PARTIAL_PLUS",
            "PENDING_HUMAN_REVIEW",
            "PARTIAL",
            "NOT_STARTED",
            "WAIT",
            "RECONSTRUCTED_EVIDENCE_ONLY",
            "STRICT_PIT_PROVEN",
            "NOT_PROVEN",
            "BLOCKED",
        }
    ),
    "m4": frozenset(
        {
            "PENDING_USER_PRIVATE_INPUT",
            "REAL_DATA_AVAILABLE",
            "READY",
            "SIMULATED_ONLY",
            "ENGINEERING_DONE_SIMULATED",
            "NOT_STARTED",
            "WAIT",
        }
    ),
    "m5": frozenset(
        {
            "DONE",
            "ENGINEERING_DONE_OFFLINE",
            "PENDING_HUMAN_REVIEW",
            "PENDING_RECONCILIATION",
            "PARTIAL",
            "NOT_STARTED",
            "WAIT",
            "DEGRADED",
        }
    ),
    "m6": frozenset(
        {
            "PREFLIGHT_DONE",
            "NOT_STARTED",
            "OPERATIONAL_NOT_STARTED",
            "WAIT",
            "ACTIVE",
            "DEGRADED",
            "BLOCKED",
        }
    ),
}
_M2_ROW_STATUSES = frozenset(
    {
        "VERIFIED_FOR_DEEP_RESEARCH",
        "REJECTED_AFTER_VERIFICATION",
        "INSUFFICIENT_EVIDENCE",
        "UNSUPPORTED",
    }
)
_M2_NEXT_TRIGGERS = {
    "VERIFIED_FOR_DEEP_RESEARCH": "进入深入研究与人工复核。",
    "REJECTED_AFTER_VERIFICATION": "仅在出现新的实质证据后重新进入复核。",
    "INSUFFICIENT_EVIDENCE": "补齐该通道的关键证据后重新复核。",
    "UNSUPPORTED": "保留为当前模型不支持的研究记录。",
}
_CHANNEL_LABELS = {
    "quality": "质量通道",
    "dividend_cash_return": "股息与现金回报通道",
    "value": "价值通道",
    "cyclical": "周期通道",
}
_COMPANY_SECTION_KEYS = (
    "business_quality",
    "financial_quality",
    "capital_allocation",
    "valuation",
    "dividend",
    "risks_counterevidence",
)
_SCENARIO_KEYS = ("bear", "base", "bull")


def _required_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _required_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _required_symbol(value: object, field: str) -> str:
    symbol = _required_text(value, field)
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError(f"{field} must contain exactly six digits")
    return symbol


def _require_status(value: object, allowed: frozenset[str], field: str) -> str:
    status = _required_text(value, field).upper()
    if status not in allowed:
        raise ValueError(f"Unsupported {field}: {status}")
    return status


def _inactive_execution_value(value: object) -> bool:
    if value is None or value is False:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 0
    return isinstance(value, str) and value.strip().lower() in {
        "",
        "no_order",
        "false",
        "0",
    }


def _reject_active_execution_keys(value: object, path: str = "packet") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _EXECUTION_KEYS and not _inactive_execution_value(child):
                raise ValueError(
                    f"Legacy M7 packet contains active execution key at {path}.{key}"
                )
            _reject_active_execution_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_active_execution_keys(child, f"{path}[{index}]")


def _reject_output_execution_keys(value: object, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        forbidden = _EXECUTION_KEYS.intersection(value)
        if forbidden:
            raise ValueError(
                f"Product workbench payload contains execution keys at {path}: "
                + ", ".join(sorted(forbidden))
            )
        for key, child in value.items():
            _reject_output_execution_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_output_execution_keys(child, f"{path}[{index}]")


def _reject_simulated_portfolio_metrics(value: object, path: str = "packet") -> None:
    if isinstance(value, Mapping):
        forbidden = _SIMULATED_PORTFOLIO_KEYS.intersection(value)
        if forbidden:
            raise ValueError(
                f"Simulated portfolio metric is not allowed at {path}: "
                + ", ".join(sorted(forbidden))
            )
        for key, child in value.items():
            _reject_simulated_portfolio_metrics(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_simulated_portfolio_metrics(child, f"{path}[{index}]")


def _reject_assessment_values(value: object, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        if value.get("available") is False and value.get("value_text") is not None:
            raise ValueError(
                f"Unavailable assessment cannot carry a numeric placeholder at {path}"
            )
        for key, child in value.items():
            if key == "value_text" and child is not None:
                raise ValueError(
                    f"Legacy packet has no approved assessment value at {path}.{key}"
                )
            _reject_assessment_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_assessment_values(child, f"{path}[{index}]")


def _reject_internal_stage_tokens(
    value: object,
    *,
    path: str,
) -> None:
    if isinstance(value, str):
        if _INTERNAL_STAGE_TOKEN.search(value):
            raise ValueError(
                f"User-facing product payload contains an internal stage "
                f"token at {path}"
            )
    elif isinstance(value, Mapping):
        for key, child in value.items():
            if key == "evidence_refs":
                continue
            _reject_internal_stage_tokens(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_internal_stage_tokens(child, path=f"{path}[{index}]")


def _verify_evidence_files(
    root: Path,
    evidence: list[dict[str, Any]],
) -> None:
    project_root = root.resolve()
    for record in evidence:
        relative = Path(record["path"].replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Evidence path must remain inside the project root")
        target = (project_root / relative).resolve()
        if not target.is_relative_to(project_root):
            raise ValueError("Evidence path escapes the project root")
        if not target.is_file():
            raise ValueError(f"Missing evidence file: {record['path']}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != record["sha256"]:
            raise ValueError(
                f"Evidence hash mismatch for {record['path']}: "
                f"expected {record['sha256']}, got {actual}"
            )


def _evidence_records(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    audit = _required_mapping(packet.get("audit"), "audit")
    if audit.get("action") != ACTION_NO_ORDER:
        raise ValueError("audit.action must remain no_order")
    artifacts = _required_list(audit.get("artifacts"), "audit.artifacts")
    if not artifacts:
        raise ValueError("Pinned audit evidence is required")

    records: list[dict[str, Any]] = []
    for index, raw_artifact in enumerate(artifacts, 1):
        artifact = _required_mapping(raw_artifact, "audit artifact")
        if artifact.get("action") != ACTION_NO_ORDER:
            raise ValueError("Every audit artifact must remain no_order")
        sha256 = _required_text(artifact.get("sha256"), "artifact sha256").lower()
        if not _SHA256.fullmatch(sha256):
            raise ValueError("Artifact sha256 must be SHA-256 hex")
        records.append(
            {
                "evidence_id": f"source-{index:02d}",
                "title": _required_text(artifact.get("label"), "artifact label"),
                "artifact_type": "pinned_artifact",
                "path": _required_text(artifact.get("path"), "artifact path"),
                "sha256": sha256,
                "available_at": None,
                "action": ACTION_NO_ORDER,
            }
        )
    return records


def _evidence_ref(
    evidence: list[dict[str, Any]],
    path_suffix: str,
) -> str:
    normalized_suffix = path_suffix.replace("\\", "/")
    matches = [
        record["evidence_id"]
        for record in evidence
        if record["path"].replace("\\", "/").endswith(normalized_suffix)
    ]
    if len(matches) != 1:
        raise ValueError(f"Required evidence is missing: {path_suffix}")
    return matches[0]


def _unavailable_assessment(
    *,
    status: str,
    reason: str,
    needed: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "available": False,
        "value_text": None,
        "unavailable_reason": reason,
        "needed_evidence": needed,
        "evidence_refs": evidence_refs,
    }


def _m2_rows(packet: Mapping[str, Any]) -> tuple[Mapping[str, Any], list[dict[str, Any]]]:
    m2 = _required_mapping(packet.get("m2"), "m2")
    _require_status(m2.get("status"), _STAGE_STATUS_CODES["m2"], "m2.status")
    _require_status(
        m2.get("checkpoint_a_status"),
        frozenset({"HUMAN_PASS", "PENDING_HUMAN_REVIEW", "NOT_APPROVED"}),
        "m2.checkpoint_a_status",
    )
    _require_status(
        m2.get("acceptance_status"),
        frozenset({"HUMAN_PASS", "PENDING_HUMAN_REVIEW", "NOT_APPROVED"}),
        "m2.acceptance_status",
    )
    if m2.get("status") == "DONE" and m2.get("checkpoint_a_status") != "HUMAN_PASS":
        raise ValueError("M2 completion requires a bound HUMAN_PASS status")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed_channels = frozenset(_CHANNEL_LABELS)
    for raw_row in _required_list(m2.get("rows"), "m2.rows"):
        row = _required_mapping(raw_row, "m2 row")
        symbol = _required_symbol(row.get("symbol"), "m2 row symbol")
        if symbol in seen:
            raise ValueError("M2 rows must use unique symbols")
        seen.add(symbol)
        channel = _required_text(row.get("channel"), "m2 row channel")
        if channel not in allowed_channels:
            raise ValueError(f"Unsupported m2 row channel: {channel}")
        rows.append(
            {
                "symbol": symbol,
                "name": _required_text(row.get("name"), "m2 row name"),
                "channel": channel,
                "status": _require_status(
                    row.get("status"),
                    _M2_ROW_STATUSES,
                    "m2 row status",
                ),
                "reason": _required_text(row.get("reason"), "m2 row reason"),
                "evidence_count": _non_negative_int(
                    row.get("evidence_count"),
                    "m2 row evidence_count",
                ),
            }
        )
    if not rows:
        raise ValueError("Missing M2 evidence rows")

    counts = {
        key: _non_negative_int(m2.get(key), f"m2.{key}")
        for key in (
            "lead_count",
            "verified_count",
            "rejected_count",
            "insufficient_count",
            "unsupported_count",
        )
    }
    if sum(
        counts[key]
        for key in (
            "verified_count",
            "rejected_count",
            "insufficient_count",
            "unsupported_count",
        )
    ) != counts["lead_count"]:
        raise ValueError("M2 row status counts are inconsistent")
    if counts["lead_count"] != len(rows):
        raise ValueError("M2 rows do not match the reported lead count")
    return m2, rows


def _m3_cards(packet: Mapping[str, Any]) -> tuple[Mapping[str, Any], list[dict[str, Any]]]:
    m3 = _required_mapping(packet.get("m3"), "m3")
    _require_status(m3.get("status"), _STAGE_STATUS_CODES["m3"], "m3.status")
    _require_status(
        m3.get("checkpoint_b_status"),
        frozenset({"NOT_APPROVED_YET", "PENDING_HUMAN_REVIEW", "APPROVED"}),
        "m3.checkpoint_b_status",
    )
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_card in _required_list(m3.get("negative_cards"), "m3.negative_cards"):
        card = _required_mapping(raw_card, "m3 negative card")
        symbol = _required_symbol(card.get("symbol"), "m3 card symbol")
        if symbol in seen:
            raise ValueError("M3 cards must use unique symbols")
        seen.add(symbol)
        status = _require_status(
            card.get("status"),
            frozenset({"INSUFFICIENT_RESEARCH"}),
            "m3 card status",
        )
        reason_kind = _require_status(
            card.get("reason_kind"),
            frozenset({"RESEARCH_INCOMPLETE"}),
            "m3 card reason_kind",
        )
        blockers = _required_list(card.get("blockers"), "m3 card blockers")
        if not blockers:
            raise ValueError("M3 negative cards require blockers")
        cards.append(
            {
                "symbol": symbol,
                "name": _required_text(card.get("name"), "m3 card name"),
                "status": status,
                "reason_kind": reason_kind,
                "blockers": [
                    _required_text(blocker, "m3 blocker") for blocker in blockers
                ],
            }
        )
    if not cards:
        raise ValueError("M3 negative cards are required")
    return m3, cards


def _m4_stage(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    m4 = _required_mapping(packet.get("m4"), "m4")
    _require_status(m4.get("status"), _STAGE_STATUS_CODES["m4"], "m4.status")
    private_status = _required_text(
        m4.get("private_input_status"),
        "m4.private_input_status",
    )
    if private_status not in _STAGE_STATUS_CODES["m4"]:
        raise ValueError(f"Unsupported m4.private_input_status: {private_status}")
    if private_status != "PENDING_USER_PRIVATE_INPUT":
        raise ValueError("M4 private input must remain pending")
    if m4.get("new_capacity_available") is not False:
        raise ValueError("M4 simulated capacity cannot be presented as available")
    return m4


def _m5_items(packet: Mapping[str, Any]) -> tuple[Mapping[str, Any], list[dict[str, Any]]]:
    m5 = _required_mapping(packet.get("m5"), "m5")
    _require_status(m5.get("status"), _STAGE_STATUS_CODES["m5"], "m5.status")
    _require_status(
        m5.get("continuous_ops_status"),
        frozenset({"READY", "NOT_READY", "DEGRADED", "BLOCKED"}),
        "m5.continuous_ops_status",
    )
    items: list[dict[str, Any]] = []
    for raw_item in _required_list(m5.get("pending_items"), "m5.pending_items"):
        item = _required_mapping(raw_item, "m5 pending item")
        items.append(
            {
                "symbol": _required_symbol(item.get("symbol"), "m5 item symbol"),
                "announcement_id": _required_text(
                    item.get("announcement_id"),
                    "m5 item announcement_id",
                ),
                "title": _required_text(item.get("title"), "m5 item title"),
                "disposition": _require_status(
                    item.get("disposition"),
                    frozenset({"PENDING_HUMAN_REVIEW"}),
                    "m5 item disposition",
                ),
            }
        )
    return m5, items


def _m6_packet(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    m6 = _required_mapping(packet.get("m6"), "m6")
    _require_status(m6.get("status"), _STAGE_STATUS_CODES["m6"], "m6.status")
    _require_status(
        m6.get("engineering_status"),
        frozenset({"DONE", "PARTIAL", "NOT_STARTED", "BLOCKED"}),
        "m6.engineering_status",
    )
    _require_status(
        m6.get("operational_status"),
        frozenset({"NOT_STARTED", "OPERATIONAL_NOT_STARTED"}),
        "m6.operational_status",
    )
    blockers = _required_list(m6.get("blockers"), "m6.blockers")
    return {**m6, "blockers": [_required_text(item, "m6 blocker") for item in blockers]}


def _stages(
    packet: Mapping[str, Any],
    m2: Mapping[str, Any],
    m3: Mapping[str, Any],
    m4: Mapping[str, Any],
    m5: Mapping[str, Any],
    m6: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    details = {
        "m2": (
            f"{m2['lead_count']} 条线索已完成二阶段结论；"
            f"{m2['verified_count']} 条进入深入研究。"
        ),
        "m3": f"{len(_required_list(m3.get('negative_cards'), 'm3.negative_cards'))} 家公司仍待补齐研究证据。",
        "m4": "未接入真实个人组合，模拟结果不会显示为个人指标。",
        "m5": f"{len(_required_list(m5.get('pending_items'), 'm5.pending_items'))} 条披露等待人工复核。",
        "m6": f"运营预检完成，仍有 {len(_required_list(m6.get('blockers'), 'm6.blockers'))} 项阻断。",
    }
    statuses = {
        "m2": m2.get("status"),
        "m3": m3.get("status"),
        "m4": m4.get("private_input_status"),
        "m5": m5.get("status"),
        "m6": m6.get("operational_status") if m6.get("status") == "PREFLIGHT_DONE" else "NOT_STARTED",
    }
    return {
        key: {
            "status": _require_status(
                statuses[key],
                _STAGE_STATUS_CODES[key],
                f"stages.{key}.status",
            ),
            "detail": details[key],
        }
        for key in ("m2", "m3", "m4", "m5", "m6")
    }


def _opportunities(
    rows: list[dict[str, Any]],
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "symbol": row["symbol"],
            "company_name": row["name"],
            "why_now": (
                f"{_CHANNEL_LABELS[row['channel']]}已完成二阶段验证；"
                f"关联证据记录 {row['evidence_count']} 项。"
            ),
            "research_status": row["status"],
            "valuation_status": "NOT_READY",
            "dividend_status": "NOT_READY",
            "price_status": "WAIT",
            "main_risk": "该记录只反映初步筛选状态，不代表估值、价格或交易结论。",
            "next_trigger": _M2_NEXT_TRIGGERS[row["status"]],
            "evidence_refs": evidence_refs,
            "action": ACTION_NO_ORDER,
        }
        for row in rows
    ]


def _companies(
    cards: list[dict[str, Any]],
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    companies: list[dict[str, Any]] = []
    for card in cards:
        unavailable = _unavailable_assessment(
            status="NOT_READY",
            reason="深入研究尚未给出经人工批准的该字段结论。",
            needed="经人工批准的已验证字段结论。",
            evidence_refs=evidence_refs,
        )
        companies.append(
            {
                "symbol": card["symbol"],
                "company_name": card["name"],
                "research_status": "NEED_MORE_EVIDENCE",
                "price": _unavailable_assessment(
                    status="UNAVAILABLE",
                    reason="深入研究尚未给出经人工批准的当前价格结论。",
                    needed="与同一研究时点绑定的已验证价格证据。",
                    evidence_refs=evidence_refs,
                ),
                "valuation": unavailable,
                "margin_of_safety": _unavailable_assessment(
                    status="NOT_READY",
                    reason="深入研究尚未完成，不能形成安全边际结论。",
                    needed="经人工批准的已验证估值输入与估值结论。",
                    evidence_refs=evidence_refs,
                ),
                "dividend": _unavailable_assessment(
                    status="NOT_READY",
                    reason="深入研究尚未给出经人工批准的股息结论。",
                    needed="经人工批准的已验证股息证据与结论。",
                    evidence_refs=evidence_refs,
                ),
                "sections": [
                    {
                        "key": key,
                        "status": "BLOCKED",
                        "summary": "深入研究尚未完成，该模块没有经批准的可用结论。",
                        "evidence_refs": evidence_refs,
                    }
                    for key in _COMPANY_SECTION_KEYS
                ],
                "scenarios": [
                    {
                        "key": key,
                        "assessment": _unavailable_assessment(
                            status="NOT_READY",
                            reason="深入研究尚未提供经人工批准的情景输入。",
                            needed="经人工批准的已验证情景假设与结论。",
                            evidence_refs=evidence_refs,
                        ),
                    }
                    for key in _SCENARIO_KEYS
                ],
                "latest_change": "深入研究尚未完成，当前没有经批准的完整结论。",
                "next_trigger": "完成研究阻断并取得人工研究批准后重新生成。",
                "original_thesis": "当前候选包未包含经人工批准的原始投资逻辑。",
                "thesis_change": "UNKNOWN",
                "evidence_refs": evidence_refs,
                "action": ACTION_NO_ORDER,
            }
        )
    return companies


def _today_items(
    *,
    m2: Mapping[str, Any],
    m3_cards: list[dict[str, Any]],
    m5_items: list[dict[str, Any]],
    m6: Mapping[str, Any],
    symbol_names: Mapping[str, str],
    m2_refs: list[str],
    m3_refs: list[str],
    m5_refs: list[str],
    m6_refs: list[str],
    daily_quote: Mapping[str, Any] | None = None,
    daily_quote_refs: list[str] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if daily_quote is not None:
        quotes = _required_list(daily_quote.get("quotes"), "daily_quote.quotes")
        rendered = "；".join(
            f"{_required_text(item.get('symbol'), 'daily_quote.symbol')} {item.get('price')} 元"
            for item in quotes
            if isinstance(item, Mapping)
        )
        if not rendered or not daily_quote_refs:
            raise ValueError("daily_quote evidence is incomplete")
        items.append(
            {
                "category": "MARKET_DATA",
                "company": "市场数据",
                "what_happened": f"{daily_quote['as_of']} 收盘行情已双源校验：{rendered}。",
                "why_it_matters": "行情只用于展示与后续价格桥接，不会修改内在价值、研究结论或交易状态。",
                "current_status": "当前行情已归档，仍需与可用研究结论分别判断。",
                "next_step": "仅在研究、估值与价格桥接均满足门槛时进入人工复核。",
                "evidence_refs": daily_quote_refs,
            }
        )
    for item in m5_items:
        items.append(
            {
                "category": "EVENT",
                "company": symbol_names.get(item["symbol"], item["symbol"]),
                "symbol": item["symbol"],
                "what_happened": item["title"],
                "why_it_matters": "该披露已进入人工复核队列，当前尚未形成材料性结论。",
                "current_status": "等待人工复核。",
                "next_step": "人工查看公告并决定是否需要后续研究。",
                "evidence_refs": m5_refs,
            }
        )
    for card in m3_cards:
        items.append(
            {
                "category": "RESEARCH_CHANGE",
                "company": card["name"],
                "symbol": card["symbol"],
                "what_happened": "公司研究结论仍为证据不足。",
                "why_it_matters": "尚不能形成可用于估值或股息判断的批准结论。",
                "current_status": "研究复核尚未完成。",
                "next_step": "补齐研究阻断后重新进入复核。",
                "evidence_refs": m3_refs,
            }
        )
    if m6["blockers"]:
        items.append(
            {
                "category": "DATA_ISSUE",
                "company": "系统",
                "what_happened": "运营预检已完成，但真实监控尚未开始。",
                "why_it_matters": "运营门尚未满足，系统继续只读运行。",
                "current_status": "真实监控尚未开始。",
                "next_step": "完成预检阻断并取得真实运营授权后重新评估。",
                "evidence_refs": m6_refs,
            }
        )
    items.append(
        {
            "category": "RESEARCH_CHANGE",
            "company": "初步筛选",
            "what_happened": (
                f"初步筛选已完成 {m2['lead_count']} 条线索的二阶段结论："
                f"{m2['verified_count']} 条进入深入研究，"
                f"{m2['rejected_count']} 条未通过，"
                f"{m2['insufficient_count']} 条证据不足。"
            ),
            "why_it_matters": "流程完成不等于存在投资机会或交易结论。",
            "current_status": "初步筛选流程已通过人工复核。",
            "next_step": "继续等待有证据支持的研究队列更新。",
            "evidence_refs": m2_refs,
        }
    )
    return items


def _m6_event(m6_refs: list[str]) -> dict[str, Any]:
    return {
        "event_id": "m6-operational-preflight",
        "event_type": "SYSTEM_DATA_RISK",
        "company_name": "系统",
        "what_happened": "运营预检已完成，但真实监控尚未开始。",
        "impact_area": "真实监控与运营准备。",
        "current_conclusion": "运营门尚未满足，系统保持只读状态。",
        "research_action": "PENDING_REVIEW",
        "next_step": "完成预检阻断并取得真实运营授权后重新评估。",
        "evidence_refs": m6_refs,
        "action": ACTION_NO_ORDER,
    }


def validate_product_workbench_candidate_payload(
    payload: Mapping[str, Any],
) -> None:
    """Reject execution semantics or placeholder assessment values."""

    _reject_output_execution_keys(payload)
    _reject_assessment_values(payload)
    for section in _USER_VISIBLE_SECTIONS:
        _reject_internal_stage_tokens(payload.get(section), path=section)


def build_product_workbench_candidate_payload(
    packet: Mapping[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    """Build a fail-closed product payload from one verified legacy packet."""

    if not isinstance(root, Path):
        raise ValueError("root must be a pathlib.Path")
    packet = _required_mapping(packet, "legacy M7 packet")
    _reject_active_execution_keys(packet)
    _reject_simulated_portfolio_metrics(packet)
    if packet.get("schema_version") != LEGACY_PACKET_SCHEMA_VERSION:
        raise ValueError("Unsupported legacy M7 packet schema")
    if packet.get("action") != ACTION_NO_ORDER:
        raise ValueError("Legacy M7 packet must remain no_order")

    m2, rows = _m2_rows(packet)
    m3, m3_cards = _m3_cards(packet)
    m4 = _m4_stage(packet)
    m5, m5_items = _m5_items(packet)
    m6 = _m6_packet(packet)
    evidence = _evidence_records(packet)
    _verify_evidence_files(root, evidence)

    m2_refs = [
        _evidence_ref(evidence, "m2-channel-verification-20260924-v2/report.json"),
        _evidence_ref(evidence, "m2-live-20260923-v3/manifest.json"),
    ]
    m3_refs = [
        _evidence_ref(
            evidence,
            "m3-decision-acceptance-audit-20260924T062947Z/receipt.json",
        ),
        _evidence_ref(evidence, "m1-post-review-20260923T114228Z/integrated-runs.json"),
    ]
    m5_refs = [
        _evidence_ref(
            evidence,
            "m5-human-review-reconciliation-20260924-v1/pending-queue.json",
        )
    ]
    m6_refs = [
        _evidence_ref(
            evidence,
            "m6-operational-preflight-20260924T050357Z/receipt.json",
        )
    ]
    daily_quote = packet.get("daily_quote")
    daily_quote_refs = (
        [_evidence_ref(evidence, _required_text(daily_quote.get("bundle_path"), "daily_quote.bundle_path"))]
        if isinstance(daily_quote, Mapping)
        else []
    )
    symbol_names = {row["symbol"]: row["name"] for row in rows}
    symbol_names.update({card["symbol"]: card["name"] for card in m3_cards})
    today_items = _today_items(
        m2=m2,
        m3_cards=m3_cards,
        m5_items=m5_items,
        m6=m6,
        symbol_names=symbol_names,
        m2_refs=m2_refs,
        m3_refs=m3_refs,
        m5_refs=m5_refs,
        m6_refs=m6_refs,
        daily_quote=daily_quote if isinstance(daily_quote, Mapping) else None,
        daily_quote_refs=daily_quote_refs,
    )
    pending_count = len(m3_cards) + len(m5_items) + int(bool(m6["blockers"]))
    payload = {
        "schema_version": PRODUCT_PAYLOAD_SCHEMA_VERSION,
        "generated_at": _required_text(packet.get("generated_at"), "generated_at"),
        "as_of": _required_text(packet.get("as_of"), "as_of"),
        "action": ACTION_NO_ORDER,
        "overview": {"pending_count": pending_count},
        "system_health": {
            "status": "EVIDENCE_INSUFFICIENT",
            "message": "部分研究、事件和运营状态仍待人工复核；未接入真实组合。",
        },
        "stages": _stages(packet, m2, m3, m4, m5, m6),
        "audit": {"evidence": evidence},
        "today_items": today_items,
        "opportunities": _opportunities(rows, m2_refs),
        "companies": _companies(m3_cards, m3_refs),
        "portfolio": {
            "real_data_available": False,
            "status": "PENDING_USER_PRIVATE_INPUT",
            "connection_hint": (
                "尚未收到真实个人组合输入；模拟演练结果不会显示为个人指标。"
            ),
            "summary": [],
            "positions": [],
            "action": ACTION_NO_ORDER,
        },
        "events": [_m6_event(m6_refs)],
    }
    validate_product_workbench_candidate_payload(payload)
    return payload


__all__ = [
    "ACTION_NO_ORDER",
    "LEGACY_PACKET_SCHEMA_VERSION",
    "PRODUCT_PAYLOAD_SCHEMA_VERSION",
    "build_product_workbench_candidate_payload",
    "validate_product_workbench_candidate_payload",
]

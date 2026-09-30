"""Project the pinned legacy M7 daily packet into the product workbench payload.

This module performs no investment reasoning. It copies closed M2-M6 states,
fails closed on unsupported or unsafe input, and leaves unsupported product
assessments explicitly unavailable for the presentation read model to render.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from typing import Any, Mapping

from .prospective_observation import load_verified_observation_ledger
from .public_event_projection import project_public_event_projection_as_of


LEGACY_PACKET_SCHEMA_VERSION = "m7-daily-workbench-v1"
PRODUCT_PAYLOAD_SCHEMA_VERSION = "m7-product-workbench-v1"
ACTION_NO_ORDER = "no_order"
PROSPECTIVE_SNAPSHOT_SCHEMA_VERSION = "prospective-baseline-snapshot-v2"
_PROSPECTIVE_SNAPSHOT_PINS = {
    "config/prospective-baseline-publication-v6.json": (
        "prospective-baseline-publication-v6", "prospective-snapshot-pin-v6",
    ),
    "config/prospective-baseline-publication-v7.json": (
        "prospective-baseline-publication-v7", "prospective-snapshot-pin-v7",
    ),
}
_BASELINE_DISPLAY_PREFIXES = {
    "BASELINE_PARTIAL": "研究进行中",
    "EXPLICIT_NOT_READY": "关键证据未齐",
    "PARTIAL:": "仍在核验：",
    "DATA_INCOMPLETE:": "资料不足：",
    "MODEL_NOT_READY:": "模型尚不可运行：",
    "CYCLICAL_MODEL_NOT_READY:": "周期模型尚不可运行：",
    "NOT_ESTABLISHED.": "尚未形成可证实的判断。",
}
_PROSPECTIVE_NEXT_STEPS = {
    "next official financial filing with cash-flow, capital-allocation and share disclosures":
        "下一份官方财报：核对现金流、资本配置与股本披露。",
    "next statutory financial report or material dividend/buyback filing":
        "跟踪下一份法定财报，或新的分红、回购重要披露。",
    "next official financial report or material coal/power/capital-allocation filing":
        "跟踪下一份官方财报，或煤炭、电力及资本配置的重要披露。",
}


def _baseline_display_text(value: str) -> str:
    rendered = value
    for prefix, readable in _BASELINE_DISPLAY_PREFIXES.items():
        if rendered.startswith(prefix):
            rendered = readable + rendered[len(prefix):]
            break
    rendered = rendered.replace(
        "existing segment facts do not establish verified FCFF scope, share denominator, capex split or WACC.",
        "现有分部数据尚不能确认自由现金流口径、股数范围、资本开支拆分或折现率（WACC）。",
    )
    rendered = re.sub(r"\bunverified\b", "尚未核实", rendered, flags=re.IGNORECASE)
    return re.sub(r"\bverified\b", "已核实", rendered, flags=re.IGNORECASE)

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
            "PARKED_WAITING_R2_NONBLOCKING",
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
    "VERIFIED_FOR_DEEP_RESEARCH": "进入深入研究，补齐关键经营证据并核验来源。",
    "REJECTED_AFTER_VERIFICATION": "仅在出现新的实质证据后重新评估。",
    "INSUFFICIENT_EVIDENCE": "补齐该通道的关键证据后重新评估。",
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


def _validate_m5_projection_availability(projection: Mapping[str, Any]) -> None:
    """Reject evidence that was unavailable at the projection's declared cutoff."""
    cutoff_value = projection.get("evaluation_cutoff_date")
    if cutoff_value is None:
        return
    if not isinstance(cutoff_value, str):
        raise ValueError("M5 projection evaluation cutoff must be an ISO date")
    try:
        cutoff = date.fromisoformat(cutoff_value)
    except ValueError as error:
        raise ValueError("M5 projection evaluation cutoff must be an ISO date") from error
    _, exclusions = project_public_event_projection_as_of(projection, cutoff)
    if exclusions:
        raise ValueError("M5 projection contains evidence unavailable by evaluation cutoff")


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
    if private_status not in {
        "PENDING_USER_PRIVATE_INPUT",
        "PARKED_WAITING_R2_NONBLOCKING",
    }:
        raise ValueError("M4 private input must remain parked or pending")
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
        "m4": "个性化组合分析已暂停，不影响公共研究。",
        "m5": f"历史事件队列有 {len(_required_list(m5.get('pending_items'), 'm5.pending_items'))} 条披露尚未完成材料性判定。",
        "m6": f"运营预检完成，仍有 {len(_required_list(m6.get('blockers'), 'm6.blockers'))} 项阻断。",
    }
    statuses = {
        "m2": m2.get("status"),
        "m3": m3.get("status"),
        "m4": "PARKED_WAITING_R2_NONBLOCKING",
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
            reason="当前缺少足以形成该字段结论的已验证证据。",
            needed="补齐原始来源、报告期和口径，并完成交叉核验。",
            evidence_refs=evidence_refs,
        )
        companies.append(
            {
                "symbol": card["symbol"],
                "company_name": card["name"],
                "research_status": "NEED_MORE_EVIDENCE",
                "decision_process": [
                    {
                        "key": key,
                        "status": "BLOCKED",
                        "reason": reason,
                        "next_action": next_action,
                        "evidence_refs": evidence_refs,
                    }
                    for key, reason, next_action in (
                        ("financial_facts", "候选包没有提供已准入的财务事实及时间点核验结果。", "绑定原始财报、事实口径与 available_at，并完成事实准入。"),
                        ("business_quality", "候选包没有提供已验证的商业质量审查。", "审查竞争优势、现金转换、资本配置、负债和最强反证。"),
                        ("model_applicability", "尚无与当前公司经济结构绑定的模型适用性结果。", "通过公司 profile 和模型路由确认适用模型；不默认采用 FCFF。"),
                        ("valuation", "尚无与已准入事实及假设绑定的 Bear/Base/Bull 结果。", "由适用共享模型生成情景估值、置信度和敏感性。"),
                        ("price_bridge", "没有与当前估值、模型有效性绑定的已验证价格桥接。", "核验价格日期、证券及股本口径、重大事件和 ModelValidity。"),
                        ("research_gate", "候选身份不等于研究门通过，当前没有绑定估值的正式门禁结果。", "评估证据、财务、论点及估值门，保留反证和 blockers。"),
                        ("portfolio_gate", "候选包没有提供用户投资政策和账户约束的组合门结果。", "提供人工确认的投资政策及组合快照；未提供时不输出个性化仓位。"),
                        ("decision_gate", "关键前置门尚未通过，当前建议为 NOT_READY，不产生买卖指令。", "前置结果准入后再计算可解释的人工复核状态，保持 action=no_order。"),
                    )
                ],
                "price": _unavailable_assessment(
                    status="UNAVAILABLE",
                    reason="没有与当前研究时点绑定的已验证价格证据。",
                    needed="补齐同一交易会话、可追溯来源的价格证据。",
                    evidence_refs=evidence_refs,
                ),
                "valuation": unavailable,
                "margin_of_safety": _unavailable_assessment(
                    status="NOT_READY",
                    reason="估值尚未就绪，不能形成安全边际结论。",
                    needed="先补齐估值模型所需事实与可验证假设。",
                    evidence_refs=evidence_refs,
                ),
                "dividend": _unavailable_assessment(
                    status="NOT_READY",
                    reason="当前缺少足以判断股息状态的证据。",
                    needed="核实分红实施、现金覆盖及债务和资本开支约束。",
                    evidence_refs=evidence_refs,
                ),
                "sections": [
                    {
                        "key": key,
                        "status": "BLOCKED",
                        "summary": "研究证据尚不足以形成该模块的可用结论。",
                        "evidence_refs": evidence_refs,
                    }
                    for key in _COMPANY_SECTION_KEYS
                ],
                "scenarios": [
                    {
                        "key": key,
                        "assessment": _unavailable_assessment(
                            status="NOT_READY",
                            reason="当前缺少已验证的情景输入。",
                            needed="补齐情景所需经营事实并说明关键假设依据。",
                            evidence_refs=evidence_refs,
                        ),
                    }
                    for key in _SCENARIO_KEYS
                ],
                "latest_change": "当前研究证据不足，尚未形成完整结论。",
                "next_trigger": "补齐关键原始证据并完成口径核验后重新评估。",
                "original_thesis": "当前候选包尚未形成可验证的完整投资逻辑。",
                "thesis_change": "UNKNOWN",
                "evidence_refs": evidence_refs,
                "action": ACTION_NO_ORDER,
            }
        )
    return companies


def _project_prospective_baseline(
    payload: dict[str, Any], *, root: Path, snapshot_path: Path, snapshot_sha256: str,
    daily_quote: Mapping[str, Any] | None = None,
    daily_quote_refs: list[str] | None = None,
) -> None:
    if not isinstance(snapshot_path, Path) or not isinstance(snapshot_sha256, str) or not _SHA256.fullmatch(snapshot_sha256):
        raise ValueError("Prospective snapshot requires a path and SHA-256")
    project_root = root.resolve()
    target = (project_root / snapshot_path).resolve()
    if not target.is_relative_to(project_root / "runtime") or not target.is_file():
        raise ValueError("Prospective snapshot path must be an existing runtime file")
    raw = target.read_bytes()
    if hashlib.sha256(raw).hexdigest() != snapshot_sha256:
        raise ValueError("Prospective snapshot SHA-256 mismatch")
    snapshot = _required_mapping(json.loads(raw), "prospective snapshot")
    if snapshot.get("schema_version") != PROSPECTIVE_SNAPSHOT_SCHEMA_VERSION or snapshot.get("action") != ACTION_NO_ORDER:
        raise ValueError("Unsupported prospective snapshot or action")
    if (
        snapshot.get("registration_time_assurance") != "PROCESS_CLOCK_ONLY_UNATTESTED"
        or snapshot.get("strict_pit_admissible") is not False
    ):
        raise ValueError("Prospective snapshot must disclose its unattested process-clock boundary")
    snapshot_relative = target.relative_to(project_root).as_posix()
    matched_pin: tuple[str, str, bytes, dict[str, Any]] | None = None
    for relative_pin_path, (schema_version, evidence_id) in _PROSPECTIVE_SNAPSHOT_PINS.items():
        candidate_path = project_root / relative_pin_path
        if not candidate_path.is_file():
            continue
        candidate_raw = candidate_path.read_bytes()
        candidate = _required_mapping(
            json.loads(candidate_raw), "prospective snapshot publication pin"
        )
        if (
            candidate.get("schema_version") == schema_version
            and candidate.get("action") == ACTION_NO_ORDER
            and candidate.get("snapshot_path") == snapshot_relative
            and candidate.get("snapshot_sha256") == snapshot_sha256
            and candidate.get("registration_receipt_sha256") == snapshot.get("registration_receipt_sha256")
            and candidate.get("baseline_input_sha256") == snapshot.get("baseline_input_sha256")
        ):
            if matched_pin is not None:
                raise ValueError("Prospective snapshot matches multiple publication pins")
            matched_pin = (relative_pin_path, evidence_id, candidate_raw, candidate)
    if matched_pin is None:
        raise ValueError("Prospective snapshot is not the repository-pinned verified baseline")
    pin_relative_path, pin_ref, pin_raw, _ = matched_pin
    cards = _required_list(snapshot.get("cards"), "prospective cards")
    prospective_companies = {
        card.get("symbol"): card.get("company")
        for card in cards
        if isinstance(card, dict)
    }
    if (
        len(cards) != 3
        or len(prospective_companies) != len(cards)
        or any(
            not isinstance(symbol, str) or not isinstance(company, str)
            for symbol, company in prospective_companies.items()
        )
    ):
        raise ValueError("Prospective snapshot issuer count mismatch")
    existing = {card["symbol"]: card for card in payload["companies"]}
    seen: set[str] = set()
    snapshot_ref = "prospective-snapshot-v2"
    payload["audit"]["evidence"].append({
        "evidence_id": snapshot_ref, "title": "Prospective baseline snapshot",
        "artifact_type": "pinned_artifact", "path": snapshot_relative,
        "sha256": snapshot_sha256,
        "available_at": datetime.fromisoformat(
            _required_text(snapshot.get("built_at"), "prospective built_at")
        ).date().isoformat(),
        "action": ACTION_NO_ORDER,
    })
    pin_evidence = {
        "evidence_id": pin_ref, "title": "Prospective baseline publication pin",
        "artifact_type": "pinned_artifact", "path": pin_relative_path,
        "sha256": hashlib.sha256(pin_raw).hexdigest(),
        "available_at": datetime.fromisoformat(
            _required_text(snapshot.get("built_at"), "prospective built_at")
        ).date().isoformat(),
        "action": ACTION_NO_ORDER,
    }
    _verify_evidence_files(root, [pin_evidence])
    payload["audit"]["evidence"].append(pin_evidence)
    prospective_opportunities: list[dict[str, Any]] = []
    prospective_today_items: list[dict[str, Any]] = []
    admitted_fact_count = 0
    unadmitted_fact_count = 0
    quote_as_of: str | None = None
    quote_prices: dict[str, str] = {}
    if daily_quote is not None:
        if (
            daily_quote.get("schema_version") != "daily-quote-binding-v1"
            or daily_quote.get("action") != ACTION_NO_ORDER
        ):
            raise ValueError("Prospective quote input must be a bound no_order quote set")
        quote_as_of = _required_text(daily_quote.get("as_of"), "daily_quote.as_of")
        date.fromisoformat(quote_as_of)
        for quote in _required_list(daily_quote.get("quotes"), "daily_quote.quotes"):
            if not isinstance(quote, Mapping):
                raise ValueError("daily_quote item must be an object")
            symbol = _required_text(quote.get("symbol"), "daily_quote.symbol")
            if not _SYMBOL.fullmatch(symbol) or symbol in quote_prices:
                raise ValueError("daily_quote symbols must be unique six-digit codes")
            price_text = _required_text(quote.get("price"), "daily_quote.price")
            try:
                price = Decimal(price_text)
            except InvalidOperation as error:
                raise ValueError("daily_quote price must be a positive decimal") from error
            if not price.is_finite() or price <= 0:
                raise ValueError("daily_quote price must be a positive decimal")
            quote_prices[symbol] = price_text
        if quote_prices and not daily_quote_refs:
            raise ValueError("daily_quote evidence is incomplete")

    for raw_card in cards:
        card = _required_mapping(raw_card, "prospective card")
        symbol = _required_symbol(card.get("symbol"), "prospective symbol")
        if (symbol in seen
                or card.get("company") != prospective_companies.get(symbol)
                or card.get("case_id") != f"prospective-{symbol}-20260927-v2"):
            raise ValueError("Prospective issuer identity mismatch")
        seen.add(symbol)
        if card.get("action") != ACTION_NO_ORDER or card.get("valuation_status") != "VALUATION_NOT_READY":
            raise ValueError("Prospective card must remain valuation-not-ready and no_order")
        facts = _required_list(card.get("known_facts"), "prospective known_facts")
        unadmitted = _required_list(card.get("unadmitted_fact_ids"), "prospective unadmitted_fact_ids")
        admitted_fact_count += len(facts)
        unadmitted_fact_count += len(unadmitted)
        status = "BASELINE_PARTIAL" if facts else "EXPLICIT_NOT_READY"
        if card.get("research_status") != ("BASELINE_PARTIAL" if facts else "BASELINE_EXPLICIT_NOT_READY"):
            raise ValueError("Prospective baseline status contradicts admitted facts")
        refs = [snapshot_ref, pin_ref]
        for index, raw_fact in enumerate(facts, 1):
            fact = _required_mapping(raw_fact, "prospective fact")
            path = _required_text(fact.get("source_path"), "prospective source_path")
            digest = _required_text(fact.get("source_sha256"), "prospective source_sha256")
            if not _SHA256.fullmatch(digest):
                raise ValueError("Prospective source SHA-256 invalid")
            ref = f"prospective-{symbol}-fact-{index}"
            record = {
                "evidence_id": ref, "title": _required_text(fact.get("fact_id"), "prospective fact_id"),
                "artifact_type": "pinned_artifact", "path": path, "sha256": digest,
                "available_at": datetime.fromisoformat(
                    _required_text(fact.get("available_at"), "prospective available_at")
                ).date().isoformat(),
                "action": ACTION_NO_ORDER,
            }
            _verify_evidence_files(root, [record])
            payload["audit"]["evidence"].append(record)
            refs.append(ref)
        note = (
            f"{_baseline_display_text(status)}：前瞻基线只记录当前可核验证据，尚不支持完整研究或估值结论。"
            "登记时间仅为进程时钟、未经独立时间戳认证，不构成同期PIT证明。"
        )
        if not facts:
            note = "前瞻基线尚无已接纳事实；经营与财务结论待原始来源和发布时间核验。"
        if symbol in existing:
            company = existing[symbol]
            if company["company_name"] != card["company"]:
                raise ValueError("Prospective issuer differs from existing company card")
            company["latest_change"] += " " + note
            company["evidence_refs"] = list(dict.fromkeys([*company["evidence_refs"], *refs]))
            company["next_trigger"] += " 前瞻基线：" + _required_text(
                card.get("next_evidence_trigger"), "next_evidence_trigger"
            )
        else:
            company = _companies([{"symbol": symbol, "name": card["company"]}], refs)[0]
            company["research_status"] = "PARTIAL" if facts else "INSUFFICIENT_EVIDENCE"
            company["latest_change"] = note
            company["next_trigger"] = _required_text(card.get("next_evidence_trigger"), "next_evidence_trigger")
            company["original_thesis"] = "待形成投资逻辑；当前仅登记研究回报驱动：" + _required_text(
                card.get("return_drivers"), "return_drivers"
            )
            payload["companies"].append(company)
        summaries = {
            "business_quality": "business_quality",
            "financial_quality": "financial_quality",
            "capital_allocation": "capital_allocation",
            "valuation": "model_applicability",
            "dividend": "dividend_sustainability",
            "risks_counterevidence": "strongest_counterevidence",
        }
        for section in company["sections"]:
            key = section["key"]
            if facts:
                baseline_summary = _baseline_display_text(_required_text(card.get(summaries[key]), key))
            elif key == "valuation":
                baseline_summary = "估值模型适用性尚未完成验证，模型暂不可运行。"
            else:
                baseline_summary = "尚无可用于评价该项的已接纳证据。"
            if symbol in existing:
                section["summary"] += " 前瞻基线：" + baseline_summary
                section["evidence_refs"] = list(dict.fromkeys([*section["evidence_refs"], *refs]))
            else:
                section["status"] = "PARTIAL" if facts and key in {
                    "business_quality", "financial_quality", "capital_allocation", "risks_counterevidence"
                } else "MISSING"
                section["summary"] = baseline_summary
                section["evidence_refs"] = refs
        fact_rows = []
        for index, fact in enumerate(facts, 1):
            fact_type = _required_text(fact.get("fact_type"), "fact_type")
            fact_label = {
                "revenue": "营业收入",
                "parent_attributable_profit": "归母净利润",
                "operating_cash_flow": "经营活动现金流净额",
            }.get(fact_type, fact_type)
            unit_label = {"CNY_MILLION": "百万元", "CNY": "元", "CNY_THOUSAND": "千元"}.get(
                fact.get("unit"), _required_text(fact.get("unit"), "fact unit")
            )
            fact_rows.append(
                f"{fact.get('report_period')} {fact_label}：{fact.get('value')} {unit_label}；"
                f"可用日 {fact.get('available_at')}；证据 prospective-{symbol}-fact-{index}"
            )
        company["decision_review"] = [*company.get("decision_review", []),
            {"label": "前瞻研究画像", "value": _required_text(card.get("profile"), "profile")},
            {"label": "基线证据覆盖", "value": f"{len(facts)} 项事实已准入；{len(unadmitted)} 项待准入；{len(refs)} 个证据引用。"},
            *([{"label": "已准入财务事实", "value": "\n".join(fact_rows)}] if fact_rows else []),
            *([{"label": "中期报告保证边界", "value": "中期财务报表未经审计；注册会计师实施有限审阅，未发表审计意见。"}]
              if any(fact.get("source_assurance") == "INTERIM_UNAUDITED_LIMITED_REVIEW" for fact in facts) else []),
            {"label": "估值模型适用性", "value": _baseline_display_text(_required_text(card.get("model_applicability"), "model_applicability")) if facts else "尚无已接纳经营事实，暂不能判断估值模型是否适用。"},
            {"label": "最强反证", "value": _required_text(card.get("strongest_counterevidence"), "strongest_counterevidence") if facts else "尚无已接纳事实，反证梳理未完成。"},
            {"label": "尚缺证据", "value": "；".join(card.get("unknowns") or ["待核验"])},
        ]
        next_trigger = _required_text(card.get("next_evidence_trigger"), "next_evidence_trigger")
        next_step = _PROSPECTIVE_NEXT_STEPS.get(
            next_trigger,
            "补充核验：" + _baseline_display_text(next_trigger),
        )
        quote_price = quote_prices.get(symbol)
        quote_summary = (
            f"双源匹配收盘价 {quote_price} 元（{quote_as_of}）；"
            "估值尚未就绪，价格吸引力暂不能判断。"
            if quote_price and quote_as_of else ""
        )
        opportunity_refs = list(dict.fromkeys(
            [*refs, *(daily_quote_refs or [])] if quote_price else refs
        ))
        prospective_opportunities.append({
            "symbol": symbol,
            "company_name": card["company"],
            "why_now": "；".join(filter(None, [
                f"当前注册前瞻研究对象；已接纳 {len(facts)} 项事实，"
                f"{len(unadmitted)} 项仍待准入。",
                quote_summary,
            ])),
            "research_status": "PARTIAL" if facts else "INSUFFICIENT_EVIDENCE",
            "valuation_status": "NOT_READY",
            "dividend_status": "NOT_READY",
            "price_status": "AVAILABLE" if quote_price else "UNAVAILABLE",
            "main_risk": "估值尚未就绪；" + _baseline_display_text(
                _required_text(card.get("strongest_counterevidence"), "strongest_counterevidence")
            ),
            "next_trigger": next_step,
            "evidence_refs": opportunity_refs,
            "action": ACTION_NO_ORDER,
        })
        prospective_today_items.append({
            "category": "RESEARCH_CHANGE",
            "company": card["company"],
            "symbol": symbol,
            "what_happened": f"前瞻基线：已接纳 {len(facts)} 项事实，{len(unadmitted)} 项仍待准入。",
            "why_it_matters": "当前证据状态决定研究边界；估值未就绪，不产生买卖或仓位信号。",
            "current_status": "研究仍在进行；估值未就绪。" if facts else "尚无已接纳事实；估值未就绪。",
            "next_step": next_step,
            "evidence_refs": opportunity_refs,
        })
    if seen != set(prospective_companies):
        raise ValueError("Prospective issuer set mismatch")

    company_cards = {company["symbol"]: company for company in payload["companies"]}
    if not set(prospective_companies).issubset(company_cards):
        raise ValueError("Prospective company cards are incomplete")
    payload["companies"] = [
        company_cards[symbol] for symbol in prospective_companies
    ]

    company_order = {symbol: position for position, symbol in enumerate(prospective_companies)}
    payload["opportunities"] = sorted(
        prospective_opportunities, key=lambda item: company_order[item["symbol"]]
    )
    payload["overview"]["pending_count"] = len(prospective_opportunities)
    payload["system_health"]["message"] = (
        "当前注册研究对象为美的集团、伊利股份和中国神华；三家估值均未就绪，"
        "各自证据状态与下一步见机会页。真实个人组合未接入，系统不生成交易指令。"
    )
    payload["stages"]["m2"]["detail"] = "历史初筛批次（非当前注册研究样本）；不代表当前机会名单。"
    payload["stages"]["m3"].update({
        "status": "PARTIAL",
        "detail": (
            f"当前注册三家已接纳 {admitted_fact_count} 项基线事实，"
            f"{unadmitted_fact_count} 项待准入；研究与估值状态见机会页。"
        ),
    })

    historical_items: list[dict[str, Any]] = []
    for raw_item in payload["today_items"]:
        item = dict(raw_item)
        if item.get("category") == "EVENT":
            item["what_happened"] = "历史/旧来源披露队列：" + item["what_happened"]
            item["why_it_matters"] = "该旧队列尚未形成当前事件结论，不能视为当前注册研究的已分类事件。"
            item["current_status"] = "历史/旧来源记录，材料性尚未判定。"
            item["next_step"] = "如需纳入当前研究，先绑定原公告、可用时间和研究依赖；否则保留为历史记录。"
        elif item.get("category") == "RESEARCH_CHANGE":
            item["what_happened"] = "历史/旧来源状态：" + item["what_happened"]
            item["why_it_matters"] = "该状态来自旧研究批次，不代表当前三家注册案例。"
            item["current_status"] = "历史/旧来源记录；当前状态以机会页的前瞻基线为准。"
            item["next_step"] = "当前三家研究进度与下一项证据触发见机会页。"
        historical_items.append(item)
    legacy_event_count = sum(item.get("category") == "EVENT" for item in payload["today_items"])
    if legacy_event_count:
        payload["stages"]["m5"].update({
            "status": "PENDING_RECONCILIATION",
            "detail": f"历史/旧来源披露队列 {legacy_event_count} 条未映射为当前事件结论。",
        })
    payload["today_items"] = historical_items + prospective_today_items


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
        coverage = _required_text(daily_quote.get("coverage_status"), "daily_quote.coverage_status")
        if coverage not in {"COMPLETE", "PARTIAL"}:
            raise ValueError("daily_quote.coverage_status is unsupported")
        rendered = "；".join(
            f"{_required_text(item.get('symbol'), 'daily_quote.symbol')} {item.get('price')} 元"
            for item in quotes
            if isinstance(item, Mapping)
        )
        if not rendered or not daily_quote_refs:
            raise ValueError("daily_quote evidence is incomplete")
        missing = _required_list(daily_quote.get("missing_symbols"), "daily_quote.missing_symbols")
        excluded = _required_list(daily_quote.get("excluded_symbols"), "daily_quote.excluded_symbols")
        coverage_note = (
            f"当前登记样本报价仅部分覆盖，缺少：{'、'.join(missing)}。"
            if coverage == "PARTIAL" else "当前登记样本报价覆盖完整。"
        )
        if excluded:
            coverage_note += f"已排除非本轮样本：{'、'.join(excluded)}。"
        items.append(
            {
                "category": "MARKET_DATA",
                "company": "市场数据",
                "what_happened": f"{daily_quote['as_of']} 收盘行情双源对照：{rendered}。{coverage_note}",
                "why_it_matters": "行情只用于展示与后续价格桥接，不会修改内在价值、研究结论或交易状态。",
                "current_status": "当前行情覆盖不全，不能据此比较全部登记公司的同日价格。" if coverage == "PARTIAL" else "当前行情已归档，仍需与可用研究结论分别判断。",
                "next_step": "下一个官方完成交易日后补齐同日登记标的行情。" if coverage == "PARTIAL" else "结合已验证研究、估值和价格桥接更新状态；行情本身不构成交易信号。",
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
                "why_it_matters": "该披露尚未形成材料性结论，当前数据不足以改变研究状态。",
                "current_status": "材料性尚未判定。",
                "next_step": "核对原文、可用时间和受影响的研究依赖后再分类。",
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
                "why_it_matters": "当前证据不足以支持估值或股息判断。",
                "current_status": "研究证据尚未齐备。",
                "next_step": "补齐来源、报告期与口径可核验的关键经营事实。",
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
            "current_status": "初步筛选二阶段结论已记录。",
            "next_step": "仅在出现新的实质证据时更新筛选结果。",
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


def _project_prospective_observation_ledger(
    payload: dict[str, Any],
    *,
    root: Path,
    manifest_path: Path,
    manifest_sha256: str,
    evaluation_cutoff: datetime,
) -> None:
    """Project verified observations as research changes, never as events."""
    rows = load_verified_observation_ledger(
        root=root,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        evaluation_cutoff=evaluation_cutoff,
    )
    evidence_ids: dict[str, str] = {}
    for row in rows:
        path = (root / row["_ledger_path"]).resolve()
        relative = path.relative_to(root.resolve()).as_posix()
        evidence_id = f"prospective-observation-{row['observation_id']}"
        evidence_ids[row["observation_id"]] = evidence_id
        evidence = {
            "evidence_id": evidence_id,
            "title": f"前瞻观察记录：{row['source_document_id']}",
            "artifact_type": "pinned_artifact",
            "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "available_at": datetime.fromisoformat(row["source_available_at"]).date().isoformat(),
            "action": ACTION_NO_ORDER,
        }
        _verify_evidence_files(root, [evidence])
        payload["audit"]["evidence"].append(evidence)

    companies = {item.get("symbol"): item for item in payload["companies"]}
    opportunities = {item.get("symbol"): item for item in payload["opportunities"]}
    for row in rows:
        evidence_id = evidence_ids[row["observation_id"]]
        symbol = row.get("symbol")
        status = "观察已记录；材料性尚未判定，估值与交易状态不变。"
        title = f"{row.get('source_document_id', '公开来源')} 已进入前瞻观察账本。"
        item = {
            "category": "RESEARCH_CHANGE",
            "company": companies.get(symbol, {}).get("company_name", symbol),
            "symbol": symbol,
            "what_happened": title,
            "why_it_matters": (
                "观察记录已按截止时间纳入研究审计，但尚未形成材料性或估值结论。"
                "登记时钟未经独立认证，因此不构成严格同期PIT证明。"
            ),
            "current_status": status,
            "next_step": "完成材料性、依赖项和研究结论评估后再决定是否重开研究。",
            "evidence_refs": [evidence_id],
        }
        payload["today_items"].append(item)
        company = companies.get(symbol)
        if company is not None:
            company["evidence_refs"] = list(dict.fromkeys([*company.get("evidence_refs", []), evidence_id]))
            company["latest_change"] = f"{company.get('latest_change', '').rstrip()} {status}".strip()
        opportunity = opportunities.get(symbol)
        if opportunity is not None:
            opportunity["evidence_refs"] = list(dict.fromkeys([*opportunity.get("evidence_refs", []), evidence_id]))
            opportunity["next_trigger"] = "先完成观察材料性与依赖项评估，再更新研究状态。"

    payload["overview"]["pending_count"] += len(rows)


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
    m5_event_projection: Mapping[str, Any] | None = None,
    prospective_snapshot_path: Path | None = None,
    prospective_snapshot_sha256: str | None = None,
    prospective_observation_ledger_path: Path | None = None,
    prospective_observation_ledger_sha256: str | None = None,
    prospective_observation_evaluation_cutoff: datetime | None = None,
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
            "message": "研究、事件或运营门仍有证据缺口；未接入真实组合，系统不生成交易指令。",
        },
        "stages": _stages(packet, m2, m3, m4, m5, m6),
        "audit": {"evidence": evidence},
        "today_items": today_items,
        "opportunities": _opportunities(rows, m2_refs),
        "companies": _companies(m3_cards, m3_refs),
        "portfolio": {
            "real_data_available": False,
            "status": "PARKED_WAITING_R2_NONBLOCKING",
            "connection_hint": "个性化组合分析已暂停，不影响公共研究。",
            "summary": [],
            "positions": [],
            "action": ACTION_NO_ORDER,
        },
        "events": [_m6_event(m6_refs)],
    }
    if m5_event_projection is not None:
        projection = _required_mapping(m5_event_projection, "m5_event_projection")
        if projection.get("action") != ACTION_NO_ORDER:
            raise ValueError("M5 event projection must remain no_order")
        projected_events = _required_list(projection.get("events"), "m5_event_projection.events")
        projected_evidence = _required_list(
            projection.get("audit_evidence"), "m5_event_projection.audit_evidence"
        )
        _validate_m5_projection_availability(projection)
        decisions = _required_list(
            projection.get("audit_decisions"), "m5_event_projection.audit_decisions"
        )
        decision_ids = [item.get("event_id") for item in decisions]
        projected_ids = [item.get("event_id") for item in projected_events]
        if (len(decision_ids) != len(set(decision_ids))
                or len(projected_ids) != len(set(projected_ids))
                or set(projected_ids) != {
                    item["event_id"] for item in decisions if item.get("visible") is True
                }
                or any(item.get("action") != ACTION_NO_ORDER for item in decisions)):
            raise ValueError("M5 visible events differ from audited dispositions")
        _verify_evidence_files(root, projected_evidence)
        if {item["evidence_id"] for item in projected_evidence} & {
            item["evidence_id"] for item in evidence
        }:
            raise ValueError("M5 projection reuses an existing evidence id")
        payload["audit"]["evidence"].extend(projected_evidence)
        payload["audit"]["event_decisions"] = decisions
        payload["events"].extend(projected_events)
    if prospective_snapshot_path is not None or prospective_snapshot_sha256 is not None:
        _project_prospective_baseline(
            payload, root=root, snapshot_path=prospective_snapshot_path,
            snapshot_sha256=prospective_snapshot_sha256,
            daily_quote=daily_quote if isinstance(daily_quote, Mapping) else None,
            daily_quote_refs=daily_quote_refs,
        )
    if (
        prospective_observation_ledger_path is not None
        or prospective_observation_ledger_sha256 is not None
        or prospective_observation_evaluation_cutoff is not None
    ):
        if (
            prospective_observation_ledger_path is None
            or prospective_observation_ledger_sha256 is None
            or prospective_observation_evaluation_cutoff is None
        ):
            raise ValueError("Observation ledger path, SHA-256 and evaluation cutoff are required together")
        _project_prospective_observation_ledger(
            payload,
            root=root,
            manifest_path=prospective_observation_ledger_path,
            manifest_sha256=prospective_observation_ledger_sha256,
            evaluation_cutoff=prospective_observation_evaluation_cutoff,
        )
    validate_product_workbench_candidate_payload(payload)
    return payload


__all__ = [
    "ACTION_NO_ORDER",
    "LEGACY_PACKET_SCHEMA_VERSION",
    "PRODUCT_PAYLOAD_SCHEMA_VERSION",
    "build_product_workbench_candidate_payload",
    "validate_product_workbench_candidate_payload",
]

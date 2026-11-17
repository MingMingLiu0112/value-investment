"""Publish the reviewed 000333 draft as a read-only research artifact.

This adapter does not calculate valuation. It binds the existing shared result,
removes execution fields, and writes a separate research-draft pointer consumed
by the Web presentation layer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.common import sha256_file  # noqa: E402


SYMBOL = "000333"
RUN_ID = "midea-draft-20261017-v2"
SOURCE_DIR = ROOT / "runtime" / "company-research" / RUN_ID
RESULT_PATH = SOURCE_DIR / "research-result.json"
PACKAGE_PATH = SOURCE_DIR / "package.json"
EVENT_SCAN_PATH = SOURCE_DIR / "event-scan-20261017.json"
MEMO_PATH = SOURCE_DIR / "assumption-memo-v2.json"
BUILD_RECEIPT_PATH = SOURCE_DIR / "package-build-receipt.json"
PRIOR_RUN_ID = "midea-draft-20261016-v1"
PRIOR_SOURCE_DIR = ROOT / "runtime" / "company-research" / PRIOR_RUN_ID
PRIOR_RESULT_PATH = PRIOR_SOURCE_DIR / "research-result.json"
PRIOR_PACKAGE_PATH = PRIOR_SOURCE_DIR / "package.json"
REQUEST_PATH = (
    ROOT
    / "runtime"
    / "research-schedule-requests"
    / "midea-denominator-reopen-20261017-v1.json"
)
ADMISSION_RECEIPT_PATH = (
    ROOT
    / "runtime"
    / "research-evidence-stop-consumptions"
    / "d6119ce67b76de5f66305539ecdde1c3fd1a5f43f53bfb3ddce82931f4b14295.json"
)
RECOVERY_RECEIPT_PATH = (
    ROOT
    / "runtime"
    / "research-evidence-stop-recoveries"
    / "d6119ce67b76de5f66305539ecdde1c3fd1a5f43f53bfb3ddce82931f4b14295.json"
)
RESUME_RECEIPT_PATH = (
    ROOT
    / "runtime"
    / "research-evidence-stop-resumes"
    / "d6119ce67b76de5f66305539ecdde1c3fd1a5f43f53bfb3ddce82931f4b14295.json"
)
RESOLUTION_RECEIPT_PATH = (
    ROOT
    / "runtime"
    / "research-evidence-stop-resolutions"
    / "d6119ce67b76de5f66305539ecdde1c3fd1a5f43f53bfb3ddce82931f4b14295.json"
)
PRIOR_EVIDENCE_PATH = (
    ROOT
    / "runtime"
    / "company-research"
    / "midea-valuation-applicability-20261013-v5"
    / "evidence.json"
)
PRIOR_DENOMINATOR_NOTE_PATH = (
    ROOT / "docs" / "current" / "tl8-c-000333-share-denominator-recheck-20261013.md"
)
ARTIFACT_DIR = ROOT / "artifacts" / "current" / "midea-draft-20261017"
PUBLIC_DRAFT_PATH = ARTIFACT_DIR / "public-draft-v2.json"
POINTER_PATH = ROOT / "config" / "current-research-drafts.json"

SOURCE_TITLES = {
    "midea_fy2025_annual": "美的集团 2025 年年度报告",
    "midea_2026h1": "美的集团 2026 年半年度报告",
    "midea_202606_hkex_monthly_return": "美的集团 H 股 2026 年 6 月月度证券变动报告表",
    "midea_quote_20261016": "2026-10-16 双源收盘行情封包（本地证据）",
    "midea_event_scan_20261017": "巨潮资讯 2026-10-14 至 2026-10-17 公告检索结果",
    "midea_assumption_memo_20261017_v2": "美的集团条件性估值假设备忘录 v2",
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_new_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
    return hashlib.sha256(encoded).hexdigest()


def _write_replace_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp-" + os.urandom(8).hex())
    with temporary.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return hashlib.sha256(encoded).hexdigest()


def _text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) and value.strip() else default


def _evidence_rows(
    package: dict[str, Any], event_scan: dict[str, Any]
) -> list[dict[str, Any]]:
    event_titles = {}
    for announcement in event_scan.get("announcements", []):
        if not isinstance(announcement, dict):
            continue
        title = _text(announcement.get("title"))
        for ref in announcement.get("evidence_refs", []):
            if isinstance(ref, dict) and isinstance(ref.get("id"), str) and title:
                event_titles[ref["id"]] = title
    pending = {
        ref.get("id"): ref
        for item in event_scan.get("announcements", [])
        if isinstance(item, dict)
        for ref in item.get("evidence_refs", [])
        if isinstance(ref, dict) and isinstance(ref.get("id"), str)
    }
    rows = []
    for source in package.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str):
            continue
        ref = pending.get(source_id, {})
        rows.append(
            {
                "id": source_id,
                "title": (
                    SOURCE_TITLES.get(source_id)
                    or event_titles.get(source_id)
                    or source.get("title")
                    or ref.get("title")
                    or source_id
                ),
                "url": source.get("location"),
                "published_at": source.get("published_at"),
                "available_at": source.get("source_available_at"),
                "sha256": source.get("sha256"),
            }
        )
    return rows


def _scenario_rows(result: dict[str, Any]) -> list[dict[str, str]]:
    valuation = result["valuation"]
    sensitivities = {
        row.get("scenario"): row
        for row in valuation.get("sensitivities", [])
        if isinstance(row, dict)
    }
    rows = []
    for name in ("bear", "base", "bull"):
        row = sensitivities.get(name, {})
        rows.append(
            {
                "scenario": name,
                "per_share_value": str(valuation[f"{name}_value"]),
                "terminal_residual_contribution_ratio": str(
                    row.get("terminal_residual_contribution_ratio", "")
                ),
                "basis_to_valuation_factor": str(
                    row.get("basis_to_valuation_factor", "")
                ),
                "dividend_crosscheck_difference": str(
                    row.get("dividend_crosscheck_difference", "")
                ),
            }
        )
    return rows


def _public_draft(
    result: dict[str, Any], package: dict[str, Any], event_scan: dict[str, Any]
) -> dict[str, Any]:
    research_case = package["research_case"]
    valuation = result["valuation"]
    validity = result["model_validity"]
    quote = result["quote_snapshot"]
    bridge = result["price_bridge"]
    financing = research_case["financial_summary"]
    assumptions = []
    for row in result["assumptions"].get("assumptions", []):
        if not isinstance(row, dict):
            continue
        assumptions.append(
            {
                "name": row.get("name"),
                "unit": row.get("unit"),
                "bear": row.get("bear"),
                "base": row.get("base"),
                "bull": row.get("bull"),
                "basis": row.get("basis"),
                "rationale": row.get("rationale"),
                "confidence": row.get("confidence"),
            }
        )
    announcements = []
    for item in event_scan.get("announcements", []):
        if isinstance(item, dict):
            announcements.append(
                {
                    "announcement_id": item.get("announcement_id"),
                    "title": item.get("title"),
                    "published_at": item.get("published_at"),
                    "review_status": item.get("review_status"),
                    "source_url": item.get("source_url"),
                }
            )
    return {
        "schema_version": "public-research-draft-v1",
        "action": "no_order",
        "symbol": SYMBOL,
        "company_name": research_case["name"],
        "run_id": RUN_ID,
        "research_version": research_case["research_version"],
        "status": "RESEARCH_DRAFT_NOT_APPROVED",
        "research_as_of": result["as_of"],
        "available_at": result["available_at"],
        "financial_period": research_case["financial_period"],
        "summary": research_case["thesis"],
        "thesis": research_case["thesis"],
        "return_driver": research_case["return_driver"],
        "mispricing_hypothesis": research_case["mispricing_hypothesis"],
        "financial_facts": financing,
        "valuation": {
            "model_type": valuation["model_type"],
            "model_version": valuation["model_version"],
            "valuation_date": valuation["valuation_date"],
            "status": valuation["assumptions"]["status"],
            "confidence": valuation["confidence"],
            "currency": "CNY",
            "scope": valuation["assumptions"]["scope"],
            "disclaimer": valuation["assumptions"]["disclaimer"],
            "scenarios": _scenario_rows(result),
            "assumptions": assumptions,
        },
        "model_validity": {
            "model_id": validity["model_id"],
            "model_as_of": validity["model_as_of"],
            "last_material_event_check": validity["last_material_event_check"],
            "status": validity["status"],
            "blockers": validity["blockers"],
        },
        "quote_fact": {
            "quote_date": quote["quote_date"],
            "current_price": quote["current_price"],
            "currency": "CNY",
            "status": "VERIFIED_CLOSE_NOT_ADMITTED",
            "providers": [
                ref
                for ref in quote.get("evidence_refs", [])
                if isinstance(ref, dict)
                and ref.get("kind") == "quote_provider_document"
            ],
        },
        "price_bridge": {
            "status": bridge["bridge_status"],
            "price_admitted": False,
            "margin_to_bear": None,
            "margin_to_base": None,
            "blockers": bridge.get("blockers", []),
            "reason": (
                "模型有效性尚未建立，不能把收盘价与条件性估值进行正式比较。"
                if bridge.get("bridge_status") != "READY"
                else "条件性价格关系可计算，但正式决策门仍未通过。"
            ),
            "needed_evidence": (
                "逐条完成待处理公告的材料性人工复核、建立模型有效性，"
                "并完成有权研究审批。"
            ),
        },
        "gates": result.get("gate"),
        "events": {
            "status": event_scan.get("status"),
            "coverage_status": event_scan.get("coverage_status"),
            "pending_count": sum(
                1
                for row in announcements
                if row.get("review_status") == "PENDING_HUMAN_REVIEW"
            ),
            "items": announcements,
        },
        "counter_evidence": [
            _text(item.get("text"))
            for item in research_case.get("counter_evidence", [])
            if isinstance(item, dict) and _text(item.get("text"))
        ],
        "thesis_breakers": [
            _text(item.get("text"))
            for item in research_case.get("thesis_breakers", [])
            if isinstance(item, dict) and _text(item.get("text"))
        ],
        "next_events": [
            _text(item.get("text"))
            for item in research_case.get("next_events", [])
            if isinstance(item, dict) and _text(item.get("text"))
        ],
        "reopen_triggers": [
            "人工逐条完成当前待处理公告的材料性复核。",
            "补充下一期定期报告，重新核验利润、现金转换和ROE路径。",
            "任何股本注销、回购或分红变化均触发普通股分母重算。",
        ],
        "limitations": [
            "9%权益门槛、ROE路径、终端增长和留存率均为候选研究假设，未经人工批准。",
            "正式 G3 估值门未通过；不得据此生成买卖信号。",
            "报价仅为已核验收盘事实，PriceBridge 未准入。",
            "公告快照覆盖不完整，且严格 contemporaneous PIT 未证明。",
            "未接入真实个人组合、现金和 IPS，不得生成仓位建议。",
        ],
        "boundary": (
            "研究草稿不等于买入或卖出建议；当前 action=no_order，"
            "正式决策仍为待研究。"
        ),
        "evidence": _evidence_rows(package, event_scan),
    }


def _render_report(draft: dict[str, Any]) -> str:
    valuation = draft["valuation"]
    comparison = draft["version_comparison"]
    scenario_lines = [
        f"| {row['scenario'].title()} | {row['per_share_value']} | "
        f"{row['terminal_residual_contribution_ratio']} | "
        f"{row['basis_to_valuation_factor']} |"
        for row in valuation["scenarios"]
    ]
    evidence_lines = []
    for row in draft["evidence"]:
        location = row.get("url") or "未提供定位"
        if not str(location).startswith(("https://", "http://")):
            location = f"`{location}`"
        evidence_lines.append(
            f"- {row.get('title') or row['id']}（`{row['id']}`）：{location}  \n"
            f"  SHA-256 `{row['sha256']}`"
        )
    event_lines = [
        f"- {row['published_at'][:10]} {row['title']} (`{row['review_status']}`)"
        for row in draft["events"]["items"]
    ]
    assumptions = [
        f"- {row['name']}: bear={row['bear']}, base={row['base']}, bull={row['bull']}；{row['rationale']}"
        for row in valuation["assumptions"]
    ]
    counter = [f"- {line}" for line in draft["counter_evidence"]]
    reopen = [f"- {line}" for line in draft["reopen_triggers"]]
    limitations = [f"- {line}" for line in draft["limitations"]]
    return f"""# 美的集团（000333）条件性研究草案

> **研究草稿（未批准）**。当前状态为 `{draft['status']}`，`action=no_order`。本研究不能生成正式买入、卖出或仓位建议。

## 结论

{draft['summary']}

估值只作为条件性研究结果：Bear / Base / Bull 分别对应不同的 ROE、终端增长和留存假设，不是目标价。已核验收盘价 CNY {draft['quote_fact']['current_price']}（{draft['quote_fact']['quote_date']}）仅作为报价事实展示，PriceBridge 状态为 `{draft['price_bridge']['status']}`，价格准入为 `false`。

## 条件性估值

模型：`{valuation['model_version']}`  
研究截止日：`{draft['research_as_of']}`  
估值基准：`{valuation['scope']}`  
置信度：`{valuation['confidence']}`

版本变化：`{comparison['from']['research_version']}`（{comparison['from']['status']}）
→ `{comparison['to']['research_version']}`（{comparison['to']['status']}）。新增事项：
{chr(10).join(f'- {line}' for line in comparison['changed'])}

| 情景 | 每股权益价值（CNY） | 终端剩余收益贡献比 | 基准至估值日因子 |
|---|---:|---:|---:|
{chr(10).join(scenario_lines)}

## 财务事实

- 2025 年归母净利润：CNY {draft['financial_facts']['fy2025_parent_profit_cny']}
- 2025 年末归母权益：CNY {draft['financial_facts']['fy2025_parent_equity_cny']}
- 2025 年加权 ROE：{draft['financial_facts']['fy2025_weighted_roe']}
- 2026H1 扣非归母净利润：CNY {draft['financial_facts']['h1_2026_adjusted_parent_profit_cny']}，同比 {draft['financial_facts']['h1_2026_adjusted_parent_profit_yoy']}
- 2026H1 归母权益：CNY {draft['financial_facts']['h1_2026_parent_equity_cny']}
- 2026-06-30 普通股分母：{draft['financial_facts']['ordinary_shares_20260630']} 股

## 候选假设

{chr(10).join(assumptions)}

## 反证与失效条件

反证：

{chr(10).join(counter)}

失效条件：

{chr(10).join(f'- {line}' for line in draft['thesis_breakers'])}

## 事件与模型有效性

截至研究截止日的公告状态：`{draft['events']['status']}`，人工复核状态：`PENDING_HUMAN_REVIEW`。

{chr(10).join(event_lines)}

模型有效性：`{draft['model_validity']['status']}`。  
PriceBridge：`{draft['price_bridge']['status']}`，价格准入：`false`。  
阻塞原因：{draft['price_bridge']['reason']}

## 重开与后续证据

{chr(10).join(reopen)}

## 限制

{chr(10).join(limitations)}

## 证据与哈希

{chr(10).join(evidence_lines)}

## 运行链

`research package -> shared residual-income model -> ValuationResult -> ModelValidity -> PriceBridge -> Web research draft`

旧版 v1 已完成一次性 Evidence Stop 重开和显式恢复；v2 先以 append-only
结案收据确认普通股分母缺口已解决，再以正常研究路径运行。v2 没有再次消费
Evidence Stop，也没有把研究草案升级为审批或订单。v2 同时把财务事实页锚、
九项情景绑定、公告覆盖和假设备忘录纳入来源契约；公告覆盖仍为不完整，
严格 contemporaneous PIT 仍为 NOT_PROVEN。
"""


def _comparison(
    result: dict[str, Any], package: dict[str, Any]
) -> dict[str, Any]:
    valuation = result["valuation"]
    prior_result = _load(PRIOR_RESULT_PATH)
    prior_valuation = prior_result["valuation"]
    return {
        "schema_version": "research-version-comparison-v2",
        "action": "no_order",
        "symbol": SYMBOL,
        "from": {
            "status": "DRAFT_NOT_APPROVED",
            "research_version": PRIOR_RUN_ID,
            "result": {
                "path": PRIOR_RESULT_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(PRIOR_RESULT_PATH),
            },
            "package": {
                "path": PRIOR_PACKAGE_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(PRIOR_PACKAGE_PATH),
            },
            "valuation": {
                "model_version": prior_valuation["model_version"],
                "bear": prior_valuation["bear_value"],
                "base": prior_valuation["base_value"],
                "bull": prior_valuation["bull_value"],
                "confidence": prior_valuation["confidence"],
            },
        },
        "to": {
            "status": "RESEARCH_DRAFT_NOT_APPROVED",
            "research_version": RUN_ID,
            "research_as_of": result["as_of"],
            "valuation": {
                "model_version": valuation["model_version"],
                "bear": valuation["bear_value"],
                "base": valuation["base_value"],
                "bull": valuation["bull_value"],
                "confidence": valuation["confidence"],
            },
            "model_validity": result["model_validity"]["status"],
            "price_bridge": result["price_bridge"]["bridge_status"],
        },
        "changed": [
            "research_inputs_migrated_to_source_bound_v2_contract",
            "nine_financial_facts_now_have_physical_page_anchors",
            "all_nine_scenario_assumptions_now_bind_to_the_hash_bound_memo",
            "four_announcements_covered_including_2026_10_17_buyback_progress",
            "event_coverage_is_honestly_incomplete",
            "evidence_stop_resolution_is_now_append_only_and_reusable_for_normal_research",
        ],
        "unchanged": [
            "bear_base_bull_values_unchanged",
            "human_research_approval_absent",
            "formal_G3_absent",
            "event_materiality_pending_human_review",
            "strict_contemporaneous_pit_not_proven",
            "price_admitted_false",
            "position_guidance_null",
            "action_no_order",
        ],
        "numeric_delta": {
            "bear": {
                "from": prior_valuation["bear_value"],
                "to": valuation["bear_value"],
            },
            "base": {
                "from": prior_valuation["base_value"],
                "to": valuation["base_value"],
            },
            "bull": {
                "from": prior_valuation["bull_value"],
                "to": valuation["bull_value"],
            },
        },
        "next_gate": "Human materiality review of the four retained announcements and model-validity closure.",
    }


def publish() -> dict[str, Any]:
    required = (
        RESULT_PATH,
        PACKAGE_PATH,
        EVENT_SCAN_PATH,
        MEMO_PATH,
        BUILD_RECEIPT_PATH,
        PRIOR_RESULT_PATH,
        PRIOR_PACKAGE_PATH,
        REQUEST_PATH,
        ADMISSION_RECEIPT_PATH,
        RECOVERY_RECEIPT_PATH,
        RESUME_RECEIPT_PATH,
        RESOLUTION_RECEIPT_PATH,
        PRIOR_EVIDENCE_PATH,
        PRIOR_DENOMINATOR_NOTE_PATH,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(", ".join(missing))
    if ARTIFACT_DIR.exists():
        raise FileExistsError("research draft publication target already exists")
    if not POINTER_PATH.is_file():
        raise FileNotFoundError(POINTER_PATH)

    result = _load(RESULT_PATH)
    package = _load(PACKAGE_PATH)
    event_scan = _load(EVENT_SCAN_PATH)
    resolution = _load(RESOLUTION_RECEIPT_PATH)
    prior_pointer = _load(POINTER_PATH)
    if result.get("action") != "no_order" or result.get("symbol") != SYMBOL:
        raise ValueError("research result is not a no_order 000333 draft")
    if package.get("symbol") != SYMBOL:
        raise ValueError("research package symbol mismatch")
    if result.get("model_validity", {}).get("status") != "UNKNOWN":
        raise ValueError("draft requires ModelValidity UNKNOWN")
    if result.get("price_bridge", {}).get("bridge_status") == "READY":
        raise ValueError("draft publication must not admit price")
    if result.get("decision_recommendation", {}).get("position_guidance") is not None:
        raise ValueError("draft publication cannot carry position guidance")
    if (
        resolution.get("status") != "EVIDENCE_RESOLVED"
        or resolution.get("action") != "no_order"
        or resolution.get("symbol") != SYMBOL
        or resolution.get("research_result", {}).get("sha256")
        != sha256_file(PRIOR_RESULT_PATH)
    ):
        raise ValueError("Evidence Stop resolution does not bind the completed prior result")
    schedule_gate = result.get("schedule_gate") or {}
    schedule_consumption = result.get("schedule_consumption") or {}
    if (
        schedule_gate.get("status") != "ALLOW_NORMAL_RESEARCH"
        or schedule_gate.get("matched_stop_ids") != []
        or "000333-share-denominator-2026-06-30"
        in schedule_gate.get("active_stop_ids", [])
    ):
        raise ValueError("v2 result did not run through the resolved-scope normal path")
    if schedule_consumption.get("status") != "NORMAL_RESEARCH_NOT_CONSUMED":
        raise ValueError("normal research must not consume a second Evidence Stop request")

    comparison = _comparison(result, package)
    draft = _public_draft(result, package, event_scan)
    draft["version_comparison"] = comparison
    ARTIFACT_DIR.mkdir(parents=True)
    public_draft_sha = _write_new_json(PUBLIC_DRAFT_PATH, draft)
    previous_pointer_path = ARTIFACT_DIR / "previous-current-research-drafts.json"
    pointer = {
        "schema_version": "current-research-drafts-v1",
        "action": "no_order",
        "drafts": {
            SYMBOL: {
                "path": PUBLIC_DRAFT_PATH.relative_to(ROOT).as_posix(),
                "sha256": public_draft_sha,
            }
        },
    }
    previous_pointer_sha = _write_new_json(previous_pointer_path, prior_pointer)
    prior_entry = (prior_pointer.get("drafts") or {}).get(SYMBOL) or {}
    if (
        prior_entry.get("path")
        != "artifacts/current/midea-draft-20261016/public-draft-v1.json"
        or prior_entry.get("sha256")
        != sha256_file(ROOT / "artifacts/current/midea-draft-20261016/public-draft-v1.json")
    ):
        raise ValueError("current research pointer is not the verified v1 draft")
    pointer_sha = _write_replace_json(POINTER_PATH, pointer)

    shutil.copyfile(RESULT_PATH, ARTIFACT_DIR / "research-result.json")
    shutil.copyfile(PACKAGE_PATH, ARTIFACT_DIR / "package.json")
    shutil.copyfile(BUILD_RECEIPT_PATH, ARTIFACT_DIR / "package-build-receipt.json")
    shutil.copyfile(EVENT_SCAN_PATH, ARTIFACT_DIR / "event-scan-20261017.json")
    shutil.copyfile(MEMO_PATH, ARTIFACT_DIR / "assumption-memo-v2.json")
    execution_receipt_path = ARTIFACT_DIR / "research-execution-receipt-v2.json"
    execution_receipt = {
        "schema_version": "research-execution-receipt-v2",
        "status": "NORMAL_RESEARCH_EXECUTED_AFTER_EVIDENCE_STOP_RESOLUTION",
        "symbol": SYMBOL,
        "run_id": RUN_ID,
        "action": "no_order",
        "command": (
            "python -B scripts/current/run_company_research.py --symbol 000333 "
            "--package runtime/company-research/midea-draft-20261017-v2/package.json "
            "--output runtime/company-research/midea-draft-20261017-v2/research-result.json "
            "--schedule-request runtime/research-schedule-requests/"
            "midea-denominator-reopen-20261017-v1.json"
        ),
        "inputs": {
            "package": {
                "path": PACKAGE_PATH.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(PACKAGE_PATH),
            },
            "package_build_receipt_sha256": sha256_file(BUILD_RECEIPT_PATH),
            "event_scan_sha256": sha256_file(EVENT_SCAN_PATH),
            "assumption_memo_sha256": sha256_file(MEMO_PATH),
        },
        "output": {
            "path": RESULT_PATH.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(RESULT_PATH),
            "input_descriptor_sha256": result.get("input_descriptor_sha256"),
        },
        "schedule_gate": schedule_gate,
        "schedule_consumption": schedule_consumption,
        "research_admission": "DRAFT_NOT_APPROVED",
        "price_admission": False,
        "human_approval": False,
    }
    execution_receipt_sha = _write_new_json(execution_receipt_path, execution_receipt)
    report_path = ARTIFACT_DIR / "research-report.md"
    report_path.write_text(_render_report(draft), encoding="utf-8")
    comparison_path = ARTIFACT_DIR / "research-version-comparison.json"
    _write_new_json(comparison_path, comparison)

    artifact_hashes = {
        path.name: sha256_file(path)
        for path in (
            ARTIFACT_DIR / "research-result.json",
            ARTIFACT_DIR / "package.json",
            ARTIFACT_DIR / "package-build-receipt.json",
            ARTIFACT_DIR / "event-scan-20261017.json",
            ARTIFACT_DIR / "assumption-memo-v2.json",
            execution_receipt_path,
            report_path,
            comparison_path,
            previous_pointer_path,
        )
    }
    manifest = {
        "schema_version": "research-draft-publication-manifest-v1",
        "status": "DRAFT_NOT_APPROVED",
        "symbol": SYMBOL,
        "run_id": RUN_ID,
        "public_draft": {
            "path": PUBLIC_DRAFT_PATH.relative_to(ROOT).as_posix(),
            "sha256": public_draft_sha,
        },
        "pointer": {
            "path": POINTER_PATH.relative_to(ROOT).as_posix(),
            "sha256": pointer_sha,
        },
        "artifacts": artifact_hashes,
        "source_result": {
            "path": RESULT_PATH.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(RESULT_PATH),
        },
        "source_package": {
            "path": PACKAGE_PATH.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(PACKAGE_PATH),
        },
        "schedule_chain": {
            "request_sha256": sha256_file(REQUEST_PATH),
            "admission_sha256": sha256_file(ADMISSION_RECEIPT_PATH),
            "recovery_sha256": sha256_file(RECOVERY_RECEIPT_PATH),
            "resume_sha256": sha256_file(RESUME_RECEIPT_PATH),
            "resolution_sha256": sha256_file(RESOLUTION_RECEIPT_PATH),
            "execution_receipt_sha256": execution_receipt_sha,
        },
        "previous_pointer_sha256": previous_pointer_sha,
        "formal_admission": False,
        "price_admitted": False,
        "position_guidance": None,
        "human_approval": False,
        "action": "no_order",
    }
    manifest_path = ARTIFACT_DIR / "manifest-v1.json"
    manifest_sha = _write_new_json(manifest_path, manifest)
    receipt = {
        "schema_version": "research-draft-publication-receipt-v1",
        "status": "DRAFT_PUBLISHED_READ_ONLY",
        "manifest_path": manifest_path.relative_to(ROOT).as_posix(),
        "manifest_sha256": manifest_sha,
        "action": "no_order",
    }
    receipt_path = ARTIFACT_DIR / "receipt-v1.json"
    receipt_sha = _write_new_json(receipt_path, receipt)
    return {
        "status": receipt["status"],
        "public_draft_path": str(PUBLIC_DRAFT_PATH),
        "public_draft_sha256": public_draft_sha,
        "pointer_path": str(POINTER_PATH),
        "pointer_sha256": pointer_sha,
        "report_path": str(report_path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_sha,
        "action": "no_order",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(publish(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

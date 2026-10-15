"""One bounded, hash-bound registry for current observation-only price cases."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .price_action_case import project_current_price_action_plan
from ...infrastructure.hotspot.current_price_case import load_current_price_case
from .daily_selection import verify_daily_selection

REGISTRY = "config/current-price-conditions.json"


def _path(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()) or Path(name).is_absolute():
        raise ValueError("Registry evidence escapes repository")
    return target


def registry_identity(root: Path) -> dict:
    """Bind observed bytes too: tampering creates a new, blocked identity."""
    result = {"path": REGISTRY, "observed_sha256": None, "evidence": []}
    path = root / REGISTRY
    if not path.is_file():
        return result
    try:
        raw = path.read_bytes()
        result["observed_sha256"] = hashlib.sha256(raw).hexdigest()
        registry = json.loads(raw)
        all_items = registry["items"] + registry.get("previous_items", [])
        names = {item["case_path"] for item in all_items}
        for item in registry.get("previous_items", []):
            names.add(item["watch_source_binding"]["path"])
            old_watch = json.loads(_path(root, item["watch_source_binding"]["path"]).read_bytes())
            names.update(binding["path"] for binding in old_watch.get("source_bindings", []))
        if registry.get("watch_source_binding"):
            names.add(registry["watch_source_binding"]["path"])
            watch = json.loads(_path(root, registry["watch_source_binding"]["path"]).read_bytes())
            names.update(binding["path"] for binding in watch.get("source_bindings", []))
        for item in all_items:
            case = json.loads(_path(root, item["case_path"]).read_bytes())
            names.update(source["path"] for source in case["source_bindings"].values())
            names.add(case["current_reference_close"]["bundle_path"])
        for name in sorted(names):
            target = _path(root, name)
            result["evidence"].append({"path": name, "observed_sha256":
                hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None})
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        result["error"] = "CURRENT_PRICE_REGISTRY_UNAVAILABLE"
    return result


def load_price_conditions(root: Path, *, now: datetime, research_version: str | None) -> dict:
    path = root / REGISTRY
    if not path.is_file():
        return {"status": "NOT_CONNECTED", "items": [], "blockers": []}
    try:
        registry = json.loads(path.read_bytes())
        if (registry.get("schema_version") != "current-price-conditions-v1"
                or registry.get("action") != "no_order" or not 1 <= len(registry["items"]) <= 10):
            raise ValueError("Invalid registry contract")
        source = registry["watch_source_binding"]
        source_raw = _path(root, source["path"]).read_bytes()
        if hashlib.sha256(source_raw).hexdigest() != source["sha256"]:
            raise ValueError("Watch source changed")
        watch_report = json.loads(source_raw)
        daily = watch_report.get("schema_version") == "hotspot-daily-selection-v1"
        if daily:
            verify_daily_selection(root, watch_report)
        watch_symbols = {row["symbol"] for row in watch_report.get("dated_quote_observations", [])}
        watch_symbols.update(row["symbol"] for row in watch_report.get("observation_list", []))
        items, blockers, retired_warnings, seen = [], [], [], set()
        if len(registry.get("previous_items", [])) > 10:
            raise ValueError("Too many retired observations")
        for item in registry["items"] + registry.get("previous_items", []):
            retired = item in registry.get("previous_items", [])
            source = item["watch_source_binding"] if retired else registry["watch_source_binding"]
            try:
                source_raw = _path(root, source["path"]).read_bytes()
                if hashlib.sha256(source_raw).hexdigest() != source["sha256"]:
                    raise ValueError("Candidate watch source changed")
                watch_report = json.loads(source_raw)
                daily = watch_report.get("schema_version") == "hotspot-daily-selection-v1"
                if daily:
                    verify_daily_selection(root, watch_report)
            except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
                if not retired:
                    raise
                retired_warnings.append("RETIRED_CANDIDATE_SOURCE_UNAVAILABLE:" + item["symbol"])
                continue
            watch_symbols = {row["symbol"] for row in watch_report.get("dated_quote_observations", [])}
            watch_symbols.update(row["symbol"] for row in watch_report.get("observation_list", []))
            symbol = item["symbol"]
            if symbol in seen or symbol not in watch_symbols:
                raise ValueError("Duplicate or unbound current candidate")
            seen.add(symbol)
            try:
                case = load_current_price_case(root=root, symbol=symbol,
                    case_path=_path(root, item["case_path"]),
                    expected_sha256=item["case_sha256"], now=now)
                plan = project_current_price_action_plan(case)
                if daily and case["market_trade_date"] != watch_report["trade_date"]:
                    raise ValueError("Daily selection/current case date conflict")
                plan.update(decision_id=f"hotspot-{symbol}", research_version=research_version,
                            case_path=case["case_path"], case_sha256=case["case_sha256"],
                            watch_source_scope=item["watch_source_scope"] if retired else registry["watch_source_scope"])
                plan["watch_reason"] = "来自已归档、双源核对日期的证券观察记录；本轮更新其价格结构。行业热度日期尚未认证，不代表已通过热点筛选。"
                if daily:
                    candidate = next(row for row in watch_report["observation_list"] if row["symbol"] == symbol)
                    plan.update(watch_reason="当日带日期行情按行业相对强度、成交额、代码确定性排序；这是研究观察，不是正式热点准入。",
                                daily_selection=candidate, selection_rule_version=watch_report["ranking"]["rule_version"],
                                daily_selection_binding=source,
                                market_environment=watch_report["ranking"]["market"],
                                observation_evidence=dict(source=watch_report["source_bindings"],
                                    available_at=max(datetime.fromisoformat(binding["available_at"]) for binding in watch_report["source_bindings"]).isoformat(), trade_date=watch_report["trade_date"],
                                    sha256=source["sha256"], status="DATED_DAILY_OBSERVATION_NOT_ADMISSION"),
                                selection_source_bindings=watch_report["source_bindings"],
                                classification_effective_date=None,
                                required_confirmations=watch_report["unknowns"])
                plan.update(formal_eligibility=False, portfolio_eligibility=None, sleeve="HOTSPOT_SATELLITE")
                if retired:
                    plan["candidate_lifecycle"] = "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"
                    if plan["signal_state"] != "TRIGGER_REJECTED":
                        plan.update(signal_state="STALE", action_intent="WATCH",
                                    explanation="未进入本次当日候选名单；旧价格结构仅供复盘，不作为今日机会。")
                items.append({"symbol": symbol, "company_name": item["company_name"],
                              "price_action_plan": plan})
            except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
                if retired:
                    retired_warnings.append(f"RETIRED_PRICE_CASE_UNAVAILABLE:{symbol}")
                else:
                    blockers.append(f"CURRENT_PRICE_CASE_UNAVAILABLE:{symbol}")
        return {"status": "CURRENT_OBSERVATION" if items else "BLOCKED", "items": items,
                "watch_source_scope": registry["watch_source_scope"], "blockers": blockers,
                "retired_warnings": retired_warnings}
    except (ValueError, OSError, KeyError, TypeError, AttributeError, ArithmeticError):
        return {"status": "BLOCKED", "items": [], "blockers": ["CURRENT_PRICE_REGISTRY_UNAVAILABLE"]}

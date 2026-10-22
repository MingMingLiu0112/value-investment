"""Compose the one trusted daily public decision packet (TL9 MVP-1).

Every public surface (Web daily overview, company detail, decision history,
system status and the CLI summary) reads this same composition: the verified
publication chain, the registered quote bridge, the published company rows and
the registered research blockers. No business rule is duplicated here and no
private portfolio state ever enters the packet. ``action`` stays ``no_order``.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .common import sha256_file
from .daily_research_status import (
    REGISTRY_UNAVAILABLE,
    registered_quote_symbols,
    registry_state,
)
from .publication_chain import STRUCTURE_ERRORS, try_load_current_chain
from .quote_bridge import execute_quote_bridge_for_symbol
from ..hotspot.current_registry import registry_identity, load_price_conditions
from ..decision.current_value_plan import load_current_value_action_plans


SCHEMA_VERSION = "daily-public-packet-v1"
# Bump this whenever the derived content can change for the same upstream
# chain (bug fixes included). It is part of the identity below so a new engine
# revision yields a new publication_id instead of silently reusing a stored
# record that an older revision computed.
# v20 retains source-verified retired observations with their original expiry.
# v22 keeps per-case inspection clocks out of immutable decision content.
# v23 publishes the current source-replayed pending plan with its own identity.
# v24 keeps publication-context restrictions separate from replayed model fields.
ENGINE_VERSION = "daily-public-packet-engine-v24"
# v4 folds every content-deciding input into the identity: the company
# research registry and its evidence files, the archived quote bundles, the
# bound decision-explanation files and the business clock (natural date +
# latest completed session) that decides the trading day, freshness and
# admission. A change in any of them mints a new publication_id instead of
# reusing a stored record with different facts.
IDENTITY_SCHEMA = "daily-public-packet-identity-v10"
ACTION = "no_order"
CHINA = ZoneInfo("Asia/Shanghai")
QUOTE_POINTER_PATH = "config/current-quote-bridge.json"
REGISTRY_PATH = "config/current-company-research-registry.json"
REGISTRY_SCHEMA = "current-company-research-registry-v1"
# Stamped when the packet is composed or rechecked at read time; never part of
# the identity and never part of ``content_sha256``.
VOLATILE_PACKET_FIELDS = ("generated_at", "generated_at_china", "content_sha256",
                          "excel_sync")
_SYMBOL = re.compile(r"[0-9]{6}\Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_of(path: Path) -> str | None:
    try:
        return sha256_file(path) if path.is_file() else None
    except OSError:
        return None


def _repo_path(root: Path, name: object) -> Path | None:
    """Resolve a repo-relative path without escaping the repository root."""
    if not isinstance(name, str) or not name:
        return None
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return root / relative


def _stem(path_name: object) -> str | None:
    return Path(path_name).stem if isinstance(path_name, str) and path_name else None


def packet_content_sha256(packet: Mapping[str, Any]) -> str:
    """Digest the decision content, ignoring read-time stamps and view checks.

    ``generated_at`` is a clock reading, not a research fact; ``excel_sync``
    is a read-only comparison stamped when the packet is built. Everything
    else (dates, statuses, blockers, counts) is decision content and is
    covered, so the same identity can never carry two different answers.
    """
    content = {key: value for key, value in packet.items()
               if key not in VOLATILE_PACKET_FIELDS}
    return hashlib.sha256(_canonical(content).encode("utf-8")).hexdigest()


def publication_identity(inputs: Mapping[str, Any]) -> str:
    """Content-addressed identity over every input that decides a packet."""
    return "pub-" + hashlib.sha256(_canonical(inputs).encode("utf-8")).hexdigest()[:20]


def identity_inputs(root: Path, chain: Mapping[str, Any], *,
                    natural_day: str,
                    latest_completed_session: str | None,
                    evaluated_at: datetime | None = None,
                    value_plans: Mapping[str, Any] | None = None) -> dict:
    """The explicit version inputs behind one daily public packet.

    Everything the packet content derives from appears here exactly once:
    the verified publication chain, the quote registry and its archived
    bundles (observed hashes, so an edited file is a new version), the
    company research registry and its evidence, the decision explanations the
    read model binds, the calculation engine revision, and the business clock
    that decides trading day, freshness and admission.
    """
    summary = _quote_pointer_summary(root)
    if value_plans is None:
        value_plans = load_current_value_action_plans(root, now=_now(evaluated_at))
    registry_entries, registry_binding, _ = _research_registry(root)
    evidence: list[dict] = []
    for symbol in sorted(registry_entries):
        for item in _registry_evidence(root, registry_entries[symbol]):
            evidence.append({"symbol": symbol, "path": item["path"],
                             "observed_sha256": item["observed_sha256"]})
    bundles: list[dict] = []
    from .incremental_validity import incremental_validity_identity
    supplemental = [{"symbol": binding["symbol"],
        "sources": incremental_validity_identity(root, binding["ref"])}
        for binding in summary["incremental_bindings"]]
    for binding in summary["bundle_bindings"]:
        target = _repo_path(root, binding["path"])
        bundles.append({"role": binding["role"], "path": binding["path"],
                        "observed_sha256": _sha_of(target) if target is not None else None})
    # The read model binds each decision explanation by path+sha256, and the
    # packet content degrades the bound company when a file no longer
    # verifies. The files are runtime artifacts outside the chain, so their
    # observed bytes have to enter the identity explicitly.
    model = chain.get("model") if isinstance(chain.get("model"), Mapping) else {}
    bindings = model.get("additional_evidence_bindings")
    explanations: list[dict] = []
    value_sources: dict[str, dict] = {}
    extensions = model.get("product_extensions") or {}
    policy_binding = extensions.get("value_action_policy_registry")
    if isinstance(policy_binding, dict) and isinstance(policy_binding.get("path"), str):
        target = _repo_path(root, policy_binding["path"])
        value_sources[policy_binding["path"]] = {"path": policy_binding["path"],
            "observed_sha256": _sha_of(target) if target is not None else None}
    for binding in bindings if isinstance(bindings, list) else []:
        if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
            continue
        target = _repo_path(root, binding["path"])
        explanations.append({"path": binding["path"],
                             "observed_sha256": _sha_of(target) if target is not None else None})
        if target is not None and binding["path"].endswith("-value-decision-explanation.json"):
            try:
                explanation = json.loads(target.read_bytes())
                for reference in (explanation.get("valuation") or {}).get("evidence_refs", []):
                    name = reference.get("path")
                    if isinstance(name, str):
                        source = _repo_path(root, name)
                        value_sources[name] = {"path": name, "observed_sha256": _sha_of(source) if source else None}
            except (ValueError, OSError, TypeError, AttributeError):
                pass
    return {
        "schema": IDENTITY_SCHEMA,
        "engine": ENGINE_VERSION,
        "current_value_plans_sha256": hashlib.sha256(_canonical(value_plans).encode('utf-8')).hexdigest(),
        "natural_date": natural_day,
        "latest_completed_session": latest_completed_session,
        "chain": [{"role": item["role"], "path": item["path"], "sha256": item["sha256"]}
                  for item in sorted(chain["bindings"], key=lambda item: str(item["role"]))],
        "quote_bridge_pointer": {"path": QUOTE_POINTER_PATH,
                                 "observed_sha256": summary["sha256"]},
        "quote_bundles": sorted(bundles, key=lambda item: item["path"]),
        "incremental_validity_sources": supplemental,
        "incremental_materiality_handoff_version": 1,
        "research_registry": ({"path": registry_binding["path"],
                               "observed_sha256": registry_binding["sha256"]}
                              if registry_binding is not None else None),
        "registered_evidence": sorted(evidence, key=lambda item: item["path"]),
        "bound_explanations": sorted(explanations, key=lambda item: item["path"]),
        "current_price_conditions": registry_identity(root),
        "hotspot_structure_rule": {"path": "config/hotspot-confirmed-structure-v1.json",
            "observed_sha256": _sha_of(root / "config/hotspot-confirmed-structure-v1.json")},
        "value_action_sources": sorted(value_sources.values(), key=lambda item: item["path"]),
    }


def _now(generated_at: datetime | None) -> datetime:
    moment = generated_at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _bridge_rows(root: Path, now: datetime) -> tuple[list[dict], list[str]]:
    """Execute the registered bridge once per symbol; failures stay per-symbol."""
    rows: list[dict] = []
    blockers: list[str] = []
    if registry_state(root) == REGISTRY_UNAVAILABLE:
        # A corrupt registry is an unknown state, never "nothing registered".
        return rows, ["QUOTE_REGISTRY_UNAVAILABLE"]
    for symbol in registered_quote_symbols(root):
        try:
            execution = execute_quote_bridge_for_symbol(root, symbol, today=now)
        except STRUCTURE_ERRORS:
            execution = {"symbol": symbol, "status": "EXECUTION_FAILED",
                         "price_admitted": False, "quote": None, "research_day": None,
                         "compatibility": None, "reason": "价格桥接执行失败。", "next_step": None}
            blockers.append(f"PRICE_BRIDGE_EXECUTION_FAILED:{symbol}")
        rows.append(execution)
    return rows, blockers


def _bridge_status(execution: Mapping[str, Any]) -> dict:
    quote = execution.get("quote") if isinstance(execution.get("quote"), dict) else {}
    ladder = execution.get("compatibility") if isinstance(execution.get("compatibility"), dict) else {}
    comparison = ladder.get("comparison_eligible") if isinstance(ladder.get("comparison_eligible"), dict) else {}
    research_day = execution.get("research_day")
    quote_date = quote.get("quote_date")
    incremental = execution.get("incremental_validity") or {}
    return {
        "status": execution.get("status"),
        "quote_verification_status": execution.get("quote_verification_status", execution.get("status")),
        "price_admitted": execution.get("price_admitted") is True,
        "quote_date": quote_date if isinstance(quote_date, str) else None,
        "quote_observed_at": quote.get("collected_at") if isinstance(quote.get("collected_at"), str) else None,
        "research_day": research_day if isinstance(research_day, str) else None,
        "needs_re_research": bool(isinstance(quote_date, str) and isinstance(research_day, str)
                                  and quote_date > research_day and not incremental),
        "incremental_status": incremental.get("status"),
        "review_cutoff": incremental.get("review_cutoff"),
        "announcement_count": incremental.get("announcement_count"),
        "model_validity": incremental.get("model_validity"),
        "incremental_validity_binding": incremental.get("binding_ref"),
        "incremental_validity": incremental or None,
        "price_comparison": execution.get("price_comparison"),
        "conditional_valuation": execution.get("conditional_valuation"),
        "blockers": list(dict.fromkeys([*incremental.get("blockers", []),
            *(execution.get("price_comparison") or {}).get("blockers", [])])),
        "current_price": quote.get("display_price"),
        "comparison_eligible": comparison.get("eligible") is True,
        "display_scope": quote.get("display_scope"),
        "latest_completed_session": quote.get("latest_completed_session"),
        "reason": execution.get("reason"),
        "next_step": execution.get("next_step"),
    }


def _quote_pointer_summary(root: Path) -> dict:
    path = root / QUOTE_POINTER_PATH
    digest = _sha_of(path)
    summary = {"path": QUOTE_POINTER_PATH, "sha256": digest,
               "registered_at": None, "quotes_registered": 0, "bundle_bindings": [], "incremental_bindings": []}
    if digest is None:
        return summary
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except STRUCTURE_ERRORS:
        return summary
    if not isinstance(data, dict) or data.get("schema_version") != "current-quote-bridge-v1":
        return summary
    if isinstance(data.get("registered_at"), str):
        summary["registered_at"] = data["registered_at"]
    quotes = data.get("quotes")
    if isinstance(quotes, dict):
        for symbol in sorted(key for key in quotes if _SYMBOL.fullmatch(str(key))):
            entry = quotes[symbol]
            if not isinstance(entry, dict):
                continue
            summary["quotes_registered"] += 1
            if "incremental_validity_binding" in entry:
                summary["incremental_bindings"].append({"symbol": symbol, "ref": entry["incremental_validity_binding"]})
            if isinstance(entry.get("quote_bundle"), str) and isinstance(entry.get("quote_bundle_sha256"), str):
                summary["bundle_bindings"].append(
                    {"role": f"quote_bundle:{symbol}", "path": entry["quote_bundle"],
                     "sha256": entry["quote_bundle_sha256"]})
    return summary


def _research_registry(root: Path) -> tuple[dict, dict | None, str | None]:
    """Registered research blockers for companies outside the bound snapshot."""
    path = root / REGISTRY_PATH
    if not path.is_file():
        return {}, None, None
    digest = _sha_of(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except STRUCTURE_ERRORS:
        return {}, None, "RESEARCH_REGISTRY_UNREADABLE"
    if (not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA
            or data.get("action") != ACTION):
        return {}, None, "RESEARCH_REGISTRY_INVALID"
    companies = data.get("companies")
    entries: dict[str, dict] = {}
    if isinstance(companies, dict):
        for symbol, entry in companies.items():
            if _SYMBOL.fullmatch(str(symbol)) and isinstance(entry, dict):
                entries[str(symbol)] = entry
    binding = {"role": "company_research_registry", "path": REGISTRY_PATH, "sha256": digest}
    return entries, binding, None


def _registry_evidence(root: Path, entry: Mapping[str, Any]) -> list[dict]:
    evidence = entry.get("evidence")
    checked: list[dict] = []
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict):
            continue
        name, digest = item.get("path"), item.get("sha256")
        target = _repo_path(root, name)
        observed = _sha_of(target) if target is not None else None
        checked.append({"path": name, "sha256": digest,
                        "observed_sha256": observed,
                        "sha256_verified": bool(digest) and observed == digest,
                        "present": observed is not None})
    return checked


def _bound_explanations(root: Path, model: Mapping[str, Any]) -> tuple[dict, set]:
    from .publication_chain import bound_object

    found: dict[str, dict] = {}
    broken: set[str] = set()
    for binding in model.get("additional_evidence_bindings", []):
        if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
            continue
        if not binding["path"].endswith("-value-decision-explanation.json"):
            continue
        symbol = Path(binding["path"]).name.partition("-")[0]
        if not _SYMBOL.fullmatch(symbol):
            continue
        try:
            explanation = bound_object(root, binding)
        except STRUCTURE_ERRORS:
            broken.add(symbol)
            continue
        if (explanation.get("schema_version") == "public-value-decision-explanation-v1"
                and explanation.get("symbol") == symbol and explanation.get("action") == ACTION):
            found[symbol] = explanation
        else:
            broken.add(symbol)
    return found, broken


def _pending_actions(symbol: str, bridge: Mapping[str, Any] | None,
                     decision: Mapping[str, Any] | None,
                     explanation: Mapping[str, Any] | None,
                     registry_entry: Mapping[str, Any] | None) -> list[dict]:
    """User-facing pending work, derived only from real recorded signals."""
    actions: list[dict] = []
    if bridge and bridge.get("needs_re_research") is True:
        actions.append({"code": "RE_RESEARCH_FOR_QUOTE", "actor": "ENGINEERING",
                        "label": f"重跑研究以覆盖 {bridge.get('quote_date')} 收盘，再重跑价格桥接"})
    blockers = [str(item) for item in (decision or {}).get("blockers", []) if isinstance(item, str)]
    blockers.extend(str(item) for item in (explanation or {}).get("blockers", []) if isinstance(item, str))
    joined = " ".join(blockers)
    model_validity = (decision or {}).get("model_validity")
    if bridge and bridge.get("incremental_status"):
        incremental = bridge.get("incremental_validity") or {}
        if bridge["incremental_status"] != "VALID" or bridge.get("blockers"):
            route = incremental.get("materiality_review_route") or {}
            if route.get("status") == "MATERIALITY_HANDOFF_BLOCKED":
                actions.append({"code": "INCREMENTAL_MATERIALITY_HANDOFF_BLOCKED", "actor": "ENGINEERING",
                    "label": "当前公告审核交接绑定未通过；修复证据交接后再办理，不以 G3 替代材料性签署。",
                    "binding_ref": bridge.get("incremental_validity_binding"),
                    "scan_ref": incremental.get("scan_ref")})
            review_cutoff = bridge.get("review_cutoff")
            announcement_count = bridge.get("announcement_count")
            label = (
                f"复核截至 {review_cutoff} 的 {announcement_count} 份公告及原模型适用性；不预支 G3。"
                if isinstance(review_cutoff, str)
                and isinstance(announcement_count, int)
                and announcement_count >= 0
                else "复核增量公告及原模型适用性；公告扫描窗口尚不可读取，不能据此视为已审核或不影响模型；不预支 G3。"
            )
            actions.append({"code": "INCREMENTAL_EVENT_MATERIALITY_REVIEW", "actor": "HUMAN",
                "label": label,
                "binding_ref": bridge.get("incremental_validity_binding"),
                "handoff_status": route.get("status"),
                "next_url": f"/decisions/{symbol}#value-review-handoff",
                "announcements": incremental.get("announcements", []),
                "evidence_refs": incremental.get("source_bindings", [])})
    if isinstance(model_validity, dict) and model_validity.get("status") == "UNKNOWN":
        actions.append({"code": "MODEL_VALIDITY_REVIEW", "actor": "EVIDENCE",
                        "label": "模型有效性未确立；需完成重大事件与假设有效性复核"})
    if "human_research_approval" in joined or "G3" in joined:
        actions.append({"code": "HUMAN_VALUATION_APPROVAL", "actor": "HUMAN",
                        "label": "估值与决策仍待人工门（G3）批准"})
    if "event_materiality" in joined:
        actions.append({"code": "EVENT_MATERIALITY_REVIEW", "actor": "HUMAN",
                        "label": "事件材料性复核未完成"})
    if explanation is not None and explanation.get("requires_human_review") is True:
        actions.append({"code": "HUMAN_RESEARCH_REVIEW", "actor": "HUMAN",
                        "label": "该研究记录要求人工复核"})
    if bridge is None or bridge.get("quote_date") is None:
        actions.append({"code": "AWAITING_VERIFIED_CLOSE", "actor": "EXTERNAL_DATA",
                        "label": "等待双源核验收盘行情登记"})
    if isinstance(registry_entry, dict):
        next_step = registry_entry.get("next_step")
        if isinstance(next_step, str) and next_step:
            actions.append({"code": "REGISTERED_RESEARCH_GAP",
                            "actor": str(registry_entry.get("required_actor") or "ENGINEERING"),
                            "label": next_step})
    seen: set[str] = set()
    unique: list[dict] = []
    for action in actions:
        if action["code"] not in seen:
            seen.add(action["code"])
            unique.append(action)
    return unique


def _company_entry(root: Path, symbol: str, name: str,
                   company: Mapping[str, Any] | None, opportunity: Mapping[str, Any] | None,
                   queue_entry: Mapping[str, Any] | None, decision: Mapping[str, Any] | None,
                   bridge: Mapping[str, Any] | None, explanation: Mapping[str, Any] | None,
                   explanation_broken: bool, registry_entry: Mapping[str, Any] | None) -> dict:
    pending = _pending_actions(symbol, bridge, decision, explanation, registry_entry)
    research_status = ((opportunity or {}).get("research_status")
                       or (company or {}).get("research_status"))
    valuation_status = (opportunity or {}).get("valuation_status")
    entry: dict[str, Any] = {
        "symbol": symbol,
        "name": name,
        "coverage": ("BOUND" if company is not None or opportunity is not None
                     else "QUOTE_ONLY" if bridge is not None else "REGISTERED_ONLY"),
        "research_status": research_status if isinstance(research_status, dict) else None,
        "valuation_status": valuation_status if isinstance(valuation_status, dict) else None,
        "research_version": (explanation or {}).get("research_version") if explanation else None,
        "decision_as_of": (explanation or {}).get("decision_as_of") if explanation else None,
        "price_bridge": bridge,
        "next_trigger": ((company or {}).get("next_trigger") or (opportunity or {}).get("next_trigger")
                         or (queue_entry or {}).get("next_trigger") or (registry_entry or {}).get("next_step")),
        "pending_actions": pending,
        "blockers": [],
    }
    if bridge and bridge.get("incremental_status"):
        for key in ("incremental_status", "review_cutoff", "announcement_count", "model_validity",
                    "incremental_validity_binding", "incremental_validity", "price_comparison"):
            entry[key] = bridge.get(key)
        entry["blockers"].extend(bridge.get("blockers", []))
    if explanation_broken:
        entry["blockers"].append("VALUE_EXPLANATION_BINDING_UNAVAILABLE")
    if not explanation and not decision:
        entry["blockers"].append("RESEARCH_ASSESSMENT_NOT_BOUND")
        if not isinstance(valuation_status, dict) or valuation_status.get("code") != "ADMITTED":
            entry["blockers"].append("VALUATION_NOT_ADMITTED")
        registered_evidence = _registry_evidence(root, registry_entry) if registry_entry else []
        if registered_evidence and all(item["sha256_verified"] for item in registered_evidence):
            pending.append({"code": "REGISTERED_RESEARCH_NOT_FORMALLY_ADMITTED", "actor": "EVIDENCE",
                            "label": "已接通并校验既有研究登记；当前未形成可准入的完整研究决策，按下方具体经济输入缺口处理，不能将历史底稿当作正式估值。"})
        else:
            pending.append({"code": "BIND_CURRENT_RESEARCH_ASSESSMENT", "actor": "ENGINEERING",
                            "label": "核对已有研究及来源，将适用的研究评估、估值准入与决策说明绑定到当前发布，再重新验证；当前缺少绑定不代表不存在历史研究。"})
    if decision:
        entry["valuation_review"] = {
            "model_validity": decision.get("model_validity"),
            "price_attractiveness_status": decision.get("price_attractiveness_status"),
            "conditional_range_present": isinstance(decision.get("valuation_range"), dict),
            "blockers": [str(item) for item in decision.get("blockers", []) if isinstance(item, str)][:24],
        }
    if isinstance(registry_entry, dict):
        evidence = _registry_evidence(root, registry_entry)
        entry["registered_research"] = {
            "status": registry_entry.get("status"),
            "valuation_route": registry_entry.get("valuation_route"),
            "summary": registry_entry.get("summary"),
            "missing_inputs": [item for item in registry_entry.get("missing_inputs", [])
                               if isinstance(item, str)],
            "evidence": evidence,
        }
        if any(not item["sha256_verified"] for item in evidence):
            entry["blockers"].append("REGISTERED_EVIDENCE_CHANGED")
    return entry


def _row_symbols(rows: object) -> list[dict]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows
            if isinstance(row, dict) and _SYMBOL.fullmatch(str(row.get("symbol", "")))]


def decision_chain_view(entry: Mapping[str, Any], plan: Mapping[str, Any]) -> dict:
    """Project recorded qualification separately from workflow ownership.

    This is a public read model, not an additional eligibility engine. Private
    policies and account readiness are deliberately evaluated only after login.
    """
    actor_classes = {"EXTERNAL_DATA": "DATA", "ENGINEERING": "ENGINEERING",
                     "HUMAN": "HUMAN", "EVIDENCE": "EVIDENCE",
                     "STRATEGY": "STRATEGY", "PRIVATE": "PRIVATE"}
    gaps = []
    for task in entry.get("pending_actions", []):
        gaps.append({"code": task["code"],
                     "classification": actor_classes.get(task.get("actor"), "EVIDENCE"),
                     "reason": task["label"],
                     "next_url": task.get("next_url") or f"/decisions/{entry['symbol']}",
                     "evidence_refs": task.get("evidence_refs", [])})
    registered = entry.get("registered_research") or {}
    for field in registered.get("missing_inputs", []):
        gaps.append({"code": "RESEARCH_INPUT_MISSING", "classification": "EVIDENCE",
                     "reason": field, "next_url": f"/decisions/{entry['symbol']}",
                     "evidence_refs": registered.get("evidence", [])})
    bridge = entry.get("price_bridge") or {}
    review = entry.get("valuation_review") or {}
    return {"action": ACTION, "symbol": entry["symbol"],
            "research_version": entry.get("research_version"),
            "identity": {"symbol": entry["symbol"], "name": entry["name"],
                         "scope": "PUBLISHED_RESEARCH_IDENTITY"},
            "market_integrity": {"quote_date": bridge.get("quote_date"),
                                 "price_admitted": bridge.get("price_admitted") is True,
                                 "current_price": bridge.get("current_price")},
            "financial_evidence": registered.get("evidence", []),
            "research_status": entry.get("research_status"),
            "model_applicability": review.get("model_validity") or entry.get("model_validity"),
            "judgment": plan.get("explanation"),
            "research_conclusion": {
                "status": registered.get("status"),
                "summary": registered.get("summary") if registered.get("evidence")
                    and all(item.get("sha256_verified") is True
                            for item in registered["evidence"]) else None,
                "evidence_verified": bool(registered.get("evidence")) and
                    all(item.get("sha256_verified") is True for item in registered["evidence"]),
                "scope": "RESEARCH_INTERPRETATION_NOT_INVESTMENT_APPROVAL",
            },
            "price_conditions": {key: plan.get(key) for key in (
                "entry_trigger_price", "add_trigger_price", "reduce_trigger_price", "exit_trigger_price")},
            "formal_eligibility": plan.get("formal_eligibility") is True,
            "private_qualification": {"status": "AUTHENTICATED_VIEW_REQUIRED", "next_url": "/portfolio"},
            "gaps": gaps,
            "next_actions": entry.get("pending_actions", [])}


def count_formal_admissions(rows: list[dict]) -> int:
    """Formal admissions from the published rows, counted once per security.

    A symbol can legitimately appear in the company snapshot, the opportunity
    list and the research queue at the same time; that is one formal admission,
    not three.
    """
    admitted: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "")
        status = row.get("valuation_status")
        if _SYMBOL.fullmatch(symbol) and isinstance(status, dict) \
                and status.get("code") == "ADMITTED":
            admitted.add(symbol)
    return len(admitted)


def _universe_count(root: Path, model: Mapping[str, Any], discovery: Mapping[str, Any]) -> int | None:
    """Universe size from the published report health, never invented."""
    health = discovery.get("data_health")
    if isinstance(health, dict) and isinstance(health.get("universe_count"), int):
        return health["universe_count"]
    binding = (model.get("product_extensions") or {}).get("value_discovery_report")
    if not isinstance(binding, dict):
        return None
    from .publication_chain import bound_object

    try:
        report = bound_object(root, binding)
    except STRUCTURE_ERRORS:
        return None
    health = report.get("data_health")
    if isinstance(health, dict) and isinstance(health.get("universe_count"), int):
        return health["universe_count"]
    return None


def _verified_bindings(root: Path, bindings: list[dict],
                       outside_roles: frozenset[str] = frozenset()) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    blockers: list[str] = []
    for binding in bindings:
        role, name, expected = binding.get("role"), binding.get("path"), binding.get("sha256")
        target = Path(name) if role in outside_roles and isinstance(name, str) else _repo_path(root, name)
        observed = _sha_of(target) if isinstance(target, Path) else None
        verified = bool(observed is not None and isinstance(expected, str) and observed == expected)
        rows.append({"role": role, "path": name, "sha256": expected,
                     "present": observed is not None, "sha256_verified": verified})
        if not verified:
            blockers.append(f"SOURCE_BINDING_HASH_MISMATCH:{role}")
    return rows, blockers


def _unavailable_packet(now: datetime, natural_day: str, chain_error: str | None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "action": ACTION,
        "packet_status": "UNAVAILABLE",
        "publication_id": None,
        "research_version": None,
        "generated_at": now.isoformat(),
        "generated_at_china": now.astimezone(CHINA).isoformat(),
        "content_sha256": None,
        "identity_inputs": None,
        "chain_error": chain_error,
        "quote_bridge": None,
        "dates": {"current_natural_date": natural_day,
                  "latest_completed_trade_session": None, "quote_trade_date": None,
                  "quote_observed_at": None, "research_as_of": None,
                  "model_validity": {"status": "NOT_EVALUATED", "valid_through": None},
                  "decision_published_on": None, "excel_published_as_of": None,
                  "excel_quote_observation_as_of": None},
        "source_bindings": [],
        "source_bindings_verified": False,
        "company_statuses": {},
        "valuation_statuses": {},
        "price_bridge_statuses": {},
        "event_review_statuses": {},
        "formal_admission_count": 0,
        "pending_review_count": 0,
        "research_counts": {"universe_count": None, "lead_count": None, "queue_count": None,
                            "needs_re_research_count": 0, "incomplete_research_count": 0,
                            "awaiting_verified_close_count": 0},
        "blockers": ["PUBLICATION_CHAIN_UNAVAILABLE"],
        "data_freshness": {
            "quote": {"status": "UNKNOWN", "quote_date": None,
                      "latest_completed_trade_session": None,
                      "reason": "发布链不可用，未读取行情登记。"},
            "research": {"status": "UNKNOWN", "research_as_of": None,
                         "reason": "发布链不可用，未读取研究状态。"},
            "excel": {"status": "UNKNOWN", "as_of": None,
                      "note": "发布链不可用，无法确认 Excel 与 Web 的版本对应。"}},
        "excel_sync": None,
    }


def unavailable_packet(*, generated_at: datetime | None = None,
                       chain_error: str | None = None) -> dict:
    """Public fail-closed shape for callers whose own composition failed."""
    now = _now(generated_at)
    return _unavailable_packet(now, now.astimezone(CHINA).date().isoformat(), chain_error)


def build_daily_public_packet(root: Path, *, generated_at: datetime | None = None,
                              excel_path: Path | None = None) -> dict:
    """Compose the one daily public decision packet; never raises on bad inputs."""
    root = Path(root).resolve()
    now = _now(generated_at)
    natural_day = now.astimezone(CHINA).date().isoformat()
    chain, chain_error = try_load_current_chain(root)
    if chain is None:
        return _unavailable_packet(now, natural_day, chain_error)

    pointer = chain["pointer"]
    model = chain["model"]
    state = chain["state"]
    publication = pointer.get("current_publication") if isinstance(pointer.get("current_publication"), dict) else {}
    snapshot = model.get("snapshot") if isinstance(model.get("snapshot"), dict) else {}
    content = state.get("content") if isinstance(state.get("content"), dict) else {}
    extensions = content.get("extensions") if isinstance(content.get("extensions"), dict) else {}
    state_companies = content.get("companies") if isinstance(content.get("companies"), dict) else {}
    queue = extensions.get("value_research_queue") if isinstance(extensions.get("value_research_queue"), dict) else {}
    companies = _row_symbols(snapshot.get("companies"))
    opportunities = _row_symbols(snapshot.get("opportunities"))
    queue_entries = _row_symbols(queue.get("entries"))

    explanations, broken_explanations = _bound_explanations(root, model)
    registry_entries, registry_binding, registry_error = _research_registry(root)
    bridge_rows, bridge_blockers = _bridge_rows(root, now)
    price_bridge_statuses = {}
    for execution in bridge_rows:
        symbol = str(execution.get("symbol") or "")
        if symbol:
            price_bridge_statuses[symbol] = _bridge_status(execution)

    names: dict[str, str] = {}
    for row in [*companies, *opportunities, *queue_entries]:
        name = row.get("company_name")
        if isinstance(name, str) and name:
            names[str(row["symbol"])] = name
    for symbol, entry in registry_entries.items():
        if isinstance(entry.get("name"), str) and entry["name"]:
            names.setdefault(symbol, entry["name"])

    by_symbol = {str(row["symbol"]): row for row in companies}
    opp_by_symbol = {str(row["symbol"]): row for row in opportunities}
    queue_by_symbol = {str(row["symbol"]): row for row in queue_entries}
    symbols = sorted(set(by_symbol) | set(opp_by_symbol) | set(price_bridge_statuses)
                     | set(state_companies) | set(registry_entries))
    company_statuses: dict[str, dict] = {}
    valuation_statuses: dict[str, dict] = {}
    event_review_statuses: dict[str, dict] = {}
    blockers = list(bridge_blockers)

    research_as_of = snapshot.get("as_of") if isinstance(snapshot.get("as_of"), str) else None
    pointer_research = publication.get("research_as_of")
    if isinstance(pointer_research, str) and research_as_of and pointer_research != research_as_of:
        blockers.append("POINTER_RESEARCH_DATE_MISMATCH")

    model_validity_states: list[str] = []
    for symbol in symbols:
        state_entry = state_companies.get(symbol)
        decision = state_entry.get("decision") if isinstance(state_entry, dict) else None
        decision = decision if isinstance(decision, dict) else None
        bridge = price_bridge_statuses.get(symbol)
        explanation = explanations.get(symbol)
        status_entry = _company_entry(
            root, symbol, names.get(symbol, symbol), by_symbol.get(symbol),
            opp_by_symbol.get(symbol), queue_by_symbol.get(symbol), decision, bridge,
            explanation, symbol in broken_explanations, registry_entries.get(symbol))
        company_statuses[symbol] = status_entry
        if decision is not None:
            validity = decision.get("model_validity")
            if isinstance(validity, dict):
                model_validity_states.append(str(validity.get("status")))
            valuation_range = decision.get("valuation_range")
            valuation_statuses[symbol] = {
                "symbol": symbol,
                "published_code": (opp_by_symbol.get(symbol, {}).get("valuation_status") or {}).get("code")
                if isinstance(opp_by_symbol.get(symbol, {}).get("valuation_status"), dict) else None,
                "conditional_range": ({key: valuation_range[key] for key in ("bear", "base", "bull", "currency")
                                       if key in valuation_range} if isinstance(valuation_range, dict) else None),
                "model_validity": decision.get("model_validity"),
                "price_attractiveness_status": decision.get("price_attractiveness_status"),
                "blocker_count": len([item for item in decision.get("blockers", []) if isinstance(item, str)]),
            }
            joined = " ".join(str(item) for item in decision.get("blockers", []) if isinstance(item, str))
            if "event_materiality" in joined:
                event_review_statuses[symbol] = {"status": "PENDING_REVIEW",
                                                 "source": "STATE_DECISION_BLOCKERS"}
            else:
                event_review_statuses[symbol] = {"status": "REGISTERED",
                                                 "source": "STATE_DECISION_BLOCKERS"}
        elif explanation is not None:
            event_review_statuses[symbol] = {"status": "REGISTERED", "source": "EXPLANATION"}
        else:
            event_review_statuses[symbol] = {"status": "NOT_REGISTERED", "source": None}
        if bridge and bridge.get("incremental_status"):
            model_validity_states.append(str(bridge["incremental_status"]))
            valuation_statuses.setdefault(symbol, {"symbol": symbol, "conditional_range": None})
            valuation_statuses[symbol].update(model_validity=bridge.get("model_validity"),
                price_comparison=bridge.get("price_comparison"),
                incremental_validity_binding=bridge.get("incremental_validity_binding"))
            event_review_statuses[symbol] = {"status": bridge["incremental_status"],
                "source": "EXPLICIT_INCREMENTAL_BINDING", "review_cutoff": bridge.get("review_cutoff"),
                "announcement_count": bridge.get("announcement_count"),
                "binding_ref": bridge.get("incremental_validity_binding"),
                "announcements": (bridge.get("incremental_validity") or {}).get("announcements", []),
                "blockers": bridge.get("blockers", [])}
            blockers.extend(f"INCREMENTAL_VALIDITY:{symbol}:{item}" for item in bridge.get("blockers", []))
        if bridge and bridge.get("needs_re_research"):
            blockers.append(f"NEEDS_RE_RESEARCH:{symbol}")
        if bridge and bridge.get("quote_date") and not bridge.get("price_admitted"):
            blockers.append(f"PRICE_NOT_ADMITTED:{symbol}")
        if isinstance(decision, dict):
            validity = decision.get("model_validity")
            if isinstance(validity, dict) and validity.get("status") == "UNKNOWN":
                blockers.append(f"MODEL_VALIDITY_UNKNOWN:{symbol}")

    if model_validity_states:
        unique_states = set(model_validity_states)
        validity_status = ("UNKNOWN" if unique_states == {"UNKNOWN"}
                           else "PARTIAL" if "UNKNOWN" in unique_states else "KNOWN")
    else:
        validity_status = "NOT_EVALUATED"

    quote_dates = sorted({row["quote_date"] for row in price_bridge_statuses.values()
                          if isinstance(row.get("quote_date"), str)})
    latest_sessions = sorted({row["latest_completed_session"] for row in price_bridge_statuses.values()
                              if isinstance(row.get("latest_completed_session"), str)})
    observed = sorted({row["quote_observed_at"] for row in price_bridge_statuses.values()
                       if isinstance(row.get("quote_observed_at"), str)})
    dates = {
        "current_natural_date": natural_day,
        "latest_completed_trade_session": latest_sessions[-1] if latest_sessions else None,
        "quote_trade_date": quote_dates[-1] if quote_dates else None,
        "quote_observed_at": observed[-1] if observed else None,
        "research_as_of": research_as_of,
        "model_validity": {"status": validity_status, "valid_through": None},
        "decision_published_on": publication.get("registered_at") if isinstance(publication.get("registered_at"), str) else None,
        "excel_published_as_of": pointer.get("as_of") if isinstance(pointer.get("as_of"), str) else None,
        "excel_quote_observation_as_of": publication.get("quote_observation_as_of") if isinstance(publication.get("quote_observation_as_of"), str) else None,
    }

    formal_count = count_formal_admissions([*companies, *opportunities, *queue_entries])
    human_pending = sum(1 for entry in company_statuses.values()
                        if any(action["actor"] == "HUMAN" for action in entry["pending_actions"]))
    needs_re_research = sum(1 for row in price_bridge_statuses.values() if row["needs_re_research"])
    incomplete = len({str(row.get("symbol"))
                      for row in opportunities
                      if isinstance(row.get("valuation_status"), dict)
                      and row["valuation_status"].get("code") in {"NOT_READY", "UNDER_REVIEW"}})
    awaiting_close = sum(1 for entry in company_statuses.values()
                         if any(action["actor"] == "EXTERNAL_DATA" for action in entry["pending_actions"]))
    discovery = extensions.get("value_discovery_report")
    discovery = discovery if isinstance(discovery, dict) else {}
    health = discovery.get("data_health")
    leads = discovery.get("lead_symbols")
    research_counts = {
        "universe_count": _universe_count(root, model, discovery),
        "lead_count": len(leads) if isinstance(leads, list) else None,
        "queue_count": len(queue_entries),
        "needs_re_research_count": needs_re_research,
        "incomplete_research_count": incomplete,
        "awaiting_verified_close_count": awaiting_close,
    }

    if not price_bridge_statuses:
        quote_freshness = {"status": "UNAVAILABLE", "quote_date": None,
                           "latest_completed_trade_session": dates["latest_completed_trade_session"],
                           "reason": "尚未登记双源收盘行情。"}
    else:
        latest = dates["latest_completed_trade_session"]
        newest_quote = dates["quote_trade_date"]
        if latest is None:
            quote_freshness = {"status": "UNKNOWN", "quote_date": newest_quote,
                               "latest_completed_trade_session": None,
                               "reason": "归档日历未给出最近已完成交易日，无法判定行情新鲜度。"}
        elif newest_quote == latest:
            quote_freshness = {"status": "FRESH", "quote_date": newest_quote,
                               "latest_completed_trade_session": latest,
                               "reason": f"已登记行情 {newest_quote} 即最近已完成交易日。"}
        else:
            quote_freshness = {"status": "STALE", "quote_date": newest_quote,
                               "latest_completed_trade_session": latest,
                               "reason": f"已登记行情日 {newest_quote} 早于最近已完成交易日 {latest}；需采集并登记新收盘。"}
    re_research_pairs = [row for row in price_bridge_statuses.values()
                         if isinstance(row.get("quote_date"), str) and isinstance(row.get("research_day"), str)]
    if not re_research_pairs:
        research_freshness = {"status": "UNKNOWN", "research_as_of": research_as_of,
                              "reason": "尚未登记行情，无法判定研究是否覆盖报价。"}
    else:
        stale_pairs = [row for row in re_research_pairs if row["quote_date"] > row["research_day"]]
        if stale_pairs and all(row.get("incremental_status") for row in stale_pairs):
            covered = all(row.get("comparison_eligible") is True for row in stale_pairs)
            research_freshness = {"status": "INCREMENTALLY_COVERS" if covered else "INCREMENTAL_REVIEW_PENDING",
                                  "research_as_of": research_as_of,
                                  "reason": ("原研究截止日保持不变；增量有效性支持条件性价格比较，正式投资资格另行核验。" if covered else
                                             "已接入增量公告复核；按具体材料性、模型及证据缺口处理，日期推进本身不要求重做整份研究。")}
        elif stale_pairs:
            research_freshness = {"status": "STALE", "research_as_of": research_as_of,
                                  "reason": (f"报价日 {max(row['quote_date'] for row in stale_pairs)} 晚于研究截止日；"
                                             "需重跑研究并完成事件复核后才能形成正式价格比较。")}
        else:
            research_freshness = {"status": "COVERS", "research_as_of": research_as_of,
                                  "reason": "登记研究截止日覆盖已登记报价日。"}
    data_freshness = {
        "quote": quote_freshness,
        "research": research_freshness,
        "excel": {"status": "SNAPSHOT", "as_of": dates["excel_published_as_of"],
                  "note": "Web 读取发布链；唯一正式 Excel 为发布快照，不会自动被覆盖。"},
    }

    excel_sync = None
    if excel_path is not None:
        expected = pointer.get("canonical_workbook_sha256")
        observed_workbook = _sha_of(Path(excel_path))
        if observed_workbook is None or not isinstance(expected, str):
            # The file is unreadable or the pointer carries no published hash:
            # the comparison is impossible, which is never "in sync".
            excel_status, matches = "NOT_VERIFIED", None
        elif observed_workbook == expected:
            excel_status, matches = "MATCHED", True
        else:
            excel_status, matches = "DIFFERENT", False
        excel_sync = {"path": str(excel_path), "status": excel_status,
                      "expected_sha256": expected if isinstance(expected, str) else None,
                      "observed_sha256": observed_workbook, "matches": matches,
                      "checked_at": now.isoformat(),
                      "note": "只读校验：不覆盖、不重建正式工作簿。"}
        if excel_status == "DIFFERENT":
            blockers.append("EXCEL_AND_WEB_VERSION_DIFFER")
        elif excel_status == "NOT_VERIFIED":
            blockers.append("EXCEL_VERSION_NOT_VERIFIED")

    quote_summary = _quote_pointer_summary(root)
    binding_inputs = list(chain["bindings"])
    if quote_summary["sha256"]:
        binding_inputs.append({"role": "quote_bridge_pointer", "path": QUOTE_POINTER_PATH,
                               "sha256": quote_summary["sha256"]})
    binding_inputs.extend(quote_summary["bundle_bindings"])
    if registry_binding is not None:
        binding_inputs.append(registry_binding)
    # The formal-workbook comparison is a read-time view check (``excel_sync``,
    # excluded from ``content_sha256``): whether the caller asked for it must
    # never change the decision content or the version identity.
    source_bindings, binding_blockers = _verified_bindings(root, binding_inputs)
    blockers.extend(binding_blockers)

    if registry_error is not None:
        blockers.append(registry_error)
    for symbol, entry in company_statuses.items():
        blockers.extend(f"{code}:{symbol}" for code in entry["blockers"])
        registered = entry.get("registered_research")
        if registered and any(not item["sha256_verified"] for item in registered["evidence"]):
            blockers.append(f"REGISTERED_EVIDENCE_CHANGED:{symbol}")
    if formal_count == 0:
        blockers.append("NO_FORMAL_ADMISSION")
    deduped: list[str] = []
    for code in blockers:
        if code not in deduped:
            deduped.append(code)

    receipt_binding = next((item for item in chain["bindings"]
                            if item["role"] == "publication_receipt"), None)
    value_plans = load_current_value_action_plans(root, now=now)
    identity = identity_inputs(
        root, chain, natural_day=natural_day,
        latest_completed_session=dates["latest_completed_trade_session"],
        evaluated_at=now, value_plans=value_plans)
    current_conditions = load_price_conditions(root, now=now,
        research_version=_stem(receipt_binding["path"]) if receipt_binding else None)
    if "case_reviews" in current_conditions:
        # The packet's generated_at already records this inspection. Keep all
        # source/availability times and outcomes hashed; only the redundant
        # wall-clock stamp must not change a same-input publication on retry.
        current_conditions = {**current_conditions, "case_reviews": [
            {key: value for key, value in review.items() if key != "evaluated_at"}
            for review in current_conditions["case_reviews"]]}
    deduped = list(dict.fromkeys([*deduped, *current_conditions["blockers"]]))
    value_conditions = {}
    registered_plans = {plan["symbol"]: plan for plan in value_plans["items"]}
    deduped = list(dict.fromkeys([*deduped, *value_plans["blockers"]]))
    for symbol, entry in company_statuses.items():
        valuation = valuation_statuses.get(symbol, {})
        bridge = price_bridge_statuses.get(symbol, {})
        source_decision = (state_companies.get(symbol) or {}).get("decision") or {}
        explanation = explanations.get(symbol) or {}
        value_blockers = list(dict.fromkeys([*entry["blockers"],
            *source_decision.get("blockers", []), *explanation.get("blockers", []),
            *(["PRICE_NOT_ADMITTED"] if not bridge.get("price_admitted") else [])]))
        value_conditions[symbol] = {
            "schema_version": "value-price-observation-v1", "action": ACTION,
            "strategy": "CORE_VALUE", "symbol": symbol, "decision_id": symbol,
            "research_version": entry.get("research_version"),
            "market_trade_date": bridge.get("quote_date"),
            "current_reference_price": bridge.get("current_price"),
            "conditional_valuation_range": valuation.get("conditional_range"),
            "entry_trigger_price": None, "add_trigger_price": None,
            "reduce_trigger_price": None, "exit_trigger_price": None,
            "invalidation_price": None, "signal_state": "WATCH",
            "action_eligibility": False, "blockers": value_blockers,
            "required_confirmations": value_blockers,
            "next_observation": [action["label"] for action in entry["pending_actions"]],
            "support": explanation.get("support"), "counter": explanation.get("counter_evidence"),
            "exit_condition": explanation.get("exit_conditions"),
            "explanation": ("当前发布尚未绑定适用的研究评估与决策说明，估值准入须独立核验；不是仅缺行情，也不代表不存在历史研究。"
                            if "RESEARCH_ASSESSMENT_NOT_BOUND" in value_blockers
                            else "估值情景仅供研究观察；尚无经完整准入的建仓、加减仓阈值。"),
            "model_or_rule_version": entry.get("research_version"),
        }
        if symbol in registered_plans:
            plan = registered_plans[symbol]
            value_conditions[symbol].update(plan)
            value_conditions[symbol].update(decision_id=symbol,
                current_reference_price=plan["reference_close"],
                conditional_valuation_range=({key: plan[key] for key in ('bear', 'base', 'bull')}
                    if all(plan.get(key) is not None for key in ('bear', 'base', 'bull')) else None),
                action_eligibility=plan["formal_eligibility"],
                support=plan["supporting_facts"], counter=plan["counter_evidence"],
                blockers=plan["blockers"],
                publication_blockers=list(dict.fromkeys([*value_blockers, *plan["blockers"]])))
        pending_source_plan = (symbol in registered_plans
            and registered_plans[symbol].get('verification_scope') == 'SOURCE_BOUND_PENDING_ARITHMETIC_NOT_APPROVAL'
            and registered_plans[symbol].get('formal_eligibility') is False)
        if "RESEARCH_ASSESSMENT_NOT_BOUND" in entry["blockers"] and not pending_source_plan:
            value_conditions[symbol].update(
                action_eligibility=False,
                formal_eligibility=False,
                formal_eligibility_blockers=list(dict.fromkeys([
                    *value_conditions[symbol].get("formal_eligibility_blockers", []),
                    *entry["blockers"]])),
                required_confirmations=value_conditions[symbol]["blockers"],
                next_observation=[action["label"] for action in entry["pending_actions"]],
                explanation="当前发布尚未绑定适用的研究评估与决策说明，估值准入须独立核验；不是仅缺行情，也不代表不存在历史研究。")
    for symbol, entry in company_statuses.items():
        entry["decision_chain"] = decision_chain_view(entry, value_conditions.get(symbol, {}))
    packet = {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "action": ACTION,
        "packet_status": "CURRENT",
        "publication_id": publication_identity(identity),
        "identity_inputs": identity,
        "research_version": _stem(receipt_binding["path"]) if receipt_binding else None,
        "generated_at": now.isoformat(),
        "generated_at_china": now.astimezone(CHINA).isoformat(),
        "content_sha256": None,
        "chain_error": None,
        "quote_bridge": {"path": QUOTE_POINTER_PATH, "sha256": quote_summary["sha256"],
                         "registered_at": quote_summary["registered_at"],
                         "quotes_registered": quote_summary["quotes_registered"]},
        "dates": dates,
        "source_bindings": source_bindings,
        "source_bindings_verified": (all(item["sha256_verified"] for item in source_bindings)
                                     and not current_conditions["blockers"]),
        "company_statuses": company_statuses,
        "price_conditions": current_conditions,
        "value_price_conditions": value_conditions,
        "value_action_policy_inventory": value_plans["policy_inventory"],
        "valuation_statuses": valuation_statuses,
        "price_bridge_statuses": price_bridge_statuses,
        "event_review_statuses": event_review_statuses,
        "formal_admission_count": formal_count,
        "pending_review_count": human_pending,
        "research_counts": research_counts,
        "blockers": deduped,
        "data_freshness": data_freshness,
        "excel_sync": excel_sync,
    }
    packet["content_sha256"] = packet_content_sha256(packet)
    return packet


def publication_block(root: Path, chain: Mapping[str, Any], *,
                      generated_at: datetime | None = None) -> dict:
    """Compact identity block shared by every public endpoint.

    When a verified daily public snapshot exists, every endpoint reports the
    identity of that one frozen version instead of recomposing a private one.
    Without a published snapshot yet (fresh checkout, tests) the block falls
    back to composing the same identity inputs live, marked as such.
    """
    now = _now(generated_at)
    root = Path(root)
    from .public_snapshot import load_current_packet

    stored, _ = load_current_packet(root)
    if isinstance(stored, dict):
        dates = stored.get("dates") if isinstance(stored.get("dates"), dict) else {}
        quote_bridge = stored.get("quote_bridge") if isinstance(stored.get("quote_bridge"), dict) else None
        return {
            "schema_version": SCHEMA_VERSION,
            "engine_version": stored.get("engine_version") or ENGINE_VERSION,
            "action": ACTION,
            "packet_status": "CURRENT",
            "snapshot_status": "VERIFIED",
            "publication_id": stored.get("publication_id"),
            "research_version": stored.get("research_version"),
            "research_as_of": dates.get("research_as_of"),
            "decision_published_on": dates.get("decision_published_on"),
            "excel_published_as_of": dates.get("excel_published_as_of"),
            "quote_bridge": quote_bridge,
            "source_binding_count": len(stored.get("source_bindings") or []),
            "generated_at": stored.get("generated_at"),
        }
    summary = _quote_pointer_summary(root)
    pointer = chain["pointer"]
    publication = pointer.get("current_publication") if isinstance(pointer.get("current_publication"), dict) else {}
    receipt_binding = next((item for item in chain["bindings"]
                            if item["role"] == "publication_receipt"), None)
    snapshot = chain["handoff"].get("snapshot") if isinstance(chain["handoff"].get("snapshot"), dict) else {}
    bridge_rows, _ = _bridge_rows(root, now)
    sessions = sorted({str((_bridge_status(row) or {}).get("latest_completed_session"))
                       for row in bridge_rows
                       if isinstance((_bridge_status(row) or {}).get("latest_completed_session"), str)})
    identity = identity_inputs(root, chain, natural_day=now.astimezone(CHINA).date().isoformat(),
                               latest_completed_session=sessions[-1] if sessions else None, evaluated_at=now)
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "action": ACTION,
        "packet_status": "CURRENT",
        "snapshot_status": "NO_VERIFIED_SNAPSHOT",
        "publication_id": publication_identity(identity),
        "research_version": _stem(receipt_binding["path"]) if receipt_binding else None,
        "research_as_of": snapshot.get("as_of") if isinstance(snapshot.get("as_of"), str) else None,
        "decision_published_on": publication.get("registered_at") if isinstance(publication.get("registered_at"), str) else None,
        "excel_published_as_of": pointer.get("as_of") if isinstance(pointer.get("as_of"), str) else None,
        "quote_bridge": {"registered_at": summary["registered_at"],
                         "sha256": summary["sha256"],
                         "quotes_registered": summary["quotes_registered"]},
        "source_binding_count": len(chain["bindings"]),
        "generated_at": now.isoformat(),
    }


def publication_block_unavailable(*, generated_at: datetime | None = None) -> dict:
    """Compact identity block for a broken chain: no invented identity."""
    now = _now(generated_at)
    return {"schema_version": SCHEMA_VERSION, "action": ACTION,
            "engine_version": ENGINE_VERSION,
            "packet_status": "UNAVAILABLE", "snapshot_status": "UNAVAILABLE",
            "publication_id": None,
            "research_version": None, "research_as_of": None,
            "decision_published_on": None, "excel_published_as_of": None,
            "quote_bridge": None, "source_binding_count": 0,
            "generated_at": now.isoformat()}

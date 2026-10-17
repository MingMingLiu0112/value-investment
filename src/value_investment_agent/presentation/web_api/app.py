"""Hash-bound, read-only projections of the current published product."""
from __future__ import annotations

import json
import hashlib
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from ...application.product.daily_public_packet import (
    SCHEMA_VERSION as PACKET_SCHEMA,
    build_daily_public_packet,
    count_formal_admissions,
    publication_block,
    publication_block_unavailable,
    unavailable_packet,
)
from ...application.product.daily_research_status import build_daily_research_status
from ...application.product.dual_sleeve_risk import run_dual_sleeve_review
from ...application.product.publication_chain import (
    STRUCTURE_ERRORS as _STRUCTURE_ERRORS,
    bound_object as _bound,
    load_current_chain as _current,
)
from ...application.product.public_snapshot import (
    load_current_packet as _load_snapshot,
)
from ...application.product.public_snapshot import (
    snapshot_metadata as _snapshot_metadata,
)
from ...application.product.public_snapshot import (
    workbook_version_report as _workbook_report,
)
from ...application.product.quote_bridge import execute_quote_bridge_for_symbol
from ...application.product.research_draft import load_current_research_draft
from ...application.product.research_funnel_status import research_funnel_status
from ...application.hotspot.price_action_case import project_price_action_plan
from ...application.decision.current_value_plan import revalidate_current_value_plan
from ...infrastructure.hotspot.sina_price_case import load_historical_case
from ...infrastructure.hotspot.current_price_case import load_current_price_case
from ..read_models.dual_sleeve_surface import (
    BLOCKER_SURFACE_INVALID,
    build_dual_sleeve_surface,
    unavailable as dual_sleeve_unavailable,
)
from ..read_models.research_history import build_research_history
from ..read_models.value_decision_detail import project_value_decision_detail
from .local_auth import (
    BOOTSTRAP_ENV,
    SESSION_HEADER,
    SESSION_TTL_SECONDS,
    LocalAuthorizationError,
    LocalOperatorSession,
    authorize,
)
from .private_routes import portfolio_connection, register_private_routes
from .runtime_identity import data_freshness, git_head, runtime_identity, sha256
from .value_policy_routes import register_value_policy_routes
from ...application.decision.value_policy_interaction import (
    ValuePolicyInteractionService, PolicyPrincipal, PERMISSION,
)


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PORT = 8001
_ID = re.compile(r"[0-9]{6}\Z")
_UNAVAILABLE_RESEARCH = {"schema_version": "daily-research-status-v1", "action": "no_order",
                         "status": "UNAVAILABLE", "registered_count": 0, "rows": [],
                         "blockers": ["RESEARCH_STATUS_UNAVAILABLE"]}


def _public(root: Path) -> dict | None:
    try:
        return _current(root)
    except _STRUCTURE_ERRORS:
        return None


def _publication_block(root: Path, current: dict | None) -> dict:
    """The compact identity block every public endpoint must share (TL9 MVP-1)."""
    if current is None:
        return publication_block_unavailable()
    try:
        return publication_block(root, current)
    except _STRUCTURE_ERRORS:
        return publication_block_unavailable()


def _binding_path(model: dict, role: str) -> str | None:
    """Name the artifact a failure came from, without reading it again."""
    binding = (model.get("product_extensions") or {}).get(role)
    if isinstance(binding, dict) and isinstance(binding.get("path"), str):
        return binding["path"]
    return None


def _unavailable(code: str, reason: str, *, source: str | None = None) -> dict:
    """Fail closed on a broken publication chain without inventing any count."""
    body = {"action": "no_order", "status": "UNAVAILABLE", "as_of": None,
            "market": {"status": "UNKNOWN", "reason": reason},
            "summary": {"universe_count": None, "formal_count": 0, "watch_count": None},
            "sections": {"holdings": [], "value": [], "hotspot": []},
            "research": dict(_UNAVAILABLE_RESEARCH),
            "dual_sleeve": dual_sleeve_unavailable(),
            "publication": publication_block_unavailable(),
            "blockers": [code], "gate_code": code, "reason": reason}
    if source is not None:
        body["publication_source"] = source
    return body


def _pick(value: dict, *keys: str) -> dict:
    return {key: value[key] for key in keys if key in value}


def _quote_bridge_execution(root: Path, symbol: str) -> dict | None:
    """Execute the registered price bridge; a broken registration degrades, never raises."""
    try:
        return execute_quote_bridge_for_symbol(root, symbol, today=datetime.now(timezone.utc))
    except _STRUCTURE_ERRORS:
        return None


def _daily_research(root: Path, names: dict[str, str]) -> dict:
    """Compose the registered research/close status; a broken chain degrades, never raises."""
    try:
        return build_daily_research_status(root, today=datetime.now(timezone.utc), names=names)
    except _STRUCTURE_ERRORS:
        return dict(_UNAVAILABLE_RESEARCH)


def _item(row: dict, as_of: str, status: str = "RESEARCH_ONLY") -> dict:
    symbol = row["symbol"]
    return {"id": symbol, "symbol": symbol, "name": row.get("company_name", symbol),
            "strategy": "value", "status": status, "candidate_action": "no_order",
            "reason": row.get("why_now") or row.get("next_trigger") or "研究证据仍待复核",
            "as_of": as_of}


def _queue_item(row: dict, as_of: str) -> dict:
    reasons = row.get("screening_reasons", [])
    item = _item(row, as_of)
    item["reason"] = reasons[0] if isinstance(reasons, list) and reasons and isinstance(reasons[0], str) else "待完成数据核验"
    item["why_selected"] = item["reason"]
    item["channels"] = [part for part in row.get("channels", []) if isinstance(part, str)]
    item["blockers"] = [part for part in row.get("gaps", []) if isinstance(part, str)]
    return item


_EXPLANATION_FIELDS = ("support", "counter_evidence", "thesis_breakers", "blockers",
                       "price_context", "next_events")


def _attach_value_explanations(root: Path, model: dict, items: list[dict]) -> list[dict]:
    """Copy bound value explanations onto list rows without hiding a broken binding."""
    explanations: dict[str, dict] = {}
    unreadable: set[str] = set()
    for binding in model.get("additional_evidence_bindings", []):
        if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
            continue
        if not binding["path"].endswith("-value-decision-explanation.json"):
            continue
        symbol = Path(binding["path"]).name.partition("-")[0]
        if not _ID.fullmatch(symbol):
            continue
        try:
            explanation = _bound(root, binding)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
            unreadable.add(symbol)
            continue
        if (explanation.get("schema_version") == "public-value-decision-explanation-v1"
                and explanation.get("symbol") == symbol and explanation.get("action") == "no_order"):
            explanations[symbol] = explanation
        else:
            unreadable.add(symbol)
    for item in items:
        symbol = str(item.get("id", ""))
        explanation = explanations.get(symbol)
        if explanation is not None:
            item.update(_pick(explanation, *_EXPLANATION_FIELDS))
        if symbol in unreadable:
            item["blockers"] = [*(item.get("blockers") or []), "VALUE_EXPLANATION_BINDING_UNAVAILABLE"]
    return items


def _default_port() -> int:
    raw = os.environ.get("VALUE_INVESTMENT_WEB_PORT", "")
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_PORT
    return port if 1024 <= port <= 65535 else DEFAULT_PORT


def create_app(
    root: Path | None = None,
    *,
    port: int | None = None,
    session_ttl_seconds: float = SESSION_TTL_SECONDS,
    bootstrap_secret: str | None = None,
    value_policy_service: ValuePolicyInteractionService | None = None,
) -> FastAPI:
    # Root injection is for in-process tests; no HTTP parameter or environment override exists.
    project = (root or ROOT).resolve()
    backend_module = Path(__file__).resolve()
    backend_head = git_head(project)
    backend_module_sha = sha256(backend_module)
    bound_port = port if port is not None else _default_port()
    # The launcher exports a per-run secret; without one the workbench stays
    # locked, so an accidentally exposed process never serves the private API.
    secret = bootstrap_secret if bootstrap_secret is not None else os.environ.get(BOOTSTRAP_ENV)
    sessions = LocalOperatorSession(bootstrap_secret=secret, ttl_seconds=session_ttl_seconds)
    api = FastAPI(title="Value Investment Read API")

    def current_items(packet):
        rows = (packet or {}).get("price_conditions", {}).get("items", [])
        registry = (packet or {}).get("identity_inputs", {}).get("current_price_conditions")
        registry_matches = True
        if registry is not None:
            try:
                observed = hashlib.sha256((project / "config/current-price-conditions.json").read_bytes()).hexdigest()
                registry_matches = observed == registry["observed_sha256"]
            except (OSError, KeyError, TypeError):
                registry_matches = False
        checked = []
        for row in rows:
            plan = row["price_action_plan"]
            try:
                if not registry_matches:
                    raise ValueError("Current price registry differs from frozen publication")
                load_current_price_case(root=project, symbol=row["symbol"],
                    case_path=Path(plan["case_path"]), expected_sha256=plan["case_sha256"])
                if plan.get("daily_selection_binding"):
                    from ...application.hotspot.daily_selection import verify_daily_selection
                    binding = plan["daily_selection_binding"]
                    target = (project / binding["path"]).resolve()
                    if not target.is_relative_to(project / "runtime") or hashlib.sha256(target.read_bytes()).hexdigest() != binding["sha256"]:
                        raise ValueError("Daily selection changed")
                    selection = json.loads(target.read_bytes())
                    verify_daily_selection(project, selection)
                    selected = next(r for r in selection["observation_list"] if r["symbol"] == row["symbol"])
                    if selected != plan["daily_selection"]:
                        raise ValueError("Frozen selection differs from original")
                checked.append(row)
            except (ValueError, OSError, KeyError, TypeError, StopIteration, ArithmeticError) as error:
                stale = "B1 current close rejected" in str(error)
                checked.append({**row, "price_action_plan": {**plan,
                    "signal_state": "STALE" if stale else "BLOCKED",
                    "action_eligibility": False, "formal_eligibility": False,
                    "portfolio_eligibility": None, "action_intent": "WATCH", "entry_trigger_price": None,
                    "invalidation_price": None, "current_reference_price": None,
                    "entry_condition": None, "exit_condition": None, "invalidation_condition": None,
                    "price_behavior": None, "risk_reward_ratio": None,
                    "levels": {}, "current_reference_close": None,
                    "blockers": [*plan["blockers"], "CURRENT_CASE_CHANGED_OR_STALE"],
                    "explanation": "本次读取无法验证价格条件的新鲜度或原始证据；旧价位不作为当前条件。"}})
        return checked

    def value_plan(symbol, packet):
        frozen = (packet or {}).get("value_price_conditions", {}).get(symbol)
        return revalidate_current_value_plan(project, frozen, now=datetime.now(timezone.utc)) if frozen else None

    def pinned_publication(packet, current):
        if packet is None:
            return _publication_block(project, current)
        return {"action": "no_order", "packet_status": "CURRENT", "snapshot_status": "VERIFIED",
                "publication_id": packet["publication_id"],
                "research_version": packet.get("research_version"),
                "generated_at": packet.get("generated_at"),
                "engine_version": packet.get("engine_version")}

    def chain_matches_packet(packet, current):
        bindings = (packet or {}).get("identity_inputs", {}).get("chain")
        if bindings is None:
            return True
        observed = [{"role": row["role"], "path": row["path"], "sha256": row["sha256"]}
                    for row in sorted(current["bindings"], key=lambda row: str(row["role"]))]
        return bindings == observed

    def current_item(row):
        plan = row["price_action_plan"]
        return {"id": plan["decision_id"], "symbol": row["symbol"],
                "name": row["company_name"], "company_name": row["company_name"],
                "strategy": "hotspot", "status": plan["signal_state"],
                "action": "no_order", "as_of": plan["market_trade_date"],
                "reason": plan["explanation"], "blockers": plan["blockers"],
                "why_selected": plan.get("watch_reason"),
                "price_action_plan": plan}

    @api.get("/api/v1/current-price-case/{symbol}")
    def current_price_case(symbol: str):
        packet, _ = _load_snapshot(project)
        current = _public(project)
        if current is None or not chain_matches_packet(packet, current):
            return {"action": "no_order", "status": "UNAVAILABLE", "reason": "PUBLICATION_VERSION_MISMATCH"}
        row = next((row for row in current_items(packet) if row["symbol"] == symbol), None)
        if row is None:
            return {"action": "no_order", "status": "UNAVAILABLE", "reason": "CURRENT_CASE_NOT_PUBLISHED"}
        plan = row["price_action_plan"]
        if plan["signal_state"] in ("BLOCKED", "STALE"):
            return {"action": "no_order", "status": "UNAVAILABLE", "reason": "CURRENT_CASE_CHANGED_OR_STALE"}
        try:
            case = load_current_price_case(root=project, symbol=symbol,
                case_path=Path(plan["case_path"]), expected_sha256=plan["case_sha256"])
            return {**case, "price_action_plan": plan}
        except (ValueError, OSError, KeyError, TypeError):
            return {"action": "no_order", "status": "UNAVAILABLE", "reason": "CURRENT_CASE_CHANGED_OR_STALE"}

    @api.get("/api/v1/historical-price-case/{symbol}/{trade_date}")
    def historical_price_case(symbol: str, trade_date: str):
        if not _ID.fullmatch(symbol):
            return {"action": "no_order", "status": "UNAVAILABLE",
                    "reason": "INVALID_SYMBOL"}
        try:
            requested_date = date.fromisoformat(trade_date)
            case = load_historical_case(root=project, symbol=symbol,
                                        as_of=requested_date)
            return {**case, "price_action_plan": project_price_action_plan(case)}
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
            return {"action": "no_order", "status": "UNAVAILABLE",
                    "reason": "HISTORICAL_SOURCE_OR_CALCULATION_UNAVAILABLE"}

    @api.get("/api/v1/historical-price-cases")
    def historical_price_cases():
        base = project / "runtime" / "hotspot-price-cases"
        items = []
        if base.is_dir():
            for folder in sorted(base.iterdir(), reverse=True):
                if len(items) >= 10:
                    break
                match = re.fullmatch(r"([0-9]{6})-([0-9]{4}-[0-9]{2}-[0-9]{2})", folder.name)
                if not match or not folder.is_dir():
                    continue
                try:
                    case = load_historical_case(root=project, symbol=match[1],
                                                as_of=date.fromisoformat(match[2]))
                except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
                    continue
                items.append({"symbol": case["symbol"], "market_trade_date": case["market_trade_date"],
                              "reference_price": case["current_reference_price"],
                              "levels": case["levels"], "signal_state": case["signal_state"],
                              "blockers": case["blockers"]})
        return {"action": "no_order", "status": "HISTORICAL_NOT_CURRENT", "items": items}

    @api.get("/api/v1/daily-decisions")
    def daily_decisions():
        packet, _ = _load_snapshot(project)
        empty = {"action": "no_order", "status": "UNAVAILABLE", "as_of": None,
                 "market": {"status": "UNKNOWN", "reason": "PUBLICATION_UNAVAILABLE"},
                 "summary": {"universe_count": None, "formal_count": 0, "watch_count": None},
                 "sections": {"holdings": [], "value": [], "hotspot": []},
                 "research": dict(_UNAVAILABLE_RESEARCH),
                 "dual_sleeve": dual_sleeve_unavailable(),
                 "publication": publication_block_unavailable(),
                 "blockers": ["PUBLICATION_UNAVAILABLE"],
                 "gate_code": "PUBLICATION_UNAVAILABLE", "reason": "PUBLICATION_UNAVAILABLE"}
        current = _public(project)
        if current is None or not chain_matches_packet(packet, current):
            return empty
        state, model = current["state"], current["model"]
        extensions = state["content"].get("extensions", {})
        snapshot = model.get("snapshot", {})
        if not isinstance(extensions, dict) or not isinstance(snapshot, dict) or snapshot.get("action") != "no_order":
            return empty
        discovery = extensions.get("value_discovery_report", {})
        quality = extensions.get("m2_quality_diagnostic", {})
        market = extensions.get("market_regime_observation", {})
        hotspot = extensions.get("hotspot_watch_queue", {})
        queue = extensions.get("value_research_queue", {})
        if (discovery.get("status") != "RESEARCH_LEADS_ONLY" or
                quality.get("schema_version") != "m2-quality-diagnostic-v1" or
                market.get("schema_version") != "market-regime-observation-v1" or
                hotspot.get("schema_version") != "hotspot-watch-queue-v1" or
                queue.get("schema_version") != "value-research-queue-v1" or
                queue.get("admission") != "RESEARCH_QUEUE_ONLY"):
            return empty
        # The dual-sleeve section restates only a formally bound review. An
        # older publication without the binding gets the shared not-connected
        # result instead of an invented portfolio, and a malformed report
        # fails closed alone so the research page keeps answering.
        dual_report = extensions.get("dual_sleeve_report")
        try:
            if dual_report is None:
                dual_report = run_dual_sleeve_review(
                    root=project, generated_at=datetime.now(timezone.utc))
                dual_sleeve = build_dual_sleeve_surface(dual_report)
            else:
                dual_sleeve = build_dual_sleeve_surface(
                    dual_report, source=_binding_path(model, "dual_sleeve_report"))
        except _STRUCTURE_ERRORS:
            dual_sleeve = dual_sleeve_unavailable(BLOCKER_SURFACE_INVALID)
        leads = discovery.get("lead_symbols", [])
        if not isinstance(leads, list):
            return empty
        report_source = _binding_path(model, "value_discovery_report")
        try:
            report = _bound(project, model["product_extensions"]["value_discovery_report"])
        except _STRUCTURE_ERRORS:
            return _unavailable("VALUE_DISCOVERY_REPORT_BINDING_UNAVAILABLE",
                                "VALUE_DISCOVERY_REPORT_UNAVAILABLE", source=report_source)
        try:
            receipt = _bound(project, report["receipt_binding"])
        except _STRUCTURE_ERRORS:
            binding = report.get("receipt_binding")
            source = binding.get("path") if isinstance(binding, dict) else None
            return _unavailable("VALUE_DISCOVERY_RECEIPT_BINDING_UNAVAILABLE",
                                "VALUE_DISCOVERY_RECEIPT_UNAVAILABLE",
                                source=source if isinstance(source, str) else report_source)
        universe = receipt.get("universe")
        records = universe.get("records") if isinstance(universe, dict) else None
        if (receipt.get("schema_version") != "m2-opportunity-discovery-v2"
                or not isinstance(records, list)):
            return _unavailable("VALUE_DISCOVERY_UNIVERSE_UNAVAILABLE",
                                "VALUE_DISCOVERY_UNIVERSE_UNREADABLE", source=report_source)
        # Counts are published beside the rows they describe; a mismatch means the
        # chain is only half-wired and no number here would be fully true.
        health = report.get("data_health")
        if isinstance(health, dict) and health.get("universe_count") != len(records):
            return _unavailable("VALUE_DISCOVERY_UNIVERSE_INCONSISTENT",
                                "VALUE_DISCOVERY_UNIVERSE_COUNT_MISMATCH", source=report_source)
        if ("deduplicated_lead_count" in report
                and report["deduplicated_lead_count"] != len(leads)):
            return _unavailable("VALUE_DISCOVERY_LEAD_COUNT_INCONSISTENT",
                                "VALUE_DISCOVERY_LEAD_COUNT_MISMATCH", source=report_source)
        symbols = {row["symbol"] for row in records
                   if isinstance(row, dict) and isinstance(row.get("symbol"), str)}
        if symbols and any(lead not in symbols for lead in leads if isinstance(lead, str)):
            return _unavailable("VALUE_DISCOVERY_LEAD_NOT_IN_UNIVERSE",
                                "VALUE_DISCOVERY_LEAD_UNIVERSE_MISMATCH", source=report_source)
        companies = snapshot.get("companies", [])
        as_of = queue.get("as_of") or snapshot.get("as_of")
        pending_symbols = {c.get("symbol") for c in snapshot.get("opportunities", [])
                           if isinstance(c, dict) and c.get("valuation_status", {}).get("code") == "NOT_READY"}
        value = [_item(c, as_of, "PENDING_RESEARCH" if c.get("symbol") in pending_symbols else "RESEARCH_ONLY")
                 for c in companies if isinstance(c, dict)
                 and c.get("action") == "no_order" and _ID.fullmatch(str(c.get("symbol", "")))]
        known = {c.get("symbol") for c in value}
        value.extend(_item(c, as_of, "PENDING_RESEARCH") for c in snapshot.get("opportunities", [])
                     if isinstance(c, dict) and c.get("action") == "no_order"
                     and _ID.fullmatch(str(c.get("symbol", ""))) and c["symbol"] not in known)
        value = _attach_value_explanations(project, model, value)
        for item in value:
            plan = value_plan(item["symbol"], packet)
            if plan is not None:
                item["price_action_plan"] = plan
        known = {c["symbol"] for c in value}
        value.extend(_queue_item(c, as_of) for c in queue.get("entries", [])
                     if isinstance(c, dict) and c.get("queue_status") == "SELECTED_FOR_DATA_CHECK"
                     and _ID.fullmatch(str(c.get("symbol", ""))) and c["symbol"] not in known)
        named = [*(companies if isinstance(companies, list) else []),
                 *snapshot.get("opportunities", []),
                 *queue.get("entries", [])]
        names = {row["symbol"]: str(row.get("company_name")) for row in named
                 if isinstance(row, dict) and isinstance(row.get("symbol"), str)
                 and isinstance(row.get("company_name"), str)}
        # Formal admissions are counted from the published rows themselves; no row
        # carries an admitted valuation status yet, so the count stays derived, not fixed.
        formal_count = count_formal_admissions(named)
        return {"action": "no_order", "status": "RESEARCH_OBSERVATION",
                "as_of": as_of,
                "market": _pick(market, "status", "reason"),
                "summary": {"universe_count": len(records),
                            "formal_count": formal_count,
                            "watch_count": len(leads)},
                "research": _daily_research(project, names),
                "dual_sleeve": dual_sleeve,
                "publication": pinned_publication(packet, current),
                "sections": {"holdings": [], "value": value,
                             "hotspot": [current_item(row) for row in current_items(packet)] or [dict(_item(c, as_of, "UNKNOWN"), strategy="hotspot")
                                         for c in hotspot.get("items", []) if isinstance(c, dict)
                                         and c.get("action") == "no_order"
                                         and _ID.fullmatch(str(c.get("symbol", "")))]},
                # The public packet never claims anything about the private ledger;
                # private connection state is owned by the authorized private routes.
                "blockers": ["NO_FORMAL_ADMISSION"]}

    @api.get("/api/v1/decisions/{decision_id}")
    def decision(decision_id: str):
        packet, _ = _load_snapshot(project)
        current = _public(project)
        if current is None or not chain_matches_packet(packet, current):
            return {"action": "no_order", "status": "UNAVAILABLE", "decision": None,
                    "publication": publication_block_unavailable(),
                    "reason": "PUBLICATION_VERSION_MISMATCH"}
        if decision_id.startswith("hotspot-"):
            row = next((row for row in current_items(packet)
                        if row["price_action_plan"]["decision_id"] == decision_id), None)
            return {"action": "no_order", "status": "CURRENT_OBSERVATION" if row else "NOT_FOUND",
                    "publication": pinned_publication(packet, current),
                    "decision": current_item(row) if row else None}
        if not _ID.fullmatch(decision_id):
            return {"action": "no_order", "status": "NOT_FOUND", "decision": None, "reason": "UNKNOWN_DECISION"}
        current = _public(project)
        if current is None or not chain_matches_packet(packet, current):
            return {"action": "no_order", "status": "UNAVAILABLE", "decision": None,
                    "publication": _publication_block(project, current),
                    "reason": "PUBLICATION_UNAVAILABLE"}
        model = current["model"]
        published = model.get("snapshot") if isinstance(model.get("snapshot"), dict) else {}

        def with_research_draft(payload: dict) -> dict:
            draft = load_current_research_draft(project, decision_id)
            if draft is not None:
                payload["research_draft"] = draft
            return payload

        for company in published.get("companies", []):
            if isinstance(company, dict) and company.get("symbol") == decision_id and company.get("action") == "no_order":
                pending = any(isinstance(c, dict) and c.get("symbol") == decision_id
                              and c.get("valuation_status", {}).get("code") == "NOT_READY"
                              for c in published.get("opportunities", []))
                status = "PENDING_RESEARCH" if pending else "RESEARCH_ONLY"
                item = _item(company, published.get("as_of"), status)
                binding = next((b for b in model.get("additional_evidence_bindings", [])
                                if isinstance(b, dict) and isinstance(b.get("path"), str)
                                and b["path"].endswith(f"/{decision_id}-value-decision-explanation.json")), None)
                explanation = None
                binding_status = "NOT_BOUND"
                if binding:
                    try:
                        candidate = _bound(project, binding)
                    except _STRUCTURE_ERRORS:
                        binding_status = "UNAVAILABLE"
                    else:
                        if (candidate.get("schema_version") == "public-value-decision-explanation-v1"
                                and candidate.get("symbol") == decision_id
                                and candidate.get("action") == "no_order"):
                            explanation, binding_status = candidate, "VERIFIED"
                        else:
                            binding_status = "UNAVAILABLE"
                if explanation is not None:
                    item.update(_pick(explanation, "candidate_explanation", "support",
                                      "counter_evidence", "thesis_breakers", "blockers",
                                      "price_context", "next_events"))
                    item["reason"] = explanation.get("candidate_explanation") or item["reason"]
                elif binding_status == "UNAVAILABLE":
                    # Keep the verified company card readable, but never present it
                    # as if the bound decision explanation had been read.
                    item["blockers"] = [*(item.get("blockers") or []),
                                        "VALUE_EXPLANATION_BINDING_UNAVAILABLE"]
                item["research"] = project_value_decision_detail(
                    symbol=decision_id, company=company, explanation=explanation,
                    binding_status=binding_status, binding=binding,
                    price_bridge_execution=_quote_bridge_execution(project, decision_id),
                    binding_blockers=(["VALUE_EXPLANATION_BINDING_UNAVAILABLE"]
                                      if binding_status == "UNAVAILABLE" else []))
                plan = value_plan(decision_id, packet)
                if plan is not None:
                    item["price_action_plan"] = plan
                return with_research_draft({"action": "no_order", "status": status,
                                            "publication": pinned_publication(packet, current),
                                            "decision": item})
        for opportunity in published.get("opportunities", []):
            if isinstance(opportunity, dict) and opportunity.get("symbol") == decision_id and opportunity.get("action") == "no_order":
                return with_research_draft({
                    "action": "no_order", "status": "PENDING_RESEARCH",
                    "publication": _publication_block(project, current),
                    "decision": _item(opportunity, published.get("as_of"), "PENDING_RESEARCH")})
        queue_binding = model.get("product_extensions", {}).get("value_research_queue")
        if queue_binding:
            try:
                queue = _bound(project, queue_binding)
            except (OSError, ValueError, KeyError, TypeError):
                return {"action": "no_order", "status": "UNAVAILABLE", "decision": None,
                        "reason": "PUBLICATION_UNAVAILABLE"}
            for entry in queue.get("entries", []):
                if (isinstance(entry, dict) and entry.get("symbol") == decision_id
                        and entry.get("queue_status") == "SELECTED_FOR_DATA_CHECK"):
                    return with_research_draft({
                        "action": "no_order", "status": "RESEARCH_ONLY",
                        "publication": _publication_block(project, current),
                        "decision": _queue_item(entry, queue.get("as_of"))})
        return {"action": "no_order", "status": "NOT_FOUND", "decision": None,
                "publication": _publication_block(project, current),
                "reason": "UNKNOWN_DECISION"}

    def bound_decisions() -> dict[str, dict]:
        """Every research decision the current publication really binds."""
        current = _public(project)
        decisions: dict[str, dict] = {}
        if current is None:
            return decisions
        model = current["model"]
        for binding in model.get("additional_evidence_bindings", []):
            if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
                continue
            if not binding["path"].endswith("-value-decision-explanation.json"):
                continue
            try:
                explanation = _bound(project, binding)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if (explanation.get("schema_version") == "public-value-decision-explanation-v1"
                    and explanation.get("action") == "no_order"
                    and isinstance(explanation.get("symbol"), str)
                    and isinstance(explanation.get("research_version"), str)):
                decisions[explanation["symbol"]] = {
                    "research_version": explanation["research_version"],
                    "candidate_action": explanation.get("candidate_action"),
                    "decision_cutoff": explanation.get("decision_as_of"),
                    "artifact": binding["path"], "sha256": binding["sha256"]}
        return decisions

    @api.get("/api/v1/daily-update-status")
    def daily_update_status():
        from ...application.product.daily_refresh import read_latest_run
        result = read_latest_run(project)
        return {"action": "no_order", "status": "RECORDED" if result else "NOT_RECORDED", "last_run": result}

    @api.get("/api/v1/hotspot-replay-review")
    def hotspot_replay_review():
        from ...application.hotspot.replay_read_model import load_replay_summary
        try:
            pins = json.loads((project / "config/hotspot-replay-review-v1.json").read_bytes())
            if pins.get("action") != "no_order":
                raise ValueError("Invalid review pins")
            return load_replay_summary(root=project, manifest_sha256=pins["manifest_sha256"],
                                      structure_manifest_sha256=pins["structure_manifest_sha256"])
        except (ValueError, OSError, KeyError, TypeError):
            return JSONResponse(status_code=409, content={
                "action": "no_order", "status": "REPLAY_UNAVAILABLE"})

    @api.get("/api/v1/value-policy-review/{symbol}")
    def value_policy_review(symbol: str):
        from ...application.decision.value_price_policy import load_value_policy_review
        try:
            review = load_value_policy_review(project, symbol, datetime.now(timezone.utc))
            return {"action": "no_order", "status": "RESEARCH_ONLY", **review}
        except (ValueError, OSError):
            return JSONResponse(status_code=409, content={
                "action": "no_order", "status": "REVIEW_UNAVAILABLE",
                "detail": "Review sources or current research basis are unavailable or changed."})

    @api.get("/api/v1/decision-history")
    def decision_history():
        decisions = bound_decisions()
        history = build_research_history(
            project,
            published_versions={symbol: row["research_version"]
                                for symbol, row in decisions.items()},
            published_decisions=decisions)
        current = _public(project)
        history["publication"] = _publication_block(project, current)
        return history

    @api.get("/api/v1/daily-public-packet")
    def daily_public_packet():
        """The one frozen public daily decision packet (TL10-RC).

        Every surface serves the same verified snapshot: the bytes the daily
        entry wrote, re-checked against the recorded SHA-256. Only when no
        snapshot has ever been published (a fresh checkout or a test fixture)
        does this fall back to a live composition, and then the response says
        so instead of presenting itself as a frozen version.
        """
        packet, error = _load_snapshot(project)
        if packet is not None:
            return packet
        try:
            live = build_daily_public_packet(project)
        except _STRUCTURE_ERRORS:
            return unavailable_packet(chain_error="PACKET_BUILD_FAILED")
        if live.get("packet_status") == "CURRENT":
            live = dict(live)
            live["snapshot_status"] = "NO_VERIFIED_SNAPSHOT"
            live["snapshot_reason"] = error
            live["blockers"] = list(dict.fromkeys(
                ["PUBLIC_SNAPSHOT_UNAVAILABLE", *(live.get("blockers") or [])]))
        return live

    @api.get("/api/v1/daily-public-snapshot")
    def daily_public_snapshot():
        """Version metadata for the frozen snapshot plus the read-only Excel check."""
        metadata = _snapshot_metadata(project)
        metadata["excel_live"] = _workbook_report(project)
        return metadata

    @api.get("/api/v1/runtime-identity")
    def runtime_version():
        identity = runtime_identity(project, backend_head=backend_head,
                                    backend_module=backend_module,
                                    backend_module_sha=backend_module_sha)
        snapshot = _snapshot_metadata(project)
        identity["publication"] = {
            "status": snapshot["status"],
            "publication_id": snapshot["publication_id"],
            "packet_sha256": snapshot["packet_sha256"],
            "published_at": snapshot["published_at"],
            "dates": snapshot["dates"],
        }
        identity["data_freshness"] = data_freshness(snapshot.get("dates"))
        return identity

    @api.get("/api/v1/research-funnel-status")
    def research_funnel_audit_status():
        """Serve only the hash-verified, read-only W6 audit projection."""
        return research_funnel_status(project)

    @api.get("/api/v1/system/status")
    def system_status(request: Request):
        try:
            authorize(request, session=sessions, port=bound_port)
            portfolio = portfolio_connection(project)
        except LocalAuthorizationError:
            # Whether a private ledger exists is itself private information.
            portfolio = "LOCKED"
        current = _public(project)
        if current is None:
            return {"action": "no_order", "status": "UNAVAILABLE", "publication": "UNAVAILABLE",
                    "portfolio": portfolio}
        return {"action": "no_order", "status": "READ_ONLY",
                "publication": current["pointer"]["current_publication"]["status"],
                "portfolio": portfolio}

    @api.exception_handler(RequestValidationError)
    def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={
            "action": "no_order", "status": "VALIDATION_FAILED",
            "detail": [{"field": ".".join(str(part) for part in item.get("loc", ())),
                        "message": item.get("msg", "invalid")} for item in error.errors()]})

    register_private_routes(
        api, project, sessions=sessions, port=bound_port)
    register_value_policy_routes(api, sessions=sessions, port=bound_port,
        principal_resolver=lambda request: PolicyPrincipal("local-account-owner", frozenset({PERMISSION})),
        get_service=lambda: value_policy_service or ValuePolicyInteractionService(
            project, storage_relative="runtime/value-policy-review/local-account-owner"))

    dist = project / "web" / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        bundle = dist.resolve()

        @api.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return {"detail": "Not Found"}
            # The bundler emits flat bundles beside index.html, so every real file
            # is served as-is and only client-side routes fall back to the shell.
            if path and not path.endswith("/"):
                candidate = (bundle / path).resolve()
                if candidate.is_relative_to(bundle) and candidate.is_file():
                    return FileResponse(candidate, headers={"Cache-Control": "no-store"})
            return FileResponse(bundle / "index.html", headers={"Cache-Control": "no-store"})

    return api


app = create_app()

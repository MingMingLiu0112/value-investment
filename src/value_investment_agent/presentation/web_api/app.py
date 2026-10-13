"""Hash-bound, read-only projections of the current published product."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from ..read_models.research_history import build_research_history
from .local_auth import SESSION_TTL_SECONDS, LocalOperatorSession
from .private_routes import portfolio_connection, register_private_routes


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PORT = 8001
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[0-9]{6}\Z")
_POINTER_SCHEMA = "m7-current-trial-workbook-v5"
_MODEL_SCHEMA = "historical-company-read-model-preview-v1"


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid object")
    return value


def _bound(root: Path, binding: dict) -> dict:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("invalid binding")
    name, digest = binding["path"], binding["sha256"]
    if not isinstance(name, str) or not isinstance(digest, str) or not _HASH.fullmatch(digest):
        raise ValueError("invalid binding fields")
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "runtime":
        raise ValueError("invalid runtime binding")
    runtime = (root / "runtime").resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(runtime) or not path.is_file():
        raise ValueError("binding outside runtime")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("binding hash mismatch")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid bound object")
    return value


def _current(root: Path) -> tuple[dict, dict, dict]:
    pointer = _object(root / "config/current-trial-workbook.json")
    if pointer.get("schema_version") != _POINTER_SCHEMA or pointer.get("action") != "no_order":
        raise ValueError("unknown pointer")
    publication = pointer["current_publication"]
    if publication.get("status") != "PUBLISHED_WPS_READONLY_VERIFIED":
        raise ValueError("publication not verified")
    receipt = _bound(root, {"path": publication["receipt"], "sha256": publication["receipt_sha256"]})
    if (receipt.get("schema_version") != "canonical-reviewed-research-publication-v1"
            or receipt.get("canonical_written") is not True):
        raise ValueError("publication receipt invalid")
    sources = _bound(root, {"path": receipt["source_bindings_path"],
                            "sha256": receipt["source_bindings_sha256"]})
    if sources.get("schema_version") != "existing-workbench-preview-bindings-v1":
        raise ValueError("unknown source ledger")
    handoff = _bound(root, sources["publication_input_binding"])
    if handoff.get("schema_version") != "research-publication-input-v1" or handoff.get("action") != "no_order":
        raise ValueError("unknown publication input")
    model = _bound(root, handoff["read_model_binding"])
    if model.get("schema_version") != _MODEL_SCHEMA or model.get("action") != "no_order":
        raise ValueError("unknown read model")
    state = _bound(root, pointer["daily_product_state_binding"])
    if state.get("action") != "no_order" or not isinstance(state.get("content"), dict):
        raise ValueError("unknown daily state")
    if model.get("snapshot") != handoff.get("snapshot"):
        raise ValueError("publication snapshot mismatch")
    for role, binding in model.get("product_extensions", {}).items():
        if role in state["content"].get("extensions", {}):
            extension = _bound(root, binding)
            if state["content"]["extensions"][role] != extension.get("semantic_content", extension):
                raise ValueError("daily state and published model disagree")
    return pointer, state, model


def _public(root: Path) -> tuple[dict, dict, dict] | None:
    try:
        return _current(root)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        return None


def _pick(value: dict, *keys: str) -> dict:
    return {key: value[key] for key in keys if key in value}


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
) -> FastAPI:
    # Root injection is for in-process tests; no HTTP parameter or environment override exists.
    project = (root or ROOT).resolve()
    bound_port = port if port is not None else _default_port()
    api = FastAPI(title="Value Investment Read API")

    @api.get("/api/v1/daily-decisions")
    def daily_decisions():
        empty = {"action": "no_order", "status": "UNAVAILABLE", "as_of": None,
                 "market": {"status": "UNKNOWN", "reason": "PUBLICATION_UNAVAILABLE"},
                 "summary": {"universe_count": 0, "formal_count": 0, "watch_count": 0},
                 "sections": {"holdings": [], "value": [], "hotspot": []},
                 "blockers": ["PUBLICATION_UNAVAILABLE"]}
        current = _public(project)
        if current is None:
            return empty
        pointer, state, model = current
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
        leads = discovery.get("lead_symbols", [])
        if not isinstance(leads, list):
            return empty
        report = _bound(project, model["product_extensions"]["value_discovery_report"])
        receipt = _bound(project, report["receipt_binding"])
        if receipt.get("schema_version") != "m2-opportunity-discovery-v2":
            return empty
        records = receipt.get("universe", {}).get("records")
        if not isinstance(records, list):
            return empty
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
        known = {c["symbol"] for c in value}
        value.extend(_queue_item(c, as_of) for c in queue.get("entries", [])
                     if isinstance(c, dict) and c.get("queue_status") == "SELECTED_FOR_DATA_CHECK"
                     and _ID.fullmatch(str(c.get("symbol", ""))) and c["symbol"] not in known)
        return {"action": "no_order", "status": "RESEARCH_OBSERVATION",
                "as_of": as_of,
                "market": _pick(market, "status", "reason"),
                "summary": {"universe_count": len(records),
                            "formal_count": 0,
                            "watch_count": len(leads)},
                "sections": {"holdings": [], "value": value,
                             "hotspot": [dict(_item(c, as_of, "UNKNOWN"), strategy="hotspot")
                                         for c in hotspot.get("items", []) if isinstance(c, dict)
                                         and c.get("action") == "no_order"
                                         and _ID.fullmatch(str(c.get("symbol", "")))]},
                "blockers": ["NO_FORMAL_ADMISSION", "PRIVATE_PORTFOLIO_NOT_CONNECTED"]}

    @api.get("/api/v1/decisions/{decision_id}")
    def decision(decision_id: str):
        if not _ID.fullmatch(decision_id):
            return {"action": "no_order", "status": "NOT_FOUND", "decision": None, "reason": "UNKNOWN_DECISION"}
        current = _public(project)
        if current is None:
            return {"action": "no_order", "status": "UNAVAILABLE", "decision": None,
                    "reason": "PUBLICATION_UNAVAILABLE"}
        model = current[2]
        for company in model.get("snapshot", {}).get("companies", []):
            if isinstance(company, dict) and company.get("symbol") == decision_id and company.get("action") == "no_order":
                pending = any(isinstance(c, dict) and c.get("symbol") == decision_id
                              and c.get("valuation_status", {}).get("code") == "NOT_READY"
                              for c in model["snapshot"].get("opportunities", []))
                status = "PENDING_RESEARCH" if pending else "RESEARCH_ONLY"
                item = _item(company, model["snapshot"].get("as_of"), status)
                binding = next((b for b in model.get("additional_evidence_bindings", [])
                                if isinstance(b, dict) and isinstance(b.get("path"), str)
                                and b["path"].endswith(f"/{decision_id}-value-decision-explanation.json")), None)
                if binding:
                    try:
                        explanation = _bound(project, binding)
                        if (explanation.get("schema_version") == "public-value-decision-explanation-v1"
                                and explanation.get("symbol") == decision_id and explanation.get("action") == "no_order"):
                            item.update(_pick(explanation, "candidate_explanation", "support",
                                              "counter_evidence", "thesis_breakers", "blockers",
                                              "price_context", "next_events"))
                            item["reason"] = explanation.get("candidate_explanation") or item["reason"]
                    except (OSError, ValueError, KeyError, TypeError):
                        return {"action": "no_order", "status": "UNAVAILABLE", "decision": None,
                                "reason": "PUBLICATION_UNAVAILABLE"}
                return {"action": "no_order", "status": status,
                        "decision": item}
        for opportunity in model.get("snapshot", {}).get("opportunities", []):
            if isinstance(opportunity, dict) and opportunity.get("symbol") == decision_id and opportunity.get("action") == "no_order":
                return {"action": "no_order", "status": "PENDING_RESEARCH",
                        "decision": _item(opportunity, model["snapshot"].get("as_of"), "PENDING_RESEARCH")}
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
                    return {"action": "no_order", "status": "RESEARCH_ONLY",
                            "decision": _queue_item(entry, queue.get("as_of"))}
        return {"action": "no_order", "status": "NOT_FOUND", "decision": None, "reason": "UNKNOWN_DECISION"}

    def published_research_versions() -> dict[str, str]:
        """Every research version string the current publication really binds."""
        current = _public(project)
        versions: dict[str, str] = {}
        if current is None:
            return versions
        model = current[2]
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
                versions[explanation["symbol"]] = explanation["research_version"]
        return versions

    @api.get("/api/v1/decision-history")
    def decision_history():
        return build_research_history(project, published_versions=published_research_versions())

    @api.get("/api/v1/system/status")
    def system_status():
        current = _public(project)
        if current is None:
            return {"action": "no_order", "status": "UNAVAILABLE", "publication": "UNAVAILABLE",
                    "portfolio": portfolio_connection(project)}
        return {"action": "no_order", "status": "READ_ONLY",
                "publication": current[0]["current_publication"]["status"],
                "portfolio": portfolio_connection(project)}

    @api.exception_handler(RequestValidationError)
    def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={
            "action": "no_order", "status": "VALIDATION_FAILED",
            "detail": [{"field": ".".join(str(part) for part in item.get("loc", ())),
                        "message": item.get("msg", "invalid")} for item in error.errors()]})

    register_private_routes(
        api, project,
        sessions=LocalOperatorSession(ttl_seconds=session_ttl_seconds),
        port=bound_port)

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
                    return FileResponse(candidate)
            return FileResponse(bundle / "index.html")

    return api


app = create_app()

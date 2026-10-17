"""Load a hash-bound, read-only research draft for the product surface.

Research drafts are deliberately separate from the formal publication chain.
They may explain conditional work in progress, but cannot carry price
admission, eligibility, position sizing or execution fields.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from .common import normalize_symbol, sha256_file


POINTER_PATH = Path("config/current-research-drafts.json")
ARTIFACT_ROOT = Path("artifacts/current")
POINTER_SCHEMA = "current-research-drafts-v1"
DRAFT_SCHEMA = "public-research-draft-v1"
DRAFT_STATUS = "RESEARCH_DRAFT_NOT_APPROVED"
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_KEYS = {
    "action_eligibility",
    "buy_quantity",
    "cash_impact",
    "formal_eligibility",
    "holdings",
    "order",
    "order_intent",
    "portfolio_eligibility",
    "position_guidance",
    "position_size",
    "quantity",
    "sell_quantity",
    "target_weight",
    "trade_eligible",
}


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _aware_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("available_at is required")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("available_at must include a timezone")
    return parsed


def _reject_execution_fields(value: object) -> None:
    if isinstance(value, dict):
        overlap = _FORBIDDEN_KEYS.intersection(value)
        if overlap:
            raise ValueError(
                "research draft contains forbidden execution fields: "
                + ", ".join(sorted(overlap))
            )
        for child in value.values():
            _reject_execution_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_execution_fields(child)


def _validate_draft(payload: dict[str, Any], symbol: str, now: datetime) -> None:
    if payload.get("schema_version") != DRAFT_SCHEMA:
        raise ValueError("unknown research draft schema")
    if payload.get("action") != "no_order":
        raise ValueError("research draft must remain no_order")
    if payload.get("symbol") != symbol:
        raise ValueError("research draft symbol mismatch")
    if payload.get("status") != DRAFT_STATUS:
        raise ValueError("research draft is not in the unapproved state")
    _reject_execution_fields(payload)

    if _aware_timestamp(payload.get("available_at")) > now:
        raise ValueError("research draft is not yet available")
    research_as_of = payload.get("research_as_of")
    if not isinstance(research_as_of, str):
        raise ValueError("research_as_of is required")
    if date.fromisoformat(research_as_of[:10]) > now.date():
        raise ValueError("research_as_of is in the future")

    valuation = payload.get("valuation")
    if not isinstance(valuation, dict) or valuation.get("status") != "conditional_research_only":
        raise ValueError("research draft valuation is not conditional")
    scenarios = valuation.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("research draft scenarios are required")
    scenario_names = {
        row.get("scenario")
        for row in scenarios
        if isinstance(row, dict) and isinstance(row.get("per_share_value"), str)
    }
    if scenario_names != {"bear", "base", "bull"}:
        raise ValueError("research draft must expose bear, base and bull values")

    bridge = payload.get("price_bridge")
    if not isinstance(bridge, dict) or bridge.get("price_admitted") is not False:
        raise ValueError("research draft cannot admit price")
    quote = payload.get("quote_fact")
    if not isinstance(quote, dict) or quote.get("status") != "VERIFIED_CLOSE_NOT_ADMITTED":
        raise ValueError("research draft quote must remain unadmitted")
    gates = payload.get("gates")
    results = gates.get("results") if isinstance(gates, dict) else None
    if not isinstance(results, dict) or results.get("G3_估值门") is not False:
        raise ValueError("research draft cannot bypass G3")


def load_current_research_draft(
    root: Path,
    symbol: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return a verified draft, or ``None`` when it is absent or invalid."""

    try:
        normalized = normalize_symbol(symbol)
        pointer = _json_object(root / POINTER_PATH)
        if pointer.get("schema_version") != POINTER_SCHEMA or pointer.get("action") != "no_order":
            raise ValueError("unknown research draft pointer")
        drafts = pointer.get("drafts")
        entry = drafts.get(normalized) if isinstance(drafts, dict) else None
        if entry is None:
            return None
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ValueError("invalid research draft binding")
        relative_value = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(relative_value, str) or not isinstance(digest, str):
            raise ValueError("invalid research draft binding fields")
        if not _HASH_RE.fullmatch(digest):
            raise ValueError("invalid research draft digest")

        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("invalid research draft path")
        approved_root = (root / ARTIFACT_ROOT).resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(approved_root) or not target.is_file():
            raise ValueError("research draft outside approved artifacts")
        if sha256_file(target) != digest:
            raise ValueError("research draft hash mismatch")

        payload = _json_object(target)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must include a timezone")
        _validate_draft(payload, normalized, current)
        return payload
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError):
        return None

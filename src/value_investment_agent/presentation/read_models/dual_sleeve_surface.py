"""Project the published dual-sleeve review onto the daily product surface.

The daily page answers with one section what the dual-sleeve chain currently
knows: the formally bound `dual-sleeve-risk-review-v1` report, or the shared
not-connected result when an older publication carries no binding. The surface
restates `position_guidance`, `trade_eligible` and `acceptance_authority`
verbatim; it never computes a position, never reads private storage and never
turns a research state into an order.
"""
from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "daily-dual-sleeve-surface-v1"
REPORT_SCHEMA = "dual-sleeve-risk-review-v1"
ACTION = "no_order"
STATUS_UNAVAILABLE = "UNAVAILABLE"
REVIEWED_STATUSES = ("RISK_REVIEW_CALCULATED", "REVIEW_REQUIRED")
BLOCKER_STATUS_UNAVAILABLE = "DUAL_SLEEVE_STATUS_UNAVAILABLE"
BLOCKER_SURFACE_INVALID = "DUAL_SLEEVE_SURFACE_INVALID"
NEXT_INPUT_PRIVATE_PORTFOLIO = "PRIVATE_PORTFOLIO_INPUT_REQUIRED"
NEXT_INPUT_INCOMPLETE = "PRIVATE_INPUT_INCOMPLETE"


def unavailable(reason: str = BLOCKER_STATUS_UNAVAILABLE) -> dict[str, Any]:
    """Fail-closed section body; a broken secondary surface invents nothing."""
    return {"schema_version": SCHEMA_VERSION, "action": ACTION,
            "status": STATUS_UNAVAILABLE, "namespace": None,
            "portfolio_connected": False, "position_guidance": None,
            "position_guidance_available": False, "trade_eligible": False,
            "acceptance_authority": None, "review_generated_at": None,
            "blockers": [reason], "next_user_input": None, "source": None}


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _next_user_input(status: str, blockers: list[str], guidance: Any) -> str | None:
    """Name the user-supplied input still missing; never fabricate holdings."""
    if guidance is not None:
        return None
    if status == "NOT_CONNECTED":
        return NEXT_INPUT_PRIVATE_PORTFOLIO
    if status == "BLOCKED_PRIVATE_INPUT" and blockers:
        return NEXT_INPUT_INCOMPLETE
    return None


def build_dual_sleeve_surface(report: Mapping[str, Any], *,
                              source: str | None = None) -> dict[str, Any]:
    """Restate one formally produced review; any unknown shape fails closed."""
    if (not isinstance(report, Mapping)
            or report.get("schema_version") != REPORT_SCHEMA
            or report.get("action") != ACTION):
        raise ValueError("dual-sleeve report schema or boundary mismatch")
    status = _optional_text(report.get("status"))
    if status is None:
        raise ValueError("dual-sleeve report status missing")
    raw_blockers = report.get("blockers")
    blockers = ([item for item in raw_blockers if isinstance(item, str)]
                if isinstance(raw_blockers, list) else [])
    guidance = report.get("position_guidance")
    namespace = _optional_text(report.get("namespace"))
    return {"schema_version": SCHEMA_VERSION, "action": ACTION, "status": status,
            "namespace": namespace,
            # Only a real ACTUAL review proves a connected private portfolio.
            "portfolio_connected": (status in REVIEWED_STATUSES
                                    and namespace == "ACTUAL"),
            "position_guidance": guidance,
            "position_guidance_available": guidance is not None,
            "trade_eligible": report.get("trade_eligible") is True,
            "acceptance_authority": _optional_text(report.get("acceptance_authority")),
            "review_generated_at": _optional_text(report.get("generated_at")),
            "blockers": blockers,
            "next_user_input": _next_user_input(status, blockers, guidance),
            "source": _optional_text(source)}

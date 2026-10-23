"""Public current-case explanations, separate from authenticated held reviews."""
from datetime import datetime
from pathlib import Path
import re

from ..hotspot.lifecycle_review import build_hotspot_lifecycle_review


def current_hotspot_lifecycle(*, root: Path, symbol: str, plan: dict,
                              now: datetime) -> dict | None:
    """Recompute the published case, never infer an Entry from a prior candidate.

    Candidate/registry validation belongs to the existing publication consumer.
    A rejected parent plan must not regain authority through this explanation.
    Private journals and user-provided bindings are not inputs to this surface.
    """
    if (not isinstance(plan, dict) or plan.get("symbol") != symbol
            or plan.get("action") != "no_order"
            or plan.get("signal_state") == "BLOCKED"
            or plan.get("candidate_lifecycle") == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"):
        return None
    try:
        path = plan["case_path"]
        digest = plan["case_sha256"]
        if (not isinstance(path, str) or not path.startswith("runtime/")
                or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
            return None
        review = build_hotspot_lifecycle_review(root=root, symbol=symbol,
            current_case_binding={"path": path, "sha256": digest}, now=now)
        observation = review["decision_explanation"]["current_price_observation"]
        if observation and observation["as_of"] != plan.get("market_trade_date"):
            return None
        if plan.get("signal_state") == "STALE" and review["current_data_status"] == "CURRENT":
            return None
        return review
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
        return None

"""Layer current quote evidence over the frozen M7 research packet."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.build_m7_daily_workbench import build_packet


def build_daily_product_packet(*, root: Path, generated_at: datetime, daily_quote: dict[str, Any]) -> dict[str, Any]:
    if daily_quote.get("action") != "no_order":
        raise ValueError("daily quote context must remain no_order")
    bundle = root / str(daily_quote["bundle_path"])
    if not bundle.is_file() or daily_quote.get("bundle_sha256") is None:
        raise ValueError("daily quote bundle is unavailable")
    packet = build_packet(generated_at)
    packet["as_of"] = daily_quote["as_of"]
    packet["daily_quote"] = daily_quote
    packet["audit"]["artifacts"].append(
        {
            "label": "当日双源行情原始归档",
            "path": str(bundle.relative_to(root)),
            "sha256": daily_quote["bundle_sha256"],
            "action": "no_order",
        }
    )
    return packet

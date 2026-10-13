"""Build the one versioned daily public decision packet (TL9 MVP-1)."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.product.common import write_new_json  # noqa: E402
from value_investment_agent.application.product.daily_public_packet import (  # noqa: E402
    SCHEMA_VERSION,
    build_daily_public_packet,
)


def _next_steps(packet: dict) -> list[str]:
    labels: list[str] = []
    for entry in packet["company_statuses"].values():
        for action in entry["pending_actions"]:
            if action["actor"] in {"HUMAN", "ENGINEERING"} and action["label"] not in labels:
                labels.append(str(action["label"]))
    return labels[:6]


def _report(packet: dict, status: str, path: Path | None) -> None:
    summary = {
        "status": status,
        "schema_version": SCHEMA_VERSION,
        "engine_version": packet.get("engine_version"),
        "action": packet["action"],
        "packet_status": packet["packet_status"],
        "publication_id": packet["publication_id"],
        "research_version": packet["research_version"],
        "generated_at": packet["generated_at"],
        "dates": packet["dates"],
        "formal_admission_count": packet["formal_admission_count"],
        "pending_review_count": packet["pending_review_count"],
        "research_counts": packet["research_counts"],
        "data_freshness": packet.get("data_freshness"),
        "source_bindings_verified": packet.get("source_bindings_verified", False),
        # Compact digest of the registered closes, so the daily entry can skip
        # a redundant re-registration of the same trade session (idempotency).
        "bridge_quote_dates": {
            symbol: (entry.get("price_bridge") or {}).get("quote_date")
            for symbol, entry in packet.get("company_statuses", {}).items()
        },
        "blockers": packet["blockers"],
        "next_steps": _next_steps(packet),
    }
    if path is not None:
        summary["path"] = path.relative_to(ROOT).as_posix()
        summary["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if packet.get("chain_error"):
        summary["chain_error"] = packet["chain_error"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("runtime/daily-public-packet"))
    parser.add_argument("--excel", type=Path, default=None,
                        help="Optional formal workbook path for the version comparison.")
    parser.add_argument("--generated-at", default=None,
                        help="Injected ISO timestamp for reproducible builds.")
    args = parser.parse_args()
    generated_at = datetime.fromisoformat(args.generated_at) if args.generated_at else None
    packet = build_daily_public_packet(
        ROOT, generated_at=generated_at, excel_path=args.excel)
    output_dir = (ROOT / args.output_dir).resolve()
    if not output_dir.is_relative_to((ROOT / "runtime").resolve()):
        parser.error("output directory must remain under runtime/")

    if packet["packet_status"] != "CURRENT" or not packet["publication_id"]:
        stamp = (generated_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")
        target = output_dir / f"daily-public-packet-unavailable-{stamp}.json"
        write_new_json(target, packet)
        _report(packet, "BLOCKED_CHAIN_UNAVAILABLE", target)
        return 2

    target = output_dir / f"daily-public-packet-{packet['publication_id']}.json"
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            existing = None
        if (isinstance(existing, dict) and existing.get("schema_version") == SCHEMA_VERSION
                and existing.get("action") == "no_order"
                and existing.get("publication_id") == packet["publication_id"]):
            # Report the stored record, not this run's clock: the identity is the
            # packet that is already on disk and no new bytes were written.
            _report(existing, "UNCHANGED", target)
            return 0
        _report(packet, "REFUSED_EXISTING_UNREADABLE", target)
        return 3
    write_new_json(target, packet)
    _report(packet, "WRITTEN", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

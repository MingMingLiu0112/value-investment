"""Build and publish the one versioned daily public decision packet.

TL9 MVP-1 composed the shared packet; TL10-RC makes the version identity
sound and publishes the result as the one frozen snapshot the Web reads.
With ``--read-only``, only verify the retained snapshot via public_snapshot;
never build, repair, publish, inspect Excel or write artifacts.

Exit codes:

* ``0``  the packet was written, re-verified unchanged, or repaired from the
  already stored identical version;
* ``2``  the publication chain is unavailable; nothing was published;
* ``3``  a stored artifact with the same identity exists but is unreadable;
  nothing was overwritten;
* ``4``  the same identity would carry different content: an identity conflict
  receipt was written and the current snapshot was left untouched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.product.common import write_new_json  # noqa: E402
from value_investment_agent.application.product.daily_public_packet import (  # noqa: E402
    SCHEMA_VERSION,
    build_daily_public_packet,
)
from value_investment_agent.application.product.public_snapshot import (  # noqa: E402
    load_current_packet,
    publish_snapshot,
)


def _next_steps(packet: dict) -> list[str]:
    labels: list[str] = []
    for entry in packet["company_statuses"].values():
        for action in entry["pending_actions"]:
            if action["actor"] in {"HUMAN", "ENGINEERING"} and action["label"] not in labels:
                labels.append(str(action["label"]))
    return labels[:6]


def _report(packet: dict, status: str, path: Path | None, *,
            snapshot: dict | None = None, conflict: Path | None = None,
            note: str | None = None) -> None:
    summary = {
        "status": status,
        "schema_version": SCHEMA_VERSION,
        "engine_version": packet.get("engine_version"),
        "action": packet["action"],
        "packet_status": packet["packet_status"],
        "publication_id": packet["publication_id"],
        "research_version": packet["research_version"],
        "generated_at": packet["generated_at"],
        "content_sha256": packet.get("content_sha256"),
        "dates": packet["dates"],
        "formal_admission_count": packet["formal_admission_count"],
        "pending_review_count": packet["pending_review_count"],
        "research_counts": packet["research_counts"],
        "data_freshness": packet.get("data_freshness"),
        "source_bindings_verified": packet.get("source_bindings_verified", False),
        "price_condition_status": packet.get("price_conditions", {}).get("status", "NOT_CONNECTED"),
        "price_condition_rows": [{"symbol": row["symbol"], "company_name": row["company_name"],
            **{key: row["price_action_plan"].get(key) for key in
               ("market_trade_date", "current_reference_price", "entry_trigger_price",
                "invalidation_price", "signal_state", "action_eligibility")}}
            for row in packet.get("price_conditions", {}).get("items", [])],
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
    if snapshot is not None:
        summary["snapshot"] = {
            "status": snapshot.get("status"),
            "publication_id": snapshot.get("publication_id"),
            "packet_path": snapshot.get("packet_path"),
            "packet_sha256": snapshot.get("packet_sha256"),
            "content_sha256": snapshot.get("content_sha256"),
            "published_at": snapshot.get("published_at"),
            "receipt_path": snapshot.get("receipt_path"),
        }
    if conflict is not None:
        summary["conflict_receipt"] = conflict.relative_to(ROOT).as_posix()
    if note is not None:
        summary["note"] = note
    if packet.get("chain_error"):
        summary["chain_error"] = packet["chain_error"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _stored(target: Path) -> dict | None:
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def _publish(packet: dict, target: Path, *, skip: bool) -> dict | None:
    """Publish or fail closed; a refused publish never half-updates the pointer."""
    if skip:
        return None
    try:
        return publish_snapshot(ROOT, packet, target)
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "REFUSED_PUBLISH_INVALID", "action": "no_order",
                          "publication_id": packet.get("publication_id"),
                          "reason": f"{type(error).__name__}: {error}",
                          "note": "快照发布前置校验失败；当前公开快照引用未被改动。"},
                         ensure_ascii=False, indent=2))
        raise SystemExit(3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--read-only", action="store_true",
                        help="Verify only the existing public snapshot; never build, publish or write.")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("runtime/daily-public-packet"))
    parser.add_argument("--excel", type=Path, default=None,
                        help="Optional formal workbook path for the version comparison.")
    parser.add_argument("--generated-at", default=None,
                        help="Injected ISO timestamp for reproducible builds.")
    parser.add_argument("--no-publish", action="store_true",
                        help="Store the packet artifact only; do not repoint the current snapshot.")
    args = parser.parse_args()
    if args.read_only:
        if sys.argv[1:] != ["--read-only"]:
            parser.error("--read-only cannot be combined with build, output, timestamp or Excel options")
        packet, reason = load_current_packet(ROOT)
        print(json.dumps({
            "status": "VERIFIED_READ_ONLY" if packet is not None else "BLOCKED",
            "action": "no_order", "read_only": True, "published": False,
            "scope": "STORED_PUBLIC_SNAPSHOT_INTEGRITY_ONLY",
            "publication_id": packet.get("publication_id") if packet is not None else None,
            "reason": reason,
            "web_url": "http://127.0.0.1:8001/daily",
        }, ensure_ascii=False, indent=2))
        return 0 if packet is not None else 2
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
        _report(packet, "BLOCKED_CHAIN_UNAVAILABLE", target,
                note="发布链不可用；未生成快照，也未改动当前公开快照引用。")
        return 2

    stamp = (generated_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")
    target = output_dir / f"daily-public-packet-{packet['publication_id']}.json"
    if target.is_file():
        existing = _stored(target)
        if (existing is not None and existing.get("schema_version") == SCHEMA_VERSION
                and existing.get("action") == "no_order"
                and existing.get("publication_id") == packet["publication_id"]):
            if existing.get("content_sha256") != packet.get("content_sha256"):
                # One identity must never carry two different decisions. The
                # stored record is kept, the disagreement is recorded and the
                # current snapshot keeps pointing at the previously verified
                # version.
                conflict = output_dir / (
                    f"daily-public-packet-conflict-{packet['publication_id']}-{stamp}.json")
                write_new_json(conflict, {
                    "schema_version": SCHEMA_VERSION, "action": "no_order",
                    "status": "IDENTITY_CONFLICT",
                    "publication_id": packet["publication_id"],
                    "stored_content_sha256": existing.get("content_sha256"),
                    "recomputed_content_sha256": packet.get("content_sha256"),
                    "stored_identity_inputs": existing.get("identity_inputs"),
                    "recomputed_identity_inputs": packet.get("identity_inputs"),
                    "note": ("同一版本身份出现了不同内容：拒绝覆盖既有记录，当前公开快照保持不变。"),
                })
                _report(packet, "REFUSED_IDENTITY_CONFLICT", target, conflict=conflict,
                        note="同一版本身份对应不同内容；已写入冲突回执，未覆盖、未发布。")
                return 4
            # Same identity, byte-equal decision content: report the stored
            # record (not this run's clock) and make sure the current snapshot
            # still points at it.
            snapshot = _publish(existing, target, skip=args.no_publish)
            _report(existing, "UNCHANGED", target, snapshot=snapshot,
                    note="输入与规则未变化；未写入新字节，快照引用已复核。")
            return 0
        _report(packet, "REFUSED_EXISTING_UNREADABLE", target,
                note="同身份记录无法读取；已失败关闭，未覆盖既有文件。")
        return 3
    write_new_json(target, packet)
    snapshot = _publish(packet, target, skip=args.no_publish)
    _report(packet, "WRITTEN", target, snapshot=snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

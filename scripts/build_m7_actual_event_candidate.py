"""Render an isolated M7 candidate with the verified ACTUAL M5 read model."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m7_daily_workbench import write_daily_workbench  # noqa: E402
from value_investment_agent.m5_actual_read_model import build_actual_event_read_model  # noqa: E402
from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload  # noqa: E402
from value_investment_agent.m5_event_run import m5_event_run_receipt_from_payload  # noqa: E402
from value_investment_agent.m5_recalculation_plan import bounded_recalculation_plan_from_payload  # noqa: E402
from value_investment_agent.m5_disclosure_queue import disclosure_review_queue_from_payload  # noqa: E402


def verified_followup_scan(path: Path, *, root: Path, symbol: str,
                           previous_scan_to: str, as_of: str) -> dict:
    path = path.resolve()
    root = root.resolve()
    if not path.is_relative_to(root):
        raise ValueError("Follow-up queue escapes the project root")
    payload = json.loads(path.read_text(encoding="utf-8"))
    queue = disclosure_review_queue_from_payload(payload)
    if queue.as_policy() != payload:
        raise ValueError("Follow-up queue is not canonical")
    if (len(queue.scans) != 1 or queue.scans[0].symbol != symbol
        or queue.scan_from != date.fromisoformat(previous_scan_to) + timedelta(days=1)
        or queue.scan_to > date.fromisoformat(as_of)
        or queue.retrieved_at.date() < queue.scan_to):
        raise ValueError("Follow-up scan identity or coverage window differs")
    scan = queue.scans[0]
    if (scan.coverage_status != "COMPLETE" or scan.announcements
        or len(scan.evidence_refs) != 1 or queue.unavailable_source_count):
        raise ValueError("Follow-up scan cannot claim zero complete announcements")
    ref = scan.evidence_refs[0]
    index_path = (root / ref["path"]).resolve()
    if (not index_path.is_relative_to(root) or not index_path.is_file()
        or hashlib.sha256(index_path.read_bytes()).hexdigest() != ref["sha256"]):
        raise ValueError("Follow-up CNINFO index is missing or changed")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    params = index.get("parameters") or {}
    if (ref.get("source_url") != "https://www.cninfo.com.cn/new/hisAnnouncement/query"
        or ref.get("announcement_count") != 0
        or index.get("total_announcements") != 0 or index.get("announcements") != []
        or params.get("seDate") != f"{queue.scan_from}~{queue.scan_to}"
        or str(params.get("stock", "")).split(",", 1)[0] != symbol):
        raise ValueError("Follow-up CNINFO index does not match the requested scan")
    return {
        "symbol": symbol, "provider": queue.provider,
        "scan_from": queue.scan_from.isoformat(), "scan_to": queue.scan_to.isoformat(),
        "retrieved_at": queue.retrieved_at.isoformat(),
        "coverage_status": scan.coverage_status, "announcement_count": 0,
        "queue_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "index_sha256": ref["sha256"], "action": "no_order",
    }


def project_m6_preflight(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (payload.get("schema_version") != "m6-operational-preflight-v1"
        or payload.get("action") != "no_order"
        or payload.get("operational_acceptance_status") != "NOT_STARTED"):
        raise ValueError("M6 preflight cannot certify operational acceptance")
    criteria = payload.get("criteria") or {}
    keys = {
        "mechanism": "m6c3_isolated_restore_mechanism",
        "restore": "m6c4_real_restore_rpo_rto",
        "calendar": "m6c7_official_exchange_calendar",
        "shadow": "m6c5_real_sessions_and_events",
        "authorization": "m6c6_production_authorization",
    }
    statuses = {name: criteria[key]["status"] if key in criteria else "NOT_PROVEN"
                for name, key in keys.items()}
    if (statuses["authorization"] != "REQUIRES_AUTHORIZATION"
        or statuses["shadow"] == "DONE"):
        raise ValueError("M6 preflight overstates authorization or real shadow")
    return {
        "status": "PREFLIGHT_ONLY",
        "engineering_status": payload["engineering_status"],
        "operational_status": "NOT_STARTED",
        "blockers": list(payload["summary"]["blockers"]),
        "criteria_status": statuses,
        "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--read-model", required=True, type=Path)
    parser.add_argument("--m6-receipt", type=Path)
    parser.add_argument("--followup-queue", type=Path)
    parser.add_argument("--scenario-review", type=Path)
    parser.add_argument("--review-source", type=Path)
    parser.add_argument("--review-package", type=Path)
    parser.add_argument("--pending-input", type=Path)
    for name in ("queue", "reviews", "receipt", "graph", "plan", "facts", "outcome"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    model_path = args.read_model.resolve()
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if (model.get("schema_version") != "m5-actual-event-read-model-v1"
        or model.get("action") != "no_order" or model.get("pending_human_review") != 0):
        raise ValueError("Actual M5 read model is not complete or no_order")
    review_requested = any(getattr(args, name) is not None for name in
                           ("scenario_review", "review_source", "review_package", "pending_input"))
    if review_requested or "scenario_review_file_sha256" in model:
        if model.get("research_review_status") != "HUMAN_REVIEWED_NEED_MORE_EVIDENCE":
            raise ValueError("Reviewed candidate cannot downgrade human research review")
        paths = (args.scenario_review, args.review_source, args.review_package, args.pending_input)
        if any(path is None for path in paths):
            raise ValueError("Reviewed candidate requires review, source, package and pending input")
        review = json.loads(args.scenario_review.read_text(encoding="utf-8"))
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        if (review.get("decision") != "NEED_MORE_EVIDENCE"
            or review.get("review_sha256") != model.get("research_review_sha256")
            or digest(args.scenario_review) != model.get("scenario_review_file_sha256")
            or digest(args.review_source) != review.get("source_sha256")
            or digest(args.review_package) != review.get("review_package_sha256")
            or digest(args.pending_input) != review.get("pending_input_file_sha256")
            or model.get("recalculation_result_sha256") != review.get("bounded_result_sha256")):
            raise ValueError("Reviewed candidate evidence binding differs")
        from value_investment_agent.m5_scenario_research_review import _sha
        if _sha({key: value for key, value in review.items() if key != "review_sha256"}) != review["review_sha256"]:
            raise ValueError("Reviewed candidate receipt hash differs")
        evidence_names = ("queue", "reviews", "receipt", "graph", "plan", "facts", "outcome")
        if any(getattr(args, name) is None for name in evidence_names):
            raise ValueError("Reviewed candidate requires complete ACTUAL replay evidence")
        evidence_paths = {name: getattr(args, name) for name in evidence_names}
        if any(digest(path) != model.get("input_sha256", {}).get(name)
               for name, path in evidence_paths.items()):
            raise ValueError("Reviewed candidate ACTUAL replay input hash differs")
        load = lambda name: json.loads(evidence_paths[name].read_text(encoding="utf-8"))
        rebuilt = build_actual_event_read_model(
            queue=load("queue"), reviews=load("reviews"),
            receipt=m5_event_run_receipt_from_payload(load("receipt")["receipt"]),
            graph=dependency_graph_from_payload(load("graph")["graph"]),
            plan=bounded_recalculation_plan_from_payload(load("plan")),
            facts_artifact=load("facts"), outcome_receipt=load("outcome"),
            facts_source_sha256=digest(evidence_paths["facts"]),
            scenario_review=review,
            scenario_review_source_bytes=args.review_source.read_bytes(),
            scenario_review_package_bytes=args.review_package.read_bytes(),
            scenario_review_pending_input_bytes=args.pending_input.read_bytes(),
        )
        if any(model.get(key) != value for key, value in rebuilt.items()):
            raise ValueError("Reviewed candidate read model differs from ACTUAL evidence replay")
    generated_at = datetime.now(timezone.utc)
    builder = runpy.run_path(str(source_root / "scripts" / "build_m7_daily_workbench_post_checkpoint_a.py"))
    packet = builder["build_packet"](generated_at)
    packet["as_of"] = generated_at.date().isoformat()
    queue = packet["m5"]["disclosure_queue_600519"]
    if queue["queue_id"] != model["queue_id"] or queue["symbol"] != model["symbol"]:
        raise ValueError("M7 disclosure queue does not match actual review read model")
    queue["pending_count"] = model["pending_human_review"]
    queue["pending_items"] = []
    packet["m5"]["actual_event_chain"] = model
    packet["stage_statuses"]["m3"] = [
        "M3", "ENGINEERING_PARTIAL_PLUS", "PARTIAL", "STRICT_PIT_NOT_PROVEN / R6",
    ]
    packet["stage_statuses"]["m4"] = [
        "M4", "NONPERSONALIZED_ENGINEERING_COMPLETE", "PARTIAL", "PENDING_PRIVATE_INPUT / R2",
    ]
    packet["stage_statuses"]["m6"] = [
        "M6", "PREFLIGHT_ONLY", "NOT_STARTED operationally", "AUTHORIZATION / SHADOW PENDING",
    ]
    packet["stage_statuses"]["m7"] = [
        "M7", "DISPLAY_ENGINEERING_AVAILABLE", "PARTIAL", "FINAL_USER_ACCEPTANCE_NOT_PASSED",
    ]
    if args.m6_receipt is not None:
        m6_path = args.m6_receipt.resolve()
        packet["m6"] = project_m6_preflight(m6_path)
        packet["audit"]["artifacts"].append({
            "label": "M6 指定只读预检收据", "path": str(m6_path),
            "sha256": packet["m6"]["receipt_sha256"],
        })
    if args.followup_queue is not None:
        followup = verified_followup_scan(
            args.followup_queue, root=source_root, symbol=model["symbol"],
            previous_scan_to=queue["scan_to"], as_of=packet["as_of"],
        )
        packet["m5"]["followup_scan"] = followup
        packet["audit"]["artifacts"].append({
            "label": "M5 后续 CNINFO 公告覆盖", "path": str(args.followup_queue.resolve()),
            "sha256": followup["queue_sha256"],
        })
    packet["stage_statuses"]["m5"] = [
        "M5", "ENGINEERING_DONE_WITH_VALIDATED_NOT_READY", "PARTIAL", "SCENARIO_NEED_MORE_EVIDENCE",
    ]
    packet["audit"]["artifacts"].append({
        "label": "M5 600519 ACTUAL 事件与有界重算状态",
        "path": str(model_path),
        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
    })
    receipt = write_daily_workbench(packet, output=args.output, root=ROOT)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

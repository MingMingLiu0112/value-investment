"""Build and optionally publish the two retained-source v4 value candidates.

This command is deliberately narrow.  It reuses the existing pending-candidate
producer and current-research registry; it does not approve research, admit a
price, calculate a personal position, or place an order.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from value_investment_agent.application.product.common import (
    load_json_object,
    sha256_file,
)
from value_investment_agent.application.product.pending_research_candidate import (
    prepare_pending_research_candidate,
    verify_pending_research_candidate,
)


ROOT = Path(__file__).resolve().parents[2]
CURRENT_POINTER = ROOT / "config" / "current-research-drafts.json"
CASES = {
    "600519": {
        "package": "runtime/product-cash-allocation-consumer/20261026T090212419386Z/candidate/package.json",
        "policy": "config/research-proposals/600519-joint-capital-cash-path-v4.json",
        "choice": "ADVANTAGE_CONTINUITY",
    },
    "600887": {
        "package": "runtime/cc1-companion-replay-20261023-v2-final/600887/package.json",
        "policy": "config/research-proposals/600887-joint-capital-cash-path-v4.json",
        "choice": "DAIRY_STABILIZATION",
    },
}


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _atomic_replace_json(path: Path, payload: dict) -> None:
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".part", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def build(*, output_root: Path, publish_current: bool) -> dict:
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite: {output_root}")
    bindings: dict[str, dict[str, str]] = {}
    summaries: dict[str, dict] = {}
    for symbol, case in CASES.items():
        package_path = ROOT / case["package"]
        policy_path = ROOT / case["policy"]
        package = load_json_object(package_path, f"{symbol} retained source package")
        request = {
            "schema_version": "research-schedule-request-v1",
            "symbol": symbol,
            "source_id": "CNINFO",
            "period": package["point_in_time"]["report_period"],
            "research_question_id": "joint_cash_v4_economic_terminal_research",
            "blocker_id": "pending_economic_model_review",
            "reopen_condition_met": True,
            "new_evidence_ids": [],
        }
        destination = output_root / symbol
        candidate = prepare_pending_research_candidate(
            root=ROOT,
            package_path=package_path,
            package_sha256=sha256_file(package_path),
            policy_path=policy_path,
            policy_sha256=sha256_file(policy_path),
            choice_id=case["choice"],
            output_dir=destination,
            schedule_request=request,
            schedule_request_sha256=_canonical_hash(request),
        )
        candidate_path = destination / "candidate.json"
        digest = sha256_file(candidate_path)
        verified = verify_pending_research_candidate(
            root=ROOT, path=candidate_path, expected_sha256=digest
        )
        if verified != candidate:
            raise ValueError(f"{symbol} candidate replay differs from generated result")
        bindings[symbol] = {
            "path": candidate_path.relative_to(ROOT).as_posix(),
            "sha256": digest,
        }
        summaries[symbol] = {
            "selected_choice": candidate["selected_choice"],
            "candidate_valuation": candidate["candidate_valuation"],
            "research_admitted": candidate["research_admitted"],
            "price_admitted": candidate["price_admitted"],
            "position_guidance": candidate["position_guidance"],
            "action": candidate["action"],
        }

    if publish_current:
        pointer = load_json_object(CURRENT_POINTER, "current research drafts")
        if (
            pointer.get("schema_version") != "current-research-drafts-v1"
            or pointer.get("action") != "no_order"
            or not isinstance(pointer.get("pending_candidates", {}), dict)
        ):
            raise ValueError("current research pointer is not publishable")
        pointer["pending_candidates"] = {
            **pointer.get("pending_candidates", {}),
            **bindings,
        }
        _atomic_replace_json(CURRENT_POINTER, pointer)

    return {
        "schema_version": "joint-cash-v4-current-publication-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "published_current": publish_current,
        "candidate_bindings": bindings,
        "summaries": summaries,
        "action": "no_order",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT
        / "runtime"
        / "joint-cash-v4-current"
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
    )
    parser.add_argument("--publish-current", action="store_true")
    args = parser.parse_args()
    result = build(
        output_root=args.output_root.resolve(), publish_current=args.publish_current
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

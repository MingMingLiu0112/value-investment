"""Build a narrow, honest M3 historical research replay packet.

The pinned Median-PE v2 contract is a retrospective research extension. Its
2024-06-21 source decision is replayed as point-in-time research only; it is
never promoted to a valuation or trade.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m3_historical_research_replay import (  # noqa: E402
    ACTION_NO_ORDER,
    REPLAY_NAMESPACE,
    REPLAY_SCHEMA,
    HistoricalEvidenceReference,
    HistoricalResearchReplay,
    HistoricalRuleBinding,
    ThenKnownFinancialFacts,
    ThenKnownQuote,
)


DEFAULT_SOURCE_DIR = (
    ROOT
    / "runtime"
    / "strategy-validation"
    / "moutai-pe-mid-paper-contract-v2-20260912T052747Z"
)
CN_TZ = timezone(timedelta(hours=8))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--as-of", type=lambda value: datetime.fromisoformat(value))
    return parser.parse_args()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_iso(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value}")
    return parsed


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _source_reference(path: Path, payload: dict) -> dict:
    return {
        "path": str(path.resolve()),
        "sha256": _digest(path),
        "rule_version": payload.get("rule_version") or payload.get("contract_version"),
        "valuation_approved": bool(payload.get("valuation_approved")),
        "trade_approved": bool(payload.get("trade_approved")),
    }


def _annual_for_replay(annual_inputs: list[dict], replay_date) -> dict:
    eligible = [
        row
        for row in annual_inputs
        if _parse_iso(row["available_at"]).date() <= replay_date
    ]
    if not eligible:
        raise ValueError("No annual inputs were available on the replay date")
    return max(eligible, key=lambda row: (_parse_iso(row["available_at"]), row["report_year"]))


def _find_ref(kind: str, refs: list[dict], *, contains: str = "") -> dict:
    for ref in refs:
        if ref.get("kind") != kind:
            continue
        if contains and contains not in json.dumps(ref, ensure_ascii=False):
            continue
        return ref
    raise ValueError(f"Reference not found: kind={kind}, contains={contains}")


def _date_from_url(ref: dict) -> datetime:
    match = re.search(r"/(\d{4}-\d{2}-\d{2})/", str(ref.get("url") or ""))
    if match:
        return datetime.fromisoformat(match.group(1) + "T00:00:00+08:00")
    raise ValueError("Reference URL does not contain an ISO date")


def build_replay(source_dir: Path, *, generated_at: datetime) -> HistoricalResearchReplay:
    source_dir = source_dir.resolve()
    input_path = source_dir / "input.json"
    daily_path = source_dir / "daily-decisions.json"
    summary_path = source_dir / "summary.json"
    manifest_path = source_dir / "manifest.json"
    if not all(path.is_file() for path in (input_path, daily_path, summary_path)):
        raise ValueError("Moutai historical source receipt is incomplete")
    input_payload = _load_json(input_path)
    daily_payload = json.loads(daily_path.read_text(encoding="utf-8"))
    summary = _load_json(summary_path)
    manifest = _load_json(manifest_path)
    if input_payload.get("contract_version") != "moutai-pe-mid-paper-contract-v2-2025-extension":
        raise ValueError("Unexpected Moutai historical contract version")
    if summary.get("valuation_approved") is not False or summary.get("trade_approved") is not False:
        raise ValueError("Source summary unexpectedly approves valuation or trade")
    if input_payload.get("research_simulation_eligible") is not True:
        raise ValueError("Source is not marked as research simulation eligible")
    if not str(input_payload.get("research_rule", {}).get("entry_margin")).startswith("30%"):
        raise ValueError("Unexpected historical research entry margin")

    source_decision = next(
        row for row in daily_payload if row.get("date") == "2024-06-21"
    )
    if source_decision.get("state") != "proposed_entry":
        raise ValueError("Historical source decision is not a proposed entry")
    if source_decision.get("action") != "propose_entry_review":
        raise ValueError("Historical source action is not propose_entry_review")
    replay_date = datetime.fromisoformat("2024-06-21T00:00:00+08:00").date()
    close_cny = str(source_decision["price_close_cny"])

    annual_inputs = [
        row
        for row in json.loads(
            (
                ROOT
                / "runtime"
                / "strategy-validation"
                / "moutai-warmup-20260909T062823719664Z"
                / "annual-inputs.json"
            ).read_text(encoding="utf-8")
        )
        if isinstance(row, dict) and row.get("symbol") == "600519"
    ]
    annual = _annual_for_replay(annual_inputs, replay_date)
    if annual.get("report_year") != 2023:
        raise ValueError("The latest PIT annual input must be the 2023 annual report")
    annual_available = _parse_iso(annual["available_at"])
    annual_published = _parse_iso(annual["published_date"] + "T00:00:00+08:00")
    annual_ref = HistoricalEvidenceReference(
        ref_id=str(annual["source_id"]),
        kind="annual_filing",
        path=str(annual["source_path"]),
        sha256=str(annual["raw_file_hash"]),
        source_url=str(annual["source_url"]),
        available_at=annual_available,
        role="2023 annual report, point-in-time filing",
        notes=str(annual.get("validation_scope") or ""),
    )
    distribution_ref_payload = _find_ref(
        "distribution",
        input_payload.get("references") or [],
        contains="2024-06-12",
    )
    distribution_ref = HistoricalEvidenceReference(
        ref_id="cninfo:" + re.search(r"/(\d+)\.PDF", distribution_ref_payload["url"], re.I).group(1),
        kind="distribution",
        path=str(distribution_ref_payload["path"]),
        sha256=str(distribution_ref_payload["sha256"]),
        source_url=str(distribution_ref_payload["url"]),
        available_at=_date_from_url(distribution_ref_payload),
        role="distribution filing available before replay date",
    )
    price_ref_payload = _find_ref(
        "prices",
        input_payload.get("references") or [],
        contains="2024",
    )
    price_ref = HistoricalEvidenceReference(
        ref_id="sh600519-2024-price-file",
        kind="prices",
        path=str(price_ref_payload["path"]),
        sha256=str(price_ref_payload["sha256"]),
        source_url=str(price_ref_payload["url"]),
        available_at=datetime(2024, 6, 21, 15, 0, tzinfo=CN_TZ),
        role="authenticated 2024 price file",
    )
    rule = HistoricalRuleBinding(
        rule_version=str(input_payload["contract_version"]),
        model_scope="relative_pe_research_only",
        registered_at=datetime(2026, 9, 12, 5, 27, 47, tzinfo=timezone.utc),
        rule_registration_status="RETROSPECTIVE_RESEARCH_EXTENSION",
        entry_margin=__import__("decimal").Decimal("0.30"),
        research_quantity=100,
        exit_rule="close exceeds that day's median-relative value",
    )
    facts = ThenKnownFinancialFacts(
        symbol="600519",
        period_label="2023-12-31",
        source_id=str(annual["source_id"]),
        published_at=annual_published,
        parent_profit_cny=str(annual["inputs"]["parent_profit_cny"]),
        ending_issued_shares=str(annual["inputs"]["ending_issued_shares"]),
        reported_basic_eps=str(annual["inputs"]["reported_basic_eps"]),
        source_ref=annual_ref,
    )
    quote = ThenKnownQuote(
        symbol="600519",
        quote_date=replay_date,
        close_cny=close_cny,
        source_ref=price_ref,
    )
    source_receipt = {
        "input": _source_reference(input_path, input_payload),
        "daily_decisions": _source_reference(daily_path, summary),
        "summary": _source_reference(summary_path, summary),
        "manifest": _source_reference(manifest_path, manifest),
        "source_decision": {
            "date": source_decision["date"],
            "state": source_decision["state"],
            "action": source_decision["action"],
            "safety_margin": source_decision.get("safety_margin"),
            "mid_value_cny": source_decision.get("mid_value_cny"),
            "prior_pe_multiple": source_decision.get("prior_pe_multiple"),
            "model_scope": source_decision.get("model_scope"),
        },
    }
    blockers = (
        "relative_pe_research_only_not_intrinsic_valuation",
        "retrospective_rule_not_contemporaneous",
        "valuation_approved_false",
        "no_human_research_approval",
        "positive_price_review_not_eligible",
    )
    return HistoricalResearchReplay(
        replay_id="m3-historical-research-replay-600519-2024-06-21-v1",
        schema_version=REPLAY_SCHEMA,
        namespace=REPLAY_NAMESPACE,
        symbol="600519",
        replay_date=replay_date,
        generated_at=generated_at,
        source_receipt=source_receipt,
        then_known_facts=facts,
        then_known_filings=(annual_ref, distribution_ref),
        then_known_quote=quote,
        rule=rule,
        source_decision_state=source_decision["state"],
        source_decision_action=source_decision["action"],
        final_decision="WAIT",
        blockers=blockers,
        valuation_approved=False,
        trade_approved=False,
        positive_price_review_eligible=False,
        future_facts_used=False,
        future_rule_version_used=True,
        action=ACTION_NO_ORDER,
    )


def main() -> int:
    args = parse_args()
    generated_at = args.as_of or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    replay = build_replay(args.source_dir.resolve(), generated_at=generated_at)
    output_dir = args.output_dir or (
        ROOT / "runtime" / f"m3-historical-research-replay-{generated_at:%Y%m%dT%H%M%SZ}"
    )
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Historical replay output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    replay_path = output_dir / "replay.json"
    replay_path.write_text(replay.to_json() + "\n", encoding="utf-8")
    manifest = {
        "schema_version": REPLAY_SCHEMA,
        "namespace": REPLAY_NAMESPACE,
        "replay_id": replay.replay_id,
        "replay_sha256": replay.replay_sha256,
        "source_dir": str(args.source_dir.resolve()),
        "source_input_sha256": replay.source_receipt["input"]["sha256"],
        "generated_at": generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

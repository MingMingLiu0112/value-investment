"""Optional, read-only monthly comparison of pinned existing workbenches."""
from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from .common import (
    ACTION_NO_ORDER, encode_json_bytes, normalize_symbol, receipt, require_inside,
    sha256_bytes, sha256_file,
)
from .decision_surface import verify_current_decision_workbench
from .workbench import load_existing_workbench_for_presentation
from ...research_artifact_codecs import artifact_payload


SCHEMA_VERSION = "monthly-research-review-v1"
_FIELDS = (
    "financial_operating_facts", "main_valuation_assumptions", "dividend_policy",
    "price_attractiveness", "thesis_consistency", "next_month_triggers",
)


def _select(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any] | None:
    selected = {key: payload[key] for key in keys if payload.get(key) not in (None, [], {})}
    return selected or None


def _read(*, root: Path, path: Path, digest: str, symbol: str) -> dict[str, Any]:
    target = require_inside(root, root / path, "monthly workbench input")
    raw = target.read_bytes()
    if sha256_bytes(raw) != digest:
        raise ValueError("monthly workbench hash mismatch")
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("symbol") != symbol:
        raise ValueError("monthly workbench symbol mismatch")
    generated = datetime.fromisoformat(payload["generated_at"])
    if generated.utcoffset() is None:
        raise ValueError("monthly workbench requires an aware timestamp")
    values = dict.fromkeys(_FIELDS)
    if payload.get("schema_version") == "product-existing-research-workbench-v1":
        verified = load_existing_workbench_for_presentation(
            root=root, path=target, expected_sha256=digest,
        )
        if verified.get("scope") != "EXISTING_RESEARCH_ONLY_NOT_CURRENT_ADVICE":
            raise ValueError("historical workbench scope mismatch")
        research = verified["research"]
        as_of = (research.get("dependency_view") or {}).get("valuation_date")
        scope = "HISTORICAL_RESEARCH_ONLY_NOT_CURRENT_ADVICE"
        uncertainty = ["Historical source hashes do not prove strict PIT or current admission."]
    else:
        restored = verify_current_decision_workbench(payload)
        objects = restored.dependency_objects
        case = artifact_payload(objects["research_case"])[1]
        facts = artifact_payload(objects["financial_facts"])[1]
        assumptions = objects.get("valuation_assumptions")
        zone = objects.get("price_attractiveness")
        consistency = objects.get("investment_consistency_review")
        # Scenario inputs are forward-looking assumptions, never disclosed facts.
        if (facts.get("verified") is True and not facts.get("blockers")
                and facts.get("evidence_refs") and facts.get("operating_inputs")):
            values["financial_operating_facts"] = _select(facts, ("facts_type", "operating_inputs"))
        if assumptions is not None:
            assumption_payload = artifact_payload(assumptions)[1]
            if assumption_payload.get("assumptions"):
                values["main_valuation_assumptions"] = _select(
                    assumption_payload, ("assumptions", "status", "blockers"),
                )
        # A financial-summary policy is research text, not a new official announcement.
        values["dividend_policy"] = _select(case.get("financial_summary") or {}, ("dividend_policy",))
        if zone is not None:
            values["price_attractiveness"] = _select(
                artifact_payload(zone)[1],
                ("status", "current_price", "quote_date", "blockers", "reasons"),
            )
        if consistency is not None:
            values["thesis_consistency"] = _select(
                artifact_payload(consistency)[1],
                ("status", "thesis_status", "blockers", "reasons", "comparisons"),
            )
        values["next_month_triggers"] = _select(case, ("next_events", "thesis_breakers"))
        as_of = case["as_of"]
        scope = "VERIFIED_SECURITY_RESEARCH_ONLY"
        uncertainty = ["Research changes are not proof of newly disclosed official facts."]
        source_contract_status = (payload.get("source_verification") or {}).get("source_contract_status")
        if source_contract_status == "LEGACY_CONTRACT_NOT_REAL_INPUT_ADMISSION":
            scope = source_contract_status
            uncertainty.append(
                "Legacy source contract: dependency replay does not establish real-input admission."
            )
        if consistency is None:
            uncertainty.append("Thesis consistency unavailable: no verified consistency review.")
    if as_of is not None:
        date.fromisoformat(as_of)
    if sha256_file(target) != digest:
        raise ValueError("monthly workbench changed during read")
    return dict(path=target, digest=digest, generated=generated, as_of=as_of,
                scope=scope, values=values, uncertainty=uncertainty)


def build_monthly_research_review(
    *, root: Path, symbol: str, current_workbench_path: Path,
    current_workbench_sha256: str, previous_workbench_path: Path | None = None,
    previous_workbench_sha256: str | None = None, output_path: Path | None = None,
) -> dict[str, Any]:
    """Compare replayed semantics without running research or changing approval.

    The caller supplies exact workbench pins; no latest-pointer discovery or
    private portfolio input is accepted. Missing previous evidence is explicit.
    """
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    target = None if output_path is None else require_inside(root, root / output_path, "monthly output")
    if (previous_workbench_path is None) != (previous_workbench_sha256 is None):
        raise ValueError("previous workbench requires both path and SHA-256")
    current = _read(root=root, path=current_workbench_path,
                    digest=current_workbench_sha256, symbol=symbol)
    previous = None if previous_workbench_path is None else _read(
        root=root, path=previous_workbench_path, digest=previous_workbench_sha256, symbol=symbol,
    )
    if previous is not None and (
        previous["generated"] > current["generated"] or
        (previous["as_of"] is not None and current["as_of"] is not None
         and previous["as_of"] > current["as_of"])
    ):
        raise ValueError("previous workbench is later than current workbench")
    rows = {}
    for field in _FIELDS:
        before = None if previous is None else previous["values"][field]
        after = current["values"][field]
        status = "UNAVAILABLE" if before is None or after is None else (
            "UNCHANGED" if before == after else "CHANGED_RESEARCH_ARTIFACT"
        )
        rows[field] = dict(status=status, previous=before, current=after,
                           interpretation="Unavailable comparable explicit fields." if status == "UNAVAILABLE"
                           else "Research semantics only; not proof of a new official disclosure.")
    same_date = previous is not None and previous["as_of"] == current["as_of"]
    result = {
        "schema_version": SCHEMA_VERSION, "symbol": symbol, "action": ACTION_NO_ORDER,
        "scope": current["scope"], "previous_scope": None if previous is None else previous["scope"],
        "current_research_as_of": current["as_of"],
        "previous_research_as_of": None if previous is None else previous["as_of"],
        "comparison_status": "PREVIOUS_UNAVAILABLE" if previous is None else "SAME_RESEARCH_DATE" if same_date else "COMPARED",
        "official_facts_status": "NO_NEW_DISCLOSED_FACTS_ESTABLISHED",
        "official_facts_note": "No new disclosed facts established by this comparison; artifact changes do not establish official disclosure novelty.",
        "fields": rows, "uncertainty": current["uncertainty"] + ([] if previous is None else previous["uncertainty"]),
        "position_guidance": None, "portfolio_input_status": "BLOCKED_PRIVATE_INPUT",
        "current_admission": False, "approval_changed": False,
        "canonical_workbook_written": False,
    }
    inputs = {"current_workbench": current_workbench_sha256}
    if previous is not None:
        inputs["previous_workbench"] = previous_workbench_sha256
    sources = [current] + ([] if previous is None else [previous])
    result["source_bindings"] = [dict(path=str(item["path"].relative_to(root)), sha256=item["digest"]) for item in sources]
    for item in sources:
        if sha256_file(item["path"]) != item["digest"]:
            raise ValueError("monthly workbench changed during comparison")
    encoded = encode_json_bytes(result)
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(encoded)
    return {"result": result, "receipt": receipt(
        command="monthly_research_review", symbol=symbol, input_hashes=inputs,
        output_path=target, output_bytes=encoded if target is not None else None,
    )}

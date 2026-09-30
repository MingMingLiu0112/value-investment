"""Read a pinned existing result for display, without re-running research."""
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Mapping

from ...domain.research.research_run_contract import valuation_result_sha256
from ...domain.research.research_case import ResearchCase
from ...domain.research.research_gate import evaluate_with_valuation
from ...valuation_models.base import ValuationResult
from ...valuation_models.residual_income import MODEL_VERSION, scenario_value
from ...model_validity import evaluate_model_validity
from ...price_bridge import bridge_with_quote
from ...quote_snapshot import QuoteSnapshot, QUOTE_STATUS_PENDING_EXTERNAL_DATA
from .common import require_inside, sha256_bytes, normalize_symbol, write_new_json


def read_existing_research_result(
    *, root: Path, symbol: str, manifest_path: Path, manifest_sha256: str,
    output_path: Path | None = None,
    arithmetic_input_path: Path | None = None, arithmetic_input_sha256: str | None = None,
) -> dict:
    manifest_path = require_inside(root, manifest_path, "existing-result manifest")
    content = manifest_path.read_bytes()
    if sha256_bytes(content) != manifest_sha256:
        raise ValueError("existing-result manifest hash mismatch")
    manifest = json.loads(content.decode("utf-8-sig"))
    if manifest.get("action") != "no_order" or manifest.get("status") != "PASS":
        raise ValueError("existing-result manifest not verified")
    valuation, sources = load_existing_valuation(
        root=root, artifact_path=root / manifest["artifact_path"],
        expected_sha256=manifest["artifact_sha256"],
        evidence_paths={item["evidence_id"]: root / item["path"] for item in manifest["evidence"]},
        observed_at=datetime.fromisoformat(manifest["verified_at"]),
    )
    if valuation.symbol != normalize_symbol(symbol):
        raise ValueError("existing-result symbol mismatch")
    result = dict(schema_version="existing-research-read-v1", symbol=valuation.symbol,
                  mode="READ_EXISTING_ONLY", action="no_order", status="EXISTING_RESEARCH_ONLY",
                  valuation=json.loads(valuation.to_json()), source_records=list(sources),
                  suggested_state="NOT_READY", position_guidance=None,
                  model_validity="NOT_ESTABLISHED", price_bridge=None, strict_pit="NOT_PROVEN",
                  manifest_sha256=manifest_sha256, artifact_sha256=manifest["artifact_sha256"],
                  blockers=["Existing-result read does not admit current model validity, price, research or portfolio gates."],
                  research_rerun=False, canonical_workbook_written=False)
    artifact_bytes = (root / manifest["artifact_path"]).read_bytes()
    if sha256_bytes(artifact_bytes) != manifest["artifact_sha256"]:
        raise ValueError("existing valuation artifact changed during read")
    artifact = json.loads(artifact_bytes)
    observation = datetime.fromisoformat(manifest["verified_at"])
    run = artifact.get("run", {})
    for key in ("available_at", "computed_at"):
        if key in run:
            timestamp = datetime.fromisoformat(run[key])
            if timestamp.utcoffset() is None or timestamp > observation:
                raise ValueError(f"research {key} not available at observation")
    if "research_as_of" in run and date.fromisoformat(run["research_as_of"]) > observation.date():
        raise ValueError("follow-up research date exceeds observation")
    result["dependency_view"] = dict(
        valuation_result_sha256=artifact["valuation_result_sha256"],
        valuation_date=valuation.valuation_date.isoformat(),
        followup_run_id=run.get("run_id"), followup_research_as_of=run.get("research_as_of"),
        observed_at=observation.isoformat(), availability_basis="current_observation_only",
        current_research_admission=False, current_price_admission=False,
        portfolio_snapshot=None, original_source_count=len(sources),
    )
    validity = evaluate_model_validity(
        model_id=valuation.model_version, symbol=valuation.symbol,
        model_as_of=valuation.valuation_date, valid_from=valuation.valuation_date,
        quote_date=observation.date(), events=[], event_scan_evidence_refs=[],
        blockers=["Existing-result read does not include an admitted current event scan."],
    )
    pending_quote = QuoteSnapshot(
        valuation.symbol, None, None, QUOTE_STATUS_PENDING_EXTERNAL_DATA, [],
        ["Existing-result read does not include an admitted current quote."],
    )
    pending_bridge = bridge_with_quote(
        valuation, validity, pending_quote, blockers=pending_quote.blockers,
    )
    result["model_validity_result"] = json.loads(validity.to_json())
    result["price_bridge"] = json.loads(pending_bridge.to_json())
    result["blockers"] = list(dict.fromkeys([*result["blockers"], *pending_bridge.blockers]))
    binding = artifact.get("run", {}).get("source_package")
    if binding is not None:
        package = require_inside(root, root / binding["path"], "research source package")
        package_bytes = package.read_bytes()
        if sha256_bytes(package_bytes) != binding["sha256"]:
            raise ValueError("research source package hash mismatch")
        raw = dict(json.loads(package_bytes)["research_case"])
        for key in ("as_of", "quote_date", "financial_period"):
            raw[key] = date.fromisoformat(raw[key])
        raw["generated_at"] = datetime.fromisoformat(raw["generated_at"])
        case = ResearchCase(**raw)
        if case.symbol != valuation.symbol:
            raise ValueError("research source package symbol mismatch")
        if case.as_of > observation.date():
            raise ValueError("research date exceeds observation date")
        gate = evaluate_with_valuation(case, valuation, model_id=valuation.model_type, approval=None)
        result["historical_research_gate"] = dict(
            research_as_of=case.as_of.isoformat(), source_package_sha256=binding["sha256"],
            results=gate.results, blockers=gate.blockers, conclusion=gate.conclusion,
            internal_status=gate.internal_status, current_admission=False,
            assessment_basis="pinned_original_case_without_valuation_approval",
        )
        result["dependency_view"].update(
            original_research_version=case.research_version,
            original_research_as_of=case.as_of.isoformat(),
            original_research_sha256=sha256_bytes(case.to_json().encode("utf-8")),
            source_package_path=package.relative_to(root.resolve()).as_posix(),
            source_package_sha256=binding["sha256"],
            original_case_is_current_approval=False,
        )
    if (arithmetic_input_path is None) != (arithmetic_input_sha256 is None):
        raise ValueError("arithmetic replay requires input path and hash")
    if arithmetic_input_path is not None:
        result["arithmetic_replay"] = replay_residual_income_input(
            root=root, path=arithmetic_input_path, expected_sha256=arithmetic_input_sha256,
            valuation=valuation,
        )
    if output_path is not None:
        write_new_json(require_inside(root, output_path, "existing-result output"), result)
    return result


def replay_residual_income_input(
    *, root: Path, path: Path, expected_sha256: str, valuation: ValuationResult,
) -> dict:
    """Recompute explicitly reconstructed arithmetic; never admit original-run PIT."""
    content = require_inside(root, path, "arithmetic input").read_bytes()
    if sha256_bytes(content) != expected_sha256:
        raise ValueError("arithmetic input hash mismatch")
    packet = json.loads(content)
    if (packet.get("schema_version") != "residual-income-arithmetic-replay-input-v1"
            or packet.get("action") != "no_order" or packet.get("symbol") != valuation.symbol
            or packet.get("model_version") != MODEL_VERSION
            or valuation.model_version != MODEL_VERSION
            or valuation.model_type != "residual_income_or_equity_value"
            or packet.get("input_basis") != "reconstructed_from_pinned_review"
            or packet.get("valuation_result_sha256") != valuation_result_sha256(valuation)):
        raise ValueError("arithmetic input scope or valuation binding mismatch")
    if not packet.get("source_bindings"):
        raise ValueError("arithmetic input requires source bindings")
    bound_sources = {}
    for source in packet["source_bindings"]:
        raw = require_inside(root, root / source["path"], "arithmetic source").read_bytes()
        if sha256_bytes(raw) != source["sha256"]:
            raise ValueError("arithmetic source hash mismatch")
        bound_sources[source["path"]] = (source["sha256"], raw)
    if date.fromisoformat(packet["valuation_date"]) != valuation.valuation_date:
        raise ValueError("arithmetic valuation basis mismatch")
    if set(packet["scenarios"]) != {"bear", "base", "bull"}:
        raise ValueError("arithmetic requires three explicit scenarios")
    primary_review = _read_primary_numeric_review(packet, bound_sources, valuation)
    rows = []
    for key in ("bear", "base", "bull"):
        inputs = packet["scenarios"][key]
        computed = scenario_value(Decimal(packet["start_book_equity"]), Decimal(packet["ordinary_shares"]),
                                  Decimal(inputs["cost_of_equity"]), inputs)
        value = Decimal(computed["conditional_value_per_2025_issued_share_cny"])
        retained = getattr(valuation, f"{key}_value")
        if retained is None or value != retained:
            raise ValueError(f"arithmetic scenario mismatch: {key}")
        rows.append(dict(scenario=key, recomputed=str(value), retained=str(retained), match=True))
    return dict(status="ARITHMETIC_MATCH", input_sha256=expected_sha256, model_version=MODEL_VERSION,
                scenarios=rows, input_basis=packet["input_basis"], action="no_order",
                original_run_input_descriptor_verified=False, strict_pit="NOT_PROVEN",
                current_admission=False, primary_numeric_review=primary_review)


def _read_primary_numeric_review(packet: dict, sources: dict, valuation: ValuationResult) -> dict | None:
    """Bind reviewed fact metadata to arithmetic, not to financial/PIT admission."""
    binding = packet.get("primary_numeric_review")
    if binding is None:
        return None
    if (binding.get("current_admission") is not False
            or binding.get("scope") != "two_input_values_verified_against_primary_report"
            or binding.get("path") not in sources):
        raise ValueError("primary numeric review binding mismatch")
    digest, content = sources[binding["path"]]
    review = json.loads(content)
    if (review.get("schema_version") != "primary-equity-basis-numeric-review-v1"
            or review.get("symbol") != valuation.symbol or review.get("action") != "no_order"
            or review.get("financial_gate_admission") is not False
            or review.get("current_admission") is not False or review.get("strict_pit") != "NOT_PROVEN"):
        raise ValueError("primary numeric review scope mismatch")
    observed = datetime.fromisoformat(review["observed_at"])
    if observed.utcoffset() is None or observed > datetime.now(timezone.utc):
        raise ValueError("primary numeric observation is timezone-free or in the future")
    expected = {"start_book_equity": "CNY", "ordinary_shares": "shares"}
    facts = review.get("facts", [])
    if len(facts) != 2 or {fact.get("fact_name") for fact in facts} != set(expected):
        raise ValueError("primary numeric review requires exactly the two model basis facts")
    for fact in facts:
        name = fact["fact_name"]
        source = sources.get(fact.get("source_path"))
        if (fact.get("symbol") != valuation.symbol or fact.get("unit") != expected[name]
                or date.fromisoformat(fact["period"]) != valuation.valuation_date
                or Decimal(fact["value"]) != Decimal(packet[name])
                or source is None or source[0] != fact.get("source_file_hash")
                or fact.get("current_admission") is not False
                or fact.get("historical_availability_verified") is not False
                or fact.get("verification_status") != "NUMERIC_SOURCE_REVIEW_ONLY"
                or fact.get("availability_basis") != "current_observation_only"
                or datetime.fromisoformat(fact["available_at"]) != observed
                or not fact.get("source_id") or not fact.get("source_url")
                or not fact.get("evidence_excerpt") or not fact.get("parser_version")
                or type(fact.get("physical_page")) is not int or fact["physical_page"] < 1):
            raise ValueError("primary numeric fact does not match model input or source binding")
    return dict(status="INPUT_VALUES_BOUND_TO_REVIEWED_FACTS", review_sha256=digest,
                observed_at=observed.isoformat(), facts=facts, source_excerpt_semantics_verified=False,
                financial_gate_admission=False, current_admission=False, strict_pit="NOT_PROVEN")


def load_existing_valuation(
    *, root: Path, artifact_path: Path, expected_sha256: str,
    evidence_paths: Mapping[str, Path], observed_at: datetime,
) -> tuple[ValuationResult, tuple[dict, ...]]:
    """Availability means observed now, never inferred historical availability.

    Pinning authenticates bytes against the caller's expected artifact only;
    it does not provide research approval, issuer authentication or strict PIT.
    """
    if observed_at.utcoffset() is None:
        raise ValueError("observation must include timezone")
    path = require_inside(root, artifact_path, "existing valuation artifact")
    content = path.read_bytes()
    if sha256_bytes(content) != expected_sha256:
        raise ValueError("existing valuation artifact hash mismatch")
    payload = json.loads(content)
    if payload.get("action") != "no_order":
        raise ValueError("existing valuation must remain no_order")
    raw = dict(payload["valuation_result"])
    raw["valuation_date"] = date.fromisoformat(raw["valuation_date"])
    for key in ("bear_value", "base_value", "bull_value"):
        raw[key] = None if raw[key] is None else Decimal(raw[key])
    result = ValuationResult(**raw)
    if valuation_result_sha256(result) != payload["valuation_result_sha256"]:
        raise ValueError("existing valuation result hash mismatch")
    if result.valuation_date > observed_at.date():
        raise ValueError("valuation basis exceeds observation date")
    records = []
    seen = set()
    for ref in result.evidence_refs:
        evidence_id = ref["id"]
        if evidence_id in seen:
            raise ValueError("duplicate valuation evidence id")
        seen.add(evidence_id)
        if evidence_id not in evidence_paths:
            raise ValueError("missing valuation original path")
        source = require_inside(root, evidence_paths[evidence_id], "valuation original")
        if sha256_bytes(source.read_bytes()) != ref.get("sha256"):
            raise ValueError("valuation original hash mismatch")
        records.append(dict(
            evidence_id=evidence_id, title=evidence_id,
            artifact_type="existing_original_observed_now", path=source.relative_to(root.resolve()).as_posix(),
            sha256=ref["sha256"], available_at=observed_at.date().isoformat(), source_url=ref.get("url"),
            observed_at=observed_at.isoformat(), availability_basis="current_observation_only", action="no_order",
        ))
    return result, tuple(records)

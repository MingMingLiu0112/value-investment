"""Fail-closed preparation of a first-research-input-v1 specification.

This is deliberately an intake boundary, not a valuation, research or publication
service.  It reads three content-addressed inputs (native facts, D2 assumptions
and a source-bound company profile), validates that they describe the same issuer
and cut-off, then returns the *exact* v1 spec bytes for an explicit downstream
writer.  It never writes a candidate, receipt, package or approval.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from ..product.common import encode_json_bytes, require_inside, write_new_bytes
from . import first_research_input_v1 as consumer


SCHEMA = "first-research-intake-v2"
PROFILE_SCHEMA = "company-research-profile-v1"
_BINDING_KEYS = {"path", "sha256"}
_POINT_IN_TIME_KEYS = {
    "report_period", "research_as_of", "valuation_date", "available_at", "computed_at"
}
_INPUT_KEYS = {
    "schema_version", "action", "symbol", "name", "run_id", "point_in_time",
    "source_binding", "assumption_binding", "profile_binding", "capital_bindings",
    "share_basis", "research_case",
}
_SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_bound_json(root: Path, binding: Mapping[str, Any], label: str) -> tuple[dict, dict, bytes]:
    """Load exactly one project-local JSON artifact by immutable binding."""
    if (
        not isinstance(binding, Mapping)
        or set(binding) != _BINDING_KEYS
        or not isinstance(binding.get("path"), str)
        or not isinstance(binding.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"])
    ):
        raise ValueError(f"{label} requires an exact project-relative path/hash binding")
    relative = Path(binding["path"])
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"{label} path must remain project-relative")
    path = require_inside(root, root / relative, label)
    raw = path.read_bytes()
    if _digest(raw) != binding["sha256"]:
        raise ValueError(f"{label} hash mismatch: {binding['path']}")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must contain one JSON object") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return payload, dict(binding), raw


def _instant(value: Any, ceiling: datetime, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} requires an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} requires an ISO timestamp") from error
    if parsed.utcoffset() is None or parsed > ceiling:
        raise ValueError(f"{label} follows the intake cutoff or lacks timezone")
    return parsed


def _day(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} requires an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} requires an ISO date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} requires an exact ISO date")
    return parsed


def _point_in_time(value: Any, now: datetime) -> tuple[dict, datetime]:
    if not isinstance(value, Mapping) or set(value) != _POINT_IN_TIME_KEYS:
        raise ValueError("First intake requires the exact v1 point-in-time contract")
    result = dict(value)
    report_period = _day(result["report_period"], "report_period")
    valuation_date = _day(result["valuation_date"], "valuation_date")
    research_as_of = _day(result["research_as_of"], "research_as_of")
    if report_period != valuation_date or research_as_of < valuation_date:
        raise ValueError("First intake requires one financial basis no later than research_as_of")
    computed = _instant(result["computed_at"], now, "computed_at")
    available = _instant(result["available_at"], computed, "available_at")
    return result, available


def _validate_source(payload: Mapping[str, Any], *, symbol: str, basis: str, cutoff: datetime) -> None:
    required = {"schema_version", "symbol", "generated_at", "financial_basis", "sources", "facts"}
    if not required.issubset(payload) or payload.get("symbol") != symbol or payload.get("financial_basis") != basis:
        raise ValueError("Native facts binding issuer or financial basis mismatch")
    _instant(payload["generated_at"], cutoff, "native facts generated_at")
    if not isinstance(payload["sources"], list) or not payload["sources"]:
        raise ValueError("Native facts require at least one source")
    if not isinstance(payload["facts"], list) or not payload["facts"]:
        raise ValueError("Native facts require at least one extracted fact")
    for source in payload["sources"]:
        if not isinstance(source, Mapping):
            raise ValueError("Native facts source row invalid")
        available = source.get("source_available_at", source.get("available_at"))
        if available is None:
            raise ValueError("Native facts source availability is required")
        _instant(available, cutoff, "native facts source availability")


def _validate_assumptions(payload: Mapping[str, Any], *, symbol: str, basis: str, cutoff: datetime) -> None:
    expected = {
        "schema_version", "action", "symbol", "financial_basis", "generated_at",
        "assumption_scope", "source_bindings", "choice", "historical_bindings", "scenarios",
    }
    if (
        set(payload) != expected
        or payload.get("schema_version") != consumer.ASSUMPTIONS_SCHEMA
        or payload.get("action") != "no_order"
        or payload.get("symbol") != symbol
        or payload.get("financial_basis") != basis
        or payload.get("assumption_scope") != "RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST"
    ):
        raise ValueError("D2 assumptions identity or scope mismatch")
    _instant(payload["generated_at"], cutoff, "D2 assumptions generated_at")
    if not isinstance(payload["source_bindings"], list) or not payload["source_bindings"]:
        raise ValueError("D2 assumptions require explicit rationale bindings")
    if not isinstance(payload["historical_bindings"], Mapping) or set(payload.get("scenarios", {})) != {"bear", "base", "bull"}:
        raise ValueError("D2 assumptions require historical bindings and bear/base/bull scenarios")


def _validate_profile(payload: Mapping[str, Any], *, symbol: str, basis: str,
        research_as_of: str, cutoff: datetime) -> str:
    if (
        payload.get("schema_version") != PROFILE_SCHEMA
        or payload.get("action") != "no_order"
        or payload.get("symbol") != symbol
        or payload.get("status") != "SOURCE_BOUND_PROFILE"
        or not isinstance(payload.get("profile"), Mapping)
        or not isinstance(payload.get("route"), Mapping)
    ):
        raise ValueError("Source-bound company profile required")
    profile_id = payload["profile"].get("profile_id")
    route = payload["route"]
    if (
        profile_id != "quality_compounder"
        or route.get("status") != "SUPPORTED"
        or route.get("profile_id") not in (None, profile_id)
        or route.get("requested_model") not in (None, consumer.MODEL)
    ):
        raise ValueError("Profile is not applicable to first_research_input_v1")
    if payload.get("report_period") not in (None, basis):
        raise ValueError("Company profile period does not match first compilation basis")
    if payload.get("as_of") is not None:
        profile_day = _day(payload["as_of"], "company profile as_of")
        if not _day(basis, "financial basis") <= profile_day <= _day(research_as_of, "research_as_of"):
            raise ValueError("Company profile research date falls outside the intake window")
    _instant(payload.get("available_at"), cutoff, "company profile available_at")
    return profile_id


def _validate_research_case(value: Any) -> dict:
    if not isinstance(value, Mapping) or set(value) != consumer.NARRATIVE:
        raise ValueError("First intake requires the exact v1 research-case fields")
    result = deepcopy(dict(value))
    for field in ("industry", "investment_path", "thesis", "return_driver", "mispricing_hypothesis"):
        if not isinstance(result[field], str) or not result[field].strip():
            raise ValueError(f"Research-case field is required: {field}")
    for field in ("positives", "counter_evidence", "thesis_breakers", "next_events"):
        if not isinstance(result[field], list):
            raise ValueError(f"Research-case list is required: {field}")
    return result


def prepare_first_research_intake(*, root: Path, intake: Mapping[str, Any], now: datetime) -> dict:
    """Return a normalized v1 spec and immutable input manifest without writing anything.

    A caller must write ``spec_bytes`` to a new location and bind that new file before
    calling :func:`first_research_input_v1.build_first_research_input`.  The returned
    manifest retains the profile binding because v1's frozen spec has no profile field.
    """
    if now.utcoffset() is None:
        raise ValueError("First intake requires a timezone-aware clock")
    if not isinstance(intake, Mapping) or set(intake) != _INPUT_KEYS:
        raise ValueError("First intake requires the exact v2 input contract")
    if intake.get("schema_version") != SCHEMA or intake.get("action") != "no_order":
        raise ValueError("First intake is research-only and requires action=no_order")
    symbol = intake.get("symbol")
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("First intake requires a six-digit symbol")
    if not isinstance(intake.get("name"), str) or not intake["name"].strip():
        raise ValueError("First intake requires an issuer name")
    if not isinstance(intake.get("run_id"), str) or not _SAFE_RUN_ID.fullmatch(intake["run_id"]):
        raise ValueError("First intake run_id is invalid")
    pit, cutoff = _point_in_time(intake["point_in_time"], now)
    root = root.resolve()
    source, source_binding, source_raw = _read_bound_json(root, intake["source_binding"], "native facts")
    assumptions, assumption_binding, assumptions_raw = _read_bound_json(
        root, intake["assumption_binding"], "D2 assumptions"
    )
    profile, profile_binding, profile_raw = _read_bound_json(root, intake["profile_binding"], "company profile")
    _validate_source(source, symbol=symbol, basis=pit["valuation_date"], cutoff=cutoff)
    _validate_assumptions(assumptions, symbol=symbol, basis=pit["valuation_date"], cutoff=cutoff)
    profile_id = _validate_profile(profile, symbol=symbol, basis=pit["valuation_date"],
        research_as_of=pit["research_as_of"], cutoff=cutoff)
    capital = intake.get("capital_bindings")
    if (
        not isinstance(capital, Mapping)
        or set(capital) != {"start_book_equity", "ordinary_shares"}
        or not all(isinstance(value, str) and value.strip() for value in capital.values())
    ):
        raise ValueError("First intake requires explicit capital fact identifiers")
    if intake.get("share_basis") not in {"issued_ordinary_shares", "ordinary_shares_excluding_treasury"}:
        raise ValueError("First intake share basis is unsupported")
    case = _validate_research_case(intake["research_case"])
    spec = {
        "schema_version": consumer.SCHEMA,
        "action": "no_order",
        "symbol": symbol,
        "name": intake["name"],
        "profile_id": profile_id,
        "run_id": intake["run_id"],
        "point_in_time": pit,
        "native_facts_binding": source_binding,
        "capital_bindings": dict(capital),
        "share_basis": intake["share_basis"],
        "assumption_binding": assumption_binding,
        "research_case": case,
    }
    spec_bytes = encode_json_bytes(spec)
    manifest = {
        "schema_version": SCHEMA,
        "action": "no_order",
        "formal_eligibility": False,
        "approvals_created": 0,
        "writes_formal_candidate": False,
        "consumer_schema": consumer.SCHEMA,
        "symbol": symbol,
        "profile_id": profile_id,
        "point_in_time": deepcopy(pit),
        "source_binding": source_binding,
        "assumption_binding": assumption_binding,
        "profile_binding": profile_binding,
        "source_bytes_sha256": _digest(source_raw),
        "assumption_bytes_sha256": _digest(assumptions_raw),
        "profile_bytes_sha256": _digest(profile_raw),
        "spec_sha256": _digest(spec_bytes),
    }
    manifest_bytes = encode_json_bytes(manifest)
    return {
        "status": "FIRST_INPUT_SPEC_PREPARED",
        "action": "no_order",
        "formal_eligibility": False,
        "approvals_created": 0,
        "writes_formal_candidate": False,
        "spec": spec,
        "spec_bytes": spec_bytes,
        "input_manifest": manifest,
        "input_manifest_bytes": manifest_bytes,
        "input_fingerprint": _digest(manifest_bytes),
    }


def compile_first_research_from_intake(*, root: Path, intake: Mapping[str, Any],
        intake_output_dir: Path, output_dir: Path, now: datetime, fact_replay=None) -> dict:
    """Persist a new source-bound v1 spec then invoke the existing E2 compiler.

    This is the only write-capable E2 convenience entry.  It intentionally
    delegates arithmetic, candidate/package creation and cold replay to
    ``first_research_input_v1``; no second valuation path is introduced here.
    Both directories are append-only and must be distinct so a failed compiler
    cannot overwrite the input record used to explain or retry the run.
    """
    root = root.resolve()
    prepared = prepare_first_research_intake(root=root, intake=intake, now=now)
    intake_output_dir = require_inside(root / "runtime", intake_output_dir, "first intake output")
    output_dir = require_inside(root / "runtime", output_dir, "first compilation output")
    if intake_output_dir == output_dir:
        raise ValueError("first intake and compilation outputs must be separate")
    if intake_output_dir.exists() or output_dir.exists():
        raise FileExistsError("first intake or compilation output already exists")
    intake_output_dir.mkdir(parents=True)
    spec_path = intake_output_dir / "spec.json"
    manifest_path = intake_output_dir / "input-manifest.json"
    write_new_bytes(spec_path, prepared["spec_bytes"])
    write_new_bytes(manifest_path, prepared["input_manifest_bytes"])
    spec_binding = {"path": spec_path.relative_to(root).as_posix(), "sha256": _digest(prepared["spec_bytes"])}
    try:
        compiled = consumer.build_first_research_input(
            root=root, spec_binding=spec_binding, output_dir=output_dir, now=now,
            fact_replay=fact_replay,
        )
    except Exception:
        # The retained input record is intentional: it is the immutable failed
        # run input and must not be silently deleted or modified.
        raise
    return {
        "status": "FIRST_INPUT_COMPILED_FROM_INTAKE",
        "action": "no_order",
        "formal_eligibility": False,
        "approvals_created": 0,
        "writes_formal_candidate": False,
        "input_manifest_binding": {
            "path": manifest_path.relative_to(root).as_posix(),
            "sha256": _digest(prepared["input_manifest_bytes"]),
        },
        "spec_binding": spec_binding,
        "compilation": compiled,
    }


__all__ = ["SCHEMA", "prepare_first_research_intake", "compile_first_research_from_intake"]

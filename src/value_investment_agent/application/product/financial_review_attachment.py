"""Load retained financial research as a read-only, unadmitted supplement."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from typing import Any

from .common import load_json_object, normalize_symbol, require_inside, sha256_file


MANIFEST_SCHEMA = "yili-current-fact-review-v1-manifest"
FACTS_SCHEMA = "yili-current-fact-review-v1"
SOURCE_SCOPE = "CURRENT_REVIEW_OF_RETAINED_DISCLOSURES_NOT_CURRENT_VALUATION_OR_PIT_ADMISSION"
STATUS = "SOURCE_VERIFIED_RESEARCH_SUPPLEMENT_NOT_ADMITTED"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_OFFICIAL_PDF = re.compile(
    r"https://static\.cninfo\.com\.cn/finalpage/(\d{4}-\d{2}-\d{2})/(\d+)\.PDF",
    re.IGNORECASE,
)


def _timestamp(value: Any, label: str, now: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} requires an ISO timestamp") from None
    if parsed.utcoffset() is None:
        raise ValueError(f"{label} requires a timezone")
    if parsed > now:
        raise ValueError(f"{label} is a future timestamp")
    return parsed


def _check_timestamps(value: Any, now: datetime) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if (key.endswith("_at") or key == "available_at_conservative") and item is not None:
                _timestamp(item, key, now)
            _check_timestamps(item, now)
    elif isinstance(value, list):
        for item in value:
            _check_timestamps(item, now)


def load_financial_review_attachment(
    *, root: Path, symbol: str, manifest_path: Path, manifest_sha256: str,
) -> dict:
    """Rehash every binding; generated_at is never a research cutoff.

    No script is run and no financial calculation, admission, approval or
    decision state is recomputed. Only the existing versioned manifest is read.
    """
    root = Path(root).resolve(strict=True)
    now = datetime.now(timezone.utc)
    symbol = normalize_symbol(symbol)
    verified: dict[Path, str] = {}

    def verify(path_value: Any, digest: Any, label: str, base: Path = root) -> Path:
        if not isinstance(path_value, (str, Path)) or not str(path_value):
            raise ValueError(f"{label} requires a local path")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError(f"{label} requires an exact SHA-256")
        path = require_inside(root, base / path_value, label)
        if not path.is_file():
            raise ValueError(f"{label} file is missing")
        if path in verified and verified[path] != digest:
            raise ValueError(f"{label} has conflicting hashes")
        if sha256_file(path) != digest:
            raise ValueError(f"{label} hash mismatch")
        verified[path] = digest
        return path

    def binding(value: Any, label: str) -> Path:
        if not isinstance(value, dict):
            raise ValueError(f"{label} requires a path/sha256 binding")
        return verify(value.get("path"), value.get("sha256"), label)

    manifest_path = verify(manifest_path, manifest_sha256, "financial review manifest")
    manifest = load_json_object(manifest_path, "financial review manifest")
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("unsupported financial review manifest schema")
    if manifest.get("action") != "no_order":
        raise ValueError("financial review manifest must remain no_order")
    script_path = binding(manifest.get("script"), "financial review script")
    if script_path.suffix.lower() != ".py":
        raise ValueError("financial review script must be a Python file")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != {"facts.json", "report.md"}:
        raise ValueError("financial review outputs require exactly facts.json and report.md")
    facts_path = verify("facts.json", outputs["facts.json"], "financial review facts", manifest_path.parent)
    report_path = verify("report.md", outputs["report.md"], "financial review report", manifest_path.parent)
    if len({manifest_path, script_path, facts_path, report_path}) != 4:
        raise ValueError("financial review bindings must name distinct files")
    payload = load_json_object(facts_path, "financial review facts")
    if payload.get("schema_version") != FACTS_SCHEMA:
        raise ValueError("unsupported financial review facts schema")
    if payload.get("symbol") != symbol:
        raise ValueError("financial review symbol mismatch")
    if payload.get("scope") != SOURCE_SCOPE:
        raise ValueError("financial review must declare retained disclosure scope")
    if (payload.get("action") != "no_order"
            or any(payload.get(key) is not False for key in (
                "model_approved", "strict_pit_admitted", "price_admitted"))
            or payload.get("recommendation") != "NO_ACTION"
            or payload.get("position_guidance") is not None):
        raise ValueError("financial review must remain unadmitted and no_order")
    _timestamp(payload.get("generated_at"), "generated_at", now)
    _check_timestamps(manifest, now)
    _check_timestamps(payload, now)
    try:
        period_end = date.fromisoformat(payload["financial_period_end"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("financial_period_end requires an ISO date") from None
    if period_end > now.date():
        raise ValueError("financial_period_end is in the future")

    sources = manifest.get("source_bindings")
    if not isinstance(sources, list) or not sources or payload.get("source_bindings") != sources:
        raise ValueError("financial review source_bindings must match the manifest")
    catalog = {}
    for source in sources:
        source_path = binding(source, "financial review original PDF")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id or source_id in catalog:
            raise ValueError("financial review source ids must be unique")
        url = source.get("source_url")
        official = _OFFICIAL_PDF.fullmatch(url) if isinstance(url, str) else None
        if (source_path.suffix.lower() != ".pdf" or official is None
                or source_id != "cninfo:" + official.group(2)
                or source.get("published_date") != official.group(1)):
            raise ValueError("financial review original requires an official PDF binding")
        try:
            published = date.fromisoformat(source["published_date"])
        except (TypeError, ValueError):
            raise ValueError("source published_date requires an ISO date") from None
        available = _timestamp(source.get("available_at_conservative"), "source availability", now)
        _timestamp(source.get("current_local_verified_at"), "source verification", now)
        if published > now.date() or available.date() < published or not source.get("availability_basis"):
            raise ValueError("financial review source availability is invalid")
        catalog[source_id] = source

    facts = payload.get("facts")
    calculations = payload.get("calculations")
    limitations = payload.get("limitations")
    if not isinstance(facts, list) or not facts or not isinstance(calculations, dict) or not calculations:
        raise ValueError("financial review requires facts and defined calculations")
    if not isinstance(limitations, list) or not limitations or any(
        not isinstance(item, str) or not item for item in limitations
    ):
        raise ValueError("financial review requires explicit limitations")
    fact_catalog = {}
    for fact in facts:
        if not isinstance(fact, dict) or not isinstance(fact.get("id"), str) or not fact["id"]:
            raise ValueError("financial review fact requires an id")
        source = catalog.get(fact.get("source_id"))
        if source is None or fact.get("source_binding") != source:
            raise ValueError("financial review fact references an unbound source")
        if fact["id"] in fact_catalog or not isinstance(fact.get("columns"), list) or not fact["columns"]:
            raise ValueError("financial review facts require unique ids and columns")
        fact_catalog[fact["id"]] = fact
    for calculation in calculations.values():
        if not isinstance(calculation, dict) or any(
            not isinstance(calculation.get(key), str) or not calculation[key]
            for key in ("formula", "value", "unit", "scope")
        ):
            raise ValueError("financial review calculation requires its existing definition")
        try:
            numeric_value = Decimal(calculation["value"])
        except InvalidOperation:
            raise ValueError("financial review calculation value must be a finite Decimal") from None
        if not numeric_value.is_finite():
            raise ValueError("financial review calculation value must be a finite Decimal")
        ids = calculation.get("input_fact_ids")
        indices = calculation.get("input_column_indices")
        if not isinstance(ids, list) or not ids or not isinstance(indices, list) or len(ids) != len(indices):
            raise ValueError("financial review calculation requires fact/column references")
        for fact_id, index in zip(ids, indices):
            if (not isinstance(fact_id, str) or fact_id not in fact_catalog
                    or type(index) is not int or not 0 <= index < len(fact_catalog[fact_id]["columns"])):
                raise ValueError("financial review calculation references an undefined fact/column")

    # The historical review is inspected, not consumed as a financial fact.
    if "old_review_inspected" in payload:
        old_review = payload["old_review_inspected"]
        binding(old_review, "inspected historical review")
        if old_review.get("consumed_as_fact_object") is not False:
            raise ValueError("historical review must not be consumed as facts")
    for path, digest in verified.items():
        verify(path, digest, "financial review final verification")

    return {
        "status": STATUS,
        "scope": "NOT_ADMITTED",
        "verification_scope": "LOCAL_SOURCE_BYTES_ONLY_NOT_FINANCIAL_APPROVAL",
        "symbol": symbol,
        "manifest_binding": {"path": manifest_path.relative_to(root).as_posix(), "sha256": manifest_sha256},
        "facts": facts,
        "calculations": calculations,
        "limitations": limitations,
        "financial_period_end": payload["financial_period_end"],
        "generated_at": payload["generated_at"],
        "generated_at_role": "ARTIFACT_GENERATION_NOT_RESEARCH_CUTOFF",
        "source_bindings": sources,
        "model_approved": False,
        "strict_pit_admitted": False,
        "price_admitted": False,
        "action": "no_order",
    }

"""Explicit supplemental scan bindings; immutable research packages stay intact."""
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING
import json
import os
import tempfile

from .common import load_json_object, normalize_symbol, require_inside, sha256_file, write_new_json
from .quote_bridge import POINTER_PATH, POINTER_SCHEMA
from ...event_scan import event_scan_from_payload

if TYPE_CHECKING:
    from ...model_validity import ModelValidity

BINDING_SCHEMA = "incremental-validity-binding-v1"


def read_bound_json(root: Path, ref: dict, label: str) -> tuple[Path, dict]:
    if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
        raise ValueError(f"{label} requires explicit path and SHA-256")
    path = require_inside(root, root / ref["path"], label)
    if sha256_file(path) != ref["sha256"]:
        raise ValueError(f"{label} hash mismatch")
    return path, load_json_object(path, label)


def registered_package(root: Path, symbol: str) -> tuple[dict, dict]:
    pointer = load_json_object(root / POINTER_PATH, "quote pointer")
    if pointer.get("schema_version") != POINTER_SCHEMA:
        raise ValueError("Invalid quote pointer schema")
    entry = pointer["quotes"][normalize_symbol(symbol)]
    ref = {"path": entry["research_package"], "sha256": entry["research_package_sha256"]}
    _, package = read_bound_json(root, ref, "registered research package")
    if package.get("symbol") != symbol:
        raise ValueError("Registered research symbol mismatch")
    return ref, package


def collect_registered_validity_scan(*, root: Path, symbol: str, review_cutoff: date,
                                    output_dir: Path) -> dict:
    """Bounded official acquisition, not event-window or materiality approval."""
    from .daily_event_observation import collect_daily_event_observation

    root = root.resolve()
    symbol = normalize_symbol(symbol)
    package_ref, package = registered_package(root, symbol)
    start = date.fromisoformat(package["point_in_time"]["research_as_of"])
    if not 0 <= (review_cutoff - start).days <= 31:
        raise ValueError("Incremental acquisition must cover at most 31 days from original model cutoff")
    output_dir = require_inside(root / "runtime", root / output_dir, "incremental acquisition")
    if output_dir.exists():
        path = output_dir / "incremental-binding.json"
        ref = {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        load_incremental_scan_binding(root=root, binding_ref=ref, symbol=symbol,
            package_path=root / package_ref["path"], package_sha256=package_ref["sha256"],
            review_cutoff=review_cutoff, today=datetime.now(timezone.utc))
        _, binding = read_bound_json(root, ref, "existing incremental binding")
        _, observation = read_bound_json(root, binding["observation_ref"], "existing observation")
        if any(sha256_file(require_inside(root, root / source["path"], "retained source")) != source["sha256"]
               for source in observation["source_bindings"]):
            raise ValueError("Retained incremental source changed; cannot reuse acquisition")
        return {"binding_ref": ref, "observation": observation, "action": "no_order"}
    observation = collect_daily_event_observation(root=root, symbol=symbol,
        issuer_name=package["name"], start=start, end=review_cutoff, output_dir=output_dir,
        retain_raw_index=True)
    # Revalidate the package after network acquisition; never bind a moved target.
    read_bound_json(root, package_ref, "original research package")
    observation_path = output_dir / "observation.json"
    binding = {"schema_version": BINDING_SCHEMA, "symbol": symbol, "action": "no_order",
        "package_ref": package_ref, "research_as_of": start.isoformat(),
        "review_cutoff": review_cutoff.isoformat(), "model_id": package["model_validity_input"]["model_id"],
        "observation_ref": {"path": observation_path.relative_to(root).as_posix(),
                            "sha256": sha256_file(observation_path)},
        "scan_ref": observation["scan_binding"], "materiality_approved": False,
        "g3_approval_granted": False, "research_cutoff_changed": False}
    path = output_dir / "incremental-binding.json"
    write_new_json(path, binding)
    return {"binding_ref": {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)},
            "observation": observation, "action": "no_order"}


def load_incremental_scan_binding(*, root: Path, binding_ref: dict, symbol: str,
        package_path: Path, package_sha256: str, review_cutoff: date, today: datetime) -> dict:
    """Resolve a caller-selected supplement, never choose a file by recency."""
    _, binding = read_bound_json(root, binding_ref, "incremental validity binding")
    expected_package = {"path": package_path.relative_to(root).as_posix(), "sha256": package_sha256}
    if (binding.get("schema_version") != BINDING_SCHEMA or binding.get("symbol") != symbol
            or binding.get("package_ref") != expected_package
            or binding.get("review_cutoff") != review_cutoff.isoformat()
            or binding.get("action") != "no_order"):
        raise ValueError("Incremental binding identity/package/window mismatch")
    _, package = read_bound_json(root, expected_package, "incremental original package")
    if (binding.get("research_as_of") != package["point_in_time"]["research_as_of"]
            or binding.get("model_id") != package["model_validity_input"]["model_id"]):
        raise ValueError("Incremental model binding mismatch")
    _, observation = read_bound_json(root, binding["observation_ref"], "incremental observation")
    scan_ref = binding["scan_ref"]
    _, payload = read_bound_json(root, scan_ref, "incremental event scan")
    scan = event_scan_from_payload(payload)
    acquired = datetime.fromisoformat(observation["acquired_at"])
    if acquired.utcoffset() is None or acquired > today or acquired != scan.retrieved_at:
        raise ValueError("Incremental observation availability mismatch")
    if (observation.get("schema_version") != "daily-event-observation-v1"
            or observation.get("symbol") != symbol or observation.get("scan_binding") != scan_ref
            or observation.get("scan_from") != binding["research_as_of"]
            or observation.get("scan_to") != review_cutoff.isoformat()
            or observation.get("pagination_complete") is not True
            or observation.get("collection_status") != "OFFICIAL_QUERY_ARCHIVED"
            or observation.get("announcement_count") != len(scan.announcements)
            or observation.get("source_bindings") != list(scan.evidence_refs)):
        raise ValueError("Incremental observation/scan provenance mismatch")
    elapsed = observation.get("full_calendar_window_elapsed") is True
    if elapsed and scan.scan_to >= acquired.astimezone(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("Incremental observation cannot assert full-day coverage at acquisition")
    if not elapsed and scan.status != "PENDING_HUMAN_REVIEW":
        raise ValueError("Snapshot-only observation cannot establish completed event-window review")
    return scan_ref


def resolve_incremental_model_validity(*, root: Path, symbol: str, binding_ref: dict,
        review_cutoff: date, today: datetime) -> "ModelValidity":
    """Replay evidence into the existing typed ModelValidity consumer contract.

    Callers can pass this object to bridge_with_quote / predecision eligibility;
    neither a saved report nor a counterfactual is trusted as a validity input.
    """
    from .research_validity_review import review_research_validity
    from ...model_validity import model_validity_from_payload

    root = root.resolve()
    package_ref, package = registered_package(root, symbol)
    package_path = root / package_ref["path"]
    scan_ref = load_incremental_scan_binding(root=root, binding_ref=binding_ref, symbol=symbol,
        package_path=package_path, package_sha256=package_ref["sha256"],
        review_cutoff=review_cutoff, today=today)
    review = review_research_validity(root=root, symbol=symbol, package_path=package_path,
        package_sha256=package_ref["sha256"], event_scan_path=root / scan_ref["path"],
        event_scan_sha256=scan_ref["sha256"], review_cutoff=review_cutoff, today=today)
    payload = review["model_validity_review"]["current"]
    original_ref = package["model_validity_input"].get("event_scan_ref")
    if original_ref and original_ref != scan_ref:
        _, original_scan = read_bound_json(root, original_ref, "original model event scan")
        prior = event_scan_from_payload(original_scan)
        if prior.status != "COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW" or prior.blockers:
            payload.update(status="UNKNOWN", material_event_found=None)
            payload["blockers"].append("ORIGINAL_EVENT_REVIEW_UNRESOLVED")
    # The shared evaluator can retain blockers alongside VALID. Do not expose
    # that label as a usable incremental price input until all reuse gates pass.
    if payload["status"] == "VALID" and review["incremental_review"]["status"] != "MODEL_VALID_AT_REVIEW_CUTOFF":
        payload.update(status="UNKNOWN", material_event_found=None)
    payload["evidence_refs"] = [*payload["evidence_refs"],
        {"id": "incremental-validity-binding-" + binding_ref["sha256"], **binding_ref}]
    return model_validity_from_payload(payload)


def register_incremental_validity_binding(root: Path, symbol: str, binding_ref: dict,
                                        review_cutoff: date, today: datetime) -> dict:
    """Atomically attach verified evidence, including pending review, not approval."""
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    pointer_path = root / POINTER_PATH
    initial_sha = sha256_file(pointer_path)
    pointer = load_json_object(pointer_path, "quote pointer")
    if pointer.get("schema_version") != POINTER_SCHEMA or pointer.get("action") != "no_order":
        raise ValueError("Invalid current quote pointer")
    validity = resolve_incremental_model_validity(root=root, symbol=symbol, binding_ref=binding_ref,
        review_cutoff=review_cutoff, today=today)
    _, binding = read_bound_json(root, binding_ref, "incremental binding")
    _, observation = read_bound_json(root, binding["observation_ref"], "incremental observation")
    for source in observation["source_bindings"]:
        path = require_inside(root, root / source["path"], "incremental source")
        if sha256_file(path) != source["sha256"]:
            raise ValueError("Cannot register changed incremental source")
    entry = pointer["quotes"][symbol]
    if binding["package_ref"] != {"path": entry["research_package"], "sha256": entry["research_package_sha256"]}:
        raise ValueError("Quote pointer changed during incremental registration")
    ref = {"path": binding_ref["path"], "sha256": binding_ref["sha256"]}
    if entry.get("incremental_validity_binding") != ref:
        entry["incremental_validity_binding"] = ref
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=pointer_path.parent,
                                         prefix=".incremental-validity-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(pointer, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            if sha256_file(pointer_path) != initial_sha:
                raise ValueError("Quote pointer changed during incremental registration")
            os.replace(temporary, pointer_path)
        finally:
            temporary.unlink(missing_ok=True)
    elif sha256_file(pointer_path) != initial_sha:
        raise ValueError("Quote pointer changed during incremental registration")
    return {"symbol": symbol, "binding_ref": ref, "pointer_sha256": sha256_file(pointer_path),
            "model_validity_status": validity.status, "action": "no_order", "g3_approval_granted": False}


def rebuild_registered_valuation(root: Path, symbol: str):
    """Compute the original pinned model via the existing in-memory application."""
    from .source_bound_inputs import verify_package_local_sources
    from ...m1_valuation_package_builder import build_descriptor
    from ...research_input import build_research_run_spec
    from ...research_application import ResearchApplicationService

    ref, package = registered_package(root, symbol)
    verify_package_local_sources(root, package)
    descriptor = build_descriptor(package, root=root)
    result = ResearchApplicationService().run_company_research(build_research_run_spec(descriptor))
    valuation = result.valuation
    if valuation is None or valuation.status == "not_ready" or any(
            value is None for value in (valuation.bear_value, valuation.base_value, valuation.bull_value)):
        raise ValueError("Original registered valuation cannot be safely reconstructed: "
                         + "; ".join(valuation.blockers if valuation else [result.status]))
    read_bound_json(root, ref, "original package after reconstruction")
    verify_package_local_sources(root, package)
    return valuation


def incremental_validity_identity(root: Path, binding_ref: dict) -> list[dict]:
    """Observe bound supplemental and reconstruction bytes, even if now invalid."""
    rows = {}

    def observe(ref):
        if not isinstance(ref, dict):
            return None
        name = ref.get("path", ref.get("local_path"))
        if not isinstance(name, str) or name in rows:
            return None
        try:
            path = require_inside(root, root / name, "incremental identity source")
            rows[name] = {"path": name, "observed_sha256": sha256_file(path)}
            return load_json_object(path, "identity input")
        except (ValueError, OSError, TypeError):
            rows.setdefault(name, {"path": name, "observed_sha256": None})
            return None

    binding = observe(binding_ref) or {}
    package = observe(binding.get("package_ref")) or {}
    observation = observe(binding.get("observation_ref")) or {}
    scan = observe(binding.get("scan_ref")) or {}
    original_quote = package.get("quote") or {}
    observe({"path": original_quote.get("bundle_path")})
    prior_scan = observe((package.get("model_validity_input") or {}).get("event_scan_ref")) or {}
    from .research_materiality_reviews import materiality_transport_identity_refs
    for transport_ref in materiality_transport_identity_refs(root=root,
            package_binding=binding.get("package_ref", {}), scan_binding=binding.get("scan_ref", {})):
        observe(transport_ref)
    for ref in [*package.get("sources", []), *observation.get("source_bindings", []),
                *scan.get("evidence_refs", []), *prior_scan.get("evidence_refs", []),
                *(ref for item in scan.get("announcements", []) for ref in item.get("evidence_refs", []))]:
        observe(ref)
    return sorted(rows.values(), key=lambda row: row["path"])

"""Read verified existing cases and produce append-only, nonpersonal replay evidence."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

from ...domain.hotspot.event_replay import replay_v1, validate_spec
from ...domain.hotspot.shadow_observation import make_shadow_baseline
from ...infrastructure.hotspot.current_price_case import load_current_price_case
from .price_action_case import project_price_action_plan


def _v1_shadow_plan(case: dict) -> dict:
    # The current projection now includes Root's new structure rule. Keep this
    # frozen baseline on the existing v1 field projection, without calling it.
    plan = project_price_action_plan({**case, "signal_state": "HISTORICAL_OBSERVATION_NOT_ADMITTED"})
    plan["signal_state"] = case["signal_state"]
    return plan


def _bound_bytes(root: Path, binding: dict, *, path_key: str = "path", hash_key: str = "sha256") -> bytes:
    name = binding[path_key]
    path = (root / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(root):
        raise ValueError("Replay binding escapes repository")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding[hash_key]:
        raise ValueError("Replay source hash mismatch: " + name)
    return raw


def _availability(case: dict, bundle: dict) -> str:
    stamps = [source["fetched_at"] for source in case["source_bindings"].values()]
    stamps.append(bundle["finished_at"])
    refs = bundle["references"][case["symbol"]]["document_refs"]
    keys = [refs["tencent"], refs["sina"], *refs["calendar_documents"]]
    stamps.extend(bundle["documents"][key]["fetched_at"] for key in keys)
    parsed = [datetime.fromisoformat(stamp) for stamp in stamps]
    if any(stamp.utcoffset() is None for stamp in parsed):
        raise ValueError("Dependency availability requires timezone")
    return max(parsed).isoformat()


def build_replay(*, root: Path, spec_path: Path, expected_sha256: str, now: datetime) -> dict:
    root = root.resolve()
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware actual clock required")
    spec_name = spec_path.as_posix()
    spec_raw = _bound_bytes(root, {"path": spec_name, "sha256": expected_sha256})
    spec = json.loads(spec_raw)
    validate_spec(spec)
    registered = datetime.fromisoformat(spec["registered_at"])
    if registered.utcoffset() is None or registered > now:
        raise ValueError("Protocol must precede calculation")
    for binding in spec["rule_bindings"]:
        _bound_bytes(root, binding)
    registry = json.loads(_bound_bytes(root, spec["selection_binding"]))
    registry_cases = {item["symbol"]: (item["case_path"], item["case_sha256"]) for item in registry["items"]}
    if len(spec["cases"]) != 5 or len({item["symbol"] for item in spec["cases"]}) != 5:
        raise ValueError("Exactly five distinct bound cases required")
    for item in spec["cases"]:
        if registry_cases.get(item["symbol"]) != (item["case_path"], item["case_sha256"]):
            raise ValueError("Frozen selection identity mismatch")
    results, baselines, availability = [], [], []
    for item in spec["cases"]:
        case = load_current_price_case(root=root, symbol=item["symbol"], case_path=Path(item["case_path"]),
                                       expected_sha256=item["case_sha256"], now=now)
        if case["market_trade_date"] != spec["end_date"]:
            raise ValueError("Case date differs from protocol end")
        quote = case["current_reference_close"]
        bundle_binding = {"path": quote["bundle_path"], "sha256": quote["bundle_sha256"]}
        bundle = json.loads(_bound_bytes(root, bundle_binding))
        available = _availability(case, bundle)
        if datetime.fromisoformat(available) > now:
            raise ValueError("Evidence not yet available")
        availability.append(available)
        case["data_available_at"] = available
        result = replay_v1(case["bars"], spec)
        results.append({
            "symbol": item["symbol"], "case_binding": item,
            "source_bindings": case["source_bindings"], "quote_bundle_binding": bundle_binding,
            "data_available_at": available,
            "historical_source_availability": "NOT_CONTEMPORANEOUSLY_ARCHIVED",
            **result,
        })
        baselines.append(make_shadow_baseline(case, _v1_shadow_plan(case), observed_at=now))
    code_paths = (
        "src/value_investment_agent/domain/hotspot/event_replay.py",
        "src/value_investment_agent/domain/hotspot/shadow_observation.py",
        "src/value_investment_agent/application/hotspot/event_replay.py",
    )
    return {
        "schema_version": "hotspot-five-case-replay-report-v1",
        "computed_at": now.isoformat(),
        "data_available_at": max(availability, key=datetime.fromisoformat),
        "spec_binding": {"path": spec_name, "sha256": expected_sha256},
        "rule_bindings": spec["rule_bindings"],
        "implementation_bindings": [{"path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
                                    for name in code_paths],
        "partitions": {key: spec[key] for key in ("start_date", "development_end", "validation_start", "end_date")},
        "results": results, "shadow_baselines": baselines,
        "shadow_scope": "READ_ONLY_BASELINE_ONLY_NOT_PRODUCTION_OR_SESSION_CREDIT",
        "elapsed_real_shadow_sessions": 0,
        "strict_pit_admitted": False, "strict_oos_admitted": False,
        "historical_classification_used": False,
        "formal_eligibility": False, "portfolio_eligibility": None,
        "performance_claim_allowed": False,
        "limitations": [
            "Current candidate selection is retrospective; no historical universe/industry reconstruction.",
            "Historical bars were acquired now; bar-close chronology is not historical source availability.",
            "Minute evidence is single provider; corporate-action-adjusted comparability is unproven.",
            "Five observed-session outcomes are overlapping, not independent trades or certified complete sessions.",
            "No dated execution limits/liquidity/costs: fills, unfilled counts, trade MAE and net returns are unknown.",
            "No v1 pullback rule or validated market regime: those performance results are null.",
            "No earlier archived Shadow judgment: today's real baseline is not an elapsed Shadow session.",
        ],
        "action": "no_order",
    }


def write_replay(*, root: Path, report: dict, directory: Path) -> dict:
    """Exclusive create: a later run must use a new suffix, never overwrite history."""
    root = root.resolve()
    directory = (root / directory).resolve()
    allowed = root / "artifacts/current/tl11-p5-20261014"
    if directory != allowed:
        raise ValueError("Replay output outside authorized artifact directory")
    outputs = {
        "replay-results-v1.json": report,
        "replay-shadow-baseline-v1.json": {
            "schema_version": "hotspot-shadow-baseline-batch-v1", "computed_at": report["computed_at"],
            "data_available_at": report["data_available_at"], "spec_binding": report["spec_binding"],
            "items": report["shadow_baselines"], "elapsed_real_shadow_sessions": 0, "action": "no_order",
        },
    }
    manifest_path = directory / "replay-manifest-v1.json"
    if manifest_path.exists() or any((directory / name).exists() for name in outputs):
        raise FileExistsError("Replay evidence already exists")
    directory.mkdir(parents=True, exist_ok=True)
    bindings = []
    for name, value in outputs.items():
        raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with (directory / name).open("xb") as stream:
            stream.write(raw)
        bindings.append({"path": (directory / name).relative_to(root).as_posix(),
                         "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    manifest = {
        "schema_version": "hotspot-event-replay-manifest-v1", "outputs": bindings,
        "spec_binding": report["spec_binding"], "rule_bindings": report["rule_bindings"],
        "implementation_bindings": report["implementation_bindings"],
        "original_bindings": [{"symbol": result["symbol"], "case": result["case_binding"],
                               "sources": result["source_bindings"], "quote_bundle": result["quote_bundle_binding"]}
                              for result in report["results"]],
        "independent_restore_complete": False, "source_storage": "EXISTING_LOCAL_IMMUTABLE_RUNTIME",
        "action": "no_order",
    }
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest

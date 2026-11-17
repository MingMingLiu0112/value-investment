"""Separate evidence for Root's new rule; original v1 replay remains frozen."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

from ...domain.hotspot.structure_replay import observe_structure_prefixes
from ...infrastructure.hotspot.current_price_case import load_current_price_case
from .event_replay import _bound_bytes, _availability


def build_baostock_structure_observation(*, root: Path, binding: dict, now: datetime) -> dict:
    """Describe a separately verified historical provider without current-price admission."""
    from ...infrastructure.hotspot.baostock_price_case import load_baostock_history
    from ...domain.hotspot.structure_replay import describe_prefix
    case = load_baostock_history(root=root, binding=binding, now=now)
    description = describe_prefix(case['bars'])
    return dict(schema_version='baostock-historical-structure-observation-v1',
        symbol=case['symbol'], computed_at=now.isoformat(),
        market_trade_date=case['bars']['daily'][-1]['time'],
        data_available_at=case['data_available_at'], source_bindings=case['source_bindings'],
        attempt_binding=case['attempt_binding'], description=description,
        scope='RETROSPECTIVE_STRUCTURE_NOT_SELECTION_HISTORY_OR_EXECUTION',
        current_pit=False, strict_pit_admitted=False, strict_oos_admitted=False,
        strategy_validation='NOT_PROVEN', formal_eligibility=False, action='no_order')


def build_structure_observation(*, root: Path, spec_path: Path, expected_sha256: str,
                                now: datetime, progress=None) -> dict:
    root = root.resolve()
    spec = json.loads(_bound_bytes(root, {"path": spec_path.as_posix(), "sha256": expected_sha256}))
    if (spec.get("schema_version") != "hotspot-structure-prefix-spec-v1"
            or spec.get("rule_version") != "hotspot-confirmed-structure-v1"
            or spec.get("action") != "no_order" or spec.get("parameters_changed") is not False):
        raise ValueError("Structure observation protocol mismatch")
    registered = datetime.fromisoformat(spec["registered_at"])
    if now.utcoffset() is None or registered.utcoffset() is None or registered > now:
        raise ValueError("Actual registered observation clock required")
    for binding in spec["rule_bindings"]:
        _bound_bytes(root, binding)
    parent = json.loads(_bound_bytes(root, spec["parent_spec_binding"]))
    for binding in parent["rule_bindings"]:
        _bound_bytes(root, binding)
    results = []
    for item in parent["cases"]:
        case = load_current_price_case(root=root, symbol=item["symbol"], case_path=Path(item["case_path"]),
                                       expected_sha256=item["case_sha256"], now=now)
        quote = case["current_reference_close"]
        bundle_binding = {"path": quote["bundle_path"], "sha256": quote["bundle_sha256"]}
        bundle = json.loads(_bound_bytes(root, bundle_binding))
        result = observe_structure_prefixes(case["bars"], parent)
        result.update(symbol=item["symbol"], case_binding=item, source_bindings=case["source_bindings"],
                      quote_bundle_binding=bundle_binding, data_available_at=_availability(case, bundle))
        results.append(result)
        if progress:
            progress(item["symbol"])
    # Guard concurrent rule edits: they must receive a separate registration.
    for binding in spec["rule_bindings"] + parent["rule_bindings"]:
        _bound_bytes(root, binding)
    names = ["src/value_investment_agent/domain/hotspot/structure_replay.py",
             "src/value_investment_agent/application/hotspot/structure_replay.py"]
    return {
        "schema_version": "hotspot-descriptive-structure-prefix-report-v1",
        "computed_at": now.isoformat(), "spec_binding": {"path": spec_path.as_posix(), "sha256": expected_sha256},
        "parent_spec_binding": spec["parent_spec_binding"], "rule_bindings": spec["rule_bindings"],
        "implementation_bindings": [{"path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
                                    for name in names],
        "results": results, "historical_classification_used": False,
        "data_available_at": max((item["data_available_at"] for item in results), key=datetime.fromisoformat),
        "scope": spec["scope"], "prospective_oos_admitted": False,
        "parameters_changed": False, "formal_eligibility": False, "portfolio_eligibility": None,
        "elapsed_real_shadow_sessions": 0, "action": "no_order",
    }


def write_structure_observation(*, root: Path, report: dict) -> dict:
    folder = root.resolve() / "artifacts/current/tl11-p5-20261014"
    target = folder / "replay-structure-results-v1.json"
    manifest_path = folder / "replay-structure-manifest-v1.json"
    if target.exists() or manifest_path.exists():
        raise FileExistsError("Structure observation already archived")
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with target.open("xb") as stream:
        stream.write(raw)
    binding = {"path": target.relative_to(root.resolve()).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    manifest = {"schema_version": "hotspot-structure-prefix-manifest-v1", "output_binding": binding,
                "spec_binding": report["spec_binding"], "parent_spec_binding": report["parent_spec_binding"],
                "rule_bindings": report["rule_bindings"], "implementation_bindings": report["implementation_bindings"],
                "original_bindings": [{"symbol": item["symbol"], "case": item["case_binding"],
                                       "sources": item["source_bindings"], "quote_bundle": item["quote_bundle_binding"]}
                                      for item in report["results"]], "action": "no_order"}
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest

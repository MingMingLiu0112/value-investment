"""Read-time official attributes from bound publication or latest-run originals.

Root entry: load_verified_security_attributes(root, symbols, now=aware_datetime).
No private policy binding is authoritative. None means unavailable evidence;
[] means no matching fresh supported securities. Returned field-level records
include symbol/company_name/exchange/security_type/industry, field_evidence,
known_at and valid_until. Acquisition is not publication or historical
classification effectiveness; cyclical/common_factors/liquidity stay UNKNOWN.
The seven-day refresh boundary is engineering freshness, not economic approval.
Current support is SZSE A shares and SSE main/STAR original exchange lists;
other instruments are missing, never coerced into a supported type.
"""
from datetime import timedelta
import json
from pathlib import Path
from zipfile import BadZipFile
from ...domain.portfolio.security_attributes import moment
from ...infrastructure.portfolio.security_attributes import replay_official_attributes
from ..product.publication_chain import load_current_chain, bound_object, STRUCTURE_ERRORS


def trading_rules_for(attributes, symbol):
    """Project rules only from observations replayed by this public adapter."""
    return next((row.get("trading_rules") for row in attributes or []
        if row["symbol"] == symbol), None) or {}


def load_verified_security_attributes(root, symbols, *, now):
    """Return partial verified facts; never use private policy paths as authority."""
    if not symbols:
        return []
    root = Path(root).resolve()
    if now.utcoffset() is None:
        return None
    candidates, verified_expired = [], False
    for loader in (_published_universe, _latest_run_universe):
        try:
            universe, binding = loader(root)
            captured = moment(universe["fetched_at"])
            source_times = [moment(source["fetched_at"]) for source in universe["sources"]
                            if source["label"] in {"SZSE_A", "SSE_1", "SSE_8"}]
            if not source_times:
                raise ValueError("No supported official originals")
            if captured > now or any(stamp > now or stamp > captured for stamp in source_times):
                raise ValueError("Official metadata collection is not known at read time")
            rows = replay_official_attributes(root, universe, binding, set(symbols), now=now)
            if now > min(source_times) + timedelta(days=7):
                verified_expired = True
                continue
            if loader is _latest_run_universe:
                # The adapter shares these reference objects with field and
                # quantity evidence; this acquisition is not a publication.
                for row in rows:
                    for ref in row["evidence_refs"]:
                        if ref.get("source_role") == "PUBLISHED_OFFICIAL_UNIVERSE":
                            ref["source_role"] = "CURRENT_OFFICIAL_UNIVERSE"
            candidates.append((min(source_times), captured, rows))
        except (*STRUCTURE_ERRORS, BadZipFile):
            continue
    if candidates:
        return max(candidates, key=lambda item: item[:2])[2]
    return [] if verified_expired else None


def _latest_run_universe(root):
    """Use only the existing latest-run manifest binding, without discovering files."""
    latest = root / '.tmp/daily-workbench-latest-run.json'
    if latest.is_symlink() or not latest.resolve().is_relative_to(root / '.tmp') or latest.stat().st_size > 512_000:
        raise ValueError('Invalid latest-run metadata path or size')
    run = json.loads(latest.read_text(encoding='utf-8-sig'))
    if (run['schema_version'] != 'daily-workbench-run-v1' or run['action'] != 'no_order'
            or run['mode'] != 'SAFE_REFRESH'):
        raise ValueError('Unknown latest-run metadata contract')
    screen = run['marketwide_screen']
    if screen['status'] != 'RESEARCH_ONLY':
        raise ValueError('No completed metadata collection')
    binding = dict(path=screen['manifest_path'].replace('\\', '/'), sha256=screen['manifest_sha256'])
    path = root / binding['path']
    if (not path.resolve().is_relative_to(root / 'runtime/daily-marketwide')
            or path.name != 'manifest.json' or path.is_symlink() or path.stat().st_size > 512_000):
        raise ValueError('Invalid metadata manifest path or size')
    manifest = bound_object(root, binding)
    summary = manifest['summary']
    if (manifest['schema_version'] != 'm2-run-manifest-v1' or summary['action'] != 'no_order'
            or summary['input_mode'] != 'LIVE_COLLECTION' or summary['rule_version'] != 'm2-evidence-screen-v3'):
        raise ValueError('Unknown metadata manifest contract')
    official = dict(manifest['files']['official'])
    official['path'] = official['path'].replace('\\', '/')
    official_path = root / official['path']
    if (official_path.resolve() != path.resolve().parent / 'official-universe.json'
            or official_path.is_symlink() or official_path.stat().st_size > 8_000_000):
        raise ValueError('Official metadata must belong to the bound run')
    return bound_object(root, official), official


def _published_universe(root):
    """Keep the original published report/receipt identity checks as fallback."""
    chain = load_current_chain(root)
    report = bound_object(root, chain["model"]["product_extensions"]["value_discovery_report"])
    if report.get("schema_version") != "value-discovery-product-v1" or report.get("action") != "no_order":
        raise ValueError("Unknown published discovery report")
    receipt = bound_object(root, report["receipt_binding"])
    refs = receipt["universe"]["evidence_refs"]
    binding = {"path": refs[0]["path"].replace("\\", "/"), "sha256": refs[0]["sha256"]}
    universe = bound_object(root, binding)
    keys = ("symbol", "name", "exchange", "board", "listed_on", "security_type", "official_industry")
    def identities(rows):
        return sorted((tuple(row[key] for key in keys) for row in rows))
    if identities(universe["records"]) != identities(receipt["universe"]["records"]):
        raise ValueError("Published universe differs from receipt")
    return universe, binding

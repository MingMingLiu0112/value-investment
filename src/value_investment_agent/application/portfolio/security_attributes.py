"""Read-time official attributes through the existing verified discovery chain.

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
from zipfile import BadZipFile
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
    try:
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
        return replay_official_attributes(root, universe, binding, set(symbols), now=now)
    except (*STRUCTURE_ERRORS, BadZipFile):
        return None

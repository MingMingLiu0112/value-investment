"""Compare replay entitlements with the retained, reviewed distribution registry.

This is input correspondence, not a new semantic PDF review or PIT admission.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from .historical_price_correspondence import require_inside, sha256_file


def _number(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("distribution amount must be numeric") from error
    if not number.is_finite() or number < 0:
        raise ValueError("distribution amount must be finite and nonnegative")
    return number


def _terms(event: dict, *, reviewed: bool) -> tuple:
    payment_key = "cash_payment_date" if reviewed else "payment_date"
    days = tuple(date.fromisoformat(event[key]).isoformat()
                 for key in ("record_date", "ex_date", payment_key))
    if not days[0] < days[1] <= days[2]:
        raise ValueError("distribution dates must follow record/ex/payment order")
    amount = _number(event["cash_per_share"])
    bonus = _number(event.get("bonus_shares_per_share") or "0")
    listing = event.get("bonus_listing_date")
    if listing is not None:
        listing = date.fromisoformat(listing).isoformat()
    if (bonus > 0 and (listing is None or listing < days[1])) or (bonus == 0 and listing):
        raise ValueError("distribution bonus listing date is inconsistent")
    if reviewed:
        if event.get("amount_basis") != "implemented_gross_entitlement":
            raise ValueError("distribution registry must use implemented gross entitlements")
        denominator = _number(event["per_shares"])
        if denominator == 0 or _number(event["cash_amount"]) / denominator != amount:
            raise ValueError("reviewed distribution per-share arithmetic mismatch")
    return (*days, amount, bonus, listing)


def verify_distribution_correspondence(
    *, root: Path, symbol: str, sessions: list, cash_events: list, references: list,
) -> dict:
    proof = dict(
        schema_version="historical-distribution-correspondence-v1",
        status="NOT_ASSESSABLE", rows=[], matched_events=0,
        scope="RETAINED_REVIEWED_GROSS_ENTITLEMENT_CORRESPONDENCE_ONLY",
        complete_historical_coverage_proven=False, pdf_semantics_reverified=False,
        tax_treatment_verified=False, historical_availability_proven=False,
        execution_admitted=False, action="no_order",
    )
    registries = [item for item in references if item.get("kind") == "reviewed_event_registry"]
    if not registries:
        return proof
    if len(registries) != 1:
        raise ValueError("exactly one reviewed distribution registry is required")
    reference = registries[0]
    path = require_inside(root, root / reference["path"], "reviewed distribution registry")
    if sha256_file(path) != reference["sha256"]:
        raise ValueError("reviewed distribution registry hash mismatch")
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("backtest_ready") is not False or not isinstance(registry.get("events"), list):
        raise ValueError("reviewed distribution registry scope is unsupported")
    start, end = sessions[0]["date"], sessions[-1]["date"]
    reviewed = {}
    bindings = [(path, reference["sha256"])]
    for event in registry["events"]:
        if event.get("symbol") != symbol:
            continue
        terms = _terms(event, reviewed=True)
        if not start <= terms[0] <= end:
            continue
        if terms[0] in reviewed:
            raise ValueError("duplicate reviewed distribution record date")
        reviewed[terms[0]] = (terms, event)
    rows = []
    seen = set()
    identities = set()
    for event in cash_events:
        terms = _terms(event, reviewed=False)
        identity = event.get("event_id")
        if not isinstance(identity, str) or not identity.strip() or identity in identities:
            raise ValueError("distribution event identity is missing or duplicated")
        identities.add(identity)
        if terms[0] in seen or terms[0] not in reviewed:
            raise ValueError("execution distribution lacks a unique reviewed event")
        seen.add(terms[0])
        expected, source_event = reviewed[terms[0]]
        if terms != expected:
            raise ValueError("execution distribution differs from reviewed terms: " + identity)
        evidence = source_event.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("reviewed distribution requires original evidence")
        for original in evidence:
            original_path = require_inside(root, root / original["path"], "distribution original")
            if sha256_file(original_path) != original["sha256"]:
                raise ValueError("distribution original hash mismatch")
            matches = [item for item in references if item.get("kind") == "distribution"
                       and require_inside(root, root / item["path"], "distribution reference") == original_path
                       and item.get("sha256") == original["sha256"]
                       and item.get("url") == original.get("url")]
            if not matches or not original.get("url") or not original.get("pages"):
                raise ValueError("reviewed distribution original is not bound by execution input")
            bindings.append((original_path, original["sha256"]))
        rows.append(dict(event_id=identity, record_date=terms[0], ex_date=terms[1],
                         payment_date=terms[2], cash_per_share=str(terms[3]),
                         bonus_shares_per_share=str(terms[4]), bonus_listing_date=terms[5],
                         evidence=evidence))
    if seen != reviewed.keys():
        raise ValueError("execution input omits a reviewed in-period distribution")
    if any(sha256_file(item) != digest for item, digest in bindings):
        raise ValueError("distribution source changed during read")
    proof.update(status="MATCH", rows=rows, matched_events=len(rows),
                 registry_binding=dict(path=reference["path"], sha256=reference["sha256"]))
    return proof

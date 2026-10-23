"""Body-verified single cash event, conditional coordinate mapping only."""
from datetime import date, datetime
from pathlib import Path

from ...domain.hotspot.cash_price_mapping import map_cash_price_coordinates
from ...infrastructure.hotspot.cash_implementation import load_cash_implementation
from ...quote_sessions import CHINA


def build_cash_event_mapping(*, root: Path, symbol: str, record_date: date,
        registry_binding: dict, now: datetime, original_protection, current_price,
        original_basis_date: date, current_basis_date: date,
        related_disclosure_bindings: tuple = ()) -> dict:
    """No synthetic owned Entry, price-source verification or window approval."""
    if (now.utcoffset() is None or type(current_basis_date) is not date
            or current_basis_date > now.astimezone(CHINA).date()):
        raise ValueError("Price date must be available at an aware cutoff")
    result = dict(schema_version="hotspot-cash-event-mapping-v1", symbol=symbol,
        evaluated_at=now.isoformat(), status="NOT_ASSESSABLE", event_proof=None, mapping=None,
        original_protection_price=str(original_protection), original_current_price=str(current_price),
        price_input_scope="REFERENCE_ONLY_NOT_VERIFIED_QUOTES_OR_OWNED_ENTRY",
        window_comparability="UNKNOWN", strategy_validation="NOT_PROVEN",
        formal_eligibility=False, position_guidance=None, action="no_order",
        blockers=["COMPLETE_OPENING_AND_EFFECTIVE_ACTION_WINDOW_NOT_PROVEN",
                  "AMENDMENT_AND_CANCELLATION_ABSENCE_NOT_PROVEN",
                  "PRICE_INPUTS_ARE_REFERENCE_ONLY"])
    try:
        proof = load_cash_implementation(root=root, symbol=symbol, record_date=record_date,
            registry_binding=registry_binding, now=now, related_disclosure_bindings=related_disclosure_bindings)
        result["event_proof"] = proof
        if proof["revision_status"] == "PENDING_LINKAGE":
            result["blockers"].append("REVISION_OR_CANCELLATION_REQUIRES_LINKAGE")
            return result
        result["mapping"] = map_cash_price_coordinates(original_protection=original_protection,
            current_price=current_price, cash_per_share=proof["terms"]["cash_per_share"],
            original_basis_date=original_basis_date, current_basis_date=current_basis_date,
            ex_date=date.fromisoformat(proof["terms"]["ex_date"]))
        result["status"] = result["mapping"]["mapping_status"]
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        result["blockers"].append("EVENT_BODY_OR_INPUT_NOT_VERIFIED")
        result["diagnostic"] = str(error)
    return result

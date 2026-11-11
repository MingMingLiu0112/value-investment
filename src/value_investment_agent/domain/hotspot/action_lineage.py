"""Explicit document linkage does not establish a complete price-basis chain."""
from datetime import date


def relate_action_documents(original: dict, amendment: dict) -> dict:
    """Consume source-parsed identities; never infer a cancellation from a title."""
    result = dict(schema_version="hotspot-action-relation-v1", relation_status="UNRESOLVED",
        original_number=original.get("announcement_number"), amendment_number=amendment.get("announcement_number"),
        original_published_date=original.get("published_date"), amendment_published_date=amendment.get("published_date"),
        original_noncash_terms_present=original.get("noncash_terms_present"),
        effect_status="UNKNOWN", cancellation_asserted_by_this_document=None,
        changed_section=amendment.get("changed_section"), requires_terms_revalidation=True,
        complete_chain_proven=False, comparison_allowed=False, action="no_order")
    references = amendment.get("references", [])
    if len(references) != 1:
        result["reason"] = "MISSING_OR_AMBIGUOUS_EXPLICIT_TARGET"
        return result
    reference = references[0]
    if (original.get("kind") != "IMPLEMENTATION" or original.get("symbol") != amendment.get("symbol")
            or not original.get("action_title") or original.get("action_title") != amendment.get("action_title")
            or reference.get("number") != original.get("announcement_number")
            or reference.get("title") != original.get("title")
            or reference.get("published_date") != original.get("published_date")):
        result["reason"] = "TARGET_IDENTITY_MISMATCH"
        return result
    if date.fromisoformat(amendment["published_date"]) < date.fromisoformat(original["published_date"]):
        result["reason"] = "AMENDMENT_PREDATES_ORIGINAL"
        return result
    result.update(relation_status="EXPLICIT_TARGET_MATCH", reason="ISSUER_NUMBER_TITLE_DATE_MATCH",
        intraday_publication_order_proven=False,
        unchanged_remainder_declared=amendment.get("unchanged_remainder_declared", False))
    if amendment.get("operative_correction") is True and amendment.get("operative_cancellation") is True:
        result["effect_status"] = "COMPOUND_CHANGE_REQUIRES_REVIEW"
    elif amendment.get("kind") == "CORRECTION" and amendment.get("operative_correction") is True:
        result.update(effect_status="CORRECTION_DECLARED", cancellation_asserted_by_this_document=False)
    elif amendment.get("kind") == "CANCELLATION" and amendment.get("operative_cancellation") is True:
        result.update(effect_status="CANCELLATION_DECLARED", cancellation_asserted_by_this_document=True)
    return result

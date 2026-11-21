"""Project the consumed share basis from an already cold-replayed V3 result."""

from datetime import date, datetime
from pathlib import Path
import re
from unicodedata import normalize

from .direct_owner_cash_agent_facts_v2 import read_parent_cash_agent_facts_v2
from .parent_cash_task_receipt_v3 import RECEIPT_SCHEMA
from ...domain.research.issuer_identity import source_identity_matches_registered_issuer


def read_task_share_anchors(*, root: Path, result: dict) -> list[dict]:
    """Return F2-shaped opening anchors from pinned originals, without alignment.

    The caller must supply the full result of replay_parent_cash_task_receipt.
    Missing supported evidence returns no anchors. Inconsistencies fail closed.
    """
    provenance = result["provenance"]
    descriptor = result["descriptor"]
    contract = descriptor["source_contract"]
    valuation = result["valuation"]
    symbol = result["symbol"]
    period = valuation["valuation_date"]
    completed_at = datetime.fromisoformat(provenance["completed_at"])
    if (result["action"] != "no_order" or result["formal_eligibility"] is not False
            or result["main_range_adopted"] is not False
            or valuation["status"] != "conditional_research_only"
            or valuation["symbol"] != symbol or descriptor["symbol"] != symbol
            or descriptor["point_in_time"]["valuation_date"] != period
            or contract["schema_version"] != RECEIPT_SCHEMA
            or any(contract.get(key) != provenance[key]
                   for key in ("task_id", "spec_binding"))
            or datetime.fromisoformat(contract["completed_at"]) != completed_at
            or completed_at.utcoffset() is None):
        raise ValueError("TASK_SHARE_REPLAY_IDENTITY_MISMATCH")

    facts = read_parent_cash_agent_facts_v2(
        root=root, spec_binding=provenance["spec_binding"], now=completed_at)
    proof = facts["ordinary_shares"]
    inputs = descriptor["facts"]
    count = proof["count"]
    if (facts["symbol"] != symbol or facts["valuation_date"] != period
            or proof["period_end"] != period or proof["unit"] != "shares"
            or proof["scope"] != "TOTAL_ISSUED_ORDINARY_SHARES"
            or not isinstance(count, str) or not re.fullmatch(r"[1-9][0-9]*", count)
            or inputs["operating_inputs"]["ordinary_shares"] != count
            or set(inputs["scenario_inputs"]) != {"bear", "base", "bull"}
            or any(row["ordinary_shares"] != count for row in inputs["scenario_inputs"].values())):
        raise ValueError("TASK_SHARE_CONSUMED_BASIS_MISMATCH")

    classification = proof["classification"]
    derivation = proof.get("derivation")
    refs = proof["source_refs"]
    if isinstance(refs, dict):
        refs = [refs]
    if classification == "DERIVED_FACT":
        if derivation != "ANNUAL_SHARE_TABLE_AND_DATED_TOTAL_NO_PREFERRED":
            return []
        day = date.fromisoformat(period)
        prefix = f"截至{day.year}年{day.month}月{day.day}日,公司股份总数为"
        dated = re.compile(re.escape(prefix) + r"([0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)股")
        matches = []
        for ref in refs:
            line = re.sub(r"\s+", "", normalize("NFKC", ref["excerpt"]))
            if match := dated.search(line):
                if match[1].replace(",", "") != count:
                    raise ValueError("TASK_SHARE_DATED_TOTAL_MISMATCH")
                matches.append(ref)
        if len(matches) > 1:
            raise ValueError("TASK_SHARE_DATED_TOTAL_AMBIGUOUS")
        refs = matches
    elif classification != "FACT":
        return []

    anchors = []
    for ref in refs:
        binding = {key: ref[key] for key in ("path", "sha256")}
        if binding not in result["source_bindings"]:
            continue
        sources = [row for row in descriptor["sources"]
                   if row.get("kind") == "official_issuer_filing"
                   and row.get("id") == ref.get("source_id")
                   and row.get("sha256") == binding["sha256"]
                   and row.get("location") == ref.get("source_url")
                   and row.get("local_path") in (None, binding["path"])]
        page = ref.get("physical_page")
        excerpt = ref.get("excerpt")
        if (len(sources) != 1 or type(page) is not int or page < 1
                or not isinstance(excerpt, str) or not excerpt.strip()
                or not source_identity_matches_registered_issuer(
                    symbol=symbol, location=ref["source_url"],
                    issuer_identity=sources[0].get("issuer_identity"))):
            continue
        anchors.append(dict(source_id=ref["source_id"], field="ordinary_shares",
            source_value=count, unit=proof["unit"], period_end=period, scope=proof["scope"],
            classification=classification, derivation=derivation, physical_page=page,
            excerpt=excerpt, binding=binding, source_url=ref["source_url"],
            available_at=ref["available_at"]))
    return anchors

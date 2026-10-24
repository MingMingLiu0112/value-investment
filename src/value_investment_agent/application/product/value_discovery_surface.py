"""Project a bound M2 receipt into non-admitted product research leads."""
from __future__ import annotations

from pathlib import Path

from value_investment_agent.m2_opportunity_discovery import discovery_receipt_from_payload

from .common import load_json_object, require_inside, sha256_file, write_new_json


def publish_value_discovery_report(*, root: Path, receipt_path: Path,
                                   receipt_sha256: str, output_path: Path) -> dict:
    report = project_value_discovery_report(root=root, receipt_path=receipt_path,
                                            receipt_sha256=receipt_sha256)
    write_new_json(output_path, report)
    return report


def project_value_discovery_report(*, root: Path, receipt_path: Path,
                                   receipt_sha256: str) -> dict:
    """Revalidate sources without writing or granting research admission."""
    receipt_path = require_inside(root / "runtime", receipt_path, "M2 receipt")
    if sha256_file(receipt_path) != receipt_sha256:
        raise ValueError("M2 receipt hash mismatch")
    receipt = discovery_receipt_from_payload(load_json_object(receipt_path, "M2 receipt"))
    if receipt.action != "no_order":
        raise ValueError("M2 receipt may not authorize orders")
    for reference in receipt.evidence_refs:
        source = require_inside(root / "runtime", root / reference.path, "M2 evidence")
        if sha256_file(source) != reference.sha256:
            raise ValueError(f"M2 evidence hash mismatch: {reference.id}")

    pool = receipt.candidate_pool()
    leads = []
    for symbol, reasons in sorted(pool.items()):
        first = reasons[0]
        leads.append({
            "symbol": symbol,
            "company_name": first.name,
            "channels": sorted({item.channel for item in reasons}),
            "screening_reasons": list(dict.fromkeys(reason for item in reasons for reason in item.reasons)),
            "data_status": "PARTIAL" if receipt.data_health.status != "COMPLETE" else first.data_status,
            "research_state": "DISCOVERED",
            "candidate_class": "LEAD",
            "quote_date": receipt.quote_date,
            "quote_date_verification": "UNVERIFIED_PROVIDER_TRADE_DATE",
            "next_required_evidence": "核验逐股行情交易日、官方财报和适用估值模型；人工审核后才可进入正式研究。",
            "evidence_ids": sorted({ref.id for item in reasons for ref in item.evidence_refs}),
        })
    leads.sort(key=lambda item: (-len(item["channels"]), item["symbol"]))
    counts = {channel: len(result.candidates) for channel, result in receipt.channel_results.items()}
    report = {
        "schema_version": "value-discovery-product-v1",
        "action": "no_order",
        "status": "RESEARCH_LEADS_ONLY",
        "run_id": receipt.run_id,
        "as_of": receipt.as_of.isoformat(),
        "quote_date_verification": "UNVERIFIED_PROVIDER_TRADE_DATE",
        "data_health": receipt.data_health.as_policy(),
        "channel_counts": counts,
        "deduplicated_lead_count": len(leads),
        "leads": leads,
        "receipt_binding": {"path": receipt_path.relative_to(root).as_posix(), "sha256": receipt_sha256},
        "semantic_content": {
            "status": "RESEARCH_LEADS_ONLY",
            "data_health": receipt.data_health.status,
            "channel_counts": counts,
            "lead_symbols": [lead["symbol"] for lead in leads],
        },
    }
    from ..discovery.scoped_screening import VERSION, OFFICIAL_VERSION, scoped_inputs
    references = {reference.id: reference for reference in receipt.evidence_refs}
    official_input = (load_json_object(root / references['official'].path, 'official scan input')
                      if 'official' in references else {})
    partial_source = (official_input.get('parser_version') == OFFICIAL_VERSION
        or official_input.get('scope') == 'OBSERVED_VENUES_ONLY_NOT_ALL_A'
        or receipt.universe.scope == 'OBSERVED_VENUES_ONLY_NOT_ALL_A')
    if partial_source and receipt.rule_version != VERSION:
        raise ValueError('Partial official input requires the scoped screening rule')
    if receipt.rule_version == VERSION:
        inputs = {key: load_json_object(root / references[key].path, 'scoped scan ' + key)
                  for key in ('official', 'tencent', 'sina')}
        _, _, scope = scoped_inputs(root=root, official_payload=inputs['official'],
            tencent_payload=inputs['tencent'], sina_payload=inputs['sina'])
        if (receipt.universe.complete or receipt.universe.scope != scope['scope']
                or receipt.data_health.universe_count != scope['observed_universe_count']
                or receipt.data_health.status != 'PARTIAL'
                or {row.symbol for row in receipt.universe.records}
                    != {row['symbol'] for row in inputs['official']['records']}):
            raise ValueError('Scoped receipt disagrees with official coverage')
        report['screening_scope'] = scope
        report['semantic_content']['screening_scope'] = scope
    return report

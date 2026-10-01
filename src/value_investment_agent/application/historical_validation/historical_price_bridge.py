"""Replay pinned historical quote observations with original event integrity gates."""
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path

from ..product.common import require_inside, load_json_object, sha256_file
from ..product.workbench import load_existing_workbench_for_presentation
from .event_evidence_audit import audit_event_evidence
from ...quote_session_conversion import quote_snapshot_from_bundle_file
from ...event_scan import event_scan_from_payload
from ...model_validity import evaluate_model_validity
from ...price_bridge import bridge_with_quote
from ...valuation_models.base import ValuationResult


def replay_historical_bridge(*, root: Path, workbench_path: Path, workbench_sha256: str,
                             quote_path: Path, quote_sha256: str, scan_path: Path,
                             scan_sha256: str, cutoffs: list[datetime]) -> dict:
    payload = load_existing_workbench_for_presentation(root=root, path=workbench_path,
                                                       expected_sha256=workbench_sha256)
    raw = dict(payload['research']['valuation'])
    raw['valuation_date'] = date.fromisoformat(raw['valuation_date'])
    for key in ('bear_value', 'base_value', 'bull_value'):
        raw[key] = None if raw[key] is None else Decimal(raw[key])
    valuation = ValuationResult(**raw)
    research = payload['research']
    result_known_at = max(datetime.fromisoformat(value) for value in (
        payload['generated_at'], research['dependency_view']['observed_at'],
        *(record['observed_at'] for record in research['source_records'])))
    if result_known_at.utcoffset() is None:
        raise ValueError('research observation requires timezone')
    quote_path = require_inside(root, quote_path, 'historical quote')
    if sha256_file(quote_path) != quote_sha256:
        raise ValueError('historical quote hash mismatch')
    bundle = load_json_object(quote_path, 'historical quote')
    observed_at = datetime.fromisoformat(bundle['finished_at'])
    if observed_at.utcoffset() is None:
        raise ValueError('quote observation requires timezone')
    quote = quote_snapshot_from_bundle_file(quote_path, root, symbol=valuation.symbol,
        ref_id='historical-close', expected_sha256=quote_sha256)
    audit = audit_event_evidence(root=root, path=scan_path,
                                expected_sha256=scan_sha256, symbol=valuation.symbol)
    bridge = None
    validity = None
    if audit['evidence_integrity_verified']:
        scan = event_scan_from_payload(load_json_object(scan_path, 'event scan'))
        validity = evaluate_model_validity(model_id=valuation.model_version,
            symbol=valuation.symbol, model_as_of=valuation.valuation_date,
            valid_from=scan.validity_from, quote_date=quote.quote_date,
            events=[], event_scan_evidence_refs=[], event_scan=scan)
        bridge = bridge_with_quote(valuation, validity, quote)
    rows = []
    for cutoff in cutoffs:
        if cutoff.utcoffset() is None:
            raise ValueError('historical bridge cutoff requires timezone')
        observed = cutoff >= observed_at
        valuation_observed = cutoff >= result_known_at
        blockers = []
        if not observed:
            blockers.append('Quote bundle was captured after the decision cutoff.')
        if not valuation_observed:
            blockers.append('Valuation result was produced after the decision cutoff.')
        if not audit['evidence_integrity_verified']:
            blockers.append('Event original evidence failed integrity verification.')
        blockers.extend(quote.blockers)
        if validity is not None:
            blockers.extend(validity.blockers)
        rows.append(dict(cutoff=cutoff.isoformat(), quote_observed=observed,
            valuation_observed=valuation_observed,
            valuation=payload['research']['valuation'] if valuation_observed else None,
            quote=json.loads(quote.to_json()) if observed else None,
            bridge=json.loads(bridge.to_json()) if observed and valuation_observed and bridge is not None else None,
            blockers=blockers, suggested_state='NOT_READY', position_guidance=None,
            action='no_order', orders=[], fills=[]))
    return dict(schema_version='historical-price-bridge-replay-v1', symbol=valuation.symbol,
        scope='RETAINED_HISTORICAL_OBSERVATIONS_NOT_STRATEGY_VALIDATION',
        quote_observed_at=observed_at.isoformat(), quote_sha256=quote_sha256,
        valuation_observed_at=result_known_at.isoformat(),
        valuation_reference_sha256=workbench_sha256, event_evidence_audit=audit,
        rows=rows, strict_pit_admitted=False, current_research_admitted=False,
        historical_execution_validated=False, action='no_order')

"""Separate retrospective financial-input reconstruction from strict PIT admission."""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from ..product.common import require_inside, load_json_object, sha256_file
from ..product.workbench import load_existing_workbench_for_presentation
from ..product.existing_valuation import replay_residual_income_input
from ...valuation_models.base import ValuationResult
from ...infrastructure.filings.disclosure_availability import indexed_disclosure_availability


def reconstruct_equity_inputs(*, root: Path, workbench_path: Path, workbench_sha256: str,
                              arithmetic_path: Path, arithmetic_sha256: str,
                              index_path: Path, index_sha256: str, cutoffs: list[datetime]) -> dict:
    payload = load_existing_workbench_for_presentation(root=root, path=workbench_path,
                                                       expected_sha256=workbench_sha256)
    raw = dict(payload['research']['valuation'])
    raw['valuation_date'] = date.fromisoformat(raw['valuation_date'])
    for key in ('bear_value', 'base_value', 'bull_value'):
        raw[key] = None if raw[key] is None else Decimal(raw[key])
    valuation = ValuationResult(**raw)
    arithmetic = replay_residual_income_input(root=root, path=arithmetic_path,
                                              expected_sha256=arithmetic_sha256, valuation=valuation)
    review = arithmetic.get('primary_numeric_review')
    if review is None:
        raise ValueError('reconstruction requires primary numeric review')
    index_path = require_inside(root, index_path, 'disclosure index')
    if sha256_file(index_path) != index_sha256:
        raise ValueError('disclosure index hash mismatch')
    index = load_json_object(index_path, 'disclosure index')
    facts = []
    for fact in review['facts']:
        availability = indexed_disclosure_availability(index, symbol=valuation.symbol,
            source_id=fact['source_id'], source_url=fact['source_url'])
        facts.append(dict(fact_name=fact['fact_name'], value=fact['value'], unit=fact['unit'],
            period=fact['period'], source_id=fact['source_id'], source_file_hash=fact['source_file_hash'],
            physical_page=fact['physical_page'], original_review_available_at=fact['available_at'],
            reconstructed_availability=availability,
            source_excerpt_semantics_verified=False))
    points = []
    for cutoff in cutoffs:
        if cutoff.utcoffset() is None:
            raise ValueError('reconstruction cutoff requires timezone')
        eligible = [fact for fact in facts
                    if datetime.fromisoformat(fact['reconstructed_availability']['available_from']) <= cutoff]
        points.append(dict(cutoff=cutoff.isoformat(), eligible_facts=eligible,
                           missing_facts=[fact['fact_name'] for fact in facts if fact not in eligible]))
    return dict(schema_version='reconstructed-equity-input-v1', symbol=valuation.symbol,
        scope='RETROSPECTIVE_FINANCIAL_INPUT_RECONSTRUCTION_ONLY',
        reconstructed_at=datetime.now(timezone.utc).isoformat(),
        arithmetic_input_sha256=arithmetic_sha256, index_sha256=index_sha256,
        assumptions_basis='PINNED_RECONSTRUCTED_SCENARIOS_NOT_CONTEMPORANEOUS_FORECAST',
        assumptions_historically_registered=False, arithmetic_match=arithmetic['status'],
        facts=facts, cutoffs=points, strict_pit_admitted=False, financial_gate_admitted=False,
        current_model_admitted=False, performance_claim_allowed=False, action='no_order')

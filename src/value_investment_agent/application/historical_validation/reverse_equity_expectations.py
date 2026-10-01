"""Bind a retrospective expectation calculation to actual pinned inputs."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..product.common import require_inside, load_json_object, sha256_file
from ..product.workbench import load_existing_workbench_for_presentation
from ..product.existing_valuation import replay_residual_income_input
from ...valuation_models.base import ValuationResult
from ...quote_session_conversion import quote_snapshot_from_bundle_file
from ...domain.valuation.residual_income_reverse import implied_terminal_roe


def reverse_equity_expectations(*, root: Path, workbench_path: Path, workbench_sha256: str,
                               arithmetic_path: Path, arithmetic_sha256: str,
                               quote_path: Path, quote_sha256: str) -> dict:
    workbench = load_existing_workbench_for_presentation(root=root, path=workbench_path,
                                                        expected_sha256=workbench_sha256)
    raw = dict(workbench['research']['valuation'])
    raw['valuation_date'] = date.fromisoformat(raw['valuation_date'])
    for key in ('bear_value', 'base_value', 'bull_value'):
        raw[key] = None if raw[key] is None else Decimal(raw[key])
    valuation = ValuationResult(**raw)
    replay_residual_income_input(root=root, path=arithmetic_path,
                                expected_sha256=arithmetic_sha256, valuation=valuation)
    packet = load_json_object(require_inside(root, arithmetic_path, 'arithmetic input'), 'arithmetic input')
    if sha256_file(arithmetic_path) != arithmetic_sha256:
        raise ValueError('reverse arithmetic input changed during read')
    quote = quote_snapshot_from_bundle_file(quote_path, root, symbol=valuation.symbol,
        ref_id='reverse-equity-historical-quote', expected_sha256=quote_sha256)
    if quote.status != 'verified_close':
        raise ValueError('reverse expectations require an existing verified quote')
    rows = [dict(scenario=name, **implied_terminal_roe(start_book=Decimal(packet['start_book_equity']),
        shares=Decimal(packet['ordinary_shares']), price=quote.current_price, configuration=config))
        for name, config in packet['scenarios'].items()]
    return dict(schema_version='retrospective-equity-expectations-v1', symbol=valuation.symbol,
        scope='RETROSPECTIVE_CONDITIONAL_EXPECTATIONS_NOT_CURRENT_ADVICE',
        valuation_date=valuation.valuation_date.isoformat(), quote_date=quote.quote_date.isoformat(),
        workbench_sha256=workbench_sha256, arithmetic_input_sha256=arithmetic_sha256,
        quote_bundle_sha256=quote_sha256, scenarios=rows, action='no_order',
        assumptions_contemporaneously_registered=False, strict_pit_admitted=False,
        current_model_admitted=False, performance_claim_allowed=False,
        limitation='Historical price and retrospective scenarios are compared outside the observed cutoff rows; no backdated decision or approved expectations gap.')

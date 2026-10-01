"""Describe already pinned valuation arithmetic without approving assumptions."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from .common import load_json_object, require_inside, sha256_file
from .workbench import load_existing_workbench_for_presentation
from .existing_valuation import replay_residual_income_input
from ...valuation_models.base import ValuationResult
from ...valuation_models.residual_income import scenario_value


def describe_valuation_drivers(*, root: Path, workbench_path: Path, workbench_sha256: str,
                              arithmetic_path: Path, arithmetic_sha256: str) -> dict:
    workbench = load_existing_workbench_for_presentation(root=root, path=workbench_path,
        expected_sha256=workbench_sha256)
    raw = dict(workbench['research']['valuation'])
    raw['valuation_date'] = date.fromisoformat(raw['valuation_date'])
    for key in ('bear_value', 'base_value', 'bull_value'):
        raw[key] = None if raw[key] is None else Decimal(raw[key])
    valuation = ValuationResult(**raw)
    replay_residual_income_input(root=root, path=arithmetic_path, expected_sha256=arithmetic_sha256, valuation=valuation)
    path = require_inside(root, arithmetic_path, 'valuation drivers')
    packet = load_json_object(path, 'valuation drivers')
    if sha256_file(path) != arithmetic_sha256:
        raise ValueError('valuation driver input changed during read')
    book, shares = Decimal(packet['start_book_equity']), Decimal(packet['ordinary_shares'])
    scenarios = []
    for name in ('bear', 'base', 'bull'):
        inputs = packet['scenarios'][name]
        result = scenario_value(book, shares, Decimal(inputs['cost_of_equity']), inputs)
        scenarios.append(dict(scenario=name, assumptions=inputs, opening_book_per_share_cny=str(book / shares),
            explicit_residual_per_share_cny=str(Decimal(result['present_value_explicit_residual_income_cny']) / shares),
            terminal_residual_per_share_cny=str(Decimal(result['present_value_terminal_residual_income_cny']) / shares),
            value_per_share_cny=result['conditional_value_per_2025_issued_share_cny'],
            terminal_residual_contribution_ratio=result['terminal_residual_contribution_ratio'],
            forecast_years=result['forecast_years'], dividend_crosscheck_difference_cny=result['dividend_crosscheck_difference_cny']))
    return dict(schema_version='source-bound-valuation-drivers-v1', symbol=valuation.symbol,
        valuation_date=valuation.valuation_date.isoformat(), arithmetic_sha256=arithmetic_sha256,
        scenarios=scenarios, assumptions_approved=False, strict_pit_admitted=False,
        dividend_capacity_proven=False, action='no_order')

"""Describe already pinned valuation arithmetic without approving assumptions."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from itertools import product
from .common import load_json_object, require_inside, sha256_file
from .workbench import load_existing_workbench_for_presentation
from .existing_valuation import replay_residual_income_input
from ...valuation_models.base import ValuationResult
from ...valuation_models.residual_income import scenario_value


def replay_bound_sensitivity_grid(*, root: Path, packet: dict) -> list:
    reviews = []
    for binding in packet['source_bindings']:
        path = require_inside(root, root / binding['path'], 'sensitivity source')
        if path.suffix.lower() != '.json':
            continue
        source = load_json_object(path, 'sensitivity source')
        if source.get('schema_version') != 'valuation-readiness-review-v2':
            continue
        if sha256_file(path) != binding['sha256']:
            raise ValueError('sensitivity source hash mismatch')
        reviews.append((binding, source))
    if not reviews:
        return []
    if len(reviews) != 1:
        raise ValueError('sensitivity requires one unambiguous registered grid')
    binding, review = reviews[0]
    if (review['symbol'] != packet['symbol']
            or review['valuation_basis_as_of'] != packet['valuation_date']
            or review['model']['model_version'] != packet['model_version']):
        raise ValueError('sensitivity model identity mismatch')
    assumptions = review['model']['assumptions']
    book, shares = Decimal(packet['start_book_equity']), Decimal(packet['ordinary_shares'])
    if (book != Decimal(assumptions['opening_parent_equity_cny'])
            or shares != Decimal(assumptions['ordinary_shares_as_of_' + packet['valuation_date'].replace('-', '_')])):
        raise ValueError('sensitivity equity basis mismatch')
    for name, inputs in packet['scenarios'].items():
        if ([Decimal(str(value)) / 100 for value in assumptions['forecast_roe_pct'][name]]
                != [Decimal(value) for value in inputs['forecast_roe']]
                or Decimal(str(assumptions['terminal_roe_pct'][name])) / 100 != Decimal(inputs['terminal_roe'])
                or Decimal(str(assumptions['explicit_period_retention_pct'])) / 100 != Decimal(inputs['retention'])):
            raise ValueError('sensitivity scenario assumptions mismatch')
    expected = set(product(packet['scenarios'], assumptions['cost_of_equity_sensitivity_pct'],
                           assumptions['terminal_growth_sensitivity_pct']))
    rows, seen = [], set()
    for row in review['model']['sensitivity_grid']:
        key = (row['scenario'], row['cost_of_equity_pct'], row['terminal_growth_pct'])
        if key not in expected or key in seen:
            raise ValueError('sensitivity grid contains unexpected or duplicate cell')
        seen.add(key)
        inputs = dict(packet['scenarios'][row['scenario']],
                      terminal_growth=str(Decimal(str(row['terminal_growth_pct'])) / 100))
        if Decimal(str(row['terminal_roe_pct'])) / 100 != Decimal(inputs['terminal_roe']):
            raise ValueError('sensitivity terminal ROE mismatch')
        computed = scenario_value(book, shares, Decimal(str(row['cost_of_equity_pct'])) / 100, inputs)
        value = Decimal(computed['conditional_value_per_2025_issued_share_cny'])
        recorded = Decimal(row['per_share_cny'])
        if not recorded.is_finite() or value.quantize(Decimal(1).scaleb(recorded.as_tuple().exponent)) != recorded:
            raise ValueError('sensitivity arithmetic differs from registered grid')
        rows.append(dict(row, recomputed_per_share_cny=str(value), source_path=binding['path'],
                         source_sha256=binding['sha256'], arithmetic_match=True))
    if seen != expected:
        raise ValueError('sensitivity grid is incomplete')
    if sha256_file(require_inside(root, root / binding['path'], 'sensitivity source')) != binding['sha256']:
        raise ValueError('sensitivity source changed during replay')
    return rows


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
        scenarios=scenarios, sensitivity_grid=replay_bound_sensitivity_grid(root=root, packet=packet),
        assumptions_approved=False, strict_pit_admitted=False,
        dividend_capacity_proven=False, action='no_order')

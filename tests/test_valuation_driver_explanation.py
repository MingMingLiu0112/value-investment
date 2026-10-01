from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import pytest
from test_bound_valuation_step import result
from value_investment_agent.application.product import valuation_drivers as service
from value_investment_agent.domain.research.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_models.residual_income import MODEL_VERSION


def test_driver_decomposition_uses_reconciled_existing_model_not_market_price(tmp_path, monkeypatch):
    valuation = replace(result(), model_type='residual_income_or_equity_value', model_version=MODEL_VERSION,
        bear_value=Decimal('10'), base_value=Decimal('10'), bull_value=Decimal('10'))
    source = tmp_path / 'original.json'
    source.write_text('{}', encoding='utf-8')
    packet = dict(schema_version='residual-income-arithmetic-replay-input-v1', action='no_order',
        symbol=valuation.symbol, model_version=MODEL_VERSION, input_basis='reconstructed_from_pinned_review',
        valuation_result_sha256=valuation_result_sha256(valuation), valuation_date=valuation.valuation_date.isoformat(),
        source_bindings=[dict(path=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest())],
        start_book_equity='100', ordinary_shares='10', scenarios={key:dict(cost_of_equity='0.1',
            forecast_roe=['0.1'], terminal_roe='0.1', terminal_growth='0', retention='0') for key in ('bear','base','bull')})
    path = tmp_path / 'arithmetic.json'
    path.write_text(json.dumps(packet), encoding='utf-8')
    monkeypatch.setattr(service, 'load_existing_workbench_for_presentation', lambda **k:
        {'research': {'valuation': json.loads(valuation.to_json())}})
    args = dict(root=tmp_path, workbench_path=tmp_path/'workbench.json', workbench_sha256='a'*64,
                arithmetic_path=path, arithmetic_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    output = service.describe_valuation_drivers(**args)
    for row in output['scenarios']:
        assert Decimal(row['opening_book_per_share_cny']) + Decimal(row['explicit_residual_per_share_cny']) + Decimal(row['terminal_residual_per_share_cny']) == Decimal(row['value_per_share_cny'])
        assert Decimal(row['terminal_residual_contribution_ratio']) == 0
    assert not output['assumptions_approved']
    assert not output['dividend_capacity_proven']
    assert 'current_price' not in output
    source.write_text('{"changed":true}', encoding='utf-8')
    with pytest.raises(ValueError, match='source hash'): service.describe_valuation_drivers(**args)

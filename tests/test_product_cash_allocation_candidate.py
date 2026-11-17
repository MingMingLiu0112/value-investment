"""TEST_ONLY evidence seam, actual cash/model/descriptor/review consumption."""
import json
from decimal import Decimal as D

from test_product_continuation_candidate import case, prepare, verify, store
from value_investment_agent.application.research import shareholder_cash_evidence
from value_investment_agent.application.research.shareholder_cash_allocation import allocate_inputs
from value_investment_agent.application.product.common import sha256_file


def allocation():
    return dict(schema_version='source-bound-cash-allocation-policy-v2', rationale='TEST_ONLY explicit timing, not a disclosed date',
        timing_identity='UNAPPROVED_CALL_SCHEDULE_NOT_DISCLOSED_DATES',
        fund_call_weights=['1']+['0']*9, digital_call_weights=['.5','.5']+['0']*8,
        net_maintenance_gap_fraction='0.5', requested_payout_ratios=['.9']*10)


def test_cash_limited_candidate_uses_actual_annual_retention_and_model(case, monkeypatch):
    args, _ = case
    root = args['root']
    parent = json.loads((root/args['source_candidate_binding']['path']).read_bytes())
    old = json.loads((root/parent['native_cash_ledger_binding']['path']).read_bytes())
    fund = old['history']['known_uncalled_fund_commitment']['amount_cny']
    ref = store(root, 'runtime/TEST_ONLY-allocation-evidence.json', dict(fund=fund, digital='100'))
    monkeypatch.setattr(shareholder_cash_evidence, 'load_shareholder_cash_evidence',
        lambda *a: dict(status='SOURCE_REPLAYED_PARTIAL_ECONOMIC_OBSERVATIONS', source_bindings=[ref],
            observations=dict(fund_uncalled_total_cny=dict(value=fund), digital_remaining_cny=dict(value='100'))))
    ppath = root/args['continuation_policy_binding']['path']
    policy = json.loads(ppath.read_bytes())
    policy['cash_allocation'] = allocation()
    args['continuation_policy_binding'] = store(root, 'runtime/TEST_ONLY-allocation-policy.json', policy)
    candidate = prepare(case)
    assert verify(case, candidate) == candidate
    assert candidate['input_mode'] == 'SOURCE_NATIVE_CASH_CONSTRAINED_TEN_YEAR_V2'
    assert candidate['candidate_valuation']['model_version'] == 'residual-income-equity-path-v2'
    ledger = json.loads((args['output_dir']/'cash-ledger.json').read_bytes())
    rows = ledger['centers']['base']['cash_rows']
    assert len(rows) == 10
    assert any(D(r['distribution_cny']) < D(r['requested_distribution_cny']) for r in rows)
    package = json.loads((args['output_dir']/'package.json').read_bytes())
    assert 'retention' not in package['facts']['scenario_inputs']['base']
    assert len(package['facts']['scenario_inputs']['base']['forecast_retentions']) == 10
    assert any(a['name']=='forecast_retentions_9' for a in package['assumptions']['assumptions'])
    assert candidate['position_guidance'] is None and candidate['execution_status'] == 'NO_ACTION'
    assert not candidate['price_admitted'] and not candidate['research_admitted']
    from value_investment_agent.application.product.pending_candidate_supplement import load_current_pending_candidate_supplement
    from value_investment_agent.application.product.economic_review_materials import project_product_continuation_review
    from datetime import datetime, timezone
    store(root, 'config/current-research-drafts.json', dict(schema_version='current-research-drafts-v1',
        action='no_order', drafts={}, pending_candidates={candidate['symbol']:dict(
            path='runtime/center/candidate.json', sha256=sha256_file(args['output_dir']/'candidate.json'))}))
    supplement = load_current_pending_candidate_supplement(root=root, symbol=candidate['symbol'])
    view = project_product_continuation_review(root=root, supplement=supplement, now=datetime.now(timezone.utc))
    assert view['cash_allocation']['observations']['digital_remaining_cny']['value']=='100'
    assert view['price_draft'] is None and not view['primary_approved']


def test_commitment_calls_reduce_remaining_balance_once():
    from test_product_continuation_cash_path_v1 import inputs
    from value_investment_agent.domain.valuation.cash_constrained_product_path_v2 import build_cash_constrained_product_path
    arg = inputs.__wrapped__()
    arg['opening_state']['uncalled_fund_commitment_cny'] = '60'
    p = allocation()
    p['net_maintenance_gap_fraction'] = '0'
    opening, cap, dist, context = allocate_inputs(policy=p, evidence_amounts=dict(
        fund_uncalled_total_cny='60', digital_remaining_cny='4'), opening=arg['opening_state'],
        capital=arg['capital_cash_rows'], distribution=arg['distribution_rows'], first_profit='600.7')
    assert opening['selected_project_budget_cny']=='4'
    assert cap[0]['fund_call_cny']=='60' and cap[0]['project_cash_cny']=='2.0'
    assert cap[1]['fund_call_cny']=='0' and cap[1]['project_cash_cny']=='2.0'
    out = build_cash_constrained_product_path(**{**arg, 'opening_state':opening,
        'capital_cash_rows':cap, 'distribution_rows':dist}, allocation_policy=dict(
        schema_version='cash-constrained-product-path-v2', rationale='TEST_ONLY no double debit',
        capacity_scope='CONDITIONAL_OWNER_EQUIVALENT_NOT_LEGAL_PARENT_CAPACITY'))
    assert out['valuation']['usable']
    assert out['cash_rows'][0]['closing_uncalled_fund_commitment_cny']=='0'
    assert D(out['cash_rows'][1]['closing_selected_project_budget_cny'])==0


def test_annual_candidate_research_and_economic_consumers(case, monkeypatch):
    """TEST_ONLY public evidence; real candidate, analysis and economic consumers."""
    from dataclasses import replace
    from datetime import datetime, timezone
    from decimal import localcontext

    from value_investment_agent.application.research.value_research_analysis import (
        load_current_value_research_analysis,
    )
    from value_investment_agent.application.research.value_economic_assessment import (
        load_current_value_economic_assessment,
    )
    from value_investment_agent.m1_valuation_package_builder import build_quality_facts
    from value_investment_agent.valuation_models.residual_income_path_v2 import scenario_calculation

    args, _ = case
    root, target = args['root'], args['output_dir']
    parent = json.loads((root / args['source_candidate_binding']['path']).read_bytes())
    ledger = json.loads((root / parent['native_cash_ledger_binding']['path']).read_bytes())
    fund = ledger['history']['known_uncalled_fund_commitment']['amount_cny']
    ref = store(root, 'runtime/TEST_ONLY-consumer-allocation-evidence.json',
                dict(fund=fund, digital='100'))
    monkeypatch.setattr(shareholder_cash_evidence, 'load_shareholder_cash_evidence',
        lambda *a: dict(status='SOURCE_REPLAYED_PARTIAL_ECONOMIC_OBSERVATIONS',
            source_bindings=[ref], observations=dict(
                fund_uncalled_total_cny=dict(value=fund),
                digital_remaining_cny=dict(value='100'))))
    policy = json.loads((root / args['continuation_policy_binding']['path']).read_bytes())
    policy['cash_allocation'] = allocation()
    args['continuation_policy_binding'] = store(
        root, 'runtime/TEST_ONLY-consumer-allocation-policy.json', policy)
    candidate = prepare(case)
    store(root, 'config/current-research-drafts.json',
        dict(schema_version='current-research-drafts-v1', action='no_order', drafts={},
             pending_candidates={candidate['symbol']: dict(
                 path=(target / 'candidate.json').relative_to(root).as_posix(),
                 sha256=sha256_file(target / 'candidate.json'))}))
    package = json.loads((target / 'package.json').read_bytes())
    typed_facts = build_quality_facts(package['facts'])
    base = typed_facts.scenario_inputs['base']
    assert len(base.forecast_retentions) == 10
    assert len(set(base.forecast_retentions)) > 1
    assert all('retention' not in row and row['retention_contract'] == 'annual-retention-v2'
               for row in package['facts']['scenario_inputs'].values())
    before = {p.relative_to(root).as_posix(): sha256_file(p)
              for p in root.rglob('*') if p.is_file()}
    now = datetime.now(timezone.utc)

    analysis = load_current_value_research_analysis(root=root, symbol=candidate['symbol'], now=now)
    assert analysis['status'] == 'CONDITIONAL_ANALYSIS_VERIFIED'
    assert analysis['valuation'] == candidate['candidate_valuation']
    assert analysis['valuation']['model_version'] == 'residual-income-equity-path-v2'
    assert analysis['valuation']['status'] == 'conditional_research_only'
    retention_rows = [row for row in analysis['sensitivity']['rows']
                      if row['field_path'].startswith('forecast_retentions.')]
    assert len(retention_rows) == 10
    assert {row['field_path'] for row in retention_rows} == {
        f'forecast_retentions.{index}' for index in range(10)}
    assumptions = {row['name']: row for row in package['assumptions']['assumptions']}
    for row in retention_rows:
        index = int(row['field_path'].split('.')[1])
        assert {point['bound'] for point in row['points']} == {'bear', 'base', 'bull'}
        for point in row['points']:
            assert point['status'] == 'ARITHMETIC_COMPLETE'
            expected_input = D(assumptions[row['assumption_name']][point['bound']])
            assert D(point['input_value']) == expected_input
            retentions = list(base.forecast_retentions)
            retentions[index] = expected_input
            expected = scenario_calculation(
                typed_facts, replace(base, forecast_retentions=tuple(retentions)))
            assert abs(D(point['per_share_value']) - D(expected['per_share_value'])) < D('1e-20')

    economic = load_current_value_economic_assessment(root=root, symbol=candidate['symbol'], now=now)
    assert economic['status'] == 'ECONOMIC_DIAGNOSTICS_COMPLETE_PRIMARY_NOT_ESTABLISHED'
    assert economic['sensitivity'] == analysis['sensitivity']
    assert len(economic['scenarios']) == 3
    # Independent clean-surplus recurrence exercises every year's retention.
    with localcontext() as context:
        context.prec = 48
        for row in economic['scenarios']:
            scenario = typed_facts.scenario_inputs[row['scenario']]
            book = typed_facts.operating_inputs['start_book_equity']
            for year, (roe, retention) in enumerate(zip(
                    scenario.forecast_roes, scenario.forecast_retentions, strict=True)):
                profit = book * roe
                dividend = profit * (1 - retention)
                if year == 0:
                    assert D(row['first_year_profit_cny']) == profit
                    assert D(row['first_year_dividend_assumption_cny']) == dividend
                    assert D(row['first_year_payout_ratio']) == 1 - retention
                book += profit * retention
            assert D(row['final_explicit_profit_cny']) == profit
            assert row['explicit_years'] == 10
            assert abs(D(row['dividend_ri_reconciliation_cny'])) < D('.01')
    for result in (analysis, economic):
        assert result['action'] == 'no_order'
        assert not result['approval_changed']
        assert not result['strategy_admitted'] and not result['action_admitted']
        assert not result['economic_assumptions_reviewed']
    assert not analysis['price_comparison_eligible']
    assert not economic['primary_valuation_usable']
    assert economic['sustainable_distribution_status'] == 'NOT_ESTABLISHED'
    assert candidate['status'] == 'PENDING_REVIEW'
    assert not candidate['research_admitted'] and not candidate['price_admitted']
    assert candidate['execution_status'] == 'NO_ACTION' and candidate['position_guidance'] is None
    assert before == {p.relative_to(root).as_posix(): sha256_file(p)
                      for p in root.rglob('*') if p.is_file()}

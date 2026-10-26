"""Source-bound finite-return/cash sensitivities beside, not replacing, a candidate."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path

from ...domain.valuation.finite_advantage_cash_path_v1 import build_finite_advantage_cash_path, SCOPE
from ...domain.valuation.product_continuation_cash_path_v1 import build_product_continuation_cash_path
from ...m1_valuation_package_builder import build_descriptor
from ..product.common import require_inside, sha256_file
from ..product.incremental_validity import read_bound_json
from ..product.pending_candidate_supplement import load_current_pending_candidate_supplement
from ..product.source_native_candidate_v2 import verify_source_native_candidate

_CODE_ROOT = Path(__file__).resolve().parents[4]
_IMPLEMENTATIONS = tuple(dict(path=name, sha256=sha256_file(_CODE_ROOT/name)) for name in (
    'src/value_investment_agent/application/research/finite_advantage_research.py',
    'src/value_investment_agent/domain/valuation/finite_advantage_cash_path_v1.py',
    'src/value_investment_agent/domain/valuation/product_continuation_cash_path_v1.py',
    'src/value_investment_agent/application/research/product_operating_research.py',
    'src/value_investment_agent/application/research/operating_earnings_bridge.py',
    'src/value_investment_agent/infrastructure/filings/operating_erosion_sources.py',
    'src/value_investment_agent/domain/valuation/operating_product_paths.py',
))

def _capital(year, project, fund, gap, rationale):
    return dict(year=year, scope=SCOPE, rationale=rationale,
        funding_treatment='NET_NEEDS_DEDUCTED_HERE_NOT_IN_UPSTREAM_MAPPING',
        maintenance_basis='EXPLICIT_NET_GAP_ASSUMPTION', net_maintenance_gap_cny=str(gap),
        project_cash_cny=str(project), maintenance_project_overlap_cny='0',
        operating_wc_increase_cny='0', fund_call_cny=str(fund),
        other_noncash_adjustment_cny='0', net_financing_cny='0')


def _distribution(year, policy, *, persistent, terminal=False):
    return dict(year=year, payout_ratio='1' if terminal else '0.90',
        newly_withheld_fraction=(policy['persistent_withheld_challenge'] if persistent else
                                 ('0.10' if year == 1 else '0')),
        release_fraction='0' if terminal or persistent or year != 2 else '1',
        reserve_transfer_fraction='0' if terminal else '0.10',
        reserve_policy_rationale=policy['terminal_distribution_rationale'] if terminal else policy['capacity_rationale'],
        capacity_mapping_rationale=policy['cash_mapping_rationale'])


def _opening_state(case, history, facts):
    return dict(scope=SCOPE, currency='CNY',
        book_equity_cny=str(facts.operating_inputs['start_book_equity']),
        ordinary_shares=str(facts.operating_inputs['ordinary_shares']),
        cash_cny=history['ttm']['cash_end'], unremitted_assets_cny='0',
        distribution_capacity_cny=history['ttm']['parent_retained_profit_end'],
        cash_floor_cny=case['cash_floor'],
        uncalled_fund_commitment_cny=history['known_uncalled_fund_commitment']['amount_cny'],
        selected_project_budget_cny=case['project_budget'])


def _contribution_reference(*, root, package):
    from .operating_earnings_bridge import REQUIRED, COSTS, GAINS, research_from_retained_sources
    from ...infrastructure.filings.operating_erosion_sources import read_operating_erosion_sources
    # Blank impairment rows are not asserted zero; the bridge retains any residual.
    fields = (REQUIRED | set(COSTS) | set(GAINS)) - {'asset_impairment'}
    inputs = read_operating_erosion_sources(root=root, symbol=package['symbol'], sources=package['sources'], fields=fields)
    bridge = research_from_retained_sources(root=root, specs=inputs['specs'])
    with localcontext() as context:
        context.prec = 48
        lines = {key: Decimal(value) for key, value in bridge['ttm']['lines_cny'].items()}
        financial = lines['interest_income']-lines['interest_expense']-lines['commission_expense']-lines['finance']
        other = sum(lines[key] for key in GAINS if key in lines)+lines['nonoperating_income']-lines['nonoperating_expense']
        commercial = lines['operating_revenue']-sum(lines[key] for key in ('cost_of_sales','taxes_surcharges','selling','administration','research'))
        total = lines['profit_before_tax']-commercial
        reference = dict(financial_cny=str(financial), other_cny=str(other), unallocated_cny=str(total-financial-other),
            basis='FY2025+H12026-H12025 reported consolidated PBT contribution attribution; not financial-subsidiary net profit or distributable parent cash.')
    return dict(reference=reference, period=bridge['ttm']['period'],
        original_statements=bridge['original_statements'], source_bindings=inputs['source_bindings'],
        scope='SOURCE_DERIVED_PRETAX_ATTRIBUTION_NOT_NORMALIZED_OR_DISTRIBUTABLE_PROFIT')


def build_product_continuation_research(*, policy, cash_policy, generated, ledger, facts, contribution_reference=None):
    """Extend verified product hypotheses, never infer profitability from book ROE."""
    if (policy.get('center') != 'FLAT_YEAR5_PRODUCT_LEVELS_AND_COST_RATIOS'
            or policy.get('continuation_years') != 5
            or policy.get('challenge_moutai_realization_growth') != '-0.01'
            or policy.get('challenge_cost_ratio_increment') != '0.005'
            or generated.get('status') != 'CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED'):
        raise ValueError('Explicit product continuation and countercase required')
    for key in ('rationale','cash_return_rationale','terminal_rationale','challenge_rationale'):
        if not isinstance(policy.get(key),str) or not policy[key].strip():
            raise ValueError('Product continuation explanation required')
    if (not isinstance(policy.get('counter_evidence'),list) or not policy['counter_evidence']
            or any(not isinstance(item,str) or not item.strip() for item in policy['counter_evidence'])):
        raise ValueError('Product continuation counterevidence required')
    outcomes=[]
    sensitivities=[]
    challenge_policy=policy.get('economic_challenges')
    if challenge_policy is not None and (not isinstance(challenge_policy,dict)
            or challenge_policy.get('financial_retained_fractions') != ['0.9','0.8','0.7','0.6','0.5']
            or challenge_policy.get('cost_of_equity_increment') != '0.01'
            or not isinstance(challenge_policy.get('rationale'),str) or not challenge_policy['rationale'].strip()
            or contribution_reference is None):
        raise ValueError('Explicit source-derived contribution and economic challenge policy required')
    if {row['scenario'] for row in generated['scenarios']} != {'bear','base','bull'} or len(generated['scenarios']) != 3:
        raise ValueError('Three verified original product paths required')
    with localcontext() as context:
        context.prec=48
        for source in generated['scenarios']:
            scenario=source['scenario']
            old=ledger['cases']['TIMING_DELAY'][scenario]
            opening=_opening_state(old,ledger['history'],facts)
            first=source['operating_rows']
            if (len(first) != 5 or len(old['annual_rows']) != 5
                    or any(abs(Decimal(row['legacy_ex_parent'])-Decimal(prior['legacy_profit_before_new_cash_cost'])) > Decimal('1e-24')
                           for row,prior in zip(first,old['annual_rows']))):
                raise ValueError('Continuation changed the source-bound first five product years')
            for branch in ('FLAT_PRODUCT_CONTINUATION','REALIZATION_AND_COST_CHALLENGE'):
                continuation=[dict(moutai_volume_growth='0',moutai_realization_growth='0',
                    series_volume_growth='0',series_realization_growth='0',other_revenue_growth='0',
                    cost_ratio=first[-1]['drivers']['cost_ratio']) for _ in range(5)]
                if branch == 'REALIZATION_AND_COST_CHALLENGE':
                    for row in continuation:
                        row['moutai_realization_growth']=policy['challenge_moutai_realization_growth']
                        row['cost_ratio']=str(Decimal(row['cost_ratio'])+Decimal(policy['challenge_cost_ratio_increment']))
                capital=[_capital(y,Decimal(old['project_budget'])/5 if y<=5 else Decimal(0),
                    Decimal(opening['uncalled_fund_commitment_cny']) if y==1 else Decimal(0),
                    Decimal(0),cash_policy['maintenance_rationale']) for y in range(1,11)]
                distribution=[_distribution(y,cash_policy,persistent=False) for y in range(1,11)]
                terminal=dict(method='STABLE_PRODUCT_PROFIT_ZERO_GROWTH_FULL_PAYOUT',
                    rationale=policy['terminal_rationale'],
                    operating_continuation='FINAL_PRODUCT_LEVELS_AND_EARNINGS_BRIDGE_CONSTANT',
                    distribution_constraint_rationale=cash_policy['terminal_distribution_rationale'],
                    capital_cash_row=_capital(11,Decimal(0),Decimal(0),Decimal(0),cash_policy['maintenance_rationale']),
                    distribution_row=_distribution(11,cash_policy,persistent=False,terminal=True))
                arguments=dict(opening_state=opening,first_five_product_rows=first,
                    continuation_policy=continuation,capital_cash_rows=capital,distribution_rows=distribution,
                    cost_of_equity=ledger['plan']['ke'],incremental_cash_yield=ledger['plan']['incremental_parent_cash_yield'],
                    terminal_policy=terminal)
                result=build_product_continuation_cash_path(**arguments)
                outcomes.append(dict(scenario=scenario,branch=branch,result=result))
                if scenario == 'base' and branch == 'FLAT_PRODUCT_CONTINUATION' and challenge_policy is not None:
                    reference=contribution_reference['reference']
                    other_policy=dict(reference=reference,
                        rows=[dict(year=year, financial_cny=str(Decimal(reference['financial_cny'])*Decimal(fraction)),
                            other_cny=reference['other_cny'],unallocated_cny=reference['unallocated_cny'])
                            for year,fraction in enumerate(challenge_policy['financial_retained_fractions'],6)],
                        terminal_mode='HOLD_Y10_COMPONENTS', rationale=challenge_policy['rationale'])
                    for name,contributions,cost_increment in (
                        ('FINANCIAL_CONTRIBUTION_FADE',other_policy,Decimal(0)),
                        ('COST_OF_EQUITY_PLUS_100BP',None,Decimal(challenge_policy['cost_of_equity_increment'])),
                        ('FINANCIAL_FADE_AND_HIGHER_REQUIRED_RETURN',other_policy,Decimal(challenge_policy['cost_of_equity_increment']))):
                        sensitivities.append(dict(scenario='base',branch=name,
                            result=build_product_continuation_cash_path(**{**arguments,
                                'other_pre_tax_policy':contributions,
                                'cost_of_equity':str(Decimal(arguments['cost_of_equity'])+cost_increment)})))
    return dict(status='SOURCE_BOUND_PRODUCT_CONTINUATION_NOT_APPROVED',action='no_order',confidence='LOW',
        formal_eligibility=False,economic_approval=False,price_admission=False,primary_valuation_changed=False,
        rationale=policy['rationale'],cash_return_rationale=policy['cash_return_rationale'],
        challenge_rationale=policy['challenge_rationale'],terminal_rationale=policy['terminal_rationale'],
        counter_evidence=policy['counter_evidence'],scenarios=outcomes,
        sensitivity_cases=sensitivities,contribution_reference=contribution_reference,
        economic_challenges=challenge_policy)


def _load_product_continuation(*,root,symbol,now,candidate_binding,package,ledger,facts,cash_policy):
    relative='config/research-assumptions/'+symbol+'-product-continuation-v1.json'
    path=require_inside(root,root/relative,'product continuation policy')
    if not path.is_file():
        return None,[]
    try:
        raw=path.read_bytes()
        policy=json.loads(raw)
        available=datetime.fromisoformat(policy['generated_at'])
        if (available.utcoffset() is None or available>now
                or policy['schema_version'] != 'product-continuation-research-policy-v1'
                or policy['candidate_binding'] != candidate_binding or policy['symbol'] != symbol
                or policy['action'] != 'no_order' or policy['confidence'] != 'LOW'):
            raise ValueError('Product continuation availability/identity changed')
        from .product_operating_research import build_product_operating_research
        generated=build_product_operating_research(root=root,package=package,ledger=ledger,facts=facts,evaluation_at=now)
        contribution = _contribution_reference(root=root,package=package) if policy.get('economic_challenges') is not None else None
        result=build_product_continuation_research(policy=policy,cash_policy=cash_policy,generated=generated,ledger=ledger,facts=facts,
            contribution_reference=contribution)
        refs=[dict(path=relative,sha256=sha256(raw).hexdigest()),*generated['source_bindings']]
        for ref in refs:
            if sha256_file(require_inside(root,root/ref['path'],'product continuation source')) != ref['sha256']:
                raise ValueError('Product continuation source changed during calculation')
        return dict(result,input_available_at=available.isoformat(),source_bindings=refs),refs
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError) as error:
        return dict(status='PRODUCT_CONTINUATION_SOURCE_OR_ASSUMPTION_UNAVAILABLE',action='no_order',
            formal_eligibility=False,economic_approval=False,price_admission=False,
            scenarios=[],reason=type(error).__name__+':'+str(error)),[]

def build_finite_advantage_research(*, policy, package, ledger, facts):
    """Compute existing real-input hypotheses; caller authenticates all sources."""
    if (package['symbol'] != policy['symbol'] or policy['confidence'] != 'LOW'
            or policy['action'] != 'no_order' or policy['fade_years'] != [5, 10]
            or policy['maintenance_gap_challenge_ratios'] != ['0.02', '0.05']
            or policy['persistent_withheld_challenge'] != '0.10'):
        raise ValueError('Explicit reviewed sensitivity policy required')
    for key in ('rationale', 'cash_mapping_rationale', 'maintenance_rationale',
                'capacity_rationale', 'terminal_rationale', 'terminal_distribution_rationale'):
        if not isinstance(policy[key], str) or not policy[key].strip():
            raise ValueError('Finite cash hypothesis explanation required')
    history, plan = ledger['history'], ledger['plan']
    if (history['scope'] != 'standalone parent, NOT consolidated free cash'
            or history['unit'] != 'CNY' or plan['horizon'] != 5
            or plan['incremental_parent_cash_yield'] != '0.01'
            or plan['explicit_retention'] != '0.10'):
        raise ValueError('Inherited cash basis changed; research needs re-evaluation')
    outputs = []
    with localcontext() as context:
        context.prec = 48
        for scenario in ('bear', 'base', 'bull'):
            case = ledger['cases']['TIMING_DELAY'][scenario]
            legacy = [dict(year=row['year'], profit_cny=row['legacy_profit_before_new_cash_cost'])
                      for row in case['annual_rows']]
            if len(legacy) != 5 or case['blockers']:
                raise ValueError('Complete inherited operating hypothesis required')
            opening = _opening_state(case,history,facts)
            branches = [('BALANCED_NET_MAINTENANCE', Decimal(0), False)]
            if scenario == 'base':
                branches += [('EXTRA_NET_MAINTENANCE_2_PERCENT', Decimal('.02'), False),
                             ('EXTRA_NET_MAINTENANCE_5_PERCENT', Decimal('.05'), False),
                             ('PERSISTENT_10_PERCENT_UNREMITTED', Decimal(0), True)]
            for fade in policy['fade_years']:
                horizon = 5 + fade
                for name, ratio, persistent in branches:
                    gap = ratio * Decimal(legacy[0]['profit_cny'])
                    capital = [_capital(year,
                        Decimal(case['project_budget'])/5 if year <= 5 else Decimal(0),
                        Decimal(opening['uncalled_fund_commitment_cny']) if year == 1 else Decimal(0),
                        gap, policy['maintenance_rationale']) for year in range(1, horizon+1)]
                    distributions = [_distribution(year, policy, persistent=persistent)
                                     for year in range(1, horizon+1)]
                    terminal = dict(method='ZERO_GROWTH_KE_RETURN_FULL_PAYOUT',
                        rationale=policy['terminal_rationale'],
                        equity_pricing_assumption='ECONOMIC_BOOK_PRICING_NOT_LIQUIDATION_FACT',
                        distribution_constraint_rationale=policy['terminal_distribution_rationale'],
                        capital_cash_row=_capital(horizon+1, Decimal(0), Decimal(0), gap, policy['maintenance_rationale']),
                        distribution_row=_distribution(horizon+1, policy, persistent=persistent, terminal=True))
                    result = build_finite_advantage_cash_path(opening_state=opening,
                        legacy_profit_rows=legacy, capital_cash_rows=capital,
                        distribution_rows=distributions, fade_policy=dict(cost_of_equity=plan['ke'],
                            fade_years=fade, incremental_cash_yield=plan['incremental_parent_cash_yield']),
                        terminal_policy=terminal)
                    outputs.append(dict(scenario=scenario, branch=name, fade_years=fade,
                        net_maintenance_gap_cny=str(gap), result=result))
    return dict(branches=outputs, inherited_cost_of_equity=plan['ke'],
        rationale=policy['rationale'], counter_evidence=policy['counter_evidence'],
        methodology_urls=policy['methodology_urls'],
        explanation='Five operating years plus finite total-ROE fade. Research values are at the inherited model basis, not current fair values or approved condition prices.',
        price_condition_cny=None, primary_valuation_changed=False,
        unknowns=['Future conversion and legal distribution capacity', 'Maintenance/project overlap and WC',
                  'Competitive-advantage duration and required return', 'Terminal book pricing and lawful full payout'])


def load_finite_advantage_research(*, root: Path, symbol: str, now: datetime):
    """No writes/network/private inputs; bad current sources never fall back."""
    root = root.resolve()
    relative = 'config/research-assumptions/'+symbol+'-finite-advantage-cash-v1.json'
    path = require_inside(root, root/relative, 'finite advantage research policy')
    if not path.is_file():
        return None
    envelope = dict(schema_version='finite-advantage-research-v1', symbol=symbol,
        scope=SCOPE, currency='CNY', action='no_order', confidence='LOW',
        formal_eligibility=False, economic_approval=False, price_admission=False,
        status='SOURCE_OR_HYPOTHESIS_REVALIDATION_FAILED', branches=[])
    try:
        if now.utcoffset() is None or now > datetime.now(timezone.utc):
            raise ValueError('Observed aware evaluation clock required')
        raw = path.read_bytes()
        policy = json.loads(raw)
        available = datetime.fromisoformat(policy['generated_at'])
        if (available.utcoffset() is None or available > now or policy['symbol'] != symbol
                or policy['schema_version'] != 'finite-advantage-cash-research-policy-v1'
                or policy['identity'] != 'UNAPPROVED_ECONOMIC_HYPOTHESES_NOT_DISCLOSED_FORECAST'):
            raise ValueError('Finite research identity or availability mismatch')
        current = load_current_pending_candidate_supplement(root=root, symbol=symbol)
        from .product_continuation_candidate import SCHEMA as TEN_YEAR
        antecedent = (current['candidate'].get('source_candidate_binding')
            if current is not None and current['candidate']['schema_version'] == TEN_YEAR else None)
        if current is None or (current['candidate_binding'] != policy['candidate_binding']
                and antecedent != policy['candidate_binding']):
            raise ValueError('Finite research no longer matches current pending candidate')
        ref = policy['candidate_binding']
        candidate = verify_source_native_candidate(root=root, path=root/ref['path'], expected_sha256=ref['sha256'], now=now)
        _, package = read_bound_json(root, candidate['source_package_binding'], 'finite research package')
        _, ledger = read_bound_json(root, candidate['native_cash_ledger_binding'], 'finite research cash')
        facts = build_descriptor(package, root=root).facts
        computed = build_finite_advantage_research(policy=policy, package=package, ledger=ledger, facts=facts)
        continuation,continuation_refs=_load_product_continuation(root=root,symbol=symbol,now=now,
            candidate_binding=ref,package=package,ledger=ledger,facts=facts,cash_policy=policy)
        if continuation is not None:
            computed['product_continuation']=continuation
        refs = [dict(path=relative, sha256=sha256(raw).hexdigest()), dict(ref),
                dict(candidate['source_package_binding']), dict(candidate['native_cash_ledger_binding']),
                *candidate['source_bindings'], *[dict(row) for row in _IMPLEMENTATIONS], *continuation_refs]
        for binding in refs:
            if sha256_file(require_inside(root, root/binding['path'], 'finite research source')) != binding['sha256']:
                raise ValueError('Finite research source changed during evaluation')
        return dict(envelope, **computed, status='SOURCE_BOUND_FINITE_RESEARCH_NOT_APPROVED',
            source_bindings=refs, input_available_at=available.isoformat(),
            basis_date=package['point_in_time']['valuation_date'], research_as_of=now.date().isoformat(),
            availability_scope='CURRENT_RESEARCH_NOT_HISTORICAL_PIT')
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        return dict(envelope, reason=type(error).__name__+':'+str(error))

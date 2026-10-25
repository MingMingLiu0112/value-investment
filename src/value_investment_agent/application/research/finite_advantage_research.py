"""Source-bound finite-return/cash sensitivities beside, not replacing, a candidate."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path

from ...domain.valuation.finite_advantage_cash_path_v1 import build_finite_advantage_cash_path, SCOPE
from ...m1_valuation_package_builder import build_descriptor
from ..product.common import require_inside, sha256_file
from ..product.incremental_validity import read_bound_json
from ..product.pending_candidate_supplement import load_current_pending_candidate_supplement
from ..product.source_native_candidate_v2 import verify_source_native_candidate

_CODE_ROOT = Path(__file__).resolve().parents[4]
_IMPLEMENTATIONS = tuple(dict(path=name, sha256=sha256_file(_CODE_ROOT/name)) for name in (
    'src/value_investment_agent/application/research/finite_advantage_research.py',
    'src/value_investment_agent/domain/valuation/finite_advantage_cash_path_v1.py',
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
            opening = dict(scope=SCOPE, currency='CNY',
                book_equity_cny=str(facts.operating_inputs['start_book_equity']),
                ordinary_shares=str(facts.operating_inputs['ordinary_shares']),
                cash_cny=history['ttm']['cash_end'], unremitted_assets_cny='0',
                distribution_capacity_cny=history['ttm']['parent_retained_profit_end'],
                cash_floor_cny=case['cash_floor'],
                uncalled_fund_commitment_cny=history['known_uncalled_fund_commitment']['amount_cny'],
                selected_project_budget_cny=case['project_budget'])
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
        if current is None or current['candidate_binding'] != policy['candidate_binding']:
            raise ValueError('Finite research no longer matches current pending candidate')
        ref = policy['candidate_binding']
        candidate = verify_source_native_candidate(root=root, path=root/ref['path'], expected_sha256=ref['sha256'], now=now)
        _, package = read_bound_json(root, candidate['source_package_binding'], 'finite research package')
        _, ledger = read_bound_json(root, candidate['native_cash_ledger_binding'], 'finite research cash')
        facts = build_descriptor(package, root=root).facts
        computed = build_finite_advantage_research(policy=policy, package=package, ledger=ledger, facts=facts)
        refs = [dict(path=relative, sha256=sha256(raw).hexdigest()), dict(ref),
                dict(candidate['source_package_binding']), dict(candidate['native_cash_ledger_binding']),
                *candidate['source_bindings'], *[dict(row) for row in _IMPLEMENTATIONS]]
        for binding in refs:
            if sha256_file(require_inside(root, root/binding['path'], 'finite research source')) != binding['sha256']:
                raise ValueError('Finite research source changed during evaluation')
        return dict(envelope, **computed, status='SOURCE_BOUND_FINITE_RESEARCH_NOT_APPROVED',
            source_bindings=refs, input_available_at=available.isoformat(),
            basis_date=package['point_in_time']['valuation_date'], research_as_of=now.date().isoformat(),
            availability_scope='CURRENT_RESEARCH_NOT_HISTORICAL_PIT')
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        return dict(envelope, reason=type(error).__name__+':'+str(error))

"""Parent funding research orchestration."""
from value_investment_agent.infrastructure.filings.parent_funding_facts_v1 import (
    load_parent_facts, bind_original_page, bind_payment_arrangement, validate_supported_case,
)
from value_investment_agent.domain.research.parent_distribution_capacity_v1 import assess_capacity


def review_parent_funding(root, native_path, *, cutoff, period='2026-06-30'):
    packet = load_parent_facts(root, native_path, cutoff=cutoff)
    period = validate_supported_case(packet, period)
    def one(field):
        matches = [f for f in packet['facts'] if f['field'] == field and f['period_end'] == period]
        if len(matches) != 1:
            raise ValueError('missing/ambiguous parent fact: ' + field)
        return matches[0]
    evidence = [one(field) for field in (
        'parent_cash_equivalents', 'parent_dividend_payable', 'parent_retained_profit')]
    result = assess_capacity(opening_cash=evidence[0]['value'],
                             dividend_payable=evidence[1]['value'],
                             retained_profit=evidence[2]['value'], obligations=[])
    h1 = packet['sources'][evidence[0]['source_id']]
    debt_evidence = [bind_original_page(root, h1, cutoff, page, amount)
                     for page, amount in [(40, '1,510,049,088.62'),
                                          (40, '1,220,000,000.00'),
                                          (40, '12,311,533,974.01'),
                                          (100, '1,508,700,000.00'),
                                          (100, '1,748,151.38'),
                                          (100, '7,689,071.11')]]
    capex = one('parent_capex')
    capex_evidence = bind_original_page(root, packet['sources'][capex['source_id']],
                                       cutoff, capex['physical_page'], '413,591,845.80')
    legal_evidence = bind_original_page(root, h1, cutoff, 40, '23,214,184,665.64')
    return dict(result=result, period=period, evidence=evidence,
                sources=packet['sources'], native_sha256=packet['native_sha256'],
                debt_evidence=debt_evidence, historical_capex=capex_evidence,
                future_necessary_investment='UNKNOWN',
                historical_cash_uses=dict(scope='parent', period='2026-H1', unit='CNY',
                    treatment='Already included in ending cash; no additional deduction.',
                    cash_statement_reconciliation='NOT_PERFORMED_OUT_OF_SCOPE'),
                retained_profit_evidence=legal_evidence, legal_adjustments='UNKNOWN',
                unknowns=['subsequent_parent_cash_bridge', 'principal_interest_maturity_split',
                          'operating_reserve', 'necessary_investment', 'legal_distribution_adjustments'],
                debt_review=dict(parent_current_noncurrent_liabilities='1510049088.62',
                    other_payables_including_dividend='12311533974.01',
                    other_payables_ex_dividend='5809966323.44',
                    other_payables_cash_timing='UNKNOWN',
                    parent_page=40, principal_interest_split=None,
                    parent_noncurrent_borrowing='1220000000.00',
                    consolidated_note_page=100,
                    consolidated_current_principal='1508700000.00',
                    consolidated_current_interest='1748151.38',
                    consolidated_current_lease='7689071.11',
                    warning='Consolidated components cannot be assigned to parent.'),
                interpretation='Historical static remainder is not current free cash; retained profit is not certified legal capacity.', action='no_order')


def review_post_h1(root, native_path, receipt_path, *, cutoff):
    review = review_parent_funding(root, native_path, cutoff=cutoff)
    review['post_h1_bridge'] = bind_payment_arrangement(root, receipt_path, cutoff)
    return review


def read_registered_parent_funding_review(*, root, symbol, now):
    """Pure public read of the registered historical review, not current capacity."""
    from copy import deepcopy
    from datetime import datetime
    import hashlib
    import json
    from pathlib import Path
    import re
    from . import operating_cash_consumption_v1 as oldcashapp
    from ..product.common import require_inside
    from ...infrastructure.filings import parent_funding_facts_v1 as native
    from ...domain.research import parent_distribution_capacity_v1 as economics

    result = dict(status='NOT_STARTED', symbol=symbol, action='no_order', formal_eligibility=False,
                  current_capacity_proven=False, review=None)
    try:
        if not isinstance(symbol, str) or not re.fullmatch(r'[0-9]{6}', symbol):
            raise ValueError('INVALID_PARENT_REVIEW_SYMBOL')
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError('AWARE_PARENT_REVIEW_CLOCK_REQUIRED')
        root = Path(root).resolve()
        registry = require_inside(root, root / 'config/current-operating-research-sources-v1.json', 'parent registry')
        if not registry.exists():
            return result
        raw = registry.read_bytes()
        registration = json.loads(raw)
        if (not isinstance(registration, dict) or registration.get('schema_version') != 'current-operating-research-sources-v1'
                or registration.get('action') != 'no_order' or not isinstance(registration.get('cases'), dict)):
            raise ValueError('INVALID_PARENT_REVIEW_REGISTRY')
        entry = registration['cases'].get(symbol)
        if entry is None:
            return result
        if not isinstance(entry, dict):
            raise ValueError('INVALID_PARENT_REVIEW_REGISTRY_ENTRY')
        if 'parent_funding_followup' not in entry:
            return result
        binding = entry['parent_funding_followup']
        spec = oldcashapp._bound_json(root, binding)
        if (not isinstance(spec, dict) or set(spec) != {'schema_version', 'symbol', 'scope', 'action',
                'native_facts', 'source_receipt', 'generated_at'}
                or spec['schema_version'] != 'parent-funding-followup-v1'
                or spec['symbol'] != symbol or spec['scope'] != 'HISTORICAL_PARENT_CASH_REVIEW_NOT_CURRENT_CAPACITY'
                or spec['action'] != 'no_order'):
            raise ValueError('INVALID_PARENT_FUNDING_SPEC')
        generated = datetime.fromisoformat(spec['generated_at'])
        if generated.utcoffset() is None or generated > now:
            raise ValueError('PARENT_FUNDING_SPEC_NOT_AVAILABLE')
        if spec['native_facts'] != entry.get('native_facts'):
            raise ValueError('PARENT_NATIVE_BINDING_NOT_CURRENT_REGISTRY')
        packet = oldcashapp._bound_json(root, spec['native_facts'])
        if not isinstance(packet, dict) or packet.get('symbol') != symbol:
            raise ValueError('PARENT_NATIVE_SYMBOL_MISMATCH')
        oldcashapp._bound_json(root, spec['source_receipt'])
        modules = {__name__: Path(__file__), native.__name__: Path(native.__file__),
                   economics.__name__: Path(economics.__file__)}
        hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in modules.items()}
        review = review_post_h1(root, spec['native_facts']['path'], spec['source_receipt']['path'], cutoff=now)
        for pin in (binding, spec['native_facts'], spec['source_receipt']):
            oldcashapp._bound_json(root, pin)
        if registry.read_bytes() != raw:
            raise ValueError('PARENT_REGISTRY_CHANGED_DURING_READ')
        if hashes != {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in modules.items()}:
            raise ValueError('PARENT_IMPLEMENTATION_CHANGED_DURING_READ')
        result.update(status='HISTORICAL_PARENT_REVIEW', scope=spec['scope'], review=review,
            source_spec=deepcopy(binding), source_receipt=deepcopy(spec['source_receipt']),
            native_facts=deepcopy(spec['native_facts']), implementation_sha256=hashes)
        return result
    except (ValueError, OSError, TypeError, KeyError) as error:
        result.update(status='UNASSESSABLE', error_code=type(error).__name__, reason=str(error), review=None)
        return result


def compare_parent_cash_opening(parent, cash):
    """Compare amounts in bound read models, never certify their derivation."""
    from decimal import InvalidOperation
    import re
    from ...domain.research.parent_distribution_capacity_v1 import money
    from ...domain.valuation.joint_capital_cash_path_v4 import SCOPE
    result = dict(status='NOT_ASSESSABLE', action='no_order', current_capacity_proven=False,
                  source_mapping_verified=False, scope='AMOUNT_COMPARISON_NOT_SOURCE_MAPPING_OR_LEGAL_CAPACITY')
    if not isinstance(parent,dict) or not isinstance(cash,dict):
        return dict(result,reason='STRUCTURED_VERIFIED_READ_MODELS_REQUIRED')
    review=parent.get('review')
    if parent.get('status') != 'HISTORICAL_PARENT_REVIEW' or not isinstance(review,dict):
        return dict(result, reason='HISTORICAL_PARENT_REVIEW_REQUIRED')
    annual = cash.get('annual_followup')
    opening = annual.get('opening_state') if isinstance(annual,dict) else None
    native=parent.get('native_facts')
    if (not isinstance(annual,dict) or not isinstance(opening,dict)
            or annual.get('status') != 'CONDITIONAL_STRESS_CONSUMED'
            or opening.get('as_of') != review.get('period') or opening.get('currency') != 'CNY'
            or opening.get('scope') != SCOPE):
        return dict(result, reason='SAME_DATE_SUPPORTED_SCOPE_CNY_CASH_MODEL_INPUT_REQUIRED')
    if (not isinstance(native,dict) or set(native) != {'path','sha256'}
            or not isinstance(native['sha256'],str) or re.fullmatch('[0-9a-f]{64}',native['sha256']) is None
            or cash.get('source_binding') != native or cash.get('symbol') != parent.get('symbol')
            or not isinstance(parent.get('symbol'),str) or re.fullmatch('[0-9]{6}',parent['symbol']) is None
            or not isinstance(annual.get('input_descriptor_sha256'),str)
            or re.fullmatch('[0-9a-f]{64}',annual['input_descriptor_sha256']) is None
            or not isinstance(parent.get('source_spec'),dict)):
        return dict(result,reason='SAME_SYMBOL_NATIVE_AND_MODEL_VERSION_BINDINGS_REQUIRED')
    amounts=review.get('result')
    if not isinstance(amounts,dict):
        return dict(result,reason='STRUCTURED_STATIC_REVIEW_REQUIRED')
    try:
        observed = money(amounts['static_after_declared_dividend'], signed=True)
        consumed = money(opening['cash_cny'], signed=True)
    except (KeyError,TypeError,InvalidOperation,ValueError):
        return dict(result, reason='EXPLICIT_FINITE_CASH_AMOUNTS_REQUIRED')
    return dict(result, status='AMOUNT_EQUAL_NOT_MAPPING_VERIFIED' if observed == consumed else 'AMOUNT_DIFFERENT',
        source_static_remainder_cny=str(observed),model_opening_cash_cny=str(consumed),
        model_financial_basis=opening['as_of'],model_scope=opening['scope'],
        input_descriptor_sha256=annual['input_descriptor_sha256'],source_spec=parent['source_spec'],
        explanation='Amount equality in the same bound source context does not prove automatic derivation, owner-equivalent mapping, cash floor, future remittance, debt completeness or legal distribution capacity.')

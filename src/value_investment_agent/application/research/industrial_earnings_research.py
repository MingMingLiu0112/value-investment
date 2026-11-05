"""Retained industrial statements into explicit, unapproved earnings hypotheses."""
from datetime import datetime, timezone
import json
from pathlib import Path

from ...domain.valuation.industrial_earnings_paths import build_industrial_earnings_paths
from .operating_earnings_bridge import research_from_retained_sources
from ..product.common import require_inside, sha256_file

DRIVERS = ('revenue_growth', 'commercial_margin', 'inventory_impairment_ratio',
    'goodwill_impairment_cny', 'other_asset_impairment_cny', 'other_pbt_cny',
    'tax_research_rate', 'signed_nci_cny')
SPEC = 'docs/current/two-company-earnings-bridge-20261024/sources.json'
IMPLEMENTATIONS = (
    'application/research/industrial_earnings_research.py',
    'application/research/operating_earnings_bridge.py',
    'domain/valuation/industrial_earnings_paths.py',
    'domain/valuation/signed_parent_profit.py',
    'infrastructure/filings/pdf_text.py', 'infrastructure/filings/pdfium_runtime.py')
_EXECUTING_ROOT = Path(__file__).resolve().parents[4]
_EXECUTED_BINDINGS = tuple(dict(path='src/value_investment_agent/'+name,
    sha256=sha256_file(_EXECUTING_ROOT/'src/value_investment_agent'/name)) for name in IMPLEMENTATIONS)


def load_industrial_earnings_research(*, root: Path, symbol: str, now: datetime) -> dict | None:
    """Read only; source changes invalidate this appendix, never erase old research."""
    if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isascii() or not symbol.isdigit():
        raise ValueError('Industrial research requires a security identity')
    root = root.resolve()
    policy_name = 'config/research-assumptions/'+symbol+'-industrial-earnings-v1.json'
    policy_path = require_inside(root, root/policy_name, 'industrial research policy')
    if not policy_path.is_file():
        return None
    envelope = dict(schema_version='industrial-earnings-research-v1', symbol=symbol,
        action='no_order', confidence='LOW', formal_eligibility=False,
        primary_valuation_usable=False, price_admitted=False, strategy_admitted=False,
        economic_approval=False, normalized_parent_profit_cny=None,
        context_scope='INDEPENDENT_SOURCE_BOUND_RESEARCH_NOT_CURRENT_VALUATION',
        scenarios={})
    try:
        if now.utcoffset() is None:
            raise ValueError('Timezone-aware research observation required')
        policy_ref = dict(path=policy_name, sha256=sha256_file(policy_path))
        policy = json.loads(policy_path.read_bytes())
        available = datetime.fromisoformat(policy['generated_at'])
        if (available.utcoffset() is None or policy['symbol'] != symbol
                or policy['schema_version'] != 'industrial-earnings-research-policy-v1'
                or policy['identity_class'] != 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST'
                or policy['action'] != 'no_order' or policy['confidence'] != 'LOW'
                or policy['source_spec_path'] != SPEC):
            raise ValueError('Industrial policy identity/scope mismatch')
        if available > now:
            return dict(envelope, status='NOT_YET_AVAILABLE', input_available_at=available.isoformat())
        for ref in _EXECUTED_BINDINGS:
            if sha256_file(require_inside(root, root/ref['path'], 'industrial executing code')) != ref['sha256']:
                raise ValueError('Industrial research differs from executing implementation')
        spec_path = require_inside(root, root/SPEC, 'industrial statement specification')
        spec_ref = dict(path=SPEC, sha256=sha256_file(spec_path))
        spec = json.loads(spec_path.read_bytes())
        if (spec['schema_version'] != 'two-company-earnings-source-spec-v1'
                or spec['scope'] != 'RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION'
                or spec['action'] != 'no_order'):
            raise ValueError('Industrial original specification identity mismatch')
        originals = spec['companies'][symbol]
        expected = {row['source_id']: row['sha256'] for row in originals}
        if len(originals) != 2 or len(expected) != 2 or policy['official_sources'] != expected:
            raise ValueError('Industrial policy is not bound to these originals')
        historical = research_from_retained_sources(root=root,
            specs=[dict(row, fields=spec['common_fields']+row['extra_fields']) for row in originals], now=now)
        if historical['symbol'] != symbol:
            raise ValueError('Industrial originals belong to another company')
        if set(policy['scenarios']) != {'bear', 'base', 'bull'}:
            raise ValueError('Three explicit industrial scenarios required')
        expanded = {}
        for name, row in policy['scenarios'].items():
            if (set(row) != set(DRIVERS) | {'rationale'}
                    or not isinstance(row['rationale'], str) or not row['rationale'].strip()
                    or any(not isinstance(row[key], list) or len(row[key]) != 5 for key in DRIVERS)):
                raise ValueError('Five explicit years and rationale required')
            expanded[name] = [dict(year=year+1, **{key: row[key][year] for key in DRIVERS}) for year in range(5)]
        for key in ('rationale', 'tax_convention'):
            if not isinstance(policy[key], str) or not policy[key].strip():
                raise ValueError('Industrial research explanation missing')
        for key in ('counter_evidence', 'thesis_breakers', 'unknowns'):
            if (not isinstance(policy[key], list) or not policy[key]
                    or any(not isinstance(text, str) or not text.strip() for text in policy[key])):
                raise ValueError('Industrial research needs countercase and uncertainty')
        calculation = build_industrial_earnings_paths(historical_ttm=historical['ttm']['lines_cny'], scenarios=expanded)
        refs = [policy_ref, spec_ref, *[dict(path=row['path'], sha256=row['sha256']) for row in originals],
                *[dict(ref) for ref in _EXECUTED_BINDINGS]]
        for ref in refs:
            if sha256_file(require_inside(root, root/ref['path'], 'industrial final source read')) != ref['sha256']:
                raise ValueError('Industrial source changed during research')
        return dict(envelope, status=calculation['status'],
            input_available_at=available.isoformat(), evaluated_at=now.isoformat(),
            financial_basis='2026-06-30', historical_period=historical['ttm']['period'],
            historical_reference=calculation['historical_reference'],
            scenarios={name:dict(calculation['scenarios'][name], rationale=policy['scenarios'][name]['rationale'])
                       for name in ('bear', 'base', 'bull')},
            rationale=policy['rationale'], tax_convention=policy['tax_convention'],
            counter_evidence=policy['counter_evidence'], thesis_breakers=policy['thesis_breakers'],
            unknowns=policy['unknowns'], policy_binding=policy_ref, source_bindings=refs,
            official_sources=historical['source_bindings'],
            availability_scope='RETAINED_ORIGINAL_RESEARCH_NOT_CONTEMPORANEOUS_PIT_PROOF')
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, IndexError):
        return dict(envelope, status='SOURCE_OR_ASSUMPTION_REVALIDATION_FAILED',
            reason='经营研究原件、假设或实现未通过核验；不沿用金额或授予操作资格。')

"""Bind fiscal-year earnings hypotheses to retained annual/interim originals."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

from ...domain.valuation.fiscal_industrial_earnings_paths_v1 import build_fiscal_industrial_earnings_paths
from ...domain.valuation.industrial_earnings_paths import HISTORICAL_FIELDS
from ...infrastructure.filings.pdf_text import extract_pages
from ..product.common import require_inside, sha256_file
from .industrial_earnings_research import DRIVERS, SPEC
from .operating_earnings_bridge import research_from_retained_sources

_ROOT = Path(__file__).resolve().parents[4]
_IMPLEMENTATIONS = tuple(dict(path='src/value_investment_agent/'+name,
    sha256=sha256_file(_ROOT/'src/value_investment_agent'/name)) for name in (
        'application/research/fiscal_earnings_research.py',
        'application/research/operating_earnings_bridge.py',
        'application/research/industrial_earnings_research.py',
        'domain/valuation/fiscal_industrial_earnings_paths_v1.py',
        'domain/valuation/industrial_earnings_paths.py',
        'domain/valuation/signed_parent_profit.py',
        'infrastructure/filings/pdf_text.py', 'infrastructure/filings/pdfium_runtime.py'))


def load_fiscal_earnings_research(*, root: Path, symbol: str, now: datetime) -> dict | None:
    """Read only; no approval, market price, private data or payout inference."""
    if not isinstance(symbol, str) or not re.fullmatch(r'[0-9]{6}', symbol):
        raise ValueError('Fiscal research requires a security identity')
    root = root.resolve()
    name = 'config/research-assumptions/'+symbol+'-fiscal-earnings-v1.json'
    policy_path = require_inside(root, root/name, 'fiscal research policy')
    if not policy_path.is_file():
        return None
    envelope = dict(schema_version='fiscal-earnings-research-v1', symbol=symbol, currency='CNY', scope='consolidated',
        action='no_order', confidence='LOW', formal_eligibility=False, economic_approval=False,
        price_admitted=False, strategy_admitted=False, primary_valuation_usable=False,
        dividend_capacity_cny=None, normalized_parent_profit_cny=None, scenarios={})
    try:
        if now.utcoffset() is None:
            raise ValueError('Fiscal research needs an aware clock')
        policy_bytes = policy_path.read_bytes()
        policy = json.loads(policy_bytes)
        policy_ref = dict(path=name, sha256=sha256(policy_bytes).hexdigest())
        available = datetime.fromisoformat(policy['generated_at'])
        if (available.utcoffset() is None or available > now or policy['symbol'] != symbol
                or policy['schema_version'] != 'fiscal-earnings-research-policy-v1'
                or policy['identity_class'] != 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST'
                or policy['action'] != 'no_order' or policy['confidence'] != 'LOW'):
            raise ValueError('Fiscal policy identity or availability mismatch')
        inherited_ref = policy['annual_policy_binding']
        if inherited_ref['path'] != 'config/research-assumptions/'+symbol+'-industrial-earnings-v1.json':
            raise ValueError('Fiscal policy inherits a different company')
        inherited_path = require_inside(root, root/inherited_ref['path'], 'annual drivers')
        inherited_bytes = inherited_path.read_bytes()
        if sha256(inherited_bytes).hexdigest() != inherited_ref['sha256']:
            raise ValueError('Inherited annual drivers changed')
        annual_policy = json.loads(inherited_bytes)
        if (annual_policy['symbol'] != symbol or annual_policy['action'] != 'no_order'
                or annual_policy['identity_class'] != 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST'
                or datetime.fromisoformat(annual_policy['generated_at']) > available):
            raise ValueError('Annual policy identity or chronology differs')
        spec_path = require_inside(root, root/SPEC, 'fiscal original specification')
        spec_bytes = spec_path.read_bytes()
        spec = json.loads(spec_bytes)
        if (spec['schema_version'] != 'two-company-earnings-source-spec-v1'
                or spec['scope'] != 'RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION'
                or spec['action'] != 'no_order'):
            raise ValueError('Original specification identity mismatch')
        originals = spec['companies'][symbol]
        if (len(originals) != 2 or len({row['source_id'] for row in originals}) != 2
                or annual_policy['official_sources'] != {row['source_id']:row['sha256'] for row in originals}):
            raise ValueError('Fiscal originals differ from inherited evidence')
        for row in originals:
            identifier = re.fullmatch(r'cninfo:([0-9]+)', row['source_id'])
            url = re.fullmatch(r'https://static\.cninfo\.com\.cn/finalpage/(\d{4}-\d{2}-\d{2})/([0-9]+)\.PDF', row['source_url'])
            if (row['symbol'] != symbol or not identifier or not url
                    or identifier[1] != url[2] or url[1] != row['published_date']):
                raise ValueError('Fiscal official source identity/URL mismatch')
        refs = [policy_ref, inherited_ref, dict(path=SPEC, sha256=sha256(spec_bytes).hexdigest()),
                *[dict(path=row['path'], sha256=row['sha256']) for row in originals],
                *[dict(ref) for ref in _IMPLEMENTATIONS]]
        for ref in refs:
            if sha256_file(require_inside(root, root/ref['path'], 'fiscal input')) != ref['sha256']:
                raise ValueError('Fiscal source or executing code changed')
        parsed = research_from_retained_sources(root=root, specs=[dict(row,
            fields=spec['common_fields']+row['extra_fields']) for row in originals], now=now)
        if parsed['symbol'] != symbol:
            raise ValueError('Fiscal originals belong to another issuer')
        historical = {}
        for statement in parsed['original_statements']:
            for index, period in enumerate(statement['periods']):
                if period not in ('FY2025', 'H12025', 'H12026'):
                    continue
                year = period[-4:]
                historical[period] = dict(symbol=symbol, period_start=year+'-01-01',
                    period_end=year+('-12-31' if period.startswith('FY') else '-06-30'),
                    scope='consolidated', unit='CNY', currency='CNY',
                    accounting_basis_id=policy['accounting_comparability']['basis_id'],
                    lines={key:statement['rows'][key]['values'][index] for key in HISTORICAL_FIELDS})
        comparison = policy['accounting_comparability']
        if (comparison['status'] != 'REVIEWED_COMPARABLE_FOR_CURRENT_RESEARCH'
                or comparison['conclusion'] != 'NO_DISCLOSED_RESTATEMENT_IDENTIFIED_IN_REVIEWED_ORIGINALS'
                or comparison['perimeter'] != 'AS_REPORTED_NOT_CONSTANT_PERIMETER'
                or not comparison['limitations'].strip()
                or not comparison['evidence'] or comparison['source_sha256'] != annual_policy['official_sources']):
            raise ValueError('Fiscal accounting comparability not source-bound')
        pages_by_id = {row['source_id']:extract_pages(require_inside(root,root/row['path'], 'fiscal comparability original')) for row in originals}
        reviewed = set()
        for evidence in comparison['evidence']:
            page = evidence['physical_page']
            pages = pages_by_id[evidence['source_id']]
            excerpt = evidence['expected_excerpt']
            if (type(page) is not int or not 1 <= page <= len(pages) or not isinstance(excerpt,str)
                    or not excerpt.strip() or re.sub(r'\s+','',excerpt) not in re.sub(r'\s+','',pages[page-1])):
                raise ValueError('Fiscal comparability excerpt/page mismatch')
            reviewed.add(evidence['source_id'])
        if reviewed != set(annual_policy['official_sources']):
            raise ValueError('Both fiscal originals need comparability evidence')
        annual_drivers = {key:[dict(year=i+2027, **{field:row[field][i] for field in DRIVERS})
            for i in range(5)] for key, row in annual_policy['scenarios'].items()}
        if set(policy['stub_scenarios']) != {'bear', 'base', 'bull'}:
            raise ValueError('Three explicit stub scenarios required')
        calculated = build_fiscal_industrial_earnings_paths(historical=historical,
            stub_scenarios=policy['stub_scenarios'], scenarios=annual_drivers)
        outcomes = {scenario:dict(stub=calculated['research_h2_2026'][scenario],
            fy2026=calculated['fy2026_research_base'][scenario], rows=calculated['scenarios'][scenario]['rows'])
            for scenario in ('bear','base','bull')}
        for key in ('rationale', 'stub_rationale'):
            if not isinstance(policy[key], str) or not policy[key].strip():
                raise ValueError('Fiscal research explanation missing')
        for key in ('counter_evidence', 'thesis_breakers', 'limitations'):
            if not isinstance(policy[key], list) or not policy[key] or any(not isinstance(v,str) or not v.strip() for v in policy[key]):
                raise ValueError('Fiscal research countercase missing')
        for ref in refs:
            if sha256_file(require_inside(root, root/ref['path'], 'fiscal final read')) != ref['sha256']:
                raise ValueError('Fiscal input changed during calculation')
        return dict(envelope, status='SOURCE_BOUND_FISCAL_RESEARCH_NOT_APPROVED',
            input_available_at=available.isoformat(), evaluated_at=now.isoformat(),
            historical_h2_2025=calculated['historical_h2_2025'], scenarios=outcomes,
            rationale=policy['rationale'], stub_rationale=policy['stub_rationale'],
            counter_evidence=policy['counter_evidence'], thesis_breakers=policy['thesis_breakers'],
            limitations=policy['limitations'], accounting_comparability=comparison,
            cost_component_allocation='H22025_COST_PROPORTIONS_AS_RESEARCH_PROXY_NOT_OBSERVED_FUTURE_COSTS',
            source_bindings=refs, official_sources=parsed['source_bindings'],
            availability_scope='RETAINED_RESEARCH_NOT_CONTEMPORANEOUS_PIT_PROOF')
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, IndexError):
        return dict(envelope, status='SOURCE_OR_FISCAL_ASSUMPTION_REVALIDATION_FAILED')

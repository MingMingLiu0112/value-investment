"""TEST_ONLY parser substitutes exercise source-bound forward research orchestration."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from hashlib import sha256
from decimal import Decimal

import pytest
from value_investment_agent.application.research import industrial_earnings_research as service


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


@pytest.fixture
def retained(tmp_path, monkeypatch):
    executing = Path(__file__).resolve().parents[1]
    policy_name = 'config/research-assumptions/600887-industrial-earnings-v1.json'
    policy = json.loads((executing/policy_name).read_bytes())
    originals = []
    for n, ident in enumerate(policy['official_sources']):
        path = tmp_path/f'runtime/TEST_ONLY-original-{n}.pdf'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'TEST_ONLY parser fixture, not an official report '+str(n).encode())
        digest = sha256(path.read_bytes()).hexdigest()
        policy['official_sources'][ident] = digest
        originals.append(dict(symbol='600887', source_id=ident, path=path.relative_to(tmp_path).as_posix(),
            sha256=digest, extra_fields=[], source_url='https://static.cninfo.com.cn/finalpage/TEST_ONLY.PDF'))
    write(tmp_path/policy_name, policy)
    spec = dict(schema_version='two-company-earnings-source-spec-v1',
        scope='RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION', action='no_order',
        common_fields=[], companies={'600887':originals})
    write(tmp_path/service.SPEC, spec)
    for ref in service._EXECUTED_BINDINGS:
        target = tmp_path/ref['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((executing/ref['path']).read_bytes())
    lines = dict(operating_revenue='1000', cost_of_sales='600', taxes_surcharges='10', selling='100',
        administration='50', research='10', profit_before_tax='200', asset_impairment='-40',
        income_tax='50', minority_profit='-10', parent_profit='160')
    parsed = dict(symbol='600887', ttm=dict(period='TEST_ONLY-TTM', lines_cny=lines),
        source_bindings=deepcopy(originals))
    monkeypatch.setattr(service, 'research_from_retained_sources', lambda **_: deepcopy(parsed))
    now = datetime.fromisoformat(policy['generated_at'])+timedelta(seconds=1)
    return tmp_path, policy, spec, parsed, now


def test_explicit_hypotheses_use_signed_nci_without_valuation_or_file_writes(retained):
    root, _, _, _, now = retained
    before = {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = service.load_industrial_earnings_research(root=root, symbol='600887', now=now)
    assert result['status'] == 'CONDITIONAL_EARNINGS_RESEARCH_NOT_APPROVED'
    row = result['scenarios']['base']['rows'][0]
    assert row['signed_nci_cny'] == '-150000000'
    assert Decimal(row['bridge_residual_cny']) == 0
    assert result['confidence'] == 'LOW'
    assert result['economic_approval'] is result['formal_eligibility'] is result['price_admitted'] is False
    assert result['normalized_parent_profit_cny'] is None
    assert 'valuation' not in result and 'current_price' not in result
    assert before == {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fault', ['source', 'policy_identity', 'policy_source', 'short_years',
    'no_countercase', 'future', 'naive', 'implementation', 'wrong_issuer'])
def test_invalid_sources_or_assumptions_never_keep_amounts(retained, fault):
    root, policy, spec, parsed, now = retained
    if fault == 'source': (root/spec['companies']['600887'][0]['path']).write_bytes(b'changed')
    elif fault == 'policy_identity': policy['symbol'] = '600519'
    elif fault == 'policy_source': policy['official_sources']['cninfo:1225259562'] = '0'*64
    elif fault == 'short_years': policy['scenarios']['base']['signed_nci_cny'] = ['0']
    elif fault == 'no_countercase': policy['counter_evidence'] = []
    elif fault == 'future': now -= timedelta(days=1)
    elif fault == 'naive': now = now.replace(tzinfo=None)
    elif fault == 'implementation': (root/service._EXECUTED_BINDINGS[-1]['path']).write_bytes(b'drift')
    elif fault == 'wrong_issuer': parsed['symbol'] = '600519'
    write(root/'config/research-assumptions/600887-industrial-earnings-v1.json', policy)
    result = service.load_industrial_earnings_research(root=root, symbol='600887', now=now)
    assert result['status'] == ('NOT_YET_AVAILABLE' if fault == 'future' else 'SOURCE_OR_ASSUMPTION_REVALIDATION_FAILED')
    assert result['scenarios'] == {} and result['price_admitted'] is False


def test_final_source_recheck_rejects_mid_calculation_drift(retained, monkeypatch):
    root, _, spec, _, now = retained
    original = service.build_industrial_earnings_paths
    def changed(**kwargs):
        result = original(**kwargs)
        (root/spec['companies']['600887'][0]['path']).write_bytes(b'TEST_ONLY TOCTOU')
        return result
    monkeypatch.setattr(service, 'build_industrial_earnings_paths', changed)
    result = service.load_industrial_earnings_research(root=root, symbol='600887', now=now)
    assert result['status'] == 'SOURCE_OR_ASSUMPTION_REVALIDATION_FAILED' and result['scenarios'] == {}


def test_no_policy_leaves_existing_company_analysis_alone(tmp_path):
    assert service.load_industrial_earnings_research(root=tmp_path, symbol='600519', now=datetime.now(timezone.utc)) is None

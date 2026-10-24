"""Opt-in retained originals, actual native compiler, no real signatures."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from decimal import Decimal as D
import pytest

from test_source_native_economic_review_v1 import public_js2
from value_investment_agent.application.research import source_native_operating_erosion_v1 as app
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.source_native_candidate_v2 import verify_source_native_candidate


def run(root, ref, name='runtime/erosion-test-v1'):
    return app.build_source_native_operating_erosion(root=root, candidate_binding=ref,
        output_dir=root/name)


def test_real_official_inputs_to_native_candidate_and_base_bull_unchanged(public_js2):
    root, ref, _ = public_js2
    original = json.loads((root/ref['path']).read_bytes())
    original_package = json.loads((root/original['source_package_binding']['path']).read_bytes())
    old_ledger = json.loads((root/original['native_cash_ledger_binding']['path']).read_bytes())
    before = {r['path']:sha256_file(root/r['path']) for r in [ref,*original['source_bindings']]}
    result = run(root, ref)
    assert result['status'] == 'PENDING_NATIVE_RESEARCH_CANDIDATE_NOT_APPROVED'
    new = verify_source_native_candidate(root=root, path=root/result['candidate_binding']['path'],
        expected_sha256=result['candidate_binding']['sha256'], now=datetime.now(timezone.utc))
    package = json.loads((root/result['source_package_binding']['path']).read_bytes())
    ledger = json.loads((root/result['native_cash_ledger_binding']['path']).read_bytes())
    for name in ('base','bull'):
        assert package['facts']['scenario_inputs'][name] == original_package['facts']['scenario_inputs'][name]
        assert ledger['cases']['TIMING_DELAY'][name] == old_ledger['cases']['TIMING_DELAY'][name]
        assert new['candidate_valuation'][name+'_value'] == original['candidate_valuation'][name+'_value']
        assert [a[name] for a in package['assumptions']['assumptions']] == [a[name] for a in original_package['assumptions']['assumptions']]
        assert [b for b in package['assumption_bindings'] if b['scenario']==name] == [b for b in original_package['assumption_bindings'] if b['scenario']==name]
    assert D(new['candidate_valuation']['bear_value']) < D(original['candidate_valuation']['bear_value'])
    assert new['research_admitted'] is False and new['price_admitted'] is False
    assert all(abs(D(row['dividend_crosscheck_difference'])) < D('1e-25')
               for row in new['candidate_valuation']['sensitivities'])
    inputs = json.loads((root/'runtime/erosion-test-v1/operating-inputs.json').read_bytes())
    assert inputs['mixed_proxy']['revenue_yoy_pct'] == '-1.08'
    assert inputs['mixed_proxy']['volume_yoy_pct'] == '2.13'
    assert inputs['unknown']['normalized_profit'] is None
    assert inputs['research_assumptions']['h1_cost_ratio_from_year_one'] is True
    assert inputs['parameter_metadata']['five_year_operating_path']['identity'] == 'RESEARCH_ASSUMPTION'
    assert inputs['derived_historical_ratios']['identity_class'] == 'DERIVED_FROM_SOURCE_FACTS_NOT_FORECAST'
    assert package['source_contract']['cutoff_at'] == result['observed_at']
    assert set(package['research_case']['financial_summary']['js2_economic_review']['five_groups'].values()) == {'PENDING_FORMAL_REVIEW'}
    assert before == {p:sha256_file(root/p) for p in before}
    (root/'erosion-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with pytest.raises(FileExistsError): run(root, ref)


@pytest.mark.parametrize('damage', ['candidate', 'official', 'ledger'])
def test_real_original_drift_rejected_before_publication(public_js2, damage):
    root, ref, _ = public_js2
    original = json.loads((root/ref['path']).read_bytes())
    package = json.loads((root/original['source_package_binding']['path']).read_bytes())
    path = ref['path'] if damage == 'candidate' else original['native_cash_ledger_binding']['path']
    if damage == 'official': path = next(x['local_path'] for x in package['sources'] if x['id']=='cninfo:1225114741')
    target = root/path
    target.write_bytes(target.read_bytes()+b'\nTEST_ONLY_DRIFT')
    with pytest.raises(ValueError): run(root, ref)
    assert not (root/'runtime/erosion-test-v1').exists()


def test_future_or_naive_clock_rejected(public_js2):
    root, ref, _ = public_js2
    for now in (datetime.now(), datetime(2020,1,1,tzinfo=timezone.utc)):
        with pytest.raises(ValueError):
            app.build_source_native_operating_erosion(root=root,candidate_binding=ref,
                output_dir=root/'runtime/not-created',now=now)


@pytest.mark.parametrize('damage', ['issuer', 'url', 'hash', 'unsupported_symbol'])
def test_readonly_provider_rejects_wrong_official_identity(public_js2, damage):
    root, ref, _ = public_js2
    candidate = json.loads((root/ref['path']).read_bytes())
    package = json.loads((root/candidate['source_package_binding']['path']).read_bytes())
    sources = deepcopy(package['sources'])
    symbol = candidate['symbol']
    annual = next(s for s in sources if s['id']=='cninfo:1225114741')
    if damage == 'issuer': annual['issuer_identity']['security_code'] = '000000'
    elif damage == 'url': annual['location'] = 'https://example.invalid/NOT_OFFICIAL.pdf'
    elif damage == 'hash': annual['sha256'] = '0'*64
    else: symbol = '600887'
    with pytest.raises(ValueError):
        app.source_provider.read_operating_erosion_sources(root=root,symbol=symbol,sources=sources,fields=app.FIELDS)


@pytest.mark.parametrize('damage', ['revenue_missing', 'volume_missing', 'header_missing', 'extra_wine_row'])
def test_real_table_extraction_corruption_rejects_without_borrowing(public_js2, monkeypatch, damage):
    """Fault-inject extraction output only; native source verifier is real."""
    root, ref, _ = public_js2
    extract = app.source_provider.extract_pages
    def corrupted(*args, **kwargs):
        pages = list(extract(*args, **kwargs))
        if damage == 'revenue_missing': pages[9] = pages[9].replace('91.23 -1.08 8.63', '91.23 8.63')
        elif damage == 'volume_missing': pages[9] = pages[9].replace('11.25 2.13 9.67', '11.25 9.67')
        elif damage == 'header_missing': pages[9] = pages[9].replace('主营业务分产品情况', 'MISSING')
        else: pages[9] = pages[9].replace('酒类 吨 ', '酒类 吨 1 1 1 1 1 1\n酒类 吨 ')
        return pages
    monkeypatch.setattr(app.source_provider, 'extract_pages', corrupted)
    with pytest.raises(ValueError, match='boundaries|row shape'): run(root, ref)
    assert not (root/'runtime/erosion-test-v1').exists()


@pytest.mark.parametrize('damage', ['official', 'ledger', 'package'])
def test_final_original_closure_rechecked_after_actual_native_prepare(public_js2, monkeypatch, damage):
    root, ref, _ = public_js2
    original = json.loads((root/ref['path']).read_bytes())
    package = json.loads((root/original['source_package_binding']['path']).read_bytes())
    if damage == 'official':
        path = next(x['local_path'] for x in package['sources'] if x['id']=='cninfo:1225114741')
    else:
        path = original['native_cash_ledger_binding' if damage == 'ledger' else 'source_package_binding']['path']
    prepare = app.prepare_source_native_candidate
    def drift(**kwargs):
        result = prepare(**kwargs)
        target = root/path
        target.write_bytes(target.read_bytes()+b'\nTEST_ONLY_AFTER_NATIVE_REPLAY')
        return result
    monkeypatch.setattr(app, 'prepare_source_native_candidate', drift)
    with pytest.raises(ValueError, match='Original source closure drift'): run(root, ref)

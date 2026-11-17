"""Scoped consumers use TEST_ONLY parser fixtures, not production/PIT approval."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import os

import pytest

from test_official_universe import SATURDAY, v2_documents  # noqa: F401
from test_official_universe_partial import coverage_documents, retained_partial  # noqa: F401
from test_m2_opportunity_discovery import (
    RUN_M2, _tencent_payload, _sina_payload, _dividend_payload, _financial_points,
)
from value_investment_agent.application.discovery.scoped_screening import (
    VERSION, scoped_inputs, build_discovery_receipt,
)
from value_investment_agent.application.discovery.current_scan import current_scan_details
from value_investment_agent.application.product.value_discovery_surface import project_value_discovery_report
from value_investment_agent.application.product.daily_refresh import _screening_summary
from value_investment_agent.infrastructure.screening import evidence_screen_v3
from value_investment_agent.m2_discovery_engine import M2ScreeningPolicy
from value_investment_agent.m2_opportunity_discovery import EvidenceReference


@pytest.fixture
def scan(tmp_path, coverage_documents):
    output = tmp_path / 'runtime/daily-marketwide/scoped-test'
    output.mkdir(parents=True)
    official = retained_partial(coverage_documents, output)
    tencent, sina = _tencent_payload(), _sina_payload()
    for symbol in ('920000', '603999'):
        tencent['rows'].append(dict(tencent['rows'][0], code='bj' + symbol))
        sina['rows'].append(dict(sina['rows'][0], code=symbol))
    refs = {}
    for key, payload in dict(official=official, tencent=tencent, sina=sina,
                             dividend=_dividend_payload()).items():
        raw = json.dumps(payload).encode()
        path = output / (key + '.json')
        path.write_bytes(raw)
        refs[key] = EvidenceReference(id=key, path=path.relative_to(tmp_path).as_posix(),
            sha256=sha256(raw).hexdigest(), source_name='TEST_ONLY',
            source_url='https://example.test/' + key, fetched_at=SATURDAY)
    return tmp_path, output, dict(run_id='scope-test',
        generated_at=SATURDAY + timedelta(seconds=3), official_payload=official,
        tencent_payload=tencent, sina_payload=sina, dividend_payload=_dividend_payload(),
        financial_points=_financial_points(), quote_date='2026-10-23', run_refs=refs,
        policy=M2ScreeningPolicy(), quote_date_verified=False)


def test_scope_filters_only_observed_members_and_accounts_for_all_other_quotes(scan):
    root, _, kwargs = scan
    original = deepcopy(kwargs)
    tencent, sina, scope = scoped_inputs(root=root, official_payload=kwargs['official_payload'],
        tencent_payload=kwargs['tencent_payload'], sina_payload=kwargs['sina_payload'])
    assert kwargs == original
    assert scope['all_a_complete'] is False
    assert scope['observed_universe_count'] == 4003
    assert scope['covered_venues'] == ['SZSE', 'SSE']
    assert scope['failed_venues'] == ['BSE']
    assert scope['venue_coverage']['BSE']['record_count'] is None
    for provider in scope['quote_coverage'].values():
        assert provider['received_row_count'] == 6
        assert provider['scoped_row_count'] == 4
        assert provider['excluded_row_count'] == 2
        assert {row['symbol'] for row in provider['excluded_quotes']} == {'920000', '603999'}
        assert all(row['reason'] == 'NOT_IN_OBSERVED_OFFICIAL_LIST_NOT_PROOF_OF_DELISTING'
                   for row in provider['excluded_quotes'])
    actual = build_discovery_receipt(root=root, **kwargs)
    baseline = evidence_screen_v3.build_discovery_receipt(**dict(kwargs,
        tencent_payload=tencent, sina_payload=sina))
    assert actual.rule_version == VERSION
    assert actual.channel_results == baseline.channel_results
    assert actual.candidate_signature == baseline.candidate_signature
    assert actual.coverage_signature == baseline.coverage_signature
    assert actual.universe.complete is False
    assert actual.data_health.status == 'PARTIAL'
    assert actual.data_health.quote_count == 4
    assert actual.data_health.extra_quote_count == 0
    assert actual.data_health.missing_quote_count == 3999
    assert actual.action == 'no_order'


def test_scope_replays_raw_sources_and_cannot_claim_complete_or_zero_failed_venue(scan):
    root, _, kwargs = scan
    for key, value in [('complete', True), ('covered_venues', ['SZSE', 'SSE', 'BSE'])]:
        changed = deepcopy(kwargs)
        changed['official_payload'][key] = value
        with pytest.raises(ValueError):
            build_discovery_receipt(root=root, **changed)
    binding = kwargs['official_payload']['sources'][0]
    from pathlib import Path
    Path(binding['local_path']).write_bytes(b'CHANGED_TEST_ONLY')
    with pytest.raises(ValueError):
        build_discovery_receipt(root=root, **kwargs)


def test_scoped_report_and_daily_read_model_preserve_coverage_and_exclusions(scan):
    root, output, kwargs = scan
    receipt = build_discovery_receipt(root=root, **kwargs)
    raw = json.dumps(receipt.as_policy()).encode()
    path = output / 'receipt.json'
    path.write_bytes(raw)
    binding = dict(path=path.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())
    report = project_value_discovery_report(root=root, receipt_path=path, receipt_sha256=binding['sha256'])
    scope = report['screening_scope']
    assert scope['all_a_complete'] is False
    assert scope['quote_coverage']['tencent']['excluded_row_count'] == 2
    assert all(row['symbol'] not in {'920000', '603999'} for row in report['leads'])
    report_path = output / 'report.json'
    raw = json.dumps(report).encode()
    report_path.write_bytes(raw)
    files = dict(receipt=binding, lead_report=dict(path=report_path.relative_to(root).as_posix(),
        sha256=sha256(raw).hexdigest()))
    summary = dict(as_of=report['as_of'], channel_counts=report['channel_counts'],
        data_health=report['data_health'], screening_scope=scope, action='no_order',
        input_mode='LIVE_COLLECTION', rule_version=VERSION, lead_count=len(report['leads']))
    manifest = dict(summary=summary, files=files)
    details = current_scan_details(root, manifest)
    assert details['status'] == 'SOURCE_REVALIDATED'
    assert details['summary']['screening_scope'] == scope
    manifest_path = output / 'manifest.json'
    raw = json.dumps(manifest).encode()
    manifest_path.write_bytes(raw)
    daily = _screening_summary(root, dict(manifest_path=manifest_path.relative_to(root).as_posix(),
        manifest_sha256=sha256(raw).hexdigest()))
    assert daily['status'] == 'VERIFIED_RESEARCH_SCAN'
    assert daily['screening_scope'] == scope
    assert daily['formal_eligibility'] is False
    summary['screening_scope'] = dict(scope, all_a_complete=True)
    assert current_scan_details(root, manifest)['status'] == 'SOURCE_REVALIDATION_FAILED'


def test_registered_cli_runs_and_replays_partial_scope_without_new_market_data(scan, monkeypatch):
    root, output, kwargs = scan
    from datetime import datetime

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (SATURDAY + timedelta(seconds=5)).astimezone(tz)

    def official(directory, project):
        raw = RUN_M2._json_bytes(kwargs['official_payload'])
        path = RUN_M2._write(directory, 'official-universe.json', raw)
        return kwargs['official_payload'], RUN_M2._reference('official', path, root=project,
            source_name='TEST_ONLY', source_url='https://example.test',
            fetched_at=SATURDAY + timedelta(seconds=2))

    def market(value):
        payload = dict(value, fetched_at=SATURDAY.isoformat())
        return RUN_M2._json_bytes(payload), payload

    monkeypatch.setattr(RUN_M2, 'datetime', Clock)
    monkeypatch.setattr(RUN_M2, '_collect_official', official)
    monkeypatch.setattr(RUN_M2, 'fetch_tencent_board_rank', lambda: market(kwargs['tencent_payload']))
    monkeypatch.setattr(RUN_M2, 'fetch_sina_industry_quotes', lambda: market(kwargs['sina_payload']))
    monkeypatch.setattr(RUN_M2, 'fetch_eastmoney_dividends', lambda **_: market(kwargs['dividend_payload']))
    summary = RUN_M2.run_once(root=root, output_dir=output, wps_dir=None, max_per_channel=50,
        skip_dividend=False, reuse_inputs=False, project_leads=True, skip_workbook=True)
    assert summary['rule_version'] == VERSION
    assert summary['screening_scope']['all_a_complete'] is False
    assert summary['screening_scope']['quote_coverage']['sina']['excluded_row_count'] == 2
    assert summary['quote_date'] == '2026-10-23'
    assert summary['quote_date_verification'] == 'UNVERIFIED_PROVIDER_TRADE_DATE'
    assert summary['data_health']['quote_count'] == 4
    assert all(summary['replay'].values())
    manifest = json.loads((output / 'manifest.json').read_bytes())
    assert current_scan_details(root, manifest)['status'] == 'SOURCE_REVALIDATED'
    for name in ('_collect_official', 'fetch_tencent_board_rank', 'fetch_sina_industry_quotes',
                 'fetch_eastmoney_dividends', 'build_financial_input'):
        monkeypatch.setattr(RUN_M2, name, lambda *a, **k: pytest.fail('historical replay must not fetch'))
    replay = RUN_M2.run_once(root=root, output_dir=output, wps_dir=None, max_per_channel=50,
        skip_dividend=False, reuse_inputs=True, skip_workbook=True)
    assert replay['rule_version'] == VERSION
    assert replay['input_mode'] == 'HISTORICAL_REPLAY'
    assert replay['screening_scope'] == summary['screening_scope']
    assert replay['candidate_signature'] == summary['candidate_signature']
    assert all(replay['replay'].values())


def test_partial_source_cannot_hide_coverage_by_downgrading_receipt_rule(scan):
    root, output, kwargs = scan
    payload = build_discovery_receipt(root=root, **kwargs).as_policy()
    payload['rule_version'] = evidence_screen_v3.VERSION
    raw = json.dumps(payload).encode()
    path = output / 'receipt.json'
    path.write_bytes(raw)
    with pytest.raises(ValueError, match='Partial official input requires'):
        project_value_discovery_report(root=root, receipt_path=path,
            receipt_sha256=sha256(raw).hexdigest())


@pytest.mark.skipif(not os.environ.get('SCOPED_SCREEN_REAL_ROOT'),
                    reason='Explicit real public collection root required')
def test_new_public_collection_rebuilds_exactly_without_reacquisition():
    from datetime import datetime
    from decimal import Decimal
    from pathlib import Path
    from value_investment_agent.application.discovery.public_financial_input import verify_public_supplement
    from value_investment_agent.m2_opportunity_discovery import evidence_reference_from_payload
    root = Path(os.environ['SCOPED_SCREEN_REAL_ROOT'])
    path = root / 'runtime/daily-marketwide/scoped-live-20261024-1519/manifest.json'
    raw = path.read_bytes()
    assert sha256(raw).hexdigest() == 'b869072fc7e81e839faef841065046b40b52389f5594ae01843179fe140ed4b5'
    manifest = json.loads(raw)
    inputs = {}
    for name, binding in manifest['files'].items():
        raw_input = (root / binding['path']).read_bytes()
        assert sha256(raw_input).hexdigest() == binding['sha256']
        inputs[name] = json.loads(raw_input)
    receipt, policy = inputs['receipt'], inputs['policy']
    defaults = M2ScreeningPolicy()
    fields = {key: Decimal(value) if isinstance(getattr(defaults, key), Decimal) else value
              for key, value in policy.items()}
    when = datetime.fromisoformat(receipt['generated_at'])
    verify_public_supplement(root=root, payload=inputs['financial'], evaluation_at=when)
    rebuilt = build_discovery_receipt(root=root, run_id=receipt['run_id'], generated_at=when,
        official_payload=inputs['official'], tencent_payload=inputs['tencent'],
        sina_payload=inputs['sina'], dividend_payload=inputs['dividend'],
        financial_points=inputs['financial']['points'], quote_date=receipt['quote_date'],
        run_refs={ref['id']: evidence_reference_from_payload(ref) for ref in receipt['evidence_refs']},
        policy=M2ScreeningPolicy(**fields), quote_date_verified=False)
    assert rebuilt.as_policy() == receipt
    assert receipt['universe']['complete'] is False
    assert inputs['official']['covered_venues'] == ['SZSE', 'SSE']
    assert inputs['official']['venue_coverage']['BSE']['record_count'] is None
    official_symbols = {row['symbol'] for row in inputs['official']['records']}
    assert len(official_symbols) == 5224
    assert all(lead['symbol'] in official_symbols for lead in inputs['lead_report']['leads'])
    assert len(inputs['lead_report']['leads']) == 111
    assert inputs['financial']['public_financial_input']['accepted_official_fact_count'] == 0
    assert len(inputs['financial']['points']) == 50055
    assert manifest['summary']['channel_counts']['quality'] == 0
    assert current_scan_details(root, manifest)['status'] == 'SOURCE_REVALIDATED'

"""Isolated TEST_ONLY exchange originals; no economic publication changes."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json

import pytest

from test_security_attributes import published, quantity_original, GENERATED_AT
from value_investment_agent.application.portfolio import security_attributes as application
from value_investment_agent.domain.portfolio.security_attributes import parse_observed_attributes


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


def binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())


@pytest.fixture
def alternate(published):
    root, original, _, raw = published
    folder = root / 'runtime/daily-marketwide/TEST_ONLY'
    folder.mkdir(parents=True)
    original_path = folder / 'original.json'
    original_path.write_bytes(raw.read_bytes())
    universe = deepcopy(original)
    stamp = GENERATED_AT + timedelta(days=1)
    universe['fetched_at'] = stamp.isoformat()
    source = universe['sources'][0]
    source.update(local_path=original_path.relative_to(root).as_posix(), fetched_at=stamp.isoformat())
    # Raw/normalized fields are checked, not an economic or liquidity claim.
    universe.update(current_price='999', cyclical=False, liquidity_profile='LIQUID')
    universe['records'][0]['name'] = 'TEST_ONLY_FRESH'
    data = json.loads(original_path.read_bytes())
    data['result'][0]['SEC_NAME_CN'] = 'TEST_ONLY_FRESH'
    write(original_path, data)
    source['sha256'] = sha256(original_path.read_bytes()).hexdigest()
    value = dict(root=root, folder=folder, universe=universe, original=original_path,
        manifest=dict(schema_version='m2-run-manifest-v1', files={}, summary=dict(
            action='no_order', input_mode='LIVE_COLLECTION', rule_version='m2-evidence-screen-v3',
            current_publication_eligible=False, quote_date_verification='UNVERIFIED')),
        run=dict(schema_version='daily-workbench-run-v1', action='no_order', mode='SAFE_REFRESH',
            marketwide_screen=dict(status='RESEARCH_ONLY', current_publication_eligible=False)))
    rebind(value)
    return value


def rebind(value):
    root, folder = value['root'], value['folder']
    write(folder / 'official-universe.json', value['universe'])
    value['manifest']['files']['official'] = binding(root, folder / 'official-universe.json')
    write(folder / 'manifest.json', value['manifest'])
    value['run']['marketwide_screen'].update(manifest_path=(folder / 'manifest.json').relative_to(root).as_posix(),
        manifest_sha256=sha256((folder / 'manifest.json').read_bytes()).hexdigest())
    write(root / '.tmp/daily-workbench-latest-run.json', value['run'])


def read(value, now=None, symbols=('600519',)):
    return application.load_verified_security_attributes(value['root'], symbols,
        now=now or GENERATED_AT + timedelta(days=2))


def test_stale_publication_uses_fresh_alternate_and_quantity_originals(alternate, quantity_original):
    now = GENERATED_AT + timedelta(days=8)
    alternate['universe']['fetched_at'] = (now - timedelta(minutes=1)).isoformat()
    alternate['universe']['sources'][0]['fetched_at'] = alternate['universe']['fetched_at']
    rebind(alternate)
    root, _, receipt_path, receipt = quantity_original
    receipt['known_at'] = (now - timedelta(days=1)).isoformat()
    write(receipt_path, receipt)
    before = {p: p.read_bytes() for p in [root / 'runtime/report.json', root / 'runtime/receipt.json',
        root / 'runtime/universe.json', alternate['folder'] / 'manifest.json', alternate['original']]}
    row = read(alternate, now)[0]
    assert row['company_name'] == 'TEST_ONLY_FRESH'
    assert row['trading_rules']['minimum_buy_quantity'] == 100
    assert row['trading_rules']['buy_quantity_increment'] == 100
    assert row['industry'] == 'CSRC_SECTION:C' and row['exchange'] == 'SSE'
    assert row['historical_pit'] is False and row['published_at'] is None
    assert row['classification_effective_date'] is None
    assert all(row[key] == 'UNKNOWN' for key in ('cyclical', 'common_factors', 'liquidity_profile'))
    assert all(key not in row for key in ('current_price', 'current_publication_eligible', 'trade_eligible', 'formal_eligibility'))
    assert row['action'] == row['trading_rules']['action'] == 'no_order'
    assert parse_observed_attributes(row, now=now).gaps == ('cyclical', 'common_factors', 'liquidity_profile')
    assert any(ref['source_role'] == 'CURRENT_OFFICIAL_UNIVERSE' for ref in row['evidence_refs'])
    assert all(ref['source_role'] != 'PUBLISHED_OFFICIAL_UNIVERSE' for ref in row['field_evidence']['symbol'])
    assert all(p.read_bytes() == content for p, content in before.items())


@pytest.mark.parametrize('change', ['missing', 'manifest_hash', 'official_hash', 'original_hash',
    'manifest_traversal', 'official_traversal', 'original_traversal', 'future_capture', 'future_source',
    'naive_capture', 'identity', 'endpoint', 'latest_schema', 'latest_action', 'manifest_schema',
    'manifest_action', 'foreign_parser', 'foreign_mode', 'expired'])
def test_unusable_alternate_falls_back_to_verified_published_source(alternate, change):
    value, root = alternate, alternate['root']
    if change == 'future_capture':
        value['universe']['fetched_at'] = (GENERATED_AT + timedelta(days=3)).isoformat()
    elif change == 'future_source':
        value['universe']['sources'][0]['fetched_at'] = (GENERATED_AT + timedelta(days=3)).isoformat()
    elif change == 'naive_capture':
        value['universe']['fetched_at'] = GENERATED_AT.replace(tzinfo=None).isoformat()
    elif change == 'identity':
        value['universe']['records'][0]['security_type'] = 'ETF'
    elif change == 'endpoint':
        value['universe']['sources'][0]['url'] = 'https://evil.test/list'
    elif change == 'original_traversal':
        value['universe']['sources'][0]['local_path'] = '../outside.json'
    elif change == 'latest_schema':
        value['run']['schema_version'] = 'foreign'
    elif change == 'latest_action':
        value['run']['action'] = 'order'
    elif change == 'manifest_schema':
        value['manifest']['schema_version'] = 'foreign'
    elif change == 'manifest_action':
        value['manifest']['summary']['action'] = 'order'
    elif change == 'foreign_parser':
        value['universe']['parser_version'] = 'foreign'
    elif change == 'foreign_mode':
        value['manifest']['summary']['input_mode'] = 'REPLAY'
    elif change == 'expired':
        stamp = GENERATED_AT - timedelta(days=8)
        value['universe']['fetched_at'] = stamp.isoformat()
        value['universe']['sources'][0]['fetched_at'] = stamp.isoformat()
    rebind(value)
    latest = root / '.tmp/daily-workbench-latest-run.json'
    if change == 'missing':
        latest.unlink()
    elif change == 'manifest_hash':
        (value['folder'] / 'manifest.json').write_bytes(b'{}')
    elif change == 'official_hash':
        (value['folder'] / 'official-universe.json').write_bytes(b'{}')
    elif change == 'original_hash':
        value['original'].write_bytes(b'changed')
    elif change == 'manifest_traversal':
        value['run']['marketwide_screen']['manifest_path'] = 'runtime/daily-marketwide/TEST_ONLY/../TEST_ONLY/manifest.json'
        write(latest, value['run'])
    elif change == 'official_traversal':
        value['manifest']['files']['official']['path'] = 'runtime/daily-marketwide/TEST_ONLY/../TEST_ONLY/official-universe.json'
        write(value['folder'] / 'manifest.json', value['manifest'])
        value['run']['marketwide_screen']['manifest_sha256'] = sha256((value['folder'] / 'manifest.json').read_bytes()).hexdigest()
        write(latest, value['run'])
    assert read(value)[0]['company_name'] == 'TEST_ONLY'


def test_freshest_original_wins_over_late_aggregate_time(alternate):
    # An older source is not fresher because its universe was assembled later.
    alternate['universe']['sources'][0]['fetched_at'] = (GENERATED_AT - timedelta(days=1)).isoformat()
    rebind(alternate)
    assert read(alternate)[0]['company_name'] == 'TEST_ONLY'


def test_valid_empty_does_not_resurrect_older_identity_and_absence_falls_back(alternate):
    raw = json.loads(alternate['original'].read_bytes())
    raw['result'][0]['A_STOCK_CODE'] = '600693'
    write(alternate['original'], raw)
    alternate['universe']['sources'][0]['sha256'] = sha256(alternate['original'].read_bytes()).hexdigest()
    alternate['universe']['records'][0]['symbol'] = '600693'
    rebind(alternate)
    assert read(alternate) == []
    assert read(alternate, symbols=('600693',))[0]['symbol'] == '600693'
    (alternate['root'] / '.tmp/daily-workbench-latest-run.json').unlink()
    assert read(alternate)[0]['company_name'] == 'TEST_ONLY'


def test_absent_publication_can_use_alternate_but_corrupt_both_is_unavailable(alternate, monkeypatch):
    def unavailable(root):
        raise ValueError('TEST_ONLY unavailable publication')
    monkeypatch.setattr(application, 'load_current_chain', unavailable)
    assert read(alternate)[0]['company_name'] == 'TEST_ONLY_FRESH'
    alternate['original'].write_bytes(b'changed')
    assert read(alternate) is None


def test_all_expired_is_empty_not_unverified_and_naive_read_is_rejected(alternate):
    assert read(alternate, GENERATED_AT + timedelta(days=9)) == []
    assert read(alternate, GENERATED_AT.replace(tzinfo=None)) is None


@pytest.mark.parametrize('change', ['future_capture', 'future_source', 'source_after_capture'])
def test_future_valid_empty_alternate_cannot_displace_available_publication(alternate, change):
    raw = json.loads(alternate['original'].read_bytes())
    raw['result'][0]['A_STOCK_CODE'] = '600693'
    write(alternate['original'], raw)
    source = alternate['universe']['sources'][0]
    source['sha256'] = sha256(alternate['original'].read_bytes()).hexdigest()
    alternate['universe']['records'][0]['symbol'] = '600693'
    if change == 'future_capture':
        alternate['universe']['fetched_at'] = (GENERATED_AT + timedelta(days=3)).isoformat()
    elif change == 'future_source':
        source['fetched_at'] = (GENERATED_AT + timedelta(days=3)).isoformat()
    else:
        source['fetched_at'] = (GENERATED_AT + timedelta(days=1, hours=1)).isoformat()
    rebind(alternate)
    row = read(alternate)[0]
    assert row['company_name'] == 'TEST_ONLY'
    assert row['known_at'] == GENERATED_AT.isoformat()
    assert row['historical_pit'] is False
    assert row['cyclical'] == row['liquidity_profile'] == row['common_factors'] == 'UNKNOWN'


def test_valid_capture_controls_known_at_without_price_or_economic_elevation(alternate):
    captured = GENERATED_AT + timedelta(days=1, minutes=2)
    alternate['universe']['fetched_at'] = captured.isoformat()
    rebind(alternate)
    row = read(alternate)[0]
    assert row['known_at'] == captured.isoformat()
    assert row['known_at'] != (GENERATED_AT + timedelta(days=2)).isoformat()
    assert row['valid_until'] == (GENERATED_AT + timedelta(days=8)).isoformat()
    assert row['published_at'] is None and not row['historical_pit']
    assert all(key not in row for key in ('current_price', 'formal_eligibility', 'current_publication_eligible'))

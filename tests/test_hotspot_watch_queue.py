import hashlib
import json

import pytest

from value_investment_agent.application.hotspot.watch_queue import build_hotspot_watch_queue


def _binding(tmp_path, name, day, *, quote_day=None, source_ref='a' * 64):
    path = tmp_path / name
    report = {
        'schema_version': 'hotspot-observation-report-v1', 'action': 'no_order',
        'classification_as_of': day, 'confirmed_market_date': quote_day or day,
        'sources': [{'role': 'industry', 'sha256': 'a' * 64}],
        'themes': [{'theme': 'Sector', 'classification': 'SINA_SHENWAN',
                    'status': 'HISTORICAL_SNAPSHOT_OBSERVATION',
                    'equal_weight_change_percent': '2'}],
        'observation_list': [{'symbol': '600519', 'industry': 'Sector',
                              'source_refs': [source_ref], 'action': 'no_order'}],
        'dated_quote_observations': [{'symbol': '600519', 'quote_date': quote_day or day,
                                      'status': 'DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION',
                                      'source_hashes': ['b' * 64, 'c' * 64], 'action': 'no_order'}],
    }
    path.write_text(json.dumps(report), encoding='utf-8')
    return {'path': path, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def test_queue_is_research_only_and_continuity_requires_distinct_dates(tmp_path):
    first = _binding(tmp_path, 'first.json', '2026-10-08')
    second = _binding(tmp_path, 'second.json', '2026-10-09')
    single = build_hotspot_watch_queue([first])
    assert single['continuity_status'] == 'UNKNOWN'
    queue = build_hotspot_watch_queue([first, second])
    assert queue['status'] == 'HOTSPOT_WATCH_QUEUE'
    assert queue['action'] == 'no_order'
    assert queue['continuity_status'] == 'OBSERVED'
    assert len(queue['items']) == 1
    item = queue['items'][0]
    assert (item['symbol'], item['theme'], item['date']) == ('600519', 'Sector', '2026-10-09')
    assert item['priority'] == 'REVIEW_CONTINUITY'
    assert item['evidence']['report_sha256'] == second['sha256']
    assert 'price' not in item and 'signal' not in item and item['action'] == 'no_order'


@pytest.mark.parametrize('day,quote_day', [('UNKNOWN', None), ('2026-10-09', '2026-10-08')])
def test_undated_or_conflicting_session_fails_closed(tmp_path, day, quote_day):
    binding = _binding(tmp_path, 'report.json', day, quote_day=quote_day)
    with pytest.raises(ValueError):
        build_hotspot_watch_queue([binding])


def test_hash_or_source_mismatch_fails_closed(tmp_path):
    binding = _binding(tmp_path, 'report.json', '2026-10-09')
    binding['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='hash mismatch'):
        build_hotspot_watch_queue([binding])
    mismatched = _binding(tmp_path, 'other.json', '2026-10-09', source_ref='f' * 64)
    with pytest.raises(ValueError, match='source reference mismatch'):
        build_hotspot_watch_queue([mismatched])

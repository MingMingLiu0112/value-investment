"""Candidate audit must stay within current membership and unique evidence."""
import importlib.util
from pathlib import Path
import sys
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('candidate_financing_audit', SCRIPTS / 'audit_candidate_financing.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def payload():
    return {'market_candidates': [{'symbol': '000581'}],
            'financial_quality': [{'symbol': '000581', 'calculation_details': {
                'required_fields': ['interest_bearing_debt'], 'accepted_fields': []}}],
            'disclosures': [{'symbol': '000581', 'report_kind': 'annual',
                'report_period': '2025-12-31', 'sha256': 'a' * 64,
                'source_url': 'https://static.cninfo.com.cn/finalpage/2026-04-17/1225111397.PDF'}]}


def test_duplicate_export_rows_are_one_report():
    data = payload()
    data['filing_candidates'] = data['disclosures'] * 3
    assert len(module.select_reports(data, 5)) == 1


def test_conflicting_archive_hash_requires_revision_review():
    data = payload()
    data['filing_candidates'] = [{**data['disclosures'][0], 'sha256': 'b' * 64}]
    assert module.select_reports(data, 5) == []


def test_nonmember_and_completed_debt_are_not_selected():
    data = payload()
    data['market_candidates'] = []
    assert module.select_reports(data, 5) == []
    data = payload()
    data['financial_quality'][0]['calculation_details']['accepted_fields'] = ['interest_bearing_debt']
    assert module.select_reports(data, 5) == []


def test_nonofficial_or_interim_evidence_is_not_selected():
    for changes in ({'source_url': 'https://example.com/report.pdf'},
                    {'report_kind': 'interim'}, {'report_period': '2024-12-31'},
                    {'sha256': ''}):
        data = payload()
        data['disclosures'][0].update(changes)
        assert module.select_reports(data, 5) == []


def test_pagination_has_no_overlap_for_same_payload():
    data = payload()
    for symbol in ('000700', '000758'):
        data['market_candidates'].append({'symbol': symbol})
        data['financial_quality'].append({**data['financial_quality'][0], 'symbol': symbol})
        data['disclosures'].append({**data['disclosures'][0], 'symbol': symbol})
    first = module.select_reports(data, 2)
    second = module.select_reports(data, 2, offset=2)
    assert [row['symbol'] for row in first + second] == ['000581', '000700', '000758']
    assert module.select_reports(data, 2, offset=3) == []
    with pytest.raises(ValueError):
        module.select_reports(data, 2, offset=-1)

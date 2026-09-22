from pathlib import Path
import hashlib

import pytest

from decimal import Decimal

from value_investment_agent import candidate_review
from value_investment_agent.candidate_review import load_review_rows, reviewed_records, values_agree


def test_review_csv_requires_full_traceability_columns(tmp_path: Path) -> None:
    path = tmp_path / 'reviews.csv'
    path.write_text('candidate_id,confirmed_value\nabc,1\n', encoding='utf-8')

    with pytest.raises(ValueError, match='missing columns'):
        load_review_rows(path)


class _Result:
    def __init__(self, row: dict | None) -> None:
        self.row = row

    def fetchone(self) -> dict | None:
        return self.row


class _Connection:
    def execute(self, _statement: str, _params: tuple) -> _Result:
        return _Result({
            'candidate_id': 'candidate-1', 'field_name': 'roe', 'value': '8.32', 'unit': 'percent',
            'page_number': 8, 'source_label': 'ROE', 'symbol': '600015', 'report_period': '2025-12-31',
            'source_name': 'CNINFO', 'source_url': 'https://www.cninfo.com.cn/a.pdf',
            'published_at': None, 'sha256': 'a' * 64, 'local_path': 'unused.pdf',
            'archive_status': 'server_resident', 'archive_uri': None,
        })


def test_review_rejects_value_mismatch_before_promotion() -> None:
    row = {
        'candidate_id': 'candidate-1', 'confirmed_value': '8.33', 'confirmed_unit': 'percent',
        'report_period': '2025-12-31', 'official_url': 'https://www.cninfo.com.cn/a.pdf',
        'file_sha256': 'a' * 64, 'reviewed_by': 'reviewer',
        'reviewed_at': '2026-09-04T10:00:00+08:00', 'approve': 'yes',
    }

    with pytest.raises(ValueError, match='value differs'):
        reviewed_records(_Connection(), [row])


def test_automatic_cross_source_tolerances_are_unit_specific() -> None:
    assert values_agree(Decimal('8.32'), Decimal('8.36'), 'percent')
    assert not values_agree(Decimal('8.32'), Decimal('8.38'), 'percent')
    assert values_agree(Decimal('19.84'), Decimal('19.85'), 'CNY/share')
    assert not values_agree(Decimal('19.84'), Decimal('19.87'), 'CNY/share')
    assert values_agree(Decimal('1000000'), Decimal('1000900'), 'CNY')
    assert not values_agree(Decimal('1000000'), Decimal('1001100'), 'CNY')


def test_automatic_verification_prefilters_for_matching_independent_evidence() -> None:
    source = Path(candidate_review.__file__).read_text(encoding='utf-8')

    assert 'AND EXISTS (' in source
    assert "p.period_label = o.report_period" in source
    assert "p.unit = c.unit" in source
    assert "abs(c.value - p.value) <= 0.05" in source
    assert "abs(c.value - p.value) <= 0.02" in source
    assert source.count("AND NOT (p.field_name = 'revenue' AND d.source_name = 'AkShare / Sina financial abstract')") == 2
    assert source.count("AND p.validation_status IN ('pending', 'verified')") == 2
    assert "AND p.validation_status <> 'failed'" not in source
    assert source.count("AND NOT (COALESCE(p.metadata, '{}'::jsonb) ? 'evidence_quarantine')") == 2


@pytest.mark.parametrize('tampered', [False, True])
@pytest.mark.parametrize('prior_state', ['none', 'quarantined', 'verified', 'other_quarantine'])
def test_automatic_promotion_retains_actual_pdf_hash(tmp_path, tampered, prior_state):
    payload = b'%PDF-1.7 official test fixture'
    path = tmp_path / 'filing.pdf'
    path.write_bytes(payload + (b'changed' if tampered else b''))
    candidate = _Connection().execute('', ()).fetchone()
    candidate.update(local_path=str(path), sha256=hashlib.sha256(payload).hexdigest(),
                     excerpt='单位依据（PDF第64页）：财务附注中报表的单位为：元')

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return None

    class Connection:
        def execute(self, sql, params):
            if 'FROM filing_candidates c JOIN' in sql:
                return Result([candidate])
            if 'SELECT data_point_id, validation_status, metadata FROM data_points' in sql:
                if prior_state == 'none':
                    return Result([])
                return Result([dict(data_point_id='old-point',
                    validation_status='verified' if prior_state == 'verified' else 'failed',
                    metadata={'evidence_quarantine': {'reason':
                        'unrelated' if prior_state == 'other_quarantine'
                        else 'total_revenue_used_as_operating_revenue'}})])
            return Result([dict(value='8.32', unit='percent', data_point_id='secondary',
                                source_id='source', source_name='structured',
                                source_url='https://example.org/structured')])

    records = candidate_review.automatically_verified_candidates(Connection(), 1)
    assert iter(records) is records
    if prior_state in {'verified', 'other_quarantine'}:
        assert list(records) == []
        return
    if tampered:
        with pytest.raises(ValueError, match='hash no longer matches'):
            next(records)
    else:
        _, record = next(records)
        assert record.raw_payload == payload
        assert hashlib.sha256(record.raw_payload).hexdigest() == candidate['sha256']
        assert record.point_metadata['official_file_hash_verified_at_promotion'] is True
        assert record.point_metadata['candidate_excerpt'] == candidate['excerpt']
        if prior_state == 'quarantined':
            assert record.point_metadata['reverification']['previous_data_point_ids'] == ['old-point']
        else:
            assert 'reverification' not in record.point_metadata
        assert list(records) == []
def test_wrong_year_growth_never_reaches_secondary_matching():
    class Result:
        def fetchall(self):
            return [{'field_name': 'revenue_yoy', 'report_period': '2025-12-31',
                     'excerpt': '2024 年 2023 年 本年比上年增减'}]

    class Connection:
        def execute(self, sql, params):
            assert 'FROM filing_candidates c JOIN' in sql
            assert 'c.excerpt' in sql
            return Result()

    assert list(candidate_review.automatically_verified_candidates(Connection(), 1)) == []

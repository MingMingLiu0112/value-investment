from pathlib import Path

import pytest

from decimal import Decimal

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

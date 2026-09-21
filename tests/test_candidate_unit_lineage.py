import pytest
from value_investment_agent.db import candidate_evidence_excerpt, store_filing_candidates


def test_report_unit_survives_long_excerpt_truncation():
    text = candidate_evidence_excerpt({'excerpt': 'x' * 2000, 'unit_evidence_page': 64,
                                      'unit_evidence_excerpt': '财务附注中报表的单位为：元'})
    assert text.startswith('单位依据（PDF第64页）：财务附注中报表的单位为：元')
    assert len(text) == 1000


@pytest.mark.parametrize('page,declaration', [(True, '元'), (0, '元'), (64, ''), (None, '元'), (64, None)])
def test_incomplete_evidence_is_rejected(page, declaration):
    with pytest.raises(ValueError):
        candidate_evidence_excerpt({'excerpt': 'amount', 'unit_evidence_page': page,
                                    'unit_evidence_excerpt': declaration})


def test_legacy_excerpt_unchanged():
    assert candidate_evidence_excerpt({'excerpt': 'plain'}) == 'plain'


def test_database_insert_receives_unit_context():
    class DB:
        def cursor(self):
            return self

        def executemany(self, sql, rows):
            self.rows = rows
    db = DB()
    row = dict(field_name='cash', value='100', unit='CNY', page=66, source_label='货币资金',
               excerpt='货币资金 100', status='candidate_pending_automated_verification',
               unit_evidence_page=64, unit_evidence_excerpt='财务附注中报表的单位为：元')
    store_filing_candidates(db, 'unused', [row])
    assert 'PDF第64页' in db.rows[0][7]
    assert db.rows[0][5] == 66

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from register_cross_page_debt_candidate import PDF_HASH, FIELD, reviewed_row


def packet():
    return {'sha256': PDF_HASH, 'candidates': [{'field_name': FIELD,
        'value': '468249668.22', 'unit': 'CNY', 'page': 80,
        'excerpt': '标签续页依据（PDF第81页首个正文行）：债'}]}


def test_accepts_only_reviewed_candidate():
    assert reviewed_row(packet())['value'] == '468249668.22'


@pytest.mark.parametrize('key,value', [('value', '20249668.22'), ('unit', 'CNY/share'),
    ('page', 83), ('excerpt', 'missing continuation')])
def test_rejects_changed_scope_or_evidence(key, value):
    data = packet()
    data['candidates'][0][key] = value
    with pytest.raises(ValueError):
        reviewed_row(data)


def test_rejects_wrong_original_and_duplicate():
    data = packet()
    data['sha256'] = 'bad'
    with pytest.raises(ValueError):
        reviewed_row(data)
    data = packet()
    data['candidates'] *= 2
    with pytest.raises(ValueError):
        reviewed_row(data)

from scripts.compare_filing_parser_release import compare


def fact(value='10', page=1):
    return dict(field_name='net_income', value=value, unit='CNY', page=page)


def test_changed_values_preserve_both_sides():
    result = compare([fact()], [fact('20')])
    assert result['added'][0]['value'] == '20'
    assert result['removed'][0]['value'] == '10'


def test_duplicates_and_cross_page_conflicts_are_not_hidden():
    result = compare([], [fact(), fact(), fact('20', 2)])
    assert result['duplicate_facts'][0]['count'] == 2
    assert result['multiple_values'] == {'net_income': [('10', 'CNY'), ('20', 'CNY')]}


def test_excerpt_change_does_not_masquerade_as_amount_change():
    assert compare([fact()], [{**fact(), 'excerpt': 'new context'}])['added'] == []

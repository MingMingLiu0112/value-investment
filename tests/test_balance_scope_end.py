from value_investment_agent.filing_extract import extract_candidates_from_pages


def test_balance_scope_does_not_leak_into_lease_notes():
    pages = [
        '\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u5143\n'
        '\u79df\u8d41\u8d1f\u503a 5346222316.27\n'
        '\u8d1f\u503a\u548c\u6240\u6709\u8005\u6743\u76ca\u603b\u8ba1 10000000000.00\n',
        '\u672c\u96c6\u56e2\u5728\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\u4e2d\u5217\u793a\n'
        '\u5355\u4f4d\uff1a\u5143\n\u79df\u8d41\u8d1f\u503a 6748552385.18\n',
        '\u79df\u8d41\u8d1f\u503a 1793493344.21\n',
    ]
    rows = extract_candidates_from_pages(pages)
    leases = [r for r in rows if r['field_name'] == 'lease_liabilities_noncurrent']
    assert [(r['page'], r['value']) for r in leases] == [(1, '5346222316.27')]


def test_new_explicit_statement_can_reopen_after_total():
    pages = [
        '\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u5143\n'
        '\u8d1f\u503a\u53ca\u80a1\u4e1c\u6743\u76ca\u603b\u8ba1 100.00\n',
        '\u5408\u5e76\u5229\u6da6\u8868\n\u5355\u4f4d\uff1a\u5143\n'
        '\u8425\u4e1a\u6210\u672c 50.00\n',
    ]
    assert any(r['field_name'] == 'operating_cost' and r['value'] == '50.00'
               for r in extract_candidates_from_pages(pages))

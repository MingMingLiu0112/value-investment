from value_investment_agent.filing_extract import extract_candidates_from_pages
from value_investment_agent.adapters import SinaFinancialStatementsAdapter
from value_investment_agent.candidate_review import AUTOMATIC_FIELD_MAP
from value_investment_agent.derived_financials import build_verified_derivations
from decimal import Decimal


def test_consolidated_payables_are_separate_from_financing_classification():
    pages = ['\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u5143\n'
             '\u957f\u671f\u5e94\u4ed8\u6b3e 856,562,918.59 1,041,981,625.57\n'
             '\u6bcd\u516c\u53f8\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u5143\n'
             '\u957f\u671f\u5e94\u4ed8\u6b3e 250,000,000.00 500,000,000.00\n']
    rows = extract_candidates_from_pages(pages)
    assert [(r['field_name'], r['value']) for r in rows] == [
        ('long_term_payables_noncurrent', '856562918.59')]
    assert rows[0]['status'] == 'candidate_pending_automated_verification'


def test_blank_payables_are_not_zero():
    assert extract_candidates_from_pages([
        '\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u5143\n'
        '\u957f\u671f\u5e94\u4ed8\u6b3e\n']) == []


def test_mapping_does_not_add_all_payables_to_debt():
    field = 'long_term_payables_noncurrent'
    assert AUTOMATIC_FIELD_MAP[field] == field
    assert SinaFinancialStatementsAdapter._exact_balance_items['long_term_payables_excluding_special'] == '\u957f\u671f\u5e94\u4ed8\u6b3e'
    assert SinaFinancialStatementsAdapter._exact_balance_items['special_payables_noncurrent'] == '\u4e13\u9879\u5e94\u4ed8\u6b3e'
    assert '\u957f\u671f\u5e94\u4ed8\u6b3e' not in SinaFinancialStatementsAdapter._debt_fields
    assert build_verified_derivations([dict(symbol='000683', field_name=field, value='856562918.59',
        unit='CNY',period_label='2025-12-31',validation_status='verified',
        metadata={'automatic_cross_source_verification':True})], ['000683']) == []


def test_same_snapshot_components_reconcile_real_report():
    values = SinaFinancialStatementsAdapter._payables_components({
        '\u957f\u671f\u5e94\u4ed8\u6b3e': '11525169161.00',
        '\u4e13\u9879\u5e94\u4ed8\u6b3e': '23000000.00'})
    assert sum(values.values()) == Decimal('11548169161.00')


def test_missing_special_payables_never_implies_zero():
    assert SinaFinancialStatementsAdapter._payables_components({
        '\u957f\u671f\u5e94\u4ed8\u6b3e': '856562918.59'}) is None


def test_explicit_zero_special_payables_is_preserved():
    values = SinaFinancialStatementsAdapter._payables_components({
        '\u957f\u671f\u5e94\u4ed8\u6b3e': '10', '\u4e13\u9879\u5e94\u4ed8\u6b3e': '0'})
    assert values['special_payables_noncurrent'] == 0

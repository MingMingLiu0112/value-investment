from value_investment_agent.institution_metrics import parse_tables


HEADER = '(三)母公司的净资本及风险控制指标\n项目 本报告期末 上年度末\n'
ROW = '资本杠杆率(%) 17.21 19.95'


def test_missing_label_can_be_recovered_without_changing_page_or_scope():
    facts = parse_tables(['unreadable'], 'broker', '2026-06-30', fallback_pages=[HEADER + ROW])
    assert len(facts) == 1
    assert facts[0]['value'] == '17.21'
    assert facts[0]['page_number'] == 1
    assert facts[0]['text_engine'] == 'pypdf'
    assert facts[0]['statement_scope'] == '母公司（原文明确）'


def test_conflicting_decoders_or_scopes_are_not_silently_selected():
    primary = [HEADER + ROW]
    assert not parse_tables(primary, 'broker', '2026-06-30',
                            fallback_pages=[HEADER + ROW.replace('17.21', '18.21')])
    assert not parse_tables(primary, 'broker', '2026-06-30',
                            fallback_pages=['项目 本报告期末 上年度末\n' + ROW])


def test_existing_primary_conflict_is_not_rescued_by_fallback():
    primary = [HEADER + ROW, HEADER + ROW.replace('17.21', '18.21')]
    assert not parse_tables(primary, 'broker', '2026-06-30', fallback_pages=[HEADER + ROW])


def test_agreement_retains_decoder_audit_without_duplicate_pages():
    facts = parse_tables([HEADER + ROW], 'broker', '2026-06-30', fallback_pages=[HEADER + ROW])
    assert facts[0]['supporting_pages'] == [1]
    assert facts[0]['supporting_text_engines'] == ['PDFium', 'pypdf']

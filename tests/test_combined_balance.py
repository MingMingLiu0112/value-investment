from value_investment_agent.combined_balance import extract_combined_totals


def test_four_column_scope_and_scale():
    text = ('合并及公司资产负债表\n(除特别注明外，金额单位为人民币千元)\n'
            '资产 附注 2024 年 2023 年 2024 年 2023 年\n合并 合并 公司 公司\n'
            '资产总计 604,351,853 486,038,184 300,151,455 257,433,423\n')
    rows = extract_combined_totals([text])
    assert len(rows)==1 and rows[0]['value']=='604351853000'
    indented = '\n'.join(' \t'+line for line in text.splitlines())
    assert extract_combined_totals([indented])[0]['value']=='604351853000'
    assert not extract_combined_totals([text.replace('合并 合并 公司 公司','公司 公司 合并 合并')])
    assert not extract_combined_totals([text.replace('2024 年 2023 年 2024 年 2023 年','2023 年 2024 年 2023 年 2024 年')])
    assert not extract_combined_totals([text.replace(' 257,433,423','')])
    assert not extract_combined_totals([text+'单位：万元\n'])
    continuation = text.replace('资产负债表\n','资产负债表(续)\n').replace('资产总计','负债合计')
    assert extract_combined_totals([continuation])[0]['field_name']=='total_liabilities'
    assert not extract_combined_totals([continuation.replace('合并 合并 公司 公司','')])


def test_main_parser_integration():
    from value_investment_agent.filing_extract import extract_candidates_from_pages
    text = ('合并及公司资产负债表(续)\n(除特别注明外，金额单位为人民币千元)\n'
            '负债 附注 2024 年 2023 年 2024 年 2023 年\n合并 合并 公司 公司\n'
            '负债合计 376,684,462 311,738,535 193,646,429 195,202,393\n')
    rows = extract_candidates_from_pages([text])
    assert len(rows)==1 and rows[0]['value']=='376684462000'

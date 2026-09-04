from value_investment_agent.filing_extract import extract_candidates_from_pages


def test_extracts_candidate_with_page_and_excerpt() -> None:
    candidates = extract_candidates_from_pages([
        "封面",
        "合并资产负债表\n货币资金 1 53,518,798,979.08 51,690,610,946.50\n短期借款 200.00",
    ])

    cash = next(candidate for candidate in candidates if candidate["field_name"] == "cash")
    assert cash["value"] == "53518798979.08"
    assert cash["page"] == 2
    assert cash["status"] == "candidate_requires_human_review"


def test_extracts_continuation_pages_without_repeating_the_table_title() -> None:
    candidates = extract_candidates_from_pages([
        "合并资产负债表\n货币资金 1 100.00",
        "长期借款 200.00\n应付债券 300.00",
        "母公司资产负债表\n长期借款 999.00",
    ])

    values = {candidate["field_name"]: candidate["value"] for candidate in candidates}
    assert values == {"cash": "100.00", "long_term_borrowings": "200.00", "bonds_payable": "300.00"}

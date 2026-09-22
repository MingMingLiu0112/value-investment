from value_investment_agent.gap_classification import (
    GAP_ASSUMPTION_MISSING,
    GAP_ASSUMPTION_LOW_CONFIDENCE,
    GAP_FACT_MISSING,
    GAP_MODEL_NOT_APPLICABLE,
    GAP_PRICE_DATA_PENDING,
    classify_blockers,
    classify_gap,
)


def test_prefixed_gaps_keep_their_explicit_type_and_field():
    outcome = classify_gap("601088", "ASSUMPTION_MISSING:discount_rate")

    assert outcome.gap_type == GAP_ASSUMPTION_MISSING
    assert outcome.field == "discount_rate"


def test_known_evidence_blocker_is_not_just_more_data():
    outcome = classify_gap("000333", "finance_company_figures_are_not_full_standalone_statements")

    assert outcome.gap_type == GAP_FACT_MISSING


def test_model_scope_blocker_is_not_a_fact_hunt():
    outcome = classify_gap("000333", "industrial_fcff_carve_out")

    assert outcome.gap_type == GAP_MODEL_NOT_APPLICABLE


def test_pending_price_does_not_block_engineering():
    outcome = classify_gap("600519", "price_bridge_pending_external_data")

    assert outcome.gap_type == GAP_PRICE_DATA_PENDING


def test_all_blockers_receive_a_category():
    outcomes = classify_blockers(
        "601088",
        [
            "FACT_MISSING:net_cash_attributable_to_parent",
            "ASSUMPTION_MISSING:discount_rate",
            "industrial_fcff_carve_out",
            "unexpected future label",
        ],
    )

    assert [item.gap_type for item in outcomes] == [
        GAP_FACT_MISSING,
        GAP_ASSUMPTION_MISSING,
        GAP_MODEL_NOT_APPLICABLE,
        "UNCLASSIFIED",
    ]


def test_moutai_valuation_blockers_are_semantically_classified():
    outcomes = classify_blockers(
        "600519",
        [
            "优势持续期已审计为有界假设，实际持续时长尚未经验证实",
            "全年2026母公司可分配现金与子公司回款尚未披露",
            "折现率为有界研究区间，不是未来实际资本成本",
            "低置信度不得升级为研究吸引力",
        ],
    )

    assert [item.gap_type for item in outcomes] == [
        GAP_ASSUMPTION_LOW_CONFIDENCE,
        GAP_FACT_MISSING,
        GAP_ASSUMPTION_LOW_CONFIDENCE,
        GAP_ASSUMPTION_LOW_CONFIDENCE,
    ]

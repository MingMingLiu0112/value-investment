"""TEST_ONLY presentation fixtures; no market calculation or private inputs."""
from copy import deepcopy

import pytest

from value_investment_agent.application.hotspot.report_text import render_hotspot_lifecycle_markdown


EXTERNAL = ["OWNED_ENTRY_THESIS", "CORPORATE_ACTION_COMPARABILITY",
            "INDEPENDENT_STRATEGY_ADMISSION", "EVENT_RISK", "PORTFOLIO_CAPACITY",
            "SELLABLE_QUANTITY_T_PLUS_ONE_AND_EXECUTION"]
CASES = [
    ("CURRENT_DATA_UNAVAILABLE", "UNKNOWN", "当前行情证据不可用"),
    ("ENTRY_STRUCTURE_OBSERVED", "ENTRY_OBSERVATION", "当前开仓结构条件已被观察到"),
    ("ENTRY_STRUCTURE_NOT_QUALIFIED", "WATCH", "当前开仓结构尚不满足"),
    ("ENTRY_EVIDENCE_UNAVAILABLE", "UNKNOWN", "原始参考 case 在指定入场时点不可用"),
    ("ENTRY_CURRENT_RULE_MISMATCH", "UNKNOWN", "本次重算规则不一致"),
    ("ORIGINAL_PROTECTION_BREACHED", "EXIT_STRUCTURE_REVIEW", "后来恢复不能抹去"),
    ("CURRENT_PROTECTION_BREACHED", "EXIT_STRUCTURE_REVIEW", "当前保护条件已触发"),
    ("ENTRY_TO_CURRENT_DATA_INCOMPLETE", "UNKNOWN", "数据不完整"),
    ("CURRENT_REDUCTION_CONDITION_OBSERVED", "REDUCE_STRUCTURE_REVIEW", "当前减仓结构条件"),
    ("CURRENT_ADD_CONDITION_OBSERVED", "ADD_STRUCTURE_REVIEW", "当前加仓结构条件"),
    ("NO_STRUCTURAL_CHANGE_OBSERVED", "HOLD_STRUCTURE_OBSERVATION", "本次未观察到"),
]


def _review(basis="ORIGINAL_PROTECTION_BREACHED", selected="EXIT_STRUCTURE_REVIEW"):
    current = dict(path="runtime/test-only/current-case.json", sha256="a" * 64)
    entry = dict(path="runtime/test-only/entry-case.json", sha256="b" * 64)
    return dict(symbol="600519", evaluated_at="2026-09-24T16:15:00+08:00",
        observed_review=selected, action="no_order", strategy_validation="NOT_PROVEN",
        current_case_binding=current, entry_case_binding=entry,
        original_entry_comparison=dict(original_protection_price="11.00",
            current_rolling_protection_price="9.00", first_breach_at="2026-09-22T11:30:00+08:00",
            first_breach_close="10.00", breach_count=1, inspected_bar_count=12, coverage="COMPLETE"),
        decision_explanation=dict(schema_version="hotspot-lifecycle-explanation-v1",
            selected_review=selected, basis_code=basis,
            decision_path=[dict(check="ORIGINAL_PROTECTION", outcome="BREACHED",
                values=dict(original_protection_price="11.00", current_rolling_protection_price="9.00"),
                evidence_bindings=[entry, current])], why_not_add=[basis],
            required_external_reviews=list(EXTERNAL),
            current_price_observation=dict(price="12.3400", as_of="2026-09-24", available_at="2026-09-24T16:14:00+08:00",
                reference_price_scope="LATEST_COMPLETED_SESSION_DUAL_SOURCE_CLOSE", current_pit=True),
            recomputed_rule_versions=dict(current="test-rule-current-v2", entry="test-rule-entry-v1"),
            source_scope="REFERENCE_CASES_NOT_VERIFIED_OWNERSHIP_OR_ENTRY_THESIS", action="no_order"))


@pytest.mark.parametrize("basis,selected,phrase", CASES)
def test_all_supplied_decision_branches_have_readable_research_only_text(basis, selected, phrase):
    review = _review(basis, selected)
    before = deepcopy(review)
    text = render_hotspot_lifecycle_markdown(review)
    assert phrase in text and basis in text and selected in text
    assert "NOT_PROVEN" in text and "no_order" in text
    assert "参考 case 不等于已拥有的 Entry" in text
    assert "真实成交记录" in text
    assert "HOLD 仅指维持结构观察，不代表原始投资论据（thesis）已验证" in text
    assert "本次重算，不证明原入场当时真实采用了这些规则" in text
    assert "不授予个人加仓或交易权限" in text
    for code in EXTERNAL:
        assert code in text
    assert review == before


def test_original_and_rolling_levels_recovery_times_versions_and_hashes_are_not_recomputed():
    review = _review()
    text = render_hotspot_lifecycle_markdown(review)
    assert "当前价格观察（元）：12.3400" in text
    assert "观察日期：2026-09-24；原件可得时点：2026-09-24T16:14:00+08:00" in text
    assert "原始参考保护价（元）：11.00；当前滚动保护价（元）：9.00" in text
    assert "首次收盘破位时点：2026-09-22T11:30:00+08:00；收盘破位次数：1" in text
    assert "首次破位收盘价（元）：10.00" in text
    assert "当前参考重算规则：test-rule-current-v2" in text
    assert "原始参考重算规则：test-rule-entry-v1" in text
    for binding in (review["current_case_binding"], review["entry_case_binding"]):
        assert binding["path"] in text and binding["sha256"] in text
    # The deliberately unequal versions and recovered price must not cause a
    # renderer to replace the supplied decision with its own rule comparison.
    assert "判定依据：曾收盘跌破原始参考保护价" in text
    assert "ENTRY_CURRENT_RULE_MISMATCH" not in text


@pytest.mark.parametrize("value", [None, {}])
def test_missing_prices_comparison_and_versions_are_unknown_not_zero(value):
    review = _review("CURRENT_DATA_UNAVAILABLE", "UNKNOWN")
    review["original_entry_comparison"] = value
    review["entry_case_binding"] = None
    explanation = review["decision_explanation"]
    explanation.update(current_price_observation=value, recomputed_rule_versions=value,
        decision_path=[dict(check="CURRENT_DATA", outcome="UNKNOWN", values={"price": None}, evidence_bindings=[])])
    text = render_hotspot_lifecycle_markdown(review)
    assert "当前价格观察（元）：未知；观察日期：未知；原件可得时点：未知" in text
    assert "价格范围：未知；当前 PIT 标志：未知" in text
    assert "原始参考保护价（元）：未知；当前滚动保护价（元）：未知" in text
    assert "首次收盘破位时点：未知；收盘破位次数：未知" in text
    assert "已检查 K 线数量：未知" in text
    assert "当前参考重算规则：未知" in text and "原始参考重算规则：未知" in text
    assert "原始参考 case 输入引用：原件：未知；SHA-256：未知" in text
    assert "首次破位收盘价（元）：未知" in text
    assert "证据绑定：未知" in text
    assert "价格：0" not in text and "次数：0" not in text and "0元" not in text
    assert "None" not in text


@pytest.mark.parametrize("scope,pit,label", [
    ("LATEST_COMPLETED_SESSION_DUAL_SOURCE_CLOSE", True, "最近已完成交易时段的双源收盘观察"),
    ("LAST_COMPLETED_CLOSE_DISPLAY_ONLY", False, "最近已完成收盘，仅供展示"),
    ("HISTORICAL_CLOSE_NOT_CURRENT_QUOTE", False, "历史收盘，非当前报价"),
    ("FUTURE_SCOPE", False, "未识别的代码"),
])
@pytest.mark.parametrize("integrity", ["VERIFIED", "NOT_VERIFIED"])
def test_price_scope_and_pit_are_presented_without_deriving_permission(scope, pit, label, integrity):
    review = _review()
    review.update(current_pit=pit, source_integrity=integrity)
    explanation = review["decision_explanation"]
    explanation["current_price_observation"].update(reference_price_scope=scope, current_pit=pit)
    explanation["decision_path"].insert(0, dict(check="CURRENT_DATA", outcome="CURRENT",
        values=dict(current_pit=pit, source_integrity=integrity), evidence_bindings=[review["current_case_binding"]]))
    before = deepcopy(review)
    text = render_hotspot_lifecycle_markdown(review)
    price_section = text.split("## 当前价格与保护价")[1].split("## 本次重算规则与证据")[0]
    pit_label = "是" if pit else "否"
    assert f"价格范围：{label}（{scope}）；当前 PIT 标志：{pit_label}" in price_section
    assert "不是盘中实时价" in price_section
    assert "仅供展示的收盘价不等于当前 PIT 证据" in price_section
    assert f"当前 PIT 标志：{pit_label}；原件完整性状态：{integrity}" in text
    assert "原件完整性核验也不代表策略或交易准入" in text
    assert "NOT_PROVEN" in text and "订单行为：no_order" in text
    assert review == before


@pytest.mark.parametrize("missing", [True, False])
def test_missing_price_scope_and_pit_remain_unknown_even_with_verified_root_flags(missing):
    review = _review()
    review.update(current_pit=True, source_integrity="VERIFIED")
    price = review["decision_explanation"]["current_price_observation"]
    for key in ("reference_price_scope", "current_pit"):
        if missing:
            del price[key]
        else:
            price[key] = None
    text = render_hotspot_lifecycle_markdown(review)
    assert "价格范围：未知；当前 PIT 标志：未知" in text
    assert "不是盘中实时价" in text


def test_explicit_zero_false_and_all_decision_steps_are_preserved():
    review = _review("ENTRY_TO_CURRENT_DATA_INCOMPLETE", "UNKNOWN")
    review["original_entry_comparison"].update(breach_count=0, first_breach_at=None, coverage="INCOMPLETE")
    explanation = review["decision_explanation"]
    explanation["decision_path"] += [dict(check="CONTINUITY_COVERAGE", outcome="INCOMPLETE",
        values=dict(breach_count=0, observed=False, missing_completed_bars=["2026-09-23T10:30:00+08:00"]),
        evidence_bindings=[dict(path="runtime/test-only/raw-bars.jsonp", sha256="c" * 64)])]
    text = render_hotspot_lifecycle_markdown(review)
    assert text.index("1. 检查：原始参考保护价（ORIGINAL_PROTECTION）") < text.index("2. 检查：连续行情覆盖（CONTINUITY_COVERAGE）")
    assert "收盘破位次数：0" in text and "是否观察到条件：否" in text
    assert "2026-09-23T10:30:00+08:00" in text and "c" * 64 in text
    assert "首次收盘破位时点：未知" in text


@pytest.mark.parametrize("reason,phrase", [
    ("ADD_CONDITION_NOT_OBSERVED", "未观察到加仓结构条件"),
    ("ADD_STRUCTURE_QUALITY_NOT_USABLE", "加仓结构质量不可用于当前判断"),
])
def test_hold_explains_add_blockers_separately_from_external_reviews(reason, phrase):
    review = _review("NO_STRUCTURAL_CHANGE_OBSERVED", "HOLD_STRUCTURE_OBSERVATION")
    review["decision_explanation"]["why_not_add"] = [reason]
    text = render_hotspot_lifecycle_markdown(review)
    assert phrase in text and reason in text
    assert text.index("## 为何不能据此加仓") < text.index(reason) < text.index("## 必须复核事项")


def test_add_observation_without_structural_blocker_does_not_grant_permission():
    review = _review("CURRENT_ADD_CONDITION_OBSERVED", "ADD_STRUCTURE_REVIEW")
    review["decision_explanation"]["why_not_add"] = []
    text = render_hotspot_lifecycle_markdown(review)
    assert "未列明；不代表已获加仓权限" in text
    assert "上述结构结果不能单独作为加仓依据" in text
    assert "核验真实持仓归属及原始入场论据" in text


def test_unknown_codes_and_empty_path_are_retained_without_inventing_a_decision():
    review = _review("FUTURE_BASIS", "UNKNOWN")
    review["decision_explanation"].update(decision_path=[], why_not_add=["FUTURE_BLOCKER"],
        required_external_reviews=["FUTURE_REVIEW"])
    text = render_hotspot_lifecycle_markdown(review)
    assert "未识别的代码（FUTURE_BASIS）" in text
    assert "FUTURE_BLOCKER" in text and "FUTURE_REVIEW" in text
    assert "判定路径：未知" in text


def test_native_path_contract_renders_ten_checks_and_conditional_rule_values():
    review = _review()
    explanation = review["decision_explanation"]
    current, entry = review["current_case_binding"], review["entry_case_binding"]
    path = [
        dict(check="CURRENT_DATA", outcome="CURRENT", values=dict(blockers=[]), evidence_bindings=[current]),
        dict(check="ENTRY_REFERENCE", outcome="VERIFIED_REFERENCE_ONLY",
             values=dict(entry_at="2026-09-21T16:15:00+08:00"), evidence_bindings=[entry]),
        dict(check="ENTRY_RULE_COMPATIBILITY", outcome="MATCH", values=explanation["recomputed_rule_versions"],
             evidence_bindings=[current, entry]),
        dict(check="ORIGINAL_PROTECTION", outcome="BREACHED", values=review["original_entry_comparison"],
             evidence_bindings=[current, entry]),
        dict(check="CONTINUITY_COVERAGE", outcome="COMPLETE", values=dict(missing_completed_bars=[]),
             evidence_bindings=[current, entry]),
    ]
    for intent in ("EXIT", "REDUCE", "ADD", "OPEN"):
        path.append(dict(check="CURRENT_" + intent, outcome="NOT_OBSERVED",
            values=dict(intent=intent, price=None, observed=False, rule="TEST_ONLY 原规则文本",
                requires_existing_holding=True, status="CONDITIONAL_REVIEW_ONLY",
                formal_eligibility=False, personal_permission=False, action="no_order"),
            evidence_bindings=[current]))
    path.append(dict(check="STRUCTURE_QUALITY", outcome="RESEARCH_ONLY",
                     values=dict(structure_tier="ACTIVE_ONLY"), evidence_bindings=[current]))
    explanation["decision_path"] = path
    before = deepcopy(review)
    text = render_hotspot_lifecycle_markdown(review)
    assert "10. 检查：价格行为质量（STRUCTURE_QUALITY）" in text
    assert "仅参考证据已核验，不代表真实入场或持仓" in text
    assert "首次破位收盘价：10.00" in text
    assert text.count("条件规则：TEST_ONLY 原规则文本") == 4
    assert text.count("个人权限：否") == 4
    assert "价格：未知" in text
    assert review == before


@pytest.mark.parametrize("entry_state", ["NOT_SUPPLIED", "UNVERIFIED"])
def test_unverified_entry_and_unevaluated_checks_cannot_be_presented_as_negative_conditions(entry_state):
    review = _review("ENTRY_EVIDENCE_UNAVAILABLE", "UNKNOWN")
    review["original_entry_comparison"] = None
    if entry_state == "NOT_SUPPLIED":
        review["entry_case_binding"] = None
    explanation = review["decision_explanation"]
    explanation["recomputed_rule_versions"]["entry"] = None
    explanation["decision_path"] = [dict(check="ENTRY_REFERENCE", outcome=entry_state,
        values=dict(entry_at=None), evidence_bindings=[])]
    explanation["decision_path"] += [dict(check=check, outcome="NOT_EVALUATED", values={}, evidence_bindings=[])
        for check in ("ENTRY_RULE_COMPATIBILITY", "ORIGINAL_PROTECTION", "CONTINUITY_COVERAGE", "CURRENT_ADD")]
    text = render_hotspot_lifecycle_markdown(review)
    assert text.count("结果：未评估（NOT_EVALUATED）") == 4
    assert "未观察到条件（NOT_OBSERVED）" not in text
    assert "仅参考证据已核验" not in text
    assert "以下输入引用不表示已核验" in text
    assert "原始参考重算规则：未知" in text


@pytest.mark.parametrize("damage", ["missing", "version", "action", "selected"])
def test_inconsistent_explanation_cannot_be_rendered_as_a_valid_no_order_review(damage):
    review = _review()
    if damage == "missing":
        del review["decision_explanation"]
    elif damage == "version":
        review["decision_explanation"]["schema_version"] = "unknown-version"
    elif damage == "action":
        review["decision_explanation"]["action"] = "order"
    else:
        review["decision_explanation"]["selected_review"] = "ADD_STRUCTURE_REVIEW"
    with pytest.raises(ValueError, match="no_order lifecycle explanation"):
        render_hotspot_lifecycle_markdown(review)

"""Public economic-path projection outside immutable candidate generation."""
from copy import deepcopy
from .common import load_json_object
from ..research.value_research_analysis import _bound

def attach_consumed_economic_path(*, root, review):
    if review.get("schema_version") not in ("joint-capital-cash-review-v2", "joint-capital-cash-review-v3", "joint-capital-cash-review-v4"):
        return review
    result = deepcopy(review)
    policy = load_json_object(_bound(root, review["policy_binding"]), "consumed economic policy")
    choice = next(item for item in policy["choices"] if item["id"] == review["selected_choice"])
    result.update(selection_reason=choice.get("rationale"), selection_countercase=choice.get("countercase"),
        historical_input_mapping=deepcopy(policy.get("joint_historical", {})),
        research_input_bindings=deepcopy(policy.get("rationale_bindings", [])))
    result["economic_path"] = _economic_path(result)
    result["conditional_price"] = dict(status="insufficient_evidence", value=None,
        unit="CNY/share", action="no_order", formal_eligibility=False,
        reason_codes=["CANDIDATE_HAS_NO_BOUND_ACTION_PRICE_POLICY"],
        explanation="本研究候选仅包含条件估值，未携带已绑定的操作阈值、有效期及当前股本/分配/事件对齐结论。不能将估值数字直接解释为买入价；独立价格政策须另行验证。")
    _bound(root, review["policy_binding"])
    return result

def _economic_path(review):
    """Readable projection of verified consumed ledgers; no forecast or pricing here.

    Amounts remain decimal strings in CNY, years are model-period ordinals.
    Missing operands remain null with an explicit missing state, never zero.
    Each projected number is a conditional calculation, not a disclosed fact.
    """
    stages = (
        ('revenue', '营业收入', '经营收入路径', ('revenue', 'cost')),
        ('earnings', '收入到归母利润', '税前利润－所得税，再按归属口径并入增量资本收益',
         ('pre_tax_profit', 'tax', 'legacy_parent_profit', 'new_operating_profit', 'new_liquidity_profit', 'profit')),
        ('capital', '经营投入与资金承诺', '净维护投入＋营运资金＋当期承诺支出；不重复加回折旧',
         ('net_maintenance_cash_cny', 'operating_wc_cash_cny', 'commitment_cash_cny', 'mandatory_cash')),
        ('access', '可达资金', '盈利可取得比例是条件假设，未上划资金不自动释放',
         ('opening_cash', 'accessible_profit', 'newly_unremitted', 'closing_unremitted')),
        ('distribution', '普通股股东分配', '目标分配受现金及法定容量约束，不是分红承诺',
         ('target_distribution', 'cash_distribution_limit', 'capacity_distribution_limit', 'distribution')),
        ('retention', '留存与期末资本', '期初权益＋归母盈利－实际条件分配；现金与权益分别列示',
         ('opening_book', 'retained', 'closing_book', 'closing_cash', 'funding_shortfall')),
    )
    scenarios = []
    for scenario in review['scenarios']:
        years = []
        for row in scenario['ledger']['rows']:
            steps = []
            for key, title, relation, fields in stages:
                missing = [field for field in fields if row.get(field) is None]
                steps.append(dict(id=key, title=title, relation=relation,
                    status='missing' if missing else 'available', missing_fields=missing,
                    values={field: row.get(field) for field in fields}, unit='CNY',
                    classification='CONDITIONAL_CALCULATION'))
            years.append(dict(model_year=row['year'], steps=steps))
        scenarios.append(dict(scenario=scenario['scenario'], years=years))
    return dict(status='CONDITIONAL_RESEARCH', action='no_order',
        currency='CNY', scope='ordinary_owner_equivalent_cash_mapping',
        period_basis='MODEL_YEAR_NOT_DISCLOSED_FISCAL_YEAR',
        basis_at=review['basis_at'], valuation_at=review['valuation_at'],
        candidate_binding=deepcopy(review['candidate_binding']),
        assumption_binding=deepcopy(review['policy_binding']),
        scenarios=scenarios)



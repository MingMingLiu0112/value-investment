"""Small, explicit research profiles; shared workflow never implies shared economics."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchProfile:
    profile_id: str
    industry: str
    business_model: str
    investment_path: str
    life_cycle: str
    required_financial_metrics: tuple[str, ...]
    primary_valuation_model: str
    cross_check_models: tuple[str, ...]
    cycle_profile: str | None
    unsupported_models: tuple[str, ...]


QUALITY_COMPOUNDER = ResearchProfile(
    "quality_compounder", "消费品", "品牌与渠道", "成熟优质复利 / 现金回报", "成熟",
    ("return_on_equity", "distributable_cash", "capital_allocation"),
    "residual_income_or_equity_value", ("reference_multiple",), None, ("fcff_default",),
)
MATURE_MANUFACTURING = ResearchProfile(
    "mature_manufacturing", "制造业", "家电与智能制造", "成长价值 / 成熟经营", "成熟",
    ("ebit", "capex", "working_capital_change", "net_debt", "shares"),
    "fcff", ("fcf_yield", "relative_multiple"), None, (),
)
CYCLICAL_CASH_RETURN = ResearchProfile(
    "cyclical_cash_return", "周期资源", "煤炭与综合能源", "周期正常化 / 现金回报", "周期",
    ("normalized_profit", "unit_cost", "maintenance_capex", "net_cash"),
    "cyclical_normalized", ("dividend", "sotp"), "commodity_supply_demand", ("fcff_default",),
)


PROFILES = {profile.profile_id: profile for profile in (
    QUALITY_COMPOUNDER, MATURE_MANUFACTURING, CYCLICAL_CASH_RETURN,
)}

__all__ = [
    "ResearchProfile",
    "QUALITY_COMPOUNDER",
    "MATURE_MANUFACTURING",
    "CYCLICAL_CASH_RETURN",
    "PROFILES",
]

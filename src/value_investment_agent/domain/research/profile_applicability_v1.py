"""Frozen C responsibility contract: applicability is not economic approval."""
from copy import deepcopy
from .research_profile import PROFILES

VERSION = "c-profile-applicability-v1"
_COMMON_REFUSALS = (
    "OFFICIAL_SOURCE_IDENTITY_OR_HASH_INVALID",
    "SOURCE_NOT_AVAILABLE_AT_CUTOFF",
    "UNKNOWN_OR_MIXED_OWN_BUSINESS",
    "FINANCIAL_BUSINESS_REQUIRES_SPECIALIZED_MODEL",
    "REQUESTED_MODEL_NOT_AUTHORIZED_FOR_PROFILE",
)
_CONDITIONS = {
    "quality_compounder": (
        "原文确认发行人自身经营消费产品；业务类别不证明护城河",
        "普通股股东收益、权益和分配必须使用明确且一致的主体口径",
        "资本需求与母公司可达现金必须明确，不能把合并现金当可分配现金",
    ),
    "mature_manufacturing": (
        "原文确认发行人自身制造业务，不以客户或供应商所属行业代替",
        "经营现金流须能与融资及非经营资产区分",
        "经营利润、税、再投资及企业价值到股东价值桥接须口径匹配",
    ),
    "cyclical_cash_return": (
        "原文确认发行人自身资源业务，且存在可识别的周期敞口",
        "使用正常化盈利与成本，不把周期高点盈利自动延续",
        "维持性投入和正常化分配需要独立研究依据",
    ),
}

def contract_for_profile(profile_id: str) -> dict:
    if profile_id not in _CONDITIONS:
        raise ValueError("UNSUPPORTED_ECONOMIC_PROFILE")
    profile = PROFILES[profile_id]
    return deepcopy(dict(version=VERSION, profile_id=profile_id,
        applicability_conditions=list(_CONDITIONS[profile_id]),
        refusal_conditions=list(_COMMON_REFUSALS),
        required_economic_inputs=list(profile.required_financial_metrics),
        primary_model=profile.primary_valuation_model,
        authorized_alternative_models=list(profile.authorized_alternative_models),
        unsupported_models=list(profile.unsupported_models),
        permits_valuation_without_inputs=False, permits_approval=False,
        action="no_order"))

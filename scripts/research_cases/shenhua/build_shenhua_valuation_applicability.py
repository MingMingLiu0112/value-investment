"""Pin Shenhua's cyclical-model routing boundary from retained official evidence.

601088's economic profile routes to the registered cyclical-normalized model,
while the router rejects the mature-consumer residual-income model and the
generic FCFF default for this profile. Every required cyclical input remains
unadmitted as of the 2026-10-13 re-check: the retained packages compile
candidate derivations only, each with ``model_input`` null, empty registered
input lists and explicit review requirements. Cyclical valuation therefore
stays NOT_ESTABLISHED and this module never produces a scenario valuation,
fair value, position or order.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.research_profile import PROFILES
from value_investment_agent.valuation_models.cyclical import CyclicalFacts
from value_investment_agent.valuation_router import ROUTE_SUPPORTED, ValuationRouter


SCOPE = ROOT / "runtime/company-research/shenhua-cyclical-scope-20260921/evidence.json"
SCOPE_SHA256 = "4c69cf09f81ae8c0cf7fd5537276a3147d1c25adf3eee80b92c455ee2a3134c0"
CANDIDATE_INPUTS = ROOT / "runtime/company-research/shenhua-cyclical-candidate-inputs-20260921/evidence.json"
CANDIDATE_INPUTS_SHA256 = "3fc7fd27c13787ff08162e26e9762fbe1912db47766369624a42d41e5eaefe71"
PARENT_BRIDGE = ROOT / "runtime/company-research/shenhua-2025-parent-operating-profit-bridge-20260921/evidence.json"
PARENT_BRIDGE_SHA256 = "e8f177f2f0050cc3f2ae4996851b100b8a7eb2ebe8cbfbb47e89de9045504b6c"
NET_CASH_BRIDGE = ROOT / "runtime/company-research/shenhua-2025-attributable-net-cash-bridge-20260921/evidence.json"
NET_CASH_BRIDGE_SHA256 = "ce5a021c134c97a5f821acd6c6a490404806d84e5e6fbffb97eae9f876905a31"
SHARE_BRIDGE = ROOT / "runtime/company-research/shenhua-2026-share-bridge-20260921/evidence.json"
SHARE_BRIDGE_SHA256 = "1d39ca52cb75540acf65a9afe3c8dea1052f42a45edab6ccfd72598940d6b0e0"
IFRS_TAX_REVIEW = ROOT / "runtime/company-research/shenhua-2025-ifrs-subsidiary-tax-review-20260922/evidence.json"
IFRS_TAX_REVIEW_SHA256 = "ef9f3cca62cf29bfd6ffb5bd89f5585db7ff93887332796ce0d592e2ccf31e1f"
PROFIT_SERIES = ROOT / "runtime/company-research/shenhua-2014-2025-attributable-profit-series-20260922/evidence.json"
PROFIT_SERIES_SHA256 = "0eb6e930831f19d0e7ab8520dbfd4f67dd2e4afc7183e36233fd4a4ee0191e64"
CYCLE_AUDIT = ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-audit-20260922/evidence.json"
CYCLE_AUDIT_SHA256 = "7d21b86914e87be98a95dace75356746ee501309f81be273bf6d1453648da015"
STAGE_B_RESULT = ROOT / "runtime/valuation-results/601088-cyclical-b3/evidence.json"
STAGE_B_RESULT_SHA256 = "b03eaa05f7cbe117c676ddc5f6d9be6dc0c551a84fd3a457e18ee9886e5d1df6"
STAGE_B_POINTER = ROOT / "runtime/valuation-results/601088-cyclical-stage-b-latest.json"
OFFICIAL_PDF = ROOT / "runtime/shenhua-2025-official.pdf"
OFFICIAL_PDF_SHA256 = "460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc"
STOP_LEDGER = ROOT / "config/research-evidence-stop-ledger-v1.json"

OUT = ROOT / "runtime/company-research/shenhua-valuation-applicability-20261013-v1"
POINTER = ROOT / "runtime/company-research/shenhua-valuation-applicability-latest.json"

SCENARIO_PROFITS = (
    "bear_normalized_parent_operating_profit",
    "base_normalized_parent_operating_profit",
    "bull_normalized_parent_operating_profit",
)

# Candidate-package key -> the required-input names it addresses.
CANDIDATE_KEYS = (
    ("cash_tax_rate", ("cash_tax_rate",)),
    ("maintenance_capex", ("maintenance_capex",)),
    ("normalized_working_capital_change", ("normalized_working_capital_change",)),
    ("resource_life_years", ("resource_life_years",)),
    ("net_cash_attributable_to_parent", ("net_cash_attributable_to_parent",)),
    ("ordinary_shares", ("ordinary_shares",)),
    ("normalized_parent_operating_profit", SCENARIO_PROFITS),
    ("unit_cost", ("unit_cost",)),
    ("discount_rate_long_term_growth", ("discount_rate", "long_term_growth")),
)

# The exact candidate strings the pinned package must still carry.
EXPECTED_CANDIDATE_STATUS = {
    "cash_tax_rate": "unverified_historical_candidate",
    "maintenance_capex": "range_only_no_reviewed_split",
    "normalized_working_capital_change": "raw_balance_sheet_candidate_not_normalized",
    "resource_life_years": "reserve_over_current_output_range_candidate",
    "net_cash_attributable_to_parent": "unverified_reported_surface_proxies",
    "ordinary_shares": "period_end_value_not_current_denominator",
    "bear_normalized_parent_operating_profit": "cannot_derive_from_retained_disclosure",
    "base_normalized_parent_operating_profit": "cannot_derive_from_retained_disclosure",
    "bull_normalized_parent_operating_profit": "cannot_derive_from_retained_disclosure",
    "unit_cost": "change_only_no_absolute_cost_curve",
    "discount_rate": "no_company_specific_reviewed_basis",
    "long_term_growth": "no_company_specific_reviewed_basis",
}

PER_INPUT_REASONS = {
    "bear_normalized_parent_operating_profit":
        "保留的2025年报披露合并税前利润与归母净利润，但没有模型要求的归母税前营业利润归属；审计序列判定无法推导。",
    "base_normalized_parent_operating_profit":
        "缺少经复核的跨周期正常化归母税前营业利润基线；现仅有候选序列。",
    "bull_normalized_parent_operating_profit":
        "缺少有证据支持的煤价与成本上行情景区间。",
    "cash_tax_rate":
        "仅有候选上界观察（现金税费包含全部税种），未复核为正常化现金税率。",
    "maintenance_capex":
        "报告披露总资本开支，未拆分维持性与增长性资本开支。",
    "normalized_working_capital_change":
        "仅有原始资产负债表营运资金变动候选，未经正常化复核。",
    "discount_rate":
        "没有公司特有的已复核权益成本或WACC依据。",
    "long_term_growth":
        "没有有证据支持的长期真实增长率假设。",
    "resource_life_years":
        "储量吨位已披露，但以当前产量折算的静态年限不是经复核的服务年限。",
    "net_cash_attributable_to_parent":
        "仅有合并/母公司表面净现金区间候选，未完成归母与受限资金分配复核。",
    "ordinary_shares":
        "2026-06-30 分母候选 21,689,434,304 股未复核为模型输入；验收要求逐笔发行原件、时点/加权口径选择和库藏股确认。",
    "trough_parent_operating_profit":
        "描述性历史序列本身不构成经复核的低谷利润点。",
    "unit_cost":
        "仅披露单位成本变动，没有绝对成本曲线；历史生产成本被拒绝作为直接模型输入。",
}

REOPEN_CONDITIONS = (
    "一份经复核的跨周期归母税前营业利润情景区间（bear/base/bull）与低谷利润点，来源为官方定期报告序列或审计等价的官方证据。",
    "将维持性资本开支与增长性资本开支分离的官方项目级披露。",
    "公司特有的折现率与长期增长率复核依据，不得使用默认参数。",
    "归母口径净现金分配复核，包含受限资金、财务公司存款与少数股东部分。",
    "经复核的普通股分母（时点或加权口径经明确选择），包含发行、回购与库藏股的滚动证据。",
    "经复核的资源寿命年数与绝对单位成本曲线。",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


PINNED_PACKAGES = (
    ("shenhua_cyclical_scope", SCOPE, SCOPE_SHA256, "2025年报周期口径审计"),
    ("shenhua_cyclical_candidate_inputs", CANDIDATE_INPUTS, CANDIDATE_INPUTS_SHA256,
     "周期模型候选输入汇编（未复核、未准入）"),
    ("shenhua_parent_operating_profit_bridge", PARENT_BRIDGE, PARENT_BRIDGE_SHA256,
     "归母税前营业利润桥（候选）"),
    ("shenhua_attributable_net_cash_bridge", NET_CASH_BRIDGE, NET_CASH_BRIDGE_SHA256,
     "归母净现金桥（候选区间）"),
    ("shenhua_2026_share_bridge", SHARE_BRIDGE, SHARE_BRIDGE_SHA256,
     "2026发行后普通股分母桥（候选）"),
    ("shenhua_ifrs_subsidiary_tax_review", IFRS_TAX_REVIEW, IFRS_TAX_REVIEW_SHA256,
     "IFRS子公司税务复核（无已验证税前归属）"),
    ("shenhua_attributable_profit_series", PROFIT_SERIES, PROFIT_SERIES_SHA256,
     "2014-2025归母盈利候选序列（未复核）"),
    ("shenhua_operational_cycle_audit", CYCLE_AUDIT, CYCLE_AUDIT_SHA256,
     "2014-2025经营周期审计（点事实，非模型输入）"),
    ("shenhua_2025_official_pdf", OFFICIAL_PDF, OFFICIAL_PDF_SHA256,
     "交易所披露的2025年度报告原件"),
)


def verify_pins() -> None:
    for _id, path, expected, _description in PINNED_PACKAGES:
        if digest(path) != expected:
            raise ValueError(f"Shenhua applicability evidence changed: {path.name}")
    if digest(STAGE_B_RESULT) != STAGE_B_RESULT_SHA256:
        raise ValueError(f"Shenhua applicability evidence changed: {STAGE_B_RESULT.name}")


def route_boundary() -> dict:
    router = ValuationRouter()
    profile = PROFILES["cyclical_cash_return"]
    primary = router.route(profile)
    if primary.status != ROUTE_SUPPORTED:
        raise ValueError("The cyclical profile no longer routes to a supported model")
    if primary.model_type != "cyclical_normalized" or primary.facts_contract is not CyclicalFacts:
        raise ValueError("The cyclical profile no longer routes to the shared cyclical contract")

    residual = router.route(profile, requested_model="residual_income_or_equity_value")
    fcff = router.route(profile, requested_model="fcff")
    guards = {
        "residual_income_or_equity_value": {
            "status": residual.status,
            "blockers": list(residual.blockers),
        },
        "fcff": {
            "status": fcff.status,
            "blockers": list(fcff.blockers),
        },
    }
    if guards["residual_income_or_equity_value"] != {
        "status": "UNSUPPORTED",
        "blockers": ["model_not_authorized_for_profile:residual_income_or_equity_value"],
    }:
        raise ValueError("The mature-consumer model became routable for the cyclical profile")
    if guards["fcff"] != {
        "status": "UNSUPPORTED",
        "blockers": ["model_not_authorized_for_profile:fcff"],
    }:
        raise ValueError("The FCFF default became routable for the cyclical profile")
    return {
        "profile_id": profile.profile_id,
        "primary_route": primary.as_policy(),
        "unauthorized_requests": guards,
    }


def fact_gate() -> dict:
    required = tuple(CyclicalFacts.REQUIRED_CYCLICAL_INPUTS)
    facts = CyclicalFacts(
        symbol="601088",
        as_of=date(2025, 12, 31),
        verified=False,
        confidence="低",
        evidence_refs=[],
        blockers=[],
        operating_inputs={},
    )
    missing = list(facts.missing_cyclical_inputs)
    if sorted(missing) != sorted(required):
        raise ValueError("The cyclical contract no longer reports every input missing at zero inputs")
    return {
        "facts_contract": "CyclicalFacts",
        "required_inputs": list(required),
        "missing_inputs_without_admitted_facts": missing,
        "admitted_inputs": [],
        "registered_inputs": {},
    }


def per_input_admission(candidate: dict, cycle_audit: dict, profit_series: dict,
                        share_bridge: dict, net_cash_bridge: dict) -> dict:
    required = set(CyclicalFacts.REQUIRED_CYCLICAL_INPUTS)
    audit_decisions = cycle_audit["model_input_decisions"]
    if set(audit_decisions) != required:
        raise ValueError("The cycle audit no longer covers exactly the cyclical input contract")
    if cycle_audit["registered_cyclical_facts_operating_inputs"] != []:
        raise ValueError("The cycle audit unexpectedly registered model inputs")

    candidate_status: dict[str, str] = {}
    for key, names in CANDIDATE_KEYS:
        entry = candidate["candidate_derivations"][key]
        if entry.get("model_input") is not None:
            raise ValueError(f"Candidate input {key} is unexpectedly registered")
        for name in names:
            candidate_status[name] = entry["status"]
    if candidate_status != EXPECTED_CANDIDATE_STATUS:
        raise ValueError("The cyclical candidate status map changed; re-review before re-emitting")

    if share_bridge["ordinary_share_denominator_candidate"]["model_input"] is not None:
        raise ValueError("The share bridge unexpectedly registered a denominator")
    if net_cash_bridge["candidate_derivations"]["model_input"] is not None:
        raise ValueError("The net-cash bridge unexpectedly registered a model input")

    admission = {}
    series_decisions = profit_series.get("model_input_decisions", {})
    if not set(series_decisions) <= required:
        raise ValueError("The profit series records decisions outside the cyclical contract")
    if profit_series["registered_cyclical_facts_operating_inputs"] != []:
        raise ValueError("The profit series unexpectedly registered model inputs")
    for name in CyclicalFacts.REQUIRED_CYCLICAL_INPUTS:
        admission[name] = {
            "admission": "NOT_ADMITTED",
            "candidate_status": candidate_status.get(name),
            "audit_decision": audit_decisions[name],
            "series_decision": series_decisions.get(name),
            "reason": PER_INPUT_REASONS[name],
        }
    return admission


def fail_closed_anchor() -> dict:
    payload = load(STAGE_B_RESULT)
    pointer = load(STAGE_B_POINTER)
    pointer_dir = (ROOT / Path(pointer["path"].replace("\\", "/"))).resolve()
    if pointer_dir != STAGE_B_RESULT.parent or pointer["sha256"] != STAGE_B_RESULT_SHA256:
        raise ValueError("The retained fail-closed result pointer no longer pins this artifact")

    result = payload["result"]
    expected_missing = sorted(
        "cyclical_input_missing:" + name for name in CyclicalFacts.REQUIRED_CYCLICAL_INPUTS
    )
    observed_missing = sorted(
        blocker for blocker in result["blockers"] if blocker.startswith("cyclical_input_missing:")
    )
    if observed_missing != expected_missing:
        raise ValueError("The retained fail-closed result no longer blocks on every cyclical input")
    if result["status"] != "not_ready":
        raise ValueError("The retained fail-closed result unexpectedly advanced status")
    if any(result[key] is not None for key in ("bear_value", "base_value", "bull_value")):
        raise ValueError("The retained fail-closed result unexpectedly carries scenario values")
    if payload.get("formal_fair_value") is not None:
        raise ValueError("The retained fail-closed result unexpectedly carries a fair value")
    bridge_status = payload["price_bridge"]["bridge_status"]
    if bridge_status != "PENDING_EXTERNAL_DATA":
        raise ValueError("The retained fail-closed result no longer waits on external data")
    return {
        "path": STAGE_B_RESULT.relative_to(ROOT).as_posix(),
        "sha256": STAGE_B_RESULT_SHA256,
        "result_status": result["status"],
        "scenario_values": None,
        "price_bridge_status": bridge_status,
        "missing_blockers": expected_missing,
    }


def build_payload() -> dict:
    verify_pins()
    scope = load(SCOPE)
    candidate = load(CANDIDATE_INPUTS)
    cycle_audit = load(CYCLE_AUDIT)
    profit_series = load(PROFIT_SERIES)
    share_bridge = load(SHARE_BRIDGE)
    net_cash_bridge = load(NET_CASH_BRIDGE)
    ledger = load(STOP_LEDGER)

    for package in (scope, candidate, cycle_audit, profit_series, share_bridge, net_cash_bridge):
        if package.get("symbol") != "601088":
            raise ValueError("A pinned Shenhua package lost its issuer identity")
        if package.get("valuation_status") not in (None, "VALUATION_NOT_READY"):
            raise ValueError("A pinned Shenhua package unexpectedly advanced valuation status")

    stops = [stop for stop in ledger["stops"] if stop["symbol"] == "601088"]
    if not stops:
        raise ValueError("The evidence-stop ledger no longer records Shenhua")

    payload = {
        "symbol": "601088",
        "name": "中国神华",
        "package_version": "shenhua-valuation-applicability-v1",
        "review_date": "2026-10-13",
        "question": "哪个已注册估值模型适用于神华的周期画像，其必需输入是否已准入？",
        "profile_route": route_boundary(),
        "facts_contract": fact_gate(),
        "per_input_admission": per_input_admission(
            candidate, cycle_audit, profit_series, share_bridge, net_cash_bridge
        ),
        "fail_closed_result_anchor": fail_closed_anchor(),
        "evidence_stops": [
            {
                "stop_id": stop["stop_id"],
                "blocker_id": stop["blocker_id"],
                "reopen_condition": stop["reopen_condition"],
            }
            for stop in stops
        ],
        "reopen_conditions": list(REOPEN_CONDITIONS),
        "decision": "CYCLE_MODEL_ROUTE_VERIFIED_INPUTS_NOT_ADMITTED",
        "valuation_status": "NOT_ESTABLISHED",
        "valuation_run_status": "NOT_RUN_ADMITTED_INPUTS_UNAVAILABLE",
        "research_registration": {
            "performed": False,
            "expected_product_state": "PENDING_RESEARCH",
        },
        "new_model_family_created": False,
        "registered_valuation_model": None,
        "registered_valuation_inputs": {},
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "conclusion": (
            "周期画像只授权已注册的周期正常化模型；成熟消费制造业的残余收益模型与通用FCFF默认对该画像"
            "均不可路由。周期合同要求的13项输入全部未准入，周期估值保持 NOT_ESTABLISHED，不运行算术。"
        ),
        "blockers": list(candidate["blockers"]),
        "evidence_refs": [
            {
                "id": ref_id,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha,
                "description": description,
            }
            for ref_id, path, sha, description in PINNED_PACKAGES
        ],
    }
    return payload


def main() -> None:
    payload = build_payload()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    target.write_text(text, encoding="utf-8")
    digest_value = digest(target)
    POINTER.write_text(
        json.dumps(
            {"path": OUT.relative_to(ROOT).as_posix(), "sha256": digest_value},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "output": str(target),
            "sha256": digest_value,
            "decision": payload["decision"],
            "valuation_status": payload["valuation_status"],
            "admitted_inputs": len(payload["facts_contract"]["admitted_inputs"]),
            "required_inputs": len(payload["facts_contract"]["required_inputs"]),
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()

"""Public projection of a cold-replayed implemented owner distribution.

The view exposes the source-bound v2 calculation without adopting a main
valuation range, qualifying a price, or granting any formal action.
"""

from ..research.direct_owner_cash_research_v1 import _read
from ..research.owner_distribution_read_scope import (
    replay_parent_owner_distribution_successor,
)


def read_parent_owner_distribution_successor_view(*, root, receipt_binding, symbol, now):
    result = replay_parent_owner_distribution_successor(
        root=root, receipt_binding=receipt_binding, now=now,
    )
    receipt = _read(root, receipt_binding)
    spec = _read(root, receipt["spec_binding"])
    if (
        result["symbol"] != symbol
        or receipt["symbol"] != symbol
        or result["research_case"]["symbol"] != symbol
        or result["action"] != "no_order"
        or result["formal_eligibility"] is not False
        or result["successor_adopted"] is not False
        or result["main_range_adopted"] is not False
        or receipt["predecessor_binding"] != result["predecessor_binding"]
        or result["input_descriptor_sha256"] != receipt["input_descriptor_sha256"]
    ):
        raise ValueError("OWNER_DISTRIBUTION_PUBLIC_IDENTITY_OR_ADOPTION_INVALID")

    calculations = result["valuation"]["assumptions"]["scenario_calculations"]
    if set(calculations) != {"bear", "base", "bull"}:
        raise ValueError("OWNER_DISTRIBUTION_PUBLIC_SCENARIOS_INCOMPLETE")
    distributions = {}
    annual = {}
    for name, calculation in calculations.items():
        rows = calculation["annual_rows"]
        annual[name] = rows
        distributions[name] = [
            {
                "year": row["year"],
                "scheduled_owner_distribution_cny": row[
                    "scheduled_owner_distribution_cny"
                ],
                "conditional_owner_distribution_cny": row[
                    "conditional_distribution_cny"
                ],
                "total_owner_distribution_cny": row[
                    "total_owner_distribution_cny"
                ],
            }
            for row in rows
        ]

    return dict(
        schema_version="first-research-input-view-v1",
        receipt_schema_version="parent-owner-distribution-successor-receipt-v2",
        status="SOURCE_BOUND_FIRST_INPUT_COMPILED",
        reason=None,
        symbol=symbol,
        action="no_order",
        formal_eligibility=False,
        successor_adopted=False,
        main_range_adopted=False,
        main_valuation_range=None,
        current_price=None,
        condition_price=None,
        personal_quantity=None,
        user_acceptance="NOT_CONFIRMED",
        scope="SOURCE_REPLAYED_IMPLEMENTED_OWNER_DISTRIBUTION_NOT_ADOPTED",
        receipt_binding=receipt_binding,
        predecessor_binding=result["predecessor_binding"],
        input_descriptor_sha256=result["input_descriptor_sha256"],
        financial_basis=result["valuation"]["valuation_date"],
        research_as_of=spec["research_as_of"],
        input_computed_at=spec["computed_at"],
        research_case=result["research_case"],
        valuation=result["valuation"],
        valuation_status="conditional_research_only",
        scenario_valuations={
            name: result["valuation"][name + "_value"]
            for name in ("bear", "base", "bull")
        },
        annual_ledgers={name: {"rows": rows} for name, rows in annual.items()},
        owner_distributions=distributions,
        implemented_distribution=result["distribution"],
        distribution_evidence=result["distribution_evidence"],
        blockers=result["research_result"]["blockers"],
        source_bindings=result["source_bindings"],
        compilation_scope="SOURCE_REPLAYED_IMPLEMENTED_OWNER_DISTRIBUTION_SUCCESSOR",
        scenario_label_scope="CONDITIONAL_RESEARCH_NOT_ADOPTED_MAIN_RANGE",
        sources=result["package"]["sources"],
        operating_assumptions=result["compiled"]["scenarios"],
        source_review="PREDECESSOR_AND_IMPLEMENTED_DISTRIBUTION_COLD_REPLAYED_NOT_APPROVAL",
        investment_conclusion="UNAPPROVED_CONDITIONAL_OWNER_CASH_RESEARCH",
        direct_owner_cash=dict(
            method="DIRECT_CFO_LESS_EXPLICIT_CAPITAL_DEBT_AND_CONSTRAINED_DISTRIBUTIONS_V2",
            valuation_basis=result["valuation"]["valuation_date"],
            scope="ISSUER_PARENT_STANDALONE",
            annual_rows=annual,
            owner_distributions=distributions,
            implemented_distribution=result["distribution"],
            conditional_price=None,
            source_refs=result["source_bindings"],
        ),
    )



def read_aligned_owner_distribution_price(*, root, view, alignment, now):
    """Project explicit, hash-bound draft rules after the exact F2 replay."""
    from zoneinfo import ZoneInfo

    from ...research_artifact_codecs import ValuationResultCodec
    from ..decision.direct_owner_cash_price_draft_v1 import draft_direct_owner_cash_price
    from ..research.pending_candidate_alignment import CHECK_IDS, CONFIG_DIRECTORY
    from ..research.value_research_analysis import _bound
    from .common import load_json_object

    candidate = view.get("receipt_binding")
    descriptor = view.get("input_descriptor_sha256")
    checks = alignment.get("checks", [])
    if (not candidate or not descriptor
            or alignment.get("evaluated_at") != now.isoformat()
            or (alignment.get("price_bridge") or {}).get("bridge_status") != "READY"
            or alignment.get("status") != "ALIGNED_FOR_RESEARCH_COMPARISON"
            or alignment.get("currentpricecomparison") is not True
            or alignment.get("candidate_binding") != candidate
            or alignment.get("input_descriptor_sha256") != descriptor
            or alignment.get("action") != "no_order"
            or alignment.get("formal_eligibility") is not False
            or [row.get("id") for row in checks] != list(CHECK_IDS)
            or any(row.get("status") != "PASS" for row in checks)):
        return dict(status="BLOCKED", reason_codes=["EXACT_F2_ALIGNMENT_REQUIRED"], action="no_order")
    try:
        refs = alignment["evidence_bindings"]
        config_path = f"{CONFIG_DIRECTORY}/{candidate['sha256']}.json"
        config_ref, = [ref for ref in refs if ref["path"] == config_path]
        config = load_json_object(_bound(root, config_ref), "owner distribution alignment")
        policy_ref = config.get("price_policy_binding")
        if policy_ref is None:
            return dict(status="BLOCKED", reason_codes=["EXACT_PRICE_POLICY_NOT_BOUND"], action="no_order")
        policy = load_json_object(_bound(root, policy_ref), "conditional price policy")
        if (policy.get("schema_version") != "owner-distribution-price-policy-input-v1"
                or policy.get("candidate_binding") != candidate
                or policy.get("input_descriptor_sha256") != descriptor
                or policy.get("action") != "no_order"):
            raise ValueError("EXACT_PRICE_POLICY_IDENTITY_MISMATCH")
        value = view["valuation"]
        valuation = ValuationResultCodec().from_payload(value)
        plan = dict(symbol=view["symbol"], action="no_order",
                    research_version=view["research_case"]["research_version"],
                    valuation_input_version=descriptor, model_id=value["model_type"],
                    model_type=value["model_type"], model_version=value["model_version"],
                    valuation_date=value["valuation_date"],
                    source_bindings=[*refs, policy_ref], **view["scenario_valuations"])
        result = draft_direct_owner_cash_price(
            plan=plan, rule_config=policy["rule_config"], valuation=valuation,
            as_of=now.astimezone(ZoneInfo("Asia/Shanghai")).date(),
        )
        for ref in (*refs, policy_ref):
            _bound(root, ref)
        if result["status"] == "HISTORICAL_CONDITIONAL_DRAFT":
            result.update(status="UNAPPROVED_ALIGNED_CONDITIONAL_DRAFT",
                          scope="CURRENT_ALIGNMENT_RESEARCH_DRAFT_NOT_FORMAL_ACTION",
                          candidate_binding=candidate, input_descriptor_sha256=descriptor,
                          policy_binding=policy_ref, quote_date=alignment["quote_date"])
        return result
    except (ValueError, OSError, TypeError, KeyError, ArithmeticError) as error:
        return dict(status="BLOCKED", reason_codes=["PRICE_POLICY_REPLAY_REJECTED:" + str(error)],
                    action="no_order")

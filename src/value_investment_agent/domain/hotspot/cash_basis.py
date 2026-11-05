"""Separate gross shareholder entitlement from a declared ex-reference deduction."""
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, localcontext


def reconcile_cash_basis(*, total_a_shares, nonparticipating_a_shares, eligible_a_shares,
        gross_per_10_eligible_a_shares, declared_total_gross_cash_cny,
        reference_per_10_total_a_shares, reference_deduction_per_total_a_share,
        currency="CNY", share_class="A") -> dict:
    if currency != "CNY" or share_class != "A":
        raise ValueError("Only explicit CNY A-share cash basis supported")
    try:
        numbers = [Decimal(str(v)) for v in (total_a_shares, nonparticipating_a_shares,
            eligible_a_shares, gross_per_10_eligible_a_shares, declared_total_gross_cash_cny,
            reference_per_10_total_a_shares, reference_deduction_per_total_a_share)]
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Cash basis values must be finite decimals") from error
    if any(not v.is_finite() or v < 0 for v in numbers):
        raise ValueError("Cash basis values must be finite and nonnegative")
    total, excluded, eligible, gross10, payout, reference10, deduction = numbers
    if (min(total, eligible, gross10, payout, reference10, deduction) <= 0
            or any(v != v.to_integral_value() for v in (total, excluded, eligible))
            or total - excluded != eligible):
        raise ValueError("A-share total minus nonparticipants must equal eligible shares")
    with localcontext() as context:
        context.prec = 60
        gross = gross10 / 10
        if (eligible * gross).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != payout:
            raise ValueError("Gross eligible-share payout does not reconcile to declared cents")
        independently_derived = (payout * 10 / total).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
        if reference10 != independently_derived or deduction != reference10 / 10:
            raise ValueError("Total-A-share reference deduction differs from declared truncation")
    return dict(schema_version="hotspot-a-share-cash-basis-v2", currency=currency, share_class=share_class,
        total_a_shares=str(total), nonparticipating_a_shares=str(excluded), eligible_a_shares=str(eligible),
        gross_per_10_eligible_a_shares=str(gross10), gross_cash_per_eligible_a_share=str(gross),
        declared_total_gross_cash_cny=str(payout), reference_per_10_total_a_shares=str(reference10),
        reference_deduction_per_total_a_share=str(deduction),
        reference_rounding="TRUNCATE_6_DECIMALS_PER_10_TOTAL_A_SHARES_THEN_DIVIDE_BY_10",
        share_base_scope="DECLARED_IMPLEMENTATION_A_SHARES_NOT_H_SHARES_OR_CSDCC_ACTUAL_REGISTER",
        gross_cash_scope="PRE_TAX_PER_ELIGIBLE_A_SHARE_NOT_TOTAL_A_SHARES_OR_PERSONAL_NET",
        reference_scope="ISSUER_DECLARED_EX_REFERENCE_DEDUCTION_NOT_CASH_RECEIVABLE_OR_TICK_QUOTE",
        declared_aggregate_reconciled=True, shareholder_receipt_proven=False,
        tax_calculated=False, price_mapping=None, original_protection_adjusted=False,
        complete_action_coverage=False, formal_eligibility=False, action="no_order")

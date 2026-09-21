from decimal import Decimal
import pytest

from value_investment_agent.derived_financials import build_verified_derivations


def point(field: str, value: str) -> dict:
    return {
        "symbol": "600001", "field_name": field, "value": Decimal(value), "unit": "CNY",
        "period_label": "2025-12-31", "validation_status": "verified",
        "metadata": {"automatic_cross_source_verification": True}, "source_id": f"source-{field}",
    }


def test_derivations_require_verified_same_period_inputs_and_retain_sources() -> None:
    points = [
        point("revenue", "1000"), point("operating_cost", "600"), point("net_income", "100"),
        point("operating_cash_flow", "130"), point("total_assets", "2000"), point("total_liabilities", "800"),
        point("short_term_borrowings", "10"), point("current_portion_long_term_debt", "20"),
        point("long_term_borrowings", "30"), point("bonds_payable", "40"),
    ]

    records = {record.field_name: record for record in build_verified_derivations(points, ["600001"])}

    assert records["gross_margin"].value == Decimal("40.0000")
    assert records["net_margin"].value == Decimal("10.0000")
    assert records['net_margin'].point_metadata['ratio_scope'] == 'parent_attributable_net_income / operating_revenue'
    assert records['operating_cash_flow_to_net_income'].point_metadata['ratio_scope'] == 'consolidated_operating_cash_flow / parent_attributable_net_income'
    assert records["operating_cash_flow_to_net_income"].value == Decimal("130.0000")
    assert records["debt_ratio"].value == Decimal("40.0000")
    assert records["borrowings_bonds_subtotal"].value == Decimal("100.0000")
    assert 'interest_bearing_debt' not in records
    assert records["gross_margin"].point_metadata["input_source_ids"]["revenue"] == "source-revenue"


def test_derivation_does_not_use_pending_input() -> None:
    points = [point("revenue", "1000"), point("operating_cost", "600")]
    points[1]["validation_status"] = "pending"

    assert build_verified_derivations(points, ["600001"]) == []


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('change', [{'value': Decimal('2000')},
                                  {'validation_status': 'conflict'},
                                  {'source_id': 'another-source'},
                                  {'period_label': '2024-12-31'}])
def test_unresolved_versions_are_rejected_regardless_of_order(reverse, change):
    revenue = point('revenue', '1000')
    inputs = [revenue, dict(revenue, **change), point('operating_cost', '600')]
    with pytest.raises(ValueError, match='600001/revenue'):
        build_verified_derivations(inputs[::-1] if reverse else inputs, ['600001'])


def test_identical_duplicate_does_not_change_derivation():
    revenue = point('revenue', '1000')
    cost = point('operating_cost', '600')
    single = build_verified_derivations([revenue, cost], ['600001'])
    duplicate = build_verified_derivations([revenue, dict(revenue), cost], ['600001'])
    assert [r.raw_payload for r in single] == [r.raw_payload for r in duplicate]


def test_derivation_normalizes_money_and_rejects_unknown_units():
    points = [dict(point('revenue', '1'), unit='CNY 100M'), point('operating_cost', '60000000')]
    records = build_verified_derivations(points, ['600001'])
    assert records[0].value == Decimal('40')
    points[0]['unit'] = 'USD'
    assert build_verified_derivations(points, ['600001']) == []


def test_changed_input_recomputes_a_previous_derivation():
    points = [point('revenue', '1000'), point('operating_cost', '600')]
    first = build_verified_derivations(points, ['600001'])[0]
    previous = dict(point('gross_margin', '40'), metadata=first.point_metadata)
    assert build_verified_derivations(points + [previous], ['600001']) == []
    points[1]['value'] = Decimal('500')
    assert build_verified_derivations(points + [previous], ['600001'])[0].value == Decimal('50')


def test_derivation_binds_exact_point_ids_and_recomputes_after_reverification():
    points = [dict(point('revenue', '1000'), data_point_id='revenue-v1'),
              dict(point('operating_cost', '600'), data_point_id='cost-v1')]
    first = build_verified_derivations(points, ['600001'])[0]
    assert first.point_metadata['input_facts']['revenue']['data_point_id'] == 'revenue-v1'
    previous = dict(point('gross_margin', '40'), metadata=first.point_metadata)
    points[0]['data_point_id'] = 'revenue-v2'
    second = build_verified_derivations(points + [previous], ['600001'])[0]
    assert second.raw_payload != first.raw_payload
    assert second.value == first.value


@pytest.mark.parametrize('field', ['net_margin', 'operating_cash_flow_to_net_income'])
@pytest.mark.parametrize('old_scope', [None, 'consolidated_net_income'])
def test_old_ratio_scope_is_refreshed_once(field, old_scope):
    inputs = [point('net_income', '100'), point('revenue', '1000'),
              point('operating_cash_flow', '130')]
    first = next(r for r in build_verified_derivations(inputs, ['600001']) if r.field_name == field)
    old_metadata = dict(first.point_metadata)
    if old_scope is None:
        old_metadata.pop('ratio_scope')
    else:
        old_metadata['ratio_scope'] = old_scope
    old = dict(point(field, str(first.value)), metadata=old_metadata)
    refreshed = next(r for r in build_verified_derivations(inputs + [old], ['600001']) if r.field_name == field)
    assert refreshed.value == first.value
    assert refreshed.point_metadata['input_facts'] == old_metadata['input_facts']
    assert refreshed.point_metadata['ratio_scope'] == first.point_metadata['ratio_scope']
    current = dict(old, metadata=refreshed.point_metadata)
    assert field not in {r.field_name for r in build_verified_derivations(inputs + [current], ['600001'])}
    assert old['metadata'] == old_metadata

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest

from value_investment_agent.quality import accepted_verification, evaluate
from value_investment_agent.valuation import build_reference_records


def point(field_name: str, value: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "symbol": "600519",
        "field_name": field_name,
        "value": Decimal(value),
        "period_label": "2026-06-30",
        "created_at": now,
        "fetched_at": now,
        "validation_status": "pending",
        "source_id": "source-1",
    }


def test_pe_pb_reference_uses_true_ttm_eps_and_bvps() -> None:
    records = build_reference_records([point("eps_ttm", "40"), point("bvps", "200")], ["600519"])
    values = {record.field_name: record.value for record in records}

    assert values["model_pe_fair_value"] == Decimal("720.00")
    assert values["model_pb_fair_value"] == Decimal("800.00")
    assert values["model_fair_value"] == Decimal("760.00")


@pytest.mark.parametrize('reverse', [False, True])
def test_latest_input_is_not_list_order(reverse):
    old = point('eps_ttm', '30')
    new = dict(old, value=Decimal('40'), created_at=old['created_at'] + timedelta(days=1))
    inputs = [old, new] if not reverse else [new, old]
    records = build_reference_records([*inputs, point('bvps', '200')], ['600519'])
    assert next(r.value for r in records if r.field_name == 'model_fair_value') == Decimal('760')


def test_newest_invalid_input_does_not_fall_back_to_old():
    old = point('eps_ttm', '30')
    new = dict(old, validation_status='failed', created_at=old['created_at'] + timedelta(days=1))
    records = build_reference_records([new, old, point('bvps', '200')], ['600519'])
    assert 'model_fair_value' not in {r.field_name for r in records}


@pytest.mark.parametrize('timestamp', [None, 'bad', '2026-01-01T00:00:00', 'same'])
def test_ambiguous_duplicate_input_blocks_combined_reference(timestamp):
    old = point('eps_ttm', '30')
    new = dict(old, value=Decimal('40'), created_at=old['created_at'] if timestamp == 'same' else timestamp)
    records = build_reference_records([old, new, point('bvps', '200')], ['600519'])
    assert 'model_fair_value' not in {r.field_name for r in records}


def test_reference_model_skips_unprofiled_company_instead_of_borrowing_assumptions() -> None:
    records = build_reference_records([point("eps_ttm", "2")], ["000001"])

    assert records == []


def test_single_component_never_silently_becomes_combined_reference():
    records = build_reference_records([point('eps_ttm', '40')], ['600519'])
    values = {r.field_name: r.value for r in records}
    assert values['model_pe_fair_value'] == Decimal('720.00')
    assert 'model_fair_value' not in values
    assert all(not r.point_metadata['valuation']['combined_reference_available'] for r in records)


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', 'bad', '0', '-1'])
def test_invalid_numeric_input_does_not_interrupt_batch(value):
    row = dict(point('eps_ttm', '1'), value=value)
    assert build_reference_records([row], ['600519']) == []


@pytest.mark.parametrize('status', ['conflict', 'rejected', 'failed'])
def test_failed_evidence_is_not_used_even_for_reference(status):
    row = dict(point('eps_ttm', '40'), validation_status=status)
    assert build_reference_records([row], ['600519']) == []


def test_quarantined_input_cannot_contribute_to_combined_reference():
    eps = point('eps_ttm', '40')
    eps['metadata'] = {'evidence_quarantine': {'reason': 'wrong period'}}
    records = build_reference_records([eps, point('bvps', '200')], ['600519'])
    fields = {r.field_name for r in records}
    assert 'model_pe_fair_value' not in fields
    assert 'model_fair_value' not in fields
    assert 'model_pb_fair_value' in fields


def test_mixed_periods_preserve_components_without_combining():
    eps = point('eps_ttm', '40')
    book = dict(point('bvps', '200'), period_label='2025-12-31')
    records = build_reference_records([eps, book], ['600519'])
    assert 'model_fair_value' not in {r.field_name for r in records}
    assert all(r.point_metadata['review_required'] for r in records)
    periods = {r.field_name: r.period_label for r in records}
    assert periods['model_pe_fair_value'] == '2026-06-30'
    assert periods['model_pb_fair_value'] == '2025-12-31'


def test_model_reference_never_creates_a_trade_signal() -> None:
    now = datetime.now(timezone.utc)
    inputs = [point('eps_ttm', '40'), point('bvps', '200')]
    reference = next(r for r in build_reference_records(inputs, ['600519'])
                     if r.field_name == 'model_fair_value')
    result = evaluate(
        "600519",
        [
            {**point("current_price", "500"), "created_at": now, "fetched_at": now},
            {**point("model_fair_value", "760"), "created_at": now,
             'metadata': reference.point_metadata},
            *inputs,
        ],
        30,
        Decimal("0.03"),
    )

    assert result.status == "模型估值待复核"
    assert result.signal == "等待复核"
    assert result.target_weight == Decimal("0")


@pytest.mark.parametrize('mutation', ['missing', 'value', 'source', 'period', 'quarantine', 'legacy'])
def test_stale_reference_is_unavailable(mutation):
    inputs = [point('eps_ttm', '40'), point('bvps', '200')]
    reference = next(r for r in build_reference_records(inputs, ['600519'])
                     if r.field_name == 'model_fair_value')
    model = dict(point('model_fair_value', '760'), metadata=reference.point_metadata)
    if mutation == 'missing':
        inputs.pop()
    elif mutation == 'value':
        inputs[0]['value'] = Decimal('41')
    elif mutation == 'source':
        inputs[0]['source_id'] = 'replacement-source'
    elif mutation == 'period':
        inputs[0]['period_label'] = '2025-12-31'
    elif mutation == 'quarantine':
        inputs[0]['metadata'] = {'evidence_quarantine': True}
    else:
        model['metadata'] = {}
    result = evaluate('600519', [point('current_price', '500'), model, *inputs],
                      30, Decimal('0.03'))
    assert result.fair_value is None
    assert result.target_weight == 0
    assert result.signal == '待数据'


def test_human_marked_point_does_not_bypass_automatic_cross_validation() -> None:
    candidate = {
        **point("fair_value", "760"),
        "validation_status": "verified",
        "human_reviewed": True,
        "metadata": {},
    }

    assert not accepted_verification(candidate)

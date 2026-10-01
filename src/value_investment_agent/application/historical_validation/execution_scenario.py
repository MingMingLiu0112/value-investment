"""Use the existing virtual-account engine for explicitly synthetic constraints."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..product.common import require_inside, load_json_object, sha256_file
from ...virtual_account import VirtualAccount, replay, dated_research_fee
from ...domain.execution.simulation_only import simulation_execution_marker


def replay_execution_scenario(*, root: Path, path: Path, expected_sha256: str, symbol: str) -> dict:
    path = require_inside(root, path, 'execution scenario')
    if sha256_file(path) != expected_sha256:
        raise ValueError('execution scenario hash mismatch')
    value = load_json_object(path, 'execution scenario')
    if (value.get('schema_version') != 'shared-execution-engineering-input-v1'
            or value.get('scope') != 'SYNTHETIC_ENGINEERING_FIXTURE'
            or value.get('symbol') != symbol or value.get('action') != 'no_order'):
        raise ValueError('execution scenario scope mismatch')
    sessions = value['sessions']
    if not sessions or any(not date(2015, 1, 1) <= date.fromisoformat(row['date']) <= date(2025, 12, 31)
                           for row in sessions):
        raise ValueError('execution scenario outside frozen fee research span')
    days = {row['date'] for row in sessions}
    decisions = value['decisions']
    if not isinstance(decisions, dict) or set(decisions) - days:
        raise ValueError('scenario decisions must belong to supplied sessions')
    for decision in decisions.values():
        if (decision.get('action') != 'no_order' or decision.get('trade_approved') is not False
                or decision.get('live_eligible') is not False):
            raise ValueError('scenario cannot authorize live trades')
        if decision.get('state') in {'proposed_entry', 'proposed_add', 'proposed_reduce', 'proposed_exit'}:
            if 'execution_terms' not in decision:
                raise ValueError('scenario proposals require explicit bounded execution terms')
    cash = Decimal(value['initial_cash_cny'])
    if not cash.is_finite() or cash < 0:
        raise ValueError('scenario opening cash must be finite and nonnegative')
    account, journal = replay(sessions, decisions, account=VirtualAccount(cash=cash),
        cash_events=value.get('cash_events', []), fee_calculator=dated_research_fee)
    marker = simulation_execution_marker()
    for row in journal:
        row['execution_marker'] = dict(marker)
        for key in ('fill', 'created_order', 'rejected_order'):
            if row.get(key) is not None:
                row[key]['execution_marker'] = dict(marker)
    final_account = account.to_dict()
    final_account['execution_marker'] = dict(marker)
    return dict(schema_version='shared-execution-engineering-replay-v1', symbol=symbol,
        input_sha256=expected_sha256, scope='SYNTHETIC_ENGINEERING_FIXTURE',
        execution_marker=marker, journal=journal, final_account=final_account,
        initial_cash_is_synthetic=True, price_inputs_are_synthetic=True,
        historical_execution_validated=False, strict_pit_admitted=False,
        investment_rule_validated=False, performance_claim_allowed=False,
        cost_limitations=['Commission is a scenario, not broker invoice.',
                         'Dividend withholding tax is not validated.'], action='no_order')

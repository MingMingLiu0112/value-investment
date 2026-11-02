"""Scope and outcome projection over existing four-channel screening, not a new strategy."""
from __future__ import annotations

VERSION = 'sse-main-screening-v1'
CHANNELS = ('quality', 'dividend_cash_return', 'value', 'cyclical')


def project_outcome(evaluations, *, risk_warning=False, price_conflict=False):
    by_channel = {row['channel']: row for row in evaluations}
    if len(by_channel) != len(evaluations) or set(by_channel) != set(CHANNELS):
        raise ValueError('FOUR_CHANNEL_EVALUATIONS_REQUIRED')
    allowed = {'PASS', 'BUDGET_EXCLUDED', 'REJECTED', 'DATA_GAP', 'CONFLICT', 'UNSUPPORTED', 'NOT_EVALUATED'}
    if any(row['status'] not in allowed or not row.get('reason') for row in evaluations):
        raise ValueError('INVALID_CHANNEL_EVALUATION')
    gaps = [row['channel'] + ': ' + row['reason'] for row in evaluations
            if row['status'] in {'DATA_GAP', 'CONFLICT', 'NOT_EVALUATED'}]
    channels = [name for name in CHANNELS if by_channel[name]['status'] in {'PASS', 'BUDGET_EXCLUDED'}]
    if risk_warning:
        return dict(status='EXCLUDED', channels=[], reason='风险警示证券不进入本轮普通企业观察池。', gaps=gaps)
    if price_conflict or any(row['status'] == 'CONFLICT' for row in evaluations):
        return dict(status='UNASSESSABLE', channels=[], reason='来源报价存在冲突，不能确认入池。', gaps=gaps)
    if channels:
        return dict(status='CANDIDATE', channels=channels,
                    reason='通过列明通道的初筛条件，仅进入待研究观察池；不证明经济质量或可以买入。', gaps=gaps)
    if gaps:
        return dict(status='UNASSESSABLE', channels=[],
                    reason='尚无通道通过，且仍有资料或适用性未知；不能当作已充分评价后排除。', gaps=gaps)
    return dict(status='EXCLUDED', channels=[], reason='四通道均未通过或明确不适用，具体依据见逐通道记录。', gaps=[])

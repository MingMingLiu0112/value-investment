"""Manual declarations, separately typed as plans, fills and retrospective reviews."""
from __future__ import annotations

from datetime import date
import hashlib
import json

from .dual_sleeve_risk import SLEEVES, decimal, digest, fields, text, timestamp

SCHEMA = 'dual-sleeve-manual-record-v1'
BODY_FIELDS = ('record_id', 'kind', 'namespace', 'sleeve', 'symbol', 'recorded_at',
    'trade_date', 'research_version_sha256', 'candidate_action', 'observed_price_cny',
    'reason', 'risk_budget_cny', 'invalidation_condition', 'user_confirmation',
    'plan_record_sha256', 'fill', 'retrospective', 'evidence_ref')


def canonical_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')


def record_sha256(record):
    return hashlib.sha256(canonical_bytes(record)).hexdigest()


def validate_manual_body(body, *, namespace, generated_at):
    fields(body, BODY_FIELDS, 'manual record')
    if body['namespace'] != namespace or body['sleeve'] not in SLEEVES:
        raise ValueError('manual record namespace or sleeve mismatch')
    if body['kind'] not in ('PLAN', 'FILL', 'REVIEW'):
        raise ValueError('manual record kind must be PLAN, FILL or REVIEW')
    text(body['record_id'], 'record id')
    if not isinstance(body['symbol'], str) or len(body['symbol']) != 6 or not body['symbol'].isdigit():
        raise ValueError('manual record requires six-digit symbol')
    recorded = timestamp(body['recorded_at'], 'recorded_at')
    if recorded > generated_at:
        raise ValueError('manual record in future')
    trade_date = date.fromisoformat(body['trade_date'])
    if trade_date > recorded.date():
        raise ValueError('trade date cannot be after recording')
    digest(body['research_version_sha256'], 'research version')
    if body['candidate_action'] not in ('BUY_CANDIDATE', 'ADD_CANDIDATE', 'HOLD', 'TRIM_CANDIDATE',
            'SELL_CANDIDATE', 'NO_ACTION', 'ENTRY_REVIEW_CANDIDATE', 'EXIT_REVIEW_CANDIDATE'):
        raise ValueError('unknown manual candidate action')
    decimal(body['observed_price_cny'], 'observed price', positive=True)
    decimal(body['risk_budget_cny'], 'manual risk budget')
    for key in ('reason', 'invalidation_condition', 'evidence_ref'):
        text(body[key], key)
    if body['user_confirmation'] not in ('PENDING', 'USER_CONFIRMED'):
        raise ValueError('manual record requires explicit confirmation status')
    if body['kind'] == 'PLAN':
        if any(body[key] is not None for key in ('plan_record_sha256', 'fill', 'retrospective')):
            raise ValueError('plan is not a fill or retrospective')
    else:
        digest(body['plan_record_sha256'], 'linked plan')
    if body['kind'] == 'FILL':
        if body['user_confirmation'] != 'USER_CONFIRMED' or body['retrospective'] is not None:
            raise ValueError('fill requires manual confirmation, not estimated execution')
        fill = body['fill']
        fields(fill, ('transaction_id', 'side', 'quantity', 'price_cny', 'fees_cny',
            'next_sell_session', 'source_ref'), 'manual fill')
        text(fill['transaction_id'], 'transaction id')
        text(fill['source_ref'], 'manual fill source')
        if fill['side'] not in ('BUY', 'SELL'):
            raise ValueError('fill side must be BUY or SELL')
        quantity = decimal(fill['quantity'], 'fill quantity', positive=True)
        if quantity != quantity.to_integral_value():
            raise ValueError('fill quantity must be whole shares')
        decimal(fill['price_cny'], 'fill price', positive=True)
        decimal(fill['fees_cny'], 'fill fees')
        if fill['side'] == 'BUY':
            if date.fromisoformat(fill['next_sell_session']) <= trade_date:
                raise ValueError('buy fill must preserve T+1 next actual sell session')
        elif fill['next_sell_session'] is not None:
            raise ValueError('sell fill does not invent a next sell session')
    elif body['kind'] == 'REVIEW':
        if body['fill'] is not None:
            raise ValueError('retrospective cannot contain a fill')
        text(body['retrospective'], 'retrospective')


def build_manual_record(body, *, previous_record_sha256, namespace, generated_at):
    validate_manual_body(body, namespace=namespace, generated_at=generated_at)
    if previous_record_sha256 is not None:
        digest(previous_record_sha256, 'previous record')
    return dict(schema_version=SCHEMA, action='no_order', previous_record_sha256=previous_record_sha256,
        body=json.loads(canonical_bytes(body)), acceptance_authority='NONE', changes_holdings=False)


def validate_manual_history(records, *, namespace, generated_at):
    previous, ids, plans, transactions = None, set(), {}, set()
    for record in records:
        fields(record, ('schema_version', 'action', 'previous_record_sha256', 'body',
            'acceptance_authority', 'changes_holdings'), 'manual journal')
        if record != build_manual_record(record['body'], previous_record_sha256=previous,
                namespace=namespace, generated_at=generated_at):
            raise ValueError('manual record chain or immutable semantics mismatch')
        body = record['body']
        if body['record_id'] in ids:
            raise ValueError('duplicate manual record id')
        ids.add(body['record_id'])
        if body['kind'] == 'PLAN':
            plans[record_sha256(record)] = body
        else:
            plan = plans.get(body['plan_record_sha256'])
            if plan is None or any(body[key] != plan[key] for key in ('namespace', 'sleeve', 'symbol', 'research_version_sha256')):
                raise ValueError('fill/review must bind an existing exact strategy plan')
            if timestamp(body['recorded_at'], 'recorded_at') < timestamp(plan['recorded_at'], 'plan time'):
                raise ValueError('fill/review cannot predate its linked plan')
            if body['kind'] == 'FILL':
                transaction = body['fill']['transaction_id']
                if transaction in transactions:
                    raise ValueError('duplicate manual transaction')
                transactions.add(transaction)
        previous = record_sha256(record)
    return previous

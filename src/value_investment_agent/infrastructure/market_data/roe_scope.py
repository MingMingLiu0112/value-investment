"""Prove ordinary ROE identity from retained structured source bytes."""
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

SIMPLE_LABEL = '\u51c0\u8d44\u4ea7\u6536\u76ca\u7387(%)'


def snapshot_proves_simple_roe(payload, symbol, period, value):
    try:
        snapshot = json.loads(payload)
        if not isinstance(snapshot, dict) or snapshot.get('code') != symbol:
            return False
        report_date = datetime.fromisoformat(str(snapshot['report_date'])).date().isoformat()
        if report_date != period or not isinstance(snapshot.get('row'), dict):
            return False
        source_value = Decimal(str(snapshot['row'][SIMPLE_LABEL]))
        expected = Decimal(str(value))
        return source_value.is_finite() and expected.is_finite() and source_value == expected
    except (ValueError, TypeError, KeyError, InvalidOperation, UnicodeDecodeError):
        return False

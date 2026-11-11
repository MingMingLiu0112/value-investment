"""Versioned source loader for the existing Q3 OCR cash-policy selection.

This adapter delegates source verification to the established V4 loader.
It does not invoke a model or change any historical task contract.
"""
from pathlib import Path

from . import operating_cash_policy_task_v4_q3_ocr as q3_cash
from .task_execution_v1 import _hash


VERSION = "operating-q3-cash-source-loader-v1"


def implementation():
    return {**q3_cash.implementation(), __name__: _hash(Path(__file__).read_bytes())}


def load_current(*, root, symbol, now, binding=None):
    service = q3_cash.OperatingCashPolicyTaskServiceV4(root, test_provider=object())
    return service._source(root=root, symbol=symbol, now=now, binding=binding)

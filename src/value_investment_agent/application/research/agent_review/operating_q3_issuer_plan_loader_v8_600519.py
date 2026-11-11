"""Bind the existing Q3 source with the issuer's finite dividend-plan PDF.

Historical V7 tasks and source bytes remain untouched.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from . import operating_q3_cash_source_loader_v1 as prior
from . import issuer_dividend_plan_v2 as plan
from .task_execution_v1 import _bytes, _hash

VERSION = "operating-q3-issuer-plan-loader-v8-600519"
RECEIPT = Path("artifacts/current/d2-issuer-dividend-plan-v2/receipt.json")


def implementation():
    return {**prior.implementation(),
            plan.__name__: _hash(Path(plan.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


def load_current(*, root, symbol, now: datetime, binding=None):
    if symbol != "600519":
        raise ValueError("V8_ISSUER_PLAN_SYMBOL_NOT_SUPPORTED")
    if binding is not None and (not isinstance(binding, dict)
            or set(binding) != {"base", "plan_receipt", "plan_original"}):
        raise ValueError("V8_ISSUER_PLAN_BINDING_INVALID")
    original = prior.load_current(root=root, symbol=symbol, now=now,
        binding=binding["base"] if binding else None)
    disclosed = plan.read_issuer_dividend_plan(Path(root), Path(root) / RECEIPT, now=now)
    observed = dict(base=original["source_binding"],
        plan_receipt=disclosed["receipt_binding"],
        plan_original=disclosed["source_binding"])
    if binding is not None and binding != observed:
        raise ValueError("V8_ISSUER_PLAN_SOURCE_CHANGED")
    if original["action"] != "no_order" or original["formal_eligibility"] is not False:
        raise ValueError("V8_BASE_RESEARCH_BOUNDARY_INVALID")
    result = deepcopy(original)
    result["schema_version"] = VERSION
    result["prior_source_binding"] = original["source_binding"]
    result["source_binding"] = observed
    result["issuer_dividend_plan"] = disclosed
    result["snapshot_fingerprint"] = sha256(_bytes([
        VERSION, original["snapshot_fingerprint"], observed, disclosed["available_at"]
    ])).hexdigest()
    result["action"] = "no_order"
    result["formal_eligibility"] = False
    return result

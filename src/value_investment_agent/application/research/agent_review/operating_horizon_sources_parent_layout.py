"""Source-bound D2 context for verified sparse or paginated parent statements."""
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .. import parent_cash_layout_observation
from ....infrastructure.filings import stock_identity_table_v1
from . import horizon_receipt_selection as preparation
from . import operating_horizon_context_budget as budget
from . import operating_horizon_sources_v1 as legacy
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes

VERSION = "operating-horizon-sources-parent-layout-v1"
CONFIG = "config/current-operating-parent-layout-sources-v1.json"


def implementation():
    modules = (preparation, parent_cash_layout_observation, stock_identity_table_v1, budget)
    return {**legacy.implementation(),
            **{module.__name__: _hash(Path(module.__file__).read_bytes()) for module in modules},
            __name__: _hash(Path(__file__).read_bytes())}


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if now.utcoffset() is None or not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("HORIZON_SOURCE_IDENTITY_OR_CLOCK_INVALID")
    identity = dict(schema_version=VERSION, symbol=symbol, as_of=now.isoformat(),
                    implementation_sha256=implementation(), action="no_order")
    if binding is None:
        config = require_inside(root, root / CONFIG, "parent layout source registry")
        raw = config.read_bytes()
        selection = legacy._selection(json.loads(raw).get(symbol))
        manifest = dict(identity, selection=selection,
                        selected_from=dict(path=CONFIG, sha256=_hash(raw)))
    else:
        manifest = legacy._bound(root, binding)
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("PARENT_LAYOUT_SOURCE_MANIFEST_CHANGED")
        selection = legacy._selection(manifest["selection"])
    if (set(selection) != {"issuer_name", "parent_cash_observation_receipts", "parent_cash_layout", "excerpts"}
            or selection["parent_cash_layout"] != "LEGACY_BLANK_SAFE_V3" or selection["excerpts"]):
        raise ValueError("PARENT_LAYOUT_RECEIPT_ONLY_SELECTION_REQUIRED")
    base = legacy._receipt_operating_base(root, symbol, selection, now)
    observed = preparation._observe_alternate_layout(root, symbol, selection, now)
    evidence, gaps, sources = [], [], []
    for statement in observed["historical_parent_cash"]:
        period = statement["period"]
        source = statement["source_binding"]
        pin = statement["receipt_binding"]
        packet = legacy._bound(root, pin)
        published = datetime.combine(date.fromisoformat(packet["published_date"]) + timedelta(days=1),
                                     time(), ZoneInfo("Asia/Shanghai"))
        available = max(legacy._clock(value, now) for value in (
            source["available_at"], packet["fetched_at"], packet["completed_at"], published.isoformat()))
        source = dict(source, available_at=available.isoformat())
        report = legacy.statements.load_operating_statement_basis(root=root, source=source, evaluation_at=now)
        if (report["symbol"] != symbol or report["source_binding"] != source
                or report["action"] != "no_order" or report["financial_quality_granted"] is not False):
            raise ValueError("HORIZON_STATEMENT_BINDING_INVALID")
        evidence.extend(dict(legacy._fact(row), receipt_binding=pin) for row in report["evidence"])
        gaps.extend(dict(gap, report_period=period) for gap in report["gaps"])
        for field, row in statement["rows"].items():
            text = row["evidence_excerpt"]
            evidence.append(dict(id=packet["source_id"] + ":parent-cash-layout:" + field,
                source_id=packet["source_id"], pdf_sha256=source["sha256"], physical_page=row["physical_page"],
                available_at=available.isoformat(), period=period,
                period_basis="FY" if period.endswith("12-31") else "H1",
                scope="ISSUER_PARENT_STANDALONE", unit="CNY", field=field,
                value=row["columns"][0]["value"], text=text, text_sha256=_hash(text.encode("utf-8")),
                kind="SOURCE_BOUND_PARENT_CASH_OBSERVATION_NOT_POLICY", receipt_binding=pin))
        gaps.extend(dict(reason=reason + ":" + field, report_period=period)
                    for field, reason in statement["unknown_fields"].items())
        sources.append(dict(source, receipt_binding=pin, source_id=packet["source_id"]))
    if not 1 <= len(evidence) <= 100 or len({row["id"] for row in evidence}) != len(evidence):
        raise ValueError("HORIZON_EVIDENCE_LIMIT_OR_DUPLICATE")
    raw = _bytes(manifest)
    relative = Path("runtime") / VERSION / (_hash(raw) + ".json")
    expected = dict(path=relative.as_posix(), sha256=_hash(raw))
    if binding is not None and binding != expected:
        raise ValueError("PARENT_LAYOUT_SOURCE_MANIFEST_CHANGED")
    context = dict(schema_version=legacy.VERSION, source_adapter_version=VERSION,
        symbol=symbol, issuer_name=selection["issuer_name"], as_of=now.isoformat(),
        financial_basis=base["financial_basis"], source_binding=expected,
        base_source_binding=base["source_binding"], supplemental_sources=sources,
        parent_cash_observation_receipts=selection["parent_cash_observation_receipts"],
        evidence=evidence, statement_basis_gaps=gaps, implementation_sha256=identity["implementation_sha256"],
        scope_decomposition=None, prior_conditional_hypothesis=None, action="no_order",
        formal_eligibility=False, limitations=["Historical observations only; omitted amounts remain unknown."])
    context["snapshot_fingerprint"] = _hash(_bytes(context))
    if budget.measure_compact_context_chars(context) > legacy.MAX_CONTEXT_CHARS:
        raise ValueError("HORIZON_SOURCE_CONTEXT_OVER_BUDGET")
    path = require_inside(root, root / relative, "parent layout source manifest")
    try:
        write_new_bytes(path, raw)
    except FileExistsError:
        legacy._bound(root, expected)
    return context

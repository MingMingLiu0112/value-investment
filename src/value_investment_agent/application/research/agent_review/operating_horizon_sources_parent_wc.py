"""Versioned D2 source with explicitly reconciled parent working-capital cash."""
from decimal import Decimal
import json
from pathlib import Path

from ....infrastructure.filings import parent_working_capital_cash as wc
from ...product.common import require_inside, write_new_bytes
from .. import parent_cash_layout_observation as parent_cash
from . import operating_horizon_sources_parent_layout as base
from .task_execution_v1 import _bytes, _hash

VERSION = "operating-horizon-sources-parent-wc-v1"
CONFIG = "config/current-operating-parent-wc-sources-v1.json"


def _cash_rows(root, context):
    evidence = []
    for source in context["supplemental_sources"]:
        original = require_inside(root / "runtime", root / source["path"], "parent WC original")
        if _hash(original.read_bytes()) != source["sha256"]:
            raise ValueError("PARENT_WC_ORIGINAL_HASH_MISMATCH")
        pages = base.legacy.pdf_text.extract_pages(original)
        if _hash(original.read_bytes()) != source["sha256"]:
            raise ValueError("PARENT_WC_ORIGINAL_CHANGED_DURING_EXTRACTION")
        # Its own exact issuer, CNY units, report headings and printed columns
        # are verified separately from the reconciliation note.
        direct = parent_cash.observe_parent_cash_rows(
            pages=pages, symbol=context["symbol"], issuer_name=context["issuer_name"],
            period=source["period"],
        )
        printed = direct["rows"]["cfo_cny"]
        pair = tuple(Decimal(row["value"]) for row in printed["columns"])
        try:
            note = wc.read_parent_working_capital_cash(pages, verified_parent_cfo_cny=pair)
        except ValueError as error:
            if str(error) == "PARENT_WC_CASH_EXPLICIT_NOTE_REQUIRED" and not wc.has_explicit_parent_note(pages):
                continue
            raise
        text = ("母公司营运资金历史现金调整（本期及上年同期）；" +
                json.dumps(note, ensure_ascii=False, sort_keys=True) +
                "。本期金额按原附注现金影响符号列示，不是未来营运资金支出。")
        evidence.append(dict(
            id=source["source_id"] + ":parent-working-capital-cash",
            source_id=source["source_id"], pdf_sha256=source["sha256"],
            physical_page=note["physical_page"], available_at=source["available_at"],
            period=source["period"], period_basis="FY" if source["period"].endswith("-12-31") else "H1",
            scope=note["scope"], unit=note["unit"], field=note["field"],
            value=note["cash_impact_cny"][0], text=text, text_sha256=_hash(text.encode("utf-8")),
            kind="SOURCE_BOUND_PARENT_CASH_OBSERVATION_NOT_POLICY",
            receipt_binding=source["receipt_binding"],
        ))
    if not evidence:
        raise ValueError("PARENT_WC_NO_RECONCILED_SOURCE")
    return evidence


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    identity = dict(schema_version=VERSION, symbol=symbol, as_of=now.isoformat(), action="no_order",
                    implementation_sha256={**base.implementation(),
                        wc.__name__: _hash(Path(wc.__file__).read_bytes()),
                        __name__: _hash(Path(__file__).read_bytes())})
    if binding is None:
        config = require_inside(root, root / CONFIG, "parent WC source opt-in")
        config_raw = config.read_bytes()
        if json.loads(config_raw).get(symbol) is not True:
            raise ValueError("PARENT_WC_EXPLICIT_OPT_IN_REQUIRED")
        context = base.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(identity, base_binding=context["source_binding"],
                        selected_from=dict(path=CONFIG, sha256=_hash(config_raw)))
    else:
        manifest = base.legacy._bound(root, binding)
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("PARENT_WC_SOURCE_MANIFEST_CHANGED")
        context = base.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"],
        )
    evidence = [*context["evidence"], *_cash_rows(root, context)]
    if len(evidence) > 100 or len({row["id"] for row in evidence}) != len(evidence):
        raise ValueError("HORIZON_EVIDENCE_LIMIT_OR_DUPLICATE")
    raw = _bytes(manifest)
    digest = _hash(raw)
    relative = Path("runtime") / VERSION / (digest + ".json")
    expected = dict(path=relative.as_posix(), sha256=digest)
    if binding is not None and binding != expected:
        raise ValueError("PARENT_WC_SOURCE_MANIFEST_CHANGED")
    context = {**context, "evidence": evidence, "source_binding": expected,
               "source_adapter_version": VERSION, "base_source_binding": manifest["base_binding"],
               "implementation_sha256": identity["implementation_sha256"]}
    context.pop("snapshot_fingerprint")
    context["snapshot_fingerprint"] = _hash(_bytes(context))
    if base.budget.measure_compact_context_chars(context) > base.legacy.MAX_CONTEXT_CHARS:
        raise ValueError("HORIZON_SOURCE_CONTEXT_OVER_BUDGET")
    path = require_inside(root, root / relative, "parent WC manifest")
    try:
        write_new_bytes(path, raw)
    except FileExistsError:
        base.legacy._bound(root, expected)
    return context

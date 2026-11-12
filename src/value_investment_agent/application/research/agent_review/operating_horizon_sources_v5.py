"""Add a bounded official nine-month observation to the existing D2 corpus.

The FY/H1 parent cash context remains the capital opening. Nine-month
consolidated flows are observations and counter-evidence, not parent cash,
annual forecasts, or an adopted valuation.
"""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re

from . import operating_horizon_sources_v1 as v1
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import (pdf_text, quarterly_operating_facts_v1 as quarterly,
                                      native_capital_observation_v1 as capital)
from ....infrastructure.filings.native_capital_observation_v1 import _raw_excerpt
from .. import main_valuation_revalidation_v1 as revalidation
from ..main_valuation_revalidation_v1 import _verify_quarter_receipt

VERSION = "operating-horizon-sources-v5"
CONFIG = "config/current-operating-quarterly-sources-v1.json"
MAX_CONTEXT_CHARS = 71000
FIELDS = ("revenue", "parent_profit", "cfo")


def implementation():
    modules = (quarterly, pdf_text, capital, revalidation)
    return {**v1.implementation(), **{m.__name__: _hash(Path(m.__file__).read_bytes()) for m in modules},
            __name__: _hash(Path(__file__).read_bytes())}


def _selection(root, symbol):
    raw = (root / CONFIG).read_bytes()
    registry = json.loads(raw)
    if (registry.get("schema_version") != "operating-quarterly-source-selection-v1"
            or registry.get("action") != "no_order" or not isinstance(registry.get("cases"), dict)):
        raise ValueError("QUARTERLY_D2_SELECTION_INVALID")
    selected = registry["cases"].get(symbol)
    if (not isinstance(selected, dict)
            or set(selected) != {"receipt_path", "receipt_sha256", "pdf_path", "pdf_sha256", "source_id"}
            or any(not isinstance(selected[k], str) or not selected[k].startswith("runtime/")
                   for k in ("receipt_path", "pdf_path"))
            or any(not isinstance(selected[k], str) or not re.fullmatch(r"[0-9a-f]{64}", selected[k])
                   for k in ("receipt_sha256", "pdf_sha256"))
            or not isinstance(selected["source_id"], str)
            or not re.fullmatch(r"cninfo:[0-9]+", selected["source_id"])):
        raise ValueError("QUARTERLY_D2_CASE_NOT_CONFIGURED")
    return selected, dict(path=CONFIG, sha256=_hash(raw))


def _quarterly_rows(root, symbol, base, selected, now):
    receipt_path = require_inside(root / "runtime", root / selected["receipt_path"], "D2 quarter receipt")
    pdf_path = require_inside(root / "runtime", root / selected["pdf_path"], "D2 quarter original")
    if (_hash(receipt_path.read_bytes()) != selected["receipt_sha256"]
            or _hash(pdf_path.read_bytes()) != selected["pdf_sha256"]):
        raise ValueError("QUARTERLY_D2_SOURCE_HASH_CHANGED")
    receipt = json.loads(receipt_path.read_bytes())
    if receipt.get("action") != "no_order" or not isinstance(receipt.get("records"), list):
        raise ValueError("QUARTERLY_D2_RECEIPT_INVALID")
    matched = [row for row in receipt["records"] if isinstance(row, dict)
               and row.get("path") == selected["pdf_path"]
               and row.get("sha256") == selected["pdf_sha256"]]
    if len(matched) != 1:
        raise ValueError("QUARTERLY_D2_RECEIPT_PDF_MISMATCH")
    source = matched[0]
    _verify_quarter_receipt(source, {"symbol": symbol, "quarterly_source_id": selected["source_id"]},
                            {"symbol": symbol, "issuer_name": base["issuer_name"]}, now, receipt)
    h1 = [row for row in base["supplemental_sources"] if row.get("period") == base["financial_basis"]
          and row.get("symbol") == symbol]
    if len(h1) != 1:
        raise ValueError("QUARTERLY_D2_H1_CURRENCY_SOURCE_REQUIRED")
    h1_source = h1[0]
    h1_path = require_inside(root / "runtime", root / h1_source["path"], "D2 H1 currency original")
    if _hash(h1_path.read_bytes()) != h1_source["sha256"]:
        raise ValueError("QUARTERLY_D2_H1_CURRENCY_SOURCE_CHANGED")
    h1_page = pdf_text.extract_pages(h1_path, limit=56)[55]
    sentence = "4、记账本位币以人民币为记账本位币。"
    if sentence not in "".join(h1_page.split()):
        raise ValueError("QUARTERLY_D2_CURRENCY_BASIS_MISSING")
    currency_basis = dict(currency="CNY", evidence_refs=[dict(
        id=h1_source["source_id"], path=h1_source["path"], sha256=h1_source["sha256"],
        physical_page=56, excerpt=_raw_excerpt(h1_page, sentence))])
    quarter = quarterly.parse_quarterly_operating_facts(
        pdf_text.extract_pages(pdf_path, limit=80), symbol=symbol, currency_basis=currency_basis)
    available = source["available_at"]
    if datetime.fromisoformat(available) > now:
        raise ValueError("QUARTERLY_D2_SOURCE_AFTER_CUTOFF")
    rows = []
    for field in FIELDS:
        item = quarter["fields"][field]
        for column, period in (("current", quarter["period_end"]),
                               ("comparative", quarter["comparative_end"])):
            text = f"九个月合并报表{field}：{item[column]}元（{period}止，{column}列）；原文：{item['excerpt']}"
            rows.append(dict(id=f"{selected['source_id']}:{field}:{column}", source_id=selected["source_id"],
                pdf_sha256=selected["pdf_sha256"], available_at=available, period=period,
                period_basis="YTD_9M", scope=item["scope"], unit="CNY", field=field,
                value=item[column], text=text, text_sha256=_hash(text.encode("utf-8")),
                physical_page=item["physical_page"], kind="REPORTED_HISTORICAL_FACT_NOT_FORECAST"))
    return rows, dict(source_id=selected["source_id"], path=selected["pdf_path"],
        sha256=selected["pdf_sha256"], receipt_binding=dict(path=selected["receipt_path"],
        sha256=selected["receipt_sha256"]), source_url=source["url"],
        available_at=available, period=quarter["period_end"], scope="CONSOLIDATED_9M_ONLY")


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("QUARTERLY_D2_AS_OF_INVALID")
    selected, pin = _selection(root, symbol)
    if binding is None:
        base = v1.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(schema_version=VERSION, action="no_order", symbol=symbol, as_of=now.isoformat(),
            base_binding=deepcopy(base["source_binding"]), base_context_sha256=_hash(_bytes(base)),
            selection=deepcopy(selected), selected_from=pin, implementation_sha256=implementation())
        raw = _bytes(manifest)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (_hash(raw) + ".json"),
                              "D2 quarterly manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = v1._bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("action") != "no_order"
                or manifest.get("symbol") != symbol or manifest.get("as_of") != now.isoformat()
                or manifest.get("implementation_sha256") != implementation()
                or manifest.get("selection") != selected or manifest.get("selected_from") != pin):
            raise ValueError("QUARTERLY_D2_MANIFEST_CHANGED")
        base = v1.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        path = None
    if (base["source_binding"] != manifest["base_binding"]
            or _hash(_bytes(base)) != manifest["base_context_sha256"]):
        raise ValueError("QUARTERLY_D2_BASE_CHANGED")
    rows, source = _quarterly_rows(root, symbol, base, selected, now)
    result = deepcopy(base)
    if len(result["evidence"]) + len(rows) > 100 or set(r["id"] for r in result["evidence"]) & set(r["id"] for r in rows):
        raise ValueError("QUARTERLY_D2_EVIDENCE_LIMIT_OR_DUPLICATE")
    result["evidence"].extend(rows)
    result["supplemental_sources"].append(source)
    result["limitations"].append("Nine-month consolidated facts do not establish parent cash access or future policy")
    result.update(schema_version=VERSION, source_binding=deepcopy(binding),
                  implementation_sha256=manifest["implementation_sha256"])
    result["snapshot_fingerprint"] = _hash(_bytes({k: v for k, v in result.items()
                                                    if k != "snapshot_fingerprint"}))
    if len(_bytes(result).decode("utf-8")) > MAX_CONTEXT_CHARS:
        raise ValueError("QUARTERLY_D2_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            v1._bound(root, binding)
        else:
            write_new_bytes(path, _bytes(manifest))
    return result

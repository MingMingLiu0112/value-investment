"""Append three sealed historical dividend implementations to the V8 Q3 source.

This source-only loader creates no task, forecast, personal payment or order.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from . import operating_q3_issuer_plan_loader_v8_600519 as prior
from .task_execution_v1 import _bytes, _hash
from ....infrastructure.filings import official_dividend_split_receipt_v2 as split

VERSION = "operating-q3-issuer-dividend-split-loader-v9-600519"
IDS = ("1222015210", "1223934491", "1224867074")
PERIODS = ("FY2024_interim", "FY2024_final", "FY2025_interim")
PERIOD_ENDS = ("2024-06-30", "2024-12-31", "2025-06-30")
SUFFIXES = ("-cninfo-response.json", "-index-receipt.json", ".pdf", "-pdf-receipt.json")
KEYS = ("index_response", "index_receipt", "pdf", "pdf_receipt")
CAPTURE_DIR = Path("runtime/operating-dividend-split-v9")
MAX_EVIDENCE = 100
MAX_CONTEXT_BYTES = 80000


def implementation():
    return {**prior.implementation(),
        split.__name__: _hash(Path(split.__file__).read_bytes()),
        __name__: _hash(Path(__file__).read_bytes())}


def _file(root, path, name):
    candidate = (root / path).resolve()
    if (not candidate.is_relative_to(root) or not candidate.is_file()
            or candidate.name != name):
        raise ValueError("V9_SPLIT_PATH_INVALID")
    return candidate


def _captures(root, directory, aid, pinned=None):
    files = {}
    for key, suffix in zip(KEYS, SUFFIXES):
        filename = aid + suffix
        if pinned is None:
            path = _file(root, directory / filename, filename)
            files[key] = dict(path=path.relative_to(root).as_posix(),
                              sha256=_hash(path.read_bytes()))
        else:
            item = pinned.get(key)
            if (not isinstance(item, dict) or set(item) != {"path", "sha256"}
                    or not isinstance(item["path"], str)):
                raise ValueError("V9_SPLIT_BINDING_INVALID")
            path = _file(root, Path(item["path"]), filename)
            if path.parent != (root / CAPTURE_DIR).resolve():
                raise ValueError("V9_SPLIT_PATH_INVALID")
            if _hash(path.read_bytes()) != item["sha256"]:
                raise ValueError("V9_SPLIT_BYTES_CHANGED")
            files[key] = deepcopy(item)
    return files


def load_current(*, root, symbol, now: datetime, binding=None):
    root = Path(root).resolve()
    if (symbol != "600519" or not isinstance(now, datetime)
            or now.utcoffset() is None):
        raise ValueError("V9_SPLIT_IDENTITY_OR_AS_OF_INVALID")
    if binding is None:
        base = prior.load_current(root=root, symbol=symbol, now=now)
        entries = [dict(announcement_id=aid, files=_captures(root, CAPTURE_DIR, aid))
                   for aid in IDS]
        observed = dict(base=deepcopy(base["source_binding"]),
                        base_context_sha256=_hash(_bytes(base)),
                        implementation_sha256=implementation(), split=entries)
    else:
        if (not isinstance(binding, dict)
                or set(binding) != {"base", "base_context_sha256", "implementation_sha256", "split"}
                or binding["implementation_sha256"] != implementation()
                or not isinstance(binding["split"], list)
                or len(binding["split"]) != len(IDS)):
            raise ValueError("V9_SPLIT_BINDING_INVALID")
        base = prior.load_current(root=root, symbol=symbol, now=now, binding=binding["base"])
        entries = []
        for aid, item in zip(IDS, binding["split"]):
            if not isinstance(item, dict) or set(item) != {"announcement_id", "files"} \
                    or item["announcement_id"] != aid or not isinstance(item["files"], dict) \
                    or set(item["files"]) != set(KEYS):
                raise ValueError("V9_SPLIT_BINDING_INVALID")
            entries.append(dict(announcement_id=aid,
                                files=_captures(root, Path(), aid, item["files"])))
        observed = dict(base=deepcopy(base["source_binding"]),
                        base_context_sha256=_hash(_bytes(base)),
                        implementation_sha256=implementation(), split=entries)
        if binding != observed:
            raise ValueError("V9_SPLIT_SOURCE_CHANGED")
    if base.get("action") != "no_order" or base.get("formal_eligibility") is not False:
        raise ValueError("V9_BASE_BOUNDARY_INVALID")
    reports = []
    for aid, period, item in zip(IDS, PERIODS, entries):
        files = item["files"]
        report = split.replay_split_dividend_implementation(root=root,
            index_response_path=root / files["index_response"]["path"],
            index_receipt_path=root / files["index_receipt"]["path"],
            pdf_path=root / files["pdf"]["path"],
            pdf_receipt_path=root / files["pdf_receipt"]["path"],
            symbol=symbol, issuer_name=base["issuer_name"], as_of=now)
        if (report["announcement_id"] != aid or report["report_period"] != period
                or report["action"] != "no_order" or report["formal_eligibility"] is not False
                or report["pdf_sha256"] != files["pdf"]["sha256"]
                or report["index_response_sha256"] != files["index_response"]["sha256"]
                or report["index_receipt_sha256"] != files["index_receipt"]["sha256"]
                or report["pdf_receipt_sha256"] != files["pdf_receipt"]["sha256"]):
            raise ValueError("V9_SPLIT_REPLAY_CHANGED")
        reports.append(report)
    result = deepcopy(base)
    if len(result["evidence"]) + len(reports) > MAX_EVIDENCE:
        raise ValueError("V9_SPLIT_EVIDENCE_OVER_BUDGET")
    old_ids = {row["id"] for row in result["evidence"]}
    for report, item, period_end in zip(reports, entries, PERIOD_ENDS):
        text = (f"{report['report_period']}已批准的历史权益分派实施安排：每股现金红利"
            f"{report['per_share_cny']}元，实施股数{report['implemented_shares']}股，"
            f"公告分派金额{report['implemented_total_cny']}元；登记日{report['record_date']}，"
            f"公告发放日{report['scheduled_payment_date']}。不证明个人到账、2027分红政策、"
            "母公司可达现金或未来资本承诺。")
        row_id = f"cninfo:{report['announcement_id']}:historical-split-implementation"
        if row_id in old_ids:
            raise ValueError("V9_SPLIT_EVIDENCE_DUPLICATE")
        old_ids.add(row_id)
        result["evidence"].append(dict(id=row_id,
            source_id=f"cninfo:{report['announcement_id']}",
            pdf_sha256=report["pdf_sha256"], available_at=report["available_at"],
            period=period_end, period_basis=report["report_period"],
            scope="ISSUER_HISTORICAL_DISTRIBUTION_SCHEDULE", unit="TEXT", text=text,
            text_sha256=_hash(text.encode("utf-8")), physical_pages=report["physical_pages"],
            kind=report["status"], capture_binding=deepcopy(item["files"])))
    # V15 calls the V8 projector directly. Preserve its schema and old fields;
    # the new source identity lives in the loader version and source binding.
    result["schema_version"] = prior.VERSION
    result["source_binding"] = observed
    result["historical_dividend_source_version"] = VERSION
    result["implementation_sha256"] = implementation()
    result["historical_dividend_implementations"] = reports
    result["snapshot_fingerprint"] = sha256(_bytes([
        VERSION, base["snapshot_fingerprint"], observed, reports])).hexdigest()
    if len(_bytes(result)) > MAX_CONTEXT_BYTES:
        raise ValueError("V9_SPLIT_CONTEXT_OVER_BUDGET")
    return result


def project_research_context(source_context):
    if (source_context.get("schema_version") != prior.VERSION
            or source_context.get("action") != "no_order"
            or source_context.get("formal_eligibility") is not False
            or source_context.get("historical_dividend_source_version") != VERSION
            or source_context.get("source_binding", {}).get("implementation_sha256") != implementation()):
        raise ValueError("V9_SPLIT_CONTEXT_INVALID")
    return prior.project_research_context(source_context)

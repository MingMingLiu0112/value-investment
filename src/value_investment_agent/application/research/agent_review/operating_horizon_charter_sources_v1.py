"""Optional charter evidence for the existing V25 base source corpus."""

from datetime import datetime
import json
from pathlib import Path
import re

from . import operating_horizon_sources_v1 as base
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import statutory_reserve_clause as charter


VERSION = "operating-horizon-charter-sources-v1"
CONFIG = "config/current-operating-charter-sources-v1.json"


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    if now.utcoffset() is None:
        raise ValueError("CHARTER_SOURCE_AWARE_CUTOFF_REQUIRED")
    root = Path(root).resolve()
    identity = dict(
        version=VERSION, symbol=symbol, as_of=now.isoformat(), action="no_order",
        implementation_sha256={m: _hash(Path(p).read_bytes())
                               for m, p in ((__name__, __file__), (charter.__name__, charter.__file__))},
    )
    if binding is None:
        selection = json.loads((root / CONFIG).read_bytes())[symbol]
        original = base.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(identity, selection=selection, base_binding=original["source_binding"],
                        base_context_sha256=_hash(_bytes(original)))
    else:
        manifest = base._bound(root, binding)
        if any(manifest.get(k) != v for k, v in identity.items()):
            raise ValueError("CHARTER_SOURCE_MANIFEST_CHANGED")
        selection = manifest["selection"]
        original = base.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        if _hash(_bytes(original)) != manifest["base_context_sha256"]:
            raise ValueError("CHARTER_SOURCE_BASE_CHANGED")

    if not isinstance(selection, dict) or set(selection) != {"path", "sha256", "url", "available_at"}:
        raise ValueError("CHARTER_SOURCE_SELECTION_INVALID")
    source = re.fullmatch(
        r"https://static\.cninfo\.com\.cn/finalpage/(\d{4}-\d{2}-\d{2})/(\d+)\.PDF", selection["url"])
    available = datetime.fromisoformat(selection["available_at"])
    if (not source or available.utcoffset() is None or available > now
            or available.date().isoformat() < source[1]):
        raise ValueError("CHARTER_SOURCE_URL_OR_AVAILABILITY_INVALID")
    original_pdf = require_inside(root / "runtime", root / selection["path"], "charter PDF")
    rule = charter.read_statutory_reserve_clause(
        original_pdf, issuer=original["issuer_name"], expected_sha256=selection["sha256"])
    source_id = "cninfo:" + source[2]
    text = ("母公司法定公积金通常从当年税后利润提取10%；累计达到注册资本50%时可以停止。"
            "本条为章程规则，未来计提须核对届时资本、公积金、亏损及实际决议。")
    row = dict(id=source_id + ":statutory_reserve_rule", source_id=source_id,
               scope=rule["scope"], field="statutory_reserve_rule", unit="TEXT",
               period=source[1], physical_page=rule["physical_page"], available_at=available.isoformat(),
               pdf_sha256=rule["source_sha256"], kind="REPORTED_HISTORICAL_FACT_NOT_FORECAST",
               text=text, text_sha256=_hash(text.encode("utf-8")))
    if len(original["evidence"]) >= 100 or any(e["id"] == row["id"] for e in original["evidence"]):
        raise ValueError("CHARTER_SOURCE_DUPLICATE_OR_LIMIT")
    if binding is None:
        raw = _bytes(manifest)
        digest = _hash(raw)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (digest + ".json"),
                              "charter source manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=digest)
        if path.exists():
            base._bound(root, binding)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_new_bytes(path, raw)

    result = dict(original, source_binding=binding, source_adapter_version=VERSION,
                  implementation_sha256=identity["implementation_sha256"], evidence=[row, *original["evidence"]])
    result.pop("snapshot_fingerprint", None)
    result["snapshot_fingerprint"] = _hash(_bytes(result))
    return result

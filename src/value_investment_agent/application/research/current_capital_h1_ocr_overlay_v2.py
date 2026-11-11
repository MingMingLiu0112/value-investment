"""Read-only H1 share observation attached to the frozen capital read model."""
from datetime import datetime
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re

from .current_capital_observation_v1 import read_current_capital_observation
from ...infrastructure.filings.official_halfyear_shares_ocr_v2 import replay_halfyear_shares

REGISTRY = "config/current-capital-h1-ocr-v2.json"
VERSION = "current-capital-h1-ocr-overlay-v2"
FILES = frozenset({"source-manifest.json", "original.pdf", "cross-notice.pdf",
                   "page-22.png", "page-23.png", "page-22.ocr.json", "page-23.ocr.json"})


def _load(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("H1_DUPLICATE_REGISTRY_KEY")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_capital_with_h1_shares(root: Path, symbol: str, as_of: datetime) -> dict:
    """Return v1 read model plus a separate historical, non-eligible H1 row."""
    root = Path(root).resolve()
    base = read_current_capital_observation(root, symbol, as_of)
    result = dict(base)
    h1 = {"schema_version": VERSION, "status": "NOT_REGISTERED",
          "report_period_end": None, "ordinary_shares": None,
          "current_continuity": "UNPROVEN", "formal_eligibility": False,
          "action": "no_order"}
    result["h1_share_observation"] = h1
    try:
        registry = root / REGISTRY
        if not registry.is_file():
            return result
        raw = registry.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("H1_REGISTRY_TOO_LARGE")
        doc = _load(raw)
        if (not isinstance(doc, dict) or set(doc) != {"schema_version", "action", "cases"}
                or doc["schema_version"] != VERSION or doc["action"] != "no_order"
                or not isinstance(doc["cases"], dict)):
            raise ValueError("H1_REGISTRY_INVALID")
        case = doc["cases"].get(symbol)
        if case is None:
            return result
        if (not isinstance(case, dict) or set(case) != {"issuer_name", "report_year",
                "report_period_end", "original_available_at", "cross_notice_available_at", "files"}
                or type(case["report_year"]) is not int
                or case["report_period_end"] != f'{case["report_year"]}-06-30'
                or not isinstance(case["issuer_name"], str) or not case["issuer_name"]
                or not isinstance(case["files"], dict) or set(case["files"]) != FILES):
            raise ValueError("H1_REGISTRY_CASE_INVALID")
        evidence_dir = None
        for name, record in case["files"].items():
            if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
                raise ValueError("H1_REGISTRATION_INVALID")
            relative, expected = record["path"], record["sha256"]
            if (not isinstance(relative, str) or not isinstance(expected, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", expected)
                    or not relative.startswith("runtime/") or "\\" in relative
                    or Path(relative).is_absolute() or PureWindowsPath(relative).drive
                    or ".." in PureWindowsPath(relative).parts):
                raise ValueError("H1_REGISTRATION_INVALID")
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or path.name != name:
                raise ValueError("H1_REGISTRATION_INVALID")
            if evidence_dir is None:
                evidence_dir = path.parent
            if path.parent != evidence_dir or not path.is_file():
                raise ValueError("H1_REGISTERED_SOURCE_MISSING")
            if _digest(path) != expected:
                raise ValueError("H1_REGISTERED_SOURCE_HASH_MISMATCH")
        manifest = _load((evidence_dir / "source-manifest.json").read_bytes())
        if (manifest.get("original_available_at") != case["original_available_at"]
                or manifest.get("cross_notice_available_at") != case["cross_notice_available_at"]
                or manifest.get("original_sha256") != case["files"]["original.pdf"]["sha256"]
                or manifest.get("cross_notice_sha256") != case["files"]["cross-notice.pdf"]["sha256"]):
            raise ValueError("H1_REGISTRATION_MANIFEST_MISMATCH")
        parsed = replay_halfyear_shares(root=evidence_dir, symbol=symbol,
            issuer_name=case["issuer_name"], report_year=case["report_year"],
            expected_original_sha256=case["files"]["original.pdf"]["sha256"],
            as_of=as_of)
        if parsed["report_period_end"] != case["report_period_end"]:
            raise ValueError("H1_REGISTRATION_PERIOD_MISMATCH")
        if registry.read_bytes() != raw or any(
                _digest(evidence_dir / name) != record["sha256"]
                for name, record in case["files"].items()):
            raise ValueError("H1_REGISTERED_SOURCE_CHANGED_DURING_READ")
        h1.update(status="VERIFIED", report_period_end=parsed["report_period_end"],
                  ordinary_shares=parsed["ordinary_shares"],
                  shares_before=parsed["shares_before"], cancelled_shares=parsed["cancelled_shares"],
                  source=parsed, registry_sha256=hashlib.sha256(raw).hexdigest())
    except (ValueError, OSError, TypeError, KeyError, IndexError) as error:
        h1.update(status="UNASSESSABLE", error_code=str(error), ordinary_shares=None)
    return result

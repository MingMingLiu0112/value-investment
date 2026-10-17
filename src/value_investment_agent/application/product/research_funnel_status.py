"""Read and project the hash-pinned W6 research-funnel audit.

The audit is engineering evidence, not an investment decision.  The loader
re-verifies the pointer, manifest, result, human-review packet and report
before exposing a compact read model to the product surface.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping


POINTER_PATH = Path("config/current-research-funnel-audit.json")
POINTER_SCHEMA = "current-research-funnel-audit-v1"
PUBLIC_SCHEMA = "public-research-funnel-status-v1"
MANIFEST_SCHEMA = "research-funnel-audit-manifest-v1"
RESULT_SCHEMA = "research-funnel-audit-v1"
ACTION = "no_order"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_OUTPUTS = ("result.json", "report.md", "human-review-packet.json")
_CHANNEL_ORDER = ("quality", "value", "dividend_cash_return", "cyclical")


class _InvalidAudit(ValueError):
    """A fail-closed audit loading error with a stable public reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _hash_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _hash_bytes(encoded)


def _read_object(path: Path, reason: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _InvalidAudit(reason) from error
    if not isinstance(value, dict):
        raise _InvalidAudit(reason)
    return value


def _artifact_path(root: Path, value: object, reason: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise _InvalidAudit(reason)
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise _InvalidAudit(reason)
    approved = (root / "artifacts" / "current").resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(approved):
        raise _InvalidAudit(reason)
    return target


def _verified_file(path: Path, expected: object, reason: str) -> dict[str, Any]:
    if not isinstance(expected, str) or not _HASH.fullmatch(expected.lower()):
        raise _InvalidAudit(reason)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise _InvalidAudit(reason) from error
    if _hash_bytes(raw) != expected.lower():
        raise _InvalidAudit(reason)
    return _read_object(path, reason)


def _require_digest(value: object, reason: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise _InvalidAudit(reason)
    return value


def _load_verified(root: Path) -> dict[str, Any]:
    pointer = _read_object(root / POINTER_PATH, "FUNNEL_POINTER_UNREADABLE")
    if (
        pointer.get("schema_version") != POINTER_SCHEMA
        or pointer.get("action") != ACTION
        or pointer.get("status") != "VERIFIED"
    ):
        raise _InvalidAudit("FUNNEL_POINTER_INVALID")
    manifest_path = _artifact_path(
        root, pointer.get("manifest_path"), "FUNNEL_MANIFEST_PATH_INVALID"
    )
    manifest = _verified_file(
        manifest_path,
        pointer.get("manifest_sha256"),
        "FUNNEL_MANIFEST_HASH_MISMATCH",
    )
    if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("action") != ACTION:
        raise _InvalidAudit("FUNNEL_MANIFEST_INVALID")
    if manifest.get("trade_intent") != "NO_TRADE":
        raise _InvalidAudit("FUNNEL_MANIFEST_TRADE_INTENT_INVALID")

    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or not set(_OUTPUTS) <= set(outputs):
        raise _InvalidAudit("FUNNEL_OUTPUTS_MISSING")
    loaded: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    for name in _OUTPUTS:
        entry = outputs.get(name)
        if not isinstance(entry, dict):
            raise _InvalidAudit("FUNNEL_OUTPUT_BINDING_INVALID")
        path = _artifact_path(root, entry.get("path"), "FUNNEL_OUTPUT_PATH_INVALID")
        if path.parent != manifest_path.parent or path.name != name:
            raise _InvalidAudit("FUNNEL_OUTPUT_PATH_INVALID")
        if name.endswith(".json"):
            loaded[name] = _verified_file(
                path, entry.get("sha256"), "FUNNEL_OUTPUT_HASH_MISMATCH"
            )
        else:
            expected = _require_digest(
                entry.get("sha256"), "FUNNEL_OUTPUT_HASH_INVALID"
            )
            try:
                actual = _hash_bytes(path.read_bytes())
            except OSError as error:
                raise _InvalidAudit("FUNNEL_OUTPUT_MISSING") from error
            if actual != expected:
                raise _InvalidAudit("FUNNEL_OUTPUT_HASH_MISMATCH")
        digests[name] = str(entry["sha256"]).lower()

    result = loaded["result.json"]
    packet = loaded["human-review-packet.json"]
    if result.get("schema_version") != RESULT_SCHEMA or result.get("action") != ACTION:
        raise _InvalidAudit("FUNNEL_RESULT_INVALID")
    if result.get("trade_intent") != "NO_TRADE" or result.get("admission") != "READ_ONLY_AUDIT":
        raise _InvalidAudit("FUNNEL_RESULT_BOUNDARY_INVALID")
    audit_digest = _require_digest(result.get("audit_sha256"), "FUNNEL_AUDIT_HASH_INVALID")
    without_audit_digest = dict(result)
    without_audit_digest.pop("audit_sha256", None)
    if _canonical_hash(without_audit_digest) != audit_digest:
        raise _InvalidAudit("FUNNEL_RESULT_TAMPERED")
    if manifest.get("audit_sha256") != audit_digest:
        raise _InvalidAudit("FUNNEL_MANIFEST_AUDIT_MISMATCH")

    if packet.get("action") != ACTION or packet.get("source_audit_sha256") != audit_digest:
        raise _InvalidAudit("FUNNEL_REVIEW_PACKET_INVALID")
    packet_digest = _require_digest(
        packet.get("packet_sha256"), "FUNNEL_REVIEW_PACKET_HASH_INVALID"
    )
    without_packet_digest = dict(packet)
    without_packet_digest.pop("packet_sha256", None)
    if _canonical_hash(without_packet_digest) != packet_digest:
        raise _InvalidAudit("FUNNEL_REVIEW_PACKET_TAMPERED")
    if manifest.get("packet_sha256") != packet_digest:
        raise _InvalidAudit("FUNNEL_MANIFEST_PACKET_MISMATCH")
    manifest_sources = manifest.get("source_hashes")
    result_sources = result.get("source_files")
    if not isinstance(manifest_sources, dict) or not isinstance(result_sources, dict):
        raise _InvalidAudit("FUNNEL_SOURCE_BINDING_INVALID")
    if set(manifest_sources) != set(result_sources):
        raise _InvalidAudit("FUNNEL_SOURCE_BINDING_MISMATCH")
    for role, binding in result_sources.items():
        if not isinstance(binding, Mapping):
            raise _InvalidAudit("FUNNEL_SOURCE_BINDING_INVALID")
        if manifest_sources.get(role) != binding.get("sha256"):
            raise _InvalidAudit("FUNNEL_SOURCE_BINDING_MISMATCH")

    return {
        "manifest": manifest,
        "result": result,
        "packet": packet,
        "manifest_path": manifest_path,
        "manifest_relative": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": pointer["manifest_sha256"].lower(),
        "output_digests": digests,
    }


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _channel_rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    channels = _mapping(result.get("channels"))
    rows: list[dict[str, Any]] = []
    for key in _CHANNEL_ORDER:
        channel = _mapping(channels.get(key))
        counts = _mapping(channel.get("effective_status_counts"))
        reasons = channel.get("top_reasons")
        first_reason = reasons[0] if isinstance(reasons, list) and reasons else {}
        rows.append(
            {
                "key": key,
                "pass_count": _integer(counts.get("PASS")),
                "data_gap_count": _integer(counts.get("DATA_GAP")),
                "insufficient_evidence_count": _integer(
                    counts.get("INSUFFICIENT_EVIDENCE")
                ),
                "rejected_count": _integer(counts.get("REJECTED")),
                "not_evaluated_count": _integer(counts.get("NOT_EVALUATED")),
                "budget_excluded_count": _integer(counts.get("BUDGET_EXCLUDED")),
                "unsupported_count": _integer(counts.get("UNSUPPORTED")),
                "top_reason": (
                    str(first_reason.get("reason"))
                    if isinstance(first_reason, Mapping)
                    and isinstance(first_reason.get("reason"), str)
                    else None
                ),
            }
        )
    return rows


def _review_sample(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sample = packet.get("sample")
    if not isinstance(sample, list):
        return rows
    for item in sample[:10]:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "symbol": str(item.get("symbol") or ""),
                "name": str(item.get("company_name") or item.get("symbol") or ""),
                "industry": str(item.get("industry") or ""),
                "channels": [
                    str(part)
                    for part in item.get("channels", [])
                    if isinstance(part, str)
                ],
                "research_state": str(item.get("research_state") or "UNKNOWN"),
                "gaps": [str(part) for part in item.get("gaps", []) if isinstance(part, str)],
            }
        )
    return rows


def _blockers(result: Mapping[str, Any]) -> list[str]:
    codes: list[str] = []
    quote = _mapping(result.get("quote"))
    if quote.get("trade_date_verified") is not True:
        codes.append("QUOTE_DATE_UNVERIFIED")
    quality = _mapping(result.get("quality_effective_status_counts"))
    if _integer(quality.get("PASS")) == 0:
        codes.append("QUALITY_ZERO_PASS")
    if _mapping(result.get("capital_return_roic")).get("available") is not True:
        codes.append("CAPITAL_RETURN_UNAVAILABLE")
    if _mapping(result.get("human_review")).get("status") == "HUMAN_REVIEW_PENDING":
        codes.append("HUMAN_REVIEW_PENDING")
    if _integer(_mapping(result.get("queue")).get("selected_count")) > 0:
        codes.append("QUEUE_IS_DATA_CHECK_ONLY")
    return codes


def _project(loaded: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(loaded["result"])
    packet = _mapping(loaded["packet"])
    queue = _mapping(result.get("queue"))
    financial = _mapping(result.get("financial"))
    quality = _mapping(result.get("quality_effective_status_counts"))
    capital_return = _mapping(result.get("capital_return_roic"))
    quote = _mapping(result.get("quote"))
    human_review = _mapping(result.get("human_review"))
    source_files = _mapping(result.get("source_files"))

    return {
        "schema_version": PUBLIC_SCHEMA,
        "action": ACTION,
        "status": "VERIFIED",
        "reason": None,
        "task_id": str(result.get("task_id") or "UNKNOWN"),
        "as_of": result.get("as_of"),
        "audit_sha256": result.get("audit_sha256"),
        "review": {
            "status": human_review.get("status") or packet.get("review_status"),
            "approved": packet.get("approved") is True,
        },
        "universe": {
            "securities": _integer(result.get("universe_count")),
            "industries_mapped": _integer(result.get("industry_count")),
            "market_snapshots": _integer(result.get("market_snapshot_count")),
            "leads": _integer(result.get("lead_count")),
        },
        "evidence": {
            "financial_symbols": _integer(financial.get("symbol_count")),
            "financial_points": _integer(financial.get("point_count")),
            "dividend_evidence_count": _integer(
                result.get("dividend_evidence_count")
            ),
            "same_period_complete_symbols": _integer(
                result.get("same_period_complete_symbol_count")
            ),
            "quality_pass": _integer(quality.get("PASS")),
            "quality_data_gap": _integer(quality.get("DATA_GAP")),
            "quality_insufficient_evidence": _integer(
                quality.get("INSUFFICIENT_EVIDENCE")
            ),
            "capital_return_status": capital_return.get("status"),
            "capital_return_reason": capital_return.get("reason"),
        },
        "quote": {
            "date": quote.get("quote_date"),
            "trade_date_verified": quote.get("trade_date_verified") is True,
            "verified_count": _integer(quote.get("verified_quote_count")),
            "unverified_count": _integer(quote.get("unverified_quote_count")),
        },
        "queue": {
            "entry_count": _integer(queue.get("entry_count")),
            "selected_count": _integer(queue.get("selected_count")),
            "deferred_count": _integer(queue.get("deferred_count")),
            "selected_symbols": [
                str(symbol)
                for symbol in queue.get("selected_symbols", [])
                if isinstance(symbol, str)
            ],
        },
        "channels": _channel_rows(result),
        "sample": _review_sample(packet),
        "blockers": _blockers(result),
        "source_files": {
            str(role): {
                "path": str(binding.get("path") or ""),
                "sha256": str(binding.get("sha256") or ""),
            }
            for role, binding in source_files.items()
            if isinstance(binding, Mapping)
        },
        "artifacts": {
            "manifest": {
                "path": loaded["manifest_relative"],
                "sha256": loaded["manifest_sha256"],
            },
            "result_sha256": loaded["output_digests"]["result.json"],
            "report_sha256": loaded["output_digests"]["report.md"],
            "review_packet_sha256": loaded["output_digests"]["human-review-packet.json"],
        },
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "schema_version": PUBLIC_SCHEMA,
        "action": ACTION,
        "status": "UNAVAILABLE" if reason.endswith("MISSING") else "INVALID",
        "reason": reason,
        "task_id": None,
        "as_of": None,
        "audit_sha256": None,
        "review": None,
        "universe": None,
        "evidence": None,
        "quote": None,
        "queue": None,
        "channels": [],
        "sample": [],
        "blockers": [],
        "source_files": {},
        "artifacts": None,
    }


def research_funnel_status(root: Path) -> dict[str, Any]:
    """Return a verified public projection or a named fail-closed state."""
    root = Path(root).resolve()
    if not (root / POINTER_PATH).is_file():
        return _unavailable("FUNNEL_POINTER_MISSING")
    try:
        return _project(_load_verified(root))
    except _InvalidAudit as error:
        return _unavailable(error.reason)
    except (OSError, TypeError, KeyError, ValueError):
        return _unavailable("FUNNEL_AUDIT_INVALID")


load_research_funnel_status = research_funnel_status

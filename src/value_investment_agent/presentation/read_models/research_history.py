"""Version-bound research history projected from real, hash-verifiable artifacts.

WEB-D2 P2, extended by WEB-D3 P5. The admitted sources are artifacts that exist
on disk and whose SHA-256 is recomputed on read: the finite-earnings-path
proposals under `config/research-proposals/`, the m1 valuation package a
proposal declares, its declared rationale files and, when the current
publication binds one, the published `research_version` string.

Three kinds of history stay separate: a research proposal is what the research
process registered, a published decision is what the publication chain really
bound, and a historical reconstruction is only shown when a replayable artifact
exists. A recomputed file digest proves the file did not change; it is not
evidence admission, it never upgrades any admission level, and it never turns a
research observation into an order.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from ...application.product.daily_public_packet import packet_content_sha256
from ...application.product.public_snapshot import _resolve_runtime

ACTION = "no_order"
PROPOSAL_SCHEMA = "finite-earnings-path-proposal-v1"
PROPOSAL_DIRECTORY = "config/research-proposals"
PACKAGE_DIRECTORIES = ("config/m1-valuation-packages-v1",)
PROPOSAL_PATTERN = re.compile(r"^(?P<symbol>\d{6})-(?P<date>\d{8})(?:-(?P<label>v\d+))?$")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_BOUND_DIGEST = re.compile(r"-([0-9a-f]{12})\Z")
_COMPARE_FIELDS = (
    "profit_anchor_field",
    "profit_basis",
    "income_growth",
    "rationale_bindings",
    "choices",
    "economic_review_items",
    "human_review_groups",
    "assurance_limits",
    "research_preference",
    "source_package_sha256",
)
_NOTE = ("只展示真实存在、可按 SHA-256 复算的研究版本；比较是逐字段机械对比，"
         "不会把研究观察升级为任何买卖准入。")
_VERIFICATION_NOTE = ("版本文件与声明来源的 SHA-256 均在读取时复算；这只能证明文件未被改动，"
                      "既不等于来源证据已获人工复核，也不构成任何投资准入。")
_HISTORY_NOTE = ("发布历史只来自可按 SHA-256 复核的每日公开数据包回执；"
                 "它记录发布版本，不生成历史买入/卖出/减仓记录。")
_RECONSTRUCTION_NOTE = ("历史重建只在存在可复算的历史决策产物时展示；"
                        "本轮没有绑定该类产物。")


def _summary(value: Any) -> Any:
    if isinstance(value, list):
        return {"items": len(value)}
    if isinstance(value, dict):
        return {"keys": sorted(str(key) for key in value)}
    return value


def _review_groups(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    rows = payload.get("human_review_groups")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                groups[row["id"]] = row
    return groups


def compare_versions(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    changed: list[str] = []
    details: dict[str, Any] = {}
    for field in _COMPARE_FIELDS:
        before, after = previous.get(field), current.get(field)
        if before != after:
            changed.append(field)
            details[field] = {"before": _summary(before), "after": _summary(after)}
    before_groups = _review_groups(previous)
    after_groups = _review_groups(current)
    group_changes = {
        "added": sorted(set(after_groups) - set(before_groups)),
        "removed": sorted(set(before_groups) - set(after_groups)),
        "changed": sorted(key for key in set(before_groups) & set(after_groups)
                          if before_groups[key] != after_groups[key]),
    }
    return {
        "status": "COMPARED",
        "observation": "UNCHANGED" if not changed else "EVIDENCE_UPDATED",
        "changed_fields": changed,
        "field_changes": details,
        "review_group_changes": group_changes,
        "admission_effect": "NONE",
    }


def _verify_binding(root: Path, row: Any) -> dict[str, Any]:
    """Recompute one declared source digest; a declared name is not evidence."""
    if not isinstance(row, dict):
        return {"path": None, "sha256": None, "status": "INVALID_ENTRY"}
    name, declared = row.get("path"), row.get("sha256")
    result: dict[str, Any] = {"path": name if isinstance(name, str) else None,
                              "sha256": declared if isinstance(declared, str) else None}
    if not isinstance(name, str) or not name:
        result["status"] = "PATH_MISSING"
        return result
    base = Path(root).resolve()
    target = (base / name).resolve()
    if Path(name).is_absolute() or not target.is_relative_to(base):
        result["status"] = "OUTSIDE_ROOT"
        return result
    if not target.is_file():
        result["status"] = "MISSING"
        return result
    if not isinstance(declared, str) or not _HASH.fullmatch(declared):
        result["status"] = "DECLARED_HASH_INVALID"
        return result
    try:
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:
        result["status"] = "UNREADABLE"
        return result
    result["actual_sha256"] = actual
    result["status"] = "VERIFIED" if actual == declared else "HASH_MISMATCH"
    return result


def _source_package(root: Path, symbol: str, declared: Any) -> dict[str, Any]:
    """Bind the declared package digest to a real package file, not to a string."""
    if not isinstance(declared, str) or not _HASH.fullmatch(declared):
        return {"status": "DECLARED_HASH_INVALID",
                "declared_sha256": declared if isinstance(declared, str) else None}
    for directory in PACKAGE_DIRECTORIES:
        base = Path(root) / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob(f"{symbol}-*.json")):
            try:
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            if actual == declared:
                return {"status": "VERIFIED", "declared_sha256": declared,
                        "artifact": path.relative_to(Path(root)).as_posix(),
                        "sha256": actual}
    return {"status": "NOT_FOUND", "declared_sha256": declared}


def scan_proposal_versions(root: Path) -> dict[str, Any]:
    """Every candidate proposal file with its recomputed digest, oldest first."""
    directory = Path(root) / PROPOSAL_DIRECTORY
    versions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    if not directory.is_dir():
        return {"versions": versions, "skipped": skipped}
    for path in sorted(directory.glob("*.json")):
        match = PROPOSAL_PATTERN.match(path.stem)
        if match is None:
            continue
        artifact = f"{PROPOSAL_DIRECTORY}/{path.name}"
        try:
            raw = path.read_bytes()
        except OSError:
            skipped.append({"artifact": artifact, "reason": "UNREADABLE_FILE"})
            continue
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            skipped.append({"artifact": artifact, "reason": "UNREADABLE_JSON"})
            continue
        if not isinstance(payload, dict):
            skipped.append({"artifact": artifact, "reason": "NOT_AN_OBJECT"})
            continue
        for reason, ok in (("UNKNOWN_SCHEMA", payload.get("schema_version") == PROPOSAL_SCHEMA),
                           ("ACTION_NOT_NO_ORDER", payload.get("action") == ACTION),
                           ("SYMBOL_MISMATCH", payload.get("symbol") == match["symbol"])):
            if not ok:
                skipped.append({"artifact": artifact, "reason": reason})
                break
        else:
            versions.append({
                "symbol": match["symbol"],
                "version_label": path.stem,
                "research_date": match["date"],
                "artifact": artifact,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "payload": payload,
            })
    versions.sort(key=lambda item: (item["research_date"], item["version_label"]))
    return {"versions": versions, "skipped": skipped}


def load_proposal_versions(root: Path) -> list[dict[str, Any]]:
    """Backwards-compatible view of `scan_proposal_versions`."""
    return scan_proposal_versions(root)["versions"]


def _scan_published_packets(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read-only timeline of published packets whose receipt and bytes agree."""
    directory = Path(root) / "runtime/daily-public-packet/receipts"
    history: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    if not directory.is_dir():
        return history, skipped
    for receipt_path in sorted(directory.glob("*.receipt.json")):
        label = receipt_path.relative_to(Path(root)).as_posix()
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            skipped.append({"artifact": label, "reason": "UNREADABLE_RECEIPT"})
            continue
        if not isinstance(receipt, dict) or receipt.get("schema_version") != "daily-public-packet-receipt-v1":
            skipped.append({"artifact": label, "reason": "INVALID_RECEIPT"})
            continue
        if receipt.get("action") != ACTION or not isinstance(receipt.get("publication_id"), str):
            skipped.append({"artifact": label, "reason": "RECEIPT_SCOPE_INVALID"})
            continue
        target = _resolve_runtime(root, receipt.get("packet_path"))
        if target is None or not target.is_file():
            skipped.append({"artifact": label, "reason": "PACKET_MISSING"})
            continue
        try:
            raw = target.read_bytes()
            packet = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            skipped.append({"artifact": label, "reason": "PACKET_UNREADABLE"})
            continue
        if (not isinstance(packet, dict) or packet.get("action") != ACTION
                or packet.get("publication_id") != receipt.get("publication_id")
                or hashlib.sha256(raw).hexdigest() != receipt.get("packet_sha256")
                or packet.get("content_sha256") != receipt.get("content_sha256")
                or packet_content_sha256(packet) != receipt.get("content_sha256")):
            skipped.append({"artifact": label, "reason": "PACKET_BINDING_INVALID"})
            continue
        history.append({
            "publication_id": receipt["publication_id"],
            "research_version": receipt.get("research_version"),
            "decision_cutoff": (packet.get("dates") or {}).get("decision_cutoff"),
            "generated_at": receipt.get("generated_at"),
            "published_at": receipt.get("published_at"),
            "packet_path": receipt.get("packet_path"),
            "packet_sha256": receipt.get("packet_sha256"),
            "content_sha256": receipt.get("content_sha256"),
            "receipt_path": label,
            "action": ACTION,
        })
    history.sort(key=lambda row: (row.get("published_at") or "", row["publication_id"]))
    return history, skipped


def _bound_to_publication(symbol: str, digest: str, published: str | None) -> bool:
    """The publication embeds the proposal digest; compare it exactly, not loosely."""
    if not isinstance(published, str) or symbol not in published:
        return False
    match = _BOUND_DIGEST.search(published)
    return match is not None and digest[:12] == match.group(1)


def _item(root: Path, symbol: str, versions: list[dict[str, Any]], published: str | None,
          published_decision: Mapping[str, Any] | None) -> dict[str, Any]:
    latest = versions[-1]
    payload = latest["payload"]
    preference = payload.get("research_preference")
    preference = preference if isinstance(preference, dict) else {}
    rows = []
    for version in reversed(versions):
        rows.append({
            "version_label": version["version_label"],
            "research_date": version["research_date"],
            "artifact": version["artifact"],
            "sha256": version["sha256"],
            "bound_to_current_publication": _bound_to_publication(
                symbol, version["sha256"], published),
        })
    if len(versions) >= 2:
        comparison = compare_versions(versions[-2]["payload"], payload)
        comparison["from_version"] = versions[-2]["version_label"]
        comparison["to_version"] = latest["version_label"]
    else:
        comparison = {
            "status": "PREVIOUS_UNAVAILABLE",
            "observation": "UNKNOWN",
            "changed_fields": [],
            "field_changes": {},
            "review_group_changes": {"added": [], "removed": [], "changed": []},
            "admission_effect": "NONE",
            "reason": "该证券目前只有一个可复算的研究版本，无法比较",
        }
    bindings = payload.get("rationale_bindings")
    evidence = [_verify_binding(root, row) for row in bindings] if isinstance(bindings, list) else []
    verified = sum(1 for row in evidence if row["status"] == "VERIFIED")
    review_items = []
    for group in _review_groups(payload).values():
        review_items.append({key: group.get(key) for key in
                             ("id", "question", "support", "countercase", "impact", "field_paths")})
    if published_decision and published:
        decision = {
            "status": "CURRENT_PUBLICATION_ONLY",
            "research_version": published,
            "candidate_action": published_decision.get("candidate_action"),
            "decision_cutoff": published_decision.get("decision_cutoff"),
            "artifact": published_decision.get("artifact"),
            "sha256": published_decision.get("sha256"),
            "note": "这是当前发布物绑定的决策，不是历史决策记录。",
        }
    else:
        decision = {"status": "NOT_BOUND",
                    "note": "当前发布物没有绑定该证券的决策解释。"}
    return {
        "id": symbol,
        "symbol": symbol,
        "strategy": "value",
        "status": "RESEARCH_ONLY",
        "action": ACTION,
        "candidate_action": ACTION,
        "published_research_version": published,
        "latest_version_label": latest["version_label"],
        "attention": {
            "choice_id": preference.get("choice_id"),
            "scope": preference.get("scope"),
            "confidence": preference.get("confidence"),
            "reason": preference.get("reason"),
            "countercase": preference.get("countercase"),
            "reopen_triggers": list(preference.get("reopen_triggers") or []),
        },
        "assumptions": payload.get("income_growth"),
        "assurance_limits": list(payload.get("assurance_limits") or []),
        "review_items": review_items,
        "evidence": evidence,
        "versions": rows,
        "comparison": comparison,
        "verification": {
            "proposal_file": {"artifact": latest["artifact"], "sha256": latest["sha256"],
                              "status": "SHA256_RECOMPUTED_FROM_DISK"},
            "rationale_bindings": {
                "status": ("VERIFIED" if evidence and verified == len(evidence)
                           else "NO_BINDINGS" if not evidence else "INCOMPLETE"),
                "verified_count": verified, "total": len(evidence)},
            "source_package": _source_package(root, symbol, payload.get("source_package_sha256")),
            "note": _VERIFICATION_NOTE,
        },
        "timeline": {
            "proposal_research_date": latest["research_date"],
            "proposal_available_at": None,
            "proposal_available_at_status": "NOT_RECORDED_IN_PROPOSAL",
            "published_decision_cutoff": (published_decision or {}).get("decision_cutoff"),
            "note": "提案登记日期来自文件名；提案未记录可获取时间，二者不能互相替代。",
        },
        "published_decision": decision,
        "admission_effect": "NONE",
    }


def build_research_history(root: Path, *, published_versions: Mapping[str, str] | None = None,
                           published_decisions: Mapping[str, Mapping[str, Any]] | None = None,
                           ) -> dict[str, Any]:
    """Read every real research version; never synthesise one."""
    scan = scan_proposal_versions(root)
    admitted = scan["versions"]
    published = dict(published_versions or {})
    decisions = dict(published_decisions or {})
    grouped: dict[str, list[dict[str, Any]]] = {}
    for version in admitted:
        grouped.setdefault(version["symbol"], []).append(version)
    items = [_item(root, symbol, grouped[symbol], published.get(symbol), decisions.get(symbol))
             for symbol in sorted(grouped)]
    status = "CONNECTED" if admitted else "NOT_CONNECTED"
    counts = {"symbols": len(items), "versions": len(admitted)}
    current = [{"symbol": symbol,
                "research_version": row.get("research_version"),
                "candidate_action": row.get("candidate_action"),
                "decision_cutoff": row.get("decision_cutoff"),
                "artifact": row.get("artifact"), "sha256": row.get("sha256")}
               for symbol, row in sorted(decisions.items())]
    published_history, skipped_publications = _scan_published_packets(root)
    return {
        "action": ACTION,
        "status": status,
        "as_of": None,
        "counts": counts,
        "items": items,
        "note": _NOTE,
        "research_proposal_history": {"status": status, "counts": counts, "items": items,
                                      "note": _NOTE},
        "published_decision_history": {
            "status": ("HISTORY_AVAILABLE" if published_history else
                       "CURRENT_ONLY" if current else "NOT_AVAILABLE"),
            "history": published_history, "current_published_decisions": current,
            "skipped_publications": skipped_publications, "note": _HISTORY_NOTE},
        "historical_reconstruction": {"status": "NOT_AVAILABLE", "items": [],
                                      "note": _RECONSTRUCTION_NOTE},
        "skipped_proposals": scan["skipped"],
    }

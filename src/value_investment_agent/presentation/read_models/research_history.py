"""Version-bound research history projected from real, hash-verifiable artifacts.

WEB-D2 P2. The only admitted sources are artifacts that exist on disk and whose
SHA-256 can be recomputed: the finite-earnings-path research proposals under
`config/research-proposals/` and, when the current publication binds one of
them, the published `research_version` string. Nothing is inferred: a symbol
with a single version honestly reports `PREVIOUS_UNAVAILABLE`, and the
comparison is a mechanical field diff that never upgrades any admission level.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

ACTION = "no_order"
PROPOSAL_SCHEMA = "finite-earnings-path-proposal-v1"
PROPOSAL_DIRECTORY = "config/research-proposals"
PROPOSAL_PATTERN = re.compile(r"^(?P<symbol>\d{6})-(?P<date>\d{8})(?:-(?P<label>v\d+))?$")
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


def load_proposal_versions(root: Path) -> list[dict[str, Any]]:
    """Every admitted proposal file with its recomputed digest, oldest first."""
    directory = Path(root) / PROPOSAL_DIRECTORY
    if not directory.is_dir():
        return []
    versions: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        match = PROPOSAL_PATTERN.match(path.stem)
        if match is None:
            continue
        raw = path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("schema_version") != PROPOSAL_SCHEMA:
            continue
        if payload.get("action") != ACTION or payload.get("symbol") != match["symbol"]:
            continue
        versions.append({
            "symbol": match["symbol"],
            "version_label": path.stem,
            "research_date": match["date"],
            "artifact": f"{PROPOSAL_DIRECTORY}/{path.name}",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "payload": payload,
        })
    versions.sort(key=lambda item: (item["research_date"], item["version_label"]))
    return versions


def _item(symbol: str, versions: list[dict[str, Any]], published: str | None) -> dict[str, Any]:
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
            "bound_to_current_publication": bool(
                published and version["sha256"][:12] in published),
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
    evidence = []
    if isinstance(bindings, list):
        for row in bindings:
            if isinstance(row, dict) and isinstance(row.get("path"), str):
                evidence.append({"path": row["path"], "sha256": row.get("sha256")})
    review_items = []
    for group in _review_groups(payload).values():
        review_items.append({key: group.get(key) for key in
                             ("id", "question", "support", "countercase", "impact", "field_paths")})
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
    }


def build_research_history(root: Path, *, published_versions: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Read every real research version; never synthesise one."""
    admitted = load_proposal_versions(root)
    if not admitted:
        return {"action": ACTION, "status": "NOT_CONNECTED", "as_of": None,
                "counts": {"symbols": 0, "versions": 0}, "items": [], "note": _NOTE}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for version in admitted:
        grouped.setdefault(version["symbol"], []).append(version)
    published = dict(published_versions or {})
    items = [_item(symbol, grouped[symbol], published.get(symbol)) for symbol in sorted(grouped)]
    return {
        "action": ACTION,
        "status": "CONNECTED",
        "as_of": None,
        "counts": {"symbols": len(items), "versions": len(admitted)},
        "items": items,
        "note": _NOTE,
    }

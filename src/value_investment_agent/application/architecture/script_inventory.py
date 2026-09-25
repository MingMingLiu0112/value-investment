"""Deterministic inventory for the repository's script and tooling surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Iterable, Mapping


SCRIPT_INVENTORY_SCHEMA = "repository-script-inventory-v1"
SCRIPT_EXTENSIONS = frozenset({".py", ".ps1", ".mjs", ".sql"})
CATEGORIES = (
    "CURRENT_OPERATIONAL_CLI",
    "CURRENT_PRODUCT_CLI",
    "CURRENT_RESEARCH_CLI",
    "HISTORICAL_VALIDATION_TOOL",
    "COMPANY_RESEARCH_CASE_TOOL",
    "MIGRATION_TOOL",
    "DIAGNOSTIC_TOOL",
    "SUPERSEDED",
    "DELETE_CANDIDATE",
)

_COMPANY_TOKENS = (
    "moutai",
    "midea",
    "shenhua",
    "gree",
    "yili",
    "huayu",
    "haier",
    "wuliangye",
    "yankuang",
)
_HISTORICAL_TOKENS = ("historical", "replay", "backtest", "pit_conformance")
_MIGRATION_TOKENS = (
    "migrate",
    "migration",
    "backfill",
    "install_",
    "retire_",
    "candidate_migration",
)
_DIAGNOSTIC_PREFIXES = (
    "audit_",
    "check_",
    "inspect_",
    "diagnose_",
    "verify_",
    "validate_",
    "preview_",
    "compare_",
    "probe_",
    "triage_",
    "reconcile_",
)


@dataclass(frozen=True)
class ScriptInventoryEntry:
    path: str
    category: str
    current_consumers: tuple[str, ...]
    imports_business_logic: bool
    replacement: str | None
    recommended_action: str
    risk: str
    line_count: int
    sha256: str


@dataclass(frozen=True)
class ScriptInventory:
    schema_version: str
    action: str
    scripts_root: str
    current_entrypoint_count: int
    counts: dict[str, int]
    entries: tuple[ScriptInventoryEntry, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "scripts_root": self.scripts_root,
            "current_entrypoint_count": self.current_entrypoint_count,
            "counts": self.counts,
            "entries": [asdict(entry) for entry in self.entries],
        }


def _category_for(path: str, current_category: str | None) -> str:
    if current_category:
        return current_category
    name = Path(path).name.lower()
    if any(token in name for token in _HISTORICAL_TOKENS):
        return "HISTORICAL_VALIDATION_TOOL"
    if any(token in name for token in _COMPANY_TOKENS):
        return "COMPANY_RESEARCH_CASE_TOOL"
    if any(token in name for token in _MIGRATION_TOKENS):
        return "MIGRATION_TOOL"
    if name.startswith(_DIAGNOSTIC_PREFIXES):
        return "DIAGNOSTIC_TOOL"
    return "CURRENT_RESEARCH_CLI"


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _business_logic_risk(path: Path, category: str, lines: int) -> bool:
    if lines >= 300:
        return True
    text = path.read_text(encoding="utf-8", errors="replace")
    business_markers = (
        "investment_decision",
        "portfolio_contracts",
        "valuation_result",
        "position_guidance",
        "event_materiality",
        "pit_conformance",
    )
    return category.startswith("CURRENT_") and any(
        marker in text for marker in business_markers
    )


def build_script_inventory(
    root: Path,
    *,
    current_entrypoints: Mapping[str, Mapping[str, object]],
) -> ScriptInventory:
    """Build a complete, stable inventory without interpreting business results."""
    scripts_root = root / "scripts"
    entries: list[ScriptInventoryEntry] = []
    for path in sorted(scripts_root.rglob("*")):
        if not path.is_file() or path.suffix not in SCRIPT_EXTENSIONS:
            continue
        if "__pycache__" in path.parts or "node_modules" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        registry_entry = current_entrypoints.get(relative)
        current_category = (
            str(registry_entry["category"]) if registry_entry else None
        )
        category = _category_for(relative, current_category)
        lines = _line_count(path)
        is_current = registry_entry is not None
        frozen = bool(registry_entry and registry_entry.get("status") == "FROZEN_INPUT")
        consumers = (str(registry_entry["status"]),) if registry_entry else ()
        action = "KEEP_FROZEN" if frozen else "KEEP_CURRENT" if is_current else "KEEP_CLASSIFIED"
        risk = "HIGH" if frozen or (is_current and lines >= 300) else "MEDIUM" if is_current else "LOW"
        entries.append(
            ScriptInventoryEntry(
                path=relative,
                category=category,
                current_consumers=consumers,
                imports_business_logic=_business_logic_risk(path, category, lines),
                replacement=None,
                recommended_action=action,
                risk=risk,
                line_count=lines,
                sha256=_sha256(path),
            )
        )
    counts = {category: 0 for category in CATEGORIES}
    for entry in entries:
        counts[entry.category] += 1
    return ScriptInventory(
        schema_version=SCRIPT_INVENTORY_SCHEMA,
        action="no_order",
        scripts_root="scripts",
        current_entrypoint_count=len(current_entrypoints),
        counts=counts,
        entries=tuple(entries),
    )

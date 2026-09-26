#!/usr/bin/env python3
"""Publish the M7 product surface into the one configured canonical workbook.

This deliberately never creates a second user-facing workbook.  It copies the
configured workbook to a staging file beside it, proves retained sheets did not
change at cell level, then atomically replaces the original.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from posixpath import dirname, join, normpath
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from scripts.current.daily_quote_binding import load_daily_quote_binding  # noqa: E402
from scripts.current.daily_product_packet import build_daily_product_packet  # noqa: E402
from value_investment_agent.application.product.product_workbench_candidate import (  # noqa: E402
    build_product_workbench_candidate_payload,
)
from value_investment_agent.presentation.excel.product_workbench import (  # noqa: E402
    WORKBOOK_SHEETS,
    apply_product_workbench_to_existing_workbook,
)
from value_investment_agent.presentation.read_models.product_workbench import (  # noqa: E402
    product_workbench_from_payload,
)


CANONICAL_NAME = "A股价值投资_Agent前端智能跟踪模板.xlsx"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _workbook_path() -> Path:
    value = os.environ.get("WORKBOOK_PATH")
    env_file = ROOT / ".env"
    if not value and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("WORKBOOK_PATH"):
                value = line.split("=", 1)[1].strip()
                break
    if not value:
        raise ValueError("CANONICAL_WORKBOOK_NOT_RESOLVED")
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".xlsx" or path.name != CANONICAL_NAME:
        raise ValueError("CANONICAL_WORKBOOK_NOT_RESOLVED")
    if (path.parent / f"~${path.name}").exists():
        raise RuntimeError("CANONICAL_PUBLICATION_BLOCKED_BY_OPEN_WORKBOOK")
    return path


def _cell_fingerprint(sheet: Any) -> dict[str, Any]:
    cells = []
    formulas = hyperlinks = 0
    # ``iter_rows`` materializes every coordinate within WPS's styled range.
    # The internal cell map contains only real cells, so it protects the same
    # user content without turning a 13 MB workbook into a multi-GB scan.
    for cell in sheet._cells.values():
        if cell.value is None and not cell.hyperlink:
            continue
        is_formula = isinstance(cell.value, str) and cell.value.startswith("=")
        formulas += int(is_formula)
        hyperlinks += int(bool(cell.hyperlink))
        cells.append((cell.coordinate, cell.data_type, cell.value, cell.hyperlink.target if cell.hyperlink else None))
    encoded = json.dumps(cells, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
    return {
        "state": sheet.sheet_state,
        "formula_count": formulas,
        "hyperlink_count": hyperlinks,
        "cell_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _advanced_sheet_fingerprint(sheet: Any) -> dict[str, Any]:
    rows = [(key, value.height, value.hidden, value.outlineLevel, value.collapsed, value.style_id) for key, value in sheet.row_dimensions.items()]
    columns = [(key, value.min, value.max, value.width, value.hidden, value.bestFit, value.outlineLevel, value.collapsed, value.style_id) for key, value in sheet.column_dimensions.items()]
    validations = [
        (str(item.sqref), item.type, item.operator, item.formula1, item.formula2, item.allow_blank, item.showErrorMessage, item.showInputMessage, item.showDropDown)
        for item in sheet.data_validations.dataValidation
    ]
    conditional_rules = [(str(key), tuple(str(rule) for rule in rules)) for key, rules in sheet.conditional_formatting._cf_rules.items()]
    comments = [(cell.coordinate, cell.comment.text, cell.comment.author, cell.comment.width, cell.comment.height) for cell in sheet._cells.values() if cell.comment is not None]
    protection = {name: getattr(sheet.protection, name) for name in ("sheet", "objects", "scenarios", "formatCells", "formatColumns", "formatRows", "insertColumns", "insertRows", "insertHyperlinks", "deleteColumns", "deleteRows", "selectLockedCells", "sort", "autoFilter", "pivotTables", "selectUnlockedCells")}
    return {
        "merged_ranges": _stable_hash(sorted(str(item) for item in sheet.merged_cells.ranges)),
        "row_dimensions": _stable_hash(rows),
        "column_dimensions": _stable_hash(columns),
        "freeze_panes": str(sheet.freeze_panes) if sheet.freeze_panes else None,
        "protection": _stable_hash(protection),
        "comments": _stable_hash(comments),
        "data_validations": {"count": len(validations), "sha256": _stable_hash(validations)},
        "conditional_formatting": {"count": len(conditional_rules), "sha256": _stable_hash(conditional_rules)},
    }


def _relationship_part(part: str) -> str:
    return f"{dirname(part)}/_rels/{part.rsplit('/', 1)[-1]}.rels"


def _target_part(owner: str, target: str) -> str:
    if target.startswith("/"):
        return normpath(target.lstrip("/"))
    return normpath(join(dirname(owner), target))


def _protected_ooxml_parts(path: Path) -> dict[str, str]:
    """Pin only drawings/charts/media reachable from preserved worksheets.

    Product sheets are intentionally regenerated. Their relationship IDs may
    change during a valid refresh, so treating every worksheet relationship as
    protected would make publication permanently impossible after integration.
    """
    workbook_ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    package_rel_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        workbook_targets = {
            relation.attrib["Id"]: _target_part("xl/workbook.xml", relation.attrib["Target"])
            for relation in relations.findall(f"{package_rel_ns}Relationship")
        }
        queue = [
            workbook_targets[sheet.attrib[rel_ns]]
            for sheet in workbook.findall(f"{workbook_ns}sheets/{workbook_ns}sheet")
            if sheet.attrib.get("name") not in WORKBOOK_SHEETS
        ]
        protected: set[str] = set()
        while queue:
            part = queue.pop()
            if part in protected or part not in names:
                continue
            protected.add(part)
            relationship_part = _relationship_part(part)
            if relationship_part not in names:
                continue
            protected.add(relationship_part)
            relations = ElementTree.fromstring(archive.read(relationship_part))
            for relation in relations.findall(f"{package_rel_ns}Relationship"):
                target = _target_part(part, relation.attrib["Target"])
                if target.startswith(("xl/drawings/", "xl/media/", "xl/charts/")):
                    queue.append(target)
        relevant = {
            name for name in protected
            if name.startswith(("xl/drawings/", "xl/media/", "xl/charts/", "xl/worksheets/_rels/"))
        }
        return {name: hashlib.sha256(archive.read(name)).hexdigest() for name in sorted(relevant)}


def _snapshot(path: Path) -> dict[str, Any]:
    workbook = load_workbook(path, data_only=False, keep_links=True)
    try:
        return {
            "sheet_order": workbook.sheetnames,
            "defined_names": sorted((name.name, name.attr_text, name.localSheetId, name.hidden) for name in workbook.defined_names.values()),
            "sheets": {sheet.title: {**_cell_fingerprint(sheet), **_advanced_sheet_fingerprint(sheet)} for sheet in workbook.worksheets},
            "protected_ooxml_parts": _protected_ooxml_parts(path),
        }
    finally:
        workbook.close()


def _assert_retained(before: dict[str, Any], after: dict[str, Any]) -> None:
    retained = [name for name in before["sheet_order"] if name not in WORKBOOK_SHEETS]
    actual_retained = [name for name in after["sheet_order"] if name not in WORKBOOK_SHEETS]
    if retained != actual_retained:
        raise ValueError("retained sheet order changed")
    if before["defined_names"] != after["defined_names"]:
        raise ValueError("defined names changed")
    if before["protected_ooxml_parts"] != after["protected_ooxml_parts"]:
        raise ValueError("protected drawing, media, chart, or worksheet relationship parts changed")
    changed = [name for name in retained if before["sheets"][name] != after["sheets"].get(name)]
    if changed:
        raise ValueError("protected sheets changed: " + ", ".join(changed))
    if tuple(after["sheet_order"][: len(WORKBOOK_SHEETS)]) != WORKBOOK_SHEETS:
        raise ValueError("product navigation is not the first six sheets")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Required explicit confirmation to replace the canonical workbook.")
    parser.add_argument("--quote-bundle", type=Path, help="Required current, retained dual-source quote bundle.")
    args = parser.parse_args()
    if not args.publish:
        raise ValueError("refusing publish without --publish")
    if args.quote_bundle is None:
        raise ValueError("refusing publish without --quote-bundle")

    canonical = _workbook_path()
    daily_quote = load_daily_quote_binding(root=ROOT, bundle_path=args.quote_bundle)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = ROOT / "runtime" / "workbook-backups"
    receipt_dir = ROOT / "runtime" / "publication-receipts"
    backup_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    before_sha = _sha256(canonical)
    before = _snapshot(canonical)
    backup = backup_dir / f"canonical-before-m7-product-ux-{stamp}.xlsx"
    shutil.copy2(canonical, backup)
    if _sha256(backup) != before_sha:
        raise ValueError("backup hash mismatch")

    staging = canonical.with_name(f".{canonical.stem}.m7-staging-{uuid4().hex}{canonical.suffix}")
    shutil.copy2(canonical, staging)
    try:
        packet = build_daily_product_packet(
            root=ROOT, generated_at=datetime.now(timezone.utc), daily_quote=daily_quote
        )
        model = product_workbench_from_payload(build_product_workbench_candidate_payload(packet, root=ROOT))
        workbook = load_workbook(staging, data_only=False, keep_links=True)
        try:
            apply_product_workbench_to_existing_workbook(workbook, model)
            workbook.save(staging)
        finally:
            workbook.close()
        after_staging = _snapshot(staging)
        _assert_retained(before, after_staging)
        staging_sha = _sha256(staging)
        os.replace(staging, canonical)
        after_sha = _sha256(canonical)
        after = _snapshot(canonical)
        _assert_retained(before, after)
    except Exception:
        if staging.exists():
            staging.unlink()
        raise

    receipt = {
        "schema_version": "canonical-product-publication-v1",
        "status": "PUBLISHED_PENDING_WPS_VISUAL_REVIEW",
        "workbook_source": "WORKBOOK_PATH",
        "canonical_filename": canonical.name,
        "canonical_file_before_sha256": before_sha,
        "backup": str(backup.relative_to(ROOT)),
        "backup_sha256": _sha256(backup),
        "staging_sha256": staging_sha,
        "canonical_file_after_sha256": after_sha,
        "workbook_path_unchanged": True,
        "product_sheets_present": True,
        "user_managed_sheets_preserved": True,
        "frozen_sheets_unchanged": True,
        "sheet_contract": {name: ("PRODUCT_MANAGED" if name in WORKBOOK_SHEETS else "PRESERVED") for name in after["sheet_order"]},
        "action": "no_order",
        "daily_quote_binding": daily_quote,
    }
    receipt_path = receipt_dir / f"canonical-m7-product-publication-{stamp}.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**receipt, "receipt": str(receipt_path.relative_to(ROOT))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

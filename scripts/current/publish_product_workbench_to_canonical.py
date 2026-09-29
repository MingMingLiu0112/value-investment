#!/usr/bin/env python3
"""Publish the M7 product surface into the one configured canonical workbook.

This deliberately never creates a second user-facing workbook. It stages beside
the configured workbook, proves retained sheets did not change, and uses a
backup-aware Windows replacement to detect and recover a concurrent source edit.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import sys
import zipfile
from posixpath import dirname, join, normpath
from datetime import date, datetime, timezone
from pathlib import Path
import re
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
from value_investment_agent.application.product.prospective_observation import (  # noqa: E402
    load_verified_observation_ledger,
)
from value_investment_agent.application.product.prospective_registration import (  # noqa: E402
    verify_prospective_registration_receipt,
)
from value_investment_agent.presentation.excel.product_workbench import (  # noqa: E402
    WORKBOOK_SHEETS,
    apply_product_workbench_to_existing_workbook,
    build_product_workbench_workbook,
)
from value_investment_agent.presentation.read_models.product_workbench import (  # noqa: E402
    product_workbench_from_payload,
)


CANONICAL_NAME = "A股价值投资_Agent前端智能跟踪模板.xlsx"
PROSPECTIVE_RECEIPT_PATH = "runtime/prospective-v2-fc1e811/receipt.json"
PROSPECTIVE_RECEIPT_SHA256 = "8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5"
PROSPECTIVE_PLAN_PATH = "config/prospective-research-observation-plan-v2.json"


class _PreservePublicationArtifacts(RuntimeError):
    """Signal that recovery files must remain available for manual repair."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_canonical_source_unchanged(canonical: Path, expected_sha256: str) -> None:
    if not canonical.is_file() or _sha256(canonical) != expected_sha256:
        raise ValueError("canonical workbook changed during staging; refusing to replace")


def _assert_workbook_not_open(canonical: Path) -> None:
    if (canonical.parent / f"~${canonical.name}").exists():
        raise RuntimeError("CANONICAL_PUBLICATION_BLOCKED_BY_OPEN_WORKBOOK")


def _replace_file_with_backup(destination: Path, replacement: Path, backup: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("canonical workbook publication requires Windows ReplaceFileW")
    if backup.exists():
        raise FileExistsError(backup)

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    replace_file = kernel32.ReplaceFileW
    replace_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    replace_file.restype = wintypes.BOOL
    if not replace_file(str(destination), str(replacement), str(backup), 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def _canonical_write_guard(canonical: Path):
    if os.name != "nt":
        raise RuntimeError("canonical workbook publication requires Windows file sharing")

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        str(canonical),
        0x80000000,
        0x00000001 | 0x00000004,
        None,
        3,
        0x00000080,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        error_code = ctypes.get_last_error()
        error = ctypes.WinError(error_code)
        if error_code in (32, 33):
            raise RuntimeError("CANONICAL_PUBLICATION_BLOCKED_BY_OPEN_WORKBOOK") from error
        raise error
    try:
        yield
    finally:
        close_handle(handle)


def _preserve_artifacts(message: str, *paths: Path) -> _PreservePublicationArtifacts:
    retained = [str(path) for path in paths if path.exists()]
    return _PreservePublicationArtifacts(
        f"{message}; retained artifacts: {', '.join(retained) if retained else 'none'}"
    )


def _replace_canonical_staging(
    canonical: Path,
    staging: Path,
    *,
    expected_source_sha256: str,
    staging_sha256: str,
) -> str:
    _assert_canonical_source_unchanged(canonical, expected_source_sha256)
    _assert_workbook_not_open(canonical)
    if _sha256(staging) != staging_sha256:
        raise ValueError("staging workbook changed before replacement; refusing to publish")

    with _canonical_write_guard(canonical):
        _assert_canonical_source_unchanged(canonical, expected_source_sha256)
        _assert_workbook_not_open(canonical)
        if _sha256(staging) != staging_sha256:
            raise ValueError("staging workbook changed before replacement; refusing to publish")

        displaced = canonical.with_name(f".{canonical.name}.displaced-{uuid4().hex}.xlsx")
        rollback = canonical.with_name(f".{canonical.name}.rollback-{uuid4().hex}.xlsx")
        try:
            _replace_file_with_backup(canonical, staging, displaced)
        except OSError as error:
            if displaced.exists() and not canonical.exists():
                try:
                    displaced.rename(canonical)
                except OSError as restore_error:
                    raise _preserve_artifacts(
                        "atomic replacement failed and the canonical path is missing",
                        canonical, displaced, staging, rollback,
                    ) from restore_error
                if _sha256(canonical) != expected_source_sha256:
                    raise ValueError(
                        "atomic replacement failed; displaced concurrent version restored; refusing to publish"
                    ) from error
                raise
            if displaced.exists():
                if canonical.is_file() and _sha256(canonical) == expected_source_sha256:
                    if _sha256(displaced) == expected_source_sha256:
                        try:
                            displaced.unlink()
                        except OSError as cleanup_error:
                            raise _preserve_artifacts(
                                "atomic replacement failed; duplicate source could not be cleaned up",
                                canonical, displaced, staging, rollback,
                            ) from cleanup_error
                    else:
                        raise _preserve_artifacts(
                            "atomic replacement failed; canonical source and displaced version differ",
                            canonical, displaced, staging, rollback,
                        ) from error
                else:
                    raise _preserve_artifacts(
                        "atomic replacement failed; canonical and displaced files need recovery",
                        canonical, displaced, staging, rollback,
                    ) from error
            raise

        if not displaced.is_file():
            raise _preserve_artifacts(
                "atomic replacement did not preserve the displaced workbook",
                canonical, displaced, staging, rollback,
            )
        displaced_sha256 = _sha256(displaced)
        if displaced_sha256 != expected_source_sha256:
            try:
                with _canonical_write_guard(canonical):
                    _assert_workbook_not_open(canonical)
                    _replace_file_with_backup(canonical, displaced, rollback)
                    restored_sha256 = _sha256(canonical) if canonical.is_file() else None
                    if restored_sha256 != displaced_sha256:
                        raise _preserve_artifacts(
                            "canonical changed during replacement; rollback did not verify",
                            canonical, displaced, staging, rollback,
                        )
                    if rollback.is_file() and _sha256(rollback) == staging_sha256:
                        rollback.unlink()
            except (OSError, RuntimeError) as error:
                if not canonical.exists() and displaced.exists():
                    try:
                        displaced.rename(canonical)
                    except OSError as restore_error:
                        raise _preserve_artifacts(
                            "rollback failed and the canonical path is missing",
                            canonical, displaced, staging, rollback,
                        ) from restore_error
                    if _sha256(canonical) != displaced_sha256:
                        raise _preserve_artifacts(
                            "rollback recovery did not verify the displaced workbook",
                            canonical, displaced, staging, rollback,
                        ) from error
                    raise ValueError(
                        "canonical changed during replacement; concurrent version restored; "
                        "product candidate retained for recovery"
                    ) from error
                raise _preserve_artifacts(
                    "canonical changed during replacement; rollback failed",
                    canonical, displaced, staging, rollback,
                ) from error
            raise ValueError(
                "canonical changed during replacement; concurrent version restored; refusing to publish"
            )

        try:
            with _canonical_write_guard(canonical):
                after_sha256 = _sha256(canonical)
                if after_sha256 != staging_sha256:
                    raise _preserve_artifacts(
                        "canonical changed before publication could be finalized",
                        canonical, displaced, staging, rollback,
                    )
                displaced.unlink()
                after_sha256 = _sha256(canonical)
                if after_sha256 != staging_sha256:
                    raise _preserve_artifacts(
                        "canonical workbook changed immediately after replacement",
                        canonical, displaced, staging, rollback,
                    )
                return after_sha256
        except RuntimeError as error:
            raise _preserve_artifacts(
                "canonical could not be locked to finalize publication",
                canonical, displaced, staging, rollback,
            ) from error


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
    _assert_workbook_not_open(path)
    return path


def _registered_quote_context() -> dict[str, Any]:
    try:
        receipt, registration = verify_prospective_registration_receipt(
            root=ROOT, receipt_path=PROSPECTIVE_RECEIPT_PATH,
            receipt_sha256=PROSPECTIVE_RECEIPT_SHA256,
            plan_path=PROSPECTIVE_PLAN_PATH,
        )
    except (OSError, ValueError) as error:
        raise ValueError("CURRENT_QUOTE_REGISTRATION_NOT_BOUND") from error
    symbols = tuple(sorted(case.symbol for case in registration.cases))
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("CURRENT_QUOTE_REGISTRATION_NOT_BOUND")
    return {
        "symbols": symbols,
        "registration_receipt_sha256": PROSPECTIVE_RECEIPT_SHA256,
        "registration_sha256": receipt["registration_sha256"],
        "plan_sha256": receipt["plan_sha256"],
    }


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


def _load_m5_event_projection(
    root: Path, path: Path | None, expected_sha256: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if (path is None) != (expected_sha256 is None):
        raise ValueError("M5 projection path and SHA-256 must be supplied together")
    if path is None:
        return None, None
    resolved = (path if path.is_absolute() else root / path).resolve()
    runtime_root = (root / "runtime").resolve()
    if not resolved.is_relative_to(runtime_root) or not resolved.is_file():
        raise ValueError("M5 projection must be an existing file under runtime/")
    actual_sha256 = _sha256(resolved)
    if actual_sha256 != expected_sha256.lower():
        raise ValueError("M5 projection SHA-256 mismatch")
    document = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("action") != "no_order":
        raise ValueError("M5 projection must be a no_order object")
    projection = document.get("projection", document)
    if not isinstance(projection, dict) or projection.get("action") != "no_order":
        raise ValueError("M5 projection payload must be a no_order object")
    report = document.get("report")
    if isinstance(report, dict):
        cutoff = report.get("public_event_observation_as_of")
        if cutoff is None:
            appended = report.get("appended_observation")
            if isinstance(appended, dict):
                cutoff = appended.get("announcement_date")
        if str(report.get("schema_version", "")).startswith("registered-public-event-projection-"):
            if not isinstance(cutoff, str):
                raise ValueError("M5 registered public-event projection requires an explicit as-of date")
            projection = dict(projection)
            projection["evaluation_cutoff_date"] = cutoff
        elif cutoff is not None:
            projection = dict(projection)
            projection["evaluation_cutoff_date"] = cutoff
    return projection, actual_sha256


def _load_prospective_observation_ledger(
    root: Path,
    path: Path | None,
    expected_sha256: str | None,
    evaluation_cutoff: str | None,
) -> tuple[tuple[dict[str, Any], ...] | None, str | None, str | None]:
    """Validate the explicit observation input used by both publisher paths."""
    if path is None and expected_sha256 is None and evaluation_cutoff is None:
        return None, None, None
    if path is None or expected_sha256 is None or evaluation_cutoff is None:
        raise ValueError(
            "observation ledger path, SHA-256 and evaluation cutoff must be supplied together"
        )
    try:
        cutoff = datetime.fromisoformat(evaluation_cutoff)
    except ValueError as error:
        raise ValueError("observation evaluation cutoff must be ISO-8601") from error
    rows = load_verified_observation_ledger(
        root=root,
        manifest_path=path,
        manifest_sha256=expected_sha256,
        evaluation_cutoff=cutoff,
    )
    return rows, expected_sha256.lower(), cutoff.isoformat()


def _observation_ledger_binding_status(manifest_sha256: str | None) -> str:
    return "BOUND" if manifest_sha256 else "NOT_BOUND"


def _require_monotonic_quote_session(
    root: Path, quote_as_of: str, canonical_sha256: str,
) -> None:
    root = root.resolve()
    pointer_path = root / "config" / "current-trial-workbook.json"
    try:
        current = json.loads(pointer_path.read_text(encoding="utf-8"))
        current_as_of = date.fromisoformat(current["quote_as_of"])
        candidate_as_of = date.fromisoformat(quote_as_of)
        pointer_sha256 = current["canonical_workbook_sha256"]
        receipt_reference = Path(current["publication_receipt"])
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError("CURRENT_QUOTE_SESSION_POINTER_INVALID") from error

    receipt_dir = root / "runtime" / "publication-receipts"
    receipt_dir_resolved = receipt_dir.resolve()
    pointer_receipt_path = (root / receipt_reference).resolve()
    if (
        not re.fullmatch(r"[0-9a-f]{64}", str(pointer_sha256))
        or not re.fullmatch(r"[0-9a-f]{64}", canonical_sha256)
        or not pointer_receipt_path.is_relative_to(receipt_dir_resolved)
    ):
        raise ValueError("CURRENT_QUOTE_SESSION_POINTER_INVALID")

    publication_statuses = {
        "PUBLISHED_PENDING_WPS_VISUAL_REVIEW",
        "PUBLISHED_WPS_READONLY_AND_READABILITY_VERIFIED",
    }
    recovery_status = "PUBLISHED_RESULT_RECOVERED_FROM_CAPTURED_OUTPUT"

    def read_receipt(path: Path) -> dict[str, Any]:
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID") from error
        if not isinstance(receipt, dict):
            raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID")
        return receipt

    def receipt_fields(receipt: dict[str, Any]) -> tuple[str, date | None] | None:
        schema = receipt.get("schema_version")
        if schema == "canonical-product-publication-v1":
            if receipt.get("status") not in publication_statuses:
                raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID")
            after_sha256 = receipt.get("canonical_file_after_sha256")
            quote_binding = receipt.get("daily_quote_binding")
            if quote_binding is None:
                published_as_of = None
            else:
                if not isinstance(quote_binding, dict):
                    raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID")
                try:
                    published_as_of = date.fromisoformat(quote_binding["as_of"])
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID") from error
        elif schema == "canonical-product-publication-recovery-v1":
            if receipt.get("status") != recovery_status:
                raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID")
            after_sha256 = receipt.get("canonical_file_after_sha256")
            try:
                published_as_of = date.fromisoformat(receipt["quote_as_of"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID") from error
        else:
            return None
        if not isinstance(after_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", after_sha256):
            raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID")
        return after_sha256, published_as_of

    if not pointer_receipt_path.is_file():
        raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID")
    pointer_receipt_fields = receipt_fields(read_receipt(pointer_receipt_path))
    if pointer_receipt_fields is None or pointer_receipt_fields[0] != pointer_sha256:
        raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID")
    pointer_receipt_as_of = pointer_receipt_fields[1]

    matching_receipt_dates: list[date] = []
    if receipt_dir.exists():
        for receipt_path in receipt_dir.glob("canonical-m7-product-publication-*.json"):
            receipt = read_receipt(receipt_path)
            fields = receipt_fields(receipt)
            if fields is None or fields[0] != canonical_sha256:
                continue
            if fields[1] is None:
                if pointer_sha256 == canonical_sha256:
                    continue
                raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID")
            matching_receipt_dates.append(fields[1])

    if not matching_receipt_dates and pointer_sha256 != canonical_sha256:
        raise ValueError("CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID")

    latest_published_as_of = max([
        current_as_of,
        *matching_receipt_dates,
        *([pointer_receipt_as_of] if pointer_receipt_as_of is not None else []),
    ])

    if candidate_as_of < latest_published_as_of:
        raise ValueError("DAILY_QUOTE_SESSION_REGRESSION")


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
            "active_sheet": workbook.active.title if workbook.active else None,
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
    changed = []
    for name in retained:
        previous = dict(before["sheets"][name])
        current = dict(after["sheets"].get(name, {}))
        previous_state = previous.pop("state")
        current_state = current.pop("state")
        state_ok = (
            current_state == previous_state
            if previous_state != "visible"
            else current_state == "hidden"
        )
        if not state_ok or previous != current:
            changed.append(name)
    if changed:
        raise ValueError("protected sheet content or non-navigation properties changed: " + ", ".join(changed))
    if tuple(after["sheet_order"][: len(WORKBOOK_SHEETS)]) != WORKBOOK_SHEETS:
        raise ValueError("product navigation is not the first six sheets")
    if any(after["sheets"][name]["state"] == "visible" for name in retained):
        raise ValueError("non-product worksheet remains visible in default navigation")
    if after["active_sheet"] != WORKBOOK_SHEETS[0]:
        raise ValueError("default active worksheet is not the product home page")


def _hide_legacy_sheets(workbook: Any) -> list[str]:
    if tuple(workbook.sheetnames[: len(WORKBOOK_SHEETS)]) != WORKBOOK_SHEETS:
        raise ValueError("product pages must be first and in canonical order before navigation update")
    hidden = []
    for sheet in workbook.worksheets:
        if sheet.title not in WORKBOOK_SHEETS and sheet.sheet_state == "visible":
            sheet.sheet_state = "hidden"
            hidden.append(sheet.title)
    workbook.active = 0
    return hidden


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Required explicit confirmation to replace the canonical workbook.")
    parser.add_argument("--verify-only", action="store_true", help="Validate the same product model without writing the workbook.")
    parser.add_argument("--quote-bundle", type=Path, help="Required current, retained dual-source quote bundle.")
    parser.add_argument("--prospective-snapshot", type=Path, help="Verified public research snapshot under runtime.")
    parser.add_argument("--prospective-sha256", help="Pinned SHA-256 of the prospective snapshot.")
    parser.add_argument("--m5-event-projection", type=Path, help="Hash-pinned M5 projection JSON under runtime.")
    parser.add_argument("--m5-event-projection-sha256", help="Pinned SHA-256 of the M5 projection JSON.")
    parser.add_argument("--prospective-observation-ledger", type=Path, help="Hash-pinned prospective observation manifest under config.")
    parser.add_argument("--prospective-observation-ledger-sha256", help="Pinned SHA-256 of the prospective observation manifest.")
    parser.add_argument("--prospective-observation-evaluation-cutoff", help="Timezone-aware ISO-8601 evaluation cutoff for the observation manifest.")
    args = parser.parse_args()
    if args.publish == args.verify_only:
        raise ValueError("choose exactly one of --publish or --verify-only")
    if args.quote_bundle is None:
        raise ValueError("refusing publish without --quote-bundle")
    if (args.prospective_snapshot is None) != (args.prospective_sha256 is None):
        raise ValueError("prospective snapshot path and SHA-256 must be supplied together")
    m5_event_projection, m5_projection_sha256 = _load_m5_event_projection(
        ROOT, args.m5_event_projection, args.m5_event_projection_sha256,
    )
    observation_rows, observation_manifest_sha256, observation_cutoff = _load_prospective_observation_ledger(
        ROOT,
        args.prospective_observation_ledger,
        args.prospective_observation_ledger_sha256,
        args.prospective_observation_evaluation_cutoff,
    )

    canonical = _workbook_path()
    registration = _registered_quote_context()
    daily_quote = load_daily_quote_binding(
        root=ROOT, bundle_path=args.quote_bundle,
        registered_symbols=registration["symbols"],
        registration_receipt_sha256=registration["registration_receipt_sha256"],
        registration_sha256=registration["registration_sha256"],
        plan_sha256=registration["plan_sha256"], excluded_symbols=("600519",),
    )
    _require_monotonic_quote_session(ROOT, daily_quote["as_of"], _sha256(canonical))
    if args.verify_only:
        packet = build_daily_product_packet(root=ROOT, generated_at=datetime.now(timezone.utc), daily_quote=daily_quote)
        model = product_workbench_from_payload(build_product_workbench_candidate_payload(
            packet, root=ROOT, prospective_snapshot_path=args.prospective_snapshot,
            prospective_snapshot_sha256=args.prospective_sha256,
            m5_event_projection=m5_event_projection,
            prospective_observation_ledger_path=args.prospective_observation_ledger,
            prospective_observation_ledger_sha256=observation_manifest_sha256,
            prospective_observation_evaluation_cutoff=(
                datetime.fromisoformat(observation_cutoff) if observation_cutoff else None
            ),
        ))
        preview = build_product_workbench_workbook(model)
        try:
            if tuple(preview.sheetnames) != tuple(WORKBOOK_SHEETS):
                raise ValueError("product sheet contract differs from canonical navigation")
            print(json.dumps({
                "status": "VERIFIED_IN_MEMORY_ONLY", "action": "no_order",
                "canonical_before_sha256": _sha256(canonical),
                "prospective_snapshot_sha256": args.prospective_sha256,
                "m5_event_projection_sha256": m5_projection_sha256,
                "prospective_observation_ledger_binding_status": _observation_ledger_binding_status(
                    observation_manifest_sha256
                ),
                "prospective_observation_ledger_sha256": observation_manifest_sha256,
                "prospective_observation_evaluation_cutoff": observation_cutoff,
                "prospective_observation_ids": [row["observation_id"] for row in observation_rows or ()],
                "prospective_observation_count": len(observation_rows or ()),
                "company_symbols": [company.symbol for company in model.companies],
                "quote_as_of": daily_quote.get("as_of"),
                "workbook_modified": False,
            }, ensure_ascii=False, indent=2))
        finally:
            preview.close()
        return 0
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
        model = product_workbench_from_payload(build_product_workbench_candidate_payload(
            packet, root=ROOT, prospective_snapshot_path=args.prospective_snapshot,
            prospective_snapshot_sha256=args.prospective_sha256,
            m5_event_projection=m5_event_projection,
            prospective_observation_ledger_path=args.prospective_observation_ledger,
            prospective_observation_ledger_sha256=observation_manifest_sha256,
            prospective_observation_evaluation_cutoff=(
                datetime.fromisoformat(observation_cutoff) if observation_cutoff else None
            ),
        ))
        workbook = load_workbook(staging, data_only=False, keep_links=True)
        try:
            apply_product_workbench_to_existing_workbook(workbook, model)
            hidden_legacy_sheets = _hide_legacy_sheets(workbook)
            workbook.save(staging)
        finally:
            workbook.close()
        after_staging = _snapshot(staging)
        _assert_retained(before, after_staging)
        staging_sha = _sha256(staging)
        _assert_canonical_source_unchanged(canonical, before_sha)
        after_sha = _replace_canonical_staging(
            canonical,
            staging,
            expected_source_sha256=before_sha,
            staging_sha256=staging_sha,
        )
        after = _snapshot(canonical)
        _assert_retained(before, after)
    except _PreservePublicationArtifacts:
        raise
    except Exception as error:
        if not canonical.is_file():
            raise _preserve_artifacts(
                "publication failed and canonical path is missing",
                canonical, backup, staging,
            ) from error
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
        "preserved_sheet_content_unchanged": True,
        "default_navigation_limited_to_product_pages": True,
        "legacy_sheets_hidden": hidden_legacy_sheets,
        "sheet_contract": {name: ("PRODUCT_MANAGED" if name in WORKBOOK_SHEETS else "PRESERVED") for name in after["sheet_order"]},
        "action": "no_order",
        "daily_quote_binding": daily_quote,
        "prospective_snapshot_sha256": args.prospective_sha256,
        "m5_event_projection_sha256": m5_projection_sha256,
        "prospective_observation_ledger_path": (
            str(args.prospective_observation_ledger) if args.prospective_observation_ledger else None
        ),
        "prospective_observation_ledger_binding_status": _observation_ledger_binding_status(
            observation_manifest_sha256
        ),
        "prospective_observation_ledger_sha256": observation_manifest_sha256,
        "prospective_observation_evaluation_cutoff": observation_cutoff,
        "prospective_observation_ids": [row["observation_id"] for row in observation_rows or ()],
        "prospective_observation_count": len(observation_rows or ()),
    }
    receipt_path = receipt_dir / f"canonical-m7-product-publication-{stamp}.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**receipt, "receipt": str(receipt_path.relative_to(ROOT))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

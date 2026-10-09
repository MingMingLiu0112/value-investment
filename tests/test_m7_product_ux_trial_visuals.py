from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

from openpyxl import Workbook
import pytest


SCRIPT = Path(__file__).parents[1] / "scripts/current/verify_m7_product_ux_trial_visuals.py"
SPEC = importlib.util.spec_from_file_location("m7_product_ux_trial_visuals", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_workbook(
    path: Path,
    *,
    user_extra_column: bool = False,
    secondary_extra_column: bool = True,
    forbidden_token: str | None = None,
) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name in MODULE.ALL_SHEETS:
        sheet = workbook.create_sheet(sheet_name)
        sheet.freeze_panes = "B4"
        sheet.sheet_view.showGridLines = False
        sheet["A4"] = "正常内容"
        if sheet_name == MODULE.USER_SHEETS[0] and user_extra_column:
            sheet["G4"] = "不应允许的用户页第七列"
        if sheet_name == MODULE.SECONDARY_SHEETS[0] and secondary_extra_column:
            sheet["G4"] = "允许的审计页第七列"
        if sheet_name == MODULE.USER_SHEETS[0] and forbidden_token:
            sheet["B4"] = forbidden_token
    workbook.save(path)


def test_seven_column_secondary_audit_page_is_allowed(tmp_path: Path) -> None:
    workbook_path = tmp_path / "candidate.xlsx"
    _write_workbook(workbook_path)

    audit = MODULE.audit_workbook(workbook_path)

    assert audit["sheet_checks"][MODULE.SECONDARY_SHEETS[0]]["max_column"] == 7


def test_seven_column_primary_page_is_rejected(tmp_path: Path) -> None:
    workbook_path = tmp_path / "candidate.xlsx"
    _write_workbook(workbook_path, user_extra_column=True)

    with pytest.raises(ValueError, match="horizontal scrolling"):
        MODULE.audit_workbook(workbook_path)


def test_wrong_workbook_hash_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workbook_path = tmp_path / "candidate.xlsx"
    manifest_path = tmp_path / "manifest.json"
    wps_path = tmp_path / "wps.json"
    pdf_dir = tmp_path / "pdf"
    output_path = tmp_path / "visual.json"
    _write_workbook(workbook_path)
    manifest_path.write_text(
        json.dumps({"workbook_sha256": _sha256(workbook_path)}), encoding="utf-8"
    )
    wps_path.write_text(
        json.dumps({"sha256": _sha256(workbook_path), "status": "passed", "read_only": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify",
            "--root",
            str(tmp_path),
            "--workbook",
            str(workbook_path),
            "--manifest",
            str(manifest_path),
            "--wps-receipt",
            str(wps_path),
            "--pdf-directory",
            str(pdf_dir),
            "--output",
            str(output_path),
            "--expected-workbook-sha256",
            "0" * 64,
        ],
    )

    with pytest.raises(ValueError, match="workbook SHA-256"):
        MODULE.main()


def test_wps_mismatch_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workbook_path = tmp_path / "candidate.xlsx"
    manifest_path = tmp_path / "manifest.json"
    wps_path = tmp_path / "wps.json"
    pdf_dir = tmp_path / "pdf"
    output_path = tmp_path / "visual.json"
    _write_workbook(workbook_path)
    workbook_sha = _sha256(workbook_path)
    manifest_path.write_text(
        json.dumps({"workbook_sha256": workbook_sha}), encoding="utf-8"
    )
    wps_path.write_text(
        json.dumps({"sha256": "0" * 64, "status": "passed", "read_only": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify",
            "--root",
            str(tmp_path),
            "--workbook",
            str(workbook_path),
            "--manifest",
            str(manifest_path),
            "--wps-receipt",
            str(wps_path),
            "--pdf-directory",
            str(pdf_dir),
            "--output",
            str(output_path),
            "--expected-workbook-sha256",
            workbook_sha,
        ],
    )

    with pytest.raises(ValueError, match="WPS receipt"):
        MODULE.main()


def test_blank_wps_pdf_page_is_rejected(tmp_path: Path) -> None:
    if MODULE.fitz is None:
        pytest.skip("PyMuPDF is required for WPS PDF audit")
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    for sheet_name in MODULE.ALL_SHEETS:
        document = MODULE.fitz.open()
        document.new_page()
        document.save(pdf_dir / f"{sheet_name}.pdf")
        document.close()

    with pytest.raises(ValueError, match="blank PDF page"):
        MODULE.audit_pdfs(pdf_dir)


def test_forbidden_user_page_token_is_rejected(tmp_path: Path) -> None:
    workbook_path = tmp_path / "candidate.xlsx"
    _write_workbook(workbook_path, forbidden_token="BLOCKED")

    with pytest.raises(ValueError, match="internal tokens"):
        MODULE.audit_workbook(workbook_path)

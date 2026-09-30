from __future__ import annotations

from contextlib import nullcontext
import os
from pathlib import Path

from openpyxl import Workbook
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.worksheet.datavalidation import DataValidation
import pytest

from scripts.current.publish_product_workbench_to_canonical import (
    _PreservePublicationArtifacts,
    _assert_canonical_source_unchanged,
    _assert_retained,
    _hide_legacy_sheets,
    _replace_canonical_staging,
    _replace_file_with_backup,
    _sha256,
    _snapshot,
)
import scripts.current.publish_product_workbench_to_canonical as publisher
from value_investment_agent.presentation.excel.product_workbench import WORKBOOK_SHEETS


def _workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = WORKBOOK_SHEETS[0]
    for name in WORKBOOK_SHEETS[1:]:
        workbook.create_sheet(name)
    sheet = workbook.create_sheet("人工持仓")
    sheet["A1"] = "用户输入"
    sheet["B2"] = "=1+1"
    sheet["C3"].hyperlink = "https://example.test/evidence"
    sheet["D4"].comment = Comment("人工备注", "user")
    sheet.merge_cells("E1:F1")
    sheet.freeze_panes = "B3"
    sheet.row_dimensions[3].height = 24
    sheet.column_dimensions["A"].width = 22
    sheet.protection.sheet = True
    validation = DataValidation(type="list", formula1='"A,B"')
    sheet.add_data_validation(validation)
    validation.add(sheet["G1"])
    sheet.conditional_formatting.add("H1", CellIsRule(operator="greaterThan", formula=["0"]))
    workbook.create_named_range("manual_input", sheet, "A1")
    workbook.save(path)


def test_canonical_snapshot_covers_advanced_preservation_contract(tmp_path: Path):
    path = tmp_path / "canonical.xlsx"
    _workbook(path)

    before = _snapshot(path)
    workbook = load_workbook(path)
    _hide_legacy_sheets(workbook)
    workbook.save(path)
    after = _snapshot(path)

    _assert_retained(before, after)
    protected = before["sheets"]["人工持仓"]
    assert protected["merged_ranges"]
    assert protected["row_dimensions"]
    assert protected["column_dimensions"]
    assert protected["freeze_panes"] == "B3"
    assert protected["protection"]
    assert protected["comments"]
    assert protected["data_validations"]["count"] == 1
    assert protected["conditional_formatting"]["count"] == 1


def test_canonical_snapshot_fails_when_protected_structure_changes(tmp_path: Path):
    path = tmp_path / "canonical.xlsx"
    _workbook(path)
    before = _snapshot(path)

    workbook = load_workbook(path)
    workbook["人工持仓"].freeze_panes = "C3"
    _hide_legacy_sheets(workbook)
    workbook.save(path)
    after = _snapshot(path)

    with pytest.raises(ValueError, match="protected sheet content or non-navigation properties changed"):
        _assert_retained(before, after)


def test_publish_refuses_when_canonical_changes_during_staging(tmp_path: Path):
    path = tmp_path / "canonical.xlsx"
    _workbook(path)
    expected_sha256 = _sha256(path)

    workbook = load_workbook(path)
    workbook["人工持仓"]["A1"] = "用户并发修改"
    workbook.save(path)

    with pytest.raises(ValueError, match="canonical workbook changed during staging"):
        _assert_canonical_source_unchanged(path, expected_sha256)


def test_publish_detects_change_before_write_guard_is_acquired(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "canonical.xlsx"
    staging = tmp_path / "staging.xlsx"
    canonical.write_bytes(b"original")
    staging.write_bytes(b"product candidate")
    expected_source = _sha256(canonical)
    staging_sha = _sha256(staging)
    def change_before_guard(path: Path):
        path.write_bytes(b"concurrent user save")
        return nullcontext()

    monkeypatch.setattr(publisher, "_canonical_write_guard", change_before_guard)

    with pytest.raises(ValueError, match="canonical workbook changed during staging"):
        _replace_canonical_staging(
            canonical,
            staging,
            expected_source_sha256=expected_source,
            staging_sha256=staging_sha,
        )

    assert canonical.read_bytes() == b"concurrent user save"
    assert staging.read_bytes() == b"product candidate"
    assert not list(tmp_path.glob("*.displaced-*.xlsx"))
    assert not list(tmp_path.glob("*.rollback-*.xlsx"))


def test_publish_refuses_if_wps_opens_workbook_during_staging(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "canonical.xlsx"
    staging = tmp_path / "staging.xlsx"
    canonical.write_bytes(b"original")
    staging.write_bytes(b"product candidate")
    expected_source = _sha256(canonical)
    staging_sha = _sha256(staging)
    (tmp_path / f"~${canonical.name}").write_bytes(b"WPS lock")

    def unexpected_replace(*args, **kwargs):
        pytest.fail("replacement must not start while the WPS lock exists")

    monkeypatch.setattr(publisher, "_replace_file_with_backup", unexpected_replace)

    with pytest.raises(RuntimeError, match="CANONICAL_PUBLICATION_BLOCKED_BY_OPEN_WORKBOOK"):
        _replace_canonical_staging(
            canonical,
            staging,
            expected_source_sha256=expected_source,
            staging_sha256=staging_sha,
        )

    assert canonical.read_bytes() == b"original"


@pytest.mark.skipif(os.name != "nt", reason="Windows ReplaceFileW integration test")
def test_windows_replace_file_preserves_displaced_source(tmp_path: Path):
    canonical = tmp_path / "canonical.xlsx"
    staging = tmp_path / "staging.xlsx"
    displaced = tmp_path / "displaced.xlsx"
    canonical.write_bytes(b"original")
    staging.write_bytes(b"replacement")

    _replace_file_with_backup(canonical, staging, displaced)

    assert canonical.read_bytes() == b"replacement"
    assert displaced.read_bytes() == b"original"
    assert not staging.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows guarded publication integration test")
def test_publish_with_write_guard_completes_atomic_replacement(tmp_path: Path):
    canonical = tmp_path / "canonical.xlsx"
    staging = tmp_path / "staging.xlsx"
    canonical.write_bytes(b"original")
    staging.write_bytes(b"product candidate")

    result = _replace_canonical_staging(
        canonical,
        staging,
        expected_source_sha256=_sha256(canonical),
        staging_sha256=_sha256(staging),
    )

    assert canonical.read_bytes() == b"product candidate"
    assert result == _sha256(canonical)
    assert not staging.exists()
    assert not list(tmp_path.glob("*.displaced-*.xlsx"))


@pytest.mark.skipif(os.name != "nt", reason="Windows file-sharing integration test")
def test_publish_refuses_while_workbook_has_an_open_writer(tmp_path: Path):
    canonical = tmp_path / "canonical.xlsx"
    staging = tmp_path / "staging.xlsx"
    canonical.write_bytes(b"original")
    staging.write_bytes(b"product candidate")
    expected_source = _sha256(canonical)
    staging_sha = _sha256(staging)

    with canonical.open("r+b"):
        with pytest.raises(RuntimeError, match="CANONICAL_PUBLICATION_BLOCKED_BY_OPEN_WORKBOOK"):
            _replace_canonical_staging(
                canonical,
                staging,
                expected_source_sha256=expected_source,
                staging_sha256=staging_sha,
            )

    assert canonical.read_bytes() == b"original"
    assert staging.read_bytes() == b"product candidate"


@pytest.mark.skipif(os.name != "nt", reason="Windows file-sharing integration test")
def test_publish_preserves_source_if_new_canonical_is_opened_for_write(
    tmp_path: Path,
    monkeypatch,
):
    canonical = tmp_path / "canonical.xlsx"
    staging = tmp_path / "staging.xlsx"
    canonical.write_bytes(b"original")
    staging.write_bytes(b"product candidate")
    expected_source = _sha256(canonical)
    staging_sha = _sha256(staging)
    writer_handles = []

    def replace_then_open_candidate(
        destination: Path,
        replacement: Path,
        backup: Path,
    ) -> None:
        os.replace(destination, backup)
        os.replace(replacement, destination)
        handle = destination.open("r+b")
        handle.write(b"concurrent user edit")
        handle.flush()
        writer_handles.append(handle)

    monkeypatch.setattr(
        publisher,
        "_replace_file_with_backup",
        replace_then_open_candidate,
    )

    try:
        with pytest.raises(
            _PreservePublicationArtifacts,
            match="canonical could not be locked to finalize publication",
        ):
            _replace_canonical_staging(
                canonical,
                staging,
                expected_source_sha256=expected_source,
                staging_sha256=staging_sha,
            )
    finally:
        for handle in writer_handles:
            handle.close()

    assert canonical.read_bytes() == b"concurrent user edit"
    displaced = list(tmp_path.glob("*.displaced-*.xlsx"))
    assert len(displaced) == 1
    assert displaced[0].read_bytes() == b"original"


def test_partial_replacefilew_failure_restores_displaced_source(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "canonical.xlsx"
    staging = tmp_path / "staging.xlsx"
    canonical.write_bytes(b"original")
    staging.write_bytes(b"product candidate")
    expected_source = _sha256(canonical)
    staging_sha = _sha256(staging)
    monkeypatch.setattr(publisher, "_canonical_write_guard", lambda _path: nullcontext())

    def partial_failure(destination: Path, replacement: Path, backup: Path) -> None:
        os.replace(destination, backup)
        raise OSError(1177, "unable to move replacement")

    monkeypatch.setattr(publisher, "_replace_file_with_backup", partial_failure)

    with pytest.raises(OSError, match="unable to move replacement"):
        _replace_canonical_staging(
            canonical,
            staging,
            expected_source_sha256=expected_source,
            staging_sha256=staging_sha,
        )

    assert canonical.read_bytes() == b"original"
    assert staging.exists()
    assert not list(tmp_path.glob("*.displaced-*.xlsx"))


def test_partial_replacefilew_recovery_failure_preserves_all_files(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "canonical.xlsx"
    staging = tmp_path / "staging.xlsx"
    canonical.write_bytes(b"original")
    staging.write_bytes(b"product candidate")
    expected_source = _sha256(canonical)
    staging_sha = _sha256(staging)
    monkeypatch.setattr(publisher, "_canonical_write_guard", lambda _path: nullcontext())

    def partial_failure_and_recreate_path(destination: Path, replacement: Path, backup: Path) -> None:
        os.replace(destination, backup)
        destination.write_bytes(b"concurrent user file")
        raise OSError(1177, "unable to move replacement")

    monkeypatch.setattr(
        publisher,
        "_replace_file_with_backup",
        partial_failure_and_recreate_path,
    )

    with pytest.raises(
        _PreservePublicationArtifacts,
        match="canonical and displaced files need recovery",
    ):
        _replace_canonical_staging(
            canonical,
            staging,
            expected_source_sha256=expected_source,
            staging_sha256=staging_sha,
        )

    assert canonical.read_bytes() == b"concurrent user file"
    assert staging.read_bytes() == b"product candidate"
    assert len(list(tmp_path.glob("*.displaced-*.xlsx"))) == 1


def test_rollback_replacefilew_1177_restores_canonical_and_keeps_candidate(
    tmp_path: Path,
    monkeypatch,
):
    canonical = tmp_path / "canonical.xlsx"
    staging = tmp_path / "staging.xlsx"
    canonical.write_bytes(b"original")
    staging.write_bytes(b"product candidate")
    expected_source = _sha256(canonical)
    staging_sha = _sha256(staging)
    calls = 0

    def simulate_replacement_and_partial_rollback(
        destination: Path,
        replacement: Path,
        backup: Path,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            destination.write_bytes(b"concurrent user version")
            os.replace(destination, backup)
            os.replace(replacement, destination)
            return
        os.replace(destination, backup)
        raise OSError(1177, "unable to move replacement")

    monkeypatch.setattr(publisher, "_canonical_write_guard", lambda _path: nullcontext())
    monkeypatch.setattr(
        publisher,
        "_replace_file_with_backup",
        simulate_replacement_and_partial_rollback,
    )

    with pytest.raises(ValueError, match="concurrent version restored"):
        _replace_canonical_staging(
            canonical,
            staging,
            expected_source_sha256=expected_source,
            staging_sha256=staging_sha,
        )

    assert canonical.read_bytes() == b"concurrent user version"
    assert not staging.exists()
    assert not list(tmp_path.glob("*.displaced-*.xlsx"))
    recovery_candidates = list(tmp_path.glob("*.rollback-*.xlsx"))
    assert len(recovery_candidates) == 1
    assert recovery_candidates[0].read_bytes() == b"product candidate"

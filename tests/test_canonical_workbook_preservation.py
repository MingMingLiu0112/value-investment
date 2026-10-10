from __future__ import annotations

from contextlib import nullcontext
import json
import shutil
import os
import zipfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
import pytest

from scripts.current.publish_product_workbench_to_canonical import (
    _PreservePublicationArtifacts,
    _assert_canonical_source_unchanged,
    _assert_retained,
    _hide_legacy_sheets,
    _project_staging_directory,
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
    sheet["B1"] = "数值"
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
    table = Table(displayName="ManualTable", ref="A1:B2")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)
    workbook.create_named_range("manual_input", sheet, "A1")
    workbook.save(path)


def test_protected_research_preview_retains_manual_state_without_publication(tmp_path):
    from test_product_workbench_read_model import _payload
    from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
    canonical = tmp_path / 'canonical.xlsx'
    _workbook(canonical)
    before_hash = _sha256(canonical)
    before = _snapshot(canonical)
    output = tmp_path / 'runtime/integrated/canonical-integration-historical-preview.xlsx'
    model = product_workbench_from_payload(_payload())
    receipt = publisher.build_protected_research_preview(tmp_path, canonical, output, model)
    assert receipt['status'] == 'PREVIEW_PENDING_NATIVE_REVIEW'
    assert receipt['canonical_written'] is False
    assert _sha256(canonical) == before_hash
    _assert_retained(before, _snapshot(output))
    proof = json.loads((output.parent / 'canonical-preservation.json').read_text())
    assert proof['preserved_sheet_count'] == 1
    assert proof['source_sha256'] == before_hash
    assert proof['candidate_sha256'] == receipt['workbook_sha256']
    assert proof['strict_pit'] == 'NOT_PROVEN'
    with pytest.raises(FileExistsError):
        publisher.build_protected_research_preview(tmp_path, canonical, output, model)
    with pytest.raises(ValueError, match='runtime'):
        publisher.build_protected_research_preview(tmp_path, canonical, canonical, model)
    with pytest.raises(ValueError, match='filename'):
        publisher.build_protected_research_preview(tmp_path, canonical, tmp_path / 'runtime/current.xlsx', model)


def test_protected_research_preview_denies_mutated_retained_content(tmp_path, monkeypatch):
    from test_product_workbench_read_model import _payload
    from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
    canonical = tmp_path / 'canonical.xlsx'
    _workbook(canonical)
    before_hash = _sha256(canonical)
    output = tmp_path / 'runtime/integrated/canonical-integration-historical-preview.xlsx'
    render = publisher.apply_product_workbench_to_existing_workbook
    def changed(workbook, model):
        render(workbook, model)
        workbook['人工持仓']['A1'] = 'unintended modification'
    monkeypatch.setattr(publisher, 'apply_product_workbench_to_existing_workbook', changed)
    with pytest.raises(ValueError):
        publisher.build_protected_research_preview(tmp_path, canonical, output,
            product_workbench_from_payload(_payload()))
    assert _sha256(canonical) == before_hash
    assert not (output.parent / 'canonical-preservation.json').exists()


@pytest.mark.parametrize('publish', [False, True])
@pytest.mark.parametrize('fault', [None, 'proof_hash', 'preview_hash', 'wps', 'readability',
                                 'source_changed', 'preserved_content', 'simulation', 'count',
                                 'visual_failure', 'visual_hash', 'visual_missing',
                                 'source_receipt_missing', 'source_drift', 'boundary_elevation'])
def test_reviewed_research_publication_requires_all_proofs(tmp_path, monkeypatch, fault, publish):
    canonical = tmp_path / 'canonical.xlsx'
    _workbook(canonical)
    before = publisher._sha256(canonical)
    folder = tmp_path / 'runtime/review'
    folder.mkdir(parents=True)
    candidate = folder / 'canonical-integration-historical-preview.xlsx'
    shutil.copy2(canonical, candidate)
    book = load_workbook(candidate)
    publisher._hide_legacy_sheets(book)
    if fault == 'preserved_content': book['人工持仓']['A1'] = 'changed'
    book.save(candidate)
    book.close()
    candidate_sha = publisher._sha256(candidate)
    proof = dict(
        preservation='PASS',
        action='no_order',
        simulation_only=fault == 'simulation',
        historical_preview=True,
        canonical_touched=False,
        source_sha256=before,
        candidate_sha256='a' * 64 if fault == 'preview_hash' else candidate_sha,
        preserved_sheet_count=2 if fault == 'count' else 1,
        strict_pit='PROVEN' if fault == 'boundary_elevation' else 'NOT_PROVEN',
        current_price_bridge='ADMITTED' if fault == 'boundary_elevation' else 'NOT_ADMITTED',
    )
    proof_path = folder / 'canonical-preservation.json'
    proof_path.write_text(json.dumps(proof), encoding='utf-8')
    (folder / 'integrated-wps-verification.json').write_text(json.dumps(dict(
        readonly_open='FAIL' if fault == 'wps' else 'PASS', workbook_sha256=candidate_sha)), encoding='utf-8')
    (folder / 'readability.json').write_text(json.dumps(dict(
        status='failed' if fault == 'readability' else 'passed', workbook_sha256=candidate_sha)), encoding='utf-8')
    (folder / 'visual-review.json').write_text(json.dumps(dict(
        status='FAILED_VISUAL_REVIEW' if fault == 'visual_failure' else 'PASS',
        publication_allowed=fault != 'visual_failure', action='no_order',
        workbook_sha256='a' * 64 if fault == 'visual_hash' else candidate_sha)), encoding='utf-8')
    source_path = folder / 'source.json'
    source_path.write_text(json.dumps({'fact': 'reviewed'}), encoding='utf-8')
    source_receipt = candidate.with_name(candidate.stem + '.source-bindings.json')
    source_receipt.write_text(json.dumps(dict(
        schema_version='existing-workbench-preview-bindings-v1',
        integrated_canonical=True,
        historical_preview=True,
        canonical_written=False,
        action='no_order',
        workbook_sha256=candidate_sha,
        output_manifest_sha256=publisher._sha256(proof_path),
        research_recipe_binding={'path': source_path.relative_to(tmp_path).as_posix(),
                                 'sha256': publisher._sha256(source_path)},
    )), encoding='utf-8')
    if fault == 'source_drift':
        source_path.write_text(json.dumps({'fact': 'changed'}), encoding='utf-8')
    if fault == 'source_receipt_missing':
        source_receipt.unlink()
    if fault == 'visual_missing':
        (folder / 'visual-review.json').unlink()
    if fault == 'source_changed':
        with canonical.open('ab') as handle: handle.write(b'concurrent change')
    source_at_call = publisher._sha256(canonical)
    digest = 'a' * 64 if fault == 'proof_hash' else publisher._sha256(proof_path)
    staging = tmp_path / '.tmp'
    staging.mkdir()
    monkeypatch.setattr(publisher, '_assert_workbook_not_open', lambda path: None)
    monkeypatch.setattr(publisher, '_project_staging_directory', lambda *args, **kwargs: staging)
    def transport(canonical, staged, *, expected_source_sha256, staging_sha256, scratch_dir):
        publisher._assert_canonical_source_unchanged(canonical, expected_source_sha256)
        assert publisher._sha256(staged) == staging_sha256
        shutil.copy2(staged, canonical)
        staged.unlink()
        return publisher._sha256(canonical)
    # The Windows atomic transport has separate tests; this checks orchestration.
    monkeypatch.setattr(publisher, '_replace_canonical_staging', transport)
    if fault:
        with pytest.raises(ValueError):
            publisher._reviewed_research_publication(tmp_path, canonical, folder, digest, publish=publish)
    else:
        receipt = publisher._reviewed_research_publication(tmp_path, canonical, folder, digest, publish=publish)
        assert receipt['status'] == ('PUBLISHED_PENDING_WPS_VERIFICATION' if publish else 'VERIFIED_RESEARCH_PREVIEW_ONLY')
        assert receipt['canonical_written'] is publish
        assert receipt['current_price_bridge'] == 'NOT_ADMITTED'
        assert receipt['action'] == 'no_order'
        if publish:
            assert receipt['backup_sha256'] == before
            assert publisher._sha256(tmp_path / receipt['backup']) == before
            assert publisher._sha256(canonical) == candidate_sha
            assert (tmp_path / receipt['receipt']).is_file()
    if fault or not publish:
        assert publisher._sha256(canonical) == source_at_call
        assert not (tmp_path / 'runtime/workbook-backups').exists()


def test_reviewed_source_bindings_reject_nested_closure_drift(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    nested = runtime / "nested-source.json"
    nested.write_text(json.dumps({"fact": "frozen"}), encoding="utf-8")
    closure = runtime / "closure.json"
    closure.write_text(json.dumps(dict(
        schema_version="historical-company-closure-v1",
        action="no_order",
        strict_pit_admitted=False,
        historical_execution_validated=False,
        current_research_admission="NOT_READY",
        performance_claim_allowed=False,
        source_bindings=[{
            "role": "nested",
            "path": "runtime/nested-source.json",
            "sha256": publisher._sha256(nested),
        }],
    )), encoding="utf-8")
    candidate = runtime / "candidate.xlsx"
    candidate.write_bytes(b"candidate")
    proof = runtime / "proof.json"
    proof.write_text("{}", encoding="utf-8")
    receipt = runtime / "candidate.source-bindings.json"
    receipt.write_text(json.dumps(dict(
        schema_version="existing-workbench-preview-bindings-v1",
        integrated_canonical=True,
        historical_preview=True,
        canonical_written=False,
        action="no_order",
        workbook_sha256=publisher._sha256(candidate),
        output_manifest_sha256=publisher._sha256(proof),
        historical_closure_binding={
            "path": "runtime/closure.json",
            "sha256": publisher._sha256(closure),
        },
    )), encoding="utf-8")
    nested.write_text(json.dumps({"fact": "changed"}), encoding="utf-8")
    with pytest.raises(ValueError, match="bound source hash mismatch"):
        publisher._verify_reviewed_research_source_bindings(
            tmp_path, candidate, proof, receipt
        )


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
    assert any(name.startswith("xl/tables/") for name in before["protected_ooxml_parts"])
    assert any(name.startswith("xl/comments/") for name in before["protected_ooxml_parts"])


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


def test_protected_ooxml_fails_closed_when_internal_target_is_missing(tmp_path: Path):
    path = tmp_path / "canonical.xlsx"
    _workbook(path)
    with zipfile.ZipFile(path) as source:
        entries = [(item.filename, source.read(item.filename)) for item in source.infolist()]
    damaged = tmp_path / "damaged.xlsx"
    with zipfile.ZipFile(damaged, "w", zipfile.ZIP_DEFLATED) as target:
        for name, payload in entries:
            if name.startswith("xl/comments/") and name.endswith(".xml"):
                continue
            target.writestr(name, payload)
    with pytest.raises(ValueError, match="protected OOXML relationship target is missing"):
        publisher._protected_ooxml_parts(damaged)


def test_protected_ooxml_ignores_external_relationship_targets(tmp_path: Path):
    path = tmp_path / "canonical.xlsx"
    _workbook(path)
    protected = publisher._protected_ooxml_parts(path)
    assert protected
    assert not any("https://" in name or "http://" in name for name in protected)


def test_publish_refuses_when_canonical_changes_during_staging(tmp_path: Path):
    path = tmp_path / "canonical.xlsx"
    _workbook(path)
    expected_sha256 = _sha256(path)

    workbook = load_workbook(path)
    workbook["人工持仓"]["A1"] = "用户并发修改"
    workbook.save(path)

    with pytest.raises(ValueError, match="canonical workbook changed during staging"):
        _assert_canonical_source_unchanged(path, expected_sha256)


def test_relationship_fingerprint_tracks_sheet_identity_not_position(tmp_path: Path):
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.title = "retained"
    sheet["A1"] = "source"
    sheet["A1"].hyperlink = "https://example.com/original"
    first, shifted, changed = (tmp_path / name for name in ("first.xlsx", "shifted.xlsx", "changed.xlsx"))
    book.save(first)
    book.create_sheet(publisher.WORKBOOK_SHEETS[0], index=0)
    book.save(shifted)
    assert publisher._protected_ooxml_parts(first) == publisher._protected_ooxml_parts(shifted)
    sheet["A1"].hyperlink = "https://example.com/changed"
    book.save(changed)
    assert publisher._protected_ooxml_parts(first) != publisher._protected_ooxml_parts(changed)
    book.close()


def test_publication_staging_uses_project_tmp_on_the_canonical_volume(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    canonical = tmp_path / "canonical.xlsx"
    canonical.write_bytes(b"canonical")

    staging_dir = _project_staging_directory(project_root, canonical)

    assert staging_dir == project_root / ".tmp"
    assert staging_dir.resolve().is_relative_to(project_root.resolve())


@pytest.mark.parametrize("has_local_appdata", [True, False])
def test_publication_rejects_cross_volume_before_creating_temp_files(
    tmp_path: Path, monkeypatch, has_local_appdata: bool,
):
    project_root = tmp_path / "project"
    project_root.mkdir()
    canonical = tmp_path / "canonical.xlsx"
    canonical.write_bytes(b"canonical")
    local_appdata = tmp_path / "local-appdata"
    if has_local_appdata:
        monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    else:
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(
        publisher,
        "_filesystem_device",
        lambda path: 1 if path == project_root.resolve() else 2,
    )

    with pytest.raises(RuntimeError, match="across filesystem volumes"):
        _project_staging_directory(project_root, canonical)

    assert not (project_root / ".tmp").exists()
    assert not local_appdata.exists()


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

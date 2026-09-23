from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl import Workbook
import pytest


ROOT = Path(__file__).resolve().parents[1]
BUILDER_SPEC = importlib.util.spec_from_file_location(
    "m7_workbench_candidate_builder",
    ROOT / "scripts" / "build_m7_workbench_candidate.py",
)
BUILDER = importlib.util.module_from_spec(BUILDER_SPEC)
BUILDER_SPEC.loader.exec_module(BUILDER)

STAGE_SPEC = importlib.util.spec_from_file_location(
    "stage_frontend_package",
    ROOT / "scripts" / "stage_frontend_package.py",
)
STAGE = importlib.util.module_from_spec(STAGE_SPEC)
STAGE_SPEC.loader.exec_module(STAGE)


GENERATED_AT = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_workbook(path: Path, sheet_names: tuple[str, ...]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name in sheet_names:
        sheet = workbook.create_sheet(name)
        sheet["A1"] = name
        sheet["A2"] = "protected read model"
    workbook.save(path)


def _specs(base: Path, addons: tuple[Path, ...], canonical: Path) -> list[dict]:
    risk, event = addons
    return [
        {
            "id": "m4_portfolio_risk",
            "path": risk,
            "sha256": _digest(risk),
            "prefix": "M4风险_",
            "group": "M4组合风险",
            "overview_sheet": "M4风险_00_组合风险",
        },
        {
            "id": "m5_event_infrastructure",
            "path": event,
            "sha256": _digest(event),
            "prefix": "M5事件_",
            "group": "M5事件监控",
            "overview_sheet": "M5事件_00_总览",
        },
    ]


def _synthetic_project(tmp_path: Path):
    base = tmp_path / "base.xlsx"
    risk = tmp_path / "risk.xlsx"
    event = tmp_path / "event.xlsx"
    canonical = tmp_path / "canonical.xlsx"
    _write_workbook(base, ("00_历史链", "00_决策复核", "00_投资工作台"))
    _write_workbook(risk, ("00_组合风险", "01_持仓与集中度"))
    _write_workbook(event, ("00_总览",))
    _write_workbook(canonical, ("canonical",))
    return base, risk, event, canonical


def test_builder_overlays_renamed_layers_with_overview(tmp_path: Path):
    base, risk, event, canonical = _synthetic_project(tmp_path)
    output = tmp_path / "m7.xlsx"
    manifest = BUILDER.build_candidate(
        base=base,
        canonical=canonical,
        output=output,
        expected_base_sha256=_digest(base),
        expected_canonical_sha256=_digest(canonical),
        addon_specs=tuple(_specs(base, (risk, event), canonical)),
        generated_at=GENERATED_AT,
        project_root=tmp_path,
    )

    assert manifest["action"] == "no_order"
    assert manifest["status"] == "candidate_verified_not_published"
    assert manifest["candidate_sha256"] == _digest(output)
    assert manifest["sheet_count"] == 7
    assert manifest["final_sheet_order"] == [
        "00_M7总览",
        "M4风险_00_组合风险",
        "M4风险_01_持仓与集中度",
        "M5事件_00_总览",
        "00_历史链",
        "00_决策复核",
        "00_投资工作台",
    ]
    assert manifest["final_original_sheets_preserved"] == 6
    assert manifest["layers"][0]["id"] == "m4_portfolio_risk"
    assert manifest["layers"][1]["id"] == "m5_event_infrastructure"

    with ZipFile(output) as package:
        _, sheets = STAGE.sheets(package)
        overview_path = sheets[0][1]
        overview_xml = package.read(overview_path).decode("utf-8")
        rel_path = (
            overview_path.rsplit("/", 1)[0]
            + "/_rels/"
            + overview_path.rsplit("/", 1)[1]
            + ".rels"
        )
        relationships = ET.fromstring(package.read(rel_path))
        hyperlink_targets = {
            item.get("Target") for item in relationships if item.get("TargetMode") == "External"
        }
        assert "'M4风险_00_组合风险'!A1" in hyperlink_targets
        assert "'M5事件_00_总览'!A1" in hyperlink_targets
    for forbidden in BUILDER.FORBIDDEN_OVERVIEW_TEXT:
        assert forbidden not in overview_xml

    manifest_path = output.with_name(output.stem + ".candidate.manifest.json")
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["candidate_sha256"] == manifest["candidate_sha256"]


def test_builder_is_deterministic_and_never_overwrites(tmp_path: Path):
    base, risk, event, canonical = _synthetic_project(tmp_path)
    first_output = tmp_path / "first.xlsx"
    second_output = tmp_path / "second.xlsx"
    specs = tuple(_specs(base, (risk, event), canonical))

    first = BUILDER.build_candidate(
        base=base,
        canonical=canonical,
        output=first_output,
        expected_base_sha256=_digest(base),
        expected_canonical_sha256=_digest(canonical),
        addon_specs=specs,
        generated_at=GENERATED_AT,
        project_root=tmp_path,
    )
    second = BUILDER.build_candidate(
        base=base,
        canonical=canonical,
        output=second_output,
        expected_base_sha256=_digest(base),
        expected_canonical_sha256=_digest(canonical),
        addon_specs=specs,
        generated_at=GENERATED_AT,
        project_root=tmp_path,
    )

    assert _digest(first_output) == _digest(second_output)
    assert first["candidate_sha256"] == second["candidate_sha256"]
    with pytest.raises(ValueError, match="already exists"):
        BUILDER.build_candidate(
            base=base,
            canonical=canonical,
            output=first_output,
            expected_base_sha256=_digest(base),
            expected_canonical_sha256=_digest(canonical),
            addon_specs=specs,
            generated_at=GENERATED_AT,
            project_root=tmp_path,
        )


def test_builder_rejects_changed_sources(tmp_path: Path):
    base, risk, event, canonical = _synthetic_project(tmp_path)
    with pytest.raises(ValueError, match="M7 base changed"):
        BUILDER.build_candidate(
            base=base,
            canonical=canonical,
            output=tmp_path / "m7.xlsx",
            expected_base_sha256="0" * 64,
            expected_canonical_sha256=_digest(canonical),
            addon_specs=tuple(_specs(base, (risk, event), canonical)),
            generated_at=GENERATED_AT,
            project_root=tmp_path,
        )


def test_overview_rejects_forbidden_text(tmp_path: Path):
    output = tmp_path / "overview.xlsx"
    with pytest.raises(ValueError, match="forbidden decision presentation text"):
        BUILDER.build_overview(
            output,
            generated_at=GENERATED_AT,
            destinations=(("买入", "目标页"),),
        )

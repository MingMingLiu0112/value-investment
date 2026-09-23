"""Versioned acceptance audit for the M3 history overlay workbook.

The auditor proves that the five-page simulated history chain is appended to
the already protected M3 decision-review candidate without replacing any
source sheet, has a pinned simulated-only namespace, keeps the decision page
fail closed, and has a matching read-only WPS receipt. It never publishes the
candidate or converts a history demonstration into a portfolio or order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping
from zipfile import ZipFile

from openpyxl import load_workbook

from .investment_decision import ACTION_NO_ORDER
from .m3_decision_acceptance_audit import (
    DONE,
    FAILED,
    PARTIAL,
    PENDING_CI,
    PENDING_HUMAN_REVIEW,
    _check,
    _criterion,
    _criterion_status,
    _digest,
    _load_json,
    _require_sha256,
)


SCHEMA_VERSION = "m3-history-original-workbook-acceptance-audit-v1"
RULE_VERSION = "m3-history-original-workbook-v1"
TARGET_SHEET = "00_决策复核"
HISTORY_SHEETS = (
    "00_历史链",
    "01_原Entry",
    "02_决策日志",
    "03_一致性复核",
    "04_来源哈希",
)

EXPECTED_SOURCE_SHA256 = (
    "ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3"
)
EXPECTED_ADDON_SHA256 = (
    "5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0"
)
EXPECTED_HISTORY_INPUT_SHA256 = (
    "4969a5d3b8bb80dfa743807053a75bc4e1595a5081953ecff1a83ba56c8f057c"
)
EXPECTED_CANDIDATE_SHA256 = (
    "67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d"
)
EXPECTED_MANIFEST_SHA256 = (
    "d8da5fc558847e36b2b76f9faf0a008bfac9c8c3b80ccb7a187eb46d0cb4b3ab"
)
EXPECTED_WPS_RECEIPT_SHA256 = (
    "b44ee546ad89eafd16b84b0766bd91fae16ee0fb1ae38620ec5ed1e330ba7bc8"
)
EXPECTED_CANONICAL_SHA256 = (
    "64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911"
)

FORBIDDEN_DECISION_TEXT = (
    "买入",
    "加仓",
    "减仓",
    "目标仓位",
    "BUY",
    "ADD",
)
FORBIDDEN_HISTORY_PRESENTATION = ("目标仓位", "下单", "自动卖出")
EXPECTED_SHEET_COUNT = 60
EXPECTED_NEW_SHEETS = 5
EXPECTED_SOURCE_SHEETS = 55
EXPECTED_UNCHANGED_PARTS = 111
TEST_FILES = (
    "tests/test_m3_history_read_model.py",
    "tests/test_stage_frontend_package.py",
    "tests/test_m3_history_original_workbook.py",
)

ROOT = Path(__file__).resolve().parents[2]
STAGE_FRONTEND = runpy.run_path(
    str(ROOT / "scripts" / "stage_frontend_package.py"),
    run_name="stage_frontend_package",
)


@dataclass(frozen=True)
class M3HistoryOriginalWorkbookAcceptanceSpec:
    source_path: Path
    source_sha256: str
    addon_path: Path
    addon_sha256: str
    history_input_path: Path
    history_input_sha256: str
    candidate_path: Path
    candidate_sha256: str
    manifest_path: Path
    manifest_sha256: str
    generated_at: datetime
    wps_candidate_path: Path
    wps_receipt_path: Path
    wps_receipt_sha256: str
    canonical_wps_path: Path
    canonical_sha256: str
    expected_sheet_count: int = EXPECTED_SHEET_COUNT
    expected_new_sheets: int = EXPECTED_NEW_SHEETS
    expected_source_sheets: int = EXPECTED_SOURCE_SHEETS
    expected_unchanged_parts: int = EXPECTED_UNCHANGED_PARTS

    def __post_init__(self) -> None:
        for field in (
            "source_sha256",
            "addon_sha256",
            "history_input_sha256",
            "candidate_sha256",
            "manifest_sha256",
            "wps_receipt_sha256",
            "canonical_sha256",
        ):
            object.__setattr__(
                self,
                field,
                _require_sha256(getattr(self, field), field),
            )
        if self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        if min(
            self.expected_sheet_count,
            self.expected_new_sheets,
            self.expected_source_sheets,
            self.expected_unchanged_parts,
        ) < 0:
            raise ValueError("expected workbook counts cannot be negative")


def _inside(root: Path, value: Path, field: str) -> Path:
    target = value.resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"{field} escapes the audit root")
    return target


def _verify_pinned_bytes(path: Path, expected: str, label: str) -> Path:
    expected = _require_sha256(expected, label)
    if not path.is_file():
        raise ValueError(f"{label} is not a file: {path}")
    actual = _digest(path)
    if actual != expected:
        raise ValueError(f"{label} changed: expected {expected}, got {actual}")
    return path


def _verify_pinned_outside(path: Path, expected: str, label: str) -> Path:
    resolved = path.resolve()
    if "WPSDrive" not in resolved.parts:
        raise ValueError(f"{label} is not a WPS cloud path")
    return _verify_pinned_bytes(resolved, expected, label)


def _run_offline_tests(root: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "-q",
            "--basetemp=runtime/pytest-tmp-m3-history-original-audit",
            *(str(root / item) for item in TEST_FILES),
        ],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    passed_match = re.search(r"(\d+) passed", result.stdout or "")
    skipped_match = re.search(r"(\d+) skipped", result.stdout or "")
    return {
        "passed": result.returncode == 0,
        "passed_count": int(passed_match.group(1)) if passed_match else 0,
        "skipped_count": int(skipped_match.group(1)) if skipped_match else 0,
        "returncode": result.returncode,
        "output_tail": "\n".join((result.stdout or "").splitlines()[-8:]),
    }


def _hoc1_identity(
    root: Path,
    spec: M3HistoryOriginalWorkbookAcceptanceSpec,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check("M3 history source hash matches", _digest(spec.source_path) == spec.source_sha256),
        _check("M3 history addon hash matches", _digest(spec.addon_path) == spec.addon_sha256),
        _check("simulated history input hash matches", _digest(spec.history_input_path) == spec.history_input_sha256),
        _check("M3 history overlay hash matches", _digest(spec.candidate_path) == spec.candidate_sha256),
        _check("candidate manifest hash matches", _digest(spec.manifest_path) == spec.manifest_sha256),
        _check("manifest remains candidate_verified_not_published", manifest.get("status") == "candidate_verified_not_published"),
        _check("manifest remains action=no_order", manifest.get("action") == ACTION_NO_ORDER),
        _check("manifest binds the candidate hash", manifest.get("candidate_sha256") == spec.candidate_sha256),
        _check("manifest binds the source and addon hashes", manifest.get("source_sha256") == spec.source_sha256 and manifest.get("addon_sha256") == spec.addon_sha256),
        _check("manifest reports the simulated namespace", manifest.get("namespace") == "simulated"),
        _check("manifest reports 60 sheets", manifest.get("sheet_count") == spec.expected_sheet_count),
        _check("manifest reports exactly five history pages", manifest.get("new_sheets") == list(HISTORY_SHEETS)),
        _check("manifest reports all 55 source sheets preserved", manifest.get("original_sheets_preserved") == spec.expected_source_sheets),
    ]
    return _criterion(
        _criterion_status(checks),
        checks,
        evidence={
            "candidate_sha256": spec.candidate_sha256,
            "sheet_count": spec.expected_sheet_count,
        },
    )


def _hoc2_history_simulated_boundary(
    root: Path,
    spec: M3HistoryOriginalWorkbookAcceptanceSpec,
) -> dict[str, Any]:
    workbook = load_workbook(spec.candidate_path, read_only=True, data_only=False)
    try:
        if workbook.sheetnames[: len(HISTORY_SHEETS)] != list(HISTORY_SHEETS):
            raise ValueError("M3 history pages are missing or out of order")
        values = []
        for name in HISTORY_SHEETS:
            for row in workbook[name].iter_rows(values_only=True):
                values.extend(item for item in row if item is not None)
        text = "\n".join(str(item) for item in values)
        overview = workbook[HISTORY_SHEETS[0]]
        row_five = [
            overview.cell(row=5, column=column).value
            for column in range(1, 10)
        ]
        forbidden = [item for item in FORBIDDEN_HISTORY_PRESENTATION if item in text]
        checks = [
            _check("history overview has the protected title", row_five[0] == "600887" and any(item == "M3 论点连续性历史链" for item in values)),
            _check("history pages keep the simulated boundary", "模拟演示链路" in text),
            _check("history overview is namespace=simulated", row_five[2] == "模拟"),
            _check("history overview uses simulated entry type", row_five[3] == "模拟"),
            _check("history overview keeps the latest simulated decision", row_five[6] == "确认减仓"),
            _check("history overview keeps consistency broken", row_five[7] == "已破坏"),
            _check("history overview remains no_order", row_five[8] == ACTION_NO_ORDER),
            _check("history pages omit portfolio and order presentation", not forbidden),
        ]
        return _criterion(
            _criterion_status(checks),
            checks,
            evidence={"history_sheets": list(HISTORY_SHEETS), "forbidden_text_found": forbidden},
        )
    finally:
        workbook.close()


def _hoc3_structure(root: Path, spec: M3HistoryOriginalWorkbookAcceptanceSpec) -> dict[str, Any]:
    modified_source_parts = {
        "[Content_Types].xml",
        "xl/_rels/workbook.xml.rels",
        "xl/styles.xml",
        "xl/workbook.xml",
    }
    with ZipFile(spec.source_path) as source, ZipFile(spec.candidate_path) as candidate:
        _, existing = STAGE_FRONTEND["sheets"](source)
        _, verified = STAGE_FRONTEND["sheets"](candidate)
        existing_names = [sheet.get("name") for sheet, _ in existing]
        verified_names = [sheet.get("name") for sheet, _ in verified]
        unchanged = [path for path in source.namelist() if path not in modified_source_parts]
        unchanged_ok = all(candidate.read(path) == source.read(path) for path in unchanged)
        checks = [
            _check("candidate ZIP is structurally valid", candidate.testzip() is None),
            _check("candidate has the expected 60 sheets", len(verified) == spec.expected_sheet_count),
            _check("five history pages precede the source workbook", verified_names[: len(HISTORY_SHEETS)] == list(HISTORY_SHEETS)),
            _check("all source sheets follow in original order", verified_names[len(HISTORY_SHEETS) :] == existing_names),
            _check("all source sheets are preserved", set(existing_names).issubset(set(verified_names))),
            _check("expected source parts are byte-identical", len(unchanged) == spec.expected_unchanged_parts and unchanged_ok),
        ]
    STAGE_FRONTEND["validate_package_relationships"](spec.candidate_path)
    return _criterion(
        _criterion_status(checks),
        checks,
        evidence={
            "sheet_count": spec.expected_sheet_count,
            "source_sheets": spec.expected_source_sheets,
            "unchanged_parts": spec.expected_unchanged_parts,
        },
    )


def _hoc4_decision_fail_closed(root: Path, spec: M3HistoryOriginalWorkbookAcceptanceSpec) -> dict[str, Any]:
    workbook = load_workbook(spec.candidate_path, read_only=True, data_only=False)
    try:
        if TARGET_SHEET not in workbook.sheetnames:
            raise ValueError("M3 decision sheet is missing")
        sheet = workbook[TARGET_SHEET]
        values = [
            value
            for row in sheet.iter_rows(values_only=True)
            for value in row
            if value is not None
        ]
        text = "\n".join(str(value) for value in values)
        forbidden = [item for item in FORBIDDEN_DECISION_TEXT if item in text]
        has_formula = any(isinstance(value, str) and value.startswith("=") for value in values)
        checks = [
            _check("decision sheet title is the negative-only M3 title", values and str(values[0]) == "决策复核（M3 非个人化负向卡）"),
            _check("decision sheet contains all three symbols", all(symbol in text for symbol in ("000651", "600741", "600887"))),
            _check("decision sheet preserves no_order", "action=no_order" in text),
            _check("decision sheet preserves Checkpoint B pending", "Checkpoint B：未完成" in text),
            _check("decision sheet has no formulas", not has_formula),
            _check("decision sheet has no forbidden order text", not forbidden),
        ]
        return _criterion(
            _criterion_status(checks),
            checks,
            evidence={"row_values": len(values), "forbidden_text_found": forbidden},
        )
    finally:
        workbook.close()


def _hoc5_wps_boundary(root: Path, spec: M3HistoryOriginalWorkbookAcceptanceSpec) -> dict[str, Any]:
    receipt_path = _inside(root, spec.wps_receipt_path, "wps_receipt_path")
    receipt = _load_json(receipt_path)
    wps_candidate = spec.wps_candidate_path.resolve()
    canonical = spec.canonical_wps_path.resolve()
    checks = [
        _check("WPS cloud candidate is byte-identical", _digest(wps_candidate) == spec.candidate_sha256),
        _check("WPS receipt hash is pinned", _digest(receipt_path) == spec.wps_receipt_sha256),
        _check("WPS receipt status is passed", receipt.get("status") == "passed"),
        _check("WPS receipt is a protected history overlay", receipt.get("mode") == "protected_history_overlay_candidate"),
        _check("WPS receipt binds the candidate hash", receipt.get("sha256") == spec.candidate_sha256),
        _check("WPS receipt reports 60 sheets", receipt.get("sheets") == spec.expected_sheet_count),
        _check("WPS receipt reports all five history pages", receipt.get("history_sheets") == list(HISTORY_SHEETS)),
        _check("WPS receipt reports the decision page", receipt.get("target_sheet") == TARGET_SHEET),
        _check("WPS receipt reports 55 preserved source sheets", receipt.get("source_sheets_preserved") == spec.expected_source_sheets),
        _check("WPS receipt remains simulated no_order", receipt.get("namespace") == "simulated" and receipt.get("action") == ACTION_NO_ORDER),
        _check("WPS canonical workbook is unchanged", _digest(canonical) == spec.canonical_sha256),
    ]
    return _criterion(
        _criterion_status(checks),
        checks,
        evidence={"wps_candidate": str(wps_candidate), "canonical_sha256": spec.canonical_sha256},
    )


def _hoc6_regression(
    test_evidence: Mapping[str, Any] | None,
    ci_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    checks = [
        _check("offline M3 history regression passes", bool(test_evidence and test_evidence.get("passed"))),
        _check("GitHub core research gate succeeds", bool(ci_evidence and ci_evidence.get("status") == "success")),
    ]
    status = DONE if all(item["passed"] for item in checks) else (
        PENDING_CI if ci_evidence is None else PARTIAL
    )
    return _criterion(
        status,
        checks,
        evidence={"test_result": dict(test_evidence or {}), "ci": dict(ci_evidence or {})},
    )


def _hoc7_human_review() -> dict[str, Any]:
    return _criterion(
        PENDING_HUMAN_REVIEW,
        [
            _check("no real Entry, Journal, Consistency or portfolio result was invented", True),
            _check("no personal account or IPS was read", True),
            _check("candidate was not published to canonical", True),
        ],
        human_review=(
            "在 WPS 中打开叠加候选，先看 00_历史链，确认示例链路明确标注为模拟。",
            "再查看 00_决策复核，确认三张卡仍为研究证据不足，未因历史演示被改写。",
            "确认正式 canonical 工作簿未被本候选覆盖，Checkpoint B 仍由用户人工验收。",
        ),
    )


def audit(
    root: Path,
    spec: M3HistoryOriginalWorkbookAcceptanceSpec,
    *,
    ci_evidence: Mapping[str, Any] | None = None,
    test_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    source_path = _inside(root, spec.source_path, "source_path")
    addon_path = _inside(root, spec.addon_path, "addon_path")
    history_input_path = _inside(root, spec.history_input_path, "history_input_path")
    candidate_path = _inside(root, spec.candidate_path, "candidate_path")
    manifest_path = _inside(root, spec.manifest_path, "manifest_path")
    _verify_pinned_bytes(source_path, spec.source_sha256, "M3 history source")
    _verify_pinned_bytes(addon_path, spec.addon_sha256, "M3 history addon")
    _verify_pinned_bytes(history_input_path, spec.history_input_sha256, "M3 simulated history input")
    _verify_pinned_bytes(candidate_path, spec.candidate_sha256, "M3 history overlay candidate")
    _verify_pinned_bytes(manifest_path, spec.manifest_sha256, "M3 history overlay manifest")
    _verify_pinned_outside(spec.wps_candidate_path, spec.candidate_sha256, "WPS history overlay copy")
    _verify_pinned_outside(spec.canonical_wps_path, spec.canonical_sha256, "WPS canonical workbook")
    manifest = _load_json(manifest_path)
    criteria = {
        "hoc1_identity_and_manifest": _hoc1_identity(root, spec, manifest),
        "hoc2_history_simulated_boundary": _hoc2_history_simulated_boundary(root, spec),
        "hoc3_original_workbook_structure": _hoc3_structure(root, spec),
        "hoc4_decision_sheet_fail_closed": _hoc4_decision_fail_closed(root, spec),
        "hoc5_wps_and_canonical_boundary": _hoc5_wps_boundary(root, spec),
        "hoc6_offline_regression_and_ci": _hoc6_regression(test_evidence, ci_evidence),
        "hoc7_human_checkpoint_review": _hoc7_human_review(),
    }
    partial = [key for key, item in criteria.items() if item["status"] in {PARTIAL, FAILED}]
    pending_ci = [key for key, item in criteria.items() if item["status"] == PENDING_CI]
    if partial:
        status = PARTIAL
    elif pending_ci:
        status = PENDING_CI
    else:
        status = PENDING_HUMAN_REVIEW
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": ACTION_NO_ORDER,
        "status": status,
        "criteria": criteria,
        "summary": {
            "done": [key for key, item in criteria.items() if item["status"] == DONE],
            "partial": partial,
            "pending_ci": pending_ci,
            "pending_human_review": [key for key, item in criteria.items() if item["status"] == PENDING_HUMAN_REVIEW],
            "human_review_items": [item for criterion in criteria.values() for item in criterion.get("human_review") or []],
            "next_action": "用户复核 M3 历史链叠加候选并保留 Checkpoint B 人工边界",
        },
        "blockers": [blocker for criterion in criteria.values() for blocker in criterion.get("blockers") or []],
    }


def write_receipt(receipt: Mapping[str, Any], *, root: Path) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / "runtime" / f"m3-history-original-workbook-audit-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    evidence = target / "receipt.json"
    evidence.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    digest = _digest(evidence)
    pointer = {"path": str(target.relative_to(root)), "sha256": digest}
    (root / "runtime/m3-history-original-workbook-audit-latest.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "receipt_path": str(evidence.relative_to(root)),
        "pointer_path": "runtime/m3-history-original-workbook-audit-latest.json",
        "receipt_sha256": digest,
    }

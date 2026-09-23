"""Versioned acceptance audit for the M3 original-workbook decision candidate.

This auditor proves that the protected M3 candidate is byte-pinned, was built
from the frozen negative-only M1 input, replaces only the derived decision
sheet, and has a matching read-only WPS check. It never publishes the candidate
or converts a review into a decision, portfolio result or order.
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
from typing import Any, Mapping, Sequence
from zipfile import ZipFile

from openpyxl import load_workbook

from .investment_decision import ACTION_NO_ORDER
from .m1_sample_preregistration import load_m1_sample_preregistration
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
from .m3_decision_application import (
    build_nonpersonal_decision_card_collection,
    load_integrated_runs,
)


SCHEMA_VERSION = "m3-original-workbook-acceptance-audit-v1"
RULE_VERSION = "m3-original-workbook-acceptance-v1"
TARGET_SHEET = "00_决策复核"

EXPECTED_SOURCE_SHA256 = (
    "64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911"
)
EXPECTED_CANDIDATE_SHA256 = (
    "ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3"
)
EXPECTED_MANIFEST_SHA256 = (
    "192dd480b7aa8ef6299e7095014d2ca5a6becca04b4c5a42c1c6c95b375b41b4"
)
EXPECTED_INPUT_SHA256 = (
    "b1123333f2b4caa6beae16102bdca613b0894ad7fb72aa17329e838cd32b0459"
)
EXPECTED_PREREGISTRATION_SHA256 = (
    "5b7df98f8781080f66e5e053b8d0015f0b7c7eee9e27e8a10f7b0fe7990ab5b1"
)
EXPECTED_WPS_RECEIPT_SHA256 = (
    "3f650e05f92f24ec94dfa65eb8b97af041bf309ac1136a84001b2f54eff8a763"
)

FORBIDDEN_TEXT = (
    "买入",
    "加仓",
    "减仓",
    "目标仓位",
    "BUY",
    "ADD",
)
EXPECTED_SHEET_COUNT = 55
EXPECTED_ORIGINAL_SHEETS = 54
EXPECTED_DERIVED_SHEETS = 1
EXPECTED_UNCHANGED_PARTS = 113
TEST_FILES = (
    "tests/test_m3_decision_review_sheet.py",
    "tests/test_stage_frontend_replace_sheet.py",
    "tests/test_m3_original_workbook_acceptance_audit.py",
)

ROOT = Path(__file__).resolve().parents[2]
STAGE_FRONTEND = runpy.run_path(
    str(ROOT / "scripts" / "stage_frontend_package.py"),
    run_name="stage_frontend_package",
)


@dataclass(frozen=True)
class M3OriginalWorkbookAcceptanceSpec:
    source_path: Path
    source_sha256: str
    candidate_path: Path
    candidate_sha256: str
    manifest_path: Path
    manifest_sha256: str
    input_path: Path
    input_sha256: str
    preregistration_path: Path
    preregistration_sha256: str
    generated_at: datetime
    wps_candidate_path: Path
    wps_receipt_path: Path
    wps_receipt_sha256: str
    canonical_wps_path: Path
    canonical_sha256: str
    expected_sheet_count: int = EXPECTED_SHEET_COUNT
    expected_original_sheets: int = EXPECTED_ORIGINAL_SHEETS
    expected_unchanged_parts: int = EXPECTED_UNCHANGED_PARTS

    def __post_init__(self) -> None:
        for field in (
            "source_sha256",
            "candidate_sha256",
            "manifest_sha256",
            "input_sha256",
            "preregistration_sha256",
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
            self.expected_original_sheets,
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
    """Pin a deliberately external WPS path without allowing arbitrary paths."""
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
            "--basetemp=runtime/pytest-tmp-m3-original-audit",
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


def _owc1_identity(
    root: Path,
    spec: M3OriginalWorkbookAcceptanceSpec,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check("canonical source hash matches", _digest(spec.source_path) == spec.source_sha256),
        _check("M3 candidate hash matches", _digest(spec.candidate_path) == spec.candidate_sha256),
        _check("candidate manifest hash matches", _digest(spec.manifest_path) == spec.manifest_sha256),
        _check("frozen M1 input hash matches", _digest(spec.input_path) == spec.input_sha256),
        _check("M1 preregistration hash matches", _digest(spec.preregistration_path) == spec.preregistration_sha256),
        _check("manifest remains candidate_verified_not_published", manifest.get("status") == "candidate_verified_not_published"),
        _check("manifest remains action=no_order", manifest.get("action") == ACTION_NO_ORDER),
        _check("manifest binds the candidate hash", manifest.get("candidate_sha256") == spec.candidate_sha256),
        _check("manifest binds the source hash", manifest.get("source_sha256") == spec.source_sha256),
        _check("manifest reports three cards", manifest.get("card_count") == 3),
        _check("manifest reports zero positive reviews", manifest.get("positive_review_count") == 0),
    ]
    return _criterion(
        _criterion_status(checks),
        checks,
        evidence={"source_sha256": spec.source_sha256, "candidate_sha256": spec.candidate_sha256},
    )


def _owc2_negative_cards(
    root: Path,
    spec: M3OriginalWorkbookAcceptanceSpec,
) -> dict[str, Any]:
    payload, _ = load_integrated_runs(root, spec.input_path)
    names = {
        entry.symbol: entry.name
        for entry in load_m1_sample_preregistration(spec.preregistration_path).companies
    }
    collection = build_nonpersonal_decision_card_collection(
        payload,
        generated_at=spec.generated_at,
        source_run_id=spec.input_path.parent.name,
    )
    expected_symbols = {"000651", "600741", "600887"}
    checks = [
        _check("replay contains exactly three cards", len(collection.cards) == 3),
        _check("replay covers the three frozen companies", {item.symbol for item in collection.cards} == expected_symbols),
        _check("no positive review is emitted", sum(item.is_positive_review() for item in collection.cards) == 0),
        _check("every card requires human review", all(item.requires_human_review for item in collection.cards)),
        _check("every card remains no_order", all(item.action == ACTION_NO_ORDER for item in collection.cards)),
        _check("all security names match preregistration", all(names.get(item.symbol) for item in collection.cards)),
    ]
    return _criterion(
        _criterion_status(checks),
        checks,
        evidence={
            "symbols": [item.symbol for item in collection.cards],
            "positive_review_count": sum(item.is_positive_review() for item in collection.cards),
        },
    )


def _owc3_structure(root: Path, spec: M3OriginalWorkbookAcceptanceSpec) -> dict[str, Any]:
    replacements = set()
    with ZipFile(spec.source_path) as source, ZipFile(spec.candidate_path) as candidate:
        _, existing = STAGE_FRONTEND["sheets"](source)
        _, verified = STAGE_FRONTEND["sheets"](candidate)
        existing_paths = {sheet.get("name"): path for sheet, path in existing}
        verified_paths = {sheet.get("name"): path for sheet, path in verified}
        target_path = existing_paths.get(TARGET_SHEET)
        if target_path:
            replacements = {target_path, "xl/styles.xml"}
        unchanged = [
            path for path in source.namelist() if path not in replacements
        ]
        unchanged_ok = all(candidate.read(path) == source.read(path) for path in unchanged)
        checks = [
            _check("candidate ZIP is structurally valid", candidate.testzip() is None),
            _check("candidate retains the expected sheet count", len(verified) == spec.expected_sheet_count),
            _check("sheet order is unchanged", [item.get("name") for item, _ in verified] == [item.get("name") for item, _ in existing]),
            _check("derived decision sheet exists", TARGET_SHEET in verified_paths),
            _check("derived decision sheet keeps its original path", verified_paths.get(TARGET_SHEET) == target_path),
            _check("expected original sheets are preserved", len(verified) - 1 == spec.expected_original_sheets),
            _check("exactly one derived sheet is replaced", target_path is not None),
            _check("expected non-replaced ZIP parts are byte-identical", len(unchanged) == spec.expected_unchanged_parts and unchanged_ok),
        ]
    STAGE_FRONTEND["validate_package_relationships"](spec.candidate_path)
    return _criterion(
        _criterion_status(checks),
        checks,
        evidence={"sheet_count": spec.expected_sheet_count, "unchanged_parts": spec.expected_unchanged_parts},
    )


def _owc4_decision_sheet(root: Path, spec: M3OriginalWorkbookAcceptanceSpec) -> dict[str, Any]:
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
        forbidden = [item for item in FORBIDDEN_TEXT if item in text]
        has_formula = any(
            isinstance(value, str) and value.startswith("=")
            for value in values
        )
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


def _owc5_wps_boundary(root: Path, spec: M3OriginalWorkbookAcceptanceSpec) -> dict[str, Any]:
    receipt_path = _inside(root, spec.wps_receipt_path, "wps_receipt_path")
    receipt = _load_json(receipt_path)
    wps_candidate = spec.wps_candidate_path.resolve()
    canonical = spec.canonical_wps_path.resolve()
    checks = [
        _check("WPS cloud candidate is byte-identical", _digest(wps_candidate) == spec.candidate_sha256),
        _check("WPS receipt hash is pinned", _digest(receipt_path) == spec.wps_receipt_sha256),
        _check("WPS receipt status is passed", receipt.get("status") == "passed"),
        _check("WPS receipt is pre-publication", receipt.get("mode") == "pre_publication"),
        _check("WPS receipt binds the candidate hash", receipt.get("sha256") == spec.candidate_sha256),
        _check("WPS receipt reports the expected sheet count", receipt.get("sheets") == spec.expected_sheet_count),
        _check("WPS receipt reports the decision sheet", receipt.get("target_sheet") == TARGET_SHEET),
        _check("WPS receipt reports the expected unchanged parts", receipt.get("original_parts_unchanged") == spec.expected_unchanged_parts),
        _check("WPS production canonical remains unchanged", _digest(canonical) == spec.canonical_sha256),
    ]
    return _criterion(
        _criterion_status(checks),
        checks,
        evidence={
            "wps_candidate_sha256": _digest(wps_candidate),
            "wps_receipt_sha256": _digest(receipt_path),
            "canonical_sha256": _digest(canonical),
        },
    )


def _owc6_regression(test_evidence: Mapping[str, Any] | None, ci_evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    test_passed = bool(test_evidence and test_evidence.get("passed"))
    ci_passed = bool(ci_evidence and ci_evidence.get("status") == "success")
    checks = [
        _check("M3 original-workbook regression suite passed", test_passed, str(test_evidence.get("passed_count") if test_evidence else None)),
        _check("CI success is observed for the audited commit", ci_passed, str(ci_evidence.get("status") if ci_evidence else None)),
    ]
    status = DONE if all(check["passed"] for check in checks) else PENDING_CI
    return _criterion(
        status,
        checks,
        evidence={"test_result": dict(test_evidence or {}), "ci": dict(ci_evidence or {})},
    )


def _owc7_human_review() -> dict[str, Any]:
    return _criterion(
        PENDING_HUMAN_REVIEW,
        [
            _check("no Entry, Journal, Consistency or portfolio result was invented", True),
            _check("no personal account or IPS was read", True),
            _check("candidate was not published to canonical", True),
        ],
        human_review=(
            "在 WPS 中打开候选工作簿，只查看派生页 00_决策复核，确认三张卡均为研究证据不足。",
            "确认原 55 页工作簿未被本候选覆盖，正式工作簿仍是 canonical 快照。",
            "逐卡说明当前阻断、缺失输入和下一步重开触发条件，不把候选视为 Checkpoint B。",
        ),
    )


def audit(
    root: Path,
    spec: M3OriginalWorkbookAcceptanceSpec,
    *,
    ci_evidence: Mapping[str, Any] | None = None,
    test_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    source_path = _inside(root, spec.source_path, "source_path")
    candidate_path = _inside(root, spec.candidate_path, "candidate_path")
    manifest_path = _inside(root, spec.manifest_path, "manifest_path")
    input_path = _inside(root, spec.input_path, "input_path")
    preregistration_path = _inside(root, spec.preregistration_path, "preregistration_path")
    _verify_pinned_bytes(source_path, spec.source_sha256, "M3 source workbook")
    _verify_pinned_bytes(candidate_path, spec.candidate_sha256, "M3 original-workbook candidate")
    _verify_pinned_bytes(manifest_path, spec.manifest_sha256, "M3 original-workbook manifest")
    _verify_pinned_bytes(input_path, spec.input_sha256, "M3 frozen input")
    _verify_pinned_bytes(preregistration_path, spec.preregistration_sha256, "M1 preregistration")
    _verify_pinned_outside(spec.wps_candidate_path, spec.candidate_sha256, "WPS candidate copy")
    _verify_pinned_outside(spec.canonical_wps_path, spec.canonical_sha256, "WPS canonical workbook")
    manifest = _load_json(manifest_path)
    criteria = {
        "owc1_identity_and_manifest": _owc1_identity(root, spec, manifest),
        "owc2_nonpersonal_negative_card_replay": _owc2_negative_cards(root, spec),
        "owc3_original_workbook_structure": _owc3_structure(root, spec),
        "owc4_decision_sheet_fail_closed": _owc4_decision_sheet(root, spec),
        "owc5_wps_and_canonical_boundary": _owc5_wps_boundary(root, spec),
        "owc6_offline_regression_and_ci": _owc6_regression(test_evidence, ci_evidence),
        "owc7_human_checkpoint_review": _owc7_human_review(),
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
            "next_action": "用户复核 M3 原工作簿候选的决策复核页并保留 Checkpoint B 人工边界",
        },
        "blockers": [blocker for criterion in criteria.values() for blocker in criterion.get("blockers") or []],
    }


def write_receipt(receipt: Mapping[str, Any], *, root: Path) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / "runtime" / f"m3-original-workbook-audit-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    evidence = target / "receipt.json"
    evidence.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    digest = _digest(evidence)
    pointer = {"path": str(target.relative_to(root)), "sha256": digest}
    (root / "runtime/m3-original-workbook-audit-latest.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "receipt_path": str(evidence.relative_to(root)),
        "pointer_path": "runtime/m3-original-workbook-audit-latest.json",
        "receipt_sha256": digest,
    }

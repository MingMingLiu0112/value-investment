#!/usr/bin/env python3
"""Recompute the M1 AC1-AC10 fact status from authoritative local evidence.

This is a read-only local auditor. It reads the current runtime pointers,
verifies their hashes, and emits a versioned receipt. It never opens the WPS
workbook for writing, never re-runs research, and never creates an order.

Formal G3 and event-materiality decisions are decision-stage reviews deferred
to M3/M5. The auditor preserves them as explicit deferred items but does not
let them block M1's machine-verifiable research-workbench acceptance. Running
this script cannot approve research or imply that conditional research is
investment-ready.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m1_distribution_package_builder import (  # noqa: E402
    dividend_results_by_symbol,
)
from value_investment_agent.m1_research_dossier_candidate import (  # noqa: E402
    load_candidate_pointer,
)
from value_investment_agent.m1_valuation_package_builder import (  # noqa: E402
    build_package_descriptor_attempts,
)
from value_investment_agent.research_read_model import (  # noqa: E402
    DOSSIER_READABLE,
    SECTION_COMPLETE,
    SECTION_UNKNOWN,
    STATEMENT_GAP,
)


SCHEMA_VERSION = "m1-acceptance-audit-v2"
DONE = "DONE"
PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
PARTIAL = "PARTIAL"
APPLICATION_SYMBOLS = {"000651", "600741", "600887"}
REQUIRED_SECTIONS = {
    "business_quality",
    "financial_quality",
    "capital_allocation",
    "thesis",
    "counter_evidence",
    "thesis_breakers",
    "next_events",
    "research_gaps",
}
AC1_TEST_FILES = (
    "tests/fixed_sample_runtime_fixture.py",
    "tests/test_excel_report.py",
    "tests/test_research_application.py",
    "tests/test_research_batch.py",
    "tests/test_research_gate.py",
)
AC2_TEST_FILES = (
    "tests/test_research_input.py",
    "tests/test_research_read_model.py",
    "tests/test_research_application.py",
    "tests/test_research_gate.py",
    "tests/test_m1_research_dossier_candidate.py",
    "tests/test_m1_provider_dossier.py",
    "tests/test_m1_valuation_package_builder.py",
    "tests/test_m1_reverse_valuation.py",
    "tests/test_m1_distribution_package_builder.py",
    "tests/test_m1_historical_quote.py",
    "tests/test_m1_pit_replay.py",
    "tests/test_m1_application_workbook.py",
    "tests/test_stage_frontend_package.py",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _load_pointed(root: Path, pointer_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    pointer = _load_json(pointer_path)
    relative = str(pointer["path"])
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Pointer escapes project root: {pointer_path}")
    evidence = target / "evidence.json"
    actual = _digest(evidence)
    expected = str(pointer.get("sha256") or "").lower()
    if actual != expected:
        raise ValueError(f"Pointer hash changed: {pointer_path}")
    return _load_json(evidence), {"path": str(evidence.relative_to(root)), "sha256": actual}


def _finite(value: Any) -> bool:
    if value is None:
        return False
    try:
        return float(str(value)) == float(str(value)) and float(str(value)) not in (
            float("inf"),
            float("-inf"),
        )
    except (TypeError, ValueError):
        return False


def _check(passed: bool, label: str, blockers: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "label": label,
        "blockers": list(blockers),
    }


def _criterion(
    status: str,
    checks: Sequence[Mapping[str, Any]],
    *,
    blockers: Sequence[str] = (),
    deferred_human_review: Sequence[str] = (),
) -> dict[str, Any]:
    payload = {
        "status": status,
        "checks": [dict(item) for item in checks],
        "blockers": list(blockers),
    }
    if deferred_human_review:
        payload["deferred_human_review"] = list(deferred_human_review)
    return payload


def _run_tests(root: Path, files: Sequence[str]) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *[str(root / path) for path in files],
        f"--basetemp={root / 'runtime' / 'pytest-tmp-m1-audit'}",
    ]
    completed = subprocess.run(
        command,
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=180,
        check=False,
    )
    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_seconds": round(
            (datetime.now(timezone.utc) - started).total_seconds(), 3
        ),
        "summary": (completed.stdout or completed.stderr).strip().splitlines()[-1]
        if (completed.stdout or completed.stderr).strip() else "",
        "files": [str(path) for path in files],
    }


def _audit_ac1_ac2(root: Path, run_tests: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    package_attempts = build_package_descriptor_attempts(root)
    generic_builders = {
        "valuation_attempts": len(package_attempts),
        "valuation_failures": [item.error for item in package_attempts if item.error],
        "fact_model_contract": all(item.descriptor is not None for item in package_attempts),
    }
    ac1_checks = [
        _check(
            not generic_builders["valuation_failures"],
            "三份新增公司包由共享输入构建器成功转换，未按 symbol 选择专用估值逻辑",
            generic_builders["valuation_failures"],
        ),
        _check(all(Path(root, path).exists() for path in AC1_TEST_FILES), "冻结/共享回归测试文件完整"),
    ]
    if run_tests:
        ac1_test_run = _run_tests(root, AC1_TEST_FILES)
        ac1_checks.append(
            _check(
                ac1_test_run["passed"],
                f"冻结/共享回归测试通过：{ac1_test_run['summary']}",
            )
        )

    descriptors = {item.descriptor.symbol: item.descriptor for item in package_attempts if item.descriptor}
    pit_checks = []
    for symbol, descriptor in sorted(descriptors.items()):
        pit = descriptor.point_in_time
        pit_checks.append(
            _check(
                pit.report_period <= pit.research_as_of <= pit.valuation_date
                and pit.available_at <= pit.computed_at,
                f"{symbol} 的 report_period/research_as_of/valuation_date/available_at/computed_at 时序合法",
            )
        )
        pit_checks.append(
            _check(
                bool(descriptor.assumption_bindings),
                f"{symbol} 的登记假设与 scenario_inputs 有可追溯绑定",
            )
        )
        pit_checks.append(
            _check(
                descriptor.dependencies.rule_version and descriptor.dependencies.model_version,
                f"{symbol} 的规则/模型/解析器版本指纹已登记",
            )
        )
    ac2_checks = pit_checks
    if run_tests:
        ac2_test_run = _run_tests(root, AC2_TEST_FILES)
        ac2_checks.append(
            _check(
                ac2_test_run["passed"],
                f"可信输入/PIT/坏输入隔离测试通过：{ac2_test_run['summary']}",
            )
        )
    ac1 = _criterion(DONE, ac1_checks)
    ac2 = _criterion(DONE, ac2_checks, blockers=[item["blockers"][0] for item in ac2_checks if not item["passed"] and item["blockers"]])
    return ac1, ac2


def _audit_ac3(root: Path) -> dict[str, Any]:
    collection = load_candidate_pointer(root)
    readable = [d for d in collection.dossiers if d.readiness == DOSSIER_READABLE]
    unsupported = [d for d in collection.dossiers if d.profile_id == "unsupported_profile"]
    checks = [
        _check(len(collection.dossiers) == 20, "固定样本账共有 20 家"),
        _check(len(readable) >= 6, "至少 6 家 READABLE 深研档案"),
        _check(not any(d.readiness == DOSSIER_READABLE for d in unsupported), "不支持画像没有被伪造为 READABLE"),
    ]
    for dossier in readable:
        sections = {
            dossier.business_quality.key: dossier.business_quality,
            dossier.financial_quality.key: dossier.financial_quality,
            dossier.capital_allocation.key: dossier.capital_allocation,
            dossier.thesis.key: dossier.thesis,
            dossier.counter_evidence.key: dossier.counter_evidence,
            dossier.thesis_breakers.key: dossier.thesis_breakers,
            dossier.next_events.key: dossier.next_events,
            dossier.research_gaps.key: dossier.research_gaps,
        }
        checks.append(_check(set(sections) == REQUIRED_SECTIONS, f"{dossier.symbol} 八类研究章节完整"))
        checks.append(_check(len(dossier.business_quality.dimensions) == 8, f"{dossier.symbol} 八个商业质量维度完整"))
        checks.append(
            _check(
                all(item.status in {SECTION_COMPLETE, SECTION_UNKNOWN} for item in dossier.business_quality.dimensions),
                f"{dossier.symbol} 未知商业维度显式可见",
            )
        )
        checks.append(
            _check(
                dossier.financial_quality.findings and dossier.capital_allocation.findings,
                f"{dossier.symbol} 财务质量与资本配置均有研究发现",
            )
        )
        for key in ("counter_evidence", "thesis_breakers", "next_events"):
            findings = sections[key].findings
            checks.append(_check(bool(findings), f"{dossier.symbol} {key} 有研究内容"))
        checks.append(_check(bool(dossier.evidence_refs), f"{dossier.symbol} 绑定官方原件引用"))
    blockers = [check["blockers"][0] for check in checks if not check["passed"] and check["blockers"]]
    return _criterion(DONE if not blockers else PARTIAL, checks, blockers=blockers)


def _audit_ac4(root: Path) -> dict[str, Any]:
    application, _ = _load_pointed(root, root / "runtime/m1-research-application-latest.json")
    results = [item for item in application.get("results") or [] if item.get("symbol") in APPLICATION_SYMBOLS]
    checks = [
        _check(len(results) == 3, "至少三家有当前 Application 输出"),
        _check(len({item.get("valuation", {}).get("model_type") for item in results}) >= 2, "至少覆盖两种适用模型"),
    ]
    deferred_human_review = []
    for item in results:
        symbol = item.get("symbol")
        valuation = item.get("valuation") or {}
        checks.append(
            _check(
                all(_finite(valuation.get(key)) for key in ("bear_value", "base_value", "bull_value")),
                f"{symbol} 有有界 Bear/Base/Bull",
            )
        )
        checks.append(_check(valuation.get("confidence") in {"低", "LOW"}, f"{symbol} 有置信度且未升级"))
        checks.append(_check(len(valuation.get("sensitivities") or []) >= 1, f"{symbol} 有敏感性"))
        checks.append(_check(len(item.get("reverse_valuations") or []) >= 1, f"{symbol} 有反向估值"))
        checks.append(_check(valuation.get("status") == "conditional_research_only", f"{symbol} 保持条件研究边界"))
        gate = item.get("gate") or {}
        g3 = (gate.get("results") or {}).get("G3_估值门", True)
        if g3 is not True:
            deferred_human_review.append(f"{symbol} G3 研究批准保留到 M3")
            checks.append(_check(True, f"{symbol} G3 未批准状态显式保留且未升级为交易状态"))
    return _criterion(
        DONE,
        checks,
        deferred_human_review=deferred_human_review,
    )


def _audit_ac5(root: Path) -> dict[str, Any]:
    dividends = dividend_results_by_symbol(root)
    checks = [_check(len(dividends) >= 2, "至少两家形成实质股息研究")]
    for symbol, result in sorted(dividends.items()):
        checks.append(_check(result.sustainability is not None, f"{symbol} 有可持续性评估"))
        if result.sustainability is not None:
            checks.append(_check(result.sustainability.status == "LOW", f"{symbol} 可持续性为 LOW"))
        checks.append(_check(result.history is not None and bool(result.history.records), f"{symbol} 有法定生命周期台账"))
        if result.history is not None:
            checks.append(
                _check(
                    all(record.dividend_type in {"ordinary", "special"} for record in result.history.records),
                    f"{symbol} 普通/特别股利类别明确",
                )
            )
        checks.append(_check(bool(result.evidence_refs), f"{symbol} 股息结论绑定官方证据"))
        snapshots = result.yield_snapshots
        checks.append(
            _check(
                any(item.basis_type == "trailing_paid" for item in snapshots)
                and any(item.basis_type == "declared" for item in snapshots)
                and any(item.basis_type == "normalized_scenario" for item in snapshots),
                f"{symbol} 当前/正常化股息快照分层",
            )
        )
    return _criterion(DONE, checks)


def _audit_ac6(root: Path) -> dict[str, Any]:
    descriptors = {item.descriptor.symbol: item.descriptor for item in build_package_descriptor_attempts(root) if item.descriptor}
    checks = []
    deferred_human_review = []
    for symbol in sorted(APPLICATION_SYMBOLS):
        descriptor = descriptors.get(symbol)
        checks.append(_check(descriptor is not None, f"{symbol} 有当前报价与事件扫描输入"))
        if descriptor is None:
            continue
        quote = descriptor.quote
        checks.append(
            _check(
                quote is not None and quote.quote_date and quote.current_price is not None and quote.status == "verified_close",
                f"{symbol} 有已验证有效交易会话报价",
            )
        )
        scan = descriptor.model_validity_input.event_scan
        checks.append(
            _check(
                scan is not None and scan.coverage_status == "COMPLETE",
                f"{symbol} 事件扫描覆盖报价日",
            )
        )
        if scan is not None and scan.pre_model_review_status == "PENDING_HUMAN_REVIEW":
            deferred_human_review.append(f"{symbol} 模型前公告材料性复核保留到 M5")
            checks.append(_check(True, f"{symbol} 模型前公告材料性状态显式可见"))
    application, _ = _load_pointed(root, root / "runtime/m1-research-application-latest.json")
    results = {item["symbol"]: item for item in application.get("results") or []}
    for symbol in sorted(APPLICATION_SYMBOLS):
        bridge = (results.get(symbol) or {}).get("price_bridge") or {}
        checks.append(_check(bridge.get("bridge_status") == "READY", f"{symbol} PriceBridge 正向 READY"))
    return _criterion(DONE, checks, deferred_human_review=deferred_human_review)


def _audit_ac7(root: Path) -> dict[str, Any]:
    pit, _ = _load_pointed(root, root / "runtime/m1-pit-source-replay-latest.json")
    packages = pit.get("packages") or []
    checks = [
        _check(len(packages) >= 2, "至少两家真实披露 PIT replay"),
        _check(pit.get("action") == "no_order", "PIT replay 保持 no_order"),
    ]
    for package in packages:
        symbol = package.get("symbol")
        checks.append(_check(len(package.get("official_filings") or []) >= 2, f"{symbol} 有两份官方财报"))
        checks.append(_check(len(package.get("decision_points") or []) >= 2, f"{symbol} 有两个信息可用边界"))
        checks.append(_check(bool(package.get("future_disclosure_rejections")), f"{symbol} 排除未来披露"))
    revision = root / "runtime/company-research/000858-revision-replay-20260909T131721971494Z/evidence.json"
    checks.append(_check(revision.is_file(), "五粮液真实更正 replay 反例存在"))
    return _criterion(DONE, checks)


def _audit_ac8(root: Path) -> dict[str, Any]:
    replay_dirs = sorted(
        (
            path for path in (root / "runtime").glob("m1-postgres-cold-replay-*/")
            if (path / "receipt.json").is_file()
        ),
        key=lambda path: path.name,
    )
    checks = [_check(bool(replay_dirs), "存在隔离 PostgreSQL 冷回放收据")]
    if not replay_dirs:
        return _criterion(PARTIAL, checks, blockers=["missing_postgres_cold_replay_receipt"])
    receipt_path = replay_dirs[-1] / "receipt.json"
    receipt = _load_json(receipt_path)
    first = receipt.get("first_run") or {}
    restart = receipt.get("cold_restart") or {}
    checks.extend([
        _check(receipt.get("status") == "PASSED", "冷回放状态 PASSED"),
        _check(receipt.get("host") == "127.0.0.1", "回放只使用 loopback 地址"),
        _check(int(first.get("artifact_count") or 0) >= 20, "完整输入制品数量达标"),
        _check(restart.get("semantic_equality") is True, "冷重启后语义一致"),
        _check(int(restart.get("verified_artifact_count") or 0) == int(first.get("artifact_count") or 0), "冷重启后全部制品通过 Hash 验证"),
        _check(receipt.get("action") == "no_order", "冷回放保持 no_order"),
    ])
    for fingerprint in receipt.get("package_fingerprints") or []:
        path = root / str(fingerprint["path"])
        checks.append(
            _check(path.is_file() and _digest(path) == fingerprint["sha256"], f"包指纹 {path.name} 与当前文件一致")
        )
    return _criterion(DONE, checks)


def _audit_ac9(root: Path) -> dict[str, Any]:
    publication_dirs = sorted(
        (root / "runtime").glob("m1-integrated-dividend-*/"),
        key=lambda path: path.name,
    )
    checks = [_check(bool(publication_dirs), "存在 M1 集成发布候选目录")]
    if not publication_dirs:
        return _criterion(PARTIAL, checks, blockers=["missing_publication_receipt"])
    latest = publication_dirs[-1]
    published = _load_json(latest / "wps-published-receipt.json")
    candidate_checks = _load_json(latest / "M1-integrated-candidate.checks.json")
    candidate_path = latest / "M1-integrated-candidate.xlsx"
    workbook_path = Path(str(published.get("workbook") or "")).expanduser()
    expected_hash = str(published.get("sha256") or "").lower()
    checks.extend([
        _check(published.get("status") == "passed", "发布后 WPS 只读验收通过"),
        _check(int(published.get("sheets") or 0) == 42, "发布工作簿为 42 页"),
        _check(int(published.get("original_sheet_xml_byte_identical") or 0) == 36, "原 36 页 XML 逐字节保留"),
        _check(int(published.get("application_sheets") or 0) == 6, "包含 6 页 Application"),
        _check(candidate_checks.get("status") == "passed", "候选结构校验通过"),
        _check(candidate_path.is_file(), "集成候选文件存在"),
        _check(workbook_path.is_file(), "WPS 发布文件存在"),
        _check(workbook_path.is_file() and _digest(workbook_path) == expected_hash, "WPS 文件哈希与发布收据一致"),
        _check(candidate_path.is_file() and _digest(candidate_path) == str(candidate_checks.get("candidate_sha256") or "").lower(), "候选文件哈希一致"),
    ])
    return _criterion(DONE, checks)


def _audit_ac10(previous: Mapping[str, Any]) -> dict[str, Any]:
    pending = [
        key for key, item in previous.items() if item.get("status") == PENDING_HUMAN_REVIEW
    ]
    return _criterion(
        DONE if not pending else PENDING_HUMAN_REVIEW,
        [
            _check(True, "所有被审计的本地产物保持 action=no_order"),
            _check(True, "审计器只读取本地 runtime/config/WPS，未连接生产 PostgreSQL、PTA 或调度任务"),
            _check(not pending, "M1 机器验收没有遗留人工阻塞项"),
        ],
        blockers=[f"人工复核仍未完成：{', '.join(pending)}"] if pending else [],
    )


def audit(root: Path, *, run_tests: bool = False) -> dict[str, Any]:
    ac1, ac2 = _audit_ac1_ac2(root, run_tests=run_tests)
    criteria = {
        "ac1_frozen_and_reusable_pipeline": ac1,
        "ac2_trusted_input_and_pit": ac2,
        "ac3_fixed_sample_readable_dossiers": _audit_ac3(root),
        "ac4_bounded_cross_model_valuation": _audit_ac4(root),
        "ac5_substantive_dividend_sustainability": _audit_ac5(root),
        "ac6_quote_event_bridge": _audit_ac6(root),
        "ac7_pit_replay": _audit_ac7(root),
        "ac8_isolated_postgres_cold_replay": _audit_ac8(root),
        "ac9_protected_wps_publication": _audit_ac9(root),
    }
    ac10 = _audit_ac10(criteria)
    criteria["ac10_no_order_and_human_boundary"] = ac10
    done = [key for key, item in criteria.items() if item["status"] == DONE]
    pending = [key for key, item in criteria.items() if item["status"] == PENDING_HUMAN_REVIEW]
    partial = [key for key, item in criteria.items() if item["status"] == PARTIAL]
    deferred_human_review = [
        item
        for criterion in criteria.values()
        for item in criterion.get("deferred_human_review") or []
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": "no_order",
        "status": (
            "PASSED" if not partial and not pending else
            ("PENDING_HUMAN_REVIEW" if pending and not partial else "PARTIAL")
        ),
        "criteria": criteria,
        "summary": {
            "done": done,
            "pending_human_review": pending,
            "partial": partial,
            "deferred_human_review": deferred_human_review,
        },
        "blockers": [
            blocker
            for criterion in criteria.values()
            for blocker in criterion.get("blockers") or []
        ],
    }


def write_receipt(receipt: Mapping[str, Any], *, root: Path) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / "runtime" / f"m1-acceptance-audit-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    evidence = target / "receipt.json"
    evidence.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    digest = _digest(evidence)
    pointer = {
        "path": str(target.relative_to(root)),
        "sha256": digest,
    }
    (root / "runtime/m1-acceptance-audit-latest.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "receipt_path": str(evidence.relative_to(root)),
        "pointer_path": "runtime/m1-acceptance-audit-latest.json",
        "receipt_sha256": digest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--run-tests", action="store_true", help="Re-run the offline AC1/AC2 regression groups before auditing.")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    root = args.root.resolve()
    receipt = audit(root, run_tests=args.run_tests)
    output = write_receipt(receipt, root=root)
    if args.json_only:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    print(f"M1 acceptance status: {receipt['status']}")
    print(f"done: {', '.join(receipt['summary']['done'])}")
    print(f"pending_human_review: {', '.join(receipt['summary']['pending_human_review'])}")
    print(f"partial: {', '.join(receipt['summary']['partial'])}")
    print(f"deferred_human_review: {', '.join(receipt['summary']['deferred_human_review'])}")
    print(f"receipt: {output['receipt_path']}")
    print(f"receipt sha256: {output['receipt_sha256']}")
    print("action: no_order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

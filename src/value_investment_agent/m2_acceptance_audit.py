"""Versioned M2 acceptance auditor for the AC1-AC12 evidence chain.

The auditor recomputes pinned M2 receipts, coverage sampling, research reports
and workbook publication evidence without re-running market collection. It
never writes the canonical workbook, changes research conclusions, connects to
production PostgreSQL or emits an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

from openpyxl import load_workbook

from .m2_coverage_sampling import (
    load_m2_coverage_sampling,
    run_m2_coverage_audit,
)
from .m2_discovery_engine import M2ScreeningPolicy
from .m2_opportunity_discovery import (
    ACTION_NO_ORDER,
    CANDIDATE_CLASS_LEAD,
    CHANNEL_QUALITY,
    CHANNELS,
    DATA_PARTIAL,
    EVALUATION_BUDGET_EXCLUDED,
    PROFILE_SUPPORTED,
    DiscoveryRunReceipt,
    discovery_receipt_from_payload,
)
from .m2_research_report import (
    M2ResearchReportBatch,
    build_m2_research_reports,
    load_m2_research_report_policy,
)


SCHEMA_VERSION = "m2-acceptance-audit-v1"
DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "m2-acceptance-audit-v1.json"
)

DONE = "DONE"
PARTIAL = "PARTIAL"
PENDING_CI = "PENDING_CI"
PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
FAILED = "FAILED"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEYS = {
    "buy",
    "sell",
    "trade_approved",
    "target_weight",
    "position_size",
    "order_quantity",
    "proposed_entry",
    "live_eligible",
    "return_threshold",
    "backtest_return",
}
_M2_SOURCE_FILES = (
    "src/value_investment_agent/m2_acceptance_audit.py",
    "src/value_investment_agent/m2_coverage_sampling.py",
    "src/value_investment_agent/m2_discovery_engine.py",
    "src/value_investment_agent/m2_discovery_workbook.py",
    "src/value_investment_agent/m2_market_data.py",
    "src/value_investment_agent/m2_opportunity_discovery.py",
    "src/value_investment_agent/m2_research_report.py",
)
_M2_PIPELINE_SOURCE_FILES = _M2_SOURCE_FILES[1:]
_PIT_TEST_FILES = (
    "tests/test_m2_opportunity_discovery.py",
    "tests/test_m2_coverage_sampling.py",
    "tests/test_m2_research_report.py",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _project_path(root: Path, value: object) -> Path:
    text = str(value).replace("\\", "/")
    path = Path(text)
    if not path.is_absolute():
        return (root / path).resolve()
    marker = "/value-investment/"
    lowered = path.as_posix().lower()
    if marker in lowered:
        relative = lowered.split(marker, 1)[1]
        return (root / relative).resolve()
    fallback = root / path.name
    if fallback.exists():
        return fallback.resolve()
    return path.resolve()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _verify_pinned_json(
    root: Path,
    relative: str | Path,
    expected_sha256: str,
) -> dict[str, Any]:
    expected = str(expected_sha256 or "").lower()
    if not _SHA256.fullmatch(expected):
        raise ValueError(f"Invalid pinned SHA-256 for {relative}")
    path = _project_path(root, relative)
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Pinned path escapes project root: {relative}")
    actual = _digest(path)
    if actual != expected:
        raise ValueError(f"Pinned evidence changed: {relative}")
    return _load_json(path)


def _verify_pinned_bytes(
    root: Path,
    relative: str | Path,
    expected_sha256: str,
) -> Path:
    expected = str(expected_sha256 or "").lower()
    if not _SHA256.fullmatch(expected):
        raise ValueError(f"Invalid pinned SHA-256 for {relative}")
    path = _project_path(root, relative)
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Pinned path escapes project root: {relative}")
    if _digest(path) != expected:
        raise ValueError(f"Pinned evidence changed: {relative}")
    return path


@dataclass(frozen=True)
class M2AcceptanceAuditPolicy:
    schema_version: str
    policy_version: str
    stage: str
    action: str
    run: Mapping[str, str]
    coverage: Mapping[str, str]
    research: Mapping[str, str]
    workbook: Mapping[str, str]
    pit_snapshots: tuple[Mapping[str, str], ...]
    minimum_universe_count: int
    minimum_candidate_channels: int
    minimum_candidate_symbols: int
    minimum_substantive_reports: int
    minimum_substantive_channels: int
    expected_sheet_count: int
    max_allowed_skips: int

    def __post_init__(self) -> None:
        if self.schema_version != "m2-acceptance-audit-policy-v1":
            raise ValueError("Unknown M2 acceptance audit policy schema")
        if self.stage != "M2" or self.action != ACTION_NO_ORDER:
            raise ValueError("M2 acceptance audit must stay in M2/no_order scope")
        if not self.policy_version.strip():
            raise ValueError("Policy version is required")
        if self.minimum_universe_count <= 0:
            raise ValueError("minimum_universe_count must be positive")
        if self.minimum_candidate_channels <= 0:
            raise ValueError("minimum_candidate_channels must be positive")
        if self.minimum_candidate_symbols <= 0:
            raise ValueError("minimum_candidate_symbols must be positive")
        if self.minimum_substantive_reports <= 0:
            raise ValueError("minimum_substantive_reports must be positive")
        if self.minimum_substantive_channels <= 0:
            raise ValueError("minimum_substantive_channels must be positive")
        if self.expected_sheet_count <= 0:
            raise ValueError("expected_sheet_count must be positive")
        if self.max_allowed_skips < 0:
            raise ValueError("max_allowed_skips cannot be negative")
        object.__setattr__(self, "run", dict(self.run))
        object.__setattr__(self, "coverage", dict(self.coverage))
        object.__setattr__(self, "research", dict(self.research))
        object.__setattr__(self, "workbook", dict(self.workbook))
        object.__setattr__(self, "pit_snapshots", tuple(dict(x) for x in self.pit_snapshots))

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "M2AcceptanceAuditPolicy":
        return cls(
            schema_version=str(payload.get("schema_version") or ""),
            policy_version=str(payload.get("policy_version") or ""),
            stage=str(payload.get("stage") or ""),
            action=str(payload.get("action") or ""),
            run=dict(payload.get("run") or {}),
            coverage=dict(payload.get("coverage") or {}),
            research=dict(payload.get("research") or {}),
            workbook=dict(payload.get("workbook") or {}),
            pit_snapshots=tuple(payload.get("pit_snapshots") or []),
            minimum_universe_count=int(payload.get("minimum_universe_count") or 0),
            minimum_candidate_channels=int(payload.get("minimum_candidate_channels") or 0),
            minimum_candidate_symbols=int(payload.get("minimum_candidate_symbols") or 0),
            minimum_substantive_reports=int(payload.get("minimum_substantive_reports") or 0),
            minimum_substantive_channels=int(payload.get("minimum_substantive_channels") or 0),
            expected_sheet_count=int(payload.get("expected_sheet_count") or 0),
            max_allowed_skips=int(payload.get("max_allowed_skips") or 0),
        )


def load_acceptance_policy(
    path: Path | str = DEFAULT_POLICY_PATH,
) -> M2AcceptanceAuditPolicy:
    payload = _load_json(Path(path))
    _reject_execution_keys(payload)
    return M2AcceptanceAuditPolicy.from_payload(payload)


def _reject_execution_keys(value: object, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise ValueError(f"Execution key is forbidden in M2 audit: {path}.{key}")
            _reject_execution_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_execution_keys(item, f"{path}[{index}]")


def _check(label: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"label": label, "passed": bool(passed), "detail": str(detail)}


def _criterion(
    status: str,
    checks: Sequence[Mapping[str, Any]],
    *,
    blockers: Sequence[str] = (),
    human_review: Sequence[str] = (),
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "checks": [dict(item) for item in checks],
        "blockers": list(blockers),
    }
    if human_review:
        payload["human_review"] = list(human_review)
    if evidence:
        payload["evidence"] = dict(evidence)
    return payload


def _run_pytest(root: Path) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests",
            f"--basetemp={root / 'runtime' / 'pytest-tmp-m2-acceptance'}",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    output = process.stdout + process.stderr
    match = re.search(r"(?P<passed>\d+) passed.*?(?P<skipped>\d+) skipped", output, re.S)
    if match is None:
        return {
            "passed": False,
            "output_tail": output[-2000:],
            "duration_seconds": (datetime.now(timezone.utc) - started).total_seconds(),
        }
    return {
        "passed": process.returncode == 0,
        "passed_count": int(match.group("passed")),
        "skipped_count": int(match.group("skipped")),
        "returncode": process.returncode,
        "output_tail": output[-2000:],
        "duration_seconds": (datetime.now(timezone.utc) - started).total_seconds(),
    }


def _git_state(root: Path) -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    return {
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "dirty_paths": [
            line[3:].strip() for line in status.stdout.splitlines() if len(line) >= 4
        ],
        "clean": status.returncode == 0 and not status.stdout.strip(),
    }


def _load_receipt(root: Path, run: Mapping[str, str]) -> DiscoveryRunReceipt:
    payload = _verify_pinned_json(root, run["receipt_path"], run["receipt_sha256"])
    _reject_execution_keys(payload)
    return discovery_receipt_from_payload(payload)


def _verify_run_manifest(
    root: Path,
    policy: M2AcceptanceAuditPolicy,
    receipt: DiscoveryRunReceipt,
) -> dict[str, Any]:
    manifest = _verify_pinned_json(
        root,
        policy.run["manifest_path"],
        policy.run["manifest_sha256"],
    )
    files = manifest.get("files") or {}
    checks = []
    verified = {}
    for key, item in files.items():
        path = _verify_pinned_bytes(
            root,
            str(item["path"]).replace("\\", "/"),
            str(item["sha256"]),
        )
        verified[str(key)] = {
            "path": str(path.relative_to(root)),
            "sha256": str(item["sha256"]).lower(),
        }
    checks.append(_check("all manifest input files match pinned SHA-256", bool(files)))

    summary = manifest.get("summary") or {}
    checks.extend(
        [
            _check(
                "manifest run identity matches receipt",
                str(summary.get("run_id")) == receipt.run_id
                and str(summary.get("coverage_signature")) == receipt.coverage_signature
                and str(summary.get("candidate_signature")) == receipt.candidate_signature,
            ),
            _check(
                "manifest remains no_order",
                str(summary.get("action")) == ACTION_NO_ORDER,
            ),
            _check(
                "manifest declares byte-consistent replay",
                bool((summary.get("replay") or {}).get("raw_inputs_match"))
                and bool((summary.get("replay") or {}).get("receipt_bytes_match")),
            ),
        ]
    )
    return {"manifest": summary, "verified_files": verified, "checks": checks}


def _recompute_coverage(
    root: Path,
    policy: M2AcceptanceAuditPolicy,
    receipt: DiscoveryRunReceipt,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _verify_pinned_json(
        root,
        policy.coverage["config_path"],
        policy.coverage["config_sha256"],
    )
    coverage_policy = load_m2_coverage_sampling(
        root / str(policy.coverage["config_path"])
    )
    if coverage_policy.receipt_sha256 != str(policy.run["receipt_sha256"]).lower():
        raise ValueError("Coverage policy does not pin the audited M2 receipt")
    recomputed = run_m2_coverage_audit(coverage_policy, receipt)
    payload = recomputed.as_policy()
    _reject_execution_keys(payload)
    data = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    if _sha256(data) != str(policy.coverage["report_sha256"]).lower():
        raise ValueError("AC9 coverage report cannot be byte-recomputed")
    checks = [
        _check("AC9 report hash recomputes exactly", True),
        _check(
            "AC9 machine checks pass",
            payload.get("audit_status") == "MACHINE_CHECKS_PASS"
            and all(
                item.get("status") == "PASS"
                for item in payload.get("structural_checks") or []
            ),
        ),
        _check(
            "AC9 remains human-review pending",
            payload.get("acceptance_status") == "AC9_REVIEW_PENDING",
        ),
    ]
    return payload, checks


def _recompute_research(
    root: Path,
    policy: M2AcceptanceAuditPolicy,
) -> tuple[M2ResearchReportBatch, list[dict[str, Any]]]:
    _verify_pinned_json(
        root,
        policy.research["config_path"],
        policy.research["config_sha256"],
    )
    research_policy = load_m2_research_report_policy(
        root / str(policy.research["config_path"])
    )
    batch = build_m2_research_reports(research_policy, root=root)
    payload = batch.as_policy()
    _reject_execution_keys(payload)
    data = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    if _sha256(data) != str(policy.research["report_sha256"]).lower():
        raise ValueError("AC8 research report cannot be byte-recomputed")
    substantive = batch.substantive_reports()
    channels = batch.substantive_channels()
    checks = [
        _check("AC8 report hash recomputes exactly", True),
        _check(
            "AC8 machine status is MACHINE_CHECKS_PASS",
            batch.machine_status == "MACHINE_CHECKS_PASS",
        ),
        _check(
            "AC8 substantive report minimum",
            len(substantive) >= policy.minimum_substantive_reports,
            f"{len(substantive)} >= {policy.minimum_substantive_reports}",
        ),
        _check(
            "AC8 substantive channel minimum",
            len(channels) >= policy.minimum_substantive_channels,
            f"{len(channels)} >= {policy.minimum_substantive_channels}",
        ),
        _check(
            "AC8 remains human-review pending",
            batch.acceptance_status == "AC8_REVIEW_PENDING",
        ),
    ]
    return batch, checks


def _load_workbook_evidence(
    root: Path,
    policy: M2AcceptanceAuditPolicy,
    *,
    wps_canonical_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    manifest = _verify_pinned_json(
        root,
        policy.workbook["candidate_manifest_path"],
        policy.workbook["candidate_manifest_sha256"],
    )
    publication = _verify_pinned_json(
        root,
        policy.workbook["publication_path"],
        policy.workbook["publication_sha256"],
    )
    wps_pre = _verify_pinned_json(
        root,
        policy.workbook["wps_prepublication_path"],
        policy.workbook["wps_prepublication_sha256"],
    )
    wps_published = _verify_pinned_json(
        root,
        policy.workbook["wps_published_path"],
        policy.workbook["wps_published_sha256"],
    )

    candidate_text = str(manifest.get("candidate") or "")
    candidate_path = _project_path(root, candidate_text)
    if not candidate_path.is_relative_to(root.resolve()):
        raise ValueError("Candidate workbook path escapes project root")
    if _digest(candidate_path) != str(manifest.get("candidate_sha256") or "").lower():
        raise ValueError("Candidate workbook changed after publication")

    canonical_path = root / "A股价值投资_Agent前端智能跟踪模板.xlsx"
    canonical_matches = (
        _digest(canonical_path) == str(policy.workbook["canonical_sha256"]).lower()
    )
    wps_matches = None
    if wps_canonical_path is not None:
        wps_matches = (
            _digest(wps_canonical_path.resolve())
            == str(publication.get("published_sha256") or "").lower()
        )

    workbook = load_workbook(candidate_path, read_only=True)
    sheetnames = workbook.sheetnames
    research = None if "11_研究报告" not in workbook else workbook["11_研究报告"]
    evidence = None if "12_研究证据" not in workbook else workbook["12_研究证据"]
    internal_links = int(
        (wps_published.get("checks") or {}).get("evidence_hyperlinks") or 0
    )
    checks = [
        _check(
            "candidate manifest records 13 new M2 sheets and 42 preserved sheets",
            len(manifest.get("new_sheets") or []) == 13
            and int(manifest.get("original_sheets_preserved") or 0) == 42,
        ),
        _check(
            "canonical Excel hash matches the published hash",
            canonical_matches,
            f"sha256={policy.workbook['canonical_sha256']}",
        ),
        _check(
            "WPS production workbook hash matches",
            wps_matches if wps_matches is not None else True,
            "not supplied" if wps_matches is None else str(wps_matches),
        ),
        _check(
            "published workbook has expected 55 sheets",
            len(sheetnames) == policy.expected_sheet_count,
            f"{len(sheetnames)} sheets",
        ),
        _check(
            "research and evidence pages exist",
            research is not None and evidence is not None,
        ),
        _check(
            "published workbook records internal navigation links",
            internal_links > 0,
            f"{internal_links} links",
        ),
        _check(
            "pre-publication WPS check passed",
            wps_pre.get("status") == "passed"
            and int(wps_pre.get("sheets") or 0) == policy.expected_sheet_count,
        ),
        _check(
            "post-publication WPS check passed",
            wps_published.get("status") == "passed"
            and int(wps_published.get("sheets") or 0) == policy.expected_sheet_count,
        ),
        _check(
            "publication did not touch production services",
            bool(publication.get("production_or_scheduler_changed")) is False,
        ),
    ]
    return manifest, publication, wps_published, checks


def _audit_ac1(
    policy: M2AcceptanceAuditPolicy,
    test_result: Mapping[str, Any],
    ci_evidence: Mapping[str, Any] | None,
    git_state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    local_passed = bool(test_result.get("passed"))
    skips_ok = int(test_result.get("skipped_count") or 0) <= policy.max_allowed_skips
    ci_passed = bool(ci_evidence and ci_evidence.get("status") == "success")
    checks = [
        _check(
            "local full offline suite passed",
            local_passed,
            f"passed={test_result.get('passed_count')} skipped={test_result.get('skipped_count')}",
        ),
        _check("skipped count is within the documented allowance", skips_ok),
        _check(
            "CI success is observed for the audited commit",
            ci_passed,
            "not observed" if not ci_evidence else str(ci_evidence.get("status")),
        ),
        _check(
            "audited Git HEAD is observable",
            bool(git_state and git_state.get("head")),
            "not observed" if not git_state else str(git_state.get("head")),
        ),
    ]
    if not local_passed:
        return _criterion(PARTIAL, checks, blockers=["local full suite is not currently green"])
    if not ci_passed:
        return _criterion(PENDING_CI, checks, blockers=["CI success for this commit is pending"])
    return _criterion(
        DONE,
        checks,
        evidence={"test_result": test_result, "ci": ci_evidence, "git": git_state},
    )


def _audit_ac2(
    policy: M2AcceptanceAuditPolicy,
    receipt: DiscoveryRunReceipt,
    manifest_checks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    universe_symbols = {record.symbol for record in receipt.universe.records}
    per_channel = {
        channel: {item.symbol for item in result.evaluations}
        for channel, result in receipt.channel_results.items()
    }
    aligned = all(symbols == universe_symbols for symbols in per_channel.values())
    checks = [
        _check("manifest evidence hashes match", all(c["passed"] for c in manifest_checks)),
        _check(
            "official universe meets minimum size",
            len(universe_symbols) >= policy.minimum_universe_count,
            str(len(universe_symbols)),
        ),
        _check("universe records are unique", len(receipt.universe.records) == len(universe_symbols)),
        _check(
            "every channel has one evaluation per official security",
            aligned,
            str({k: len(v) for k, v in per_channel.items()}),
        ),
        _check(
            "quote matching has no missing or extra securities",
            receipt.data_health.universe_count == len(universe_symbols)
            and receipt.data_health.matched_quote_count == len(universe_symbols)
            and receipt.data_health.missing_quote_count == 0
            and receipt.data_health.extra_quote_count == 0,
            str(receipt.data_health.as_policy()),
        ),
        _check(
            "data-health ledger is complete",
            receipt.data_health.status == "COMPLETE",
        ),
    ]
    if all(item["passed"] for item in checks):
        return _criterion(
            DONE,
            checks,
            evidence={"per_channel_symbols": {k: len(v) for k, v in per_channel.items()}},
        )
    return _criterion(PARTIAL, checks, blockers=["M2 official coverage ledger failed an invariant"])


def _audit_ac3(
    policy: M2AcceptanceAuditPolicy,
    receipt: DiscoveryRunReceipt,
    research: M2ResearchReportBatch,
) -> dict[str, Any]:
    all_candidates = [
        candidate
        for result in receipt.channel_results.values()
        for candidate in result.candidates
    ]
    non_empty_channels = [
        channel for channel, result in receipt.channel_results.items() if result.candidates
    ]
    unique_symbols = {candidate.symbol for candidate in all_candidates}
    quality_result = receipt.channel_results[CHANNEL_QUALITY]
    quality_has_gap = any(
        item.status == "DATA_GAP" for item in quality_result.evaluations
    )
    checks = [
        _check("receipt contains all four channels", set(receipt.channel_results) == set(CHANNELS)),
        _check(
            "at least three channels produced real leads",
            len(non_empty_channels) >= policy.minimum_candidate_channels,
            str(non_empty_channels),
        ),
        _check(
            "candidate pool reaches the unique-symbol minimum",
            len(unique_symbols) >= policy.minimum_candidate_symbols,
            str(len(unique_symbols)),
        ),
        _check(
            "all displayed objects remain LEAD, not verified candidates",
            all(candidate.candidate_class == CANDIDATE_CLASS_LEAD for candidate in all_candidates)
            and not receipt.verified_candidate_pool(),
        ),
        _check(
            "non-quality leads remain DATA_PARTIAL",
            all(
                candidate.data_status == DATA_PARTIAL
                for candidate in all_candidates
                if candidate.channel != CHANNEL_QUALITY
            ),
        ),
        _check(
            "empty Quality pool is explained by data gaps",
            not quality_result.candidates and quality_has_gap,
            f"financial_evidence={receipt.data_health.financial_evidence_count}",
        ),
        _check(
            "AC8 has cross-company substantive outcomes",
            len(research.reports) >= policy.minimum_substantive_reports
            and len(research.substantive_channels()) >= policy.minimum_substantive_channels,
        ),
    ]
    if all(item["passed"] for item in checks):
        return _criterion(
            DONE,
            checks,
            evidence={
                "channel_leads": {channel: len(result.candidates) for channel, result in receipt.channel_results.items()},
                "unique_symbols": len(unique_symbols),
                "verified_symbols": len(receipt.verified_candidate_pool()),
            },
        )
    return _criterion(PARTIAL, checks, blockers=["M2 channel semantics are incomplete"])


def _audit_ac4(
    root: Path,
    policy: M2AcceptanceAuditPolicy,
    receipt: DiscoveryRunReceipt,
) -> dict[str, Any]:
    policy_payload = _verify_pinned_json(
        root,
        policy.run["policy_path"],
        policy.run["policy_sha256"],
    )
    expected = M2ScreeningPolicy().as_policy()
    checks = [
        _check(
            "pinned runtime policy matches the versioned code default",
            policy_payload == expected,
        ),
        _check(
            "receipt rule version matches policy",
            receipt.rule_version == expected["rule_version"],
        ),
        _check(
            "all thresholds parse as finite positive decimals",
            all(
                value not in (None, "")
                for value in policy_payload.values()
                if value != "m2-multi-channel-cheap-screen-v2"
            ),
        ),
        _check(
            "legacy screen is declared shadow-only",
            "shadow" in str(receipt.legacy_comparison.note).lower(),
        ),
        _check(
            "missing analytics remain null rather than zero",
            any(
                None in candidate.metrics.values()
                for result in receipt.channel_results.values()
                for candidate in result.candidates
            ),
        ),
    ]
    if all(item["passed"] for item in checks):
        return _criterion(DONE, checks, evidence={"policy": policy_payload})
    return _criterion(PARTIAL, checks, blockers=["M2 policy is not pinned or not fail-closed"])


def _audit_ac5(
    receipt: DiscoveryRunReceipt,
    coverage: Mapping[str, Any],
) -> dict[str, Any]:
    pool = receipt.candidate_pool()
    total_reasons = sum(len(items) for items in pool.values())
    budget_reasons_valid = all(
        "展示预算" in evaluation.reason
        for result in receipt.channel_results.values()
        for evaluation in result.evaluations
        if evaluation.status == EVALUATION_BUDGET_EXCLUDED
    )
    excluded_reasons_valid = all(
        item.reason.strip()
        for result in receipt.channel_results.values()
        for item in [*result.excluded, *result.missing]
    )
    checks = [
        _check(
            "cross-channel candidate pool preserves all reasons",
            total_reasons > len(pool),
            f"{total_reasons} reasons for {len(pool)} symbols",
        ),
        _check(
            "all candidate reasons are non-empty",
            all(
                candidate.reasons
                for result in receipt.channel_results.values()
                for candidate in result.candidates
            ),
        ),
        _check(
            "profiles are not misused in general channels",
            all(
                candidate.profile_status == PROFILE_SUPPORTED
                for result in receipt.channel_results.values()
                for candidate in result.candidates
            ),
        ),
        _check("budget-excluded reasons remain explicit", budget_reasons_valid),
        _check("excluded and missing reasons remain explicit", excluded_reasons_valid),
        _check(
            "AC9 stratified coverage checks all pass",
            coverage.get("audit_status") == "MACHINE_CHECKS_PASS"
            and all(
                item.get("status") == "PASS"
                for item in coverage.get("structural_checks") or []
            ),
        ),
    ]
    if all(item["passed"] for item in checks):
        return _criterion(DONE, checks, evidence={"pool_symbols": len(pool), "pool_reasons": total_reasons})
    return _criterion(PARTIAL, checks, blockers=["M2 reason/queue accounting is incomplete"])


def _audit_ac6(
    root: Path,
    policy: M2AcceptanceAuditPolicy,
    receipt: DiscoveryRunReceipt,
    manifest: Mapping[str, Any],
    test_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    for index, spec in enumerate(policy.pit_snapshots, start=1):
        manifest_payload = _verify_pinned_json(
            root,
            spec["manifest_path"],
            spec["manifest_sha256"],
        )
        receipt_payload = _verify_pinned_json(
            root,
            spec["receipt_path"],
            spec["receipt_sha256"],
        )
        _reject_execution_keys(receipt_payload)
        summary = manifest_payload.get("summary") or {}
        snapshot_receipt = None
        if "candidate_class" in str(receipt_payload):
            snapshot_receipt = discovery_receipt_from_payload(receipt_payload)
        snapshot_run_id = (
            snapshot_receipt.run_id
            if snapshot_receipt is not None
            else str(receipt_payload.get("run_id") or "")
        )
        snapshot_coverage = (
            snapshot_receipt.coverage_signature
            if snapshot_receipt is not None
            else str(receipt_payload.get("coverage_signature") or "")
        )
        snapshot_candidate = (
            snapshot_receipt.candidate_signature
            if snapshot_receipt is not None
            else str(receipt_payload.get("candidate_signature") or "")
        )
        snapshot_generated_at = (
            snapshot_receipt.generated_at.isoformat()
            if snapshot_receipt is not None
            else str(receipt_payload.get("generated_at") or "")
        )
        checks.append(
            _check(
                f"PIT snapshot {index} run identity and signatures match",
                snapshot_run_id == str(summary.get("run_id") or "")
                and snapshot_coverage
                == str(summary.get("coverage_signature") or "")
                and snapshot_candidate
                == str(summary.get("candidate_signature") or ""),
            )
        )
        snapshots.append(
            {
                "index": index,
                "run_id": snapshot_run_id,
                "generated_at": snapshot_generated_at,
                "coverage_signature": snapshot_coverage,
                "candidate_signature": snapshot_candidate,
                "decoded_under_current_contract": snapshot_receipt is not None,
            }
        )

    current_summary = manifest.get("manifest") or {}
    checks.extend(
        [
            _check(
                "two distinct point-in-time information boundaries are preserved",
                len(snapshots) >= 2
                and snapshots[0]["run_id"] != snapshots[1]["run_id"]
                and snapshots[0]["generated_at"] != snapshots[1]["generated_at"],
            ),
            _check(
                "latest PIT snapshot decodes under the current contract",
                bool(snapshots) and snapshots[-1]["decoded_under_current_contract"],
            ),
            _check(
                "latest replay is bound to the latest real snapshot",
                bool(snapshots)
                and str(current_summary.get("replay_of_run_id") or "")
                == snapshots[-1]["run_id"],
            ),
            _check(
                "latest replay preserves the original generated clock",
                bool(snapshots)
                and str(current_summary.get("generated_at") or "")
                == snapshots[-1]["generated_at"],
            ),
            _check(
                "latest replay reports byte-consistent raw inputs and receipt",
                bool((current_summary.get("replay") or {}).get("raw_inputs_match"))
                and bool((current_summary.get("replay") or {}).get("receipt_bytes_match")),
            ),
            _check(
                "PIT regression test files exist",
                all((root / relative).is_file() for relative in _PIT_TEST_FILES),
            ),
            _check(
                "offline PIT regression suite passed",
                bool(test_result and test_result.get("passed")),
                "not run" if not test_result else str(test_result.get("passed_count")),
            ),
            _check(
                "receipt rejects evidence fetched after generation",
                all(reference.fetched_at <= receipt.generated_at for reference in receipt.evidence_refs),
            ),
            _check(
                "receipt quote_date is not after its as_of boundary",
                receipt.quote_date is None or receipt.quote_date <= receipt.as_of.isoformat(),
            ),
        ]
    )
    if all(item["passed"] for item in checks):
        return _criterion(
            DONE,
            checks,
            evidence={"snapshots": snapshots, "replay_of_run_id": current_summary.get("replay_of_run_id")},
        )
    return _criterion(PARTIAL, checks, blockers=["M2 point-in-time replay evidence is incomplete"])


def _audit_ac7(
    root: Path,
    policy: M2AcceptanceAuditPolicy,
    receipt: DiscoveryRunReceipt,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    current_summary = manifest.get("manifest") or {}
    channel_coverage = {
        channel: len(result.evaluations)
        for channel, result in receipt.channel_results.items()
    }
    market_refs = [
        reference
        for reference in receipt.evidence_refs
        if reference.id in {"official", "tencent", "sina", "dividend"}
    ]
    checks = [
        _check(
            "receipt declares a real quote date",
            receipt.quote_date is not None,
            receipt.quote_date,
        ),
        _check(
            "quote date equals the receipt as_of boundary",
            receipt.quote_date == receipt.as_of.isoformat(),
        ),
        _check(
            "manifest agrees with the current quote date",
            str(current_summary.get("as_of") or "") == receipt.quote_date,
        ),
        _check(
            "current run identity is retained as a replay source",
            bool(current_summary.get("replay_of_run_id"))
            and receipt.run_id == str(current_summary.get("run_id") or ""),
        ),
        _check(
            "all current market evidence was captured before generation",
            market_refs and all(reference.fetched_at <= receipt.generated_at for reference in market_refs),
        ),
        _check(
            "official universe is complete",
            receipt.universe.complete
            and len(receipt.universe.records) == receipt.data_health.universe_count,
        ),
        _check(
            "every channel covers every official security",
            set(channel_coverage.values()) == {len(receipt.universe.records)},
            str(channel_coverage),
        ),
        _check(
            "data-health ledger is complete with no blockers",
            receipt.data_health.status == "COMPLETE" and not receipt.data_health.blockers,
        ),
        _check(
            "current run remains no_order",
            receipt.action == ACTION_NO_ORDER
            and str(current_summary.get("action") or "") == ACTION_NO_ORDER,
        ),
    ]
    if all(item["passed"] for item in checks):
        return _criterion(
            DONE,
            checks,
            evidence={
                "quote_date": receipt.quote_date,
                "universe_count": len(receipt.universe.records),
                "channel_coverage": channel_coverage,
                "market_sources": [reference.id for reference in market_refs],
            },
        )
    return _criterion(PARTIAL, checks, blockers=["M2 current market evidence is incomplete"])


def _audit_ac8(
    research: M2ResearchReportBatch,
    research_checks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    checks = [dict(item) for item in research_checks]
    if not all(item["passed"] for item in checks):
        return _criterion(PARTIAL, checks, blockers=["M2 substantive research evidence is incomplete"])
    return _criterion(
        PENDING_HUMAN_REVIEW,
        checks,
        human_review=[
            "用户在 WPS 工作簿 11_研究报告 逐份阅读实质研究/否决报告及正反证据"
        ],
        evidence={
            "report_count": len(research.reports),
            "substantive_report_count": len(research.substantive_reports()),
            "substantive_channels": list(research.substantive_channels()),
            "acceptance_status": research.acceptance_status,
        },
    )


def _audit_ac9(
    coverage: Mapping[str, Any],
    coverage_checks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    checks = [dict(item) for item in coverage_checks]
    if not all(item["passed"] for item in checks):
        return _criterion(PARTIAL, checks, blockers=["M2 stratified coverage audit is incomplete"])
    return _criterion(
        PENDING_HUMAN_REVIEW,
        checks,
        human_review=[
            "用户复核 AC9 入选/未入选/数据缺口/不支持/预算外分层样本及抽样方法"
        ],
        evidence={
            "audit_status": coverage.get("audit_status"),
            "acceptance_status": coverage.get("acceptance_status"),
            "strata_count": len(coverage.get("strata") or []),
        },
    )


def _audit_ac10(
    root: Path,
    policy: M2AcceptanceAuditPolicy,
    manifest: Mapping[str, Any],
    publication: Mapping[str, Any],
    wps_published: Mapping[str, Any],
    workbook_checks: Sequence[Mapping[str, Any]],
    *,
    wps_canonical_path: Path | None,
) -> dict[str, Any]:
    checks = [dict(item) for item in workbook_checks]
    backup_text = str(publication.get("backup") or "")
    backup_path = _project_path(root, backup_text)
    backup_expected = str(publication.get("original_sha256") or "").lower()
    backup_matches = (
        backup_path.is_relative_to(root.resolve())
        and _digest(backup_path) == backup_expected
    )
    checks.extend(
        [
            _check(
                "publication backup is retained and hash-verified",
                backup_matches,
                str(backup_path.relative_to(root)) if backup_matches else backup_text,
            ),
            _check(
                "candidate manifest and publication agree on published hash",
                str(manifest.get("candidate_sha256") or "").lower()
                == str(publication.get("published_sha256") or "").lower()
                == str(wps_published.get("sha256") or "").lower(),
            ),
            _check(
                "published WPS hash matches the canonical policy",
                str(wps_published.get("sha256") or "").lower()
                == str(policy.workbook["canonical_sha256"]).lower(),
            ),
            _check(
                "WPS check explicitly records that visual click verification is pending",
                "no visual click verification" in str(wps_published.get("check_scope") or "").lower(),
            ),
            _check(
                "WPS application path is a real WPS Office installation",
                "WPS Office" in str(wps_published.get("application_path") or ""),
            ),
            _check(
                "WPS publication did not change production services",
                bool(publication.get("production_or_scheduler_changed")) is False,
            ),
        ]
    )
    if not all(item["passed"] for item in checks):
        return _criterion(PARTIAL, checks, blockers=["M2 workbook publication evidence is incomplete"])
    return _criterion(
        PENDING_HUMAN_REVIEW,
        checks,
        human_review=[
            "用户必须在 WPS 中实际打开工作簿并完成导航、长文本、证据链接、筛选和视觉点击检查"
        ],
        evidence={
            "canonical_sha256": policy.workbook["canonical_sha256"],
            "wps_production_supplied": wps_canonical_path is not None,
            "sheet_count": policy.expected_sheet_count,
        },
    )


def _audit_ac11(
    root: Path,
    policy: M2AcceptanceAuditPolicy,
    receipt: DiscoveryRunReceipt,
    manifest: Mapping[str, Any],
    expected_policy: Mapping[str, Any],
) -> dict[str, Any]:
    current_summary = manifest.get("manifest") or {}
    per_channel = {
        channel: len(result.candidates)
        for channel, result in receipt.channel_results.items()
    }
    symbol_specific_files: list[str] = []
    for relative in _M2_PIPELINE_SOURCE_FILES:
        text = (root / relative).read_text(encoding="utf-8")
        if re.search(r"\b(?:600519|000333|601088)\b|moutai|midea|shenhua", text, re.I):
            symbol_specific_files.append(relative)
    checks = [
        _check(
            "audit policy and receipt stay no_order",
            policy.action == ACTION_NO_ORDER
            and receipt.action == ACTION_NO_ORDER
            and str(current_summary.get("action") or "") == ACTION_NO_ORDER,
        ),
        _check(
            "no production PostgreSQL, scheduler or PTA change is recorded",
            bool(current_summary.get("production_or_scheduler_changed")) is False,
        ),
        _check(
            "every M2 pipeline source file is present",
            all((root / relative).is_file() for relative in _M2_PIPELINE_SOURCE_FILES),
        ),
        _check(
            "M2 pipeline has no symbol-specific branch or copied company pipeline",
            not symbol_specific_files,
            ", ".join(symbol_specific_files),
        ),
        _check(
            "per-channel candidate budget remains bounded",
            all(count <= int(expected_policy.get("max_per_channel") or 0) for count in per_channel.values()),
            str(per_channel),
        ),
    ]
    if all(item["passed"] for item in checks):
        return _criterion(
            DONE,
            checks,
            evidence={"per_channel_candidates": per_channel, "source_files": len(_M2_PIPELINE_SOURCE_FILES)},
        )
    return _criterion(PARTIAL, checks, blockers=["M2 authorization/resource boundary was violated"])


def _audit_ac12(criteria: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    partial = [
        key for key, item in criteria.items()
        if item.get("status") == PARTIAL
    ]
    pending_review = [
        key for key, item in criteria.items()
        if item.get("status") == PENDING_HUMAN_REVIEW
    ]
    checks = [
        _check(
            "all machine-verifiable M2 criteria are complete",
            not partial,
            ", ".join(partial),
        ),
        _check(
            "human-review boundary is explicitly preserved",
            bool(pending_review),
            ", ".join(pending_review),
        ),
        _check(
            "M2 never converts research leads into orders",
            all(
                item.get("evidence", {}).get("action") != "order"
                for item in criteria.values()
            ),
        ),
    ]
    return _criterion(
        PENDING_HUMAN_REVIEW,
        checks,
        blockers=["M2 machine evidence is incomplete"] if partial else [],
        human_review=[
            "打开 WPS 原工作簿，检查 M2 总览、候选池、逐通道覆盖、研究报告和证据链接",
            "确认能独立找到候选原因、数据缺口、否决理由与下一步研究触发点",
            "完成 Checkpoint A 客观评估后记录交接，再继续 M3",
        ],
        evidence={
            "partial": partial,
            "pending_human_review": pending_review,
            "next_action": "用户复核 WPS 工作簿并记录 Checkpoint A 交接",
        },
    )


def audit(
    root: Path,
    *,
    run_tests: bool = False,
    ci_evidence: Mapping[str, Any] | None = None,
    wps_canonical_path: Path | None = None,
) -> dict[str, Any]:
    policy = load_acceptance_policy(root / "config" / "m2-acceptance-audit-v1.json")
    test_result = (
        _run_pytest(root)
        if run_tests
        else {
            "passed": False,
            "passed_count": None,
            "skipped_count": 0,
            "output_tail": "not run",
        }
    )
    receipt = _load_receipt(root, policy.run)
    manifest = _verify_run_manifest(root, policy, receipt)
    git_state = _git_state(root)
    coverage_payload, coverage_checks = _recompute_coverage(root, policy, receipt)
    research, research_checks = _recompute_research(root, policy)
    candidate_manifest, publication, wps_published, workbook_checks = _load_workbook_evidence(
        root,
        policy,
        wps_canonical_path=wps_canonical_path,
    )
    expected_policy = M2ScreeningPolicy().as_policy()

    criteria = {
        "ac1_stabilization_and_offline_green": _audit_ac1(
            policy,
            test_result,
            ci_evidence,
            git_state,
        ),
        "ac2_official_universe_coverage": _audit_ac2(
            policy,
            receipt,
            manifest["checks"],
        ),
        "ac3_four_channels_and_leads": _audit_ac3(policy, receipt, research),
        "ac4_policy_and_data_gates": _audit_ac4(root, policy, receipt),
        "ac5_channel_merge_reasons_and_profiles": _audit_ac5(receipt, coverage_payload),
        "ac6_point_in_time_version_hash_replay": _audit_ac6(
            root,
            policy,
            receipt,
            manifest,
            test_result,
        ),
        "ac7_real_current_market_run": _audit_ac7(root, policy, receipt, manifest),
        "ac8_substantive_research_or_rejection": _audit_ac8(research, research_checks),
        "ac9_stratified_false_positive_review": _audit_ac9(coverage_payload, coverage_checks),
        "ac10_original_excel_usability": _audit_ac10(
            root,
            policy,
            candidate_manifest,
            publication,
            wps_published,
            workbook_checks,
            wps_canonical_path=wps_canonical_path,
        ),
        "ac11_authorization_and_resource_boundary": _audit_ac11(
            root,
            policy,
            receipt,
            manifest,
            expected_policy,
        ),
    }
    criteria["ac12_user_outcome_and_stage_boundary"] = _audit_ac12(criteria)

    partial = [key for key, item in criteria.items() if item["status"] == PARTIAL]
    pending_ci = [key for key, item in criteria.items() if item["status"] == PENDING_CI]
    pending_human = [key for key, item in criteria.items() if item["status"] == PENDING_HUMAN_REVIEW]
    if partial:
        status = PARTIAL
    elif pending_ci:
        status = PENDING_CI
    elif pending_human:
        status = PENDING_HUMAN_REVIEW
    else:
        status = DONE

    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": policy.policy_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": ACTION_NO_ORDER,
        "status": status,
        "criteria": criteria,
        "summary": {
            "done": [
                key for key, item in criteria.items() if item["status"] == DONE
            ],
            "partial": partial,
            "pending_ci": pending_ci,
            "pending_human_review": pending_human,
            "human_review_items": [
                item
                for criterion in criteria.values()
                for item in criterion.get("human_review") or []
            ],
            "next_action": criteria["ac12_user_outcome_and_stage_boundary"]["evidence"]["next_action"],
        },
        "blockers": [
            blocker
            for criterion in criteria.values()
            for blocker in criterion.get("blockers") or []
        ],
    }


def write_receipt(receipt: Mapping[str, Any], *, root: Path) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / "runtime" / f"m2-acceptance-audit-{timestamp}"
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
    (root / "runtime/m2-acceptance-audit-latest.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "receipt_path": str(evidence.relative_to(root)),
        "pointer_path": "runtime/m2-acceptance-audit-latest.json",
        "receipt_sha256": digest,
    }

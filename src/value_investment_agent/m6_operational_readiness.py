"""Machine-only M6 operational readiness preflight.

This module inventories the repository's backup, restore, resource and
privacy safeguards before any production migration, scheduler change or
notification configuration is authorized. It never touches the server,
connects to a production database, creates an order or converts simulated
observations into real operational evidence.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "m6-operational-preflight-v1"
ACTION_NO_ORDER = "no_order"

DONE = "DONE"
PARTIAL = "PARTIAL"
GAP = "NOT_IMPLEMENTED"
NOT_STARTED = "NOT_STARTED"
REQUIRES_AUTHORIZATION = "REQUIRES_AUTHORIZATION"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_STAGE_STATUS = {
    DONE,
    PARTIAL,
    "PENDING_HUMAN_REVIEW",
    "PENDING_EXTERNAL_DATA",
    NOT_STARTED,
}
_REQUIRED_STAGE_KEYS = ("m1", "m2", "m3", "m4", "m5", "m6", "m7")
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".dump", ".sql.gz")
_SENSITIVE_NAME_MARKERS = ("password", "secret", "credential", "private_key")


@dataclass(frozen=True)
class RestoreTarget:
    host: str
    port: int
    database: str


@dataclass(frozen=True)
class M6PreflightConfig:
    target_rpo_hours: float
    target_rto_hours: float
    minimum_real_sessions: int
    minimum_real_events: int
    restore_target: RestoreTarget
    resource_limits: Mapping[str, int | float]
    required_files: tuple[str, ...]
    stage_status: Mapping[str, str]
    authorization_required: tuple[str, ...]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"M6 preflight config must be a JSON object: {path}")
    return payload


def _positive_number(value: Any, field: str, *, integer: bool = False) -> int | float:
    number = int(value) if integer else float(value)
    if number <= 0:
        raise ValueError(f"{field} must be positive")
    return number


def load_config(path: Path) -> M6PreflightConfig:
    payload = _load_json(path)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported M6 preflight schema version")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("M6 preflight config must be no_order")

    restore = payload.get("restore_target") or {}
    if not isinstance(restore, dict):
        raise ValueError("restore_target must be an object")
    restore_target = RestoreTarget(
        host=str(restore.get("host")),
        port=int(_positive_number(restore.get("port"), "restore_target.port", integer=True)),
        database=str(restore.get("database")),
    )
    if not restore_target.host or not restore_target.database:
        raise ValueError("restore_target host and database are required")

    resources = payload.get("resource_limits") or {}
    if not isinstance(resources, dict):
        raise ValueError("resource_limits must be an object")
    memory_mb = _positive_number(resources.get("memory_mb"), "resource_limits.memory_mb", integer=True)
    cpu_cores = _positive_number(resources.get("cpu_cores"), "resource_limits.cpu_cores")

    required_files = payload.get("required_files") or []
    if not isinstance(required_files, list) or not required_files:
        raise ValueError("required_files must be a non-empty list")

    stages = payload.get("stage_status") or {}
    if not isinstance(stages, dict) or set(stages) != set(_REQUIRED_STAGE_KEYS):
        raise ValueError("stage_status must contain exactly m1-m7")
    for key, value in stages.items():
        if value not in _ALLOWED_STAGE_STATUS:
            raise ValueError(f"Unsupported stage status for {key}: {value}")

    authorization = payload.get("authorization_required") or []
    if not isinstance(authorization, list) or not authorization:
        raise ValueError("authorization_required must be a non-empty list")

    return M6PreflightConfig(
        target_rpo_hours=float(_positive_number(payload.get("target_rpo_hours"), "target_rpo_hours")),
        target_rto_hours=float(_positive_number(payload.get("target_rto_hours"), "target_rto_hours")),
        minimum_real_sessions=int(_positive_number(
            payload.get("minimum_real_sessions"), "minimum_real_sessions", integer=True)),
        minimum_real_events=int(_positive_number(
            payload.get("minimum_real_events"), "minimum_real_events", integer=True)),
        restore_target=restore_target,
        resource_limits={"memory_mb": memory_mb, "cpu_cores": cpu_cores},
        required_files=tuple(str(item) for item in required_files),
        stage_status=dict(stages),
        authorization_required=tuple(str(item) for item in authorization),
    )


def _criterion(
    status: str,
    checks: Sequence[Mapping[str, Any]],
    *,
    blockers: Sequence[str] = (),
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "checks": [dict(item) for item in checks],
        "blockers": list(blockers),
    }
    if evidence:
        result["evidence"] = dict(evidence)
    return result


def _check(label: str, passed: bool, detail: str = "") -> dict[str, Any]:
    result = {"label": label, "passed": passed}
    if detail:
        result["detail"] = detail
    return result


def _read_text(root: Path, relative: str) -> str | None:
    path = root / relative
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(root: Path, relative: str) -> dict[str, Any]:
    text = _read_text(root, relative)
    if text is None:
        return {}
    payload = json.loads(text)
    return payload if isinstance(payload, dict) else {}


def _defined_functions(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _sensitive_tracked_files(tracked_files: Iterable[str]) -> list[str]:
    findings = []
    for relative in tracked_files:
        normalized = relative.replace("\\", "/").lower()
        if normalized == ".env" or normalized.endswith(".env.local"):
            findings.append(relative)
            continue
        suffix = Path(normalized).suffix
        if suffix in _SENSITIVE_SUFFIXES:
            findings.append(relative)
            continue
        if any(marker in normalized for marker in _SENSITIVE_NAME_MARKERS):
            findings.append(relative)
    return sorted(set(findings))


def audit_repository(
    root: Path,
    config: M6PreflightConfig,
    *,
    tracked_files: Iterable[str] = (),
    clean: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    missing_files = [
        relative for relative in config.required_files
        if not (root / relative).is_file()
    ]
    checks.append(_check(
        "required operational files exist",
        not missing_files,
        ", ".join(missing_files),
    ))

    drill = _read_text(root, "deploy/server/run_restore_drill.sh") or ""
    evidence_drill = _read_text(root, "deploy/server/test_evidence_in_restore.sh") or ""
    backup_source = _read_text(root, "src/value_investment_agent/backup.py") or ""
    security_source = _read_text(root, "src/value_investment_agent/backup_security.py") or ""
    security_functions = _defined_functions(security_source)
    security_policy = _read_json(root, "config/m6-backup-security-v1.json")
    checks.extend((
        _check(
            "restore drill is memory bounded",
            "--memory=256m" in drill and "--cpus=0.5" in drill,
        ),
        _check(
            "restore drill uses the isolated loopback database",
            "127.0.0.1:5433:5432" in drill and "value_agent_restore" in drill,
        ),
        _check(
            "restore drill removes the disposable container on exit",
            "trap 'podman rm -f value-investment-restore-postgres" in drill,
        ),
        _check(
            "evidence drill checks restored facts and hashes",
            "fair_value" in evidence_drill and "sha256 <> ''" in evidence_drill,
        ),
        _check(
            "backup code inventories original evidence hashes",
            "evidence_manifest" in backup_source and "sha256_file" in backup_source,
        ),
        _check(
            "backup code uses a transactional snapshot",
            "pg_export_snapshot" in backup_source and "REPEATABLE READ" in backup_source,
        ),
        _check(
            "restore target identity is explicitly validated",
            "validate_restore_target" in backup_source
            and "value_agent_restore" in backup_source
            and "127.0.0.1" in backup_source
            and "5433" in backup_source,
        ),
        _check(
            "restore uses clean/no-owner/no-acl and content checks",
            "--clean" in backup_source and "--no-owner" in backup_source
            and "--no-acl" in backup_source and "compare_checks" in backup_source,
        ),
    ))
    sensitive = _sensitive_tracked_files(tracked_files)
    checks.append(_check("tracked repository contains no obvious secrets", not sensitive, ", ".join(sensitive)))
    checks.append(_check("working tree is clean at audit time", clean))

    machine_failed = [item for item in checks if not item["passed"]]
    encryption_checks = [
        _check(
            "encrypted backup package has encrypt/decrypt implementations",
            {"encrypt_package", "decrypt_package"}.issubset(security_functions)
            and "AESGCM" in security_source,
        ),
        _check(
            "backup key loading and key-separation validation exist",
            {"load_key", "validate_key_separation"}.issubset(security_functions),
        ),
        _check(
            "config and release inventories are part of the manifest",
            {"_collect_named_items", "_manifest_payload"}.issubset(security_functions)
            and bool(security_policy.get("config_inventory"))
            and "release_inventory" in security_policy,
        ),
        _check(
            "offsite contract declares no_order and excludes the key",
            security_policy.get("action") == ACTION_NO_ORDER
            and "key_file"
            in (security_policy.get("offsite") or {}).get("forbidden_locations", []),
        ),
    ]
    status = PARTIAL if machine_failed or any(not item["passed"] for item in encryption_checks) else DONE
    blockers = [
        f"machine check failed: {item['label']}"
        for item in machine_failed
    ]
    if any(not item["passed"] for item in encryption_checks):
        blockers.append("encrypted offsite backup and key separation are not implemented")

    return _criterion(
        status,
        checks + encryption_checks,
        blockers=blockers,
        evidence={
            "resource_limits": dict(config.resource_limits),
            "restore_target": {
                "host": config.restore_target.host,
                "port": config.restore_target.port,
                "database": config.restore_target.database,
            },
        },
    )


def _parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} is not an ISO date: {value}") from exc


def assess_session_ledger(
    config: M6PreflightConfig,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    seen_dates: set[date] = set()
    failures: list[str] = []
    normalized = []
    for index, record in enumerate(records):
        if record.get("action") != ACTION_NO_ORDER:
            raise ValueError(f"session record {index} is not no_order")
        observed = record.get("observed")
        status = record.get("status")
        if observed not in {"actual", "simulated"}:
            raise ValueError(f"session record {index} has invalid observed value")
        if status not in {"success", "failed", "missing"}:
            raise ValueError(f"session record {index} has invalid status")
        session_date = _parse_date(record.get("session_date"), f"session {index} date")
        if session_date in seen_dates:
            raise ValueError(f"duplicate session date: {session_date}")
        seen_dates.add(session_date)
        if record.get("resource_baseline_ok") is not True:
            failures.append(f"{session_date}: resource baseline not confirmed")
        normalized.append({
            "session_date": session_date.isoformat(),
            "observed": observed,
            "status": status,
            "resource_baseline_ok": bool(record.get("resource_baseline_ok")),
            "real_event_materialized": bool(record.get("real_event_materialized")),
        })

    normalized.sort(key=lambda item: item["session_date"])
    eligible = [
        item for item in normalized
        if item["observed"] == "actual"
        and item["status"] == "success"
        and item["resource_baseline_ok"]
    ]
    latest_streak = 0
    for item in reversed(normalized):
        if (item["observed"] != "actual" or item["status"] != "success"
            or not item["resource_baseline_ok"]):
            break
        latest_streak += 1
    real_events = sum(
        item["observed"] == "actual" and item["real_event_materialized"]
        for item in normalized
    )
    simulated = sum(item["observed"] == "simulated" for item in normalized)
    criterion_status = NOT_STARTED
    if eligible:
        criterion_status = PARTIAL
    blockers = []
    if latest_streak < config.minimum_real_sessions:
        blockers.append(
            f"need {config.minimum_real_sessions} consecutive real sessions; current={latest_streak}"
        )
    if real_events < config.minimum_real_events:
        blockers.append(
            f"need {config.minimum_real_events} real financial/capital event; current={real_events}"
        )
    if eligible:
        blockers.append("session dates are not bound to an official exchange calendar and observation cutoff")
    return _criterion(
        criterion_status,
        [
            _check("all records are no_order", not failures),
            _check("no duplicate session dates", len(seen_dates) == len(records)),
            _check("reported latest session streak", latest_streak >= config.minimum_real_sessions, str(latest_streak)),
            _check("real event count", real_events >= config.minimum_real_events, str(real_events)),
            _check("simulated sessions are excluded", True, str(simulated)),
            _check("official exchange calendar and cutoff verified", False),
        ],
        blockers=blockers,
        evidence={
            "eligible_sessions": len(eligible),
            "latest_streak": latest_streak,
            "real_events": real_events,
            "simulated_sessions": simulated,
            "failures": failures,
        },
    )


def assess_restore_evidence(
    config: M6PreflightConfig,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not records:
        return _criterion(
            NOT_STARTED,
            [_check("an actual isolated restore drill exists", False)],
            blockers=["no real restore drill has been recorded"],
        )
    normalized = []
    for index, record in enumerate(records):
        if record.get("action") != ACTION_NO_ORDER:
            raise ValueError(f"restore record {index} is not no_order")
        if record.get("observed") != "actual":
            continue
        if record.get("status") != "passed":
            continue
        backup_id = str(record.get("backup_id") or "")
        sha256 = str(record.get("sha256") or "").lower()
        if not backup_id or not _SHA256.fullmatch(sha256):
            raise ValueError(f"restore record {index} has invalid identity")
        target = record.get("target") or {}
        if (
            target.get("host") != config.restore_target.host
            or str(target.get("port")) != str(config.restore_target.port)
            or target.get("database") != config.restore_target.database
        ):
            raise ValueError(f"restore record {index} targets the wrong database")
        rpo_seconds = float(record.get("rpo_seconds"))
        rto_seconds = float(record.get("rto_seconds"))
        if rpo_seconds < 0 or rto_seconds < 0:
            raise ValueError(f"restore record {index} has negative timing")
        normalized.append({
            "backup_id": backup_id,
            "sha256": sha256,
            "rpo_seconds": rpo_seconds,
            "rto_seconds": rto_seconds,
            "table_check_count": int(record.get("table_check_count") or 0),
            "evidence_files": int(record.get("evidence_files") or 0),
            "verified_at": str(record.get("verified_at") or ""),
        })
    if not normalized:
        return _criterion(
            NOT_STARTED,
            [_check("an actual successful restore drill exists", False)],
            blockers=["no actual successful restore drill has been recorded"],
        )
    latest = max(normalized, key=lambda item: item["verified_at"])
    within_targets = (
        latest["rpo_seconds"] <= config.target_rpo_hours * 3600
        and latest["rto_seconds"] <= config.target_rto_hours * 3600
    )
    complete = latest["table_check_count"] > 0 and latest["evidence_files"] > 0
    status = PARTIAL
    blockers = []
    if not within_targets:
        blockers.append(
            f"latest drill exceeds RPO/RTO target: rpo={latest['rpo_seconds']}s rto={latest['rto_seconds']}s"
        )
    if not complete:
        blockers.append("latest drill lacks table or evidence verification")
    blockers.append("restore summary is not bound to a verified manifest, dump and isolated restore result")
    return _criterion(
        status,
        [
            _check("declared restore target matches isolated database config", True),
            _check("reported drill has content checks", complete),
            _check("reported drill meets RPO/RTO targets", within_targets),
            _check("restore artifacts and verifier result independently bound", False),
        ],
        blockers=blockers,
        evidence=latest,
    )


def build_preflight_receipt(
    root: Path,
    config_path: Path,
    *,
    tracked_files: Iterable[str] = (),
    clean: bool = True,
    session_records: Sequence[Mapping[str, Any]] = (),
    restore_records: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    config = load_config(config_path)
    repository = audit_repository(
        root,
        config,
        tracked_files=tracked_files,
        clean=clean,
    )
    sessions = assess_session_ledger(config, session_records)
    restore = assess_restore_evidence(config, restore_records)
    prerequisites_complete = all(
        config.stage_status[key] == DONE for key in ("m1", "m2", "m3", "m4", "m5")
    )
    prerequisites = _criterion(
        DONE if prerequisites_complete else PARTIAL,
        [
            _check(
                "M1-M5 product stages are accepted",
                prerequisites_complete,
                json.dumps(config.stage_status, ensure_ascii=False),
            )
        ],
        blockers=[] if prerequisites_complete else ["M1-M5 product acceptance is incomplete"],
        evidence={"stage_status": config.stage_status},
    )
    authorization = _criterion(
        REQUIRES_AUTHORIZATION,
        [_check("production authorization receipt exists", False)],
        blockers=["production migration, scheduling, notification and data scope are not authorized"],
        evidence={"required_items": list(config.authorization_required)},
    )
    criteria = {
        "m6c1_product_prerequisites": prerequisites,
        "m6c2_repository_and_privacy": repository,
        "m6c3_isolated_restore_mechanism": _criterion(
            DONE,
            [_check("backup/restore unit and failure tests exist", True)],
        ),
        "m6c4_real_restore_rpo_rto": restore,
        "m6c5_real_sessions_and_events": sessions,
        "m6c6_production_authorization": authorization,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": ACTION_NO_ORDER,
        "engineering_status": repository["status"],
        "operational_acceptance_status": NOT_STARTED,
        "criteria": criteria,
        "summary": {
            "done": [key for key, item in criteria.items() if item["status"] == DONE],
            "partial": [key for key, item in criteria.items() if item["status"] == PARTIAL],
            "not_implemented": [key for key, item in criteria.items() if item["status"] == GAP],
            "requires_authorization": [
                key for key, item in criteria.items()
                if item["status"] == REQUIRES_AUTHORIZATION
            ],
            "blockers": [
                blocker
                for item in criteria.values()
                for blocker in item.get("blockers") or []
            ],
            "next_action": (
                "绑定 M6 官方交易日历与隔离恢复原始证据；继续 M5/M7 独立工作。"
                "M4 私人输入和 M6 生产启用仅阻断各自依赖节点。"
            ),
        },
    }


def write_receipt(receipt: Mapping[str, Any], *, root: Path) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / "runtime" / f"m6-operational-preflight-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    evidence = target / "receipt.json"
    evidence.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    import hashlib

    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    pointer = {"path": str(target.relative_to(root)), "sha256": digest}
    (root / "runtime/m6-operational-preflight-latest.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "receipt_path": str(evidence.relative_to(root)),
        "pointer_path": "runtime/m6-operational-preflight-latest.json",
        "receipt_sha256": digest,
    }

"""Local-only disposable PostgreSQL cold replay for the M1 application.

The runner creates a loopback-only PostgreSQL cluster from the optional
``postgresql-binaries`` package, replays the three real M1 input descriptors
through the shared application service, stops the cluster, starts it again from
the same data directory, and verifies every stored artifact hash.

No production DSN, Docker Desktop, SSH, persistent service, or order path is
used by this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from typing import Any, Mapping, Sequence

from .m1_valuation_package_builder import build_package_descriptor_attempts
from .research_application import ResearchApplicationService
from .research_artifact_repository import PostgresResearchArtifactRepository
from .research_input import build_research_run_spec


SCHEMA_VERSION = "m1-postgres-cold-replay-v1"
LOOPBACK_HOST = "127.0.0.1"
POSTGRES_USER = "postgres"
POSTGRES_DATABASE = "postgres"
APPLICATION_POINTER = Path("runtime") / "m1-research-application-latest.json"


class PostgresColdReplayError(RuntimeError):
    """Base error for local replay infrastructure failures."""


class PostgresBinaryUnavailable(PostgresColdReplayError):
    """Raised when a local PostgreSQL binary installation cannot be found."""


def _creation_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


def _clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "PGDATA",
        "PGDATABASE",
        "PGHOST",
        "PGPASSWORD",
        "PGPORT",
        "PGUSER",
        "PGSERVICE",
    ):
        env.pop(key, None)
    return env


def _run_binary(
    command: Sequence[str],
    label: str,
    *,
    capture_output: bool = True,
) -> str:
    stdout = subprocess.PIPE if capture_output else subprocess.DEVNULL
    try:
        completed = subprocess.run(
            [str(item) for item in command],
            stdout=stdout,
            stderr=subprocess.STDOUT if capture_output else subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_creation_flags(),
            timeout=180,
            check=False,
            env=_clean_environment(),
        )
    except FileNotFoundError as error:
        raise PostgresBinaryUnavailable(
            f"{label} binary was not found: {command[0]}"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise PostgresColdReplayError(f"{label} timed out") from error

    output = (completed.stdout or "").strip() if capture_output else ""
    if completed.returncode != 0:
        detail = output[-4000:] if output else "no output"
        raise PostgresColdReplayError(f"{label} failed ({detail})")
    return output


def _executable(bin_dir: Path, name: str) -> Path:
    if os.name == "nt":
        candidate = bin_dir / f"{name}.exe"
        return candidate if candidate.is_file() else bin_dir / name
    return bin_dir / name


def _has_postgres_binaries(bin_dir: Path) -> bool:
    if not bin_dir.is_dir():
        return False
    return _executable(bin_dir, "initdb").is_file() and _executable(
        bin_dir, "pg_ctl"
    ).is_file()


def resolve_postgres_bin_dir(explicit: str | Path | None = None) -> Path:
    """Resolve an optional local PostgreSQL installation."""
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if not _has_postgres_binaries(candidate):
            raise PostgresBinaryUnavailable(
                f"Configured PostgreSQL bin directory is incomplete: {candidate}"
            )
        return candidate

    configured = os.environ.get("M1_POSTGRES_BIN_DIR")
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if not _has_postgres_binaries(candidate):
            raise PostgresBinaryUnavailable(
                f"M1_POSTGRES_BIN_DIR is incomplete: {candidate}"
            )
        return candidate

    try:
        import postgresql_binaries

        candidate = Path(postgresql_binaries.bin()).resolve()
    except Exception:
        candidate = None
    if candidate is not None and _has_postgres_binaries(candidate):
        return candidate

    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    if initdb and pg_ctl:
        initdb_dir = Path(initdb).resolve().parent
        if Path(pg_ctl).resolve().parent == initdb_dir:
            return initdb_dir

    raise PostgresBinaryUnavailable(
        "No local PostgreSQL binaries found. Install postgresql-binaries in "
        "the isolated .m1-postgres-venv virtual environment."
    )


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOOPBACK_HOST, 0))
        return int(sock.getsockname()[1])


class PostgresClusterManager:
    """Manage one fresh loopback-only PostgreSQL data directory."""

    def __init__(
        self,
        *,
        bin_dir: Path,
        data_dir: Path,
        log_path: Path,
        port: int | None = None,
    ) -> None:
        self.bin_dir = resolve_postgres_bin_dir(bin_dir)
        self.data_dir = data_dir.resolve()
        self.log_path = log_path.resolve()
        self.port = int(port or _free_loopback_port())
        if not 1 <= self.port <= 65535:
            raise PostgresColdReplayError(f"Invalid loopback port: {self.port}")
        self._running = False

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{POSTGRES_USER}@{LOOPBACK_HOST}:{self.port}/"
            f"{POSTGRES_DATABASE}"
        )

    def initialize(self) -> None:
        if (self.data_dir / "PG_VERSION").exists():
            raise PostgresColdReplayError(
                f"PostgreSQL data directory is already initialized: {self.data_dir}"
            )
        if self.data_dir.exists() and any(self.data_dir.iterdir()):
            raise PostgresColdReplayError(
                f"PostgreSQL data directory must be empty: {self.data_dir}"
            )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        _run_binary(
            [
                _executable(self.bin_dir, "initdb"),
                "-D",
                self.data_dir,
                "-U",
                POSTGRES_USER,
                "--auth-host=trust",
                "--auth-local=trust",
                "--encoding=UTF8",
                "--no-locale",
            ],
            "initdb",
        )

    def start(self) -> None:
        if self._running:
            return
        _run_binary(
            [
                _executable(self.bin_dir, "pg_ctl"),
                "-D",
                self.data_dir,
                "-l",
                self.log_path,
                "-o",
                f"-p {self.port} -h {LOOPBACK_HOST}",
                "-w",
                "-t",
                "30",
                "start",
            ],
            "pg_ctl start",
            capture_output=False,
        )
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        _run_binary(
            [
                _executable(self.bin_dir, "pg_ctl"),
                "-D",
                self.data_dir,
                "-m",
                "fast",
                "-w",
                "-t",
                "30",
                "stop",
            ],
            "pg_ctl stop",
        )
        self._running = False


def _decode_canonical_bytes(value: Any) -> str:
    if isinstance(value, memoryview):
        return value.tobytes().decode("utf-8")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8")
    if isinstance(value, str):
        return value
    raise PostgresColdReplayError(
        f"Unsupported canonical payload database type: {type(value).__name__}"
    )


def _query_counts(repository: PostgresResearchArtifactRepository) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    with repository.connection.cursor() as cursor:
        for table in (
            "research_artifacts",
            "research_artifact_heads",
            "research_artifact_references",
        ):
            cursor.execute(f"SELECT count(*) FROM {table}")
            counts[table] = int(cursor.fetchone()["count"])
        cursor.execute("SELECT version()")
        counts["_postgres_version"] = str(cursor.fetchone()["version"])
    return counts


def _snapshot_rows(
    repository: PostgresResearchArtifactRepository,
) -> tuple[list[dict[str, Any]], str, bool]:
    rows: list[dict[str, Any]] = []
    with repository.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT artifact_id, scope_type, scope_key, artifact_type,
                   schema_version, as_of, available_at, payload_sha256,
                   canonical_payload, evidence_refs, run_id, created_at
            FROM research_artifacts
            ORDER BY artifact_id
            """
        )
        for row in cursor.fetchall():
            canonical = _decode_canonical_bytes(row["canonical_payload"])
            payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            rows.append(
                {
                    "artifact_id": str(row["artifact_id"]),
                    "scope_type": str(row["scope_type"]),
                    "scope_key": str(row["scope_key"]),
                    "artifact_type": str(row["artifact_type"]),
                    "schema_version": str(row["schema_version"]),
                    "as_of": (
                        row["as_of"].isoformat() if row["as_of"] is not None else None
                    ),
                    "available_at": row["available_at"].isoformat(),
                    "payload_sha256": str(row["payload_sha256"]).lower(),
                    "payload": json.loads(canonical),
                    "evidence_refs": row["evidence_refs"],
                    "run_id": str(row["run_id"]),
                    "created_at": row["created_at"].isoformat(),
                    "payload_hash_matched": payload_hash
                    == str(row["payload_sha256"]).lower(),
                }
            )
    fingerprint_source = [
        {
            "artifact_id": item["artifact_id"],
            "scope_type": item["scope_type"],
            "scope_key": item["scope_key"],
            "artifact_type": item["artifact_type"],
            "schema_version": item["schema_version"],
            "as_of": item["as_of"],
            "available_at": item["available_at"],
            "payload_sha256": item["payload_sha256"],
            "payload": item["payload"],
            "evidence_refs": item["evidence_refs"],
            "run_id": item["run_id"],
        }
        for item in rows
    ]
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_source,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return rows, fingerprint, all(item["payload_hash_matched"] for item in rows)


def _artifact_summaries(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "artifact_id": str(item["artifact_id"]),
            "scope_type": str(item["scope_type"]),
            "scope_key": str(item["scope_key"]),
            "artifact_type": str(item["artifact_type"]),
            "payload_sha256": str(item["payload_sha256"]),
            "run_id": str(item["run_id"]),
        }
        for item in rows
    ]


def _application_evidence_hash(root: Path) -> str | None:
    pointer_path = root / APPLICATION_POINTER
    if not pointer_path.is_file():
        return None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    target = (root / pointer["path"] / "evidence.json").resolve()
    if not target.is_relative_to(root.resolve()):
        raise PostgresColdReplayError("M1 application pointer escapes project root")
    expected = str(pointer.get("sha256") or "").lower()
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if not expected or actual != expected:
        raise PostgresColdReplayError("M1 application evidence hash changed")
    return actual


def _package_fingerprints(root: Path) -> list[dict[str, str]]:
    paths = sorted(
        [
            *((root / "config" / "m1-valuation-packages-v1").glob("*.json")),
            *((root / "config" / "m1-distribution-packages-v1").glob("*.json")),
        ],
        key=lambda path: str(path),
    )
    return [
        {
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths
    ]


def run_m1_postgres_cold_replay(
    *,
    root: str | Path,
    work_dir: str | Path,
    postgres_bin_dir: str | Path | None = None,
    port: int | None = None,
    keep_data: bool = True,
) -> dict[str, Any]:
    """Replay real M1 inputs into PostgreSQL and cold-restart the cluster."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise PostgresColdReplayError(f"Project root is missing: {root}")
    work_dir = Path(work_dir).resolve()
    if not work_dir.is_relative_to(root):
        raise PostgresColdReplayError("Cold replay work directory escapes project root")
    work_dir.mkdir(parents=True, exist_ok=True)

    data_dir = work_dir / "postgres-data"
    log_path = work_dir / "postgres.log"
    if data_dir.exists() and any(data_dir.iterdir()):
        raise PostgresColdReplayError(
            f"Cold replay data directory must be fresh: {data_dir}"
        )

    bin_dir = resolve_postgres_bin_dir(postgres_bin_dir)
    manager = PostgresClusterManager(
        bin_dir=bin_dir,
        data_dir=data_dir,
        log_path=log_path,
        port=port,
    )
    repository: PostgresResearchArtifactRepository | None = None
    manager.initialize()

    try:
        first_started_at = datetime.now(timezone.utc)
        first_started_monotonic = time.perf_counter()
        manager.start()
        repository = PostgresResearchArtifactRepository(manager.dsn)
        repository.migrate()

        attempts = build_package_descriptor_attempts(root)
        if len(attempts) != 3:
            raise PostgresColdReplayError(
                f"M1 PostgreSQL replay expects 3 packages, got {len(attempts)}"
            )
        if any(attempt.descriptor is None or attempt.error for attempt in attempts):
            failures = [
                {
                    "package_id": attempt.package_id,
                    "symbol": attempt.symbol,
                    "error": attempt.error,
                }
                for attempt in attempts
                if attempt.error
            ]
            raise PostgresColdReplayError(
                f"M1 input descriptor failed: {json.dumps(failures)}"
            )

        service = ResearchApplicationService(repository)
        outcomes = []
        for attempt in attempts:
            assert attempt.descriptor is not None
            outcome = service.run_company_research(
                build_research_run_spec(attempt.descriptor)
            )
            action = getattr(outcome.current_status, "action", None)
            if action is not None and action != "no_order":
                raise PostgresColdReplayError(
                    f"M1 replay violated no_order contract: {outcome.symbol}"
                )
            outcomes.append(outcome)

        first_rows, first_fingerprint, first_hashes_matched = _snapshot_rows(
            repository
        )
        if not first_hashes_matched:
            raise PostgresColdReplayError(
                "PostgreSQL rows failed their initial payload hash check"
            )
        first_counts = _query_counts(repository)
        first_completed_at = datetime.now(timezone.utc)
        first_duration_seconds = time.perf_counter() - first_started_monotonic
        postgres_version = first_counts["_postgres_version"]
        repository.close()
        repository = None

        manager.stop()
        restart_started_at = datetime.now(timezone.utc)
        restart_started_monotonic = time.perf_counter()
        manager.start()
        repository = PostgresResearchArtifactRepository(manager.dsn)
        second_rows, second_fingerprint, second_hashes_matched = _snapshot_rows(
            repository
        )
        second_counts = _query_counts(repository)
        if not second_hashes_matched:
            raise PostgresColdReplayError(
                "PostgreSQL rows failed their cold-restart hash check"
            )
        if second_fingerprint != first_fingerprint:
            raise PostgresColdReplayError(
                "PostgreSQL artifact semantics changed after cold restart"
            )
        if second_counts.get("research_artifacts") != len(first_rows):
            raise PostgresColdReplayError(
                "PostgreSQL artifact count changed after restart"
            )

        verified: list[dict[str, Any]] = []
        for row in first_rows:
            stored = repository.load_by_id(row["artifact_id"])
            verification = repository.verify(stored)
            if verification.get("verified") is not True:
                raise PostgresColdReplayError(
                    f"Cold-restarted artifact failed verification: {stored.artifact_id}"
                )
            restored = stored.envelope.payload_object()
            if restored != row["payload"]:
                raise PostgresColdReplayError(
                    f"Cold-restarted artifact payload changed: {stored.artifact_id}"
                )
            verified.append(
                {
                    "artifact_id": stored.artifact_id,
                    "payload_sha256": verification["payload_sha256"],
                    "verified": True,
                }
            )

        restart_completed_at = datetime.now(timezone.utc)
        restart_duration_seconds = time.perf_counter() - restart_started_monotonic
        repository.close()
        repository = None

        receipt = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "PASSED",
            "action": "no_order",
            "postgres_version": postgres_version,
            "host": LOOPBACK_HOST,
            "port": manager.port,
            "data_dir": str(data_dir.relative_to(root)),
            "log_path": str(log_path.relative_to(root)),
            "application_evidence_sha256": _application_evidence_hash(root),
            "package_fingerprints": _package_fingerprints(root),
            "first_run": {
                "started_at": first_started_at.isoformat(),
                "completed_at": first_completed_at.isoformat(),
                "duration_seconds": round(first_duration_seconds, 3),
                "artifact_count": len(first_rows),
                "artifact_fingerprint": first_fingerprint,
                "table_counts": {
                    key: value
                    for key, value in first_counts.items()
                    if not key.startswith("_")
                },
                "outcomes": [
                    {
                        "symbol": outcome.symbol,
                        "status": outcome.status,
                        "action": getattr(
                            outcome.current_status, "action", None
                        ),
                        "artifact_count": len(outcome.stored_artifacts),
                        "blockers": list(outcome.blockers),
                    }
                    for outcome in outcomes
                ],
            },
            "cold_restart": {
                "started_at": restart_started_at.isoformat(),
                "completed_at": restart_completed_at.isoformat(),
                "duration_seconds": round(restart_duration_seconds, 3),
                "verified_artifact_count": len(verified),
                "semantic_equality": True,
                "artifact_fingerprint": second_fingerprint,
                "table_counts": {
                    key: value
                    for key, value in second_counts.items()
                    if not key.startswith("_")
                },
                "verified_artifacts": verified,
            },
            "artifacts": _artifact_summaries(first_rows),
        }

        receipt_path = work_dir / "receipt.json"
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        receipt_digest = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        manifest_path = work_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "PASSED",
                    "action": "no_order",
                    "receipt_path": receipt_path.name,
                    "receipt_sha256": receipt_digest,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            **receipt,
            "receipt_path": str(receipt_path.relative_to(root)),
            "manifest_path": str(manifest_path.relative_to(root)),
            "receipt_sha256": receipt_digest,
        }
    finally:
        if repository is not None:
            repository.close()
        manager.stop()
        if not keep_data and data_dir.exists():
            shutil.rmtree(data_dir)

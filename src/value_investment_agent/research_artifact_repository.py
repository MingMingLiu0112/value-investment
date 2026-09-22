"""Repository implementations for immutable research artifacts.

The in-memory implementation is deterministic and offline. The PostgreSQL
implementation owns all psycopg and SQL conversion; domain objects never import
or depend on it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Protocol, Sequence

import psycopg
from psycopg.rows import dict_row

from .research_artifact_codecs import artifact_payload
from .research_artifacts import (
    ResearchArtifactEnvelope,
    ResearchArtifactHead,
    ResearchArtifactIdentity,
    StoredResearchArtifact,
    parse_stored_artifact_payload,
)


DEFAULT_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "sql" / "20260922_research_artifacts.sql"
)


class ResearchArtifactRepository(Protocol):
    def save(
        self,
        envelope: ResearchArtifactEnvelope,
        *,
        advance_head: bool = True,
    ) -> StoredResearchArtifact: ...

    def save_object(
        self,
        value: Any,
        *,
        identity: ResearchArtifactIdentity,
        evidence_refs: Sequence[dict[str, Any]] = (),
        run_id: str,
        advance_head: bool = True,
    ) -> StoredResearchArtifact: ...

    def load_by_id(self, artifact_id: str) -> StoredResearchArtifact: ...

    def load_by_hash(
        self,
        payload_sha256: str,
        *,
        scope_type: str | None = None,
        scope_key: str | None = None,
        artifact_type: str | None = None,
    ) -> list[StoredResearchArtifact]: ...

    def load_latest(
        self,
        scope_type: str,
        scope_key: str,
        artifact_type: str,
    ) -> StoredResearchArtifact: ...

    def list_versions(
        self,
        scope_type: str,
        scope_key: str,
        artifact_type: str,
        *,
        limit: int = 100,
    ) -> list[StoredResearchArtifact]: ...

    def verify(self, artifact: StoredResearchArtifact) -> dict[str, Any]: ...


class InMemoryResearchArtifactRepository:
    """Offline repository used by deterministic core tests."""

    def __init__(self) -> None:
        self._artifacts: dict[str, StoredResearchArtifact] = {}
        self._by_hash: dict[str, list[str]] = {}
        self._versions: dict[tuple[str, str, str], list[str]] = {}
        self._heads: dict[tuple[str, str, str], str] = {}
        self._counter = 0

    def _key(self, identity: ResearchArtifactIdentity) -> tuple[str, str, str]:
        return (identity.scope_type, identity.scope_key, identity.artifact_type)

    def _next_id(self) -> str:
        self._counter += 1
        return f"00000000-0000-0000-0000-{self._counter:012d}"

    def save(
        self,
        envelope: ResearchArtifactEnvelope,
        *,
        advance_head: bool = True,
    ) -> StoredResearchArtifact:
        natural_key = envelope.natural_key()
        existing = next(
            (
                artifact
                for artifact in self._artifacts.values()
                if artifact.envelope.natural_key() == natural_key
            ),
            None,
        )
        if existing is not None:
            return existing

        artifact_id = self._next_id()
        stored = StoredResearchArtifact(
            artifact_id=artifact_id,
            envelope=envelope,
            created_at=datetime.now(timezone.utc),
        )
        self._artifacts[artifact_id] = stored
        self._by_hash.setdefault(envelope.payload_sha256, []).append(artifact_id)
        key = self._key(envelope.identity)
        self._versions.setdefault(key, []).append(artifact_id)
        if advance_head:
            current_head = self._heads.get(key)
            current = (
                self._artifacts[current_head].envelope.identity
                if current_head is not None
                else None
            )
            if current is None or envelope.identity.available_at >= current.available_at:
                self._heads[key] = artifact_id
        return stored

    def save_object(
        self,
        value: Any,
        *,
        identity: ResearchArtifactIdentity,
        evidence_refs: Sequence[dict[str, Any]] = (),
        run_id: str,
        advance_head: bool = True,
    ) -> StoredResearchArtifact:
        artifact_type, payload = artifact_payload(value)
        if artifact_type != identity.artifact_type:
            raise ValueError(
                f"Object codec type {artifact_type} does not match identity {identity.artifact_type}"
            )
        envelope = ResearchArtifactEnvelope.build(
            identity=identity,
            payload=payload,
            evidence_refs=evidence_refs,
            run_id=run_id,
        )
        return self.save(envelope, advance_head=advance_head)

    def load_by_id(self, artifact_id: str) -> StoredResearchArtifact:
        try:
            artifact = self._artifacts[artifact_id]
        except KeyError as error:
            raise KeyError(f"Unknown research artifact id: {artifact_id}") from error
        self.verify(artifact)
        return artifact

    def load_by_hash(
        self,
        payload_sha256: str,
        *,
        scope_type: str | None = None,
        scope_key: str | None = None,
        artifact_type: str | None = None,
    ) -> list[StoredResearchArtifact]:
        result = [
            self.load_by_id(artifact_id)
            for artifact_id in self._by_hash.get(payload_sha256, [])
        ]
        if scope_type is not None:
            result = [
                item
                for item in result
                if item.envelope.identity.scope_type == scope_type
            ]
        if scope_key is not None:
            result = [
                item
                for item in result
                if item.envelope.identity.scope_key == scope_key
            ]
        if artifact_type is not None:
            result = [
                item
                for item in result
                if item.envelope.identity.artifact_type == artifact_type
            ]
        return result

    def load_latest(
        self,
        scope_type: str,
        scope_key: str,
        artifact_type: str,
    ) -> StoredResearchArtifact:
        key = (scope_type, scope_key, artifact_type)
        artifact_id = self._heads.get(key)
        if artifact_id is None:
            raise KeyError(
                f"No research artifact head for {scope_type}:{scope_key}:{artifact_type}"
            )
        return self.load_by_id(artifact_id)

    def list_versions(
        self,
        scope_type: str,
        scope_key: str,
        artifact_type: str,
        *,
        limit: int = 100,
    ) -> list[StoredResearchArtifact]:
        ids = self._versions.get((scope_type, scope_key, artifact_type), [])
        result = [self.load_by_id(item) for item in ids[-limit:]]
        return sorted(
            result,
            key=lambda item: (
                item.envelope.identity.available_at,
                item.created_at,
            ),
            reverse=True,
        )

    def verify(self, artifact: StoredResearchArtifact) -> dict[str, Any]:
        parse_stored_artifact_payload(artifact)
        return {
            "artifact_id": artifact.artifact_id,
            "payload_sha256": artifact.envelope.payload_sha256,
            "verified": True,
        }

    def head(self, scope_type: str, scope_key: str, artifact_type: str) -> ResearchArtifactHead:
        artifact = self.load_latest(scope_type, scope_key, artifact_type)
        envelope = artifact.envelope
        return ResearchArtifactHead(
            scope_type=scope_type,
            scope_key=scope_key,
            artifact_type=artifact_type,
            artifact_id=artifact.artifact_id,
            schema_version=envelope.identity.schema_version,
            as_of=envelope.identity.as_of,
            available_at=envelope.identity.available_at,
            payload_sha256=envelope.payload_sha256,
            updated_at=artifact.created_at,
        )


def _decode_bytes(value: Any) -> str:
    if isinstance(value, memoryview):
        return value.tobytes().decode("utf-8")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8")
    if isinstance(value, str):
        return value
    raise ValueError("Canonical payload stored in an unsupported PostgreSQL type")


class PostgresResearchArtifactRepository:
    """Disposable/local PostgreSQL implementation; never use a production DSN."""

    def __init__(
        self,
        dsn: str,
        *,
        migration_path: Path | str = DEFAULT_MIGRATION_PATH,
    ) -> None:
        self._dsn = dsn
        self._migration_path = Path(migration_path)
        self._connection: Any | None = None

    @property
    def connection(self) -> Any:
        if self._connection is None or self._connection.closed:
            self._connection = psycopg.connect(self._dsn, row_factory=dict_row)
        return self._connection

    def close(self) -> None:
        if self._connection is not None and not self._connection.closed:
            self._connection.close()

    def migrate(self) -> None:
        sql = self._migration_path.read_text(encoding="utf-8")
        with self.connection.cursor() as cursor:
            cursor.execute(sql)
        self.connection.commit()

    def _insert_references(
        self,
        cursor: Any,
        artifact_id: str,
        envelope: ResearchArtifactEnvelope,
    ) -> None:
        for ref in envelope.evidence_refs:
            cursor.execute(
                """
                INSERT INTO research_artifact_references (
                  artifact_id, reference_id, reference_kind,
                  referenced_artifact_id, external_uri, external_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (artifact_id, reference_id) DO NOTHING
                """,
                (
                    artifact_id,
                    str(ref["id"]),
                    ref.get("kind"),
                    ref.get("artifact_id"),
                    ref.get("uri") or ref.get("url") or ref.get("path"),
                    ref.get("sha256"),
                ),
            )

    def save(
        self,
        envelope: ResearchArtifactEnvelope,
        *,
        advance_head: bool = True,
    ) -> StoredResearchArtifact:
        canonical_bytes = envelope.canonical_payload.encode("utf-8")
        evidence = json.dumps(
            envelope.evidence_refs, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO research_artifacts (
                  scope_type, scope_key, artifact_type, schema_version,
                  as_of, available_at, payload_sha256, canonical_payload,
                  evidence_refs, run_id, natural_key
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (natural_key) DO NOTHING
                RETURNING artifact_id, created_at
                """,
                (
                    envelope.identity.scope_type,
                    envelope.identity.scope_key,
                    envelope.identity.artifact_type,
                    envelope.identity.schema_version,
                    envelope.identity.as_of,
                    envelope.identity.available_at,
                    envelope.payload_sha256,
                    psycopg.Binary(canonical_bytes),
                    evidence,
                    envelope.run_id,
                    envelope.natural_key(),
                ),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    SELECT artifact_id, created_at
                    FROM research_artifacts
                    WHERE natural_key = %s
                    """,
                    (envelope.natural_key(),),
                )
                row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Research artifact insert did not produce a row")
            artifact_id = str(row["artifact_id"])
            created_at = row["created_at"]
            self._insert_references(cursor, artifact_id, envelope)
            if advance_head:
                cursor.execute(
                    """
                    INSERT INTO research_artifact_heads (
                      scope_type, scope_key, artifact_type, artifact_id,
                      schema_version, as_of, available_at, payload_sha256
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (scope_type, scope_key, artifact_type)
                    DO UPDATE SET
                      artifact_id = EXCLUDED.artifact_id,
                      schema_version = EXCLUDED.schema_version,
                      as_of = EXCLUDED.as_of,
                      available_at = EXCLUDED.available_at,
                      payload_sha256 = EXCLUDED.payload_sha256,
                      updated_at = now()
                    WHERE research_artifact_heads.available_at <= EXCLUDED.available_at
                    """,
                    (
                        envelope.identity.scope_type,
                        envelope.identity.scope_key,
                        envelope.identity.artifact_type,
                        artifact_id,
                        envelope.identity.schema_version,
                        envelope.identity.as_of,
                        envelope.identity.available_at,
                        envelope.payload_sha256,
                    ),
                )
        self.connection.commit()
        return self.load_by_id(artifact_id)

    def save_object(
        self,
        value: Any,
        *,
        identity: ResearchArtifactIdentity,
        evidence_refs: Sequence[dict[str, Any]] = (),
        run_id: str,
        advance_head: bool = True,
    ) -> StoredResearchArtifact:
        artifact_type, payload = artifact_payload(value)
        if artifact_type != identity.artifact_type:
            raise ValueError(
                f"Object codec type {artifact_type} does not match identity {identity.artifact_type}"
            )
        envelope = ResearchArtifactEnvelope.build(
            identity=identity,
            payload=payload,
            evidence_refs=evidence_refs,
            run_id=run_id,
        )
        return self.save(envelope, advance_head=advance_head)

    def _load_row(self, row: dict[str, Any]) -> StoredResearchArtifact:
        identity = ResearchArtifactIdentity(
            scope_type=str(row["scope_type"]),
            scope_key=str(row["scope_key"]),
            artifact_type=str(row["artifact_type"]),
            schema_version=str(row["schema_version"]),
            as_of=row["as_of"],
            available_at=row["available_at"],
        )
        envelope = ResearchArtifactEnvelope(
            identity=identity,
            canonical_payload=_decode_bytes(row["canonical_payload"]),
            payload_sha256=str(row["payload_sha256"]).lower(),
            evidence_refs=list(row["evidence_refs"] or []),
            run_id=str(row["run_id"]),
        )
        return StoredResearchArtifact(
            artifact_id=str(row["artifact_id"]),
            envelope=envelope,
            created_at=row["created_at"],
        )

    def load_by_id(self, artifact_id: str) -> StoredResearchArtifact:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT artifact_id, scope_type, scope_key, artifact_type,
                       schema_version, as_of, available_at, payload_sha256,
                       canonical_payload, evidence_refs, run_id, created_at
                FROM research_artifacts
                WHERE artifact_id = %s
                """,
                (artifact_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Unknown research artifact id: {artifact_id}")
        artifact = self._load_row(row)
        self.verify(artifact)
        return artifact

    def load_by_hash(
        self,
        payload_sha256: str,
        *,
        scope_type: str | None = None,
        scope_key: str | None = None,
        artifact_type: str | None = None,
    ) -> list[StoredResearchArtifact]:
        clauses = ["payload_sha256 = %s"]
        params: list[Any] = [payload_sha256.lower()]
        if scope_type is not None:
            clauses.append("scope_type = %s")
            params.append(scope_type)
        if scope_key is not None:
            clauses.append("scope_key = %s")
            params.append(scope_key)
        if artifact_type is not None:
            clauses.append("artifact_type = %s")
            params.append(artifact_type)
        query = (
            """
            SELECT artifact_id, scope_type, scope_key, artifact_type,
                   schema_version, as_of, available_at, payload_sha256,
                   canonical_payload, evidence_refs, run_id, created_at
            FROM research_artifacts
            WHERE """
            + " AND ".join(clauses)
            + " ORDER BY available_at DESC, created_at DESC"
        )
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [self._load_row(row) for row in rows]

    def load_latest(
        self,
        scope_type: str,
        scope_key: str,
        artifact_type: str,
    ) -> StoredResearchArtifact:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.artifact_id, a.scope_type, a.scope_key, a.artifact_type,
                       a.schema_version, a.as_of, a.available_at, a.payload_sha256,
                       a.canonical_payload, a.evidence_refs, a.run_id, a.created_at
                FROM research_artifact_heads h
                JOIN research_artifacts a ON a.artifact_id = h.artifact_id
                WHERE h.scope_type = %s
                  AND h.scope_key = %s
                  AND h.artifact_type = %s
                """,
                (scope_type, scope_key, artifact_type),
            )
            row = cursor.fetchone()
        if row is None:
            raise KeyError(
                f"No research artifact head for {scope_type}:{scope_key}:{artifact_type}"
            )
        artifact = self._load_row(row)
        self.verify(artifact)
        return artifact

    def list_versions(
        self,
        scope_type: str,
        scope_key: str,
        artifact_type: str,
        *,
        limit: int = 100,
    ) -> list[StoredResearchArtifact]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT artifact_id, scope_type, scope_key, artifact_type,
                       schema_version, as_of, available_at, payload_sha256,
                       canonical_payload, evidence_refs, run_id, created_at
                FROM research_artifacts
                WHERE scope_type = %s
                  AND scope_key = %s
                  AND artifact_type = %s
                ORDER BY available_at DESC, created_at DESC
                LIMIT %s
                """,
                (scope_type, scope_key, artifact_type, limit),
            )
            rows = cursor.fetchall()
        return [self._load_row(row) for row in rows]

    def verify(self, artifact: StoredResearchArtifact) -> dict[str, Any]:
        parse_stored_artifact_payload(artifact)
        return {
            "artifact_id": artifact.artifact_id,
            "payload_sha256": artifact.envelope.payload_sha256,
            "verified": True,
        }

    def head(
        self,
        scope_type: str,
        scope_key: str,
        artifact_type: str,
    ) -> ResearchArtifactHead:
        artifact = self.load_latest(scope_type, scope_key, artifact_type)
        envelope = artifact.envelope
        return ResearchArtifactHead(
            scope_type=scope_type,
            scope_key=scope_key,
            artifact_type=artifact_type,
            artifact_id=artifact.artifact_id,
            schema_version=envelope.identity.schema_version,
            as_of=envelope.identity.as_of,
            available_at=envelope.identity.available_at,
            payload_sha256=envelope.payload_sha256,
            updated_at=artifact.created_at,
        )

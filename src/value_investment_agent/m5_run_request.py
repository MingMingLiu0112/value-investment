"""Self-contained, replayable M5 event run requests.

A run request is the only supported way to hand a reviewed bridge batch to the
offline coordinator: it embeds the events, their observed times, the scan
watermark, the dependency graph and the explicit direct dependency kinds, then
pins the payload with a deterministic request id and SHA-256.  Nothing here
schedules work, notifies anyone or touches production state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .m5_actual_offline_authorization import (
    M5ActualOfflineAuthorization,
    actual_offline_authorization_from_payload,
    require_actual_offline_authorization,
)
from .m5_event_core import (
    NAMESPACE_ACTUAL,
    NAMESPACE_SIMULATED,
    ChangeEventInput,
    _digest,
    _optional_text,
    _required_datetime,
    _required_text,
    _state_digest,
    change_event_input_from_payload,
)
from .m5_event_dependencies import (
    DependencyGraph,
    dependency_graph_from_payload,
)
from .m5_event_watermark import ScanWatermark, scan_watermark_from_payload
from .m5_materiality_bridge import MaterialityBridgeBatch


M5_RUN_REQUEST_SCHEMA_V1 = "m5-event-run-request-v1"
M5_RUN_REQUEST_SCHEMA = "m5-event-run-request-v2"


def batch_request_fingerprint(
    *,
    events: Sequence[ChangeEventInput],
    observed_times: Sequence[datetime],
    watermark: ScanWatermark,
    graph: DependencyGraph,
    direct_kinds_by_source_event_id: Mapping[str, Sequence[str]],
    actual_offline_authorization: M5ActualOfflineAuthorization | None = None,
) -> str:
    """Canonical fingerprint of every input that can change a verdict."""

    payload: dict[str, Any] = {
            "events": [event.as_policy() for event in events],
            "observed_times": [item.isoformat() for item in observed_times],
            "watermark": watermark.as_policy(),
            "dependency_graph": graph.as_policy(),
            "direct_kinds_by_source_event_id": {
                key: list(value)
                for key, value in sorted(
                    direct_kinds_by_source_event_id.items()
                )
            },
        }
    if actual_offline_authorization is not None:
        payload["actual_offline_authorization"] = (
            actual_offline_authorization.as_policy()
        )
    return _state_digest(payload)


def request_id_for(
    *,
    request_fingerprint: str,
    run_id: str,
    batch_id: str,
    generated_at: datetime,
) -> str:
    return "m5-request-" + _digest(
        "run-request",
        request_fingerprint,
        run_id,
        batch_id,
        generated_at.isoformat(),
    )[:32]


@dataclass(frozen=True)
class M5EventRunRequest:
    """Versioned, self-contained request for one bounded M5 event batch."""

    request_id: str
    run_id: str
    batch_id: str
    stream_id: str
    namespace: str
    generated_at: datetime
    events: tuple[ChangeEventInput, ...]
    observed_times: tuple[datetime, ...]
    watermark: ScanWatermark
    dependency_graph: DependencyGraph
    direct_kinds_by_source_event_id: Mapping[str, tuple[str, ...]]
    review_id: str | None = None
    source_symbol: str | None = None
    action: str = ACTION_NO_ORDER
    actual_offline_authorization: M5ActualOfflineAuthorization | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _required_text(self.request_id, "request_id"),
        )
        object.__setattr__(self, "run_id", _required_text(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "batch_id",
            _required_text(self.batch_id, "batch_id"),
        )
        object.__setattr__(
            self,
            "stream_id",
            _required_text(self.stream_id, "stream_id"),
        )
        object.__setattr__(
            self,
            "namespace",
            _required_text(self.namespace, "namespace"),
        )
        object.__setattr__(
            self,
            "generated_at",
            _required_datetime(self.generated_at, "generated_at"),
        )
        object.__setattr__(self, "events", tuple(self.events))
        if any(not isinstance(item, ChangeEventInput) for item in self.events):
            raise ValueError("Run request events must be ChangeEventInput objects")
        if any(item.namespace != self.namespace for item in self.events):
            raise ValueError("Run request events must match its namespace")
        object.__setattr__(
            self,
            "observed_times",
            tuple(
                _required_datetime(item, "observed_at")
                for item in self.observed_times
            ),
        )
        if not isinstance(self.watermark, ScanWatermark):
            raise ValueError("Run request watermark must be a ScanWatermark")
        if not isinstance(self.dependency_graph, DependencyGraph):
            raise ValueError(
                "Run request dependency graph must be a DependencyGraph"
            )
        require_actual_offline_authorization(
            namespace=self.namespace,
            authorization=self.actual_offline_authorization,
            graph=self.dependency_graph,
        )
        object.__setattr__(
            self,
            "direct_kinds_by_source_event_id",
            {
                _required_text(key, "direct dependency source_event_id"): tuple(
                    _required_text(item, "direct dependency kind")
                    for item in value
                )
                for key, value in dict(
                    self.direct_kinds_by_source_event_id
                ).items()
            },
        )
        object.__setattr__(
            self,
            "review_id",
            _optional_text(self.review_id, "review_id"),
        )
        object.__setattr__(
            self,
            "source_symbol",
            _optional_text(self.source_symbol, "source_symbol"),
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("M5 run request must remain no_order")
        self.verify()

    def verify(self) -> None:
        if len(self.events) != len(self.observed_times):
            raise ValueError(
                "Every run request event requires one observed_at timestamp"
            )
        source_event_ids = {item.source_event_id for item in self.events}
        unknown = sorted(
            set(self.direct_kinds_by_source_event_id) - source_event_ids
        )
        if unknown:
            raise ValueError(
                f"Run request direct kinds reference unknown events: {unknown}"
            )
        if any(
            not kinds
            for kinds in self.direct_kinds_by_source_event_id.values()
        ):
            raise ValueError("Run request direct kinds cannot be empty")
        expected_id = request_id_for(
            request_fingerprint=self.request_fingerprint(),
            run_id=self.run_id,
            batch_id=self.batch_id,
            generated_at=self.generated_at,
        )
        if self.request_id != expected_id:
            raise ValueError(
                "M5 run request id does not match its immutable payload"
            )

    def request_fingerprint(self) -> str:
        return batch_request_fingerprint(
            events=self.events,
            observed_times=self.observed_times,
            watermark=self.watermark,
            graph=self.dependency_graph,
            direct_kinds_by_source_event_id=self.direct_kinds_by_source_event_id,
            actual_offline_authorization=self.actual_offline_authorization,
        )

    @property
    def direct_kinds(self) -> dict[str, tuple[str, ...]]:
        return dict(self.direct_kinds_by_source_event_id)

    def as_policy(self) -> dict[str, Any]:
        self.verify()
        return {
            "schema_version": M5_RUN_REQUEST_SCHEMA,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "stream_id": self.stream_id,
            "namespace": self.namespace,
            "generated_at": self.generated_at.isoformat(),
            "review_id": self.review_id,
            "source_symbol": self.source_symbol,
            "request_fingerprint": self.request_fingerprint(),
            "events": [item.as_policy() for item in self.events],
            "observed_times": [
                item.isoformat() for item in self.observed_times
            ],
            "watermark": self.watermark.as_policy(),
            "dependency_graph": self.dependency_graph.as_policy(),
            "direct_kinds_by_source_event_id": {
                key: list(value)
                for key, value in sorted(
                    self.direct_kinds_by_source_event_id.items()
                )
            },
            "action": self.action,
            "actual_offline_authorization": (
                self.actual_offline_authorization.as_policy()
                if self.actual_offline_authorization is not None else None
            ),
        }

    def request_sha256(self) -> str:
        return _state_digest(self.as_policy())

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "M5EventRunRequest":
        """Parse a serialized run request fail-closed.

        The payload must round-trip to its canonical form so a hand-edited
        request cannot silently change what a replay would apply.
        """

        if not isinstance(payload, Mapping):
            raise ValueError("M5 run request must be an object")
        data = dict(payload)
        schema_version = data.get("schema_version")
        if schema_version not in {
            M5_RUN_REQUEST_SCHEMA_V1,
            M5_RUN_REQUEST_SCHEMA,
        }:
            raise ValueError("Unknown M5 run request schema")
        raw_kinds = data.get("direct_kinds_by_source_event_id") or {}
        if not isinstance(raw_kinds, Mapping):
            raise ValueError("Run request direct kinds must be an object")
        request = cls(
            request_id=_required_text(data["request_id"], "request_id"),
            run_id=_required_text(data["run_id"], "run_id"),
            batch_id=_required_text(data["batch_id"], "batch_id"),
            stream_id=_required_text(data["stream_id"], "stream_id"),
            namespace=_required_text(data["namespace"], "namespace"),
            generated_at=_required_datetime(
                datetime.fromisoformat(str(data["generated_at"])),
                "generated_at",
            ),
            events=tuple(
                change_event_input_from_payload(item)
                for item in data.get("events") or ()
            ),
            observed_times=tuple(
                _required_datetime(
                    datetime.fromisoformat(str(item)),
                    "observed_at",
                )
                for item in data.get("observed_times") or ()
            ),
            watermark=scan_watermark_from_payload(data["watermark"]),
            dependency_graph=dependency_graph_from_payload(
                data["dependency_graph"]
            ),
            direct_kinds_by_source_event_id={
                _required_text(key, "source_event_id"): tuple(
                    str(item) for item in value
                )
                for key, value in raw_kinds.items()
            },
            review_id=_optional_text(data.get("review_id"), "review_id"),
            source_symbol=_optional_text(
                data.get("source_symbol"),
                "source_symbol",
            ),
            action=str(data.get("action", ACTION_NO_ORDER)),
            actual_offline_authorization=(
                actual_offline_authorization_from_payload(data["actual_offline_authorization"])
                if data.get("actual_offline_authorization") is not None else None
            ),
        )
        if schema_version == M5_RUN_REQUEST_SCHEMA_V1:
            if request.namespace != NAMESPACE_SIMULATED:
                raise ValueError("M5 v1 requests may only use SIMULATED namespace")
            expected = request.as_policy()
            expected["schema_version"] = M5_RUN_REQUEST_SCHEMA_V1
            expected.pop("actual_offline_authorization")
        else:
            expected = request.as_policy()
        if set(data) != set(expected):
            missing = sorted(set(expected) - set(data))
            extra = sorted(set(data) - set(expected))
            raise ValueError(
                "M5 run request keys do not match the schema: "
                f"missing={missing} extra={extra}"
            )
        if data["request_fingerprint"] != request.request_fingerprint():
            raise ValueError(
                "M5 run request fingerprint does not match its payload"
            )
        if data != expected:
            raise ValueError(
                "M5 run request does not round-trip to its canonical form"
            )
        return request


def build_run_request(
    *,
    run_id: str,
    generated_at: datetime,
    events: Sequence[ChangeEventInput],
    observed_times: Sequence[datetime],
    watermark: ScanWatermark,
    graph: DependencyGraph,
    direct_kinds_by_source_event_id: Mapping[str, Sequence[str]] | None = None,
    batch_id: str | None = None,
    stream_id: str | None = None,
    namespace: str = NAMESPACE_SIMULATED,
    review_id: str | None = None,
    source_symbol: str | None = None,
    actual_offline_authorization: M5ActualOfflineAuthorization | None = None,
) -> M5EventRunRequest:
    """Build one pinned run request from explicit, already-reviewed inputs."""

    run_id = _required_text(run_id, "run_id")
    batch_id = _required_text(batch_id or run_id, "batch_id")
    generated_at = _required_datetime(generated_at, "generated_at")
    normalized_kinds = {
        _required_text(key, "direct dependency source_event_id"): tuple(
            _required_text(item, "direct dependency kind") for item in value
        )
        for key, value in dict(direct_kinds_by_source_event_id or {}).items()
    }
    events = tuple(events)
    observed_times = tuple(
        _required_datetime(item, "observed_at") for item in observed_times
    )
    fingerprint = batch_request_fingerprint(
        events=events,
        observed_times=observed_times,
        watermark=watermark,
        graph=graph,
        direct_kinds_by_source_event_id=normalized_kinds,
        actual_offline_authorization=actual_offline_authorization,
    )
    return M5EventRunRequest(
        request_id=request_id_for(
            request_fingerprint=fingerprint,
            run_id=run_id,
            batch_id=batch_id,
            generated_at=generated_at,
        ),
        run_id=run_id,
        batch_id=batch_id,
        stream_id=_required_text(stream_id or run_id, "stream_id"),
        namespace=namespace,
        generated_at=generated_at,
        events=events,
        observed_times=observed_times,
        watermark=watermark,
        dependency_graph=graph,
        direct_kinds_by_source_event_id=normalized_kinds,
        review_id=review_id,
        source_symbol=source_symbol,
        actual_offline_authorization=actual_offline_authorization,
    )


def build_run_request_from_bridge_batch(
    batch: MaterialityBridgeBatch,
    *,
    run_id: str,
    generated_at: datetime,
    watermark: ScanWatermark,
    graph: DependencyGraph,
    batch_id: str | None = None,
    stream_id: str | None = None,
    actual_offline_authorization: M5ActualOfflineAuthorization | None = None,
) -> M5EventRunRequest:
    """Convert one reviewed bridge batch into a replayable run request.

    The bridge batch already decided which human verdicts become events; this
    function only embeds that decision together with its reviewed boundary and,
    for ACTUAL data only, an explicitly offline authorization.
    """

    if not isinstance(batch, MaterialityBridgeBatch):
        raise ValueError("batch must be a MaterialityBridgeBatch")
    if batch.namespace not in {NAMESPACE_SIMULATED, NAMESPACE_ACTUAL}:
        raise ValueError("Offline run request batch namespace is unknown")
    return build_run_request(
        run_id=run_id,
        generated_at=generated_at,
        events=batch.events,
        observed_times=batch.observed_times,
        watermark=watermark,
        graph=graph,
        direct_kinds_by_source_event_id=batch.direct_kinds_by_source_event_id,
        batch_id=batch_id,
        stream_id=stream_id,
        namespace=batch.namespace,
        review_id=batch.review_id,
        source_symbol=batch.symbol,
        actual_offline_authorization=actual_offline_authorization,
    )

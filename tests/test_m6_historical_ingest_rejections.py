from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Mapping, Sequence

import pytest

from value_investment_agent.investment_decision import ACTION_NO_ORDER
from value_investment_agent.m5_event_core import (
    CONFIDENCE_HIGH,
    EVENT_TYPE_NEW_FINANCIAL_REPORT,
    INGEST_CONFLICT_REJECTED,
    INGEST_FUTURE_REJECTED,
    INGEST_OBSERVED_TIME_REGRESSION_REJECTED,
    NAMESPACE_SIMULATED,
    SEVERITY_HIGH,
    ChangeEventInput,
    _state_digest,
)
from value_investment_agent.m5_event_dependencies import (
    KIND_FACTS,
    DependencyGraph,
    DependencyNode,
)
from value_investment_agent.m5_event_run import RUN_ATTENTION, RUN_HEALTHY
from value_investment_agent.m5_event_run import run_event_batch_persisted
from value_investment_agent.m5_event_state_store import (
    JsonM5EventRunReceiptStore,
    JsonM5EventRunStateStore,
)
from value_investment_agent.m5_event_watermark import (
    SOURCE_HEALTHY,
    WATERMARK_COVERAGE_COMPLETE,
    ScanWatermark,
)
from value_investment_agent.m5_run_request import build_run_request
from value_investment_agent.m6_historical_ingest_rejections import (
    HISTORICAL_REJECTIONS_CLEAR,
    HISTORICAL_REJECTIONS_PRESENT,
    M6HistoricalIngestIntegrityError,
    build_historical_ingest_rejection_view,
    build_historical_ingest_rejection_view_from_paths,
)


TZ = timezone(timedelta(hours=8))
START = datetime(2026, 9, 24, 15, 0, tzinfo=TZ)
RUN_ID = "m6-history-synthetic-run"
ROOT = Path(__file__).resolve().parents[1]


def _event(
    *,
    source_event_id: str,
    observed_at: datetime,
    current_state: Mapping[str, object] | None = None,
) -> ChangeEventInput:
    available_at = observed_at - timedelta(minutes=5)
    return ChangeEventInput(
        source_event_id=source_event_id,
        source_id="synthetic-cninfo",
        symbol="600887",
        event_type=EVENT_TYPE_NEW_FINANCIAL_REPORT,
        detected_at=available_at,
        available_at=available_at,
        effective_at=available_at,
        previous_state={},
        current_state=dict(current_state or {"value": "1.0"}),
        severity=SEVERITY_HIGH,
        reason="synthetic M6 historical rejection fixture",
        evidence_refs=({"id": f"synthetic-{source_event_id}"},),
        confidence=CONFIDENCE_HIGH,
        requires_human_review=True,
        namespace=NAMESPACE_SIMULATED,
    )


def _watermark(*, at: datetime, watermark_id: str) -> ScanWatermark:
    return ScanWatermark(
        watermark_id=watermark_id,
        scope="600887",
        source="synthetic-cninfo",
        coverage_through=at,
        retrieved_at=at,
        parser_version="m6-history-v1",
        coverage_status=WATERMARK_COVERAGE_COMPLETE,
        source_health=SOURCE_HEALTHY,
        evidence_refs=({"id": f"scan-{watermark_id}"},),
    )


def _graph() -> DependencyGraph:
    return DependencyGraph(
        (
            DependencyNode(
                node_id="facts-600887",
                kind=KIND_FACTS,
                symbol="600887",
                inputs=(),
                version="m6-history-v1",
                evidence_refs=({"id": "facts-600887"},),
            ),
        )
    )


def _run_batch(
    *,
    state_root: Path,
    receipt_root: Path,
    batch_id: str,
    generated_at: datetime,
    events: Sequence[ChangeEventInput] = (),
    observed_times: Sequence[datetime] = (),
    watermark_at: datetime | None = None,
) -> object:
    state_store = JsonM5EventRunStateStore(state_root)
    receipt_store = JsonM5EventRunReceiptStore(receipt_root)
    graph = _graph()
    watermark = _watermark(
        at=watermark_at or generated_at,
        watermark_id=f"scan-{batch_id}",
    )
    request = build_run_request(
        run_id=RUN_ID,
        generated_at=generated_at,
        events=events,
        observed_times=observed_times,
        watermark=watermark,
        graph=graph,
        batch_id=batch_id,
    )
    receipt = run_event_batch_persisted(
        events=request.events,
        observed_times=request.observed_times,
        watermark=request.watermark,
        graph=request.dependency_graph,
        run_id=request.run_id,
        generated_at=request.generated_at,
        store=state_store,
        namespace=request.namespace,
        direct_kinds_by_source_event_id=request.direct_kinds,
        batch_id=request.batch_id,
    )
    receipt_store.publish(receipt=receipt, request=request)
    return receipt


def _base_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "state", tmp_path / "receipts"


def _view(paths: tuple[Path, Path], *, generated_at: datetime = START) -> dict:
    state_root, receipt_root = paths
    return build_historical_ingest_rejection_view_from_paths(
        state_key=RUN_ID,
        state_root=state_root,
        receipt_root=receipt_root,
        generated_at=generated_at,
    )


def test_future_rejection_remains_visible_after_later_healthy_run(tmp_path):
    paths = _base_paths(tmp_path)
    rejected = _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-future",
        generated_at=START,
        events=(_event(source_event_id="future", observed_at=START + timedelta(minutes=10)),),
        observed_times=(START,),
    )
    healthy = _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-healthy",
        generated_at=START + timedelta(minutes=10),
    )

    assert rejected.health_status == RUN_ATTENTION
    assert healthy.health_status == RUN_HEALTHY
    view = _view(paths)

    assert view["status"] == HISTORICAL_REJECTIONS_PRESENT
    assert view["historical_rejection_count"] == 1
    assert view["historical_rejections"][0]["status"] == INGEST_FUTURE_REJECTED
    assert view["current_state"]["latest_receipt_health_status"] == RUN_HEALTHY
    assert view["integrity"]["receipt_count"] == 2
    assert view["integrity"]["authenticity_status"] == "LOCAL_CONSISTENCY_ONLY"
    assert view["boundary"]["evidence_class"] == "SIMULATED_OFFLINE_ONLY"
    assert view["boundary"]["counts_toward_real_operational_events"] is False
    assert view["action"] == ACTION_NO_ORDER


def test_conflict_and_observed_time_regression_are_aggregated(tmp_path):
    conflict_paths = _base_paths(tmp_path / "conflict")
    first = _event(source_event_id="conflict", observed_at=START)
    _run_batch(
        state_root=conflict_paths[0],
        receipt_root=conflict_paths[1],
        batch_id="batch-conflict-accepted",
        generated_at=START,
        events=(first,),
        observed_times=(START,),
    )
    conflict = _run_batch(
        state_root=conflict_paths[0],
        receipt_root=conflict_paths[1],
        batch_id="batch-conflict-rejected",
        generated_at=START + timedelta(minutes=1),
        events=(
            _event(
                source_event_id="conflict",
                observed_at=START + timedelta(minutes=1),
                current_state={"value": "2.0"},
            ),
        ),
        observed_times=(START + timedelta(minutes=1),),
    )
    conflict_view = _view(conflict_paths)
    assert conflict.ingest_results[0].status == INGEST_CONFLICT_REJECTED
    assert conflict_view["historical_rejections_by_status"][
        INGEST_CONFLICT_REJECTED
    ] == 1

    regression_paths = _base_paths(tmp_path / "regression")
    _run_batch(
        state_root=regression_paths[0],
        receipt_root=regression_paths[1],
        batch_id="batch-regression-first",
        generated_at=START + timedelta(minutes=10),
        events=(_event(source_event_id="regression-first", observed_at=START + timedelta(minutes=10)),),
        observed_times=(START + timedelta(minutes=10),),
    )
    regression = _run_batch(
        state_root=regression_paths[0],
        receipt_root=regression_paths[1],
        batch_id="batch-regression-rejected",
        generated_at=START + timedelta(minutes=20),
        events=(_event(source_event_id="regression-second", observed_at=START),),
        observed_times=(START,),
    )
    regression_view = _view(regression_paths)
    assert regression.ingest_results[0].status == INGEST_OBSERVED_TIME_REGRESSION_REJECTED
    assert regression_view["historical_rejections_by_status"][
        INGEST_OBSERVED_TIME_REGRESSION_REJECTED
    ] == 1


def test_forged_rejected_verdict_with_recomputed_internal_hashes_fails_closed(tmp_path):
    paths = _base_paths(tmp_path)
    _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-future",
        generated_at=START,
        events=(_event(source_event_id="future", observed_at=START + timedelta(minutes=10)),),
        observed_times=(START,),
    )
    receipt_path = next(paths[1].glob("m5-receipt-*.json"))
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_payload = payload["receipt"]
    receipt_payload["ingest_results"][0]["message"] = "forged rejection text"
    payload["receipt_sha256"] = _state_digest(receipt_payload)
    payload["audit_fingerprint"] = _state_digest(
        {
            "receipt_id": receipt_payload["receipt_id"],
            "run_id": receipt_payload["run_id"],
            "batch_id": receipt_payload["batch_id"],
            "stream_id": receipt_payload["stream_id"],
            "namespace": receipt_payload["namespace"],
            "generated_at": receipt_payload["generated_at"],
            "ingest_results": receipt_payload["ingest_results"],
            "invalidations": receipt_payload["invalidations"],
            "checkpoint": receipt_payload["checkpoint"],
            "action": receipt_payload["action"],
        }
    )
    receipt_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        M6HistoricalIngestIntegrityError,
        match="immutable verification",
    ):
        _view(paths)


def test_missing_receipt_fails_closed(tmp_path):
    paths = _base_paths(tmp_path)
    _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-1",
        generated_at=START,
    )
    _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-2",
        generated_at=START + timedelta(minutes=1),
    )
    receipt_files = sorted(paths[1].glob("m5-receipt-*.json"))
    assert len(receipt_files) == 2
    receipt_files[0].unlink()
    with pytest.raises(M6HistoricalIngestIntegrityError, match="missing current-state revisions"):
        _view(paths)



def test_state_rollback_fails_closed(tmp_path):
    paths = _base_paths(tmp_path)
    first = _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-1",
        generated_at=START,
    )
    _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-2",
        generated_at=START + timedelta(minutes=1),
    )
    state_digest = hashlib.sha256(RUN_ID.encode("utf-8")).hexdigest()
    state_path = paths[0] / f"m5-state-{state_digest}.json"
    state_path.write_text(
        json.dumps(first.state.as_policy(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(M6HistoricalIngestIntegrityError, match="unique current-state batch record"):
        _view(paths)


def test_duplicate_json_key_and_unexpected_entry_fail_closed(tmp_path):
    paths = _base_paths(tmp_path)
    _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-1",
        generated_at=START,
    )
    receipt_path = next(paths[1].glob("m5-receipt-*.json"))
    text = receipt_path.read_text(encoding="utf-8")
    original = text
    text = text.replace(
        '"schema_version": "m5-event-run-receipt-v1",',
        '"schema_version": "m5-event-run-receipt-v1",\n  "schema_version": "m5-event-run-receipt-v1",',
        1,
    )
    receipt_path.write_text(text, encoding="utf-8")
    with pytest.raises(M6HistoricalIngestIntegrityError, match="strict JSON"):
        _view(paths)

    receipt_path.write_text(original, encoding="utf-8")
    paths[1].joinpath("unexpected.txt").write_text("not a receipt", encoding="utf-8")
    with pytest.raises(M6HistoricalIngestIntegrityError, match="Unexpected entry"):
        _view(paths)


def test_receipt_filename_must_match_receipt_id(tmp_path):
    paths = _base_paths(tmp_path)
    _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-1",
        generated_at=START,
    )
    receipt_path = next(paths[1].glob("m5-receipt-*.json"))
    wrong_name = paths[1] / ("m5-receipt-" + "0" * 64 + ".json")
    receipt_path.rename(wrong_name)

    with pytest.raises(M6HistoricalIngestIntegrityError, match="filename"):
        _view(paths)


def test_no_historical_rejections_is_clear(tmp_path):
    paths = _base_paths(tmp_path)
    _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-healthy",
        generated_at=START,
    )

    view = _view(paths)

    assert view["status"] == HISTORICAL_REJECTIONS_CLEAR
    assert view["historical_rejection_count"] == 0
    assert view["integrity"]["receipt_count"] == 1
    assert view["action"] == ACTION_NO_ORDER


def test_store_contract_view_does_not_require_paths(tmp_path):
    paths = _base_paths(tmp_path)
    _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-future",
        generated_at=START,
        events=(_event(source_event_id="future", observed_at=START + timedelta(minutes=10)),),
        observed_times=(START,),
    )

    view = build_historical_ingest_rejection_view(
        state_key=RUN_ID,
        state_store=JsonM5EventRunStateStore(paths[0]),
        receipt_root=paths[1],
        generated_at=START,
    )

    assert view["historical_rejection_count"] == 1
    assert view["current_state"]["file_sha256"] is None


def test_read_only_cli_reports_history_without_writes(tmp_path):
    paths = _base_paths(tmp_path)
    _run_batch(
        state_root=paths[0],
        receipt_root=paths[1],
        batch_id="batch-future",
        generated_at=START,
        events=(_event(source_event_id="future", observed_at=START + timedelta(minutes=10)),),
        observed_times=(START,),
    )
    before = sorted(
        (path.relative_to(tmp_path).as_posix(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_m6_historical_ingest_rejections.py"),
            "--state-key",
            RUN_ID,
            "--state-root",
            str(paths[0]),
            "--receipt-root",
            str(paths[1]),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "status: ATTENTION" in result.stdout
    assert "historical_rejection_count: 1" in result.stdout
    assert "action: no_order" in result.stdout
    after = sorted(
        (path.relative_to(tmp_path).as_posix(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    assert after == before

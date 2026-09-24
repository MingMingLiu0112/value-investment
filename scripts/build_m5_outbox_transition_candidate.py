"""Build a versioned simulated M5 workbook with persisted outbox transitions."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_m5_event_infrastructure_candidate import (
    DEFAULT_INPUT as DEFAULT_BASE_INPUT,
    build_models,
    load_input,
)
from value_investment_agent.investment_decision import ACTION_NO_ORDER
from value_investment_agent.m5_event_core import (
    EVENT_STATUS_ACTIVE,
    NAMESPACE_SIMULATED,
)
from value_investment_agent.m5_event_outbox import ALERT_STATUSES, ALERT_TYPES
from value_investment_agent.m5_event_outbox_state import apply_outbox_transition
from value_investment_agent.m5_event_run import M5EventRunReceipt
from value_investment_agent.m5_event_run_state import M5EventRunState
from value_investment_agent.m5_event_workbook import write_m5_event_workbook

DEFAULT_TRANSITION_INPUT = (
    ROOT / "tests" / "fixtures" / "m5_outbox_transition_demo.json"
)
DEFAULT_OUTPUT = (
    ROOT / "A股价值投资_M5事件监控候选_v2_20260924.xlsx"
)
SCHEMA_VERSION = "m5-outbox-transition-demo-v1"
MANIFEST_SCHEMA_VERSION = "m5-outbox-transition-candidate-v2"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_KEYS = {
    "schema_version",
    "action",
    "namespace",
    "generated_at",
    "base_input",
    "base_input_sha256",
    "operations",
}
PARENT_V1_WORKBOOK = ROOT / "A股价值投资_M5事件监控候选_20260924.xlsx"
WORKBOOK_MODULE = (
    ROOT / "src" / "value_investment_agent" / "m5_event_workbook.py"
)
_OPERATION_KEYS = {
    "source_event_id",
    "alert_type",
    "from_status",
    "to_status",
    "occurred_at",
    "error",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-input", type=Path, default=DEFAULT_BASE_INPUT)
    parser.add_argument(
        "--transitions",
        type=Path,
        default=DEFAULT_TRANSITION_INPUT,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_receipt(path: Path) -> dict[str, Any]:
    path = path.resolve()
    receipt = {
        "path": str(path),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }
    if path.is_relative_to(ROOT):
        receipt["relative_path"] = path.relative_to(ROOT).as_posix()
    return receipt


@contextmanager
def _publication_lock(output: Path):
    lock_path = output.with_name(output.name + ".lock")
    try:
        handle = lock_path.open("x", encoding="utf-8", newline="\n")
    except FileExistsError as exc:
        raise ValueError(
            "M5 outbox transition candidate publication is already in progress"
        ) from exc
    try:
        handle.write("m5-outbox-transition-candidate-lock-v1\n")
        handle.flush()
        yield
    finally:
        handle.close()
        lock_path.unlink(missing_ok=True)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _require_keys(
    payload: Mapping[str, Any],
    *,
    required: set[str],
    allowed: set[str],
    context: str,
) -> None:
    missing = required - set(payload)
    unknown = set(payload) - allowed
    if missing:
        raise ValueError(f"{context} missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{context} contains unknown fields: {sorted(unknown)}")


def load_transition_input(
    path: Path,
    *,
    base_input_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = path.resolve()
    base_input_path = base_input_path.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("M5 outbox transition input must be a JSON object")
    _require_keys(
        payload,
        required=_TOP_LEVEL_KEYS,
        allowed=_TOP_LEVEL_KEYS,
        context="M5 outbox transition input",
    )
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unknown M5 outbox transition input schema")
    if payload["action"] != ACTION_NO_ORDER:
        raise ValueError("M5 outbox transition input must remain no_order")
    if payload["namespace"] != NAMESPACE_SIMULATED:
        raise ValueError("Public M5 outbox transition input must be simulated")
    transition_generated_at = _datetime(
        payload["generated_at"],
        "generated_at",
    )

    base_reference = Path(_required_text(payload["base_input"], "base_input"))
    if base_reference.is_absolute():
        raise ValueError("base_input must be repository-relative")
    expected_base = (ROOT / base_reference).resolve()
    if not expected_base.is_relative_to(ROOT):
        raise ValueError("base_input must remain inside the repository")
    if expected_base != base_input_path:
        raise ValueError("base_input does not match the supplied base fixture")
    expected_hash = _required_text(
        payload["base_input_sha256"],
        "base_input_sha256",
    ).lower()
    if not _SHA256.fullmatch(expected_hash):
        raise ValueError("base_input_sha256 must be a SHA-256 hex digest")
    actual_hash = _sha256_file(base_input_path)
    if actual_hash != expected_hash:
        raise ValueError("Base M5 event input hash does not match the fixture")

    operations = payload["operations"]
    if not isinstance(operations, list) or not operations:
        raise ValueError("M5 outbox transition operations must be a non-empty list")
    for index, raw in enumerate(operations, 1):
        if not isinstance(raw, Mapping):
            raise ValueError(
                f"M5 outbox transition operation {index} must be an object"
            )
        _require_keys(
            raw,
            required=_OPERATION_KEYS,
            allowed=_OPERATION_KEYS,
            context=f"M5 outbox transition operation {index}",
        )
        if raw["alert_type"] not in ALERT_TYPES:
            raise ValueError(f"Unknown alert type in operation {index}")
        if raw["from_status"] not in ALERT_STATUSES:
            raise ValueError(f"Unknown from_status in operation {index}")
        if raw["to_status"] not in ALERT_STATUSES:
            raise ValueError(f"Unknown to_status in operation {index}")

    return payload, {
        "path": str(path),
        "sha256": _sha256_file(path),
        "operation_count": len(operations),
        "generated_at": transition_generated_at.isoformat(),
    }


def _resolve_alert(
    state: M5EventRunState,
    *,
    source_event_id: str,
    alert_type: str,
) -> tuple[str, str]:
    matches: list[tuple[str, str]] = []
    matching_event_statuses: list[str] = []
    for event in state.event_ledger.events():
        if event.source_event_id != source_event_id:
            continue
        for alert in state.outbox.alerts():
            if alert.event_id == event.event_id and alert.alert_type == alert_type:
                matches.append((alert.alert_id, event.symbol))
                matching_event_statuses.append(event.status)
    if len(matches) != 1:
        raise ValueError(
            "Outbox operation must resolve exactly one alert: "
            f"{source_event_id}/{alert_type}"
        )
    if matching_event_statuses[0] != EVENT_STATUS_ACTIVE:
        raise ValueError(
            "Outbox operation must target an active event: "
            f"{source_event_id}/{alert_type}"
        )
    return matches[0]


def apply_transition_operations(
    *,
    receipt: M5EventRunReceipt,
    payload: Mapping[str, Any],
) -> tuple[M5EventRunState, tuple[dict[str, Any], ...]]:
    state = receipt.state.clone()
    last_occurred_at: dict[str, datetime] = {}
    resolved: list[dict[str, Any]] = []
    transition_generated_at = _datetime(
        payload["generated_at"],
        "generated_at",
    )
    if transition_generated_at < receipt.generated_at:
        raise ValueError(
            "Outbox transition batch cannot precede its base event run"
        )

    for index, raw in enumerate(payload["operations"], 1):
        source_event_id = _required_text(
            raw["source_event_id"],
            f"operations[{index}].source_event_id",
        )
        alert_type = _required_text(
            raw["alert_type"],
            f"operations[{index}].alert_type",
        )
        from_status = _required_text(
            raw["from_status"],
            f"operations[{index}].from_status",
        )
        to_status = _required_text(
            raw["to_status"],
            f"operations[{index}].to_status",
        )
        occurred_at = _datetime(
            raw["occurred_at"],
            f"operations[{index}].occurred_at",
        )
        if occurred_at > transition_generated_at:
            raise ValueError(
                "Outbox operation cannot be later than the transition batch"
            )
        error = raw["error"]
        if error is not None:
            error = _required_text(error, f"operations[{index}].error")

        alert_id, symbol = _resolve_alert(
            state,
            source_event_id=source_event_id,
            alert_type=alert_type,
        )
        previous_occurred_at = last_occurred_at.get(alert_id)
        if previous_occurred_at is not None and occurred_at < previous_occurred_at:
            raise ValueError("Outbox operations must be chronological per alert")

        before_count = len(state.outbox_transitions)
        next_state = apply_outbox_transition(
            state=state,
            alert_id=alert_id,
            from_status=from_status,
            to_status=to_status,
            occurred_at=occurred_at,
            error=error,
        )
        idempotent = len(next_state.outbox_transitions) == before_count
        matching_transition = next(
            (
                item
                for item in reversed(next_state.outbox_transitions)
                if item.alert_id == alert_id
                and item.from_status == from_status
                and item.to_status == to_status
                and item.occurred_at == occurred_at
                and item.error == error
            ),
            None,
        )
        if matching_transition is None:
            raise ValueError("Applied outbox transition could not be resolved")

        current_alert = next(
            item
            for item in next_state.outbox.alerts()
            if item.alert_id == alert_id
        )
        resolved.append(
            {
                "operation_index": index,
                "source_event_id": source_event_id,
                "symbol": symbol,
                "alert_type": alert_type,
                "alert_id": alert_id,
                "from_status": from_status,
                "to_status": to_status,
                "status_after": current_alert.status,
                "occurred_at": occurred_at.isoformat(),
                "error": error,
                "transition_id": matching_transition.transition_id,
                "idempotent": idempotent,
            }
        )
        last_occurred_at[alert_id] = occurred_at
        state = next_state

    if state.outbox_revision != len(state.outbox_transitions):
        raise ValueError("Outbox revision does not match its transition history")
    return state, tuple(resolved)


def build_candidate(
    *,
    base_input_path: Path,
    transition_input_path: Path,
    output: Path,
    manifest_path: Path | None = None,
) -> tuple[dict[str, Any], M5EventRunState]:
    base_input_path = base_input_path.resolve()
    transition_input_path = transition_input_path.resolve()
    output = output.resolve()
    manifest_path = (
        output.with_suffix(".manifest.json")
        if manifest_path is None
        else manifest_path.resolve()
    )
    if output.exists():
        raise ValueError("M5 outbox transition candidate output already exists")
    if manifest_path.exists():
        raise ValueError("M5 outbox transition candidate manifest already exists")
    if output == manifest_path:
        raise ValueError("Workbook and manifest paths must differ")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    with _publication_lock(output):
        if output.exists():
            raise ValueError(
                "M5 outbox transition candidate output already exists"
            )
        if manifest_path.exists():
            raise ValueError(
                "M5 outbox transition candidate manifest already exists"
            )

        base_payload, base_receipt = load_input(base_input_path)
        receipt, watermark = build_models(base_payload)
        transition_payload, transition_receipt = load_transition_input(
            transition_input_path,
            base_input_path=base_input_path,
        )
        final_state, resolved_operations = apply_transition_operations(
            receipt=receipt,
            payload=transition_payload,
        )
        result = write_m5_event_workbook(
            receipt,
            watermark,
            output=output,
            root=output.parent,
            security_names=base_payload.get("security_names"),
            current_state=final_state,
            include_outbox_transitions=True,
            include_identity_metadata=True,
        )

        events_by_id = {
            event.event_id: event
            for event in final_state.event_ledger.events()
        }
        final_statuses = [
            {
                "source_event_id": events_by_id[alert.event_id].source_event_id,
                "alert_type": alert.alert_type,
                "alert_id": alert.alert_id,
                "status": alert.status,
            }
            for alert in final_state.outbox.alerts()
            if alert.event_id is not None
        ]
        identity_counts = Counter(
            event.event_identity_version
            for event in receipt.state.event_ledger.events()
        )
        manifest = {
            **result,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "generated_at": transition_payload["generated_at"],
            "base_input": base_receipt,
            "transition_input": transition_receipt,
            "producer": {
                "script": _file_receipt(Path(__file__).resolve()),
                "workbook_module": _file_receipt(WORKBOOK_MODULE),
                "parent_v1_workbook": _file_receipt(PARENT_V1_WORKBOOK),
            },
            "run_id": receipt.run_id,
            "namespace": receipt.namespace,
            "base_state_sha256": receipt.state_sha256,
            "outbox_revision": final_state.outbox_revision,
            "outbox_transition_count": len(final_state.outbox_transitions),
            "state_sha256": final_state.state_sha256(),
            "requested_operation_count": len(resolved_operations),
            "idempotent_operation_count": sum(
                item["idempotent"] for item in resolved_operations
            ),
            "resolved_operations": list(resolved_operations),
            "final_outbox_statuses": final_statuses,
            "event_identity_counts": dict(sorted(identity_counts.items())),
            "action": ACTION_NO_ORDER,
        }
        try:
            with manifest_path.open(
                "x",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                handle.write(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
                )
        except FileExistsError as exc:
            raise ValueError(
                "M5 outbox transition candidate manifest already exists"
            ) from exc
        return manifest, final_state


def main() -> int:
    args = parse_args()
    manifest, _ = build_candidate(
        base_input_path=args.base_input,
        transition_input_path=args.transitions,
        output=args.output,
        manifest_path=args.manifest,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

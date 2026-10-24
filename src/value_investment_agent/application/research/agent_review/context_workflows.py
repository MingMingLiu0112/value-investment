"""Source-bound hotspot questions and isolated portfolio retrospective questions."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from ...product.common import load_json_object, require_inside, sha256_file
from ...product.agent_research_surface import project_verified_agent_packet
from .daily_research import _bound_mock
from .llm_pilot import ROLE_TASKS, run_llm_research_pilot
from .snapshot import load_research_snapshot
from .source_context import load_source_context


CONTEXT_KINDS = {
    "hotspot": {"theme", "activity", "price_structure"},
    "retrospective": {"confirmed_holding", "original_plan", "manual_fill", "subsequent_information"},
}


def verify_workflow_context(*, root, snapshot, workflow, context_path, context_sha256, excerpts):
    """Replay exact citations; availability at plan time stays separate from later outcomes."""
    if workflow not in CONTEXT_KINDS:
        raise ValueError("Unsupported context workflow")
    root = Path(root).resolve()
    path = require_inside(root / "runtime", context_path, "workflow context")
    from .web_research import _public_path

    _public_path(root, path.relative_to(root).as_posix(), runtime_only=True)
    if path.stat().st_size > 64 * 1024 or sha256_file(path) != context_sha256:
        raise ValueError("Workflow context size/hash mismatch")
    value = load_json_object(path, "workflow context")
    if (set(value) != {"schema_version", "action", "symbol", "workflow", "scope", "records"}
            or value["schema_version"] != "agent-source-workflow-context-v1"
            or value["action"] != "no_order" or value["symbol"] != snapshot.symbol
            or value["workflow"] != workflow
            or value["scope"] not in {"PUBLIC_RESEARCH", "TEST_ONLY"}
            or workflow == "retrospective" and value["scope"] != "TEST_ONLY"):
        raise ValueError("Workflow scope mismatch; retrospective requires TEST_ONLY")
    rows = value["records"]
    if not isinstance(rows, list) or len(rows) != len(CONTEXT_KINDS[workflow]):
        raise ValueError("Missing workflow records")
    kinds, times = set(), {}
    catalog = snapshot.evidence_by_id()
    for row in rows:
        if (not isinstance(row, dict)
                or set(row) != {"kind", "source_id", "excerpt", "available_at"}
                or row["kind"] not in CONTEXT_KINDS[workflow] or row["kind"] in kinds
                or not isinstance(row["excerpt"], str) or not 8 <= len(row["excerpt"]) <= 500):
            raise ValueError("Invalid workflow record")
        kinds.add(row["kind"])
        ref = catalog.get(row["source_id"])
        if ref is None or row["available_at"] != ref.get("available_at"):
            raise ValueError("Workflow availability must equal admitted source availability")
        stamp = datetime.fromisoformat(row["available_at"])
        if stamp.utcoffset() is None or stamp.astimezone(ZoneInfo("Asia/Shanghai")).date() > snapshot.as_of:
            raise ValueError("Workflow record exceeds research cutoff")
        times[row["kind"]] = stamp
        if not any(item["source_id"] == row["source_id"]
                   and " ".join(row["excerpt"].split()) in " ".join(item["excerpt"].split())
                   for item in excerpts):
            raise ValueError("Workflow record lacks exact admitted excerpt")
    if workflow == "retrospective" and not (
            times["original_plan"] <= times["manual_fill"] <= times["confirmed_holding"]
            <= times["subsequent_information"]):
        raise ValueError("Retrospective plan/fill/holding/outcome PIT order is invalid")
    return value


def context_responses(value):
    """Deterministic Mock questions, never asserted facts or computed trade performance."""
    rows = value["records"]
    topics = ({
        "FUNDAMENTAL": "What explains theme activity and its relationship to price structure?",
        "COUNTER_EVIDENCE": "Could sentiment reversal or incomplete bars undermine hotspot persistence?",
        "EVENT": "Which verified market disclosure should trigger a human hotspot review?",
    } if value["workflow"] == "hotspot" else {
        "FUNDAMENTAL": "Which differences between the original plan and manual fill require review?",
        "COUNTER_EVIDENCE": "Could later information bias assessment of the original plan and holding risk?",
        "EVENT": "Which thesis changes after the fill require human retrospective review?",
    })
    return {role.value: json.dumps({"findings": [{
        "claim": topics[role.value], "finding_type": "RESEARCH_QUESTION",
        "supporting_evidence_refs": sorted({row["source_id"] for row in rows}),
        "counter_evidence_refs": [], "affected_research_dimensions": [task[1]],
        "confidence": "LOW", "proposed_follow_up":
            "Compare dated original excerpts; do not infer bar confirmation, trade eligibility or past knowledge.",
    }]}) for role, task in ROLE_TASKS.items()}


def run_daily_context_mock(*, root: Path, workbench: Path, workbench_sha256: str,
                           symbol: str, output: Path, source_requests: tuple,
                           workflow: str, context_path: Path, context_sha256: str) -> dict:
    # Preflight before the snapshot loader opens originals: these workflows have
    # no authority to consume a private journal, even for a labelled Mock run.
    from .web_research import _public_path, _raw, _json

    root = root.resolve()
    workbench = _public_path(root, workbench.resolve().relative_to(root).as_posix(), runtime_only=True)
    raw = _raw(workbench, 8 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != workbench_sha256:
        raise ValueError("Workflow workbench hash mismatch")
    view = _json(raw)
    originals = list(view["source_verification"]["sources"])
    for artifact in view["artifact_bundle"]["artifacts"]:
        if artifact["identity"]["artifact_type"] == "research_case":
            originals.extend(_json(artifact["canonical_payload"])["evidence_refs"])
    for original in originals:
        _public_path(root, original["path"].replace("\\", "/"))
    snapshot = load_research_snapshot(root=root, workbench=workbench,
        expected_sha256=workbench_sha256, symbol=symbol)
    context = load_source_context(root=root, snapshot=snapshot, requests=source_requests, enabled=True)
    value = verify_workflow_context(root=root, snapshot=snapshot, workflow=workflow,
        context_path=context_path, context_sha256=context_sha256,
        excerpts=[vars(item) for item in context.excerpts])
    binding = {"workflow": workflow, "version": 2,
        "workbench": {"path": workbench.resolve().relative_to(root.resolve()).as_posix(),
                      "sha256": workbench_sha256},
        "research_input_fingerprint": snapshot.input_fingerprint,
        "context": {"path": context_path.resolve().relative_to(root.resolve()).as_posix(),
                    "sha256": context_sha256}, "data_scope": value["scope"]}
    packet = run_llm_research_pilot(root=root, workbench=workbench,
        workbench_sha256=workbench_sha256, symbol=symbol, output=output,
        provider=_bound_mock(context_responses(value), binding), mode="mock", source_requests=source_requests)
    payload = {"as_of": snapshot.as_of.isoformat(), "generated_at": packet["generated_at"],
               "companies": [{"symbol": symbol}], "audit": {"evidence": []}}
    project_verified_agent_packet(payload, root=root, path=output, expected_sha256=sha256_file(output))
    return {"schema_version": "daily-agent-context-mock-v1", "action": "no_order",
        "mode": "MOCK", "symbol": symbol, "workflow_binding": binding,
        "workflow_input_sha256": packet["provider_input_sha256"],
        "packet": {"path": output.resolve().relative_to(root.resolve()).as_posix(), "sha256": sha256_file(output)},
        "findings": payload["companies"][0]["agent_research"], "sources": payload["audit"]["evidence"],
        "formal_fact_count": 0, "approval_count": 0, "decision_changed": False,
        "data_scope": value["scope"], "live_status": "LIVE_LLM_NOT_AUTHORIZED"}

"""Bounded, explicit Mock batch over existing daily research use cases."""
import json
from pathlib import Path
import re

from ...product.common import load_json_object, require_inside, sha256_file
from .daily_research import run_daily_event_mock, run_daily_financial_mock
from .source_context import ExcerptRequest


def run_daily_mock_batch(*, root: Path, plan: Path, plan_sha256: str) -> dict:
    """Isolate job failures without registering, publishing or reading private data."""
    root = root.resolve()

    def pinned(binding, label):
        if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
            raise ValueError(label + " requires path and sha256")
        path = require_inside(root, root / binding["path"], label)
        if path.stat().st_size > 1024 * 1024 or sha256_file(path) != binding["sha256"]:
            raise ValueError(label + " size/hash mismatch")
        return path

    plan = pinned({"path": str(plan), "sha256": plan_sha256}, "batch plan")
    value = load_json_object(plan, "batch plan")
    if (set(value) != {"schema_version", "action", "mode", "jobs"}
            or value["schema_version"] != "daily-agent-mock-batch-v1"
            or value["action"] != "no_order" or value["mode"] != "MOCK"
            or not isinstance(value["jobs"], list) or not 1 <= len(value["jobs"]) <= 20):
        raise ValueError("Invalid bounded Mock batch plan")
    outputs = set()
    # Validate the entire write set before invoking even one research job.
    for job in value["jobs"]:
        allowed = {"symbol", "workflow", "workbench", "output", "source_requests",
                   "mock_responses", "transcription", "metric_workbench"}
        if (not isinstance(job, dict) or set(job) - allowed
                or not {"symbol", "workflow", "workbench", "output"} <= set(job)
                or not re.fullmatch(r"\d{6}", job["symbol"])
                or job["workflow"] not in {"event", "financial"}):
            raise ValueError("Invalid batch job")
        if (job["workflow"] == "event" and {"transcription", "metric_workbench"} & set(job)
                or job["workflow"] == "financial" and "mock_responses" in job):
            raise ValueError("Cross-workflow inputs are forbidden")
        output = require_inside(root / "runtime", root / job["output"], "batch output")
        if output.suffix != ".json" or output in outputs:
            raise ValueError("Batch outputs must be distinct runtime JSON files")
        outputs.add(output)
    items = []
    for job in value["jobs"]:
        item = {"symbol": job["symbol"], "workflow": job["workflow"]}
        try:
            workbench = pinned(job["workbench"], "workbench")
            requests = ()
            if "source_requests" in job:
                source = load_json_object(pinned(job["source_requests"], "source requests"), "source requests")
                if (source.get("schema_version") != "agent-excerpt-requests-v1"
                        or source.get("symbol") != job["symbol"] or source.get("action") != "no_order"):
                    raise ValueError("Source request identity mismatch")
                requests = tuple(ExcerptRequest(**row) for row in source["requests"])
            kwargs = dict(root=root, workbench=workbench,
                          workbench_sha256=job["workbench"]["sha256"],
                          symbol=job["symbol"], output=root / job["output"],
                          source_requests=requests)
            if job["workflow"] == "event":
                replies = load_json_object(pinned(job["mock_responses"], "mock responses"), "mock responses")
                result = run_daily_event_mock(**kwargs, responses={
                    key: json.dumps(row, ensure_ascii=False) for key, row in replies.items()})
            else:
                extras = {}
                for key in ("transcription", "metric_workbench"):
                    if key in job:
                        extras[key] = pinned(job[key], key)
                        extras[key + "_sha256"] = job[key]["sha256"]
                result = run_daily_financial_mock(**kwargs, **extras)
            item.update(status="DRAFT_READY" if result.get("packet") else "BLOCKED_INPUT",
                        result=result)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            # No raw file content, credentials or private paths in the batch receipt.
            item.update(status="FAILED", error_type=type(exc).__name__)
        items.append(item)
    ready = sum(row["status"] == "DRAFT_READY" for row in items)
    return {"schema_version": "daily-agent-mock-batch-result-v1", "action": "no_order",
            "mode": "MOCK", "plan_sha256": plan_sha256,
            "status": "SUCCESS" if ready == len(items) else "PARTIAL" if ready else "BLOCKED",
            "items": items, "registered_or_published": False,
            "approval_count": 0, "decision_changed": False}

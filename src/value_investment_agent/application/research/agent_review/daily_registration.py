"""Explicit display-only registration of source-reverified daily Mock drafts."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .llm_pilot import MOCK_SCOPE
from .web_research import (
    REGISTRY_PATH, REGISTRY_SCHEMA, REGISTRY_WORKFLOWS_SCHEMA,
    _json, _raw, _public_path, _read_registered_research,
)


def register_daily_draft_results(*, root: Path, batch_result: dict, now: datetime) -> dict:
    """Keep failed jobs/previous registrations; never approve research or trade.

    This is an operator-invoked application step, not a GET side effect. Candidate
    registrations pass the exact Web verifier before an atomic pointer change.
    """
    root = Path(root).resolve()
    if (not isinstance(now, datetime) or now.utcoffset() is None
            or batch_result.get("schema_version") != "daily-agent-mock-batch-result-v1"
            or batch_result.get("mode") != "MOCK" or batch_result.get("action") != "no_order"
            or batch_result.get("approval_count") != 0
            or batch_result.get("decision_changed") is not False
            or not isinstance(batch_result.get("items"), list)
            or not 1 <= len(batch_result["items"]) <= 20):
        raise ValueError("Explicit bounded Mock batch result required")
    registry_path = _public_path(root, REGISTRY_PATH)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    lock = registry_path.with_suffix(".registration.lock")
    handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        previous = _raw(registry_path, 64 * 1024) if registry_path.exists() else None
        registry = (_json(previous) if previous is not None else {
            "schema_version": REGISTRY_WORKFLOWS_SCHEMA, "action": "no_order", "cases": {}})
        if (set(registry) != {"schema_version", "action", "cases"}
                or registry["schema_version"] not in {REGISTRY_SCHEMA, REGISTRY_WORKFLOWS_SCHEMA}
                or registry["action"] != "no_order" or not isinstance(registry["cases"], dict)):
            raise ValueError("Existing registry cannot be safely extended")
        current = deepcopy(registry)
        if current["schema_version"] == REGISTRY_SCHEMA:
            current["cases"] = {symbol: {"workflows": {"legacy": entry}}
                                for symbol, entry in current["cases"].items()}
            current["schema_version"] = REGISTRY_WORKFLOWS_SCHEMA
        scratch = _public_path(root, "runtime/agent-research-registration")
        scratch.mkdir(parents=True, exist_ok=True)
        items, accepted, seen = [], [], set()
        with tempfile.TemporaryDirectory(prefix="candidate-", dir=scratch) as folder:
            candidate_path = Path(folder) / "registry.json"
            candidate_name = candidate_path.relative_to(root).as_posix()
            for job in batch_result["items"]:
                symbol, workflow = job.get("symbol"), job.get("workflow")
                item = {"symbol": symbol, "workflow": workflow, "status": "SKIPPED"}
                items.append(item)
                if job.get("status") != "DRAFT_READY":
                    continue
                try:
                    identity = (symbol, workflow)
                    if identity in seen or workflow not in {"event", "financial"}:
                        raise ValueError("Duplicate or unsupported daily workflow")
                    seen.add(identity)
                    result = job["result"]
                    if (result.get("mode") != "MOCK" or result.get("action") != "no_order"
                            or result.get("symbol") != symbol
                            or result.get("approval_count") != 0
                            or result.get("formal_fact_count") != 0
                            or result.get("decision_changed") is not False):
                        raise ValueError("Draft cannot contain admissions")
                    entry = {"packet": result["packet"],
                             "workbench": result["workflow_binding"]["workbench"],
                             "workflow_binding": result["workflow_binding"], "scope": MOCK_SCOPE}
                    proposed = deepcopy(current)
                    proposed["cases"].setdefault(symbol, {"workflows": {}})["workflows"][workflow] = entry
                    candidate_path.write_text(json.dumps(proposed, ensure_ascii=False), encoding="utf-8")
                    view = _read_registered_research(root, symbol=symbol, workflow=workflow,
                        now=now, registry_name=candidate_name)
                    if view["status"] != "VERIFIED":
                        raise ValueError("Candidate failed existing Web verification")
                    unchanged = current["cases"].get(symbol, {}).get("workflows", {}).get(workflow) == entry
                    current = proposed
                    accepted.append(identity)
                    item["status"] = "UNCHANGED" if unchanged else "REGISTERED"
                except (ValueError, OSError, KeyError, TypeError, AttributeError):
                    item["status"] = "REJECTED"
            changed = any(item["status"] == "REGISTERED" for item in items)
            if changed:
                candidate_raw = (json.dumps(current, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                if len(candidate_raw) > 64 * 1024:
                    raise ValueError("Candidate registry exceeds Web bounds")
                candidate_path.write_bytes(candidate_raw)
                for symbol, workflow in accepted:
                    if _read_registered_research(root, symbol=symbol, workflow=workflow, now=now,
                            registry_name=candidate_name)["status"] != "VERIFIED":
                        raise ValueError("Draft changed before registration")
                actual = _raw(registry_path, 64 * 1024) if registry_path.exists() else None
                if actual != previous:
                    raise ValueError("Registry changed during registration")
                if previous is not None:
                    history = scratch / (hashlib.sha256(previous).hexdigest() + ".json")
                    if history.exists():
                        if history.read_bytes() != previous:
                            raise ValueError("Registry history conflicts")
                    else:
                        with history.open("xb") as stream:
                            stream.write(previous)
                os.replace(candidate_path, registry_path)
        registered = sum(item["status"] == "REGISTERED" for item in items)
        good = sum(item["status"] in {"REGISTERED", "UNCHANGED"} for item in items)
        return {"schema_version": "daily-agent-display-registration-v1", "action": "no_order",
                "status": "PARTIAL" if good and good != len(items) else
                    "UPDATED" if registered else "UNCHANGED" if good else "BLOCKED",
                "items": items, "registered_count": registered, "approval_count": 0,
                "decision_changed": False, "formal_eligibility_changed": False}
    finally:
        os.close(handle)
        lock.unlink()

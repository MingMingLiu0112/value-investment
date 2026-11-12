"""Cold-read a plan-neutral V19 D2 task using the established E2 input gate."""
from datetime import datetime
from pathlib import Path
from copy import deepcopy
import hashlib
import json

from .operating_horizon_cash_policy_e2_v2 import _read_bound_cash_policy_e2_input
from .agent_review.operating_horizon_task_v19_generic import CONTRACT, OperatingHorizonTaskService
from .agent_review import operating_horizon_sources_v1 as generic_sources

VERSION = "operating-horizon-cash-policy-e2-input-v11"


def read_generic_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                       contract: str, service_type, version: str,
                                       label: str, service=None, staged_annual=False) -> dict:
    if service is not None and (not isinstance(service, service_type)
            or Path(root).resolve() != service.root.resolve()):
        raise ValueError(label + "_E2_BOUND_SERVICE_REQUIRED")
    service = service or service_type(root)
    spec, _, _ = service._load(task_id)
    if spec["source_loader_binding"]["version"] != generic_sources.VERSION:
        replay = service
        projection = None
    else:
        original = service._context(spec)  # Exact source bytes and loader are replayed first.
        projected = deepcopy(original)
        changed = []
        for row in projected["evidence"]:
            if row.get("kind") != "SOURCE_BOUND_REPORTED_STATEMENT_ROW":
                continue
            digest = row.get("pdf_sha256")
            if (not isinstance(digest, str) or len(digest) != 64
                    or row.get("source_id") != "official:" + digest
                    or not isinstance(row.get("physical_page"), int)
                    or row["physical_page"] < 1 or row.get("unit") != "CNY"
                    or not row.get("available_at") or not row.get("period")):
                raise ValueError(label + "_E2_REPORTED_FACT_PROVENANCE_INVALID")
            row["kind"] = "VERIFIED_REPORTED_FACT"
            changed.append(row["id"])

        class Replay:
            def read(self, candidate):
                return service.read(candidate)

            def _load(self, candidate):
                return service._load(candidate)

            def _context(self, candidate_spec):
                if candidate_spec != spec:
                    raise ValueError(label + "_E2_SOURCE_SPEC_CHANGED")
                service._context(spec)
                return deepcopy(projected)

            def _packet(self, candidate_spec, state, stage):
                return service._packet(candidate_spec, state, stage)

            def _annual_checkpoint(self, candidate_spec, state, source_context):
                if candidate_spec != spec or source_context != projected:
                    raise ValueError(label + "_E2_SOURCE_SPEC_CHANGED")
                return service._annual_checkpoint(spec, state, original)

        replay = Replay()
        projection = dict(source_kind="SOURCE_BOUND_REPORTED_STATEMENT_ROW",
            e2_kind="VERIFIED_REPORTED_FACT", evidence_ids=changed,
            original_context_sha256=spec["context_sha256"])
    result = _read_bound_cash_policy_e2_input(root=root, task_id=task_id, now=now,
        contract=contract, task_service=service_type,
        version=version, label=label, service=replay, staged_annual=staged_annual)
    if projection is not None:
        result["input_manifest"]["source_kind_projection"] = projection
        result["input_fingerprint"] = hashlib.sha256(json.dumps(
            result["input_manifest"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return result


def read_v19_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                   service=None) -> dict:
    return read_generic_cash_policy_e2_input(root=root, task_id=task_id, now=now,
        contract=CONTRACT, service_type=OperatingHorizonTaskService,
        version=VERSION, label="V19", service=service)

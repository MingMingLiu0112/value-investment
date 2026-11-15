"""Pin an HTTP submission to the existing V25 task identity across retries."""
from datetime import datetime, timezone
import json
import re

from ...product.common import require_inside, write_new_bytes
from .operating_horizon_task_v25_canonical import CONTRACT
from .task_execution_v1 import _bytes, _hash


def submit_bound_v25(service, inputs):
    """Return (task, should_dispatch, missing_anchors); never run a model here."""
    from ..operating_horizon_cash_policy_e2_v17 import cash_constraint_anchor_ids

    symbol, key, years = inputs["symbol"], inputs["request_key"], inputs["years"]
    if (years != [2027] or not re.fullmatch(r"[0-9]{6}", symbol)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", key)):
        raise ValueError("V25_IDENTITY_INVALID")
    key_hash = _hash(key.encode("utf-8"))
    directory = require_inside(service.base, service.base / ".submissions" / key_hash, "V25 submission")
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "request.json"
    with service._lock(directory):
        identity = dict(symbol=symbol, years=years, request_key_sha256=key_hash,
                        loader_version=service.source_loader_version, action="no_order")
        if manifest.exists():
            pin = json.loads(manifest.read_bytes())
            if any(pin.get(field) != value for field, value in identity.items()):
                raise ValueError("V25_REQUEST_CONFLICT")
            now = datetime.fromisoformat(pin["cutoff"])
            expected_id = pin["task_id"]
            if (service._directory(expected_id) / "input.json").is_file():
                spec, _, _ = service._load(expected_id)
                if (spec["request_key_sha256"] != key_hash or spec["symbol"] != symbol
                        or spec["source_binding"] != pin["source_binding"]):
                    raise ValueError("V25_REQUEST_CONFLICT")
                return service.read(expected_id), False, []
        else:
            pin = None
            now = datetime.now(timezone.utc)
        context = service.source_loader(root=service.root, symbol=symbol, now=now)
        binding = context["source_binding"]
        missing = sorted(term for term, ids in cash_constraint_anchor_ids(context).items() if not ids)
        if missing:
            return None, False, missing
        mode = "TEST_ONLY_LIVE_CONTRACT" if service.test_provider else "LIVE_OPERATING"
        task_id = "rt-" + _hash(_bytes([CONTRACT, mode, symbol, years, binding]))[:32]
        expected = dict(identity, cutoff=now.isoformat(), source_binding=binding, task_id=task_id)
        if pin is None:
            write_new_bytes(manifest, _bytes(expected))
        elif pin != expected:
            raise ValueError("V25_REQUEST_SOURCE_CHANGED")
        task = service.create(**inputs, now=now)
        if task["task_id"] != task_id:
            raise ValueError("V25_REQUEST_SOURCE_CHANGED")
        return task, task["status"] == "QUEUED", []

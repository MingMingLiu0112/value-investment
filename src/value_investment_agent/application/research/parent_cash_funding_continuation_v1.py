"""Persist a deterministic recheck separately from the paid V3 task and signed inputs."""
from hashlib import sha256
from itertools import islice
import json
import re
from pathlib import Path

from ..portfolio.private_journal_lock import InterProcessLock
from ..product.common import _native_path, write_new_bytes
from . import parent_cash_funding_revision_v1 as revision

VERSION = "fixed-payment-v1"
LIMIT = 2 * 1024**2


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _checker():
    from . import parent_cash_fixed_payment_recheck
    return parent_cash_fixed_payment_recheck


def _implementation(checker):
    return {module.__name__: sha256(Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for module in (revision, checker)}


def _read_seal(write_root, folder, identity):
    try:
        directory = revision._checked_path(write_root, folder)
    except FileNotFoundError:
        return None
    entries = list(islice(directory.iterdir(), 17))
    if len(entries) > 16:
        raise ValueError("CONTINUATION_DIRECTORY_LIMIT")
    # write_new_bytes publishes atomically. Its private .part files may survive a crash.
    sealed = [entry for entry in entries if entry.name != "replay.lock"
              and not (entry.name.startswith(".") and entry.name.endswith(".part"))]
    if not sealed:
        return None
    if len(sealed) != 1 or not re.fullmatch(r"[a-f0-9]{64}\.json", sealed[0].name):
        raise ValueError("CONTINUATION_SEAL_INVALID")
    source = revision._checked_path(write_root, folder / sealed[0].name)
    if not source.is_file() or source.stat().st_size > LIMIT:
        raise ValueError("CONTINUATION_SEAL_INVALID")
    with source.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    digest = sha256(data).hexdigest()
    if len(data) > LIMIT or digest != source.stem:
        raise ValueError("CONTINUATION_SEAL_CHANGED")
    record = json.loads(data)
    if any(record[key] != value for key, value in identity.items()):
        raise ValueError("CONTINUATION_BINDING_CHANGED")
    return dict(record, continuation_sha256=digest)


def replay_or_read(source_root, write_root, identity, *, create, now):
    """Resume a sealed correction. The source owner and publication root may differ."""
    task_id, digest = identity["task_id"], identity["receipt_sha256"]
    if not re.fullmatch(r"rt-[a-f0-9]{32}", task_id) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("CONTINUATION_ID_INVALID")
    folder = (write_root / "runtime" / "parent-cash-task-backed-receipts" / task_id
              / "funding-continuations" / digest / VERSION)
    checker = _checker()
    identity = dict(identity, continuation_version=VERSION, action="no_order", formal_eligibility=False,
                    current_comparable=False, new_llm_calls=0, status="REPLAYED",
                    implementation_sha256=_implementation(checker))
    retained = _read_seal(write_root, folder, identity)
    if retained is not None or not create:
        return retained

    # Never follow an existing junction, including the lock or either output directory.
    directory = write_root
    for part in folder.relative_to(write_root).parts:
        directory = directory / part
        Path(_native_path(directory)).mkdir(exist_ok=True)
        revision._checked_path(write_root, directory)
    lock = folder / "replay.lock"
    try:
        revision._checked_path(write_root, lock)
    except FileNotFoundError:
        pass
    with InterProcessLock(Path(_native_path(lock)), timeout_seconds=0.05):
        retained = _read_seal(write_root, folder, identity)
        if retained is not None:
            return retained
        # run_check cold-replays the predecessor itself before applying the fixed payment.
        corrected = checker.run_check(source_root, task_id, digest, now)
        if (corrected["schema_version"] != "fixed-owner-payment-cash-recheck-v1"
                or corrected["parent_receipt"] != digest or corrected["task_id"] != task_id
                or corrected["predecessor_input"] != identity["reassessment_spec_sha256"]
                or corrected["symbol"] != identity["symbol"] or corrected["valuation_date"] != identity["valuation_date"]
                or corrected["action"] != "no_order" or corrected["formal_eligibility"] is not False
                or corrected["current_comparable"] is not False):
            raise ValueError("CONTINUATION_FIXED_PAYMENT_RESULT_INVALID")
        scenarios = corrected["scenarios"]
        if (set(scenarios) != {"bear", "base", "bull"}
                or any(row["status"] not in {"CALCULATED", "REJECTED"} for row in scenarios.values())
                or corrected["status"] != ("REJECTED" if any(row["status"] == "REJECTED"
                    for row in scenarios.values()) else "CALCULATED")):
            raise ValueError("CONTINUATION_FIXED_PAYMENT_RESULT_INVALID")
        if _implementation(checker) != identity["implementation_sha256"]:
            raise ValueError("CONTINUATION_IMPLEMENTATION_CHANGED")
        record = dict(identity, completed_at=now.isoformat(), fixed_payment_recheck=corrected)
        data = _bytes(record)
        if len(data) > LIMIT:
            raise ValueError("CONTINUATION_SEAL_TOO_LARGE")
        seal_sha = sha256(data).hexdigest()
        write_new_bytes(folder / (seal_sha + ".json"), data)
        return dict(record, continuation_sha256=seal_sha)

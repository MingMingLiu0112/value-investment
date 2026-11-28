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
MATURITY_VERSION = "maturity-v1"
MULTIYEAR_VERSION = "multiyear-v1"
LIMIT = 2 * 1024**2


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _checker():
    from . import parent_cash_fixed_payment_recheck
    return parent_cash_fixed_payment_recheck


def _implementation(checker):
    modules = [revision, checker]
    if checker.__name__.endswith(".parent_cash_maturity_recheck"):
        modules.append(_checker())
    multiyear = checker.__name__.endswith(".parent_cash_multiyear_recheck")
    if multiyear or checker.__name__.endswith(".parent_cash_installment_recheck"):
        from . import parent_cash_maturity_recheck
        modules.extend([_checker(), parent_cash_maturity_recheck])
    if multiyear:
        from . import parent_cash_installment_recheck, direct_owner_cash_input_adapter_v2
        modules.extend([parent_cash_installment_recheck, direct_owner_cash_input_adapter_v2, checker.kernel, checker.model])
    return {module.__name__: sha256(Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for module in modules}


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


def replay_or_read(source_root, write_root, identity, *, create, now, version=VERSION):
    """Resume a sealed correction. The source owner and publication root may differ."""
    task_id, digest = identity["task_id"], identity["receipt_sha256"]
    if not re.fullmatch(r"rt-[a-f0-9]{32}", task_id) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("CONTINUATION_ID_INVALID")
    if version == VERSION:
        checker = _checker()
        result_key, schema = "fixed_payment_recheck", "fixed-owner-payment-cash-recheck-v1"
    elif version == MATURITY_VERSION:
        from . import parent_cash_maturity_recheck as checker
        result_key, schema = "maturity_recheck", "parent-cash-maturity-recheck-v1"
    elif version == "installment-v1":
        from . import parent_cash_installment_recheck as checker
        result_key, schema = "installment_recheck", "parent-cash-installment-recheck-v1"
    elif version == MULTIYEAR_VERSION:
        from . import parent_cash_multiyear_recheck as checker
        result_key, schema = "multiyear_recheck", "parent-cash-multiyear-recheck-v1"
    else:
        raise ValueError("CONTINUATION_VERSION_UNSUPPORTED")
    folder = (write_root / "runtime" / "parent-cash-task-backed-receipts" / task_id
              / "funding-continuations" / digest / version)
    identity = dict(identity, continuation_version=version, action="no_order", formal_eligibility=False,
                    current_comparable=False, new_llm_calls=0, status="REPLAYED",
                    implementation_sha256=_implementation(checker))
    if version == MULTIYEAR_VERSION:
        identity["new_model_cost_cny"] = 0
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
        if (corrected["schema_version"] != schema
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
        if version == MATURITY_VERSION:
            alternative = corrected["alternative_scenarios"]
            if (set(alternative) != set(scenarios) or corrected["current_research_range_adopted"] is not False
                    or any(row["status"] not in {"CALCULATED", "REJECTED"} for row in alternative.values())):
                raise ValueError("CONTINUATION_MATURITY_ALTERNATIVES_INVALID")
        if version == MULTIYEAR_VERSION:
            fallback = corrected["early_maturity_stress"]
            fallback_status = "REJECTED" if any(r["status"] == "REJECTED" for r in fallback.values()) else "CALCULATED"
            if (corrected["financing_condition_verified"] is not False
                    or corrected["unverified_financing_fallback_status"] != fallback_status
                    or corrected["current_research_range_adopted"] is not False or not corrected["base_basis"]):
                raise ValueError("CONTINUATION_MULTIYEAR_RESULT_INVALID")
            for group in (scenarios, corrected["original_installment_stress"], corrected["early_maturity_stress"]):
                if set(group) != set(scenarios):
                    raise ValueError("CONTINUATION_MULTIYEAR_SCENARIOS_INVALID")
                for row in group.values():
                    if (row["status"] not in {"CALCULATED", "REJECTED"}
                            or row["financing_rows_basis"] != "CONDITIONAL_PAYMENT_PLAN"
                            or not isinstance(row["financing_rows"], list)
                            or (row["status"] == "REJECTED" and
                                (not row["reason"] or not isinstance(row["first_failed_year"], int)))
                            or (row["status"] == "CALCULATED" and
                                (row["first_failed_year"] is not None or not row["annual_rows"] or not row["per_share_value"]))):
                        raise ValueError("CONTINUATION_MULTIYEAR_SCENARIOS_INVALID")
        if _implementation(checker) != identity["implementation_sha256"]:
            raise ValueError("CONTINUATION_IMPLEMENTATION_CHANGED")
        record = dict(identity, completed_at=now.isoformat(), **{result_key: corrected})
        data = _bytes(record)
        if len(data) > LIMIT:
            raise ValueError("CONTINUATION_SEAL_TOO_LARGE")
        seal_sha = sha256(data).hexdigest()
        write_new_bytes(folder / (seal_sha + ".json"), data)
        return dict(record, continuation_sha256=seal_sha)

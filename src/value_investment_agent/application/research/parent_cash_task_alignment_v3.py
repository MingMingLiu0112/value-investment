"""Project a verified live research receipt into the shared F2 checks."""
from datetime import date, datetime
from pathlib import Path

from ...research_run_contract import canonical_contract_payload
from ..product.common import sha256_bytes

from .direct_owner_cash_research_v1 import _read
from .parent_cash_task_distribution_receipt_v1 import replay as replay_parent_cash_task_receipt
from .parent_cash_task_share_anchor_v3 import read_task_share_anchors
from .pending_candidate_alignment import _event_windows, _load_bound_alignment
from .value_research_analysis import _bound

INPUT_SCHEMA = "parent-cash-task-alignment-input-v3"


def read_parent_cash_task_alignment(
    *, root: Path, receipt_binding: dict, now: datetime,
) -> dict:
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("PARENT_TASK_ALIGNMENT_AWARE_CLOCK_REQUIRED")
    result = replay_parent_cash_task_receipt(root=root, receipt_binding=receipt_binding, now=now)
    return _align_verified_parent_cash_task(
        root=root, receipt_binding=receipt_binding, result=result, now=now)


def prepare_parent_cash_task_materiality_handoff(
    *, root: Path, receipt_binding: dict, observation_binding: dict,
    review_through: date, now: datetime,
) -> dict:
    """Prepare an unsigned evidence inventory from a cold-replayed V3 receipt."""
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None or type(review_through) is not date:
        raise ValueError("PARENT_TASK_MATERIALITY_CLOCK_OR_CUTOFF_INVALID")
    result = replay_parent_cash_task_receipt(root=root, receipt_binding=receipt_binding, now=now)
    return _prepare_verified_materiality(root, receipt_binding, result, observation_binding,
                                         review_through, now)


def _prepare_verified_materiality(root, receipt_binding, result, observation_binding, review_through, now):
    receipt = _read(root, receipt_binding)
    descriptor = result["descriptor"]
    valuation = result["valuation"]
    fingerprint = result["input_descriptor_sha256"]
    symbol = result["symbol"]
    start = date.fromisoformat(descriptor["point_in_time"]["valuation_date"])
    if (result["action"] != "no_order" or result["formal_eligibility"] is not False
            or result["main_range_adopted"] is not False
            or descriptor["input_sha256"] != fingerprint or descriptor["symbol"] != symbol
            or valuation["symbol"] != symbol or valuation["valuation_date"] != start.isoformat()
            or start > review_through):
        raise ValueError("PARENT_TASK_MATERIALITY_CANDIDATE_IDENTITY_MISMATCH")

    # Reuse the same provider-independent original/index/scan replay as F2.
    checked = {}

    def read(binding):
        path = _bound(root, binding)
        previous = checked.setdefault(binding["path"], binding["sha256"])
        if previous != binding["sha256"]:
            raise ValueError("PARENT_TASK_MATERIALITY_SOURCE_HASH_CONFLICT")
        return path

    read(receipt_binding)
    read(receipt["result_binding"])
    for binding in result["source_bindings"]:
        read(binding)
    provenance = result["provenance"]
    for field in ("spec_binding", "task_record_binding"):
        read(provenance[field])

    (window,), (scan,) = _event_windows(root, dict(symbol=symbol, event_pdf_byte_limit=128 * 1024 * 1024),
                                         [observation_binding], now, read)
    if (window["source_integrity_verified"] is not True or window["full_calendar_window_elapsed"] is not True
            or window["coverage_status"] != "COMPLETE" or scan.coverage_status != "COMPLETE"
            or scan.symbol != symbol or scan.validity_from != start or scan.scan_from != start
            or scan.scan_to != review_through or scan.retrieved_at > now or not scan.announcements):
        raise ValueError("PARENT_TASK_MATERIALITY_EXACT_CLOSED_SCAN_REQUIRED")

    announcements = window["announcements"]
    if (len(announcements) != len({row["announcement_id"] for row in announcements})
            or any(not row["evidence_refs"] for row in announcements)):
        raise ValueError("PARENT_TASK_MATERIALITY_ANNOUNCEMENT_IDENTITY_INVALID")
    for row in announcements:
        for source in row["evidence_refs"]:
            read({key: source[key] for key in ("path", "sha256")})

    handoff = dict(
        schema_version="parent-cash-task-materiality-unsigned-handoff-v1",
        status="UNSIGNED_REVIEW_REQUIRED", action="no_order", formal_eligibility=False,
        materiality_approved=False, symbol=symbol, candidate_binding=dict(receipt_binding),
        receipt_schema=receipt["schema_version"], result_binding=receipt["result_binding"],
        task_id=receipt["inputs"]["task_id"], task_head=receipt["inputs"]["task_head"],
        spec_binding=provenance["spec_binding"], task_record_binding=provenance["task_record_binding"],
        input_descriptor_sha256=fingerprint, valuation=valuation,
        observation_binding=dict(observation_binding), scan_binding=window["scan_binding"],
        scan_window=dict(scan_from=scan.scan_from.isoformat(), scan_to=scan.scan_to.isoformat(),
                         retrieved_at=scan.retrieved_at.isoformat(), acquired_at=window["acquired_at"]),
        announcements=announcements,
    )
    read(handoff["task_head"])
    for path, digest in checked.items():
        _bound(root, dict(path=path, sha256=digest))
    return dict(handoff, handoff_sha256=sha256_bytes(canonical_contract_payload(handoff).encode("utf-8")))


def _distribution_model_inclusion(*, root, result, start, end, now):
    """Bind one V3 distribution to its original without establishing settlement."""
    from .parent_owner_distribution_alignment_v2 import _implemented_distribution
    from .parent_owner_distribution_successor_v2 import replay_parent_owner_distribution_successor

    binding = result["provenance"].get("distribution_receipt_binding")
    if binding is None or start >= end:
        return []
    source_contract = result["descriptor"]["source_contract"]
    distribution = source_contract["implemented_distribution"]
    if not start < date.fromisoformat(distribution["paid_date"]) <= end:
        return []
    if (source_contract["distribution_receipt_binding"] != binding
            or binding not in result["source_bindings"]):
        raise ValueError("PARENT_TASK_DISTRIBUTION_OUTSIDE_SOURCE_CLOSURE")
    source_receipt = _read(root, binding)
    source = replay_parent_owner_distribution_successor(root=root, receipt_binding=binding, now=now)
    if (source["symbol"] != result["symbol"] or source["distribution"] != distribution
            or any(ref not in result["source_bindings"]
                   for ref in source["distribution_evidence"].values())):
        raise ValueError("PARENT_TASK_DISTRIBUTION_SOURCE_IDENTITY_MISMATCH")
    # Reuse exact original/amount checks against the valuation that F2 will compare.
    spec = _read(root, source_receipt["spec_binding"])
    model_source = dict(source, valuation=result["valuation"])
    return [_implemented_distribution(model_source, spec, source_receipt, root)]

def _align_verified_parent_cash_task(*, root: Path, receipt_binding: dict, result: dict,
                                     now: datetime) -> dict:
    descriptor = result["descriptor"]
    dates = descriptor["point_in_time"]
    inputs = descriptor["facts"]["scenario_inputs"]
    shares = inputs["base"]["ordinary_shares"]
    if (result["action"] != "no_order" or result["formal_eligibility"] is not False
            or result["main_range_adopted"] is not False
            or descriptor["symbol"] != result["symbol"]
            or descriptor["input_sha256"] != result["input_descriptor_sha256"]
            or any(row["currency"] != "CNY" or row["ordinary_shares"] != shares
                   for row in inputs.values())):
        raise ValueError("PARENT_TASK_ALIGNMENT_REPLAY_IDENTITY_MISMATCH")
    receipt = _read(root, receipt_binding)
    bindings = [*result["source_bindings"], receipt["result_binding"],
                result["provenance"]["spec_binding"], result["provenance"]["task_record_binding"]]
    anchors = read_task_share_anchors(root=root, result=result)
    paths = {anchor["source_id"]: anchor["binding"]["path"] for anchor in anchors}
    catalog = [dict(source, local_path=paths.get(source["id"], source.get("local_path")),
                    source_available_at=source.get("retrieved_at"))
               for source in descriptor["sources"]]
    analysis = dict(
        status="CONDITIONAL_ANALYSIS_VERIFIED", action="no_order", arithmetic_complete=True,
        symbol=result["symbol"], valuation_date=dates["valuation_date"],
        research_as_of=dates["research_as_of"],
        input_descriptor_sha256=result["input_descriptor_sha256"],
        review_binding=dict(candidate_binding=dict(receipt_binding)),
        prepare_unsigned_task_materiality=lambda window: _prepare_verified_materiality(
            root, receipt_binding, result, window["observation_binding"],
            date.fromisoformat(window["scan_to"]), now),
        valuation=result["valuation"], source_bindings=bindings,
        event_pdf_byte_limit=128 * 1024 * 1024,
        source_catalog=catalog, official_fact_anchors=anchors,
        consumed_operating_inputs=dict(ordinary_shares=shares),
        distribution_model_inclusion=lambda start, end: _distribution_model_inclusion(
            root=root, result=result, start=start, end=end, now=now),
        joint_capital_review=dict(economic_path=dict(currency="CNY")),
    )
    return _load_bound_alignment(root=root, analysis=analysis, now=now, input_schema=INPUT_SCHEMA)

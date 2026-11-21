"""Project a verified live research receipt into the shared F2 checks."""
from datetime import datetime
from pathlib import Path

from .direct_owner_cash_research_v1 import _read
from .parent_cash_task_receipt_v3 import replay_parent_cash_task_receipt
from .parent_cash_task_share_anchor_v3 import read_task_share_anchors
from .pending_candidate_alignment import _load_bound_alignment

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
        valuation=result["valuation"], source_bindings=bindings,
        event_pdf_byte_limit=128 * 1024 * 1024,
        source_catalog=catalog, official_fact_anchors=anchors,
        consumed_operating_inputs=dict(ordinary_shares=shares),
        joint_capital_review=dict(economic_path=dict(currency="CNY")),
    )
    return _load_bound_alignment(root=root, analysis=analysis, now=now, input_schema=INPUT_SCHEMA)

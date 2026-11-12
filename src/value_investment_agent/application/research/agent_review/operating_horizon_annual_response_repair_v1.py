"""Pure, narrowly scoped repair for misplaced annual response declarations."""

from copy import deepcopy
import hashlib

from . import operating_horizon_annual_v3 as annual
from . import operating_draft_v1 as common
from .operating_driver_draft_v2 import _payload, _exact

VERSION = "operating-horizon-annual-response-repair-v1"
FIELDS = ("counter_evidence", "reopen_condition")
SCENARIOS = ("bear", "base", "bull")


def normalize_response(raw_response_text, source_context, years, generated_at):
    """Return validated annual result and a hash-bound relocation trace.

    Only a pair placed directly under one year's operating_paths is repaired.
    All other validation belongs to the unchanged annual contract.
    """
    if not isinstance(raw_response_text, str):
        raise ValueError("ANNUAL_REPAIR_RAW_TEXT_REQUIRED")
    payload = _payload(raw_response_text)
    _exact(payload, ("years",))
    _exact(payload["years"], [str(year) for year in years])
    derived = deepcopy(payload)
    trace = []
    for year, row in derived["years"].items():
        if not isinstance(row, dict) or "operating_paths" not in row:
            raise ValueError("ANNUAL_REPAIR_YEAR_SHAPE_INVALID")
        paths = row["operating_paths"]
        if not isinstance(paths, dict):
            raise ValueError("ANNUAL_REPAIR_PATHS_SHAPE_INVALID")
        misplaced = [field for field in FIELDS if field in paths]
        if misplaced:
            if set(misplaced) != set(FIELDS) or any(field in row for field in FIELDS):
                raise ValueError("ANNUAL_REPAIR_PARTIAL_OR_CONFLICTING_FIELDS")
            _exact(paths, (*SCENARIOS, *FIELDS))
            for field in FIELDS:
                row[field] = paths.pop(field)
                trace.append({"from": f"/years/{year}/operating_paths/{field}",
                              "to": f"/years/{year}/{field}"})
        else:
            _exact(paths, SCENARIOS)
    if not trace:
        raise ValueError("ANNUAL_REPAIR_NO_RELOCATION")
    derived_text = common._canonical(derived)
    result = annual.validate_response(derived_text, source_context, years, generated_at)
    return {"version": VERSION, "raw_sha256": hashlib.sha256(raw_response_text.encode("utf-8")).hexdigest(),
            "derived_sha256": hashlib.sha256(derived_text.encode("utf-8")).hexdigest(),
            "relocations": trace, "validated_result": result}

"""Read-only public fields from a task-bound, content-addressed financing revision."""
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from itertools import islice
import json
from pathlib import Path
import re
from stat import FILE_ATTRIBUTE_REPARSE_POINT, S_ISLNK, S_ISREG

from ...application.product.common import _native_path
from ...application.research.parent_cash_funding_revision_v1 import load_matrix, verify_source_set

from ...research_run_contract import canonical_contract_payload

SCHEMA = "source-bound-parent-financing-research-revision-v1"
SHA = re.compile(r"[0-9a-f]{64}")
CASH_FIELDS = ("opening_cash_cny", "direct_operating_cash_cny", "total_owner_distribution_cny",
               "closing_cash_cny", "closing_debt_cny")
MIB = 1024 * 1024


class RevisionError(ValueError):
    """Only fixed codes raised here may cross the HTTP boundary."""


def require(condition, code):
    if not condition:
        raise RevisionError(code)


def directory(root, task_id):
    require(re.fullmatch(r"rt-[0-9a-f]{32}", task_id), "TASK_IDENTITY")
    return root / "runtime" / "parent-cash-task-backed-receipts" / task_id / "funding-revisions"


def _checked_path(root, path, code):
    require(root.is_absolute() and path.is_relative_to(root), code)
    current = root
    for part in ("", *path.relative_to(root).parts):
        require(part != "..", code)
        current = current / part
        info = Path(_native_path(current)).lstat()
        require(not S_ISLNK(info.st_mode) and not (
            getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT), code)
    return Path(_native_path(path))


def verified_bytes(root, path, digest, limit, code):
    require(isinstance(digest, str) and SHA.fullmatch(digest), code)
    try:
        path = _checked_path(root, path, code)
        info = path.stat()
        require(S_ISREG(info.st_mode) and 0 < info.st_size <= limit, code)
        with path.open("rb") as stream:
            raw = stream.read(info.st_size + 1)
    except OSError:
        raise RevisionError(code) from None
    require(len(raw) == info.st_size and sha256(raw).hexdigest() == digest, code)
    return raw


def public_number(value):
    require(isinstance(value, str) and re.fullmatch(
        r"-?\d{1,40}(?:\.\d{1,80})?(?:[Ee][+-]?\d{1,2})?", value), "SCENARIO_CASH")
    return value


def _scenarios(valuation, start):
    calculations = valuation["assumptions"]["scenario_calculations"]
    require(set(calculations) == {"bear", "base", "bull"}, "SCENARIO_CASH")
    result = {}
    for name in ("bear", "base", "bull"):
        calculation = calculations[name]
        value = public_number(calculation["per_share_value"])
        require(Decimal(value) == Decimal(public_number(valuation[name + "_value"])), "SCENARIO_CASH")
        rows = calculation["annual_rows"]
        require(isinstance(rows, list) and 1 <= len(rows) <= 30, "SCENARIO_CASH")
        annual = []
        for index, row in enumerate(rows, 1):
            require(type(row["year"]) is int and row["year"] == start.year + index, "SCENARIO_CASH")
            annual.append(dict(year=row["year"], **{key: public_number(row[key]) for key in CASH_FIELDS}))
        result[name] = dict(per_share_value=value, annual_rows=annual)
    return result


def _reason(value):
    # Public reason codes and short explanatory text only; never echo a payload or a path.
    require(isinstance(value, str) and 1 <= len(value) <= 240 and re.fullmatch(
        r"[\w\u3400-\u9fff ，。、（）：；《》“”【】·％%：:,;()=+\-\.]+", value), "REASSESSMENT_FORMAT")
    return value


def _reassessment(receipt):
    if "current_reassessment" not in receipt:
        return None
    try:
        value = receipt["current_reassessment"]
        require(value["status"] in ("REJECTED", "UNAVAILABLE")
                and value["current_research_range_adopted"] is False, "REASSESSMENT_FORMAT")
        rows = value.get("scenario_rows", {})
        require(isinstance(rows, dict) and set(rows) <= {"bear", "base", "bull"}, "REASSESSMENT_FORMAT")
        public = {}
        for name, row in rows.items():
            status = row["status"]
            require(isinstance(status, str) and re.fullmatch(r"[A-Z_]{2,64}", status), "REASSESSMENT_FORMAT")
            item = {"status": status}
            if "reason" in row:
                item["reason"] = _reason(row["reason"])
            for key in ("per_share_value", "floor", "before"):
                if row.get(key) is not None:
                    item[key] = public_number(row[key])
            if row.get("year") is not None:
                year = str(row["year"])
                require(re.fullmatch(r"[12]\d{3}", year), "REASSESSMENT_FORMAT")
                item["year"] = int(year)
            public[name] = item
        return dict(status=value["status"], reason=_reason(value["reason"]), scenario_rows=public,
                    current_research_range_adopted=False)
    except (KeyError, TypeError, ValueError, AttributeError):
        return dict(status="UNAVAILABLE", reason="REASSESSMENT_FORMAT", scenario_rows={},
                    current_research_range_adopted=False)


def _financing_terms(spec, matrix):
    research = spec["financing_revision"]
    if "known_maturities" not in research:
        return None
    try:
        maturities = research["known_maturities"]
        require(isinstance(maturities, list) and 1 <= len(maturities) <= 64
                and research["unknown_balance_is_forecast"] is True, "FINANCING_TERMS")
        issues = []
        seen = set()
        for row in maturities:
            code = row["code"]
            require(re.fullmatch(r"[0-9]{6,12}", code) and code not in seen, "FINANCING_TERMS")
            seen.add(code)
            day = date.fromisoformat(row["maturity"]).isoformat()
            amount = public_number(row["principal_cny"])
            require(day == row["maturity"] and Decimal(amount) > 0, "FINANCING_TERMS")
            issues.append(dict(code=code, maturity=day, principal_cny=amount))
        terms = {key: public_number(research[key]) for key in (
            "residual_principal_cny", "cash_interest_9m_verified_floor", "mixed_less_dividend_cny")}
        rates = {name: public_number(research["unknown_rate_assumptions"][name])
                 for name in ("bear", "base", "bull")}
        require(all(Decimal(value) >= 0 for value in terms.values())
                and all(0 <= Decimal(rate) <= 1 for rate in rates.values()), "FINANCING_TERMS")
        if matrix:
            terms.update({key: public_number(matrix["prospective_debt_service"][key]) for key in (
                "five_scp_conditional_coupon_2026Q4", "mtn_conditional_coupon_2027")})
        return dict(status="VERIFIED", known_maturities=sorted(issues, key=lambda i: (i["maturity"], i["code"])),
                    unknown_rate_assumptions=rates, **terms)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return {"status": "UNAVAILABLE"}


def _project(root, folder, task_id, symbol, head, original, cache):
    def document(label, path, digest, limit):
        raw = verified_bytes(root, path, digest, limit, label)
        try:
            parsed = load_matrix(raw) if label in ("FINANCING-EVIDENCE_HASH", "SOURCE_MATRIX_HASH") else json.loads(raw)
        except (ValueError, RecursionError):
            raise RevisionError(label) from None
        require(isinstance(parsed, dict), label)
        return parsed

    r = document("RECEIPT_HASH", folder / "receipt.json", folder.name, 128 * 1024)
    require(r.get("schema_version") == SCHEMA and r.get("provenance") == "DETERMINISTIC_RESEARCH_REVISION"
            and r.get("action") == "no_order" and r.get("formal_eligibility") is False
            and r.get("current_comparable") is False, "REVISION_SCOPE")
    require((r.get("task_id"), r.get("symbol"), r.get("parent_head"), r.get("registered_spec"))
            == (task_id, symbol, head, original), "TASK_IDENTITY")
    def sibling(field, prefix, fields=r):
        pin = fields.get(field)
        require(isinstance(pin, dict) and isinstance(pin.get("sha256"), str)
                and SHA.fullmatch(pin["sha256"]) and pin.get("file") == f"{prefix}-{pin['sha256']}.json",
                prefix.upper() + "_HASH")
        return document(prefix.upper() + "_HASH", folder / pin["file"], pin["sha256"], 2 * MIB)

    spec = sibling("revision_spec", "spec")
    val = sibling("valuation", "valuation")
    desc = sibling("descriptor", "descriptor")
    date_text = r["valuation_date"]
    day = date.fromisoformat(date_text)
    stamp = datetime.fromisoformat(r["completed_at"])
    require(day.isoformat() == date_text and stamp.utcoffset() is not None
            and stamp <= datetime.now(timezone.utc) and day <= stamp.date(), "REVISION_DATE")
    require(all(obj.get("symbol") == symbol for obj in (spec, val, desc))
            and spec.get("valuation_date") == val.get("valuation_date") == date_text
            and desc["point_in_time"]["valuation_date"] == date_text
            and val.get("status") == "conditional_research_only", "VALUATION_IDENTITY")
    spec_hash = r["revision_spec"]["sha256"]
    contract = desc["source_contract"]
    digest = desc.pop("input_sha256", None)
    require(digest == r.get("input_descriptor_sha256")
            and sha256(canonical_contract_payload(desc).encode()).hexdigest() == digest, "DESCRIPTOR_IDENTITY")
    require(contract.get("schema_version") == SCHEMA and contract.get("spec_sha256") == spec_hash
            and contract.get("predecessor_task") == task_id and contract.get("predecessor_task_head") == head
            and contract.get("registered_spec") == original
            and spec["financing_revision"]["source_spec"] == original, "SOURCE_IDENTITY")
    inputs = r.get("inputs")
    matrix = sibling("originals_matrix", "financing-evidence") if "originals_matrix" in r else None
    matrix_digest = r.get("originals_matrix", {}).get("sha256")

    def read_original(digest):
        return document("SOURCE_MATRIX_HASH", folder / f"source-matrix-{digest}.json", digest, 2 * MIB)

    def check_sources(financing):
        try:
            verify_source_set(inputs, contract["raw_source_bindings"], financing, matrix, matrix_digest, read_original)
        except RevisionError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
            raise RevisionError("SOURCE_BINDING") from None

    check_sources(spec["financing_revision"])
    reassessment = _reassessment(r)
    if reassessment and isinstance(r.get("current_reassessment"), dict) and "revised_spec" in r["current_reassessment"]:
        try:
            adjusted = sibling("revised_spec", "reassessment-spec", r["current_reassessment"])
            require(adjusted["symbol"] == symbol and adjusted["valuation_date"] == date_text
                    and adjusted["financing_revision"]["source_spec"] == original, "REASSESSMENT_SPEC")
        except (RevisionError, KeyError, TypeError):
            reassessment = dict(status="UNAVAILABLE", reason="REASSESSMENT_SPEC", scenario_rows={},
                                current_research_range_adopted=False)
        else:
            check_sources(adjusted["financing_revision"])
    total = 0
    for pin in inputs:
        require(isinstance(pin, dict) and set(pin) == {"path", "sha256"}, "SOURCE_BINDING")
        name = pin["path"]
        require(isinstance(name, str) and re.fullmatch(r"runtime/[\w./-]+\.(?:pdf|json)", name, re.I)
                and not any(part in ("", ".", "..") or part.startswith(".") for part in name.split("/")),
                "SOURCE_BINDING")
        path = root / name
        key = (name, pin["sha256"])
        if key not in cache:
            raw = verified_bytes(root / "runtime", path, pin["sha256"], min(32 * MIB, 128 * MIB - total),
                                 "SOURCE_BINDING")
            cache[key] = len(raw)
        total += cache[key]
        require(total <= 128 * MIB, "SOURCE_BINDING")
    return dict(status="VERIFIED", receipt_sha256=folder.name, input_descriptor_sha256=digest,
                completed_at=stamp.isoformat(), valuation_date=date_text, scenarios=_scenarios(val, day),
                current_reassessment=reassessment, financing_terms=_financing_terms(spec, matrix),
                provenance="DETERMINISTIC_RESEARCH_REVISION", formal_eligibility=False,
                current_comparable=False, action="no_order")


def read_revisions(root, task_id, symbol, head, original):
    base = directory(root, task_id)
    try:
        checked = _checked_path(root, base, "REVISION_DIRECTORY")
    except FileNotFoundError:
        return []
    entries = [base / entry.name for entry in islice(checked.iterdir(), 17)]
    require(len(entries) <= 16, "REVISION_LIMIT")
    results, cache = [], {}
    for folder in sorted(entries):
        if not SHA.fullmatch(folder.name):
            continue
        try:
            row = _project(root, folder, task_id, symbol, head, original, cache)
        except RevisionError as error:
            row = dict(status="UNAVAILABLE", reason=error.args[0], receipt_sha256=folder.name)
        except (KeyError, TypeError, ValueError, OSError, ArithmeticError, RecursionError, AttributeError):
            row = dict(status="UNAVAILABLE", reason="REVISION_FORMAT", receipt_sha256=folder.name)
        results.append(row)
    return sorted(results, key=lambda row: row.get("completed_at", ""), reverse=True)

"""Independent point-in-time conformance verification for historical research.

The legacy replay and admission objects already carry the policy vocabulary.
This module deliberately exists beside those frozen contracts: it re-reads the
subject JSON and a separate input manifest, recomputes local artifact hashes,
and checks temporal and coverage predicates instead of trusting caller flags.

The verifier is read-only.  ``PASS`` means that all required local predicates
were independently checked; it never authorizes a valuation, performance
claim, order, portfolio action, or production operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
from typing import Any, Mapping, Sequence


PIT_CONFORMANCE_SCHEMA = "pit-conformance-verifier-v2"
PIT_CONFORMANCE_INPUT_SCHEMA = "pit-conformance-input-v2"
ACTION_NO_ORDER = "no_order"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NOT_PROVEN = "NOT_PROVEN"

CN_TZ = timezone(timedelta(hours=8))
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

REPLAY_SCHEMA = "m3-historical-research-replay-v1"
ADMISSION_SCHEMA = "historical-validation-admission-v1"

RULE_CONTEMPORANEOUS = "CONTEMPORANEOUS_RULE"
RULE_RETROSPECTIVE = "RETROSPECTIVE_RESEARCH_EXTENSION"
RULE_STATUSES = frozenset({RULE_CONTEMPORANEOUS, RULE_RETROSPECTIVE})

PIT_VERIFIED = "VERIFIED"
PIT_CONSERVATIVE = "CONSERVATIVE"
PIT_UNSUPPORTED = "UNSUPPORTED"
PIT_NOT_PROVEN = "NOT_PROVEN"
PIT_NOT_APPLICABLE = "NOT_APPLICABLE"
PIT_STATUSES = frozenset(
    {
        PIT_VERIFIED,
        PIT_CONSERVATIVE,
        PIT_UNSUPPORTED,
        PIT_NOT_PROVEN,
        PIT_NOT_APPLICABLE,
    }
)

ADMISSION_DIMENSIONS = (
    "facts_pit",
    "assumptions_pit",
    "valuation_pit",
    "quote_pit",
    "corporate_actions_pit",
    "fees_pit",
    "portfolio_context",
    "benchmark_contract",
    "universe_pit",
)
EXECUTION_DIMENSION = "execution_contract"

_KINDS_BY_DIMENSION: dict[str, frozenset[str]] = {
    "facts_pit": frozenset(
        {
            "annual_filing",
            "financial_filing",
            "financial_facts",
            "financial_statement",
            "filing",
            "distribution",
        }
    ),
    "assumptions_pit": frozenset(
        {
            "assumptions",
            "model_assumptions",
            "valuation_assumptions",
            "versioned_file",
        }
    ),
    "valuation_pit": frozenset(
        {
            "model_output",
            "valuation",
            "valuation_model",
            "versioned_file",
        }
    ),
    "quote_pit": frozenset({"market_data", "price_file", "prices", "quote"}),
    "corporate_actions_pit": frozenset(
        {
            "corporate_action",
            "corporate_actions",
            "distribution",
        }
    ),
    "fees_pit": frozenset({"fee_schedule", "fees", "tax_policy"}),
    "portfolio_context": frozenset(
        {"portfolio", "portfolio_context", "private_portfolio"}
    ),
    "benchmark_contract": frozenset(
        {"benchmark", "benchmark_contract", "index_total_return"}
    ),
    "universe_pit": frozenset(
        {
            "security_master",
            "universe",
            "universe_coverage",
            "universe_snapshot",
        }
    ),
    EXECUTION_DIMENSION: frozenset({"execution_contract"}),
    "rule_registration": frozenset(
        {"archived_document", "publication", "source_commit", "versioned_file"}
    ),
}

_SOURCE_AUTHORITY_REQUIRED = True


class _InputError(ValueError):
    """An input is structurally invalid and cannot be trusted."""


class _MissingProof(ValueError):
    """A required proof artifact or field is absent."""


@dataclass(frozen=True)
class _Evidence:
    evidence_id: str
    kind: str
    path: str
    sha256: str
    availability_basis: str
    available_at: datetime
    source_authority: str
    dimensions: tuple[str, ...]
    raw: Mapping[str, Any]


@dataclass
class _Audit:
    checks: list[dict[str, Any]]
    blockers: list[str]

    def __init__(self) -> None:
        self.checks = []
        self.blockers = []

    def pass_check(self, check: str, detail: Any = None) -> None:
        item: dict[str, Any] = {"check": check, "status": STATUS_PASS}
        if detail is not None:
            item["detail"] = detail
        self.checks.append(item)

    def fail(self, check: str, detail: str) -> None:
        self.checks.append({"check": check, "status": STATUS_FAIL, "detail": detail})
        self.blockers.append(f"FAIL:{check}:{detail}")

    def not_proven(self, check: str, detail: str) -> None:
        self.checks.append(
            {"check": check, "status": STATUS_NOT_PROVEN, "detail": detail}
        )
        self.blockers.append(f"NOT_PROVEN:{check}:{detail}")

    @property
    def status(self) -> str:
        if any(item["status"] == STATUS_FAIL for item in self.checks):
            return STATUS_FAIL
        if any(item["status"] == STATUS_NOT_PROVEN for item in self.checks):
            return STATUS_NOT_PROVEN
        return STATUS_PASS


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _InputError(f"{field} is required")
    return value.strip()


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise _InputError(f"{field} must be a SHA-256 hex digest")
    return text


def _parse_datetime(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise _InputError(f"{field} must be an ISO-8601 timestamp") from error
    else:
        raise _InputError(f"{field} must be an ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _InputError(f"{field} must be timezone-aware")
    return parsed


def _parse_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        raise _InputError(f"{field} must be an ISO-8601 date, not a datetime")
    if not isinstance(value, str):
        raise _InputError(f"{field} must be an ISO-8601 date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise _InputError(f"{field} must be an ISO-8601 date") from error
    if parsed.isoformat() != value:
        raise _InputError(f"{field} must be an ISO-8601 date")
    return parsed


def _normalize_relative_path(value: object, field: str) -> str:
    text = _required_text(value, field).replace("\\", "/")
    if (
        PureWindowsPath(text).is_absolute()
        or Path(text).is_absolute()
        or ".." in Path(text).parts
    ):
        raise _InputError(f"{field} must be repository-relative and not escape root")
    return text


def _resolve_under_root(root: Path, relative: str, field: str) -> Path:
    resolved_root = root.resolve()
    target = (resolved_root / relative).resolve()
    if not target.is_relative_to(resolved_root):
        raise _InputError(f"{field} resolves outside the repository root")
    return target


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cutoff(day: date) -> datetime:
    return datetime.combine(day, time(15, 0), tzinfo=CN_TZ)


def _parse_point_in_time(value: object, field: str) -> datetime:
    if isinstance(value, str) and len(value) == 10:
        published = _parse_date(value, field)
        return datetime.combine(
            published + timedelta(days=1), time.min, tzinfo=CN_TZ
        )
    return _parse_datetime(value, field)


def _as_cn_timestamp(value: datetime) -> datetime:
    return value.astimezone(CN_TZ)


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise _MissingProof(f"{label} does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _InputError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise _InputError(f"{label} must be a JSON object: {path}")
    return payload


def _evidence_from_record(record: object, index: int) -> _Evidence:
    if not isinstance(record, Mapping):
        raise _InputError(f"evidence[{index}] must be a JSON object")
    evidence_id = _required_text(record.get("evidence_id"), f"evidence[{index}].evidence_id")
    kind = _required_text(record.get("kind"), f"evidence[{index}].kind")
    path = _normalize_relative_path(record.get("path"), f"evidence[{index}].path")
    sha256 = _sha256(record.get("sha256"), f"evidence[{index}].sha256")
    basis = _required_text(
        record.get("availability_basis"),
        f"evidence[{index}].availability_basis",
    )
    if basis not in {"timestamp", "date_only"}:
        raise _InputError(
            "evidence[{0}].availability_basis must be timestamp or date_only".format(index)
        )
    raw_available_at = record.get("available_at")
    if basis == "timestamp":
        available_at = _parse_datetime(
            raw_available_at, f"evidence[{index}].available_at"
        )
    else:
        published = _parse_date(
            raw_available_at, f"evidence[{index}].available_at"
        )
        available_at = datetime.combine(
            published + timedelta(days=1), time.min, tzinfo=CN_TZ
        )
    source_authority = _required_text(
        record.get("source_authority"),
        f"evidence[{index}].source_authority",
    )
    dimensions = record.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise _InputError(f"evidence[{index}].dimensions must be a non-empty list")
    normalized_dimensions = tuple(
        _required_text(item, f"evidence[{index}].dimensions[]") for item in dimensions
    )
    return _Evidence(
        evidence_id=evidence_id,
        kind=kind,
        path=path,
        sha256=sha256,
        availability_basis=basis,
        available_at=available_at,
        source_authority=source_authority,
        dimensions=normalized_dimensions,
        raw=dict(record),
    )


def _load_evidence_manifest(
    root: Path,
    manifest_path: Path,
    expected_policy_version: str,
) -> tuple[dict[str, Any], dict[str, _Evidence]]:
    manifest = _load_json_object(manifest_path, "PIT conformance manifest")
    if manifest.get("schema_version") != PIT_CONFORMANCE_INPUT_SCHEMA:
        raise _InputError("Unsupported PIT conformance input manifest schema")
    if manifest.get("action") != ACTION_NO_ORDER:
        raise _InputError("PIT conformance manifest must remain action=no_order")
    if manifest.get("policy_version") != expected_policy_version:
        raise _InputError("PIT conformance manifest policy_version does not match policy")
    records = manifest.get("evidence")
    if not isinstance(records, list):
        raise _InputError("PIT conformance manifest evidence must be a list")
    parsed: dict[str, _Evidence] = {}
    seen_hashes: set[tuple[str, str]] = set()
    for index, record in enumerate(records):
        item = _evidence_from_record(record, index)
        if item.evidence_id in parsed:
            raise _InputError(f"Duplicate evidence_id: {item.evidence_id}")
        key = (item.kind, item.sha256)
        if key in seen_hashes:
            raise _InputError(
                f"Duplicate evidence kind/hash pair: {item.kind}/{item.sha256}"
            )
        seen_hashes.add(key)
        local_path = _resolve_under_root(root, item.path, f"evidence[{index}].path")
        if not local_path.is_file():
            raise _InputError(f"Evidence file is missing: {item.path}")
        if _digest(local_path) != item.sha256:
            raise _InputError(f"Evidence hash mismatch: {item.path}")
        parsed[item.evidence_id] = item
    return manifest, parsed


def _reference_id(reference: Mapping[str, Any], field: str) -> str:
    value = reference.get("id", reference.get("evidence_id"))
    return _required_text(value, f"{field}.id")


def _reference_payload(reference: object, field: str) -> dict[str, Any]:
    if not isinstance(reference, Mapping):
        raise _InputError(f"{field} must be a JSON object")
    evidence_id = _reference_id(reference, field)
    kind = _required_text(reference.get("kind"), f"{field}.kind")
    path = _normalize_relative_path(reference.get("path"), f"{field}.path")
    sha256 = _sha256(reference.get("sha256"), f"{field}.sha256")
    available_at: datetime | None = None
    if reference.get("available_at") is not None:
        available_at = _parse_datetime(reference.get("available_at"), f"{field}.available_at")
    return {
        "evidence_id": evidence_id,
        "kind": kind,
        "path": path,
        "sha256": sha256,
        "available_at": available_at,
    }


def _check_reference(
    reference: object,
    *,
    field: str,
    dimension: str,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
    require_available_at: bool,
) -> tuple[dict[str, Any], _Evidence] | None:
    try:
        payload = _reference_payload(reference, field)
    except _InputError as error:
        audit.fail("subject_reference_valid", str(error))
        return None
    evidence = evidence_by_id.get(payload["evidence_id"])
    if evidence is None:
        audit.not_proven(
            "evidence_declared",
            f"{field} references {payload['evidence_id']} absent from manifest",
        )
        return None
    if evidence.kind != payload["kind"]:
        audit.fail(
            "evidence_kind_matches",
            f"{field} kind {payload['kind']} != manifest kind {evidence.kind}",
        )
    if evidence.path != payload["path"]:
        audit.fail(
            "evidence_path_matches",
            f"{field} path {payload['path']} != manifest path {evidence.path}",
        )
    if evidence.sha256 != payload["sha256"]:
        audit.fail("evidence_hash_matches", f"{field} sha256 differs from manifest")
    if dimension not in evidence.dimensions:
        audit.fail(
            "evidence_dimension_matches",
            f"{field} uses {payload['evidence_id']} outside declared dimensions",
        )
    declared_at = payload["available_at"]
    if declared_at is None and require_available_at:
        audit.not_proven(
            "evidence_availability_declared",
            f"{field} has no subject availability timestamp",
        )
    elif declared_at is not None and _as_cn_timestamp(declared_at) != evidence.available_at:
        audit.fail(
            "evidence_availability_matches",
            f"{field} availability conflicts with manifest for {payload['evidence_id']}",
        )
    return payload, evidence


def _check_exact_evidence_coverage(
    referenced_ids: set[str],
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> None:
    missing = referenced_ids - set(evidence_by_id)
    extra = set(evidence_by_id) - referenced_ids
    if missing:
        audit.not_proven(
            "evidence_coverage_complete",
            "missing manifest evidence: " + ", ".join(sorted(missing)),
        )
    if extra:
        audit.fail(
            "evidence_coverage_bijective",
            "manifest contains unreferenced evidence: " + ", ".join(sorted(extra)),
        )
    if not missing and not extra:
        audit.pass_check(
            "evidence_coverage_bijective",
            {"referenced": len(referenced_ids)},
        )


def _kind_matches(dimension: str, kind: str) -> bool:
    allowed = _KINDS_BY_DIMENSION.get(dimension)
    return bool(allowed and kind in allowed)


def _check_dimension_kind(
    dimension: str,
    evidence: _Evidence,
    audit: _Audit,
    field: str,
) -> None:
    if not _kind_matches(dimension, evidence.kind):
        audit.fail(
            "evidence_kind_for_dimension",
            f"{field} kind {evidence.kind} is not valid for {dimension}",
        )


def _parse_rule(replay: Mapping[str, Any], audit: _Audit) -> dict[str, Any]:
    rule = replay.get("rule")
    if not isinstance(rule, Mapping):
        audit.fail("replay_rule_present", "replay.rule is required")
        return {}
    result = {
        "rule_version": _required_text(rule.get("rule_version"), "rule.rule_version"),
        "registered_at": _parse_datetime(rule.get("registered_at"), "rule.registered_at"),
        "status": _required_text(
            rule.get("rule_registration_status"),
            "rule.rule_registration_status",
        ),
        "evidence": rule.get("registration_evidence", []),
    }
    if result["status"] not in RULE_STATUSES:
        audit.fail("rule_registration_status", f"unsupported rule status: {result['status']}")
    if not isinstance(result["evidence"], list):
        audit.fail("rule_registration_evidence", "registration_evidence must be a list")
        result["evidence"] = []
    return result


def _verify_no_order_boundaries(subject: Mapping[str, Any], audit: _Audit) -> None:
    if subject.get("action") != ACTION_NO_ORDER:
        audit.fail("no_order_action", "subject must remain action=no_order")
    for field in ("valuation_approved", "trade_approved", "positive_price_review_eligible"):
        value = subject.get(field)
        if value is not None and value is not False:
            audit.fail("no_approval_boundary", f"{field} must remain false")
    if subject.get("final_decision") == "BUY_REVIEW":
        audit.fail("no_positive_buy_review", "historical replay cannot claim BUY_REVIEW")
    for field in ("target_weight", "position_size", "order_quantity"):
        if subject.get(field) not in (None, 0):
            audit.fail("no_order_field", f"subject contains forbidden order field {field}")


def _verify_replay_facts(
    subject: Mapping[str, Any],
    *,
    cutoff: datetime,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> tuple[set[str], set[str], set[str], datetime] | None:
    referenced_ids: set[str] = set()
    future_ids: set[str] = set()
    filing_ids: set[str] = set()
    facts = subject.get("then_known_facts")
    if not isinstance(facts, Mapping):
        audit.fail("replay_facts_present", "then_known_facts is required")
        return None
    published_at = _parse_datetime(
        facts.get("published_at"), "then_known_facts.published_at"
    )
    source_checked = _check_reference(
        facts.get("source_ref"),
        field="then_known_facts.source_ref",
        dimension="facts_pit",
        evidence_by_id=evidence_by_id,
        audit=audit,
        require_available_at=True,
    )
    if source_checked is None:
        return None
    source_payload, source_evidence = source_checked
    referenced_ids.add(source_payload["evidence_id"])
    _check_dimension_kind("facts_pit", source_evidence, audit, "facts source")
    if published_at > cutoff:
        audit.fail(
            "facts_available_before_cutoff",
            f"facts published at {published_at.isoformat()} after cutoff {cutoff.isoformat()}",
        )
    if published_at > source_evidence.available_at:
        audit.fail(
            "facts_availability_consistent",
            "facts publication postdates the claimed source availability",
        )

    filings = subject.get("then_known_filings")
    if not isinstance(filings, list):
        audit.fail("replay_filings_present", "then_known_filings must be a list")
        filings = []
    for index, reference in enumerate(filings):
        checked = _check_reference(
            reference,
            field=f"then_known_filings[{index}]",
            dimension="facts_pit",
            evidence_by_id=evidence_by_id,
            audit=audit,
            require_available_at=True,
        )
        if checked is None:
            continue
        payload, evidence = checked
        _check_dimension_kind("facts_pit", evidence, audit, f"filing[{index}]")
        filing_ids.add(payload["evidence_id"])
        referenced_ids.add(payload["evidence_id"])
        if evidence.available_at > cutoff:
            future_ids.add(payload["evidence_id"])
    if source_payload["evidence_id"] not in filing_ids:
        audit.fail(
            "facts_source_in_then_known_filings",
            "facts source_ref is absent from then_known_filings",
        )
    return referenced_ids, future_ids, filing_ids, published_at


def _verify_replay_quote(
    subject: Mapping[str, Any],
    *,
    replay_date: date,
    cutoff: datetime,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> tuple[set[str], set[str], date] | None:
    referenced_ids: set[str] = set()
    future_ids: set[str] = set()
    quote = subject.get("then_known_quote")
    if not isinstance(quote, Mapping):
        audit.fail("replay_quote_present", "then_known_quote is required")
        return None
    quote_date = _parse_date(quote.get("quote_date"), "then_known_quote.quote_date")
    checked = _check_reference(
        quote.get("source_ref"),
        field="then_known_quote.source_ref",
        dimension="quote_pit",
        evidence_by_id=evidence_by_id,
        audit=audit,
        require_available_at=True,
    )
    if checked is None:
        return None
    payload, evidence = checked
    _check_dimension_kind("quote_pit", evidence, audit, "quote source")
    referenced_ids.add(payload["evidence_id"])
    if quote_date > replay_date:
        audit.fail(
            "quote_not_future",
            f"quote date {quote_date.isoformat()} postdates replay date {replay_date.isoformat()}",
        )
    if evidence.available_at > cutoff:
        future_ids.add(payload["evidence_id"])
    return referenced_ids, future_ids, quote_date


def _verify_replay_rule(
    rule: Mapping[str, Any],
    *,
    cutoff: datetime,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> tuple[set[str], set[str], str]:
    referenced_ids: set[str] = set()
    future_ids: set[str] = set()
    status = str(rule["status"])
    registered_at = rule["registered_at"]
    rule_ids: set[str] = set()
    for index, reference in enumerate(rule["evidence"]):
        checked = _check_reference(
            reference,
            field=f"rule.registration_evidence[{index}]",
            dimension="rule_registration",
            evidence_by_id=evidence_by_id,
            audit=audit,
            require_available_at=True,
        )
        if checked is None:
            continue
        payload, evidence = checked
        _check_dimension_kind(
            "rule_registration", evidence, audit, f"rule evidence[{index}]"
        )
        rule_ids.add(payload["evidence_id"])
        referenced_ids.add(payload["evidence_id"])
        if evidence.available_at > registered_at:
            audit.fail(
                "rule_evidence_precedes_registration",
                f"rule evidence {payload['evidence_id']} postdates registered_at",
            )
        if evidence.available_at > cutoff:
            future_ids.add(payload["evidence_id"])

    if status == RULE_CONTEMPORANEOUS:
        if registered_at > cutoff:
            audit.fail(
                "contemporaneous_rule_before_cutoff",
                "contemporaneous rule registration postdates the replay cutoff",
            )
        if not rule_ids:
            audit.not_proven(
                "contemporaneous_rule_evidence",
                "contemporaneous rule has no independently checkable registration evidence",
            )
        else:
            audit.pass_check("contemporaneous_rule_proof", sorted(rule_ids))
    elif status == RULE_RETROSPECTIVE:
        audit.not_proven(
            "strict_contemporaneous_rule_pit",
            "rule is a retrospective research extension, not a contemporaneous rule",
        )
    return referenced_ids, future_ids, status


def _verify_replay(
    subject: Mapping[str, Any],
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> None:
    _verify_no_order_boundaries(subject, audit)
    replay_date = _parse_date(subject.get("replay_date"), "replay_date")
    cutoff = _cutoff(replay_date)
    facts_result = _verify_replay_facts(
        subject, cutoff=cutoff, evidence_by_id=evidence_by_id, audit=audit
    )
    quote_result = _verify_replay_quote(
        subject,
        replay_date=replay_date,
        cutoff=cutoff,
        evidence_by_id=evidence_by_id,
        audit=audit,
    )
    rule = _parse_rule(subject, audit)
    if not facts_result or not quote_result or not rule:
        return
    referenced_ids, fact_future, _filing_ids, published_at = facts_result
    quote_ids, quote_future, quote_date = quote_result
    referenced_ids |= quote_ids
    rule_ids, rule_future, rule_status = _verify_replay_rule(
        rule, cutoff=cutoff, evidence_by_id=evidence_by_id, audit=audit
    )
    referenced_ids |= rule_ids
    future_ids = fact_future | quote_future | rule_future

    future_facts_used = subject.get("future_facts_used")
    future_rule_used = subject.get("future_rule_version_used")
    if not isinstance(future_facts_used, bool):
        audit.fail("future_facts_flag_type", "future_facts_used must be boolean")
    if not isinstance(future_rule_used, bool):
        audit.fail("future_rule_flag_type", "future_rule_version_used must be boolean")
    derived_future = bool(future_ids) or published_at > cutoff or quote_date > replay_date
    if derived_future and future_facts_used is False:
        audit.fail(
            "future_facts_flag_consistent",
            "stored future_facts_used=false conflicts with derived future evidence use",
        )
    if future_facts_used is True:
        audit.fail("future_facts_used_forbidden", "historical replay cannot use future facts")
    if rule_status == RULE_CONTEMPORANEOUS and future_rule_used is not False:
        audit.fail(
            "contemporaneous_rule_flag",
            "contemporaneous rule cannot use a future rule version",
        )
    if rule_status == RULE_RETROSPECTIVE and future_rule_used is not True:
        audit.fail(
            "retrospective_rule_flag",
            "retrospective rule must mark future_rule_version_used=true",
        )

    _check_exact_evidence_coverage(referenced_ids, evidence_by_id, audit)
    if audit.status == STATUS_PASS and rule_status == RULE_CONTEMPORANEOUS:
        audit.pass_check("strict_pit_replay_admissible", True)
    elif audit.status == STATUS_PASS:
        audit.not_proven("strict_pit_replay_admissible", "strict PIT was not proven")


def _check_manifest_evidence_id(
    evidence_id: object,
    *,
    field: str,
    dimension: str,
    cutoff: datetime,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> _Evidence | None:
    try:
        resolved_id = _required_text(evidence_id, field)
    except _InputError as error:
        if evidence_id is None or (isinstance(evidence_id, str) and not evidence_id.strip()):
            audit.not_proven("proof_evidence_id_present", str(error))
        else:
            audit.fail("proof_evidence_id_valid", str(error))
        return None
    evidence = evidence_by_id.get(resolved_id)
    if evidence is None:
        audit.not_proven(
            "proof_evidence_declared",
            f"{field} references {resolved_id} absent from manifest",
        )
        return None
    if dimension not in evidence.dimensions:
        audit.fail(
            "proof_evidence_dimension",
            f"{field} uses {resolved_id} outside declared dimensions",
        )
    _check_dimension_kind(dimension, evidence, audit, field)
    if evidence.available_at > cutoff:
        audit.fail(
            "proof_evidence_not_future",
            f"{field} is available after the decision cutoff",
        )
    return evidence


def _assess_admission_dimension(
    admission: Mapping[str, Any],
    *,
    field: str,
    dimension: str,
    cutoff: datetime,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> set[str]:
    item = admission.get(field)
    if not isinstance(item, Mapping):
        audit.fail(f"{field}_present", f"{field} must be an object")
        return set()
    status = _required_text(item.get("status"), f"{field}.status")
    if status not in PIT_STATUSES:
        audit.fail(f"{field}_status", f"unsupported status: {status}")
        return set()
    refs = item.get("evidence_refs", [])
    if not isinstance(refs, list):
        audit.fail(f"{field}_evidence_refs", f"{field}.evidence_refs must be a list")
        refs = []
    identifiers: set[str] = set()
    for index, reference in enumerate(refs):
        checked = _check_reference(
            reference,
            field=f"{field}.evidence_refs[{index}]",
            dimension=dimension,
            evidence_by_id=evidence_by_id,
            audit=audit,
            require_available_at=False,
        )
        if checked is None:
            continue
        payload, evidence = checked
        _check_dimension_kind(dimension, evidence, audit, f"{field}.evidence_refs[{index}]")
        identifiers.add(payload["evidence_id"])
        if evidence.available_at > cutoff:
            audit.fail(
                "dimension_evidence_not_future",
                f"{field} references evidence available after the first decision cutoff",
            )
    if status in {PIT_VERIFIED, PIT_CONSERVATIVE} and not identifiers:
        audit.not_proven(
            f"{field}_proof",
            f"{field} is proven without an independently checkable evidence reference",
        )
    if status != PIT_VERIFIED:
        audit.not_proven(
            f"{field}_strict_verification",
            f"{field} status is {status}; strict replay requires VERIFIED",
        )
    else:
        audit.pass_check(f"{field}_verified", sorted(identifiers))
    return identifiers


def _verify_execution_contract_semantics(
    admission: Mapping[str, Any], audit: _Audit
) -> None:
    contract = admission.get(EXECUTION_DIMENSION)
    if not isinstance(contract, Mapping):
        return
    if contract.get("signal_to_fill") != "next_session_open":
        audit.fail(
            "execution_signal_to_fill",
            "execution contract must fill at next_session_open",
        )
    if contract.get("settlement") != "T+1":
        audit.fail("execution_settlement", "execution contract must use T+1")
    if contract.get("board_lot") != 100:
        audit.fail("execution_board_lot", "A-share execution contract must use board_lot=100")
    for field in (
        "cash_policy",
        "suspension_policy",
        "price_limit_policy",
        "liquidity_policy",
        "corporate_action_policy",
        "fee_policy",
    ):
        if not isinstance(contract.get(field), str) or not contract.get(field).strip():
            audit.fail("execution_policy_present", f"execution contract requires {field}")


def _verify_benchmark_proof(
    manifest: Mapping[str, Any],
    *,
    cutoff: datetime,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> set[str]:
    benchmark = manifest.get("benchmark")
    if not isinstance(benchmark, Mapping):
        audit.not_proven(
            "benchmark_proof_present",
            "benchmark proof requires an immutable id, version, as_of, and evidence",
        )
        return set()
    benchmark_id = _required_text(benchmark.get("benchmark_id"), "benchmark.benchmark_id")
    version = _required_text(benchmark.get("version"), "benchmark.version")
    as_of = _parse_point_in_time(benchmark.get("as_of"), "benchmark.as_of")
    if as_of > cutoff:
        audit.fail("benchmark_version_not_future", "benchmark as_of postdates the cutoff")
    methodology_id = benchmark.get("methodology_evidence_id")
    evidence_ids: list[object] = [methodology_id]
    for optional in ("return_series_evidence_id", "corporate_action_evidence_id"):
        if benchmark.get(optional) is not None:
            evidence_ids.append(benchmark[optional])
    identifiers: set[str] = set()
    for index, evidence_id in enumerate(evidence_ids):
        evidence = _check_manifest_evidence_id(
            evidence_id,
            field=f"benchmark.evidence[{index}]",
            dimension="benchmark_contract",
            cutoff=cutoff,
            evidence_by_id=evidence_by_id,
            audit=audit,
        )
        if evidence is None:
            continue
        identifiers.add(evidence.evidence_id)
        declared_version = evidence.raw.get("version")
        if declared_version is not None and str(declared_version) != version:
            audit.fail(
                "benchmark_version_matches",
                f"benchmark evidence version {declared_version} != {version}",
            )
    if not identifiers:
        audit.not_proven("benchmark_proof_evidence", "benchmark has no checked evidence")
    else:
        audit.pass_check(
            "benchmark_proof_checked",
            {"benchmark_id": benchmark_id, "version": version, "as_of": as_of.isoformat()},
        )
    return identifiers


def _verify_universe_proof(
    manifest: Mapping[str, Any],
    *,
    cutoff: datetime,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> set[str]:
    universe = manifest.get("universe")
    if not isinstance(universe, Mapping):
        audit.not_proven(
            "universe_proof_present",
            "universe proof requires snapshot, selection rule, delisting, suspension, and survivorship evidence",
        )
        return set()
    as_of = _parse_point_in_time(universe.get("as_of"), "universe.as_of")
    if as_of > cutoff:
        audit.fail("universe_not_future", "universe snapshot postdates the cutoff")
    selection_rule_version = _required_text(
        universe.get("selection_rule_version"), "universe.selection_rule_version"
    )
    required_fields = (
        "snapshot_evidence_id",
        "selection_rule_evidence_id",
        "delisted_coverage_evidence_id",
        "suspended_coverage_evidence_id",
        "survivorship_control_evidence_id",
    )
    identifiers: set[str] = set()
    for field in required_fields:
        evidence = _check_manifest_evidence_id(
            universe.get(field),
            field=f"universe.{field}",
            dimension="universe_pit",
            cutoff=cutoff,
            evidence_by_id=evidence_by_id,
            audit=audit,
        )
        if evidence is None:
            continue
        identifiers.add(evidence.evidence_id)
        declared_version = evidence.raw.get("version")
        if (
            field == "selection_rule_evidence_id"
            and declared_version is not None
            and str(declared_version) != selection_rule_version
        ):
            audit.fail(
                "universe_selection_rule_version",
                "selection-rule evidence version does not match the proof",
            )
    if len(identifiers) != len(required_fields):
        audit.not_proven(
            "universe_proof_distinct_evidence",
            "universe proof requires distinct evidence for each required control",
        )
    else:
        audit.pass_check(
            "universe_proof_checked",
            {"selection_rule_version": selection_rule_version, "as_of": as_of.isoformat()},
        )
    return identifiers


def _verify_model_sessions(
    admission: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    window_start: date,
    window_end: date,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> set[str]:
    claimed = admission.get("approved_value_model_sessions")
    if type(claimed) is not int or claimed < 0:
        audit.fail(
            "model_session_count_valid",
            "approved_value_model_sessions must be a non-negative integer",
        )
        return set()
    sessions = manifest.get("model_sessions")
    if not isinstance(sessions, list):
        audit.not_proven(
            "model_session_proofs_present",
            "approved model sessions require one independently checkable proof per session",
        )
        return set()
    if claimed == 0:
        if sessions:
            audit.fail(
                "model_session_count_matches",
                "zero approved sessions cannot carry model-session proofs",
            )
        else:
            audit.not_proven(
                "model_session_count_positive",
                "strict replay requires at least one approved value-model session",
            )
        return set()
    if len(sessions) != claimed:
        audit.fail(
            "model_session_count_matches",
            f"claimed {claimed} sessions but manifest contains {len(sessions)} proofs",
        )
    identifiers: set[str] = set()
    session_ids: set[str] = set()
    session_proofs: set[tuple[str, str, str]] = set()
    fields = (
        ("model_evidence_id", "valuation_pit"),
        ("valuation_evidence_id", "valuation_pit"),
        ("assumptions_evidence_id", "assumptions_pit"),
        ("quote_evidence_id", "quote_pit"),
    )
    for index, session in enumerate(sessions):
        if not isinstance(session, Mapping):
            audit.fail("model_session_object", f"model_sessions[{index}] must be an object")
            continue
        session_id = _required_text(
            session.get("session_id"), f"model_sessions[{index}].session_id"
        )
        if session_id in session_ids:
            audit.fail("model_session_unique", f"duplicate session_id: {session_id}")
        session_ids.add(session_id)
        proof_key = (
            str(session.get("decision_at")),
            str(session.get("model_evidence_id")),
            str(session.get("valuation_evidence_id")),
        )
        if proof_key in session_proofs:
            audit.fail("model_session_proof_unique", f"duplicate proof for {session_id}")
        session_proofs.add(proof_key)
        decision_at = _parse_datetime(
            session.get("decision_at"), f"model_sessions[{index}].decision_at"
        )
        if decision_at.date() < window_start or decision_at.date() > window_end:
            audit.fail(
                "model_session_in_window",
                f"session {session_id} is outside the admission window",
            )
        if decision_at > _cutoff(window_end):
            audit.fail(
                "model_session_before_close",
                f"session {session_id} is after the end-of-session cutoff",
            )
        proof_by_dimension: dict[str, set[str]] = {}
        for field, dimension in fields:
            evidence = _check_manifest_evidence_id(
                session.get(field),
                field=f"model_sessions[{index}].{field}",
                dimension=dimension,
                cutoff=decision_at,
                evidence_by_id=evidence_by_id,
                audit=audit,
            )
            if evidence is not None:
                identifiers.add(evidence.evidence_id)
                proof_by_dimension.setdefault(dimension, set()).add(evidence.evidence_id)
        dimension_names = list(proof_by_dimension)
        for left_index, left in enumerate(dimension_names):
            for right in dimension_names[left_index + 1 :]:
                overlap = proof_by_dimension[left] & proof_by_dimension[right]
                if overlap:
                    audit.fail(
                        "model_session_evidence_disjoint",
                        f"session {session_id} reuses {sorted(overlap)} across dimensions",
                    )
        if session.get("approved") is not True:
            audit.fail(
                "model_session_approved",
                f"session {session_id} does not explicitly approve its model",
            )
    if claimed > 0 and len(session_ids) == claimed and claimed == len(sessions):
        audit.pass_check("model_session_proofs_checked", claimed)
    return identifiers


def _verify_admission_rule(
    admission: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    cutoff: datetime,
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> set[str]:
    rule_version = _required_text(admission.get("rule_version"), "rule_version")
    status = _required_text(
        admission.get("rule_registration_status"), "rule_registration_status"
    )
    if status not in RULE_STATUSES:
        audit.fail("admission_rule_status", f"unsupported rule status: {status}")
        return set()
    raw_refs = admission.get("rule_evidence_refs", [])
    if not isinstance(raw_refs, list) or not raw_refs:
        audit.not_proven("admission_rule_evidence_refs", "rule_evidence_refs are required")
        raw_refs = []
    referenced_ids: set[str] = set()
    for index, evidence_id in enumerate(raw_refs):
        resolved = _required_text(
            evidence_id, f"rule_evidence_refs[{index}]"
        )
        evidence = _check_manifest_evidence_id(
            resolved,
            field=f"rule_evidence_refs[{index}]",
            dimension="rule_registration",
            cutoff=cutoff,
            evidence_by_id=evidence_by_id,
            audit=audit,
        )
        if evidence is not None:
            referenced_ids.add(evidence.evidence_id)
    proof = manifest.get("rule_registration")
    if status == RULE_RETROSPECTIVE:
        if isinstance(proof, Mapping):
            proof_version = proof.get("rule_version")
            if proof_version is not None and str(proof_version) != rule_version:
                audit.fail(
                    "rule_version_matches",
                    "rule registration proof version differs from admission",
                )
        audit.not_proven(
            "strict_contemporaneous_rule_pit",
            "admission uses a retrospective rule, not a contemporaneous rule",
        )
        return referenced_ids
    if not isinstance(proof, Mapping):
        audit.not_proven(
            "rule_registration_proof_present",
            "contemporaneous rule requires registration bytes and timestamp",
        )
        return referenced_ids
    proof_version = _required_text(
        proof.get("rule_version"), "rule_registration.rule_version"
    )
    proof_status = _required_text(
        proof.get("status"), "rule_registration.status"
    )
    if proof_version != rule_version or proof_status != status:
        audit.fail(
            "rule_registration_identity",
            "rule registration proof does not match the admission rule",
        )
    registered_at = _parse_datetime(
        proof.get("registered_at"), "rule_registration.registered_at"
    )
    if registered_at > cutoff:
        audit.fail(
            "rule_registration_before_cutoff",
            "rule registration postdates the first decision cutoff",
        )
    proof_ids = proof.get("evidence_ids")
    if not isinstance(proof_ids, list) or not proof_ids:
        audit.not_proven(
            "rule_registration_evidence",
            "rule registration proof has no evidence_ids",
        )
        return referenced_ids
    proof_id_set = {
        _required_text(item, "rule_registration.evidence_ids[]") for item in proof_ids
    }
    if proof_id_set != referenced_ids:
        audit.fail(
            "rule_registration_evidence_matches",
            "rule registration evidence does not match admission refs",
        )
    for index, evidence_id in enumerate(sorted(proof_id_set)):
        evidence = _check_manifest_evidence_id(
            evidence_id,
            field=f"rule_registration.evidence_ids[{index}]",
            dimension="rule_registration",
            cutoff=registered_at,
            evidence_by_id=evidence_by_id,
            audit=audit,
        )
        if evidence is not None:
            referenced_ids.add(evidence.evidence_id)
    if referenced_ids:
        audit.pass_check("rule_registration_proof_checked", sorted(referenced_ids))
    return referenced_ids


def _check_subject_evidence_index(
    admission: Mapping[str, Any],
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> set[str]:
    refs = admission.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        audit.fail("admission_evidence_refs_present", "admission evidence_refs are required")
        return set()
    identifiers: set[str] = set()
    for index, reference in enumerate(refs):
        try:
            payload = _reference_payload(reference, f"evidence_refs[{index}]")
        except _InputError as error:
            audit.fail("admission_evidence_ref_valid", str(error))
            continue
        evidence = evidence_by_id.get(payload["evidence_id"])
        if evidence is None:
            audit.not_proven(
                "admission_evidence_declared",
                f"evidence_refs[{index}] is absent from the manifest",
            )
            continue
        if (
            evidence.kind != payload["kind"]
            or evidence.path != payload["path"]
            or evidence.sha256 != payload["sha256"]
        ):
            audit.fail(
                "admission_evidence_matches_manifest",
                f"evidence_refs[{index}] does not match the manifest identity",
            )
        identifiers.add(evidence.evidence_id)
    return identifiers


def _verify_admission(
    subject: Mapping[str, Any],
    manifest: Mapping[str, Any],
    evidence_by_id: Mapping[str, _Evidence],
    audit: _Audit,
) -> None:
    _verify_no_order_boundaries(subject, audit)
    window = subject.get("window")
    if not isinstance(window, Mapping):
        audit.fail("admission_window_present", "window must be an object")
        return
    window_start = _parse_date(window.get("start"), "window.start")
    window_end = _parse_date(window.get("end"), "window.end")
    if window_start > window_end:
        audit.fail("admission_window_order", "window.start must not be after window.end")
    cutoff = _cutoff(window_start)
    cutoff_policy = _required_text(
        subject.get("information_cutoff_policy"), "information_cutoff_policy"
    )
    if "available_at <= decision_at" not in cutoff_policy:
        audit.fail(
            "admission_cutoff_policy",
            "admission must declare available_at <= decision_at",
        )

    dimension_ids: dict[str, set[str]] = {}
    for dimension in ADMISSION_DIMENSIONS:
        dimension_ids[dimension] = _assess_admission_dimension(
            subject,
            field=dimension,
            dimension=dimension,
            cutoff=cutoff,
            evidence_by_id=evidence_by_id,
            audit=audit,
        )
    dimension_ids[EXECUTION_DIMENSION] = _assess_admission_dimension(
        subject,
        field=EXECUTION_DIMENSION,
        dimension=EXECUTION_DIMENSION,
        cutoff=cutoff,
        evidence_by_id=evidence_by_id,
        audit=audit,
    )
    _verify_execution_contract_semantics(subject, audit)

    seen: dict[str, str] = {}
    for dimension, identifiers in dimension_ids.items():
        for evidence_id in identifiers:
            if evidence_id in seen:
                audit.fail(
                    "dimension_evidence_disjoint",
                    f"{evidence_id} is reused by {seen[evidence_id]} and {dimension}",
                )
            else:
                seen[evidence_id] = dimension

    benchmark_ids = _verify_benchmark_proof(
        manifest, cutoff=cutoff, evidence_by_id=evidence_by_id, audit=audit
    )
    universe_ids = _verify_universe_proof(
        manifest, cutoff=cutoff, evidence_by_id=evidence_by_id, audit=audit
    )
    model_ids = _verify_model_sessions(
        subject,
        manifest,
        window_start=window_start,
        window_end=window_end,
        evidence_by_id=evidence_by_id,
        audit=audit,
    )
    rule_ids = _verify_admission_rule(
        subject, manifest, cutoff=cutoff, evidence_by_id=evidence_by_id, audit=audit
    )
    declared_ids = _check_subject_evidence_index(subject, evidence_by_id, audit)

    referenced_ids = set().union(*dimension_ids.values())
    referenced_ids |= benchmark_ids | universe_ids | model_ids | rule_ids
    _check_exact_evidence_coverage(referenced_ids, evidence_by_id, audit)
    if declared_ids != referenced_ids:
        audit.fail(
            "admission_evidence_index_bijective",
            "admission evidence_refs do not match all checked evidence references",
        )

    survivorship = _required_text(
        subject.get("survivorship_status"), "survivorship_status"
    )
    if survivorship != "CONTROLLED":
        audit.not_proven(
            "survivorship_controlled",
            "strict replay requires controlled survivorship proof",
        )
    classification = _required_text(
        subject.get("classification"), "classification"
    )
    admission_status = _required_text(
        subject.get("admission_status"), "admission_status"
    )
    if classification != "STRICT_CONTEMPORANEOUS_REPLAY":
        audit.not_proven(
            "strict_admission_classification",
            f"admission classification is {classification}",
        )
    if admission_status != "ADMITTED_FOR_STRICT_REPLAY":
        audit.not_proven(
            "strict_admission_status",
            f"admission status is {admission_status}",
        )
    if audit.status == STATUS_PASS:
        audit.pass_check("strict_pit_admission_admissible", True)


def _policy_version(root: Path) -> str:
    path = root / "config" / "pit-conformance-policy-v2.json"
    if not path.is_file():
        raise _MissingProof(f"PIT conformance policy is missing: {path}")
    payload = _load_json_object(path, "PIT conformance policy")
    if payload.get("schema_version") != "pit-conformance-policy-v2":
        raise _InputError("Unsupported PIT conformance policy schema")
    if payload.get("action") != ACTION_NO_ORDER:
        raise _InputError("PIT conformance policy must remain action=no_order")
    return _required_text(payload.get("policy_version"), "policy_version")


def _result(
    *,
    status: str,
    policy_version: str,
    verified_at: datetime,
    subject_path: Path,
    manifest_path: Path | None,
    audit: _Audit,
    subject_schema: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PIT_CONFORMANCE_SCHEMA,
        "policy_version": policy_version,
        "verified_at": verified_at.astimezone(timezone.utc).isoformat(),
        "status": status,
        "action": ACTION_NO_ORDER,
        "subject": {
            "path": str(subject_path),
            "schema_version": subject_schema,
        },
        "manifest": {"path": str(manifest_path) if manifest_path else None},
        "checks": audit.checks,
        "blockers": audit.blockers,
        "strict_pit_admissible": status == STATUS_PASS,
        "performance_claim_allowed": False,
        "valuation_approved": False,
        "trade_approved": False,
        "production_authorized": False,
    }


def _resolve_path(root: Path, path: Path, label: str) -> Path:
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise _InputError(f"{label} resolves outside the repository root: {resolved}")
    if not resolved.is_file():
        raise _MissingProof(f"{label} does not exist: {resolved}")
    return resolved


def verify_pit_conformance_v2(
    root: Path,
    *,
    subject_path: Path,
    manifest_path: Path | None = None,
    verified_at: datetime | None = None,
) -> dict[str, Any]:
    """Verify one replay/admission subject against an independent evidence manifest."""
    root = root.resolve()
    verified = verified_at or datetime.now(timezone.utc)
    if verified.tzinfo is None or verified.utcoffset() is None:
        raise ValueError("verified_at must be timezone-aware")
    try:
        policy_version = _policy_version(root)
    except _MissingProof as error:
        audit = _Audit()
        audit.not_proven("policy_present", str(error))
        return _result(
            status=audit.status,
            policy_version="unavailable",
            verified_at=verified,
            subject_path=subject_path,
            manifest_path=manifest_path,
            audit=audit,
        )
    except (OSError, _InputError) as error:
        audit = _Audit()
        audit.fail("policy_valid", str(error))
        return _result(
            status=audit.status,
            policy_version="unavailable",
            verified_at=verified,
            subject_path=subject_path,
            manifest_path=manifest_path,
            audit=audit,
        )

    try:
        resolved_subject = _resolve_path(root, subject_path, "PIT subject")
    except _MissingProof as error:
        audit = _Audit()
        audit.not_proven("subject_present", str(error))
        return _result(
            status=audit.status,
            policy_version=policy_version,
            verified_at=verified,
            subject_path=subject_path,
            manifest_path=manifest_path,
            audit=audit,
        )
    except _InputError as error:
        audit = _Audit()
        audit.fail("subject_path", str(error))
        return _result(
            status=audit.status,
            policy_version=policy_version,
            verified_at=verified,
            subject_path=subject_path,
            manifest_path=manifest_path,
            audit=audit,
        )
    try:
        subject = _load_json_object(resolved_subject, "PIT subject")
    except _InputError as error:
        audit = _Audit()
        audit.fail("subject_valid", str(error))
        return _result(
            status=audit.status,
            policy_version=policy_version,
            verified_at=verified,
            subject_path=resolved_subject,
            manifest_path=manifest_path,
            audit=audit,
        )
    subject_schema = subject.get("schema_version")
    if not isinstance(subject_schema, str):
        audit = _Audit()
        audit.fail("subject_schema", "subject.schema_version is required")
        return _result(
            status=audit.status,
            policy_version=policy_version,
            verified_at=verified,
            subject_path=resolved_subject,
            manifest_path=manifest_path,
            audit=audit,
        )
    if manifest_path is None:
        audit = _Audit()
        audit.not_proven("manifest_present", "independent PIT input manifest is required")
        return _result(
            status=audit.status,
            policy_version=policy_version,
            verified_at=verified,
            subject_path=resolved_subject,
            manifest_path=None,
            subject_schema=subject_schema,
            audit=audit,
        )

    try:
        resolved_manifest = _resolve_path(root, manifest_path, "PIT manifest")
        manifest, evidence_by_id = _load_evidence_manifest(
            root, resolved_manifest, policy_version
        )
    except _MissingProof as error:
        audit = _Audit()
        audit.not_proven("manifest_present", str(error))
        return _result(
            status=audit.status,
            policy_version=policy_version,
            verified_at=verified,
            subject_path=resolved_subject,
            manifest_path=manifest_path,
            subject_schema=subject_schema,
            audit=audit,
        )
    except (_InputError, OSError) as error:
        audit = _Audit()
        audit.fail("manifest_valid", str(error))
        return _result(
            status=audit.status,
            policy_version=policy_version,
            verified_at=verified,
            subject_path=resolved_subject,
            manifest_path=manifest_path,
            subject_schema=subject_schema,
            audit=audit,
        )

    audit = _Audit()
    try:
        if subject_schema == REPLAY_SCHEMA:
            if subject.get("namespace") != "HISTORICAL_RESEARCH_REPLAY":
                audit.fail("replay_namespace", "historical replay namespace is required")
            if subject.get("action") != ACTION_NO_ORDER:
                audit.fail("replay_action", "historical replay must remain action=no_order")
            _verify_replay(subject, evidence_by_id, audit)
        elif subject_schema == ADMISSION_SCHEMA:
            _verify_admission(subject, manifest, evidence_by_id, audit)
        else:
            audit.fail("subject_schema_supported", f"unsupported subject schema: {subject_schema}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        audit.fail("verification_completed", f"verification failed: {error}")

    return _result(
        status=audit.status,
        policy_version=policy_version,
        verified_at=verified,
        subject_path=resolved_subject,
        manifest_path=resolved_manifest,
        subject_schema=subject_schema,
        audit=audit,
    )

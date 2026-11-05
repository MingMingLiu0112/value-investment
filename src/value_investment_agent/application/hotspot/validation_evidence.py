"""Build immutable W7 evidence without promoting activity into a trade signal."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from ...domain.hotspot.daily_selection import rank_daily_candidates
from ...infrastructure.hotspot.current_price_case import load_current_price_case
from .daily_selection import verify_daily_selection
from .price_action_case import project_current_price_action_plan
from .quantitative_validation import ProtocolBinding, compute_quantitative_validation


SCHEMA_VERSION = "hotspot-structure-validation-v2"
MANIFEST_SCHEMA = "hotspot-structure-validation-manifest-v2"
ACTION = "no_order"
STRATEGY_VALIDATION = "NOT_PROVEN"
OUTPUT_FILENAMES = ("validation.json", "report.md", "manifest.json")
REGISTERED_RULE_VERSIONS = frozenset(
    {
        "hotspot-dated-sector-liquidity-ranking-v1",
        "hotspot-dated-sector-liquidity-ranking-v2",
        "hotspot-dated-sector-liquidity-ranking-v3",
    }
)


def _hash_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def _recomputed_digest(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _hash_bytes(raw)


def _inside(root: Path, value: Path | str, parent: Path, label: str) -> Path:
    raw = Path(value)
    path = (raw if raw.is_absolute() else root / raw).resolve()
    if not path.is_relative_to(parent.resolve()):
        raise ValueError(f"{label} must remain under {parent}")
    return path


def _read_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not readable JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value, raw


def load_current_case_bindings(root: Path, pointer_path: Path) -> dict[str, Any]:
    """Read explicit immutable case bindings from the current product pointer."""
    root = root.resolve()
    pointer_file = _inside(root, pointer_path, root / "config", "price-condition pointer")
    pointer, pointer_raw = _read_object(pointer_file, "price-condition pointer")
    if pointer.get("action") != ACTION or not isinstance(pointer.get("items"), list):
        raise ValueError("price-condition pointer is not a no_order registry")
    watch = pointer.get("watch_source_binding")
    if not isinstance(watch, dict):
        raise ValueError("price-condition pointer has no selection report binding")
    watch_path = watch.get("path")
    watch_sha256 = watch.get("sha256")
    if not isinstance(watch_path, str) or not isinstance(watch_sha256, str):
        raise ValueError("price-condition selection report binding is incomplete")
    bindings: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in pointer["items"]:
        if not isinstance(item, dict):
            raise ValueError("price-condition item must be an object")
        symbol = str(item.get("symbol") or "")
        path = item.get("case_path")
        digest = item.get("case_sha256")
        if len(symbol) != 6 or not symbol.isdigit() or symbol in seen:
            raise ValueError("price-condition symbol is invalid or duplicated")
        if not isinstance(path, str) or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("price-condition case binding is incomplete")
        seen.add(symbol)
        bindings.append({"symbol": symbol, "path": path, "sha256": digest})
    return {
        "pointer_path": pointer_file.relative_to(root).as_posix(),
        "pointer_sha256": _hash_bytes(pointer_raw),
        "watch_source_path": watch_path,
        "watch_source_sha256": watch_sha256,
        "items": bindings,
    }


def _case_evidence(root: Path, binding: Mapping[str, Any], *, role: str) -> dict[str, Any]:
    runtime = (root / "runtime").resolve()
    path = _inside(root, str(binding.get("path") or ""), runtime, "price case")
    case, raw = _read_object(path, "price case")
    digest = _hash_bytes(raw)
    expected = binding.get("sha256")
    if expected is not None and digest != expected:
        raise ValueError("price case hash mismatch")
    symbol = str(case.get("symbol") or "")
    if not symbol or symbol != str(binding.get("symbol") or symbol):
        raise ValueError("price case identity mismatch")
    source_times = [
        datetime.fromisoformat(source["fetched_at"])
        for source in case.get("source_bindings", {}).values()
    ]
    if not source_times or any(item.utcoffset() is None for item in source_times):
        raise ValueError("price case must have timezone-aware source times")
    now = max(source_times).astimezone(timezone.utc) + timedelta(seconds=1)
    loaded = load_current_price_case(
        root=root,
        symbol=symbol,
        case_path=path,
        expected_sha256=digest,
        now=now,
    )
    plan = project_current_price_action_plan(loaded)
    quality = plan["opportunity_quality"]
    if plan.get("action") != ACTION or plan.get("formal_eligibility") is not False:
        raise ValueError("price case cannot remain research-only")
    return {
        "role": role,
        "symbol": symbol,
        "case_path": loaded["case_path"],
        "case_sha256": digest,
        "market_trade_date": loaded["market_trade_date"],
        "current_reference_price": loaded["current_reference_price"],
        "verified_available_at": loaded["verified_available_at"],
        "signal_state": plan["signal_state"],
        "trend_state": plan["trend_state"],
        "period_structure": plan["period_structure"],
        "structure_tier": quality["structure_tier"],
        "structure_reasons": quality["structure_reasons"],
        "expires_after_session": quality["expires_after_session"],
        "formal_eligibility": plan["formal_eligibility"],
        "portfolio_eligibility": plan.get("portfolio_eligibility"),
        "action": plan["action"],
        "blockers": plan["blockers"],
    }


def _incomplete_live_attempt(
    root: Path,
    directory: Path | None,
    reason: str | None,
) -> dict[str, Any] | None:
    if directory is None:
        return None
    runtime = (root / "runtime").resolve()
    path = _inside(root, directory, runtime, "live-attempt directory")
    if not path.is_dir():
        raise ValueError("live-attempt directory does not exist")
    report_path = path / "report.json"
    if report_path.exists():
        raise ValueError("live-attempt directory already contains a report; use it as evidence")
    files: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        resolved = _inside(root, item, runtime, "live-attempt file")
        raw = resolved.read_bytes()
        files.append(
            {
                "path": resolved.relative_to(root).as_posix(),
                "sha256": _hash_bytes(raw),
                "size_bytes": len(raw),
            }
        )
    content_sha256 = _hash_bytes(
        json.dumps(
            {"path": path.relative_to(root).as_posix(), "files": files},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    return {
        "path": path.relative_to(root).as_posix(),
        "status": "INCOMPLETE_NO_REPORT",
        "reason": reason or "ACQUISITION_NOT_COMPLETED",
        "file_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "content_sha256": content_sha256,
        "files": files,
        "used_as_evidence": False,
    }


def _report_available_at(report: Mapping[str, Any]) -> datetime:
    try:
        report_available = datetime.fromisoformat(report["available_at"])
        source_available = max(
            datetime.fromisoformat(binding["available_at"])
            for binding in report["source_bindings"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("daily selection report has invalid availability bindings") from error
    if report_available.utcoffset() is None or source_available.utcoffset() is None:
        raise ValueError("daily selection availability timestamps require timezones")
    if report_available.astimezone(timezone.utc) < source_available.astimezone(timezone.utc):
        raise ValueError("daily selection report availability precedes its source evidence")
    return report_available


def build_hotspot_structure_validation(
    *,
    root: Path,
    selection_report_path: Path,
    selection_report_sha256: str,
    current_price_conditions_path: Path,
    historical_case_paths: Iterable[Path] = (),
    incomplete_live_directory: Path | None = None,
    incomplete_live_reason: str | None = None,
    evaluated_at: datetime | None = None,
    limit: int = 10,
    pool_limit: int = 10,
) -> dict[str, Any]:
    """Replay a frozen daily report and bind only complete multi-period cases."""
    root = root.resolve()
    runtime = (root / "runtime").resolve()
    report_file = _inside(root, selection_report_path, runtime, "daily selection report")
    report, raw = _read_object(report_file, "daily selection report")
    digest = _hash_bytes(raw)
    if digest != selection_report_sha256:
        raise ValueError("daily selection report hash mismatch")
    if report.get("schema_version") != "hotspot-daily-selection-v1" or report.get("action") != ACTION:
        raise ValueError("daily selection report is not a no_order evidence report")
    verify_daily_selection(root, report)
    report_available_at = _report_available_at(report)
    source_rule_version = report["ranking"].get("rule_version")
    if source_rule_version not in REGISTERED_RULE_VERSIONS:
        raise ValueError("unexpected source daily candidate rule version")
    ranking = rank_daily_candidates(
        report["rows"],
        trade_date=report["trade_date"],
        limit=limit,
        candidate_pool_limit=pool_limit,
    )
    if ranking.get("rule_version") != "hotspot-dated-sector-liquidity-ranking-v3":
        raise ValueError("unexpected daily candidate rule version")
    pool = ranking["candidate_pool"]
    if len(pool) != pool_limit:
        raise ValueError("candidate pool was unexpectedly truncated")

    case_registry = load_current_case_bindings(root, current_price_conditions_path)
    report_relative_path = report_file.relative_to(root).as_posix()
    if (case_registry["watch_source_path"] != report_relative_path
            or case_registry["watch_source_sha256"] != digest):
        raise ValueError("price-condition pointer is bound to a different selection report")
    current_bindings = case_registry["items"]
    cases = [
        _case_evidence(root, binding, role="CURRENT_PRICE_CONDITION")
        for binding in current_bindings
    ]
    historical_hashes: set[str] = set()
    for path in historical_case_paths:
        historical = _inside(root, path, runtime, "historical negative case")
        raw_case, _ = _read_object(historical, "historical negative case")
        evidence = _case_evidence(
            root,
            {
                "symbol": raw_case.get("symbol"),
                "path": historical.relative_to(root).as_posix(),
                "sha256": None,
            },
            role="HISTORICAL_NEGATIVE_CASE",
        )
        if evidence["structure_tier"] != "CONFLICT_OR_REJECTED":
            raise ValueError("historical negative case is not a conflict or rejected structure")
        if evidence["case_sha256"] not in historical_hashes:
            historical_hashes.add(evidence["case_sha256"])
            cases.append(evidence)
    if not any(item["role"] == "HISTORICAL_NEGATIVE_CASE" for item in cases):
        raise ValueError("at least one historical negative case is required")

    cases_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for item in cases:
        cases_by_symbol.setdefault(item["symbol"], []).append(item)
    pool_status = []
    for candidate in pool:
        symbol = candidate["symbol"]
        matching = [
            item
            for item in cases_by_symbol.get(symbol, [])
            if item["market_trade_date"] == report["trade_date"]
        ]
        if matching:
            evidence = matching[0]
            pool_status.append(
                {
                    "candidate_pool_rank": candidate["candidate_pool_rank"],
                    "symbol": symbol,
                    "company_name": candidate["company_name"],
                    "industry": candidate["industry"],
                    "assessment_status": "BOUND_ASSESSED",
                    "case_path": evidence["case_path"],
                    "case_sha256": evidence["case_sha256"],
                    "signal_state": evidence["signal_state"],
                    "structure_tier": evidence["structure_tier"],
                    "structure_reasons": evidence["structure_reasons"],
                    "expires_after_session": evidence["expires_after_session"],
                    "formal_eligibility": False,
                    "action": ACTION,
                }
            )
        else:
            pool_status.append(
                {
                    "candidate_pool_rank": candidate["candidate_pool_rank"],
                    "symbol": symbol,
                    "company_name": candidate["company_name"],
                    "industry": candidate["industry"],
                    "assessment_status": "UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE",
                    "reason": "NO_COMPLETE_DAILY_60M_15M_CASE_FOR_SELECTION_DATE",
                    "structure_tier": "UNASSESSED",
                    "formal_eligibility": False,
                    "action": ACTION,
                }
            )

    expiry_values = {
        item["expires_after_session"]
        for item in cases
        if item["market_trade_date"] == report["trade_date"]
    }
    if len(expiry_values) > 1:
        raise ValueError("selection-date cases disagree on expiry session")
    expiry = next(iter(expiry_values), None)
    evaluated_at = evaluated_at or datetime.now(timezone.utc)
    if evaluated_at.utcoffset() is None:
        raise ValueError("evaluation time must include a timezone")
    evaluated_at = evaluated_at.astimezone(timezone.utc)
    if evaluated_at < report_available_at.astimezone(timezone.utc):
        raise ValueError("evaluation time precedes the selection report availability")
    if any(
        evaluated_at < datetime.fromisoformat(item["verified_available_at"]).astimezone(timezone.utc)
        for item in cases
    ):
        raise ValueError("evaluation time precedes a bound case availability")
    conflict_count = sum(item["structure_tier"] == "CONFLICT_OR_REJECTED" for item in cases)
    qualified_count = sum(
        item["structure_tier"] == "STRUCTURE_QUALIFIED_OBSERVATION" for item in cases
    )
    pool_count = len(pool)
    unassessed_count = sum(
        item["assessment_status"] != "BOUND_ASSESSED" for item in pool_status
    )
    rule_extension_status = (
        "RETROSPECTIVE_RESEARCH_EXTENSION"
        if source_rule_version != ranking["rule_version"]
        else "SOURCE_REPORTED_RULE_REPLAY"
    )
    future_rule_version_used = source_rule_version != ranking["rule_version"]
    rule_limitation = (
        f"Source report used {source_rule_version}; the pool was rebuilt with later "
        f"{ranking['rule_version']}. Strict contemporaneous rule PIT remains NOT_PROVEN."
        if future_rule_version_used
        else "The source report names the replayed rule, but repository-version timing alone "
        "does not prove strict contemporaneous rule PIT."
    )
    report_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "action": ACTION,
        "trade_intent": "NO_TRADE",
        "strategy": "HOTSPOT_SATELLITE",
        "selection_trade_date": report["trade_date"],
        "selection_available_at": report["available_at"],
        "evaluated_at": evaluated_at.isoformat(),
        "rule_version": ranking["rule_version"],
        "source_report_rule_version": source_rule_version,
        "replayed_rule_version": ranking["rule_version"],
        "rule_extension_status": rule_extension_status,
        "future_rule_version_used": future_rule_version_used,
        "rule_pit_status": "NOT_PROVEN",
        "candidate_pool_rule": ranking["candidate_pool_rule"],
        "pool_expiry_session": expiry,
        "market": ranking["market"],
        "candidate_pool": [
            {
                key: item.get(key)
                for key in (
                    "candidate_pool_rank",
                    "symbol",
                    "company_name",
                    "industry",
                    "close",
                    "change_percent",
                    "amount_cny",
                    "industry_relative_strength_percent",
                )
            }
            for item in pool
        ],
        "pool_structure_status": pool_status,
        "case_structure_evidence": cases,
        "summary": {
            "pool_count": pool_count,
            "pool_industry_count": len({item["industry"] for item in pool}),
            "pool_assessed_count": sum(
                item["assessment_status"] == "BOUND_ASSESSED" for item in pool_status
            ),
            "pool_unassessed_count": unassessed_count,
            "case_count": len(cases),
            "conflict_or_rejected_count": conflict_count,
            "structure_qualified_observation_count": qualified_count,
        },
        "strategy_validation": STRATEGY_VALIDATION,
        "prospective_oos_admitted": False,
        "historical_classification_used": True,
        "elapsed_real_shadow_sessions": 0,
        "classification_pit": "NOT_PROVEN",
        "limitations": [
            rule_limitation,
            "Sina classification has no effective-date proof; historical industry PIT remains NOT_PROVEN.",
            f"The {pool_count}-symbol activity pool is not an entry list; "
            f"{unassessed_count} symbol{'s' if unassessed_count != 1 else ''} lack bound "
            "multi-period structure for the selection date.",
            "Minute-bar structure is single-provider evidence, not an admitted trade signal.",
            "No cost-adjusted walk-forward, untouched OOS, or natural-time shadow result is claimed.",
            "Negative cases are preserved; W7 strategy validity remains NOT_PROVEN.",
        ],
        "incomplete_live_attempt": _incomplete_live_attempt(
            root,
            incomplete_live_directory,
            incomplete_live_reason,
        ),
        "source_files": {
            "selection_report": {
                "path": report_file.relative_to(root).as_posix(),
                "sha256": digest,
            },
            "current_price_conditions": {
                "path": case_registry["pointer_path"],
                "sha256": case_registry["pointer_sha256"],
            },
            "cases": {
                item["role"] + ":" + item["symbol"] + ":" + item["case_sha256"]: {
                    "path": item["case_path"],
                    "sha256": item["case_sha256"],
                }
                for item in cases
            },
        },
        "formal_eligibility": False,
        "portfolio_eligibility": None,
    }
    report_payload["evidence_sha256"] = _recomputed_digest(
        report_payload, "evidence_sha256"
    )
    return report_payload


def build_hotspot_quantitative_validation(*, root: Path, protocol_binding: dict | ProtocolBinding,
                                        now: datetime) -> dict[str, Any]:
    """Compute bound execution metrics or replay a legacy observation protocol."""
    from .event_replay import build_replay

    if isinstance(protocol_binding, ProtocolBinding):
        protocol_binding = dict(path=protocol_binding.path, sha256=protocol_binding.sha256)

    if (not isinstance(protocol_binding, dict)
            or not isinstance(protocol_binding.get("path"), str)
            or not protocol_binding["path"]
            or not isinstance(protocol_binding.get("sha256"), str)
            or len(protocol_binding["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in protocol_binding["sha256"])):
        raise ValueError("Quantitative validation requires a hash-bound protocol")
    if now.utcoffset() is None:
        raise ValueError("Quantitative protocol requires a timezone-aware clock")
    root = Path(root).resolve()
    name = protocol_binding["path"]
    if Path(name).is_absolute():
        raise ValueError("Quantitative protocol path must be repository-relative")
    path = _inside(root, name, root, "quantitative protocol")
    protocol, raw = _read_object(path, "quantitative protocol")
    if _hash_bytes(raw) != protocol_binding["sha256"]:
        raise ValueError("Quantitative protocol hash mismatch")
    from .retained_source_replay import MANIFEST_SCHEMA, build_retained_descriptive_validation

    if protocol.get("schema_version") == MANIFEST_SCHEMA:
        result = build_retained_descriptive_validation(root=root,
            manifest_binding=protocol_binding, now=now)
        result["evidence_sha256"] = _recomputed_digest(result, "evidence_sha256")
        return result
    if protocol.get("schema_version") == "hotspot-execution-protocol-v1":
        result = compute_quantitative_validation(root=root,
            binding=ProtocolBinding(**protocol_binding), protocol=protocol, now=now)
        result["evidence_sha256"] = _recomputed_digest(result, "evidence_sha256")
        return result
    # Validate the complete existing protocol and every bound original before
    # exposing observations; the replay engine enforces registration and rules.
    replay = build_replay(root=root, spec_path=Path(name),
                          expected_sha256=protocol_binding["sha256"], now=now)
    result = dict(schema_version="hotspot-quantitative-validation-v1",
        protocol_binding=dict(protocol_binding), evaluated_at=now.isoformat(),
        status="PARTIAL", strategy_validation="NOT_PROVEN",
        metrics_scope="SIGNAL_PRICE_PATH_ONLY", replay=replay,
        execution_metrics=dict(status="UNASSESSABLE", trade_count=None,
            win_rate=None, payoff_ratio=None, net_return_distribution=None,
            maximum_drawdown=None, cost_sensitivity=None,
            t_plus_one_feasibility="UNKNOWN"),
        remaining_requirements=["Source-bound fills, rejections and unfilled orders",
            "Dated fees, slippage, liquidity, suspension and price limits",
            "T+1 inventory and execution feasibility",
            "Contemporaneous universe, classification and input availability",
            "Predeclared untouched OOS execution sample"],
        formal_eligibility=False, performance_claim_allowed=False, action=ACTION)
    result["evidence_sha256"] = _recomputed_digest(result, "evidence_sha256")
    return result


def build_hotspot_review_handoff(*, root: Path, evaluated_at: datetime,
                                quantitative_protocol_binding: dict | None = None,
                                **validation_inputs: Any) -> dict[str, Any]:
    """Rebuild retained validation and prepare an unsigned independent review.

    This deliberately cannot approve a gate, sign a release or write a current
    pointer. Retrospective structure evidence does not establish strategy edge.
    """
    from ...domain.hotspot.independent_admission import GATES
    from .independent_admission import _contains_test_namespace

    if evaluated_at.utcoffset() is None:
        raise ValueError("Review handoff requires a timezone-aware cutoff")
    report = build_hotspot_structure_validation(
        root=root, evaluated_at=evaluated_at, **validation_inputs)
    _validate_report(report)
    if report["evidence_sha256"] != _recomputed_digest(report, "evidence_sha256"):
        raise ValueError("Review handoff validation digest mismatch")
    bindings = report["source_files"]
    sources = [bindings["selection_report"], bindings["current_price_conditions"],
               *bindings["cases"].values()]
    for binding in sources:
        path = _inside(root.resolve(), binding["path"], root.resolve(), "review source")
        document, raw = _read_object(path, "review source")
        if _hash_bytes(raw) != binding["sha256"]:
            raise ValueError("Review handoff source hash mismatch")
        if _contains_test_namespace(document):
            raise ValueError("TEST_ONLY evidence cannot enter ACTUAL review handoff")
    requirements = [
        dict(gap="STRICT_PIT", status="NOT_PROVEN",
             evidence_required=["contemporaneous frozen rule and input availability",
                                "effective-dated industry and survivorship universe",
                                "replay admission through historical_validation contracts"]),
        dict(gap="COST_AND_EXECUTION", status="NOT_RUN",
             evidence_required=["source-bound fills and rejected/unfilled orders",
                                "fees, slippage and cost sensitivity",
                                "limit up/down, suspension, liquidity, T+1 and single-trade risk"]),
        dict(gap="OOS_AND_STABILITY", status="NOT_RUN",
             evidence_required=["predeclared disjoint train/test windows and frozen thresholds",
                                "walk-forward with untouched OOS and no threshold retuning",
                                "trade count, win rate, payoff ratio and return distribution",
                                "maximum drawdown, market regimes, sector concentration",
                                "sample representativeness and statistical limitations"]),
    ]
    result = dict(schema_version="hotspot-independent-review-handoff-v1",
        namespace="ACTUAL", strategy="HOTSPOT_SATELLITE", action=ACTION,
        evaluated_at=evaluated_at.isoformat(), data_trade_date=report["selection_trade_date"],
        status="PENDING_INDEPENDENT_REVIEW", strategy_validation=report["strategy_validation"],
        formal_release_status="NOT_REQUESTED", formal_eligibility=False,
        risk_review_eligible=False, personal_risk_status="NOT_EVALUATED",
        validation_evidence=report, source_bindings=sources,
        validation_requirements=requirements,
        review_requirements=[dict(gate=gate, status="PENDING_REVIEW",
            required_context=["security identity", "matching frozen strategy rule",
                              "source hash and availability", "expiry and invalidation"],
            evidence_binding_required=True) for gate in GATES],
        authorization_requirements=dict(status="MISSING",
            verifier="application.hotspot.independent_admission:load_independent_admission",
            required=["independent authorized reviewer", "pinned scoped trust root",
                      "reviewer-signed source-bound gate assessments and release",
                      "ACTUAL namespace and current validity interval"],
            reviewer_id=None, signature=None),
        reopen_when="Attach missing validation evidence, then obtain independent lawful review; recheck current data before release.")
    if quantitative_protocol_binding is not None:
        quantitative = build_hotspot_quantitative_validation(root=root,
            protocol_binding=quantitative_protocol_binding, now=evaluated_at)
        if quantitative.get("namespace") != "ACTUAL":
            raise ValueError("ACTUAL review requires ACTUAL quantitative evidence")
        result["quantitative_validation"] = quantitative
        result["source_bindings"].extend([quantitative["protocol_binding"],
                                         *quantitative["source_bindings"]])
    result["evidence_sha256"] = _recomputed_digest(result, "evidence_sha256")
    return result


def render_validation_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# W7 Hotspot Structure Validation",
        "",
        f"- Action: {report['action']}",
        f"- Trade intent: {report['trade_intent']}",
        f"- Selection date: {report['selection_trade_date']}",
        f"- Rule: {report['rule_version']}",
        f"- Source report rule: {report['source_report_rule_version']}",
        f"- Rule extension: {report['rule_extension_status']}",
        f"- Rule PIT: {report['rule_pit_status']}",
        f"- Strategy validation: {report['strategy_validation']}",
        f"- Pool: {summary['pool_count']} symbols / {summary['pool_industry_count']} industries",
        f"- Bound structure assessments: {summary['pool_assessed_count']}",
        f"- Unassessed pool members: {summary['pool_unassessed_count']}",
        f"- Conflict or rejected cases (all bound, supplemental and historical): {summary['conflict_or_rejected_count']}",
        f"- Expiry session: {report['pool_expiry_session'] or 'UNAVAILABLE'}",
        "",
        "## Candidate pool",
        "",
        "| Rank | Symbol | Industry | Structure status |",
        "| ---: | --- | --- | --- |",
    ]
    for item in report["pool_structure_status"]:
        lines.append(
            f"| {item['candidate_pool_rank']} | {item['symbol']} | {item['industry']} | "
            f"{item['assessment_status']} / {item['structure_tier']} |"
        )
    lines.extend(
        [
            "",
            "## Preserved cases",
            "",
            "| Role | Symbol | Date | Signal | Structure | Expiry |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report["case_structure_evidence"]:
        lines.append(
            f"| {item['role']} | {item['symbol']} | {item['market_trade_date']} | "
            f"{item['signal_state']} | {item['structure_tier']} | "
            f"{item['expires_after_session']} |"
        )
    lines.extend(
        [
            "",
            "This artifact is research-only. Activity ranking is not a signal, the candidate pool is not an entry list, and no result establishes strategy profitability.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_report(report: Mapping[str, Any]) -> None:
    if report.get("schema_version") != SCHEMA_VERSION or report.get("action") != ACTION:
        raise ValueError("validation report is not a W7 no_order report")
    if report.get("trade_intent") != "NO_TRADE":
        raise ValueError("validation report cannot carry trade intent")
    if report.get("strategy_validation") != STRATEGY_VALIDATION:
        raise ValueError("validation report cannot upgrade strategy validation")
    if report.get("rule_pit_status") != "NOT_PROVEN":
        raise ValueError("validation report cannot upgrade rule PIT")
    source_rule_version = report.get("source_report_rule_version")
    replayed_rule_version = report.get("replayed_rule_version")
    if (
        source_rule_version not in REGISTERED_RULE_VERSIONS
        or replayed_rule_version not in REGISTERED_RULE_VERSIONS
        or report.get("rule_version") != replayed_rule_version
    ):
        raise ValueError("validation report rule versions are inconsistent")
    future_rule_version_used = source_rule_version != replayed_rule_version
    expected_rule_extension = (
        "RETROSPECTIVE_RESEARCH_EXTENSION"
        if future_rule_version_used
        else "SOURCE_REPORTED_RULE_REPLAY"
    )
    if report.get("rule_extension_status") != expected_rule_extension:
        raise ValueError("validation report rule-extension status is inconsistent")
    if report.get("future_rule_version_used") is not future_rule_version_used:
        raise ValueError("validation report future-rule flag is inconsistent")
    if report.get("classification_pit") != "NOT_PROVEN":
        raise ValueError("validation report cannot upgrade classification PIT")
    if report.get("prospective_oos_admitted") is not False:
        raise ValueError("validation report cannot admit prospective OOS")
    if report.get("formal_eligibility") is not False:
        raise ValueError("validation report cannot grant formal eligibility")
    if report.get("portfolio_eligibility") is not None:
        raise ValueError("validation report cannot grant portfolio eligibility")
    pool = report.get("candidate_pool")
    statuses = report.get("pool_structure_status")
    cases = report.get("case_structure_evidence")
    summary = report.get("summary")
    if not isinstance(pool, list) or not isinstance(statuses, list) or not isinstance(cases, list):
        raise ValueError("validation report is missing evidence lists")
    if not isinstance(summary, dict):
        raise ValueError("validation report is missing its summary")
    pool_symbols = [item.get("symbol") for item in pool if isinstance(item, dict)]
    if len(pool_symbols) != len(pool) or len(set(pool_symbols)) != len(pool):
        raise ValueError("validation candidate pool is malformed or duplicated")
    pool_by_symbol = {item["symbol"]: item for item in pool}
    if [item.get("symbol") for item in statuses] != pool_symbols:
        raise ValueError("validation pool status does not match the candidate pool")
    allowed_roles = {"CURRENT_PRICE_CONDITION", "HISTORICAL_NEGATIVE_CASE"}
    allowed_tiers = {"STRUCTURE_QUALIFIED_OBSERVATION", "ACTIVE_ONLY", "CONFLICT_OR_REJECTED"}
    cases_by_binding: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("validation case evidence must be an object")
        if item.get("role") not in allowed_roles:
            raise ValueError("validation case has an unknown role")
        if (
            item.get("action") != ACTION
            or item.get("formal_eligibility") is not False
            or item.get("portfolio_eligibility") is not None
        ):
            raise ValueError("nested validation case cannot grant eligibility")
        if item.get("structure_tier") not in allowed_tiers:
            raise ValueError("validation case has an unknown structure tier")
        case_path = item.get("case_path")
        case_sha256 = item.get("case_sha256")
        symbol = item.get("symbol")
        trade_date = item.get("market_trade_date")
        if not all(isinstance(value, str) and value for value in (
            case_path, case_sha256, symbol, trade_date
        )):
            raise ValueError("validation case binding is incomplete")
        key = (symbol, trade_date, case_path)
        if key in cases_by_binding:
            raise ValueError("validation case binding is duplicated")
        try:
            if Decimal(str(item.get("current_reference_price"))) <= 0:
                raise ValueError("validation case close is invalid")
        except (InvalidOperation, TypeError):
            raise ValueError("validation case close is invalid") from None
        cases_by_binding[key] = item
    bound_statuses: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in statuses:
        if not isinstance(item, dict):
            raise ValueError("validation pool status must be an object")
        if item.get("action") != ACTION or item.get("formal_eligibility") is not False:
            raise ValueError("nested pool status cannot grant formal eligibility")
        status = item.get("assessment_status")
        if status == "UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE":
            if any(key in item for key in ("case_path", "case_sha256")):
                raise ValueError("unassessed pool member cannot carry a case binding")
            if item.get("structure_tier") != "UNASSESSED":
                raise ValueError("unassessed pool member has an invalid structure tier")
        elif status == "BOUND_ASSESSED":
            case_path = item.get("case_path")
            case_sha256 = item.get("case_sha256")
            key = (item.get("symbol"), report.get("selection_trade_date"), case_path)
            case = cases_by_binding.get(key)
            if case is None or case.get("case_sha256") != case_sha256:
                raise ValueError("bound pool member has no matching case evidence")
            try:
                pool_close = Decimal(str(pool_by_symbol[item.get("symbol")].get("close")))
                case_close = Decimal(str(case.get("current_reference_price")))
                if pool_close != case_close:
                    raise ValueError("pool close does not match bound case close")
                if "close" in item and Decimal(str(item.get("close"))) != pool_close:
                    raise ValueError("pool close does not match bound case close")
            except (InvalidOperation, TypeError):
                raise ValueError("pool close does not match bound case close") from None
            bound_statuses.append((item, case))
        else:
            raise ValueError("validation pool status has an unknown assessment status")
    if len(bound_statuses) != len({item[0].get("case_path") for item in bound_statuses}):
        raise ValueError("bound pool case is reused")
    attempt = report.get("incomplete_live_attempt")
    if attempt is not None and (
        not isinstance(attempt, dict)
        or attempt.get("status") != "INCOMPLETE_NO_REPORT"
        or attempt.get("used_as_evidence") is not False
        or not isinstance(attempt.get("files"), list)
    ):
        raise ValueError("incomplete live attempt cannot be used as evidence")
    assessed = sum(item.get("assessment_status") == "BOUND_ASSESSED" for item in statuses)
    expected = {
        "pool_count": len(pool),
        "pool_industry_count": len({item.get("industry") for item in pool}),
        "pool_assessed_count": assessed,
        "pool_unassessed_count": len(pool) - assessed,
        "case_count": len(cases),
        "conflict_or_rejected_count": sum(
            item.get("structure_tier") == "CONFLICT_OR_REJECTED" for item in cases
        ),
        "structure_qualified_observation_count": sum(
            item.get("structure_tier") == "STRUCTURE_QUALIFIED_OBSERVATION" for item in cases
        ),
    }
    if summary != expected:
        raise ValueError("validation summary does not match its evidence")


def write_hotspot_structure_validation(
    report: Mapping[str, Any],
    *,
    root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    payload = dict(report)
    _validate_report(payload)
    digest = _recomputed_digest(payload, "evidence_sha256")
    if payload.get("evidence_sha256") != digest:
        raise ValueError("validation evidence digest is stale")
    root = root.resolve()
    target = _inside(root, output_dir, (root / "artifacts").resolve(), "validation output")
    if target.exists():
        raise FileExistsError(f"refusing to overwrite: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        staging_targets = {name: staging / name for name in OUTPUT_FILENAMES}
        validation_text = _json_text(payload)
        report_text = render_validation_markdown(payload)
        with staging_targets["validation.json"].open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(validation_text)
        with staging_targets["report.md"].open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(report_text)
        outputs = {
            name: {
                "path": (target / name).relative_to(root).as_posix(),
                "sha256": _hash_bytes(staging_targets[name].read_bytes()),
            }
            for name in ("validation.json", "report.md")
        }
        manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "action": ACTION,
            "trade_intent": "NO_TRADE",
            "strategy_validation": STRATEGY_VALIDATION,
            "rule_extension_status": payload["rule_extension_status"],
            "future_rule_version_used": payload["future_rule_version_used"],
            "rule_pit_status": payload["rule_pit_status"],
            "evidence_sha256": digest,
            "source_files": payload["source_files"],
            "retained_non_evidence": payload.get("incomplete_live_attempt"),
            "outputs": outputs,
            "formal_eligibility": False,
        }
        with staging_targets["manifest.json"].open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(_json_text(manifest))
        if target.exists():
            raise FileExistsError(f"refusing to overwrite: {target}")
        staging.replace(target)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


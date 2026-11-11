"""SSE observations to existing research queues; no investment admission."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .value_research_queue import _canonical_hash, _load_bound
from .value_evidence_enrichment_v1 import DERIVED_VERSIONS, consume_retained_enrichment
from ..discovery import sse_main_screening
from ...domain.discovery.value_candidate_selection import observation_conditions, rank_research_candidates
from ...financial_quality import GENERAL_FIELDS, _accepted
from ...infrastructure.screening.evidence_screen_v3 import evaluate_financial_quality, selected_period
from ...m2_discovery_engine import _point_available_at

SCHEMA_VERSION = "sse-value-research-priority-v1"


def _screening_decision_register(rows, *, evaluation_at, source_available_at):
    """Persist every screened issuer's explainable queue decision.

    The research queues intentionally contain candidates only. This compact,
    source-bound register keeps excluded and data-gap decisions in the same
    dated artifact without changing four-channel policy or queue membership.
    """
    register = []
    for row in sorted(rows, key=lambda item: item["symbol"]):
        status = row["status"]
        if status not in {"CANDIDATE", "EXCLUDED", "UNASSESSABLE"}:
            raise ValueError("invalid SSE screening outcome status")
        channels, data_gaps, exclusions = [], [], []
        for evaluation in row.get("channel_evaluations", []):
            channel = evaluation.get("channel")
            channel_status = evaluation.get("status")
            reason = evaluation.get("reason")
            if not isinstance(channel, str) or not isinstance(channel_status, str):
                raise ValueError("invalid SSE channel evaluation")
            channels.append(dict(channel=channel, status=channel_status, reason=reason))
            if channel_status in {"DATA_GAP", "UNSUPPORTED"} and isinstance(reason, str):
                data_gaps.append(reason)
            if channel_status in {"EXCLUDED", "BUDGET_EXCLUDED"} and isinstance(reason, str):
                exclusions.append(reason)
        gaps = [gap for gap in row.get("gaps", []) if isinstance(gap, str)]
        if status == "CANDIDATE":
            decision = "INCLUDED_CANDIDATE"
            reasons = [row.get("reason")] if isinstance(row.get("reason"), str) else []
        elif status == "UNASSESSABLE":
            decision, reasons = "DATA_GAP", [*data_gaps, *gaps]
        else:
            decision, reasons = "EXCLUDED", [*exclusions, *gaps]
        register.append(dict(
            symbol=row["symbol"], company_name=row.get("company_name") or row.get("name"),
            screening_status=status, queue_decision=decision,
            reasons=list(dict.fromkeys(reason for reason in reasons if reason)),
            channels=channels, data_gaps=list(dict.fromkeys(data_gaps)),
            excluded_reasons=list(dict.fromkeys(exclusions)),
            observation_date=row.get("updated_at"),
            evaluation_at=evaluation_at.isoformat(),
            source_available_at=source_available_at.isoformat(),
        ))
    return register


def _time(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone-aware time required")
    return result


def _inside(root, path):
    path = Path(path)
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root / "runtime"):
        raise ValueError("research inputs must remain inside runtime")
    return resolved


def _previous(root, path, digest, now):
    if (path is None) != (digest is None):
        raise ValueError("previous queue path/hash must be paired")
    if path is None:
        return {}, None
    previous = _load_bound(_inside(root, path), digest)
    body = {k: v for k, v in previous.items() if k != "content_sha256"}
    if (previous.get("schema_version") != SCHEMA_VERSION
            or previous.get("content_sha256") != _canonical_hash(body)
            or previous.get("action") != "no_order"
            or previous.get("admission") != "RESEARCH_QUEUE_ONLY"):
        raise ValueError("invalid previous research queue")
    prior_time = _time(previous["evaluation_at"])
    if prior_time >= now or _time(previous["as_of"]) != prior_time:
        raise ValueError("previous evaluation_at must strictly precede now")
    if _time(previous["source_available_at"]) > prior_time:
        raise ValueError("previous source time exceeds evaluation")
    members = {}
    for key in ("deep_research_priority", "evidence_enrichment_work_queue", "tracking_history"):
        if not isinstance(previous.get(key), list):
            raise ValueError("previous queue lists required")
        for row in previous[key]:
            symbol = row["symbol"]
            if type(row.get("tracking_selected")) is not bool:
                raise ValueError("invalid duplicate previous member")
            if row.get("first_seen_at") != row["first_seen"]:
                raise ValueError("previous first_seen aliases disagree")
            if (_time(row["timing"]["evaluation_at"]) > prior_time or
                    _time(row["timing"]["source_available_at"]) > prior_time):
                raise ValueError("previous member time exceeds evaluation")
            if _time(row["first_seen"]) > prior_time:
                raise ValueError("invalid previous first_seen")
            if symbol in members and (key != "tracking_history" or
                    members[symbol]["first_seen"] != row["first_seen"]):
                raise ValueError("inconsistent duplicate previous member")
            if symbol not in members:
                members[symbol] = deepcopy(row)
    register = previous.get("screening_decision_register", [])
    if not isinstance(register, list):
        raise ValueError("previous screening decision register must be a list")
    for decision in register:
        if (not isinstance(decision, dict) or
                decision.get("queue_decision") not in {"INCLUDED_CANDIDATE", "EXCLUDED", "DATA_GAP"} or
                _time(decision["evaluation_at"]) > prior_time or
                _time(decision["source_available_at"]) > prior_time):
            raise ValueError("invalid previous screening decision register")
    return members, previous


def _merge_replayed_points(native, consumed):
    """Keep native evidence verbatim; duplicates never create independent sources."""
    merged, identities, semantic = [], {}, {}
    for point in [*native, *consumed]:
        digest = _canonical_hash(point)
        identity = point.get("data_point_id")
        if identity in identities:
            if identities[identity] != digest:
                raise ValueError("conflicting replayed financial fact identity")
            continue
        if identity:
            identities[identity] = digest
        meta = point.get("metadata") or {}
        source_hash = point.get("sha256") or point.get("raw_file_hash")
        key = (point.get("symbol"), point.get("period_label"), point.get("field_name"),
               point.get("unit"), source_hash, meta.get("statement_scope"),
               meta.get("derivation_formula"))
        if source_hash and meta.get("derivation_formula") in DERIVED_VERSIONS:
            if key in semantic:
                if _canonical_hash({"value": semantic[key]["value"]}) != _canonical_hash({"value": point["value"]}):
                    raise ValueError("conflicting same-source derived fact")
                # Do not promote a repeated original into cross-source assurance.
                continue
            semantic[key] = point
        merged.append(deepcopy(point))
    return merged


def build_sse_research_priority(*, root, manifest_binding, financial_export_path,
        financial_export_sha256, now, budget=30, previous_path=None, previous_sha256=None):
    """Replay at explicit current cutoff; caller persists the immutable result."""
    root = Path(root).resolve()
    now = _time(now)
    if type(budget) is not int or not 1 <= budget <= 200:
        raise ValueError("budget must be an integer from 1 to 200")
    prior, previous = _previous(root, previous_path, previous_sha256, now)
    capture = sse_main_screening.replay_research_inputs(
        root=root, manifest_binding=manifest_binding, now=now)
    screen, receipt, base = capture["screen"], capture["receipt"], capture["points"]
    if (screen.get("scope") != "SSE_MAIN_A_ONLY" or screen.get("action") != "no_order"
            or screen.get("coverage_complete") is not True or receipt.get("action") != "no_order"):
        raise ValueError("complete research-only SSE replay required")
    source_time = _time(screen["available_at"])
    if source_time > now:
        raise ValueError("future source availability")
    export = _inside(root, financial_export_path)
    payload = _load_bound(export, financial_export_sha256)
    if not isinstance(base, list) or _canonical_hash({"points": payload.get("points")}) != _canonical_hash({"points": base}):
        raise ValueError("financial export points differ from exact SSE capture")
    if {k: v for k, v in payload.items() if k not in {"value_enrichment_sources", "points"}} != {k: v for k, v in capture["financial_payload"].items() if k not in {"value_enrichment_sources", "points"}}:
        raise ValueError("financial export metadata differs from exact SSE capture")
    sources = payload.get("value_enrichment_sources", [])
    if not isinstance(sources, list):
        raise ValueError("explicit enrichment source list required")
    for original in capture["financial_payload"].get("value_enrichment_sources", []):
        if original not in sources:
            raise ValueError("captured enrichment source omitted")
    # Only the helper's explicit current reconciliation results bypass legacy
    # declaration replay. Historical derived claims in base retain its checks.
    revalidated = capture.get("native_revalidated_points")
    if not isinstance(revalidated, list):
        raise ValueError("explicit native_revalidated_points list required")
    native_ids = set()
    for point in revalidated:
        if not isinstance(point, dict):
            raise ValueError("invalid native revalidation point")
        identity = point.get("data_point_id")
        if not isinstance(identity, str) or not identity or identity in native_ids:
            raise ValueError("invalid or duplicate native revalidation identity")
        matches = [p for p in base if p.get("data_point_id") == identity]
        if len(matches) != 1 or _canonical_hash(matches[0]) != _canonical_hash(point):
            raise ValueError("native revalidation point differs from exact capture")
        native_ids.add(identity)
    native = [p for p in base if p.get("data_point_id") in native_ids]
    ordinary = [p for p in base if p.get("data_point_id") not in native_ids]
    consumed, adoption = consume_retained_enrichment(
        root, deepcopy(ordinary), sources, evaluation_at=now, write_cache=False)
    points = _merge_replayed_points(native, consumed)
    grouped, unavailable = defaultdict(list), defaultdict(int)
    for point in points:
        if _point_available_at(point, now) is None:
            unavailable[point["symbol"]] += 1
        else:
            grouped[point["symbol"]].append(point)
    rows = screen["rows"]
    if len({r["symbol"] for r in rows}) != len(rows):
        raise ValueError("duplicate SSE symbol")
    candidates = [deepcopy(r) for r in rows if r["status"] == "CANDIDATE"]
    if len(candidates) != screen["counts"]["candidate"]:
        raise ValueError("SSE candidate count mismatch")
    qualities = {}
    for row in candidates:
        row["conditions"], _ = observation_conditions(grouped[row["symbol"]], now=now)
        row["price_conflict"] = bool(row.get("price_conflict") or
            row.get("financial_crosscheck", {}).get("conflict_count") or
            row.get("financial_data", {}).get("conflict_count"))
        quality = evaluate_financial_quality(row["symbol"], row["company_name"], row.get("industry"),
            grouped[row["symbol"]], evaluation_date=now.date())
        qualities[row["symbol"]] = quality
        if (row.get("applicability", {}).get("kind") is not None
                or quality.model_type != "general_enterprise"):
            row["profile_status"] = "SPECIALIZED_RESEARCH_REQUIRED"
    ranked, _ = rank_research_candidates(candidates, limit=budget)
    retained = {r["symbol"] for r in ranked if r["research_priority_eligible"]
                and prior.get(r["symbol"], {}).get("tracking_selected") is True}
    if len(retained) > budget:
        raise ValueError("BUDGET_BELOW_RETAINED_TRACKING_COUNT: explicit tracking review required")
    chosen = set(retained)
    for row in ranked:
        if len(chosen) >= budget:
            break
        if row["research_priority_eligible"]:
            chosen.add(row["symbol"])
    deep, enrichment = [], []
    for row in ranked:
        symbol = row["symbol"]
        company_points = grouped[symbol]
        quality = qualities[symbol]
        period = quality.calculation_details.get("period") or selected_period(company_points)
        required = list(quality.calculation_details.get("required_fields", GENERAL_FIELDS))
        current = [p for p in company_points if p["period_label"] == period]
        accepted = sorted({p["field_name"] for p in current if p["field_name"] in required and _accepted(p)})
        supported = row["profile_status"] == "GENERAL_RESEARCH" and quality.model_type == "general_enterprise"
        score = quality.total_score if supported and row["research_priority_eligible"] else None
        old = prior.get(symbol)
        row.update(
            research_state="DATA_CHECK", profile_statuses=[row["profile_status"]],
            supported_quality_profile=supported, model_type=quality.model_type,
            quality_status=quality.quality_status, quality_score=str(score) if score is not None else None,
            quality_reasons=quality.reasons, economic_data=quality.calculation_details,
            evidence_ids=[p["data_point_id"] for p in current if p.get("data_point_id")],
            screening_reasons=[row.get("reason", "")],
            evidence_completeness=dict(required_fields=required, accepted_fields=accepted,
                missing_fields=sorted(set(required)-set(accepted)), coverage_ratio=str(quality.coverage_ratio)),
            field_observations=[dict(p, accepted_by_existing_quality_policy=_accepted(p)) for p in current],
            timing=dict(evaluation_at=now.isoformat(), source_available_at=source_time.isoformat(),
                financial_period=period or None, unavailable_point_count=unavailable[symbol],
                quote_date=None, quote_date_verification="UNVERIFIED_PROVIDER_TRADE_DATE"),
            first_seen=old["first_seen"] if old else now.isoformat(),
            first_seen_at=old["first_seen"] if old else now.isoformat(),
            tracking_status="CARRIED" if old else "NEW",
            was_tracking_selected=bool(old and (old.get("tracking_selected") or old.get("was_tracking_selected"))),
            industry=row.get("industry"), gaps=row.get("gaps", []),
            continuity="CARRIED" if old else "NEW", tracking_selected=symbol in chosen,
            queue_status="SELECTED_FOR_RESEARCH" if symbol in chosen else "BUDGET_DEFERRED",
            scheduling_basis="EXISTING_OBSERVATION_RANK_NOT_INVESTMENT_THRESHOLD")
        (deep if score is not None else enrichment).append(row)
    current_eligible = {r["symbol"] for r in ranked if r["research_priority_eligible"]}
    observed = {r["symbol"]: r for r in rows}
    history = []
    for symbol, old in prior.items():
        if symbol in current_eligible:
            continue
        current = observed.get(symbol)
        was_selected = bool(old.get("tracking_selected") or old.get("was_tracking_selected"))
        old.update(was_tracking_selected=was_selected, tracking_selected=False, continuity="CARRIED", tracking_status="PAUSED", queue_status="TRACKING_REVIEW_REQUIRED",
            history_reason="SOURCE_UNKNOWN" if current is None else
                "SOURCE_CONFLICT" if current.get("price_conflict") or current.get("financial_crosscheck", {}).get("conflict_count")
                else "NOT_CURRENTLY_ELIGIBLE" if symbol in {r["symbol"] for r in ranked} else "NO_LONGER_SCREEN_CANDIDATE",
            current_screen_status=current.get("status") if current else None,
            last_reviewed_at=now.isoformat(), exit_confirmed=False,
            history_interpretation="SCREENING_OR_SOURCE_REVIEW_ONLY_NOT_BUSINESS_DETERIORATION_OR_CONFIRMED_EXIT")
        history.append(old)
    result = dict(schema_version=SCHEMA_VERSION, action="no_order", admission="RESEARCH_QUEUE_ONLY",
        as_of=now.isoformat(), evaluation_at=now.isoformat(), source_available_at=source_time.isoformat(),
        run_id=screen["run_id"], budget=budget, enrichment_budget=budget,
        deep_research_priority=deep, evidence_enrichment_work_queue=enrichment,
        screening_decision_register=_screening_decision_register(
            rows, evaluation_at=now, source_available_at=source_time),
        tracking_history=history, tracking_count=len(chosen), candidate_count=len(candidates), selected_deep_research_count=sum(r["tracking_selected"] for r in deep),
        selected_enrichment_count=sum(r["tracking_selected"] for r in enrichment),
        timing=dict(evaluation_at=now.isoformat(), source_available_at=source_time.isoformat()),
        evidence_completeness=dict(candidate_count=len(candidates), queue_count=len(deep)+len(enrichment)),
        inputs=dict(sse_manifest=deepcopy(manifest_binding),
            financial_export_path=export.relative_to(root).as_posix(),
            financial_export_sha256=financial_export_sha256,
            previous_queue_path=_inside(root, previous_path).relative_to(root).as_posix() if previous else None,
            previous_queue_sha256=previous_sha256),
        retained_enrichment_sources=deepcopy(sources), retained_enrichment_adoption=adoption,
        new_verification_or_approval_count=0,
        budget_basis="RESEARCH_RESOURCE_BUDGET_NOT_INVESTMENT_THRESHOLD")
    result["content_sha256"] = _canonical_hash(result)
    return result

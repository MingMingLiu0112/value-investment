"""Offline daily event/financial wiring over the existing bounded research pilot.

This consumes an explicitly selected ResearchCase, not a second announcement
collector. It drafts questions about recorded events; it does not discover new
announcements, decide materiality, or publish/register a current packet.
"""
from pathlib import Path
import hashlib
import json
import re

from ....infrastructure.agent_runtime.provider import MockLLMProvider
from ...product.agent_research_surface import project_verified_agent_packet
from ...product.common import sha256_file, require_inside, load_json_object
from ...historical_validation.disclosed_metric_review import review_disclosed_metrics
from .llm_pilot import ROLE_TASKS, run_llm_research_pilot
from .snapshot import load_research_snapshot
from .source_context import ExcerptRequest, load_source_context


def _bound_mock(responses: dict[str, str], binding: dict) -> MockLLMProvider:
    """Pin the complete daily invocation using the pilot's existing input pin.

    Replies/model identity stay unchanged. The fixture input now comprises
    both those replies and the workflow inputs; the pilot compares this pin
    under its existing exclusive-create/replay policy. Legacy packets without
    this binding must use a new output path, never be rewritten in place.
    """
    provider = MockLLMProvider(responses)
    provider.responses_sha256 = hashlib.sha256(json.dumps({
        "schema_version": "daily-workflow-mock-input-v2",
        "responses_sha256": provider.responses_sha256, "binding": binding,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
    return provider


def run_daily_event_mock(*, root: Path, workbench: Path, workbench_sha256: str,
                         symbol: str, output: Path, responses: dict[str, str],
                         source_requests: tuple[ExcerptRequest, ...]) -> dict:
    """Return a review-ready projection or an explicit missing-input outcome.

    Raw responses are supplied Mock fixtures, never generated financial facts.
    The pilot owns version matching, exclusive creation, and repeat-run reuse.
    Invalid/stale/tampered inputs raise through the existing verifiers; a failed
    run can be retried at the same output after its inputs are corrected.
    """
    snapshot = load_research_snapshot(root=root, workbench=workbench,
        expected_sha256=workbench_sha256, symbol=symbol)
    result = {
        "schema_version": "daily-agent-event-mock-v1", "action": "no_order",
        "mode": "MOCK", "symbol": symbol,
        "research_input_fingerprint": snapshot.input_fingerprint,
        "research_as_of": snapshot.as_of.isoformat(),
        "workflows": {
            "financial_report": "NOT_REQUESTED_REQUIRES_DISCLOSED_METRIC_TRANSCRIPTION",
            "announcement_event": "BLOCKED_MISSING_RECORDED_EVENT_OR_ORIGINAL",
            "hotspot": "NOT_WIRED_REQUIRES_DATED_THEME_NEWS_AND_PRICE_STRUCTURE",
            "retrospective": "NOT_WIRED_REQUIRES_PLAN_ASOF_DATA_AND_REAL_MANUAL_FILLS",
        },
        "formal_fact_count": 0, "approval_count": 0, "decision_changed": False,
        "findings": [], "sources": [],
    }
    event_refs = {ref for event in snapshot.next_events if event.get("text")
                  for ref in event.get("evidence_refs", ())}
    if not event_refs or not source_requests:
        return result
    context = load_source_context(root=root, snapshot=snapshot,
        requests=source_requests, enabled=True)
    covered = {item.source_id for item in context.excerpts}
    result["unreviewed_event_evidence_refs"] = sorted(event_refs - covered)
    if not event_refs.intersection(covered):
        return result
    # The concrete Mock is constructed here, so this entry cannot call a live
    # adapter supplied by its caller, even if credentials exist in the process.
    workflow_binding = {"workflow": "announcement_event", "version": 2,
        "workbench": {"path": workbench.resolve().relative_to(root.resolve()).as_posix(),
                      "sha256": workbench_sha256},
        "research_input_fingerprint": snapshot.input_fingerprint}
    packet = run_llm_research_pilot(root=root, workbench=workbench,
        workbench_sha256=workbench_sha256, symbol=symbol, output=output,
        provider=_bound_mock(responses, workflow_binding), mode="mock",
        source_requests=source_requests)
    payload = {"as_of": snapshot.as_of.isoformat(),
               "generated_at": packet["generated_at"],
               "companies": [{"symbol": symbol}], "audit": {"evidence": []}}
    project_verified_agent_packet(payload, root=root, path=output,
                                  expected_sha256=sha256_file(output))
    result.update(workflow_binding=workflow_binding, workflow_input_sha256=packet["provider_input_sha256"],
                  packet={"path": output.resolve().relative_to(root.resolve()).as_posix(),
                          "sha256": sha256_file(output)},
                  findings=payload["companies"][0]["agent_research"],
                  sources=payload["audit"]["evidence"])
    result["workflows"]["announcement_event"] = "MOCK_DRAFT_PENDING_HUMAN_REVIEW"
    return result


def run_daily_financial_mock(*, root: Path, workbench: Path, workbench_sha256: str,
                             symbol: str, output: Path,
                             source_requests: tuple[ExcerptRequest, ...],
                             transcription: Path | None = None,
                             transcription_sha256: str | None = None,
                             metric_workbench: Path | None = None,
                             metric_workbench_sha256: str | None = None) -> dict:
    """Draft questions from source-reverified, period-aligned cash-flow rows.

    ResearchSnapshot has no period contract. Consume the EXISTING disclosed
    metric transcription type and its verifier instead of inferring periods
    from filenames or adding financial models. The separate metric workbench
    is an existing product-existing-research-workbench-v1 source-record view;
    its source must also bind to this ResearchSnapshot. Only adjacent annual
    columns with explicit cash statement scope are supported in this slice.
    No generated number, growth calculation or accounting approval is emitted.
    """
    snapshot = load_research_snapshot(root=root, workbench=workbench,
        expected_sha256=workbench_sha256, symbol=symbol)
    result = {
        "schema_version": "daily-agent-financial-mock-v1", "action": "no_order",
        "mode": "MOCK", "symbol": symbol, "research_as_of": snapshot.as_of.isoformat(),
        "research_input_fingerprint": snapshot.input_fingerprint,
        "workflows": {"financial_report": "BLOCKED_MISSING_COMPARABLE_FINANCIAL_INPUTS"},
        "gaps": [], "findings": [], "sources": [],
        "formal_fact_count": 0, "approval_count": 0, "decision_changed": False,
        "financial_gate_admitted": False, "forecast_assumptions_approved": False,
        "strict_pit_admitted": False,
        "economic_comparability_approved": False,
        "accounting_comparability": "REQUIRES_HUMAN_REVIEW_OF_RESTATEMENT_AND_CLASSIFICATION",
    }
    if transcription is None or transcription_sha256 is None:
        result["gaps"] = ["SNAPSHOT_HAS_NO_COMPARABLE_PERIOD_CONTRACT",
                          "REQUIRES_DISCLOSED_METRIC_TRANSCRIPTION_AND_HASH"]
        return result
    path = require_inside(root.resolve(), transcription, "financial transcription")
    if path.stat().st_size > 128 * 1024:
        raise ValueError("Financial transcription exceeds bounded input")
    if sha256_file(path) != transcription_sha256:
        raise ValueError("financial transcription hash mismatch")
    request = load_json_object(path, "financial transcription")
    if (request.get("schema_version") != "disclosed-metric-transcription-v1"
            or request.get("symbol") != symbol or request.get("action") != "no_order"):
        raise ValueError("financial transcription scope mismatch")
    binding = request["source_binding"]
    catalog = snapshot.evidence_by_id()
    matches = [ref for ref in catalog.values() if ref["path"] == binding["path"]
               and ref["sha256"] == binding["sha256"]
               and ref.get("source_url") == binding.get("source_url")]
    official = re.fullmatch(
        r"https://static\.cninfo\.com\.cn/finalpage/\d{4}-\d{2}-\d{2}/(\d+)\.PDF",
        binding.get("source_url", ""), re.IGNORECASE)
    if (len(matches) != 1 or official is None
            or matches[0]["id"] != "cninfo:" + official.group(1)
            or Path(binding["path"]).suffix.lower() != ".pdf"):
        raise ValueError("Financial source must bind an official PDF in the research snapshot")
    rows = request.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
        raise ValueError("Financial transcription requires bounded rows")
    checks = []
    for row in rows:
        periods = sorted(row.get("period_columns", {}))
        if (len(periods) != 2 or any(not re.fullmatch(r"[0-9]{4}", p) for p in periods)
                or int(periods[1]) != int(periods[0]) + 1
                or int(periods[1]) >= snapshot.as_of.year):
            result["gaps"].append("REQUIRES_TWO_ADJACENT_COMPLETED_ANNUAL_PERIODS")
            continue
        contexts = " ".join(row.get("required_context", ()))
        if any(period not in contexts for period in periods):
            result["gaps"].append("PERIOD_HEADERS_NOT_EXPLICITLY_BOUND")
        else:
            headers = [value for value in row["required_context"]
                       if all(period in value for period in periods)]
            columns = row["period_columns"]
            if any(not all(re.search(r"(?<!\w)" + period + r"(?:年度)?(?!\w)", header)
                           for period in periods) for header in headers):
                result["gaps"].append("REQUIRES_ANNUAL_HEADERS_NOT_INTERIM_PERIOD_LABELS")
            if (not headers or set(columns.values()) != {0, 1}
                    or any((header.index(periods[0]) < header.index(periods[1]))
                           != (columns[periods[0]] < columns[periods[1]]) for header in headers)):
                result["gaps"].append("PERIOD_COLUMN_ORDER_NOT_BOUND_TO_HEADER")
        if (row.get("statement_scope") not in {"CONSOLIDATED", "PARENT"}
                or row.get("metric_name") not in {"reported_operating_cash_flow", "reported_cash_capex", "cash_capex"}
                or row.get("unit") != "CNY"):
            result["gaps"].append("REQUIRES_EXPLICIT_CNY_CASH_STATEMENT_SCOPE")
        checks.append({"metric": row["metric_name"], "prior_period": periods[0],
                       "current_period": periods[1], "scope": row.get("statement_scope"),
                       "unit": row.get("unit")})
    if result["gaps"]:
        return result
    if not source_requests:
        result["gaps"] = ["MISSING_ORIGINAL_ROW_AND_PERIOD_EXCERPTS"]
        return result
    context = load_source_context(root=root, snapshot=snapshot,
        requests=source_requests, enabled=True)
    original = matches[0]
    excerpts = [item for item in context.excerpts if item.source_id == original["id"]]
    for row in rows:
        text = " ".join(" ".join(item.excerpt.split()) for item in excerpts
                         if item.page in row.get("context_physical_pages", [row["physical_page"]]))
        row_text = " ".join(" ".join(item.excerpt.split()) for item in excerpts
                             if item.page == row["physical_page"])
        if (" ".join(row["evidence_excerpt"].split()) not in row_text
                or any(" ".join(value.split()) not in text for value in row["required_context"])):
            result["gaps"].append("MODEL_CONTEXT_MISSING_VERIFIED_ROW_OR_PERIOD_HEADERS")
    if result["gaps"]:
        return result
    if (metric_workbench is None) != (metric_workbench_sha256 is None):
        raise ValueError("Metric workbench requires both path and hash")
    review = review_disclosed_metrics(root=root, path=path, expected_sha256=transcription_sha256,
        workbench_path=metric_workbench if metric_workbench is not None else workbench,
        workbench_sha256=metric_workbench_sha256 if metric_workbench is not None else workbench_sha256)
    # The existing verifier checks the exact numeric columns in the original;
    # these deterministic Mock questions make no assertion about their change.
    selected = checks[0]
    subject = (f"{selected['metric']} {selected['prior_period']} vs {selected['current_period']} "
               f"({selected['scope']}, {selected['unit']})")
    questions = (
        f"What explains the disclosed annual {subject}, and which recurring cash items need review?",
        f"Could reclassification, restatement or cash timing undermine comparability of {subject}? "
        "Do not equate operating cash flow with normalized parent earnings.",
        f"Which subsequent filing or accounting-policy disclosure should reopen the review of {subject}?",
    )
    responses = {role.value: json.dumps({"findings": [{
        "claim": question, "finding_type": "RESEARCH_QUESTION",
        "supporting_evidence_refs": [original["id"]], "counter_evidence_refs": [],
        "affected_research_dimensions": [task[1]], "confidence": "LOW",
        "proposed_follow_up": "Review original columns and accounting notes; transcription SHA256 "
                              + transcription_sha256,
    }]}) for (role, task), question in zip(ROLE_TASKS.items(), questions)}
    metric_path = metric_workbench if metric_workbench is not None else workbench
    metric_pin = metric_workbench_sha256 if metric_workbench is not None else workbench_sha256
    workflow_binding = {"workflow": "financial_report", "version": 2,
        "research_input_fingerprint": snapshot.input_fingerprint,
        "workbench": {"path": workbench.resolve().relative_to(root.resolve()).as_posix(),
                      "sha256": workbench_sha256},
        "transcription": {"path": path.relative_to(root.resolve()).as_posix(),
                          "sha256": transcription_sha256},
        "metric_workbench": {"path": metric_path.resolve().relative_to(root.resolve()).as_posix(),
                             "sha256": metric_pin}, "period_checks": checks,
        "economic_comparability_approved": False}
    packet = run_llm_research_pilot(root=root, workbench=workbench,
        workbench_sha256=workbench_sha256, symbol=symbol, output=output,
        provider=_bound_mock(responses, workflow_binding), mode="mock", source_requests=source_requests)
    payload = {"as_of": snapshot.as_of.isoformat(), "generated_at": packet["generated_at"],
               "companies": [{"symbol": symbol}], "audit": {"evidence": []}}
    project_verified_agent_packet(payload, root=root, path=output, expected_sha256=sha256_file(output))
    result.update(workflow_binding=workflow_binding, workflow_input_sha256=packet["provider_input_sha256"],
                  packet={"path": output.resolve().relative_to(root.resolve()).as_posix(),
                          "sha256": sha256_file(output)},
                  transcription={"path": path.relative_to(root.resolve()).as_posix(),
                                 "sha256": transcription_sha256},
                  period_checks=checks, verified_disclosed_facts=review["facts"],
                  verification_scope=review["limitation"],
                  accounting_comparability="REQUIRES_HUMAN_REVIEW_OF_RESTATEMENT_AND_CLASSIFICATION",
                  coverage="SELECTED_ANNUAL_CASH_ROWS_NOT_FULL_REPORT_OR_NORMALIZED_EARNINGS",
                  findings=payload["companies"][0]["agent_research"],
                  sources=payload["audit"]["evidence"])
    result["workflows"]["financial_report"] = "MOCK_FINANCIAL_QUESTIONS_PENDING_HUMAN_REVIEW"
    return result

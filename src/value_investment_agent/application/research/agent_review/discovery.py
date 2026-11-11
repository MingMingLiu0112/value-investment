"""Bounded server-owned discovery; immutable exports, no live calls or registration."""
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from ....domain.research.research_case import ResearchCase
from ....research_artifact_codecs import ResearchCaseCodec
from ....research_artifacts import ResearchArtifactEnvelope, ResearchArtifactIdentity, StoredResearchArtifact
from ...decision.artifact_bundle import export_artifact_bundle
from ...hotspot.current_registry import load_price_conditions
from ...product.common import write_new_bytes
from ...product.public_snapshot import load_current_packet
from .context_workflows import CONTEXT_KINDS, verify_workflow_context
from .snapshot import load_research_snapshot
from .source_context import ExcerptRequest, load_source_context
from .web_research import _binding, _json, _raw, _public_path, read_web_agent_research, REGISTRY_PATH


SCHEMA = "agent-daily-discovery-v1"
VERSION = "agent-context-export-v1"


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(root, ref, *, runtime_only=True):
    path = _binding(root, ref, runtime_only=runtime_only)
    raw = _raw(path, 8 * 1024 * 1024)
    if _hash(raw) != ref["sha256"]:
        raise ValueError("Discovery input hash mismatch")
    return _json(raw)


def _store(root, path, raw):
    path = _public_path(root, path.relative_to(root).as_posix(), runtime_only=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_new_bytes(path, raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError("Immutable discovery export conflicts")
    return {"path": path.relative_to(root).as_posix(), "sha256": _hash(raw)}


def _stamp(value, now):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("Discovery source time is naive or future")
    return stamp


def _export_context(root, directory, *, symbol, name, workflow, scope, records, upstream, now):
    """Text is a derived source view, with every upstream original also hash-bound."""
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("Discovery requires an exact security identity")
    for row in records:
        _stamp(row["available_at"], now)
    identity = {"version": VERSION, "symbol": symbol, "name": name, "workflow": workflow,
                "scope": scope, "records": records, "upstream": upstream}
    folder = directory / (workflow + "-" + symbol + "-" + _hash(_bytes(identity)))
    existed = (folder / "workbench.json").exists()
    evidence, requests, context_rows = [], [], []
    available = max(_stamp(row["available_at"], now) for row in records)
    for row in records:
        text = row["text"]
        if not isinstance(text, str) or not 8 <= len(text) <= 500:
            raise ValueError("Discovery record exceeds bounded text contract")
        ref = _store(root, folder / (row["kind"] + ".txt"), text.encode("utf-8"))
        source_id = "derived-" + row["kind"] + "-" + ref["sha256"][:16]
        evidence.append(dict(ref, id=source_id, available_at=row["available_at"],
            title="Derived observation / " + scope + " / " + row["kind"]))
        requests.append(ExcerptRequest(source_id, ref["path"], ref["sha256"], row["available_at"],
                                      text, text_start=0, text_end=len(text)))
        context_rows.append(dict(kind=row["kind"], source_id=source_id, excerpt=text,
                                 available_at=row["available_at"]))
    # Source originals are retained as evidence, never passed off as independently
    # confirmed claims by the derived textual view.
    seen = {ref["path"] for ref in evidence}
    for ref in upstream:
        path = _binding(root, {key: ref[key] for key in ("path", "sha256")}, runtime_only=False)
        if _hash(_raw(path, 32 * 1024 * 1024)) != ref["sha256"]:
            raise ValueError("Discovery upstream original changed")
        if ref["path"] not in seen:
            evidence.append(dict(path=ref["path"], sha256=ref["sha256"],
                id="upstream-" + _hash(ref["path"].encode())[:16],
                available_at=available.isoformat(), title="Retained upstream observation bytes"))
            seen.add(ref["path"])
    if len(evidence) > 100:
        raise ValueError("Discovery upstream evidence budget exceeded")
    statement = dict(kind="interpretation", text="Observation questions pending human review",
                     evidence_refs=[evidence[0]["id"]])
    case = ResearchCase(symbol=symbol, name=name, as_of=available.astimezone(ZoneInfo("Asia/Shanghai")).date(),
        run_id=folder.name, generated_at=available, research_version=VERSION,
        industry="observation", investment_path="HOTSPOT_SATELLITE" if workflow == "hotspot" else "TEST_ONLY",
        thesis="Source-bound observation; no economic or strategy approval",
        return_driver="Not assessed", mispricing_hypothesis="Not assessed",
        financial_summary={}, positives=[statement], counter_evidence=[statement],
        thesis_breakers=[statement], next_events=[statement], evidence_status="verified",
        valuation_status="not_established", research_status="research_only",
        blockers=["DERIVED_OBSERVATION_NOT_CLAIM_APPROVAL", "NO_TRADING_ELIGIBILITY"],
        evidence_refs=evidence, quote_date=None, financial_period=None,
        missing_date_reasons={"quote_date": "Source trade date is separate from acquisition cutoff",
                             "financial_period": "Not a financial valuation"})
    stored = StoredResearchArtifact(artifact_id=folder.name,
        envelope=ResearchArtifactEnvelope.build(identity=ResearchArtifactIdentity(
            scope_type="security", scope_key=symbol, artifact_type="research_case",
            schema_version=ResearchCaseCodec.schema_version, as_of=case.as_of, available_at=available),
            payload=ResearchCaseCodec().to_payload(case), run_id=folder.name), created_at=available)
    wb = _store(root, folder / "workbench.json", _bytes(dict(symbol=symbol, action="no_order",
        artifact_bundle=export_artifact_bundle([stored]),
        source_verification=dict(status="LOCAL_BYTES_VERIFIED", sources=evidence))))
    context = _store(root, folder / "context.json", _bytes(dict(
        schema_version="agent-source-workflow-context-v1", action="no_order", symbol=symbol,
        workflow=workflow, scope=scope, records=context_rows)))
    excerpt_ref = _store(root, folder / "excerpt-requests.json", _bytes(dict(
        schema_version="agent-excerpt-requests-v1", action="no_order", symbol=symbol,
        requests=[asdict(row) for row in requests])))
    snapshot = load_research_snapshot(root=root, workbench=root / wb["path"],
        expected_sha256=wb["sha256"], symbol=symbol)
    verified = load_source_context(root=root, snapshot=snapshot, requests=tuple(requests), enabled=True)
    verify_workflow_context(root=root, snapshot=snapshot, workflow=workflow,
        context_path=root / context["path"], context_sha256=context["sha256"],
        excerpts=[vars(row) for row in verified.excerpts])
    return dict(symbol=symbol, workflow=workflow, workbench=wb, context=context,
                source_requests=excerpt_ref, output=(folder / "packet.json").relative_to(root).as_posix()), existed


def _hotspot_records(plan, now):
    selection = plan["daily_selection"]
    available = max(_stamp(plan["data_available_at"], now),
                    _stamp(plan["observation_evidence"]["available_at"], now)).isoformat()
    values = {
        "theme": dict(symbol=plan["symbol"], industry=selection["industry"],
            classification_effective_date=plan.get("classification_effective_date"),
            scope="Sector classification, not a verified causal news theme"),
        "activity": {key: selection[key] for key in
                     ("symbol", "industry", "trade_date", "amount_cny") if key in selection},
        "price_structure": dict(symbol=plan["symbol"], market_trade_date=plan["market_trade_date"],
            period_structure=plan["period_structure"], signal_state=plan["signal_state"],
            formal_eligibility=False, current_pit=False),
    }
    return [dict(kind=key, available_at=available, text=_bytes(value).decode().strip())
            for key, value in values.items()]


def _upstream_refs(root, plan):
    refs = [{"path": plan["case_path"], "sha256": plan["case_sha256"]},
            plan["daily_selection_binding"],
            {"path": plan["current_reference_close"]["bundle_path"],
             "sha256": plan["current_reference_close"]["bundle_sha256"]}]
    case = _read(root, refs[0])
    refs += list(case["source_bindings"].values()) + plan["selection_source_bindings"]
    return [{key: ref[key] for key in ("path", "sha256")} for ref in refs]


def discover_daily_mock_inputs(*, root: Path, output_directory: Path,
                               now: datetime, max_hotspots: int = 3,
                               retrospective: dict | None = None) -> dict:
    """Export a pinned existing batch plan; never run a provider or repoint a registry.

    Only fixed server registries are discovered. The optional retrospective pin
    is restricted to runtime/agent-research-test-only-inputs and explicit TEST_ONLY
    confirmation; no private-account path lookup or environment override exists.
    """
    if now.utcoffset() is None or type(max_hotspots) is not int or not 1 <= max_hotspots <= 10:
        raise ValueError("Aware clock and bounded hotspot limit required")
    root = root.resolve()
    directory = _public_path(root, (root / output_directory).absolute().relative_to(root).as_posix(), runtime_only=True)
    if not directory.is_relative_to(root / "runtime/agent-research-discovery"):
        raise ValueError("Discovery exports require dedicated runtime/agent-research-discovery directory")
    jobs, items = [], []
    errors = (ValueError, OSError, KeyError, TypeError, AttributeError, ArithmeticError)
    def failed(workflow, symbol=None, error=None):
        item = dict(workflow=workflow, symbol=symbol, status="FAILED_INPUT")
        if error is not None:
            item["reason"] = type(error).__name__
        items.append(item)
    # Reuse admitted original requests and verified financial transcription from
    # the server-owned registry, instead of adding a competing filings collector.
    try:
        registry = _json(_raw(_public_path(root, REGISTRY_PATH), 64 * 1024))
        entries = [(symbol, workflow, entry) for symbol, case in sorted(registry["cases"].items())
                   for workflow, entry in sorted(case.get("workflows", {}).items())
                   if workflow in {"event", "financial"}]
        if len(entries) > 8:
            raise ValueError("Retained daily discovery budget exceeded")
        for symbol, workflow, entry in entries:
            try:
                if read_web_agent_research(root, symbol=symbol, workflow=workflow, now=now)["status"] != "VERIFIED":
                    raise ValueError("Retained daily input not verified")
                packet = _read(root, entry["packet"])
                input_identity = dict(version=VERSION, workbench=entry["workbench"],
                    workflow_binding=entry["workflow_binding"],
                    responses={role: json.loads(text) for role, text in packet["raw_responses"].items()},
                    source_context=packet["source_context"])
                folder = directory / (workflow + "-" + symbol + "-" + _hash(_bytes(input_identity)))
                existed = (folder / "excerpt-requests.json").exists()
                requests = _store(root, folder / "excerpt-requests.json", _bytes(dict(
                    schema_version="agent-excerpt-requests-v1", action="no_order", symbol=symbol,
                    requests=packet["source_context"]["excerpts"])))
                job = dict(symbol=symbol, workflow=workflow, workbench=entry["workbench"],
                           source_requests=requests, output=(folder / "packet.json").relative_to(root).as_posix())
                if workflow == "event":
                    job["mock_responses"] = _store(root, folder / "responses.json", _bytes({
                        role: json.loads(text) for role, text in packet["raw_responses"].items()}))
                else:
                    for key in ("transcription", "metric_workbench"):
                        _read(root, entry["workflow_binding"][key])
                        job[key] = entry["workflow_binding"][key]
                jobs.append(job)
                items.append(dict(symbol=symbol, workflow=workflow, status="UNCHANGED" if existed else "EXPORTED"))
            except errors as error:
                failed(workflow, symbol, error)
    except errors as error:
        failed("retained_daily", error=error)
    try:
        # The packet is an optional verified public fallback; current registry
        # replay remains the authority for price plans and their source originals.
        packet, _ = load_current_packet(root)
        plans = load_price_conditions(root, now=now,
            research_version=packet.get("research_version") if packet else None)
        selected = [row for row in plans["items"]
                    if row["price_action_plan"].get("candidate_lifecycle") is None][:max_hotspots]
        for blocker in plans.get("blockers", []):
            failed("hotspot", blocker.rsplit(":", 1)[-1])
        if not selected and not plans.get("blockers"):
            items.append(dict(workflow="hotspot", status="NO_ADMITTED_CURRENT_PLANS"))
        for row in selected:
            try:
                plan = row["price_action_plan"]
                job, existed = _export_context(root, directory, symbol=row["symbol"], name=row["company_name"],
                    workflow="hotspot", scope="PUBLIC_RESEARCH", records=_hotspot_records(plan, now),
                    upstream=_upstream_refs(root, plan), now=now)
                jobs.append(job)
                items.append(dict(symbol=row["symbol"], workflow="hotspot",
                                  status="UNCHANGED" if existed else "EXPORTED"))
            except errors as error:
                failed("hotspot", row["symbol"], error)
    except errors as error:
        failed("hotspot", error=error)
    if retrospective is not None:
        try:
            path = _binding(root, retrospective)
            if not path.is_relative_to(root / "runtime/agent-research-test-only-inputs"):
                raise ValueError("Dedicated TEST_ONLY input boundary required")
            value = _read(root, retrospective)
            if (set(value) != {"schema_version", "action", "symbol", "account_scope", "confirmed", "records"}
                    or value["schema_version"] != "agent-test-only-retrospective-input-v1"
                    or value["action"] != "no_order" or value["account_scope"] != "TEST_ONLY"
                    or value["confirmed"] is not True or not isinstance(value["records"], list)
                    or len(value["records"]) != 4
                    or {row["kind"] for row in value["records"]} != CONTEXT_KINDS["retrospective"]
                    or any(set(row) != {"kind", "text", "available_at"} for row in value["records"])):
                raise ValueError("Confirmed TEST_ONLY retrospective input required")
            job, existed = _export_context(root, directory, symbol=value["symbol"], name="TEST_ONLY retrospective",
                workflow="retrospective", scope="TEST_ONLY", records=value["records"],
                upstream=[retrospective], now=now)
            jobs.append(job)
            items.append(dict(symbol=value["symbol"], workflow="retrospective",
                              status="UNCHANGED" if existed else "EXPORTED"))
        except errors as error:
            failed("retrospective", error=error)
    else:
        items.append(dict(workflow="retrospective", status="WAITING_CONFIRMED_TEST_ONLY_INPUT"))
    plan_ref = None
    if jobs:
        plan = dict(schema_version="daily-agent-mock-batch-v1", action="no_order", mode="MOCK", jobs=jobs)
        raw = _bytes(plan)
        plan_ref = _store(root, directory / ("batch-" + _hash(raw) + ".json"), raw)
    return dict(schema_version=SCHEMA, action="no_order", mode="MOCK", batch_plan=plan_ref,
        status="PARTIAL" if jobs and any(row["status"] == "FAILED_INPUT" for row in items) else
               "READY" if jobs else "BLOCKED", items=items, approval_count=0,
        registered_or_published=False, live_status="LIVE_LLM_NOT_AUTHORIZED")

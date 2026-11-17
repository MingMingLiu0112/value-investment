"""Isolated synthetic inputs exercise the real snapshot/pilot/projector chain."""
from dataclasses import replace
import json

import pytest

from test_llm_agent_research import _inputs, _replies
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research.agent_review.daily_research import run_daily_event_mock
from value_investment_agent.application.research.agent_review.source_context import ExcerptRequest
from value_investment_agent.application.research.agent_review import daily_research


def setup(root):
    workbench, digest, original = _inputs(root)
    text = original.read_text(encoding="utf-8")
    return dict(root=root, workbench=workbench, workbench_sha256=digest,
        symbol="600519", output=root / "runtime/daily-agent/packet.json",
        responses=_replies(), source_requests=(ExcerptRequest(
            "filing-1", "runtime/official.txt", sha256_file(original),
            "2026-10-07T12:00:00+08:00", text, text_start=0, text_end=len(text)),))


def test_mock_chain_reuses_packet_and_preserves_research(tmp_path):
    args = setup(tmp_path)
    before = args["workbench"].read_bytes()
    result = run_daily_event_mock(**args)
    stamp = args["output"].stat().st_mtime_ns
    assert result["workflows"]["announcement_event"] == "MOCK_DRAFT_PENDING_HUMAN_REVIEW"
    assert len(result["findings"]) == 3
    assert result["sources"][0]["sha256"] == args["source_requests"][0].sha256
    assert all(row["status"] == "PENDING_HUMAN_REVIEW" for row in result["findings"])
    assert result["approval_count"] == result["formal_fact_count"] == 0
    assert result["decision_changed"] is False
    assert run_daily_event_mock(**args) == result
    assert args["output"].stat().st_mtime_ns == stamp
    assert args["workbench"].read_bytes() == before


def test_missing_original_context_blocks_without_writing(tmp_path):
    args = setup(tmp_path)
    args["source_requests"] = ()
    result = run_daily_event_mock(**args)
    assert result["workflows"]["announcement_event"].startswith("BLOCKED_")
    assert not result["findings"] and not args["output"].exists()


def test_tampered_original_rejected_even_on_repeat(tmp_path):
    args = setup(tmp_path)
    run_daily_event_mock(**args)
    (tmp_path / "runtime/official.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="original bytes changed"):
        run_daily_event_mock(**args)


def test_bad_response_leaves_no_packet_or_runtime_lock_and_can_retry(tmp_path):
    args = setup(tmp_path)
    good = args["responses"]
    args["responses"] = {key: "invalid" for key in good}
    with pytest.raises(ValueError, match="not valid JSON"):
        run_daily_event_mock(**args)
    assert not args["output"].exists()
    # OS lock state lives outside the research output tree.
    assert not args["output"].with_suffix(".json.lock").exists()
    args["responses"] = good
    assert run_daily_event_mock(**args)["findings"]


def test_changed_mock_version_cannot_reuse_prior_output(tmp_path):
    args = setup(tmp_path)
    run_daily_event_mock(**args)
    args["responses"] = _replies("Changed research question")
    with pytest.raises(FileExistsError, match="different provider input"):
        run_daily_event_mock(**args)


def test_absent_recorded_event_does_not_invent_work(tmp_path, monkeypatch):
    args = setup(tmp_path)
    snapshot = daily_research.load_research_snapshot(root=tmp_path,
        workbench=args["workbench"], expected_sha256=args["workbench_sha256"], symbol="600519")
    monkeypatch.setattr(daily_research, "load_research_snapshot",
                        lambda **_: replace(snapshot, next_events=()))
    result = run_daily_event_mock(**args)
    assert result["workflows"]["announcement_event"].startswith("BLOCKED_")
    assert not args["output"].exists()


def test_mock_never_opens_provider_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Mock workflow attempted a network provider")

    monkeypatch.setattr("value_investment_agent.infrastructure.agent_runtime.provider.build_opener", forbidden)
    assert run_daily_event_mock(**setup(tmp_path))["findings"]


def financial_setup(root):
    """TEST_ONLY PDF with actual extractable text; no verifier/provider stubs."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    from value_investment_agent.research_artifact_codecs import ResearchCaseCodec
    from value_investment_agent.research_artifacts import (
        ResearchArtifactEnvelope, ResearchArtifactIdentity, StoredResearchArtifact,
    )
    from value_investment_agent.application.decision.artifact_bundle import export_artifact_bundle

    args = setup(root)
    text = "合并现金流量表 2025 2024 CNY Cash 100 90 2023 2022 PriorCash 80 70"
    chars = list(dict.fromkeys(text))
    codes = {char: index + 1 for index, char in enumerate(chars)}
    cmap = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap "
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def "
            "/CMapName /Test def /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange "
            + str(len(chars)) + " beginbfchar "
            + " ".join(f"<{codes[c]:02X}> <{c.encode('utf-16-be').hex()}>" for c in chars)
            + " endbfchar endcmap CMapName currentdict /CMap defineresource pop end end")
    writer = PdfWriter()
    page = writer.add_blank_page(width=1000, height=200)
    mapping = DecodedStreamObject()
    mapping.set_data(cmap.encode("ascii"))
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica"),
        NameObject("/ToUnicode"): writer._add_object(mapping)})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
        DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(("BT /F1 12 Tf 20 100 Td <" + "".join(f"{codes[c]:02X}" for c in text)
                     + "> Tj ET").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    pdf = root / "runtime/financial.pdf"
    with pdf.open("wb") as handle:
        writer.write(handle)
    extracted = extract_pages(pdf)[0]
    assert "Cash 100 90" in " ".join(extracted.split())
    ref = dict(id="cninfo:123", path="runtime/financial.pdf", sha256=sha256_file(pdf),
        source_url="https://static.cninfo.com.cn/finalpage/2026-04-01/123.PDF",
        available_at="2026-04-02T00:00:00+08:00")
    wb = json.loads(args["workbench"].read_text(encoding="utf-8"))
    case = ResearchCaseCodec().from_payload(json.loads(wb["artifact_bundle"]["artifacts"][0]["canonical_payload"]))
    statement = {"kind": "interpretation", "text": "TEST_ONLY cash question", "evidence_refs": [ref["id"]]}
    case = replace(case, evidence_refs=[ref], positives=[statement], counter_evidence=[statement],
                   thesis_breakers=[statement], next_events=[statement])
    stored = StoredResearchArtifact(artifact_id="financial-test", envelope=ResearchArtifactEnvelope.build(
        identity=ResearchArtifactIdentity(scope_type="security", scope_key=case.symbol,
            artifact_type="research_case", schema_version=ResearchCaseCodec.schema_version,
            as_of=case.as_of, available_at=case.generated_at),
        payload=ResearchCaseCodec().to_payload(case), run_id="test"), created_at=case.generated_at)
    wb.update(artifact_bundle=export_artifact_bundle([stored]),
              source_verification={"status": "LOCAL_BYTES_VERIFIED", "sources": [ref]},
              schema_version="product-existing-research-workbench-v1", suggested_state="NOT_READY",
              position_guidance=None, research={"source_records": [ref]})
    args["workbench"].write_text(json.dumps(wb), encoding="utf-8")
    row = dict(metric_name="reported_operating_cash_flow", physical_page=1, unit="CNY",
        statement_scope="CONSOLIDATED", row_label="Cash", evidence_excerpt="Cash 100 90",
        required_context=["2025 2024", "CNY", "合并现金流量表"],
        period_columns={"2025": 0, "2024": 1}, values_by_period={"2025": "100", "2024": "90"})
    transcription = root / "runtime/transcription.json"
    transcription.write_text(json.dumps(dict(schema_version="disclosed-metric-transcription-v1",
        symbol="600519", action="no_order", source_binding={k: ref[k] for k in
            ("path", "sha256", "source_url")}, rows=[row])), encoding="utf-8")
    args.pop("responses")
    args.update(workbench_sha256=sha256_file(args["workbench"]),
        transcription=transcription, transcription_sha256=sha256_file(transcription),
        source_requests=(ExcerptRequest(ref["id"], ref["path"], ref["sha256"],
                                       ref["available_at"], extracted, page=1),))
    return args


def test_financial_real_verifiers_and_mock_questions_are_idempotent(tmp_path):
    args = financial_setup(tmp_path)
    result = daily_research.run_daily_financial_mock(**args)
    assert result["workflows"]["financial_report"] == "MOCK_FINANCIAL_QUESTIONS_PENDING_HUMAN_REVIEW"
    assert result["period_checks"][0]["prior_period"] == "2024"
    assert [f["value"] for f in result["verified_disclosed_facts"]] == ["100", "90"]
    assert len(result["findings"]) == 3
    assert all(f["status"] == "PENDING_HUMAN_REVIEW" for f in result["findings"])
    assert "normalized parent earnings" in result["findings"][1]["claim"]
    assert not result["financial_gate_admitted"] and not result["forecast_assumptions_approved"]
    assert result["economic_comparability_approved"] is False
    assert result["workflow_binding"]["economic_comparability_approved"] is False
    assert result["accounting_comparability"].startswith("REQUIRES_HUMAN_REVIEW")
    packet = json.loads(args["output"].read_text(encoding="utf-8"))
    assert result["workflow_input_sha256"] == packet["provider_input_sha256"]
    stamp = args["output"].stat().st_mtime_ns
    assert daily_research.run_daily_financial_mock(**args) == result
    assert args["output"].stat().st_mtime_ns == stamp


@pytest.mark.parametrize("fault", ["missing", "same_period", "nonannual", "future_period",
    "scope", "headers", "interim_headers", "reversed_labels", "excerpt", "value", "columns", "official", "original", "hash"])
def test_financial_missing_or_invalid_inputs_cannot_create_draft(tmp_path, fault):
    args = financial_setup(tmp_path)
    request = json.loads(args["transcription"].read_text(encoding="utf-8"))
    row = request["rows"][0]
    if fault == "missing":
        args.pop("transcription")
        args.pop("transcription_sha256")
    elif fault == "same_period": row["period_columns"] = {"2025": 0}
    elif fault == "nonannual": row["period_columns"] = {"2025H1": 0, "2024H1": 1}
    elif fault == "future_period": row["period_columns"] = {"2026": 0, "2025": 1}
    elif fault == "scope": row["statement_scope"] = "UNSPECIFIED"
    elif fault == "headers": row["required_context"] = ["CNY"]
    elif fault == "interim_headers": row["required_context"] = ["2025H1 2024H1", "CNY"]
    elif fault == "reversed_labels":
        row["period_columns"] = {"2024": 0, "2025": 1}
        row["values_by_period"] = {"2024": "100", "2025": "90"}
    elif fault == "excerpt": args["source_requests"] = ()
    elif fault == "value": row["values_by_period"]["2025"] = "999"
    elif fault == "columns": row["period_columns"]["2024"] = 0
    elif fault == "official": request["source_binding"]["source_url"] = "https://example.test/a.pdf"
    elif fault == "original": (tmp_path / "runtime/financial.pdf").write_bytes(b"tampered")
    elif fault == "hash": args["transcription_sha256"] = "0" * 64
    if fault not in {"missing", "hash"}:
        args["transcription"].write_text(json.dumps(request), encoding="utf-8")
        args["transcription_sha256"] = sha256_file(args["transcription"])
    if fault in {"value", "official", "original", "hash"}:
        with pytest.raises(ValueError): daily_research.run_daily_financial_mock(**args)
    else:
        result = daily_research.run_daily_financial_mock(**args)
        assert result["gaps"] and not result["findings"]
    assert not args["output"].exists()


def test_financial_repeat_reverifies_transcription_and_never_uses_network(tmp_path, monkeypatch):
    args = financial_setup(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("Financial Mock attempted a network provider")

    monkeypatch.setattr("value_investment_agent.infrastructure.agent_runtime.provider.build_opener", forbidden)
    daily_research.run_daily_financial_mock(**args)
    packet = args["output"].read_bytes()
    args["transcription"].write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        daily_research.run_daily_financial_mock(**args)
    assert args["output"].read_bytes() == packet


def test_financial_model_context_must_include_actual_row_not_only_header(tmp_path):
    args = financial_setup(tmp_path)
    args["source_requests"] = (replace(args["source_requests"][0], excerpt="2025 2024 CNY"),)
    result = daily_research.run_daily_financial_mock(**args)
    assert result["gaps"] == ["MODEL_CONTEXT_MISSING_VERIFIED_ROW_OR_PERIOD_HEADERS"]
    assert not args["output"].exists()


@pytest.mark.parametrize("change", ["legal_content", "legal_period", "metric_workbench",
                                     "metric_workbench_content", "transcription_path"])
def test_financial_same_snapshot_rejects_different_binding_without_overwrite(tmp_path, change):
    args = financial_setup(tmp_path)
    if change == "metric_workbench_content":
        other = tmp_path / "runtime/metric-workbench.json"
        other.write_bytes(args["workbench"].read_bytes())
        args.update(metric_workbench=other, metric_workbench_sha256=sha256_file(other))
    first = daily_research.run_daily_financial_mock(**args)
    before = args["output"].read_bytes(), args["output"].stat().st_mtime_ns
    if change == "metric_workbench":
        other = tmp_path / "runtime/other-workbench.json"
        other.write_bytes(args["workbench"].read_bytes())
        args.update(metric_workbench=other, metric_workbench_sha256=sha256_file(other))
    elif change == "metric_workbench_content":
        payload = json.loads(args["metric_workbench"].read_text(encoding="utf-8"))
        payload["test_only_note"] = "New valid supplementary workbench version"
        args["metric_workbench"].write_text(json.dumps(payload), encoding="utf-8")
        args["metric_workbench_sha256"] = sha256_file(args["metric_workbench"])
    elif change == "transcription_path":
        other = tmp_path / "runtime/other-transcription.json"
        other.write_bytes(args["transcription"].read_bytes())
        args["transcription"] = other
    else:
        request = json.loads(args["transcription"].read_text(encoding="utf-8"))
        row = request["rows"][0]
        if change == "legal_content":
            row["required_context"].append("Cash")
        else:
            row.update(period_columns={"2023": 0, "2022": 1},
                values_by_period={"2023": "80", "2022": "70"}, row_label="PriorCash",
                evidence_excerpt="PriorCash 80 70", required_context=["2023 2022", "CNY", "合并现金流量表"])
        args["transcription"].write_text(json.dumps(request), encoding="utf-8")
        args["transcription_sha256"] = sha256_file(args["transcription"])
    with pytest.raises(FileExistsError):
        daily_research.run_daily_financial_mock(**args)
    assert (args["output"].read_bytes(), args["output"].stat().st_mtime_ns) == before
    # Prove the changed inputs are valid and only the occupied output is refused.
    args["output"] = tmp_path / "runtime/changed-financial.json"
    changed = daily_research.run_daily_financial_mock(**args)
    assert changed["findings"]
    assert changed["research_input_fingerprint"] == first["research_input_fingerprint"]
    assert changed["workflow_input_sha256"] != first["workflow_input_sha256"]


@pytest.mark.parametrize("first_workflow", ["event", "financial"])
def test_event_financial_same_path_rejects_even_identical_mock_responses(tmp_path, first_workflow):
    args = financial_setup(tmp_path)
    seed = dict(args, output=tmp_path / "runtime/seed-financial.json")
    daily_research.run_daily_financial_mock(**seed)
    raw = json.loads(seed["output"].read_text(encoding="utf-8"))["raw_responses"]
    event = {key: args[key] for key in ("root", "workbench", "workbench_sha256", "symbol",
                                      "output", "source_requests")}
    event["responses"] = raw
    first, second = ((daily_research.run_daily_event_mock, event),
                     (daily_research.run_daily_financial_mock, args))
    if first_workflow == "financial":
        first, second = second, first
    first[0](**first[1])
    before = args["output"].read_bytes(), args["output"].stat().st_mtime_ns
    with pytest.raises(FileExistsError):
        second[0](**second[1])
    assert (args["output"].read_bytes(), args["output"].stat().st_mtime_ns) == before


def test_legacy_unbound_financial_packet_is_not_silently_upgraded(tmp_path):
    from value_investment_agent.application.research.agent_review.llm_pilot import run_llm_research_pilot
    from value_investment_agent.infrastructure.agent_runtime.provider import MockLLMProvider

    args = financial_setup(tmp_path)
    seed = dict(args, output=tmp_path / "runtime/seed.json")
    daily_research.run_daily_financial_mock(**seed)
    raw = json.loads(seed["output"].read_text(encoding="utf-8"))["raw_responses"]
    run_llm_research_pilot(**{key: args[key] for key in
        ("root", "workbench", "workbench_sha256", "symbol", "output", "source_requests")},
        mode="mock", provider=MockLLMProvider(raw))
    before = args["output"].read_bytes(), args["output"].stat().st_mtime_ns
    with pytest.raises(FileExistsError, match="different provider input"):
        daily_research.run_daily_financial_mock(**args)
    assert (args["output"].read_bytes(), args["output"].stat().st_mtime_ns) == before

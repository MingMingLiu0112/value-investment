"""Content-addressed mapping preserves six-bridge scope and review authority."""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path
import os

import pytest
import pypdf

from test_economic_review_bundle import retained, NOW
from value_investment_agent.application.research import economic_review_bundle as bundle


@pytest.fixture
def addressed(retained, monkeypatch):
    root, research, analysis, persist_old = retained
    issuer = dict(venue="CNINFO", security_code="600519", issuer_name="贵州茅台",
                  organization_id="gssh0600519")
    research["issuer"] = "贵州茅台酒股份有限公司"
    originals = []
    for index, source in enumerate(research["sources"]):
        raw = f"synthetic original {index}; NOT a real filing".encode()
        digest = sha256(raw).hexdigest()
        path = root / "objects" / digest / "bytes.pdf"
        path.parent.mkdir(parents=True)
        path.write_bytes(raw)
        source.update(path=f"old/{index}.pdf", sha256=digest,
            source_url=f"https://static.cninfo.com.cn/finalpage/2026-08-15/{index+100}.PDF")
        originals.append(dict(id=f"official-{index}", kind="official_issuer_filing",
            location=source["source_url"], local_path=path.relative_to(root).as_posix(), sha256=digest,
            issuer_identity=deepcopy(issuer), report_period=source["report_period"],
            source_available_at="2026-10-08T12:00:00+00:00", retrieved_at="2026-10-08T12:00:00+00:00"))

    # Unit tests fake extraction only; real retained PDF extraction is verified
    # by the separately authorized read-only JS2 replay, not this fixture.
    def reader(path):
        half = b"original 1" in path.read_bytes()
        title = "2026年半年度报告" if half else "2025年年度报告"
        return SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:
            "贵州茅台酒股份有限公司" + title)])
    monkeypatch.setattr(pypdf, "PdfReader", reader)

    def persist():
        persist_old()
        raw = json.dumps(research).encode()
        digest = sha256(raw).hexdigest()
        path = root / "objects" / digest / "bytes.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        bridge = dict(id="bound-six-bridge", local_path=path.relative_to(root).as_posix(),
            sha256=digest, source_available_at="2026-10-08T12:00:00+00:00")
        analysis["financial_summary"] = dict(parent_distribution_capital_research_binding=
            dict(id=bridge["id"], path=bridge["local_path"], sha256=digest))
        analysis["source_catalog"] = [*deepcopy(originals), bridge]
        analysis["source_bindings"] = [dict(path=s["local_path"], sha256=s["sha256"])
            for s in analysis["source_catalog"]] + [analysis["review_binding"]["candidate_binding"]]
    persist()
    return root, research, analysis, persist


def replay(case):
    return bundle.build_current_economic_review_bundle(root=case[0], symbol="600519", now=NOW)


def test_addressed_six_bridges_no_write_or_approval(addressed):
    root, research, _, _ = addressed
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = replay(addressed)
    assert len(result["bridge_results"]) == 6
    assert all(x["difference_cny"] == "0" for x in result["bridge_results"])
    mapping = result["original_catalog_mapping"]
    assert mapping["version"] == bundle.MAPPING_VERSION
    assert mapping["frozen_bridge_bytes_changed"] is False
    assert mapping["originals"][0]["original_binding"]["path"] == research["sources"][0]["path"]
    assert mapping["originals"][0]["availability_evidence"][0]["source_available_at"].startswith("2026-10-08")
    assert result["historical_model_binding"] == research["model_binding"]
    assert result["future_distribution_capacity_cny"] is None
    assert result["forward_economic_status"] == "NOT_ESTABLISHED"
    assert result["primary_valuation_usable"] is result["economic_approval_granted"] is False
    assert result["bridge_results"][0]["reported_adjustment"] is None
    assert "/model_binding/future_retained_capital_return" in result["unknown_fields"]
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_exact_aliases_normalized(addressed):
    _, _, analysis, _ = addressed
    alias = deepcopy(analysis["source_catalog"][0]); alias["id"] = "official-alias"
    analysis["source_catalog"].append(alias)
    bridge_alias = deepcopy(analysis["source_catalog"][-2]); bridge_alias["id"] = "bridge-alias"
    analysis["source_catalog"].append(bridge_alias)
    result = replay(addressed)
    assert result["original_catalog_mapping"]["originals"][0]["catalog_source_ids"] == ["official-0", "official-alias"]


def test_same_file_lineage_alias_is_not_a_second_official_source(addressed):
    first = addressed[2]["source_catalog"][0]
    addressed[2]["source_catalog"].append(dict(id="lineage", kind="research_artifact",
        local_path=first["local_path"], location=first["local_path"], sha256=first["sha256"]))
    mapped = replay(addressed)["original_catalog_mapping"]["originals"][0]
    assert mapped["catalog_source_ids"] == ["lineage", "official-0"]
    assert mapped["official_source_ids"] == ["official-0"]


def test_hash_only_lineage_cannot_replace_official_identity(addressed):
    first = addressed[2]["source_catalog"][0]
    first.update(kind="research_artifact", location=first["local_path"])
    first.pop("issuer_identity")
    with pytest.raises(ValueError, match="official issuer source"):
        replay(addressed)


@pytest.mark.parametrize("fault", ["url", "issuer", "period", "hash", "missing", "second_file", "alias_url", "future"])
def test_catalog_conflicts_fail_closed(addressed, fault):
    root, _, analysis, _ = addressed
    first = analysis["source_catalog"][0]
    if fault == "url": first["location"] = "https://static.cninfo.com.cn/finalpage/2026-08-15/999.PDF"
    if fault == "issuer": first["issuer_identity"]["security_code"] = "600887"
    if fault == "period": first["report_period"] = "2024-01-01/2024-12-31"
    if fault == "hash": first["sha256"] = "f"*64
    if fault == "missing": (root/first["local_path"]).unlink()
    if fault in {"second_file", "alias_url"}:
        alias = deepcopy(first); alias["id"] = "conflicting-alias"
        if fault == "second_file":
            path = root/"second.pdf"; path.write_bytes((root/first["local_path"]).read_bytes())
            alias["local_path"] = "second.pdf"
        else: alias["location"] = "https://wrong.example/filing.pdf"
        analysis["source_catalog"].append(alias)
    if fault == "future": first["retrieved_at"] = "2027-01-01T00:00:00+00:00"
    with pytest.raises((ValueError, FileNotFoundError)):
        replay(addressed)


@pytest.mark.parametrize("fault", ["id", "path", "hash"])
def test_discovery_binding_must_match(addressed, fault):
    analysis = addressed[2]
    ref = analysis["financial_summary"]["parent_distribution_capital_research_binding"]
    ref[fault] = "wrong"
    with pytest.raises(ValueError, match="discovery"):
        replay(addressed)


@pytest.mark.parametrize("fault", ["issuer", "period", "amount", "version", "url"])
def test_resealed_invalid_bridge_is_not_trusted(addressed, fault):
    _, research, _, persist = addressed
    if fault == "issuer": research["issuer"] = "其他发行人"
    if fault == "period": research["sources"][0]["report_period"] = "2024-01-01/2024-12-31"
    if fault == "amount": research["parent_cash_bridges"][0]["cfo_cny"] = "21"
    if fault == "version": research["research_version"] = "invented-v2"
    if fault == "url": research["sources"][0]["source_url"] = "https://wrong.example/file.pdf"
    persist()
    with pytest.raises(ValueError):
        replay(addressed)


def test_raw_pdf_period_is_checked_without_catalog_period(addressed, monkeypatch):
    for source in addressed[2]["source_catalog"]: source.pop("report_period", None)
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda: "贵州茅台酒股份有限公司2024年年度报告")]))
    with pytest.raises(ValueError, match="PDF report period"):
        replay(addressed)


def test_assessment_period_requires_statement_context(addressed, monkeypatch):
    text = "贵州茅台酒股份有限公司成立于2013年4月12日，审核2026年6月30日财务报表"
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda: text)]))
    issuer = addressed[1]["issuer"]
    bundle._verify_original_period(addressed[0]/"original.pdf",
        dict(assessment_balance_date="2026-06-30"), issuer)
    with pytest.raises(ValueError, match="assessment period"):
        bundle._verify_original_period(addressed[0]/"original.pdf",
            dict(assessment_balance_date="2013-04-12"), issuer)


def test_content_mapping_requires_explicit_binding(addressed):
    addressed[2].pop("financial_summary")
    assert replay(addressed)["status"] == "NO_SUPPORTED_BOUND_BRIDGE"


def test_real_source_native_js2_sealed_analysis_readonly():
    location = os.environ.get("CONTENT_ADDRESSED_ECONOMIC_ROOT")
    if not location:
        pytest.skip("Explicit read-only Root research tree required")
    root = Path(location)
    directory = root / "runtime/source-native-workflow-verification/a51947ec2d1641fd9b23eaa05e72e893"
    receipt = json.loads((directory/"receipt.json").read_bytes())
    for ref in receipt["evidence_bindings"]:
        assert sha256((root/ref["path"]).read_bytes()).hexdigest() == ref["sha256"]
    analysis = json.loads((directory/"analysis.json").read_bytes())
    bindings = [r for r in analysis["source_bindings"] if set(r) == {"path", "sha256"}]
    before = {r["path"]: sha256((root/r["path"]).read_bytes()).hexdigest() for r in bindings}
    old_result = (directory/"economic-bundle.json").read_bytes()
    result = bundle._build_economic_review_bundle(root=root, analysis=analysis, now=datetime.now(timezone.utc))
    assert len(result["bridge_results"]) == 6
    assert all(row["difference_cny"] == "0.00" for row in result["bridge_results"])
    balances = {row["entity_scope"]: row["computed_closing_cny"] for row in result["bridge_results"]
                if row["kind"] == "equity" and row["period"] == "H1_2026"}
    assert balances == dict(issuer_parent_standalone="158148992327.71",
                           consolidated_attributable_to_parent="251253594419.50")
    assert result["primary_valuation_usable"] is result["approval_changed"] is False
    assert result["forward_economic_status"] == "NOT_ESTABLISHED"
    assert result["input_descriptor_sha256"] == receipt["input_descriptor_sha256"]
    assert len(result["original_catalog_mapping"]["originals"]) == 3
    assert old_result == (directory/"economic-bundle.json").read_bytes()
    assert before == {r["path"]: sha256((root/r["path"]).read_bytes()).hexdigest() for r in bindings}

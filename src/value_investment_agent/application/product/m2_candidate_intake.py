"""Open a real M2 lead as a blocked, source-bound research application run."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from value_investment_agent.disclosures import (
    download_disclosure_pdf, search_announcement_window, search_latest_reports,
)
from value_investment_agent.application.research.value_research_queue import build_value_research_queue
from value_investment_agent.m2_opportunity_discovery import discovery_receipt_from_payload
from value_investment_agent.research_application import ResearchApplicationService, ResearchRunSpec
from value_investment_agent.research_case import ResearchCase
from value_investment_agent.research_profile import PROFILES
from value_investment_agent.research_run_contract import ResearchIssuerIdentity, ResearchSourceDescriptor
from value_investment_agent.valuation_models.fcff import FinancialFacts

from .common import load_json_object, require_inside, sha256_file, write_new_json


CHINA = ZoneInfo("Asia/Shanghai")
ANNUAL_TITLE = re.compile(r"20\d{2}年年度报告(?:[（(](?:修订版|修订稿|更新版|更正版)[）)])?$")


def _verified_lead(root: Path, path: Path, expected_hash: str, symbol: str) -> dict:
    path = require_inside(root / "runtime", path, "M2 lead report")
    if sha256_file(path) != expected_hash:
        raise ValueError("M2 lead report hash mismatch")
    report = load_json_object(path, "M2 lead report")
    if (report.get("schema_version") != "value-discovery-product-v1"
            or report.get("action") != "no_order"
            or report.get("status") != "RESEARCH_LEADS_ONLY"):
        raise ValueError("M2 report is not a research-only discovery report")
    binding = report["receipt_binding"]
    receipt_path = require_inside(root / "runtime", root / binding["path"], "M2 receipt")
    if sha256_file(receipt_path) != binding["sha256"]:
        raise ValueError("M2 receipt hash mismatch")
    receipt = discovery_receipt_from_payload(load_json_object(receipt_path, "M2 receipt"))
    for ref in receipt.evidence_refs:
        source = require_inside(root / "runtime", root / ref.path, "M2 source")
        if sha256_file(source) != ref.sha256:
            raise ValueError(f"M2 source hash mismatch: {ref.id}")
    leads = [item for item in report["leads"] if item["symbol"] == symbol]
    if (len(leads) != 1 or symbol not in receipt.candidate_pool()
            or leads[0]["candidate_class"] != "LEAD"
            or leads[0]["research_state"] != "DISCOVERED"):
        raise ValueError("symbol is not one non-admitted M2 research lead")
    if sorted(leads[0]["channels"]) != sorted({r.channel for r in receipt.candidate_pool()[symbol]}):
        raise ValueError("M2 lead channels differ from receipt")
    return {"lead": leads[0], "report_path": path, "report_hash": expected_hash,
            "receipt": receipt}


def open_pending_m2_research(*, root: Path, queue_path: Path, queue_sha256: str,
                             symbol: str, profile_id: str, output_dir: Path) -> dict:
    root = root.resolve()
    if profile_id not in PROFILES:
        raise ValueError("new-company research requires an explicit supported profile")
    if profile_id != "mature_manufacturing":
        raise ValueError("UNSUPPORTED_MODEL: provisional intake only has an unverified FCFF facts contract")
    output_dir = require_inside(root / "runtime", output_dir, "pending M2 research")
    if output_dir.exists():
        raise FileExistsError("pending research output must be new")
    queue_path = require_inside(root / "runtime", queue_path, "M2 research queue")
    if sha256_file(queue_path) != queue_sha256:
        raise ValueError("M2 research queue hash mismatch")
    queue = load_json_object(queue_path, "M2 research queue")
    if (queue.get("schema_version") != "value-research-queue-v1"
            or queue.get("action") != "no_order"
            or queue.get("admission") != "RESEARCH_QUEUE_ONLY"):
        raise ValueError("M2 research queue scope mismatch")
    inputs = queue["inputs"]
    rebuilt = build_value_research_queue(root=root,
        report_path=root / inputs["report_path"], report_sha256=inputs["report_sha256"],
        receipt_path=root / inputs["receipt_path"], receipt_sha256=inputs["receipt_sha256"],
        budget=queue["budget"],
        previous_path=root / inputs["previous_queue_path"] if inputs.get("previous_queue_path") else None,
        previous_sha256=inputs.get("previous_queue_sha256"))
    if queue != rebuilt:
        raise ValueError("M2 research queue differs from replay")
    selected = [entry for entry in queue["entries"] if entry["symbol"] == symbol]
    if len(selected) != 1 or selected[0]["queue_status"] != "SELECTED_FOR_DATA_CHECK":
        raise ValueError("M2 symbol is not selected for data check")
    bound = _verified_lead(root, root / inputs["report_path"], inputs["report_sha256"], symbol)
    lead = bound["lead"]
    now = datetime.now(timezone.utc).astimezone(CHINA)
    reports = search_latest_reports(symbol, lead["company_name"])
    annual = [row for row in reports if ANNUAL_TITLE.search(str(row.get("announcementTitle") or ""))]
    if not annual:
        raise ValueError("no complete official annual report found")
    selected = max(annual, key=lambda row: int(row["announcementTime"]))
    source_url = urljoin("https://static.cninfo.com.cn/", selected["adjunctUrl"])
    parsed = urlparse(source_url)
    match = re.fullmatch(r"/finalpage/(20\d{2}-\d{2}-\d{2})/(\d+)\.PDF", parsed.path)
    if (parsed.scheme != "https" or parsed.hostname != "static.cninfo.com.cn" or not match
            or match[2] != str(selected["announcementId"])):
        raise ValueError("official annual report URL or identity invalid")
    published_at = datetime.fromtimestamp(int(selected["announcementTime"]) / 1000, timezone.utc)
    if published_at > now or published_at.astimezone(CHINA).date().isoformat() != match[1]:
        raise ValueError("official annual report publication date is invalid")
    output_dir.mkdir(parents=True)
    raw_pages = []

    def retain_raw(body: bytes, metadata: dict) -> None:
        path = output_dir / f"cninfo-index-page-{len(raw_pages) + 1}.json"
        path.write_bytes(body)
        if sha256_file(path) != metadata["sha256"]:
            raise ValueError("CNINFO index bytes changed while saving")
        raw_pages.append(dict(metadata, path=path.relative_to(root).as_posix()))

    index = search_announcement_window(symbol, match[1], match[1], lead["company_name"],
                                       raw_response_sink=retain_raw)
    matches = [row for row in index["announcements"]
               if str(row.get("announcementId")) == str(selected["announcementId"])]
    if (len(matches) != 1 or matches[0].get("secCode") != symbol
            or matches[0].get("orgId") != selected.get("orgId")
            or matches[0].get("adjunctUrl") != selected.get("adjunctUrl")
            or matches[0].get("announcementTitle") != selected.get("announcementTitle")
            or matches[0].get("announcementTime") != selected.get("announcementTime")):
        raise ValueError("annual report does not match retained official index")
    pdf_path = output_dir / "annual-report.pdf"
    pdf_hash = download_disclosure_pdf(source_url, pdf_path)
    if sha256_file(pdf_path) != pdf_hash:
        raise ValueError("annual report PDF hash mismatch")
    now = datetime.now(timezone.utc).astimezone(CHINA)
    period = datetime(int(ANNUAL_TITLE.search(selected["announcementTitle"]).group()[:4]),
                      12, 31).date()
    evidence_id = f"cninfo:{selected['announcementId']}"
    evidence = dict(id=evidence_id, sha256=pdf_hash, source_url=source_url,
                    path=pdf_path.relative_to(root).as_posix(),
                    available_at=now.isoformat(), published_at=published_at.isoformat())
    screening = dict(id="m2-discovery-report", sha256=bound["report_hash"],
                     path=bound["report_path"].relative_to(root).as_posix(),
                     available_at=now.isoformat())
    run_id = f"m2-pending-{symbol}-{now.strftime('%Y%m%dT%H%M%S')}"
    case = ResearchCase(symbol=symbol, name=lead["company_name"], as_of=now.date(),
        run_id=run_id, generated_at=now, research_version="m2-official-intake-v1",
        industry="待官方财报核验", investment_path="价值研究线索",
        thesis="待研究：四通道粗筛不能证明企业质量或低估。",
        return_driver="待研究", mispricing_hypothesis="待研究",
        financial_summary={"annual_report_period": period.isoformat(), "financial_facts_verified": False},
        positives=[], counter_evidence=[dict(kind="gap", text="财务口径、现金流和估值假设尚未核验",
                                             evidence_refs=[evidence_id])],
        thesis_breakers=[], next_events=[dict(kind="gap", text="等待财务与经济审核", evidence_refs=[])],
        evidence_status="PENDING_REVIEW", valuation_status="NOT_READY", research_status="PENDING_REVIEW",
        blockers=["financial_facts_unverified", "economic_model_unapproved",
                  "research_profile_unverified", "quote_date_unverified"],
        evidence_refs=[evidence, screening], quote_date=None, financial_period=period,
        missing_date_reasons={"quote_date": "M2 bulk snapshot has no verified provider trade date"})
    facts = FinancialFacts(symbol=symbol, as_of=now.date(), verified=False,
        evidence_refs=[evidence], blockers=["no verified financial metrics from annual PDF"],
        operating_inputs={})
    source = ResearchSourceDescriptor(id=evidence_id, kind="official_issuer_filing",
        location=source_url, sha256=pdf_hash, published_at=published_at, retrieved_at=now,
        parser_version="cninfo-annual-index-intake-v1",
        issuer_identity=ResearchIssuerIdentity(venue="CNINFO", security_code=symbol,
            issuer_name=selected["secName"], organization_id=selected["orgId"]))
    spec = ResearchRunSpec(run_id=run_id, symbol=symbol, profile_id=profile_id,
        research_case=case, facts=facts, as_of=now.date(), available_at=now,
        report_period=period, valuation_date=now.date(), computed_at=now,
        input_sources=(source,), rule_version="m2-official-intake-v1")
    outcome = ResearchApplicationService().run_company_research(spec)
    result = dict(schema_version="m2-pending-research-intake-v1", action="no_order",
        symbol=symbol, company_name=lead["company_name"], run_id=run_id,
        research_status="PENDING_REVIEW", application_status=outcome.status,
        profile_id=profile_id, profile_status="HYPOTHESIS_UNVERIFIED",
        issuer_identity_status=outcome.issuer_identity_status,
        valuation_status=outcome.valuation.status if outcome.valuation else "NOT_READY",
        decision_admitted=False, quote_admitted=False, human_approval=False,
        blockers=list(dict.fromkeys([*case.blockers, *outcome.blockers])),
        source_url=source_url, source_sha256=pdf_hash, official_index_pages=raw_pages,
        m2_report_binding={"path": screening["path"], "sha256": screening["sha256"]},
        m2_queue_binding={"path": queue_path.relative_to(root).as_posix(), "sha256": queue_sha256},
        research_case=json.loads(case.to_json()))
    write_new_json(output_dir / "pending-research.json", result)
    return result

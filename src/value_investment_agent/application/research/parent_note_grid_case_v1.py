"""Registered CNINFO identity for the note-grid case and native research adapter."""
from dataclasses import fields
from pathlib import Path

from . import parent_cash_task_receipt_v3 as legacy
from .parent_note_grid_sources_v1 import VERSION
from ...domain.research.issuer_identity import ISSUER_IDENTITY_VERIFIED, IssuerIdentityAssessment
from ...research_application import ResearchRunSpec
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report

# Additive case registration. The historical issuer registry is receipt-bound.
CNINFO_ISSUERS = {"600809": ("gssh0600809", "山西杏花村汾酒厂股份有限公司")}


def verified_descriptors(root, spec, case):
    symbol = spec["symbol"]
    registered = CNINFO_ISSUERS.get(symbol)
    if (spec.get("source_adapter_version") != VERSION
            or registered is None or registered[1] != spec["issuer_name"]
            or case.get("schema_version") != "m1-valuation-package-v2" or case.get("symbol") != symbol
            or case.get("profile_id") != "quality_compounder" or case.get("research_case", {}).get("symbol") != symbol):
        raise ValueError("NOTE_GRID_REGISTERED_CASE_IDENTITY_REQUIRED")
    expected = dict(venue="CNINFO", security_code=symbol, organization_id=registered[0], issuer_name=registered[1])
    owner_sources = spec["owner_sources"]
    if len(owner_sources) != 2 or len(case.get("sources", ())) != 2:
        raise ValueError("NOTE_GRID_TWO_DISTINCT_REPORTS_REQUIRED")
    annual, interim = (item["period_end"] for item in owner_sources)
    if not annual.endswith("-12-31") or interim != f"{int(annual[:4])+1}-06-30":
        raise ValueError("NOTE_GRID_CONSECUTIVE_FY_H1_REQUIRED")
    descriptors = []
    for item in owner_sources:
        record = load_retained_official_report(root=root, receipt_binding=item["receipt_binding"], symbol=symbol,
            issuer_name=spec["issuer_name"], period=item["period_end"])
        src = record["source"]
        rows = [row for idx in record["index_bindings"] for row in legacy._read(
            root, {k: idx[k] for k in ("path","sha256")})["announcements"]
            if str(row["announcementId"]) == record["source_id"].removeprefix("cninfo:")]
        if not rows or any(row.get("orgId") != registered[0] or row.get("secCode") != symbol or
                           "https://static.cninfo.com.cn/" + row["adjunctUrl"] != src["source_url"] for row in rows):
            raise ValueError("NOTE_GRID_INDEX_REGISTERED_ISSUER_MISMATCH")
        matches = [s for s in case["sources"] if s["id"] == record["source_id"]]
        if (len(matches) != 1 or matches[0].get("sha256") != src["sha256"]
                or matches[0].get("location") != src["source_url"]
                or matches[0].get("local_path") != src["path"] or matches[0].get("issuer_identity") != expected):
            raise ValueError("NOTE_GRID_CASE_ORIGINAL_IDENTITY_MISMATCH")
        descriptors.append(dict(id=record["source_id"], kind="official_issuer_filing", location=src["source_url"],
            local_path=src["path"], sha256=src["sha256"], retrieved_at=record["fetched_at"],
            parser_version=spec["source_adapter_version"], issuer_identity=expected))
    if len({r["id"] for r in descriptors}) != 2:
        raise ValueError("NOTE_GRID_TWO_DISTINCT_REPORTS_REQUIRED")
    refs = case["research_case"].get("evidence_refs", ())
    if sorted((ref["id"], ref["sha256"]) for ref in refs) != sorted(
        (source["id"], source["sha256"]) for source in descriptors
    ):
        raise ValueError("NOTE_GRID_CASE_SOURCE_REFS_MISMATCH")
    return descriptors


def _verify_valuation_sources(root, package):
    contract = package["source_contract"]
    if (contract.get("schema_version") != "parent-note-grid-task-receipt-v1"
            or contract.get("source_adapter_version") != VERSION):
        raise ValueError("NOTE_GRID_VALUATION_SOURCE_VERSION_REQUIRED")
    spec = legacy._read(root, contract["spec_binding"])
    case = legacy._read(root, contract["case_package_binding"])
    descriptors = verified_descriptors(root, spec, case)
    if package["symbol"] != spec["symbol"] or package["sources"] != descriptors:
        raise ValueError("NOTE_GRID_VALUATION_SOURCE_CLOSURE_MISMATCH")


def package_candidate(root, candidate, case_binding, task_id, head, completed, provenance, schema):
    spec, compiled = candidate["candidate_spec"], candidate["compiled"]
    case = legacy._read(root, case_binding)
    descriptors = verified_descriptors(root, spec, case)
    pins = [dict(path=r["local_path"], sha256=r["sha256"]) for r in descriptors]
    if any(pin not in compiled["source_bindings"] for pin in pins):
        raise ValueError("NOTE_GRID_COMPILED_SOURCE_CLOSURE_MISMATCH")
    case_data = dict(case["research_case"], quote_date=None, next_events=[])
    spec = dict(spec, owner_sources=pins, source_descriptors=descriptors, research_case=case_data,
                run_id="parent-cash-"+task_id, research_version=schema+"-"+head["sha256"],
                research_as_of=completed.astimezone(legacy.ZoneInfo("Asia/Shanghai")).date().isoformat(),
                computed_at=completed.isoformat())
    package = legacy._package(spec, compiled)
    package["descriptor_version"] = legacy.adapter.DESCRIPTOR_VERSION
    package["dependencies"].update(model_version=legacy.MODEL_VERSION, rule_version=schema)
    package["facts"].update(direct_owner_cash_contract=legacy.MODEL_VERSION, scenario_inputs=compiled["scenarios"])
    package["source_contract"].update(provenance, schema_version=schema,
        spec_sha256=provenance["spec_binding"]["sha256"], raw_source_bindings=compiled["source_bindings"])
    return package


class _RegisteredNoteGridRun(ResearchRunSpec):
    @property
    def issuer_identity_assessment(self):
        original = super().issuer_identity_assessment
        if original.status == ISSUER_IDENTITY_VERIFIED:
            return original
        if set(original.blockers) != {"issuer_identity_unverified:unregistered_issuer:" + self.symbol}:
            return original
        # This separate registration covers exactly the two authenticated CNINFO
        # originals supplied by package_candidate. Preserve every other refusal.
        registered = CNINFO_ISSUERS.get(self.symbol)
        if not registered or len(self.input_sources) != 2 or self.research_case.next_events:
            return original
        refs = {(row["id"], row["sha256"]) for row in self.facts.evidence_refs}
        case_refs = {(row["id"], row["sha256"]) for row in self.research_case.evidence_refs}
        sources = {(s.id, s.sha256) for s in self.input_sources}
        if len(sources) != 2 or refs != sources or case_refs != sources:
            return original
        for s in self.input_sources:
            identity = s.issuer_identity
            if (s.kind != "official_issuer_filing" or not s.location.startswith("https://static.cninfo.com.cn/finalpage/")
                    or not identity or identity.venue != "CNINFO" or identity.security_code != self.symbol
                    or (identity.organization_id, identity.issuer_name) != registered):
                return original
        return IssuerIdentityAssessment(ISSUER_IDENTITY_VERIFIED, (), tuple(s.id for s in self.input_sources))


def run_registered_research(root, package, completed):
    _verify_valuation_sources(root, package)
    adapter = legacy.adapter
    provenance = package["source_contract"]
    verified = verified_descriptors(root, legacy._read(root, provenance["spec_binding"]),
                                    legacy._read(root, provenance["case_package_binding"]))
    if package["sources"] != verified:
        raise ValueError("NOTE_GRID_PACKAGE_CERTIFICATE_INVALID")
    descriptor = adapter.build_direct_owner_cash_descriptor(package, root=root)
    if completed.utcoffset() is None or descriptor.point_in_time.computed_at > completed:
        raise ValueError("DIRECT_OWNER_V2_INPUT_NOT_AVAILABLE_AT_CLOCK")
    native = adapter.build_research_run_spec(descriptor)
    spec = _RegisteredNoteGridRun(**{f.name: getattr(native, f.name) for f in fields(native) if f.init})
    research = adapter.ResearchApplicationService(repository=adapter.DirectOwnerCashResearchRepository(),
        router=adapter.build_direct_owner_cash_router(), now_utc=lambda: completed)
    return research.run_company_research(spec), descriptor

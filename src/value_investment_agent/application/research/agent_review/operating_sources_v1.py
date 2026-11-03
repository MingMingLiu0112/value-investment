"""Verified public facts/excerpts for new operating research; no old predictions."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from .web_research import _binding, _raw, _json, MAX_JSON
from ....infrastructure.filings.first_research_fact_replay_v1 import replay_first_research_facts
from ....infrastructure.filings.pdf_text import extract_pages

REGISTRY = "config/current-operating-research-sources-v1.json"

def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")

def build_operating_source_context(*,root,symbol,now,binding=None):
    root=Path(root)
    if now.utcoffset() is None or re.fullmatch(r"[0-9]{6}",symbol or "") is None:
        raise ValueError("Invalid research source identity/cutoff")
    registry=None
    if binding is None:
        try:
            registry_raw=_raw(root/REGISTRY,65536)
        except FileNotFoundError:
            return _public_source_context(root=root,symbol=symbol,now=now)
        registry=_json(registry_raw)
        if (registry.get("schema_version")!="current-operating-research-sources-v1"
                or registry.get("action")!="no_order"):
            raise ValueError("OPERATING_SOURCE_REGISTRY_INVALID")
        if not isinstance(registry.get("cases"),dict):
            raise ValueError("OPERATING_SOURCE_REGISTRY_INVALID")
        if symbol not in registry["cases"]:
            return _public_source_context(root=root,symbol=symbol,now=now)
        binding=registry["cases"][symbol]["native_facts"]
    else:
        bound_payload=_json(_raw(_binding(root,binding,runtime_only=False),MAX_JSON))
        if bound_payload.get("version")=="value-debt-scope-enrichment-v1":
            return _public_source_context(root=root,symbol=symbol,now=now,binding=binding)
    replay=replay_first_research_facts(root=root,binding=binding,now=now)
    if replay["symbol"]!=symbol:
        raise ValueError("OPERATING_SOURCE_ISSUER_MISMATCH")
    manifest=_json(_raw(_binding(root,binding,runtime_only=False),MAX_JSON))
    source_map={s["id"]:s for s in manifest["sources"]}
    config_path=root/REGISTRY
    if registry is None and config_path.exists():
        registry=_json(_raw(config_path,65536))
    entry=(registry or {}).get("cases",{}).get(symbol,{})
    extras=entry.get("cash_excerpts",[])
    operating_extras=entry.get("operating_excerpts",[])
    if (extras or operating_extras) and entry.get("native_facts")!=binding:
        raise ValueError("SUPPLEMENT_SOURCE_BINDING_MISMATCH")
    if not isinstance(extras,list) or len(extras)>4:
        raise ValueError("SUPPLEMENT_EXCERPT_LIMIT")
    if not isinstance(operating_extras,list) or len(operating_extras)>3:
        raise ValueError("OPERATING_EXCERPT_LIMIT")
    evidence=[]
    for row in manifest["facts"]:
        source=source_map[row["source_id"]]
        evidence.append(dict(id=row["id"],source_id=row["source_id"],
            pdf_sha256=source["sha256"],available_at=source["available_at"],
            period=row["period_end"],scope=row["scope"],unit=row["unit"],
            value=row["value"],field=row["field"],physical_page=row["physical_page"],
            text=row["excerpt"],kind="VERIFIED_REPORTED_FACT",
            period_basis=("H1" if "半年度" in row["column_header"] else
                          "FY" if "年度" in row["column_header"] else "UNKNOWN")))
    # Finite official-section extraction, not an interpretation or an event crawler.
    # Full selected page is retained up to the bounded excerpt; the truncation is explicit.
    selected=[]
    for source in manifest["sources"]:
        path=_binding(root,{"path":source["path"],"sha256":source["sha256"]},runtime_only=False)
        before=hashlib.sha256(_raw(path,64*1024*1024)).hexdigest()
        if before!=source["sha256"]:raise ValueError("OPERATING_ORIGINAL_CHANGED")
        pages=extract_pages(path,limit=24)
        count=0
        for number,page in enumerate(pages,1):
            if not re.search(r"主要业务|经营情况|行业情况|核心竞争力|主要风险|管理层讨论",page):
                continue
            text=page[:1800]
            if len(text.strip())<40:continue
            identifier=source["id"]+":operating-page-"+str(number)
            evidence.append(dict(id=identifier,source_id=source["id"],pdf_sha256=source["sha256"],
                available_at=source["available_at"],period=source["report_period"],
                scope="ISSUER_REPORTED_NARRATIVE",unit="TEXT",text=text,
                physical_page=number,text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                excerpt_truncated=len(page)>1800,kind="OFFICIAL_EXCERPT_NOT_VERIFIED_CLAIM"))
            selected.append(identifier);count+=1
            if count==4:break
        if hashlib.sha256(_raw(path,64*1024*1024)).hexdigest()!=before:
            raise ValueError("OPERATING_ORIGINAL_CHANGED_DURING_EXTRACTION")
    for extra in extras:
        if (not isinstance(extra,dict) or set(extra)!={"source_id","physical_page","scope"}
                or type(extra["physical_page"]) is not int or not 1<=extra["physical_page"]<=300
                or extra["scope"] not in {"CONSOLIDATED_CASH_FLOW","PARENT_CASH_FLOW"}
                or extra["source_id"] not in source_map):
            raise ValueError("SUPPLEMENT_EXCERPT_CONTRACT_INVALID")
        source=source_map[extra["source_id"]];page_number=extra["physical_page"]
        path=_binding(root,{"path":source["path"],"sha256":source["sha256"]},runtime_only=False)
        if hashlib.sha256(_raw(path,64*1024*1024)).hexdigest()!=source["sha256"]:
            raise ValueError("SUPPLEMENT_ORIGINAL_CHANGED")
        pages=extract_pages(path,limit=page_number)
        if len(pages)<page_number:raise ValueError("SUPPLEMENT_PAGE_MISSING")
        text=pages[page_number-1]
        anchor=text.find("购建固定资产")
        if anchor<0:raise ValueError("SUPPLEMENT_CAPEX_ROW_MISSING")
        # A following parent-company table header must not relabel an earlier group row.
        nearby="\n".join(pages[max(0,page_number-3):page_number-1])+text[:anchor]
        headers=list(re.finditer(r"(合并|母公司)现金流量表",nearby))
        wanted="合并" if extra["scope"]=="CONSOLIDATED_CASH_FLOW" else "母公司"
        if not headers or headers[-1].group(1)!=wanted:
            raise ValueError("SUPPLEMENT_CASH_FLOW_SCOPE_NOT_PROVEN")
        header=nearby[headers[-1].start():headers[-1].start()+240]
        text=pages[page_number-1];flat=re.sub(r"\s+"," ",text)
        match=re.search(r"购建固定资产.*?支付的现金\s+[-\d,.]+\s+[-\d,.]+",flat)
        if match is None:raise ValueError("SUPPLEMENT_CAPEX_ROW_MISSING")
        excerpt=header+"\n"+match.group(0)
        evidence.append(dict(id=source["id"]+":cashflow-capex-"+str(page_number),
            source_id=source["id"],pdf_sha256=source["sha256"],available_at=source["available_at"],
            period=source["report_period"],scope=extra["scope"],unit="TEXT",text=excerpt,
            physical_page=page_number,text_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
            excerpt_truncated=True,kind="OFFICIAL_EXCERPT_NOT_VERIFIED_CLAIM"))
        if hashlib.sha256(_raw(path,64*1024*1024)).hexdigest()!=source["sha256"]:
            raise ValueError("SUPPLEMENT_ORIGINAL_CHANGED_DURING_EXTRACTION")
    for extra in operating_extras:
        if (not isinstance(extra,dict) or set(extra)!={"source_id","physical_page","start_marker","max_chars"}
                or not isinstance(extra["source_id"],str) or extra["source_id"] not in source_map
                or type(extra["physical_page"]) is not int or not 1<=extra["physical_page"]<=300
                or not isinstance(extra["start_marker"],str) or not extra["start_marker"].strip()
                or len(extra["start_marker"])>300
                or type(extra["max_chars"]) is not int or not 1<=extra["max_chars"]<=2000):
            raise ValueError("OPERATING_EXCERPT_CONTRACT_INVALID")
        source=source_map[extra["source_id"]];number=extra["physical_page"]
        path=_binding(root,{"path":source["path"],"sha256":source["sha256"]},runtime_only=False)
        if hashlib.sha256(_raw(path,64*1024*1024)).hexdigest()!=source["sha256"]:
            raise ValueError("OPERATING_ORIGINAL_CHANGED")
        pages=extract_pages(path,limit=number)
        if len(pages)<number:raise ValueError("OPERATING_EXCERPT_PAGE_MISSING")
        page=pages[number-1];marker=extra["start_marker"]
        if page.count(marker)!=1:raise ValueError("OPERATING_EXCERPT_MARKER_MISSING_OR_AMBIGUOUS")
        start=page.index(marker);text=page[start:start+extra["max_chars"]]
        identifier=source["id"]+":operating-excerpt-"+str(number)+":"+hashlib.sha256(marker.encode()).hexdigest()[:12]
        if any(row["id"]==identifier for row in evidence):raise ValueError("OPERATING_EXCERPT_DUPLICATE")
        evidence.append(dict(id=identifier,source_id=source["id"],pdf_sha256=source["sha256"],
            available_at=source["available_at"],period=source["report_period"],
            scope="ISSUER_REPORTED_NARRATIVE",unit="TEXT",text=text,physical_page=number,
            start_marker=marker,text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            excerpt_truncated=start+len(text)<len(page),kind="OFFICIAL_EXCERPT_NOT_VERIFIED_CLAIM"))
        if hashlib.sha256(_raw(path,64*1024*1024)).hexdigest()!=source["sha256"]:
            raise ValueError("OPERATING_ORIGINAL_CHANGED_DURING_EXTRACTION")
    if len(evidence)>100:raise ValueError("OPERATING_EVIDENCE_LIMIT")
    if not selected:raise ValueError("OPERATING_BUSINESS_EXCERPTS_MISSING")
    value=dict(schema_version="operating-source-context-v1",symbol=symbol,
        issuer_name=manifest["issuer_name"],as_of=now.isoformat(),
        financial_basis=manifest["financial_basis"],source_binding=binding,
        evidence=evidence,action="no_order",
        limitations=["Not a current-event completeness check","Historical facts are not normalized profit",
                     "Product revenue per tonne is a mix measure, not pure price change",
                     "Research investment is not interchangeable with income-statement research expense",
                     "No previous forecasts, thesis, final valuation or saved model response supplied"])
    # Cutoff is fixed in a task, so every read can cold-verify the same context.
    from ....infrastructure.filings import first_research_fact_replay_v1, pdf_text
    value["implementation_sha256"]={m.__name__:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (first_research_fact_replay_v1,pdf_text)}
    value["snapshot_fingerprint"]=hashlib.sha256(encode(value)).hexdigest()
    if len(encode(value))>100000:raise ValueError("OPERATING_SOURCE_CONTEXT_TOO_LARGE")
    return value


def _public_adoption(root, symbol, now, binding):
    """Resolve exact old result pins via existing checkpoints, never a newer symbol result."""
    from ....infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress
    progress=ValueEnrichmentProgress(root)
    if binding is None:
        adoption=progress.registered_adoption(symbol,cutoff=now)
        if adoption is None:
            raise ValueError("OPERATING_PUBLIC_ADOPTION_MISSING")
        return adoption
    paths=list(progress.directory.glob("*.json"))
    if len(paths)>4096:raise ValueError("OPERATING_PUBLIC_CHECKPOINT_LIMIT")
    matches=[]
    for path in paths:
        envelope=_json(_raw(path,MAX_JSON))
        payload=envelope["payload"]
        declared=payload.get("registered_adoption")
        if not declared or declared.get("symbol")!=symbol:continue
        # Select by the exact execution result, not latest completed_at or symbol alone.
        execution=_json(_raw(_binding(root,payload["execution_binding"]),MAX_JSON))
        if execution.get("result_binding")!=binding:continue
        checked=progress._load_checkpoint(path,payload["key"])
        stamp=datetime.fromisoformat(checked["completed_at"])
        if stamp.utcoffset() is None or stamp>now:
            raise ValueError("OPERATING_PUBLIC_ADOPTION_FUTURE")
        candidate=dict(checked["registered_adoption"],result_binding=binding)
        if candidate not in matches:matches.append(candidate)
    if len(matches)!=1:raise ValueError("OPERATING_PUBLIC_EXACT_ADOPTION_MISSING_OR_CONFLICT")
    return matches[0]


def _public_source_context(*,root,symbol,now,binding=None):
    """Facts-only adoption to the same D1 contract, without choosing models or writing sources."""
    from copy import deepcopy
    from decimal import Decimal
    from .. import value_enrichment_batch as batch
    from .. import value_evidence_enrichment_v1 as enrichment
    from ....infrastructure.screening import value_evidence_enrichment_v1 as extraction
    from ....infrastructure.filings import pdf_text
    adoption=_public_adoption(root,symbol,now,binding)
    if adoption.get("baseline_kind")!="AUTOMATIC_PUBLIC_FACTS_ONLY_V1":
        raise ValueError("OPERATING_PUBLIC_FACTS_ONLY_BASELINE_REQUIRED")
    pin=adoption["result_binding"]
    if binding is not None and pin!=binding:
        raise ValueError("OPERATING_PUBLIC_RESULT_BINDING_MISMATCH")
    # Explicit false must propagate through native verification; no global patch/cache write.
    checked=batch._verified_registered_adoption(root,symbol,now,binding=adoption,write_cache=False)
    if checked is None:raise ValueError("OPERATING_PUBLIC_ADOPTION_MISSING")
    summary,context,result=checked
    if (result.get("version")!="value-debt-scope-enrichment-v1"
            or result.get("action")!="no_order" or result.get("formal_eligibility") is not False
            or result.get("symbol")!=symbol or context["case"].symbol!=symbol
            or context["case"].financial_summary.get("context_origin")!="AUTOMATIC_PUBLIC_FACTS_ONLY_V1"):
        raise ValueError("OPERATING_PUBLIC_ADOPTION_IDENTITY_INVALID")
    source=result["source_extraction"]["identity"]["source"]
    if source["symbol"]!=symbol or result["period"]!=source["period"]:
        raise ValueError("OPERATING_PUBLIC_SOURCE_IDENTITY_INVALID")
    def clock(value):
        stamp=datetime.fromisoformat(value)
        if stamp.utcoffset() is None or stamp>now:
            raise ValueError("OPERATING_PUBLIC_SOURCE_FUTURE")
        return stamp
    clock(source["available_at"]);clock(result["evaluation_at"])
    pdf_pin={key:source[key] for key in ("path","sha256")}
    path=_binding(root,pdf_pin)
    if hashlib.sha256(_raw(path,64*1024*1024)).hexdigest()!=source["sha256"]:
        raise ValueError("OPERATING_ORIGINAL_CHANGED")
    evidence=[];refs=[deepcopy(pin),deepcopy(adoption["financial_export"]),pdf_pin]
    for point in result["adopted_points"]:
        meta=point.get("metadata") or {}
        value=point.get("value")
        if (point.get("symbol")!=symbol or point.get("period_label")!=source["period"]
                or point.get("validation_status")!="verified" or isinstance(value,bool)
                or not Decimal(str(value)).is_finite() or not meta.get("statement_scope")):
            raise ValueError("OPERATING_PUBLIC_FACT_INVALID")
        clock(point["available_at"])
        fact_refs=meta.get("evidence_refs",[])
        printed=[r for r in fact_refs if r.get("path")==source["path"] and r.get("sha256")==source["sha256"]]
        if not printed or any(type(r.get("page")) is not int or not 1<=r["page"]<=600
                              or not isinstance(r.get("excerpt"),str) or not r["excerpt"].strip() for r in printed):
            raise ValueError("OPERATING_PUBLIC_FACT_PAGE_MISSING")
        support=[]
        for ref in fact_refs:
            refpin={key:ref[key] for key in ("path","sha256")}
            _binding(root,refpin)
            if refpin not in refs:refs.append(refpin)
            support.append(dict(refpin,**{key:ref[key] for key in ("page","excerpt") if key in ref}))
        text="\n".join(r["excerpt"] for r in printed)
        evidence.append(dict(id=point["data_point_id"],source_id=point["source_id"],
            pdf_sha256=source["sha256"],available_at=point["available_at"],
            period=point["period_label"],scope=meta["statement_scope"],unit=point["unit"],
            value=value,field=point["field_name"],physical_page=printed[0]["page"],
            physical_pages=sorted({r["page"] for r in printed}),text=text[:1800],
            excerpt_truncated=len(text)>1800,kind="VERIFIED_ADOPTED_FINANCIAL_FACT",
            period_basis="FY",evidence_refs=support,
            verification_method=meta.get("verification_method"),
            derivation_formula=meta.get("derivation_formula"),
            assurance_basis=meta.get("assurance_basis")))
    if not evidence:raise ValueError("OPERATING_PUBLIC_ADOPTED_FACTS_EMPTY")
    pages=extract_pages(path,limit=24)
    selected=[]
    for number,page in enumerate(pages,1):
        if not re.search(r"主要业务|经营情况|行业情况|核心竞争力|主要风险|管理层讨论",page):continue
        text=page[:1800]
        if len(text.strip())<40:continue
        identifier=source["sha256"]+":operating-page-"+str(number)
        evidence.append(dict(id=identifier,source_id=source["sha256"],
            pdf_sha256=source["sha256"],available_at=source["available_at"],
            period=source["period"],scope="ISSUER_REPORTED_NARRATIVE",unit="TEXT",
            text=text,physical_page=number,text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            excerpt_truncated=len(page)>1800,kind="OFFICIAL_EXCERPT_NOT_VERIFIED_CLAIM"))
        selected.append(identifier)
        if len(selected)==4:break
    if not selected:raise ValueError("OPERATING_BUSINESS_EXCERPTS_MISSING")
    if len(evidence)>100:raise ValueError("OPERATING_EVIDENCE_LIMIT")
    if len({r["id"] for r in evidence})!=len(evidence):raise ValueError("OPERATING_EVIDENCE_DUPLICATE")
    # Recheck bytes after PDF decoding. A changed original/export/result cannot wash a task pin.
    for ref in refs:_binding(root,ref)
    value=dict(schema_version="operating-source-context-v1",symbol=symbol,
        issuer_name=context["case"].name,as_of=now.isoformat(),financial_basis=source["period"],
        source_binding=deepcopy(pin),source_bindings=refs,evidence=evidence,action="no_order",
        limitations=["Only natively revalidated adopted financial fields are supplied; financial completeness is not proven",
            "Derived adopted ratios are not printed report amounts",
            "Official narrative excerpts are issuer disclosures, not independently verified economic claims",
            "First 24 pages, at most four bounded operating/risk excerpts; not complete business or current-event coverage",
            "No model, normalized profit, future assumptions, valuation or G3 approval is inferred",
            "No previous forecasts, thesis, final valuation or saved model response supplied"])
    modules=(batch,enrichment,extraction,pdf_text)
    value["implementation_sha256"]={m.__name__:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in modules}
    value["snapshot_fingerprint"]=hashlib.sha256(encode(value)).hexdigest()
    if len(encode(value))>100000:raise ValueError("OPERATING_SOURCE_CONTEXT_TOO_LARGE")
    return value

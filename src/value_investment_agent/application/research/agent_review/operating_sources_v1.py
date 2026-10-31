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
    if binding is None:
        registry=_json(_raw(root/REGISTRY,65536))
        if (registry.get("schema_version")!="current-operating-research-sources-v1"
                or registry.get("action")!="no_order"):
            raise ValueError("OPERATING_SOURCE_REGISTRY_INVALID")
        binding=registry["cases"][symbol]["native_facts"]
    replay=replay_first_research_facts(root=root,binding=binding,now=now)
    if replay["symbol"]!=symbol:
        raise ValueError("OPERATING_SOURCE_ISSUER_MISMATCH")
    manifest=_json(_raw(_binding(root,binding,runtime_only=False),MAX_JSON))
    source_map={s["id"]:s for s in manifest["sources"]}
    evidence=[]
    for row in manifest["facts"]:
        source=source_map[row["source_id"]]
        evidence.append(dict(id=row["id"],source_id=row["source_id"],
            pdf_sha256=source["sha256"],available_at=source["available_at"],
            period=row["period_end"],scope=row["scope"],unit=row["unit"],
            value=row["value"],field=row["field"],physical_page=row["physical_page"],
            text=row["excerpt"],kind="VERIFIED_REPORTED_FACT"))
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
    if not selected:raise ValueError("OPERATING_BUSINESS_EXCERPTS_MISSING")
    value=dict(schema_version="operating-source-context-v1",symbol=symbol,
        issuer_name=manifest["issuer_name"],as_of=now.isoformat(),
        financial_basis=manifest["financial_basis"],source_binding=binding,
        evidence=evidence,action="no_order",
        limitations=["Not a current-event completeness check","Historical facts are not normalized profit",
                     "No previous forecasts, thesis, final valuation or saved model response supplied"])
    # Cutoff is fixed in a task, so every read can cold-verify the same context.
    from ....infrastructure.filings import first_research_fact_replay_v1, pdf_text
    value["implementation_sha256"]={m.__name__:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (first_research_fact_replay_v1,pdf_text)}
    value["snapshot_fingerprint"]=hashlib.sha256(encode(value)).hexdigest()
    if len(encode(value))>100000:raise ValueError("OPERATING_SOURCE_CONTEXT_TOO_LARGE")
    return value

"""Finite source-row replay for a first research input, never financial approval.

This verifies configured native row locators against original PDF bytes. It is
not a universal financial extractor or an automatic company classifier.
"""
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .pdf_text import extract_pages
from .pdfium_runtime import serialized_pdfium

SCHEMA = "first-research-native-facts-v1"
LABELS = {
    "revenue": ("营业收入", "营业总收入"),
    "cost": ("营业成本",),
    "surcharges": ("税金及附加",),
    "selling": ("销售费用",),
    "admin": ("管理费用",),
    "research": ("研发费用",),
    "pre_tax_profit": ("利润总额",),
    "tax": ("所得税费用",),
    "parent_profit": ("归属于母公司", "归属于上市公司股东的净利润"),
    "ex_parent_profit": ("扣除非经常性损益",),
    "start_book_equity": ("归属于母公司",),
    "ordinary_shares": ("总股数", "总股本", "股份总数"),
    "parent_cash": ("货币资金", "现金及现金等价物余额"),
    "parent_retained_profit": ("未分配利润",),
    "parent_cash_equivalents": ("期末现金及现金等价物余额",),
    "parent_dividend_payable": ("应付股利",),
    "depreciation": ("折旧",),
    "amortization": ("摊销",),
    "parent_investment_cash": ("取得投资收益收到的现金",),
    "parent_cfo": ("经营活动产生的现金流量净额",),
    "parent_capex": ("购建固定资产", "购建长期资产"),
}
MONEY = re.compile(r"(?<![\d.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)")
INTEGER = re.compile(r"(?<![\d.])(?:\d{1,3}(?:,\d{3})+|\d+)(?![\d.])")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _space(text):
    return re.sub(r"\s+", " ", text.replace("－", "-")).strip()


def _time(value, now):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("Native fact source has an invalid/future timestamp")
    return stamp


def _inside(root, name):
    if (not isinstance(name,str) or "\\" in name or ":" in name
            or Path(name).is_absolute() or ".." in Path(name).parts
            or Path(name).parts[0] not in {"runtime","config","artifacts","docs"}
            or any(word in name.lower() for word in ("private","secret","credential",".env"))):
        raise ValueError("Native fact requires a public canonical relative path")
    path = root / name
    if path.resolve() != path or not path.is_relative_to(root):
        raise ValueError("Native fact cannot redirect outside its public root")
    return path


def _raw(root, binding):
    if not isinstance(binding,dict) or not re.fullmatch(r"[0-9a-f]{64}",str(binding.get("sha256",""))):
        raise ValueError("Native fact binding requires a SHA256")
    path = _inside(root,binding["path"])
    raw = path.read_bytes()
    if len(raw)>32*1024*1024 or _hash(raw)!=binding["sha256"]:
        raise ValueError("Native fact source hash/size mismatch")
    return path,raw


@serialized_pdfium
def _native_column(path, page_number, amount, geometry):
    """Resolve one explicit amount to a native PDF column; blank is never zero."""
    import pypdfium2 as pdfium
    if (not isinstance(geometry,dict) or set(geometry)!={"header_page","labels"}
            or type(geometry["header_page"]) is not int
            or not isinstance(geometry["labels"],list) or len(geometry["labels"])!=2):
        raise ValueError("Native incomplete comparative row needs exact column geometry")
    document=pdfium.PdfDocument(path)
    try:
        def span(page_no,text):
            if not 1<=page_no<=len(document):
                raise ValueError("Native column page invalid")
            page=document[page_no-1]
            try:
                native=page.get_textpage()
                try:
                    content=native.get_text_range()
                    if content.count(text)!=1:
                        raise ValueError("Native PDF column locator is missing or ambiguous")
                    search=native.search(text)
                    try:
                        hit=search.get_next()
                        if hit is None or search.get_next() is not None:
                            raise ValueError("Native PDF character locator is not unique")
                        start,count=hit
                    finally:search.close()
                    boxes=[native.get_charbox(i) for i in range(start,start+count)]
                    return (min(b[0] for b in boxes)+max(b[2] for b in boxes))/2
                finally:native.close()
            finally:page.close()
        centers=[span(geometry["header_page"],label) for label in geometry["labels"]]
        if not centers[0]<centers[1]:
            raise ValueError("Native PDF column headers are reversed")
        x=span(page_number,amount)
        return 0 if x<(centers[0]+centers[1])/2 else 1
    finally:document.close()


def replay_first_research_facts(*, root: Path, binding: dict, now: datetime) -> dict:
    root=Path(root).resolve()
    if now.utcoffset() is None:
        raise ValueError("Native fact cutoff must have timezone")
    _,raw=_raw(root,binding)
    spec=json.loads(raw)
    if (spec.get("schema_version")!=SCHEMA or spec.get("action")!="no_order"
            or not re.fullmatch(r"[0-9]{6}",str(spec.get("symbol","")))
            or not isinstance(spec.get("issuer_name"),str) or not spec["issuer_name"].strip()):
        raise ValueError("Native fact manifest identity mismatch")
    basis=date.fromisoformat(spec["financial_basis"])
    _time(spec["generated_at"],now)
    if basis>now.date() or not 1<=len(spec.get("sources",[]))<=4 or not 1<=len(spec.get("facts",[]))<=150:
        raise ValueError("Native fact manifest bounds/period invalid")
    pages_by_id={}; sources={}
    for source in spec["sources"]:
        ident=source["id"]
        if ident in sources or source.get("symbol")!=spec["symbol"] or source.get("issuer_name")!=spec["issuer_name"]:
            raise ValueError("Native source has wrong/duplicate issuer")
        _time(source["available_at"],now)
        if date.fromisoformat(source["published_date"]) > now.date():
            raise ValueError("Native source publication is future")
        report_date=date.fromisoformat(source["report_period"])
        suffix=source["report_period"][4:]
        expected_title=(f"{report_date.year}年半年度报告" if suffix=="-06-30"
                        else f"{report_date.year}年年度报告" if suffix=="-12-31" else None)
        if expected_title is None or expected_title not in re.sub(r"\s+","",source["report_title"]):
            raise ValueError("Native report title and full reporting date differ")
        if date.fromisoformat(source["report_period"])>basis:
            raise ValueError("Native source report is beyond financial basis")
        url=urlsplit(source["source_url"])
        if url.scheme!="https" or url.hostname not in {"static.cninfo.com.cn","www.cninfo.com.cn","www.sse.com.cn","www.szse.cn"}:
            raise ValueError("Native source requires a registered official URL")
        if source.get("organization_id") is not None:
            if not source.get("identity_index_binding") or not source.get("identity_available_at"):
                raise ValueError("Native issuer organization requires a bound official index")
            _time(source["identity_available_at"],now)
            _,index_raw=_raw(root,source["identity_index_binding"])
            index=json.loads(index_raw)
            matches=[row for row in index.get("announcements",[])
                     if row.get("secCode")==spec["symbol"]]
            if not matches or {row.get("orgId") for row in matches}!={source["organization_id"]}:
                raise ValueError("Native issuer organization differs from official index")
            short_names={re.sub(r"<[^>]*>","",row.get("secName","")).strip() for row in matches}
            if any(not name or name not in source["issuer_name"] for name in short_names):
                raise ValueError("Native official index name differs from original issuer")
        path,_=_raw(root,source)
        pages=extract_pages(path)
        head="".join(pages[:8])
        codes=set(re.findall(r"(?:公司|证券|股票)\s*代码\s*[:：]?\s*([0-9]{6})(?!\d)",head))
        compact=re.sub(r"\s+","",head)
        if codes!={spec["symbol"]} or spec["issuer_name"] not in compact or source["report_title"] not in compact:
            raise ValueError("Native original issuer/report identity mismatch")
        pages_by_id[ident]=pages;sources[ident]=source
    facts=[];seen=set()
    for fact in spec["facts"]:
        ident= fact["id"];field=fact["field"]
        if ident in seen or field not in LABELS or fact["source_id"] not in sources:
            raise ValueError("Native fact identity/field is invalid")
        seen.add(ident)
        source=sources[fact["source_id"]];pages=pages_by_id[fact["source_id"]]
        page=fact["physical_page"]
        if type(page) is not int or not 1<=page<=len(pages):
            raise ValueError("Native fact physical page invalid")
        excerpt=fact["excerpt"];label=fact["label"]
        if not isinstance(excerpt,str) or not 1<=len(excerpt)<=2500 or not isinstance(label,str):
            raise ValueError("Native fact row locator invalid")
        normalized=_space(excerpt);original=_space(pages[page-1])
        if original.count(normalized)!=1 or _space(label) not in normalized:
            raise ValueError("Native fact excerpt/row is absent or ambiguous")
        if not any(token in re.sub(r"\s+","",label) for token in LABELS[field]):
            raise ValueError("Native fact semantic label mismatch")
        if field=="ex_parent_profit" and "扣除非经常性损益" not in re.sub(r"\s+","",label):
            raise ValueError("Native adjusted profit must name the disclosed metric")
        if field=="parent_profit" and "扣除非经常性损益" in re.sub(r"\s+","",label):
            raise ValueError("Native ordinary and adjusted profit cannot be mixed")
        if field=="start_book_equity" and ("权益" not in label or fact["scope"]!="consolidated_parent_equity"):
            raise ValueError("Native book equity must exclude minority ownership")
        if field.startswith("parent_") and field not in {"parent_profit"} and fact["scope"] not in {"parent","parent_cash","parent_retained_profit"}:
            raise ValueError("Native parent cash/retained amounts require parent scope")
        if not isinstance(fact.get("scope"),str) or not fact["scope"]:
            raise ValueError("Native fact scope is required")
        period=date.fromisoformat(fact["period_end"])
        if period>basis or period>date.fromisoformat(source["report_period"]):
            raise ValueError("Native fact period is future/mismatched")
        column=fact["column_index"];periods=fact["column_periods"]
        if type(column) is not int or not isinstance(periods,list) or not 0<=column<len(periods) or periods[column]!=fact["period_end"]:
            raise ValueError("Native fact comparative column is not bound to its period")
        # A source-row header is rechecked, never a caller-provided amount alone.
        header=fact["column_header"]
        header_pages=fact.get("header_pages",[page])
        if (not isinstance(header_pages,list) or not header_pages or len(header_pages)>3
                or header_pages!=list(range(header_pages[0],page+1))
                or header_pages[0]<max(1,page-2)
                or any(type(n) is not int or not 1<=n<=len(pages) for n in header_pages)):
            raise ValueError("Native fact header pages invalid")
        context=_space(" ".join(pages[n-1] for n in header_pages))
        if not header or _space(header) not in context:
            raise ValueError("Native comparative header is not in the original")
        marker=fact["scope_marker"]
        excerpt_at=context.find(normalized)
        if not marker or excerpt_at<0 or _space(marker) not in context[:excerpt_at]:
            raise ValueError("Native statement scope marker is absent")
        if field.startswith("parent_") and field!="parent_profit" and "母公司" not in marker:
            raise ValueError("Native parent cash cannot come from a consolidated table")
        kind = fact.get("number_kind","money")
        if kind=="shares":
            expected_periods=[source["report_period"]]
        else:
            year=int(source["report_period"][:4])
            suffix=source["report_period"][4:]
            balance=field in {"start_book_equity","parent_cash","parent_retained_profit","parent_dividend_payable"}
            previous=f"{year-1}-12-31" if balance else f"{year-1}{suffix}"
            expected_periods=[source["report_period"],previous]
            if len(periods)==3 and field in {"parent_profit","ex_parent_profit"} and suffix=="-12-31":
                expected_periods.append(f"{year-2}-12-31")
        if periods!=expected_periods:
            raise ValueError("Native fact comparative periods do not match reporting convention")
        header_years=list(dict.fromkeys(re.findall(r"20[0-9]{2}",header)))
        if header_years and header_years!=[v[:4] for v in periods]:
            raise ValueError("Native original header year order differs from selected periods")
        explicit_dates=[date(int(y),int(m),int(d)).isoformat() for y,m,d in
            re.findall(r"(20[0-9]{2})\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日",header)]
        if explicit_dates and list(dict.fromkeys(explicit_dates))!=periods:
            raise ValueError("Native original header full dates differ from selected periods")
        period_basis="EXPLICIT_COMPARATIVE_PERIODS"
        period_evidence=None
        if not header_years and kind!="shares":
            if balance and "期末余额" in header and "期初余额" in header:
                if header.index("期末余额")>=header.index("期初余额"):
                    raise ValueError("Native ending/opening balance column order is invalid")
                section=context[context.rfind(_space(marker),0,excerpt_at):excerpt_at]
                dates=[date(int(y),int(m),int(d)).isoformat() for y,m,d in
                    re.findall(r"(20[0-9]{2})\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日",section)]
                if dates and dates[0]!=source["report_period"]:
                    raise ValueError("Native ending/opening balances lack matching statement date")
                if not dates:
                    # Relative columns are tied to the primary parent balance, not
                    # any later adjusted/comparative note bearing the same title.
                    if marker not in {"母公司资产负债表","合并资产负债表"}:
                        raise ValueError("Relative balance columns require a primary statement heading")
                    first_heading=None
                    first_heading_text=None
                    primary_consolidated=None
                    for number,page_text in enumerate(pages,1):
                        for line in page_text.splitlines():
                            clean=re.sub(r"\s+","",line)
                            if re.fullmatch(r"(?:[0-9一二三四五六七八九十]+[、.．])?"+re.escape(marker),clean):
                                if first_heading is None:
                                    first_heading=number
                                    first_heading_text=_space(line)
                            if re.fullmatch(r"(?:[0-9一二三四五六七八九十]+[、.．])?合并资产负债表",clean):
                                if primary_consolidated is None:primary_consolidated=number
                    if first_heading not in header_pages or primary_consolidated is None:
                        raise ValueError("Relative balance row is not within the primary financial statement")
                    first_at=context.find(first_heading_text)
                    expected_at=first_at+first_heading_text.find(marker) if first_at>=0 else -1
                    if expected_at<0 or context[:excerpt_at].rfind(marker)!=expected_at:
                        raise ValueError("Relative balance row follows a subsequent duplicate statement heading")
                    related=" ".join(pages[primary_consolidated-1:min(len(pages),primary_consolidated+1)])
                    at=related.find("合并资产负债表")
                    before_rows=related[at:at+800]
                    primary_dates=[date(int(y),int(m),int(d)).isoformat() for y,m,d in
                        re.findall(r"(20[0-9]{2})\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日",before_rows)]
                    if not primary_dates or primary_dates[0]!=source["report_period"]:
                        raise ValueError("Related primary balance does not prove the report cutoff")
                    if any(t in section for t in ("调整表","调整后","比较附表","模拟资产")):
                        raise ValueError("Adjusted/comparative balances cannot inherit the primary period")
                    period_basis="DERIVED_FROM_REPORT_PERIOD_CONVENTION"
                    period_evidence=dict(physical_page=primary_consolidated,
                        scope_marker="合并资产负债表",period_end=primary_dates[0])
            elif not (any(t in header for t in ("本期","本报告期")) and
                      any(t in header for t in ("上期","上年同期"))):
                raise ValueError("Native original comparative header lacks period identity")
        allowed_scope = ({"issued_ordinary_shares"} if field=="ordinary_shares" else
            {"consolidated_parent_equity"} if field=="start_book_equity" else
            {"consolidated_parent"} if field in {"parent_profit","ex_parent_profit"} else
            {"parent","parent_cash","parent_retained_profit"} if field.startswith("parent_") else {"consolidated"})
        if fact["scope"] not in allowed_scope:
            raise ValueError("Native fact scope is not applicable to its financial field")
        headings=("合并资产负债表","母公司资产负债表","合并利润表","母公司利润表","合并现金流量表","母公司现金流量表")
        found=[(context[:excerpt_at].rfind(h),h) for h in headings if h in context[:excerpt_at]]
        canonical=[heading for heading in headings if heading in marker]
        if len(canonical)>1:
            raise ValueError("Native scope marker has conflicting statement headings")
        if found and canonical and max(found)[1]!=canonical[0]:
            raise ValueError("Native fact row follows a different statement-scope heading")

        unit=fact["unit"]
        if kind=="money":
            prefix=context[:excerpt_at]
            units=re.findall(r"(?:单位\s*[:：]\s*|金额单位(?:为|[:：])\s*)(?:人民币)?(美元|港元|人民币元|万元|千元|元)",prefix)
            row_units=re.findall(r"[（(](人民币元|美元|港元|万元|千元|元)[）)]",re.sub(r"\s+","",label))
            native_unit=row_units[-1] if row_units else (units[-1] if units else None)
            if native_unit not in {"元","人民币元"}:
                raise ValueError("Native money original unit is missing or unsupported: "+ident)
            currencies=re.findall(r"币种\s*[:：]\s*([^\s，,；;。]+)",prefix)
            if currencies and currencies[-1] not in {"人民币","CNY","RMB"}:
                raise ValueError("Native current table explicitly declares non-CNY currency")
            report_text=re.sub(r"\s+",""," ".join(pages))
            compact_prefix=re.sub(r"\s+","",prefix)
            cny=("币种：人民币" in compact_prefix or "币种:人民币" in compact_prefix or "人民币元" in compact_prefix or
                 "以人民币为记账本位币" in report_text or "记账本位币为人民币" in report_text or
                 "本财务报表以人民币列报" in report_text)
            if not cny:
                raise ValueError("Native money original currency is not established as CNY")
        if (kind not in {"money","shares"} or unit!=("shares" if kind=="shares" else "CNY")
                or (field=="ordinary_shares")!=(kind=="shares")):
            raise ValueError("Native fact currency/share unit mismatch")
        tail=excerpt[excerpt.index(label)+len(label):]
        values=(INTEGER if kind=="shares" else MONEY).findall(tail)
        comparative_missing=[]
        if len(values)!=len(periods):
            geometry=fact.get("column_geometry")
            if (kind!="money" or len(values)!=1 or len(periods)!=2 or not geometry
                    or geometry["header_page"] not in header_pages
                    or not all(label in header for label in geometry["labels"])
                    or _native_column(_inside(root,source["path"]),page,values[0],geometry)!=column):
                raise ValueError("Native fact row must have its exact explicit comparative columns")
            selected=values[0]
            comparative_missing=[period for i,period in enumerate(periods) if i!=column]
        else:selected=values[column]
        value=Decimal(selected.replace(",",""))
        if not isinstance(fact["value"],str):
            raise ValueError("Native fact value must be an explicit Decimal string")
        try:
            expected=Decimal(fact["value"])
        except InvalidOperation as error:
            raise ValueError("Native fact value is not a decimal") from error
        if not value.is_finite() or value!=expected or (kind=="shares" and (value<=0 or value!=value.to_integral_value())):
            raise ValueError("Native fact declared value differs from original row")
        facts.append(dict(fact,value=str(value),missing_comparative_periods=comparative_missing,period_basis=period_basis,period_evidence=period_evidence,classification="REPORTED_NATIVE_ROW_NOT_ECONOMIC_ADMISSION",
            source_sha256=source["sha256"],available_at=source["available_at"]))
    # Protect against replacement during PDF parsing.
    for source in sources.values():
        _raw(root,source)
        if source.get("identity_index_binding"):_raw(root,source["identity_index_binding"])
    _raw(root,binding)
    fingerprint=_hash(json.dumps(dict(manifest=binding,facts=facts,
        implementation=_hash(Path(__file__).read_bytes())),ensure_ascii=False,sort_keys=True,
        separators=(",",":")).encode("utf-8"))
    return dict(schema_version=SCHEMA,symbol=spec["symbol"],issuer_name=spec["issuer_name"],
        financial_basis=spec["financial_basis"],sources=list(sources.values()),
        facts=facts,by_id={row["id"]:row for row in facts},input_fingerprint=fingerprint,
        action="no_order",formal_eligibility=False,strict_historical_pit=False)

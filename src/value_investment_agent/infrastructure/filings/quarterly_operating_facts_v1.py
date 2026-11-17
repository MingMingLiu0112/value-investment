"""Bounded consolidated nine-month statements; no normalization or equity-cash claim."""
from datetime import date
from decimal import Decimal, localcontext
import re
from .native_capital_observation_v1 import _compact, _raw_excerpt

VERSION = "quarterly-operating-facts-v1"
MONEY = r"(-?[0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})"
FIELDS = {
    "revenue": "其中:营业收入", "cost": "其中:营业成本",
    "surcharges": "税金及附加", "selling": "销售费用", "admin": "管理费用",
    "research": "研发费用", "finance": "财务费用",
    "pre_tax_profit": "四、利润总额", "tax": "减:所得税费用",
    "group_profit": "五、净利润", "parent_profit": "1.归属于母公司股东的净利润",
    "nci": "2.少数股东损益",
}
CASH_FIELDS = {"cfo": "经营活动产生的现金流量净额",
    "cash_capex": "购建固定资产、无形资产和其他长期资产支付的现金",
    "customer_cash": "销售商品、提供劳务收到的现金",
    "supplier_cash": "购买商品、接受劳务支付的现金"}

def parse_quarterly_operating_facts(pages, *, symbol, currency_basis):
    """currency_basis must be independently source-verified by the caller.

    The report says yuan; retained explicit reporting-currency evidence is
    required rather than guessing currency from an A-share code.
    """
    if (not isinstance(pages,list) or not 1<=len(pages)<=80
            or any(not isinstance(p,str) for p in pages) or sum(map(len,pages))>1_000_000
            or not isinstance(symbol,str) or not re.fullmatch("[0-9]{6}",symbol)):
        raise ValueError("BOUNDED_QUARTERLY_ORIGINAL_REQUIRED")
    if (not isinstance(currency_basis,dict) or currency_basis.get("currency")!="CNY"
            or not isinstance(currency_basis.get("evidence_refs"),list) or not currency_basis["evidence_refs"]):
        raise ValueError("VERIFIED_REPORTING_CURRENCY_BASIS_REQUIRED")
    texts=[_compact(p) for p in pages]
    codes=set(re.findall(r"(?:证券|股票)代码:?([0-9]{6})(?![0-9])",texts[0]))
    title=re.search(r"(20[0-9]{2})年(?:第三|三)季度报告",texts[0])
    if codes!={symbol} or not title or "摘要" in texts[0]:
        raise ValueError("FULL_QUARTERLY_ISSUER_REQUIRED")
    year=int(title[1])
    # Repeated page headers are allowed; conflicting report years are not.
    title_pattern = r"(20[0-9]{2})年(?:第三|三)季度报告"
    if set(re.findall(title_pattern, "".join(texts))) != {str(year)}:
        raise ValueError("QUARTERLY_TITLE_PERIOD_CONFLICT")
    # Supported layout supplies a dated consolidated balance sheet. Do not
    # assign the cover year to undated or contradictory financial statements.
    statement_dates = re.findall(
        r"合并资产负债表(?:编制单位:[^0-9]{1,120})?"
        r"(20[0-9]{2})年([0-9]{1,2})月([0-9]{1,2})日", "".join(texts))
    if len(statement_dates) != 1:
        raise ValueError("QUARTERLY_STATEMENT_PERIOD_REQUIRED_OR_AMBIGUOUS")
    if date(*map(int, statement_dates[0])) != date(year, 9, 30):
        raise ValueError("QUARTERLY_STATEMENT_PERIOD_CONFLICT")
    start="2、合并年初到报告期末利润表"
    stop="3、合并年初到报告期末现金流量表"
    joined="".join(texts)
    if joined.count(start)!=1 or joined.count(stop)!=1:
        raise ValueError("EXACT_CONSOLIDATED_YTD_STATEMENTS_REQUIRED")
    income=joined.split(start)[1].split(stop)[0]
    cash=joined.split(stop)[1].split("(二)")[0]
    for section in (income,cash):
        if "单位:元项目本期发生额上期发生额" not in section:
            raise ValueError("EXPLICIT_YTD_COLUMNS_UNIT_REQUIRED")
    result={}
    for field,label in {**FIELDS,**CASH_FIELDS}.items():
        section=income if field in FIELDS else cash
        pattern=re.escape(label)+r"(?:\([^)]{0,60}\))?"+MONEY+MONEY
        matches=list(re.finditer(pattern,section))
        if len(matches)!=1:
            raise ValueError("QUARTERLY_FIELD_MISSING_OR_AMBIGUOUS:"+field)
        match=matches[0]
        locations=[(i,p) for i,p in enumerate(texts,1) if match[0] in p]
        if len(locations)!=1:
            raise ValueError("EXACT_ORIGINAL_ROW_LOCATION_REQUIRED:"+field)
        page=locations[0][0]
        result[field]=dict(current=str(Decimal(match[1].replace(",",""))),
            comparative=str(Decimal(match[2].replace(",",""))),physical_page=page,
            excerpt=_raw_excerpt(pages[page-1],match[0]),currency="CNY",
            scope="consolidated_parent" if field=="parent_profit" else "consolidated",
            period_basis="YTD_9M",kind="REPORTED_FACT")
    with localcontext() as ctx:
        ctx.prec=48
        for column in ("current","comparative"):
            amount=lambda key:Decimal(result[key][column])
            if (amount("pre_tax_profit")-amount("tax")!=amount("group_profit")
                    or amount("group_profit")-amount("nci")!=amount("parent_profit")):
                raise ValueError("NINE_MONTH_TAX_NCI_PARENT_IDENTITY_CONFLICT")
    return dict(schema_version=VERSION,status="VERIFIED_REPORTED_YTD",symbol=symbol,
        period_start=date(year,1,1).isoformat(),period_end=date(year,9,30).isoformat(),
        comparative_start=date(year-1,1,1).isoformat(),comparative_end=date(year-1,9,30).isoformat(),
        currency_basis=currency_basis,fields=result,action="no_order",formal_eligibility=False,
        limitations=["Nine-month statements are not single-quarter or full-year figures.",
          "CFO includes working-capital movement; cash CapEx is not proven maintenance and neither is parent FCFE."])

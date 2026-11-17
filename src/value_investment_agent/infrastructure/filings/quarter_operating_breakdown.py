"""Extract supported Q3 revenue breakdowns without inferring growth or forecast changes."""
from decimal import Decimal
import re

from .operating_event_terms import _Original, _match
from .parent_guarantee_event import _publication

TITLE_PATTERN = r"关于\s*20\d{2}\s*年第三季度经营数据的公告"
_AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}"


def parse_quarter_operating_breakdown(pages, *, symbol):
    original = _Original(pages)
    text = original.text
    header = _match(
        r"证券代码:(?P<symbol>\d{6})证券简称:[^:]+?公告编号:临(?P<year>20\d{2})-\d{3}"
        r"(?P<issuer>[^:]+?股份有限公司)关于(?P=year)年第三季度经营数据的公告"
        r"(?P<body>.+)特此公告。?(?P=issuer)董事会(?P<date>[^。]+日)", text,
    )
    if header["symbol"] != symbol or text.count("证券代码:") != 1:
        raise ValueError("OPERATING_BREAKDOWN_ISSUER_MISMATCH")
    year = header["year"]
    published = _publication(header["date"])
    if published < year + "-10-01" or published[:4] != year:
        raise ValueError("OPERATING_BREAKDOWN_DATE_INVALID")
    body = header["body"]
    heading = r"单位:元币种:人民币"
    periods = rf"{year}年7-9月{year}年1-9月"
    sections = (
        ("product", "产品类别", "主营业务收入按产品类别分类情况",
         "主营业务收入按销售模式分类情况", r"\(二\)"),
        ("channel", "销售模式", "主营业务收入按销售模式分类情况",
         "主营业务收入按地区分部分类情况", r"\(三\)"),
        ("region", "地区分部", "主营业务收入按地区分部分类情况",
         "二、经销商总数变化情况", ""),
    )
    groups, excerpts = {}, []
    for key, column, label, following, boundary in sections:
        pattern = label + heading + column + periods + r"(.+?)" + boundary + following
        matches = list(re.finditer(pattern, body))
        if len(matches) != 1:
            raise ValueError("OPERATING_BREAKDOWN_TABLE_MISSING_OR_AMBIGUOUS")
        table = matches[0][1]
        row_pattern = rf"([^\d,.:]+)({_AMOUNT})({_AMOUNT})"
        rows = list(re.finditer(row_pattern, table))
        if not 2 <= len(rows) <= 30 or "".join(row[0] for row in rows) != table:
            raise ValueError("OPERATING_BREAKDOWN_INCOMPLETE_ROWS")
        names = [row[1] for row in rows]
        if names[-1] != "合计" or len(set(names)) != len(names):
            raise ValueError("OPERATING_BREAKDOWN_TOTAL_OR_LABEL_INVALID")
        values = [(Decimal(row[2].replace(",", "")), Decimal(row[3].replace(",", ""))) for row in rows]
        total = values[-1]
        if any(q3 > ytd for q3, ytd in values) or tuple(map(sum, zip(*values[:-1]))) != total:
            raise ValueError("OPERATING_BREAKDOWN_TOTAL_NOT_RECONCILED")
        groups[key] = dict(rows=[dict(label=name, q3_cny=str(q3), ytd_cny=str(ytd))
                                 for name, (q3, ytd) in zip(names[:-1], values[:-1])],
                           q3_total_cny=str(total[0]), ytd_total_cny=str(total[1]))
        excerpts.extend(original.evidence(matches[0][0].removesuffix(following), key))
    if len({(g["q3_total_cny"], g["ytd_total_cny"]) for g in groups.values()}) != 1:
        raise ValueError("OPERATING_BREAKDOWN_DIMENSIONS_DISAGREE")
    summary = "公告主营业务收入：" + "、".join(
        f"{row['label']}单季{row['q3_cny']}元（前三季度累计{row['ytd_cny']}元）"
        for row in groups["product"]["rows"])
    return dict(parser_version="quarter-operating-breakdown-v1",
                event_type="REPORTED_Q3_OPERATING_BREAKDOWN", symbol=symbol,
                published_date=published, effective_date=None, summary=summary,
                implication="复核产品结构和渠道变化对原经营假设的影响。",
                affected_model_fields=["revenue_cny"], groups=groups,
                physical_pages=sorted({row["physical_page"] for row in excerpts}),
                evidence_excerpts=excerpts,
                limitations=["主营业务收入按三个维度分别列示，不可叠加，亦不等于合并营业收入。",
                             "公告只包含本年单季和前三季度累计数据，不据此推断同比、销量或售价变化。"],
                action="no_order")

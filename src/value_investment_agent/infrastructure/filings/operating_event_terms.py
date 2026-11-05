"""Bounded original-announcement terms; not a materiality or capital gate.

Only the three explicit prose layouts below are supported. Callers own PDF/hash
verification and must compare published_date with the source index/URL date.
No title-only inference, model recalculation, completion or approval is produced.
"""

from datetime import date
from decimal import Decimal
import re
import unicodedata

VERSION = "operating-event-terms-v1"
_DATE = r"(?P<{name}>20[0-9]{{2}}年[0-9]{{1,2}}月[0-9]{{1,2}}日)"
_MONEY = r"[0-9]+(?:\.[0-9]+)?"
_MEETING = r"第[一二三四五六七八九十]+届董事会20[0-9]{2}年度第[一二三四五六七八九十]+次会议"
_GUARANTEE = (
    "本公司董事会及全体董事保证本公告内容不存在任何虚假记载、误导性陈述或者"
    "重大遗漏，并对其内容的真实性、准确性和完整性承担法律责任。"
)


def _reject(reason):
    raise ValueError("OPERATING_EVENT_" + reason)


def _day(text):
    match = re.fullmatch(r"(20[0-9]{2})年([0-9]{1,2})月([0-9]{1,2})日", text)
    if not match:
        _reject("INVALID_DATE")
    try:
        return date(*(int(part) for part in match.groups())).isoformat()
    except ValueError:
        _reject("INVALID_DATE")


def _match(pattern, text):
    match = re.fullmatch(unicodedata.normalize("NFKC", pattern), text)
    if match is None:
        _reject("UNSUPPORTED_OR_AMBIGUOUS_LAYOUT")
    return match


class _Original:
    def __init__(self, pages):
        if (not isinstance(pages, (list, tuple)) or not 1 <= len(pages) <= 3
                or any(not isinstance(page, str) or not page.strip() for page in pages)
                or sum(map(len, pages)) > 40000):
            _reject("BOUNDED_COMPLETE_PAGES_REQUIRED")
        self.pages = pages
        self.text = ""
        self.positions = []
        for page_no, raw in enumerate(pages, 1):
            # Only a standalone leading physical page number may be removed.
            leading = re.match(r"\s*([0-9]+)\s*[\r\n]+", raw)
            start = 0
            if leading:
                if int(leading[1]) != page_no:
                    _reject("PHYSICAL_PAGE_SEQUENCE_MISMATCH")
                start = leading.end()
            for offset in range(start, len(raw)):
                for char in unicodedata.normalize("NFKC", raw[offset]):
                    if not char.isspace():
                        self.text += char
                        self.positions.append((page_no, offset))
        if "\ufffd" in self.text:
            _reject("UNDECODABLE_ORIGINAL")

    def evidence(self, fragment, field):
        if not fragment or self.text.count(fragment) != 1:
            _reject("AMBIGUOUS_EVIDENCE_SPAN")
        start = self.text.index(fragment)
        points = self.positions[start:start + len(fragment)]
        result = []
        for page in sorted({point[0] for point in points}):
            offsets = [offset for number, offset in points if number == page]
            result.append({
                "field": field,
                "physical_page": page,
                "text": self.pages[page - 1][min(offsets):max(offsets) + 1],
            })
        return result


def _price(body, published):
    pattern = (
        r"根据《(?P<plan>[^《》]{1,100}市场化运营方案)》，"
        r"按照“随行就市、相对平稳、供需适配、量价平衡”的原则，"
        r"为有效维护市场秩序，经研究决定，本公司自" + _DATE.format(name="effective") +
        r"零时起，将(?P<product>[^，。]{1,100}\([0-9]{4}\))"
        r"(?P<platform>[^，。]{1,30})平台零售价由"
        rf"(?P<retail_before>{_MONEY})元/瓶调整为(?P<retail_after>{_MONEY})元/瓶、"
        rf"销售合同价由(?P<contract_before>{_MONEY})元/瓶调整为(?P<contract_after>{_MONEY})元/瓶。"
        r"此次价格调整将会对本公司经营业绩产生一定影响，敬请投资者理性投资，注意风险。"
    )
    match = _match(pattern, body)
    effective = _day(match["effective"])
    if effective[:4] != published[:4]:
        _reject("UNSUPPORTED_EFFECTIVE_YEAR")
    for key in ("retail_before", "retail_after", "contract_before", "contract_after"):
        if Decimal(match[key]) <= 0:
            _reject("NONPOSITIVE_PRICE")
    terms = {
        "product_scope": match["product"],
        "operating_plan": match["plan"],
        "effective_at": effective + "T00:00:00+08:00",
        "retail_price": {
            "channel": match["platform"] + "平台", "unit": "CNY/bottle",
            "before": match["retail_before"], "after": match["retail_after"],
        },
        "sales_contract_price": {
            "unit": "CNY/bottle", "before": match["contract_before"],
            "after": match["contract_after"],
            "scope": "DISCLOSED_PRODUCT_SALES_CONTRACT_PRICE_NOT_RETAIL_REALIZATION",
        },
        "issuer_performance_statement": "此次价格调整将会对本公司经营业绩产生一定影响",
        "tax_basis": "NOT_DISCLOSED", "realized_revenue_effect": None,
    }
    return {
        "event_type": "OPERATING_PRICE_CHANGE", "effective_date": effective,
        "terms": terms, "affected_model_fields": ["revenue", "profit"],
        "summary": (
            f"公告披露{effective}零时起，{match['product']}的{match['platform']}平台"
            f"零售价由{match['retail_before']}元/瓶调整为{match['retail_after']}元/瓶；"
            f"销售合同价由{match['contract_before']}元/瓶调整为{match['contract_after']}元/瓶。"
        ),
        "implication": "需复核产品销量、渠道组合、含税口径及收入确认，不能将平台零售价直接当作销售合同收入或按涨幅机械修改利润。",
        "limitations": [
            "仅覆盖原文限定产品与渠道；未披露实际成交量、收入贡献或税基。",
            "销售合同价与平台零售价分列，不能混用；价格调整不等于已实现业绩。",
        ],
        "_evidence": [(body, "price_change_scope_and_effective_date")],
    }


def _board(body, title, issuer, published):
    meeting = title.removesuffix("决议公告")
    _match(_MEETING, meeting)
    intro, separator, decisions = body.partition("二、董事会会议审议情况")
    if not separator:
        _reject("BOARD_SCOPE_MISSING")
    intro_pattern = (
        "一、董事会会议召开情况" + _DATE.format(name="notice") + "，" + re.escape(issuer) +
        r"\(以下简称“公司”\)以直接送达或电子邮件的方式，向全体董事发出召开" +
        re.escape(meeting) + r"\(以下简称“会议”\)的通知。" +
        _DATE.format(name="meeting_date") +
        r"，会议以现场结合通讯表决方式在公司会议中心召开。会议应出席董事"
        r"(?P<expected>[0-9]+)人，实际出席董事(?P<actual>[0-9]+)人"
        r"\(其中董事[\u4e00-\u9fff]{2,10}因工作原因以通讯方式出席会议\)。"
        r"会议由董事长[\u4e00-\u9fff]{2,10}主持，公司部分高级管理人员列席了会议。"
        r"会议的召开符合《中华人民共和国公司法》等法律、行政法规和《公司章程》的规定。"
    )
    details = _match(intro_pattern, intro)
    meeting_date = _day(details["meeting_date"])
    if not _day(details["notice"]) <= meeting_date <= published:
        _reject("BOARD_DATE_ORDER_MISMATCH")
    if meeting_date[:4] not in meeting or meeting_date[:4] != published[:4]:
        _reject("BOARD_YEAR_MISMATCH")
    vote = r"同意:(?P<{prefix}yes>[0-9]+)票;反对:(?P<{prefix}no>[0-9]+)票;弃权:(?P<{prefix}abstain>[0-9]+)票。议案获得通过。"
    pattern = (
        r"\(一\)《(?P<report_year>20[0-9]{2})年半年度报告》\(详见上海证券交易所网站http://www.sse.com.cn\)" +
        vote.format(prefix="report_") +
        r"公司董事会审计委员会事前已审议通过本议案，并同意提交董事会审议。"
        r"\(二\)《关于将(?P<platform>[^《》，。]{1,30})数字营销平台相关资产无偿划转至"
        r"(?P<recipient_short>[^《》，。]{1,40})的议案》" +
        vote.format(prefix="transfer_") +
        r"会议决定，公司以无偿划转方式，向公司全资子公司"
        r"(?P<recipient>[\u4e00-\u9fff]{2,60}有限公司)\(以下简称“(?P<alias>[\u4e00-\u9fff]{2,20})”\)"
        r"划转(?P=platform)数字营销平台相关信息系统及域名等，"
        r"在授权范围内向(?P=alias)转授权使用“(?P<trademark>[A-Za-z0-9]{1,40})”等商标。"
        r"\(三\)《(?P<plan_year>20[0-9]{2})年度“提质增效重回报”行动方案半年度评估报告》" +
        vote.format(prefix="plan_")
    )
    match = _match(pattern, decisions)
    if (match["report_year"] != published[:4] or match["plan_year"] != published[:4]
            or match["recipient_short"].removesuffix("公司") not in match["recipient"]):
        _reject("BOARD_SCOPE_IDENTITY_MISMATCH")
    if int(details["expected"]) != int(details["actual"]) or int(details["actual"]) < 1:
        _reject("BOARD_ATTENDANCE_MISMATCH")
    for prefix in ("report_", "transfer_", "plan_"):
        # This bounded layout supports unanimous passage only. A consistent
        # vote total cannot override an adverse vote or prove passage by itself.
        if (int(match[prefix + "yes"]) != int(details["actual"])
                or int(match[prefix + "no"]) != 0
                or int(match[prefix + "abstain"]) != 0):
            _reject("BOARD_UNANIMOUS_PASSAGE_NOT_VERIFIED")
    transfer = decisions[decisions.index("(二)"):decisions.index("(三)")]
    return {
        "event_type": "INTERNAL_ASSET_TRANSFER_RESOLUTION", "effective_date": None,
        "terms": {
            "resolution_date": meeting_date,
            "transferor": issuer, "recipient": match["recipient"],
            "recipient_relationship": "WHOLLY_OWNED_SUBSIDIARY",
            "transfer_method": "GRATUITOUS_TRANSFER_RESOLUTION",
            "asset_scope": match["platform"] + "数字营销平台相关信息系统及域名等",
            "trademark_scope": "在授权范围内转授权使用“" + match["trademark"] + "”等商标",
            "execution_status": "RESOLUTION_ONLY_COMPLETION_NOT_EVIDENCED",
            "completion_date": None, "asset_value_cny": None,
            "other_resolutions": [
                match["report_year"] + "年半年度报告",
                match["plan_year"] + "年度“提质增效重回报”行动方案半年度评估报告",
            ],
        },
        "affected_model_fields": ["opening_operating_capital", "accessible_profit", "profit"],
        "summary": (
            f"{meeting_date}董事会决定向全资子公司{match['recipient']}无偿划转"
            f"{match['platform']}数字营销平台相关信息系统及域名等，并在授权范围内转授权商标；"
            "原文仅证明决议，不证明已完成划转。"
        ),
        "implication": "需复核实际实施时间、资产范围及账面金额、母公司与合并口径和资金可达性；不能据内部无偿划转推定经营资本、盈利或现金均无变化。",
        "limitations": [
            "董事会决议日期不是资产划转实施或完成日期；原文未披露资产金额。",
            "无偿划转不等于资产价值为零；商标转授权不等于商标所有权转让。",
            "另列其他决议仅保留范围，不表示已完成其他决议的材料性复核。",
        ],
        "_evidence": [(intro, "board_resolution_date"), (transfer, "asset_transfer_resolution")],
    }


def _accounting(body, issuer, published):
    # Exact supported statement scope: interpretations 19 and 20, not arbitrary
    # accounting changes whose titles happen to look similar.
    pattern = (
        r"重要内容提示:●" + re.escape(issuer) +
        r"\(以下简称“公司”\)根据中华人民共和国财政部\(以下简称“财政部”\)相关规定进行的会计政策变更，"
        r"不会对公司财务状况、经营成果和现金流量产生重大影响。"
        r"一、本次会计政策变更概述\(一\)会计政策变更的原因" +
        _DATE.format(name="issued_19") +
        r"，财政部发布了《企业会计准则解释第19号》\(财会〔(?P<doc19_year>20[0-9]{2})〕32号\)，"
        r"对“关于非同一控制下企业合并中补偿性资产的会计处理”、"
        r"“关于处置原通过同一控制下企业合并取得子公司时相关资本公积的会计处理”、"
        r"“关于采用电子支付系统结算的金融负债的终止确认”、"
        r"“关于金融资产合同现金流量特征的评估及相关披露”和"
        r"“关于指定为以公允价值计量且其变动计入其他综合收益的权益工具的披露”的内容进行进一步规范及明确，"
        r"本解释自" + _DATE.format(name="effective_19") + r"起施行。" +
        _DATE.format(name="issued_20") +
        r"，财政部发布了《企业会计准则解释第20号》\(财会〔(?P<doc20_year>20[0-9]{2})〕7号\)，"
        r"对“关于金融资产合同现金流量特征的评估”、“关于货币缺乏可兑换性时的会计处理及相关披露”等内容"
        r"进行进一步规范及明确。本解释自公布之日起施行，" +
        _DATE.format(name="transition_from_20") +
        r"至本解释施行日新增的本解释规定的业务，企业应当根据本解释进行调整。"
        r"\(二\)变更前采用的会计政策"
        r"本次会计政策变更前，公司执行财政部发布的《企业会计准则——基本准则》和各项具体会计准则、"
        r"企业会计准则应用指南、企业会计准则解释公告以及其他相关规定。"
        r"\(三\)变更后采用的会计政策"
        r"本次会计政策变更后，公司将按照财政部发布的《企业会计准则解释第19号》及《企业会计准则解释第20号》"
        r"要求执行。除上述会计政策变更外，其余未变更部分，仍执行财政部发布的《企业会计准则——基本准则》"
        r"和各项具体会计准则、企业会计准则应用指南、企业会计准则解释公告以及其他相关规定。"
        r"\(四\)会计政策变更日期公司按照上述文件规定的施行时间执行变更后的相关会计政策。"
        r"二、本次会计政策变更对公司的影响"
        r"本次会计政策变更是公司根据财政部发布的《企业会计准则解释第19号》\(财会〔(?P=doc19_year)〕32号\)"
        r"及《企业会计准则解释第20号》\(财会〔(?P=doc20_year)〕7号\)的要求进行的变更，"
        r"变更后的会计政策能够更加客观、公允地反映公司的财务状况、经营成果和现金流量，"
        r"本次会计政策变更不涉及对公司以前年度的追溯调整，对公司财务状况、经营成果和现金流量无重大影响，"
        r"不存在损害公司及全体股东利益的情形。"
    )
    match = _match(pattern, body)
    issued19, effective19, issued20, transition = (
        _day(match[key]) for key in ("issued_19", "effective_19", "issued_20", "transition_from_20")
    )
    if (not issued19 <= effective19 <= published or not transition <= issued20 <= published
            or issued19[:4] != match["doc19_year"] or issued20[:4] != match["doc20_year"]):
        _reject("ACCOUNTING_DATE_ORDER_MISMATCH")
    return {
        "event_type": "ACCOUNTING_POLICY_IMPACT_STATEMENT", "effective_date": None,
        "terms": {
            "standards": [
                {"interpretation": "19", "issued_date": issued19, "effective_date": effective19},
                {"interpretation": "20", "issued_date": issued20, "effective_date": issued20,
                 "transition_new_transactions_from": transition},
            ],
            "impact_scope": ["financial_position", "operating_results", "cash_flows"],
            "issuer_impact_statement": "对公司财务状况、经营成果和现金流量无重大影响",
            "issuer_prior_year_statement": "不涉及对公司以前年度的追溯调整",
            "assessment_basis": "ISSUER_STATEMENT_NOT_INDEPENDENT_APPROVAL",
        },
        "affected_model_fields": ["profit", "opening_book", "accessible_profit"],
        "summary": "公司披露执行企业会计准则解释第19号及第20号，并声明不涉及以前年度追溯调整、对财务状况、经营成果和现金流量无重大影响。",
        "implication": "这是发行人影响声明，仍需对精确候选的会计口径与受影响交易独立复核；不能据此批准材料性或认定模型无影响。",
        "limitations": [
            "两项准则施行日期及过渡期分别列示，无单一事件生效日。",
            "无重大影响及不追溯调整均为发行人声明，不是独立复核结论。",
        ],
        "_evidence": [(body, "accounting_policy_scope_dates_and_issuer_statement")],
    }


def parse_operating_event_terms(pages, *, symbol):
    """Extract bounded source terms; ValueError rejects unsupported prose.

    Input is the COMPLETE extract_pages output, not a selected excerpt. The
    expected symbol is caller-owned. Issuer heading, signature and all relevant
    dates are checked internally; index/URL publication identity is caller-owned.
    """
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        _reject("EXPECTED_SYMBOL_REQUIRED")
    original = _Original(pages)
    text = original.text
    header = _match(
        r"(?:证券代码:(?P<code_a>[0-9]{6})证券简称:(?P<short_a>[^:]{1,30})公告编号:临|"
        r"证券简称:(?P<short_b>[^:]{1,30})证券代码:(?P<code_b>[0-9]{6})编号:临)"
        r"(?P<year>20[0-9]{2})-(?P<number>[0-9]{3})"
        r"(?P<issuer>[\u4e00-\u9fffA-Za-z()]{2,80}股份有限公司)"
        r"(?P<title>重大事项公告|" + _MEETING + r"决议公告|关于会计政策变更的公告)"
        + re.escape(_GUARANTEE) + r"(?P<body>.+)特此公告。"
        r"(?P=issuer)董事会" + _DATE.format(name="published"), text,
    )
    if (header["code_a"] or header["code_b"]) != symbol or len(re.findall(r"证券代码:", text)) != 1:
        _reject("ISSUER_CODE_MISMATCH")
    published = _day(header["published"])
    if published[:4] != header["year"]:
        _reject("ANNOUNCEMENT_YEAR_MISMATCH")
    title, issuer, body = header["title"], header["issuer"], header["body"]
    if title == "重大事项公告":
        result = _price(body, published)
    elif title == "关于会计政策变更的公告":
        result = _accounting(body, issuer, published)
    else:
        result = _board(body, title, issuer, published)
    heading = text.split(unicodedata.normalize("NFKC", _GUARANTEE), 1)[0]
    evidence = original.evidence(heading, "issuer_code_and_heading")
    for fragment, field in result.pop("_evidence"):
        evidence.extend(original.evidence(fragment, field))
    footer = issuer + "董事会" + header["published"]
    evidence.extend(original.evidence(footer, "issuer_and_publication_date"))
    result.update(
        parser_version=VERSION, symbol=symbol, issuer_name=issuer,
        announcement_number=header["year"] + "-" + header["number"],
        published_date=published, action="no_order",
        evidence_excerpts=evidence,
        physical_pages=sorted({item["physical_page"] for item in evidence}),
    )
    result["limitations"].extend([
        "仅提取受支持正文条款；不证明跨期全部事件已覆盖。",
        "affected_model_fields为需复核的模型字段，不表示已量化影响或已消费。",
        "不授予材料性、股本不变、模型有效性、策略或交易资格；披露日期须由调用方与来源索引和URL核对。",
    ])
    return result

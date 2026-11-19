"""Bounded original-announcement terms; not a materiality or capital gate.

Only bounded, explicitly recognized prose layouts are supported. Callers own PDF/hash
verification and must compare published_date with the source index/URL date.
No title-only inference, model recalculation, completion or approval is produced.
"""

from calendar import monthrange
from datetime import date
from decimal import Decimal
import re
import unicodedata

VERSION = "operating-event-terms-v2"
_DATE = r"(?P<{name}>20[0-9]{{2}}年[0-9]{{1,2}}月[0-9]{{1,2}}日)"
_PUBLICATION_DATE = (
    r"(?P<{name}>(?:20[0-9]{{2}}年[0-9]{{1,2}}月[0-9]{{1,2}}日|"
    r"二[〇○零一二三四五六七八九]{{3}}年"
    r"[一二三四五六七八九十]{{1,3}}月[一二三四五六七八九十]{{1,3}}日))"
)
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
        chinese = re.fullmatch(
            r"(二[〇○零一二三四五六七八九]{3})年"
            r"([一二三四五六七八九十]{1,3})月"
            r"([一二三四五六七八九十]{1,3})日",
            text,
        )
        if chinese:
            digits = {"〇": 0, "○": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                      "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

            def number(value):
                if "十" not in value:
                    return digits[value]
                left, right = value.split("十", 1)
                return (digits[left] if left else 1) * 10 + (digits[right] if right else 0)

            year = int("".join(str(digits[char]) for char in chinese[1]))
            try:
                return date(year, number(chinese[2]), number(chinese[3])).isoformat()
            except (KeyError, ValueError):
                _reject("INVALID_DATE")
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
    def __init__(self, pages, *, max_pages=3, max_chars=40000):
        if (not isinstance(pages, (list, tuple)) or not 1 <= len(pages) <= max_pages
                or any(not isinstance(page, str) or not page.strip() for page in pages)
                or sum(map(len, pages)) > max_chars):
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


def _buyback_progress(body, published, *, first_execution=False):
    plan_rows = list(re.finditer(
        "回购方案实施期限" + _DATE.format(name="start") + "[~～至]" + _DATE.format(name="end"), body))
    if len(plan_rows) > 1:
        _reject("BUYBACK_PLAN_WINDOW_AMBIGUOUS")
    plan_terms, plan_evidence = {}, []
    if plan_rows:
        plan = plan_rows[0]
        plan_start, plan_end = _day(plan["start"]), _day(plan["end"])
        if plan_start >= plan_end or plan_start > published:
            _reject("BUYBACK_PLAN_WINDOW_INVALID")
        plan_terms = dict(plan_start=plan_start, plan_end=plan_end)
        plan_evidence = [(plan[0], "buyback_plan_window")]
    quantity = r"[1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*"
    amount = r"[0-9]+(?:,[0-9]{3})*\.[0-9]{2}"
    summary_rows = list(re.finditer(
        rf"累计已回购股数(?P<shares>{quantity})股累计已回购股数占总股本比例"
        rf"(?P<ratio>{_MONEY})%累计已回购金额(?P<total>{amount})元", body))
    _, boundary, progress = body.partition("二、回购股份的进展情况")
    progress, ending, _ = progress.partition("三、其他事项")
    zero_summary = "累计已回购股数0万股累计已回购股数占总股本比例0%累计已回购金额0万元"
    no_execution = list(re.finditer(
        r"截至" + _DATE.format(name="through") + r",公司尚未实施股份回购。", progress))
    if no_execution:
        if (first_execution or not boundary or not ending or len(no_execution) != 1
                or body.count(zero_summary) != 1 or summary_rows
                or "公司已累计回购股份" in progress):
            _reject("BUYBACK_PROGRESS_SUMMARY_MISMATCH")
        through = _day(no_execution[0]["through"])
        day = date.fromisoformat(through)
        if through >= published or day.day != monthrange(day.year, day.month)[1]:
            _reject("BUYBACK_PROGRESS_ARITHMETIC_OR_DATE_INVALID")
        return dict(
            event_type="REPORTED_BUYBACK_PROGRESS", effective_date=None,
            terms=dict(through=through, cumulative_purchased_shares=0,
                       cumulative_paid_cny="0", disclosed_share_percent="0",
                       completed_cancellation_shares=None, **plan_terms),
            affected_model_fields=["cash", "ordinary_shares"],
            summary=f"公告确认截至{through}尚未实施股份回购。",
            implication="仅作为本回购计划已披露累计数据的期初对照。",
            limitations=["该结论限于所述回购计划及截止日。"],
            _evidence=[(zero_summary, "buyback_summary"), (no_execution[0][0], "buyback_progress"), *plan_evidence],
        )
    if first_execution:
        opening = (_DATE.format(name="through") + r",公司通过集中竞价交易方式首次回购股份数量为"
                   rf"(?P<shares>{quantity})股,已回购股份占公司总股本的比例为(?P<ratio>{_MONEY})%,"
                   rf"购买的最高价为(?P<high>{_MONEY})元/股,最低价为(?P<low>{_MONEY})元/股,")
    else:
        opening = (rf"截至(?P<year>20[0-9]{{2}})年(?P<month>[0-9]{{1,2}})月底,公司已累计回购股份"
                   rf"(?P<shares>{quantity})股,占公司总股本的比例为(?P<ratio>{_MONEY})%,"
                   rf"购买的最高价为(?P<high>{_MONEY})元/股、最低价为(?P<low>{_MONEY})元/股,")
    rows = list(re.finditer(
        opening + rf"已支付的总金额为(?P<total>{amount})元人民币\(不含交易费用\)。", progress))
    if not boundary or not ending or len(summary_rows) != 1 or len(rows) != 1:
        _reject("BUYBACK_PROGRESS_TERMS_MISSING_OR_AMBIGUOUS")
    row = rows[0]
    number = lambda match, key: Decimal(match[key].replace(",", ""))
    shares, ratio, total = (number(row, key) for key in ("shares", "ratio", "total"))
    if any(number(summary_rows[0], key) != number(row, key) for key in ("shares", "ratio", "total")):
        _reject("BUYBACK_PROGRESS_SUMMARY_MISMATCH")
    low, high = number(row, "low"), number(row, "high")
    if first_execution:
        through = _day(row["through"])
    else:
        year, month = int(row["year"]), int(row["month"])
        if not 1 <= month <= 12:
            _reject("INVALID_DATE")
        through = date(year, month, monthrange(year, month)[1]).isoformat()
    if through >= published or not 0 < ratio <= 100 or not 0 < low <= total / shares <= high:
        _reject("BUYBACK_PROGRESS_ARITHMETIC_OR_DATE_INVALID")
    terms = dict(through=through, cumulative_purchased_shares=int(shares),
                 cumulative_paid_cny=str(total), disclosed_share_percent=str(ratio),
                 completed_cancellation_shares=None, **plan_terms)
    if first_execution:
        terms["first_purchase_date"] = through
    return dict(
        event_type="REPORTED_BUYBACK_PROGRESS", effective_date=None,
        terms=terms,
        affected_model_fields=["cash", "ordinary_shares"],
        summary=f"截至{through}累计购回{int(shares)}股，已支付{total}元（不含交易费用）。",
        implication="核对累计金额的期间增量及后续注销生效公告，当前资料不改变估值股数。",
        limitations=["购回进展不能证明注销生效；累计数不能重复计为各期现金支出。"],
        _evidence=[(summary_rows[0][0], "buyback_summary"), (row[0], "buyback_progress"), *plan_evidence],
    )


def _buyback_completion(body, published):
    quantity = r"[1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*"
    money = r"[0-9]+(?:,[0-9]{3})*\.[0-9]{2}"
    _, start, execution = body.partition("二、回购实施情况")
    execution, end, _ = execution.partition("三、回购期间")
    completed = list(re.finditer(
        _DATE.format(name="through") + r",公司回购股份实施完成,实际回购公司股份"
        + rf"(?P<shares>{quantity})股,占公司总股本的(?P<ratio>{_MONEY})%,"
        + rf"回购最高价格(?P<high>{money})元/股,回购最低价格(?P<low>{money})元/股,"
        + rf"回购均价{money}元/股,使用资金总额(?P<total>{money})元\(不含交易费用\)。",
        execution,
    ))
    _, cancel_start, cancellation = body.partition("四、股份注销安排")
    cancellation, cancel_end, table = cancellation.partition("五、股份变动表")
    scheduled = _match(
        r"经申请,预计公司将于" + _DATE.format(name="scheduled")
        + rf"在中国证券登记结算有限责任公司(?:上海|深圳)分公司注销本次所回购的股份(?P<shares>{quantity})股,"
        + r"并及时办理变更登记手续等相关事宜。", cancellation,
    )
    table, table_end, _ = table.partition("六、已回购股份的处理安排")
    totals = list(re.finditer(
        rf"股份总数(?P<opening>{quantity})100\.00(?P<cancel>{quantity})0(?P<closing>{quantity})100\.00$",
        table,
    ))
    if not all((start, end, cancel_start, cancel_end, table_end)) or len(completed) != 1 or len(totals) != 1:
        _reject("BUYBACK_COMPLETION_TERMS_MISSING_OR_AMBIGUOUS")
    row, counts = completed[0], totals[0]

    def number(match, key):
        return Decimal(match[key].replace(",", ""))

    overview = list(re.finditer(
        rf"实际回购股数(?P<shares>{quantity})股实际回购股数占总股本比例(?P<ratio>{_MONEY})%"
        + rf"实际回购金额(?P<total>{money})元实际回购价格区间(?P<low>{money})元/股~(?P<high>{money})元/股",
        body.partition("一、回购审批情况")[0],
    ))
    if len(overview) != 1 or any(number(overview[0], field) != number(row, field)
                                  for field in ("shares", "ratio", "total", "low", "high")):
        _reject("BUYBACK_COMPLETION_SUMMARY_MISMATCH")
    shares, total, ratio = (number(row, key) for key in ("shares", "total", "ratio"))
    opening, cancelled, closing = (number(counts, key) for key in ("opening", "cancel", "closing"))
    through, scheduled_date = _day(row["through"]), _day(scheduled["scheduled"])
    if (not through <= published <= scheduled_date or through >= scheduled_date
            or not 0 < ratio <= 100 or not 0 < number(row, "low") <= total / shares <= number(row, "high")
            or shares != cancelled or shares != number(scheduled, "shares") or opening - cancelled != closing):
        _reject("BUYBACK_COMPLETION_ARITHMETIC_OR_DATE_INVALID")
    return dict(
        event_type="REPORTED_BUYBACK_PROGRESS", effective_date=None,
        terms=dict(through=through, cumulative_purchased_shares=int(shares),
                   cumulative_paid_cny=str(total), disclosed_share_percent=str(ratio),
                   purchase_state="COMPLETED", cancellation_state="SCHEDULED_UNCONFIRMED",
                   scheduled_cancellation_date=scheduled_date, planned_post_cancellation_shares=int(closing),
                   completed_cancellation_shares=None),
        affected_model_fields=["cash", "ordinary_shares"],
        summary=f"截至{through}回购完成，共购回{int(shares)}股，支付{total}元（不含交易费用）。",
        implication="期内现金支出须与基期和其他累计回执去重；只有后续登记完成证据才能确认股份注销。",
        limitations=["公告中注销为预计安排，拟注销后股数不可当作已经生效的股数。"],
        _evidence=[(overview[0][0], "buyback_summary"), (row[0], "buyback_completion"), (scheduled[0], "planned_cancellation"),
                   (counts[0], "planned_share_count_reconciliation")],
    )


def _buyback_creditor_notice(body, published):
    future_cancellation = _match(
        r".*(?P<clause>待回购完成后,本次回购的股份将依法全部予以注销并减少公司注册资本。).*", body,
    )
    claim_window = _match(r".*(?P<clause>申报时间:(?P<start>20\d{2}年\d{1,2}月\d{1,2}日)至"
                          r"(?P<end>20\d{2}年\d{1,2}月\d{1,2}日)).*", body)
    start, end = _day(claim_window["start"]), _day(claim_window["end"])
    if start != published or end < start:
        _reject("BUYBACK_CREDITOR_CLAIM_WINDOW_INVALID")
    return dict(
        event_type="BUYBACK_CAPITAL_REDUCTION_CREDITOR_NOTICE",
        effective_date=None,
        terms=dict(claim_start=start, claim_end=end, cancellation_status="PLANNED"),
        affected_model_fields=["cash", "ordinary_shares"],
        summary=f"拟于回购完成后注销股份；债权申报期间为 {start} 至 {end}。",
        implication="后续须核对实际回购、注销及资金义务的完成证据。",
        limitations=["债权人通知不证明已注销、实付金额或债权已结清。"],
        _evidence=[(future_cancellation["clause"], "planned_cancellation"),
                   (claim_window["clause"], "creditor_claim_window")],
    )

def _plan_market_purchase_completion(body, title, published):
    """Parse a bounded employee/service-plan secondary-market purchase.

    The title is only routing information.  Admission requires the complete
    body to identify the same plan and to state that shares were bought through
    an exchange securities trading system.  Any issuance, cancellation,
    transfer, subscription or other acquisition method is outside this
    contract and therefore remains unresolved.
    """
    title_match = _match(
        r"关于(?P<plan>第[一二三四五六七八九十]+期(?:长期服务计划|员工持股计划))完成股票购买的公告",
        title,
    )
    plan = title_match["plan"]
    forbidden = (
        "非公开发行", "向特定对象发行", "发行新股", "新股发行",
        "认购新股", "股份注销", "注销股份", "转让股份", "股份转让",
        "非交易过户", "无偿划转", "大宗交易", "协议转让", "股东赠与",
    )
    if any(term in body for term in forbidden):
        _reject("PLAN_PURCHASE_ISSUANCE_CANCELLATION_OR_TRANSFER_UNRESOLVED")
    quantity = r"[1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*"
    money = r"[1-9][0-9]*(?:,[0-9]{3})*(?:\.[0-9]+)?"
    price = r"[1-9][0-9]*(?:\.[0-9]+)?"
    exchange = r"(?P<exchange>上海证券交易所|深圳证券交易所)"
    row_pattern = (
        r"截至" + _DATE.format(name="completed") + r"[,，]公司通过" + exchange
        + r"证券交易系统购买公司股票(?P<shares>" + quantity + r")股[,，]"
        + r"成交金额(?P<total>" + money + r")元\(不含交易费用\)[,，]"
        + r"占公司总股本的比例为(?P<ratio>" + _MONEY + r")%[,，]"
        + r"成交均价为(?P<average>" + price + r")元/股[,，]公司(?P<plan>" + re.escape(plan)
        + r")标的股票的购买已全部完成。"
    )
    rows = list(re.finditer(row_pattern, body))
    if len(rows) != 1:
        _reject("PLAN_PURCHASE_METHOD_OR_TERMS_MISSING_OR_AMBIGUOUS")
    row = rows[0]
    completed = _day(row["completed"])
    shares = int(row["shares"].replace(",", ""))
    total = Decimal(row["total"].replace(",", ""))
    average = Decimal(row["average"])
    ratio = Decimal(row["ratio"])
    if (completed > published or not 0 < ratio <= 100 or total <= 0 or average <= 0
            or abs(total / shares - average) > Decimal("0.0005")):
        _reject("PLAN_PURCHASE_ARITHMETIC_OR_DATE_INVALID")
    return dict(
        event_type="PLAN_SECONDARY_MARKET_SHARE_PURCHASE_COMPLETED",
        effective_date=completed,
        terms=dict(
            plan_name=plan,
            completion_date=completed,
            purchase_method="EXCHANGE_SECURITIES_TRADING_SYSTEM_EXISTING_SHARES",
            exchange=row["exchange"],
            purchased_shares=shares,
            paid_cny=str(total),
            average_price_cny_per_share=str(average),
            disclosed_total_share_percent=str(ratio),
            issued_share_effect="NO_ISSUANCE_OR_CANCELLATION_IN_THIS_PURCHASE_EVENT",
        ),
        affected_model_fields=["cash", "ordinary_shares"],
        summary=(f"{plan}于{completed}前通过{row['exchange']}证券交易系统购买"
                 f"已有公司股票{shares}股，本次购买已完成。"),
        implication="该二级市场购买事件本身不发行或注销股份；资金影响及其他股本事件仍需分别核验。",
        limitations=[
            "仅证明本公告所述购买通过交易所证券交易系统完成，不证明公告窗口内不存在其他发行或注销。",
            "购买已有股票不等于股份注销，不得据此调减发行在外股数。",
        ],
        _evidence=[(row[0], "plan_exchange_market_purchase_completion")],
    )


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
        r"(?P<title>重大事项公告|" + _MEETING + r"决议公告|关于会计政策变更的公告|(?P<no_period>"
        r"(?P<plan_purchase>关于第[一二三四五六七八九十]+期(?:长期服务计划|员工持股计划)完成股票购买的公告)|"
        r"(?P<buyback>关于股份回购进展公告|关于以集中竞价交易方式首次回购公司股份的公告|关于股份回购实施结果暨股份变动的公告|关于回购股份减少注册资本通知债权人的公告)))"
        + re.escape(_GUARANTEE) + r"(?P<body>.+)特此公告(?(no_period)。?|。)"
        r"(?P=issuer)董事会" + _PUBLICATION_DATE.format(name="published"), text,
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
    elif title == "关于股份回购实施结果暨股份变动的公告":
        result = _buyback_completion(body, published)
    elif title == "关于回购股份减少注册资本通知债权人的公告":
        result = _buyback_creditor_notice(body, published)
    elif header["plan_purchase"]:
        result = _plan_market_purchase_completion(body, title, published)
    elif header["buyback"]:
        result = _buyback_progress(body, published, first_execution="首次回购" in title)
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


BUYBACK_PLAN_TITLES = (
    "关于以集中竞价交易方式回购公司股份方案的公告",
    "关于以集中竞价交易方式回购公司股份的回购报告书",
)


def parse_buyback_cancellation_plan(pages, *, symbol):
    """Extract a named proposal or approved plan, without asserting execution."""
    original = _Original(pages, max_pages=10, max_chars=90000)
    text = original.text
    title_pattern = "|".join(map(re.escape, BUYBACK_PLAN_TITLES))
    match = _match(
        r"(?P<heading>证券代码:(?P<code>[0-9]{6})证券简称:[^:]{1,30}公告编号:临"
        r"(?P<number>20[0-9]{2}-[0-9]{3})(?P<issuer>[\u4e00-\u9fff]{2,80}股份有限公司)"
        r"(?P<title>" + title_pattern + r"))(?P<body>.+)特此公告。?"
        r"(?P<signature>(?P=issuer)董事会" + _PUBLICATION_DATE.format(name="published") + ")",
        text,
    )
    if match["code"] != symbol or text.count("证券代码:") != 1:
        _reject("ISSUER_CODE_MISMATCH")
    published = _day(match["published"])
    if not match["number"].startswith(published[:4]):
        _reject("ANNOUNCEMENT_YEAR_MISMATCH")
    terms = re.search(
        r"回购股份金额:不低于人民币(?P<low>" + _MONEY + r")亿元\(含\)且不超过人民币"
        r"(?P<high>" + _MONEY + r")亿元\(含\),[^。]+。"
        r"●回购股份资金来源:公司自有资金。"
        r"●回购股份用途:本次回购股份将依法全部予以注销并减少公司注册资本。"
        r"●回购股份价格:不超过人民币(?P<cap>" + _MONEY + r")元/股\(含\)",
        match["body"],
    )
    duration = re.search(
        r"回购股份期限:自公司股东会审议通过回购方案之日起不超过(?P<months>[1-9][0-9]?)个月。",
        match["body"],
    )
    if terms is None or duration is None:
        _reject("BUYBACK_PLAN_TERMS_MISSING")
    low, high, cap = (Decimal(terms[key]) for key in ("low", "high", "cap"))
    if not 0 < low <= high or cap <= 0:
        _reject("BUYBACK_PLAN_TERMS_INVALID")
    pending = "本次回购股份方案尚需提交公司股东会审议通过。"
    approval = re.search(
        _DATE.format(name="meeting") + r",公司召开20[0-9]{2}年第[一二三四五六七八九十]+次临时股东会,"
        r"审议通过了《关于以集中竞价交易方式回购公司股份方案的议案》。",
        match["body"],
    )
    approved_on = None
    if match["title"] == BUYBACK_PLAN_TITLES[0]:
        if pending not in match["body"] or approval is not None:
            _reject("BUYBACK_PLAN_APPROVAL_CONFLICT")
        status, decision_span = "PROPOSED_SUBJECT_TO_SHAREHOLDER_APPROVAL", pending
    else:
        if approval is None or pending in match["body"]:
            _reject("BUYBACK_PLAN_APPROVAL_MISSING_OR_CONFLICTING")
        approved_on = _day(approval["meeting"])
        if approved_on > published:
            _reject("BUYBACK_PLAN_APPROVAL_AFTER_PUBLICATION")
        status, decision_span = "SHAREHOLDER_APPROVED_PLAN", approval[0]
    excerpts = []
    for fragment, field in ((match["heading"], "issuer"), (terms[0], "budget_funding_purpose_and_price"),
                            (duration[0], "duration"), (decision_span, "approval"),
                            (match["signature"], "publication")):
        excerpts.extend(original.evidence(fragment, field))
    phase = "董事会方案待股东会审议" if approved_on is None else f"{approved_on}股东会通过方案"
    return dict(
        parser_version="buyback-cancellation-plan-v1", event_type="REPORTED_BUYBACK_CANCELLATION_PLAN",
        symbol=symbol, published_date=published, effective_date=None,
        summary=f"{phase}。原件回购预算{low}–{high}亿元，价格上限{cap}元/股，拟用于注销减资。",
        implication="核对后续回购结果及注销生效公告，再重算实际现金和股本。",
        terms=dict(plan_state=status, shareholder_approved_on=approved_on,
                   cash_min_cny=str(low * 100000000), cash_max_cny=str(high * 100000000),
                   price_cap_cny=str(cap), duration_months=int(duration["months"])),
        affected_model_fields=["ordinary_shares", "shareholder_distributions"],
        limitations=["方案和资金上限均不证明实际回购金额、注销股数或生效日。"],
        evidence_excerpts=excerpts, action="no_order",
    )

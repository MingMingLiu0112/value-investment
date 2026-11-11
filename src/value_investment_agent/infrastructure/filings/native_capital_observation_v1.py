"""Bounded native SZ report observations; caller binds official bytes and clocks.

No monetary share-capital to share-quantity conversion, continuity certificate,
payment assertion, or fiscal-year policy applied to a rolling period.
"""
from datetime import date
from decimal import Decimal, localcontext
import re
import unicodedata

VERSION = "native-capital-observation-v1"
UNKNOWN = "UNKNOWN"
INTEGER = r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
MONEY = r"([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2}|[0-9]+\.[0-9]{2})"


def _compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).replace("−", "-")


def _decimal(text):
    return Decimal(text.replace(",", ""))


def _raw_excerpt(raw, compact_excerpt):
    # Keep verbatim original text, including native PDF line wraps.
    chars, positions = [], []
    for offset, char in enumerate(raw):
        for normalized in _compact(char):
            chars.append(normalized)
            positions.append(offset)
    text = "".join(chars)
    start = text.find(compact_excerpt)
    if start < 0 or text.find(compact_excerpt, start+1) >= 0:
        raise ValueError("NATIVE_OBSERVATION_EXCERPT_AMBIGUOUS")
    return raw[positions[start]:positions[start+len(compact_excerpt)-1]+1]


def parse_native_capital_observation(pages, *, symbol):
    """Parse supported report structures, not a formula chosen by security code.

    VERIFIED refers to report identity and field-level observations. Missing
    structures stay UNKNOWN. Original hash, issuer index and availability are
    independently verified by the source consumer; this function has no I/O.
    """
    if (not isinstance(pages, (list, tuple)) or not 1 <= len(pages) <= 500
            or any(not isinstance(p, str) for p in pages)
            or sum(map(len, pages)) > 3_000_000
            or not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)):
        raise ValueError("BOUNDED_NATIVE_REPORT_REQUIRED")
    normalized = [_compact(p) for p in pages]
    cover = normalized[0]
    title = re.match(r"(.+?股份(?:有限公司|公司))(20\d{2})年(半年度报告|年度报告|第一季度报告|第三季度报告|三季度报告)", cover)
    if title is None:
        return _announcement(pages, normalized, symbol)
    if any(word in cover for word in ("摘要", "英文版")):
        raise ValueError("NATIVE_FULL_REPORT_IDENTITY_REQUIRED")
    issuer, year, label = title.groups()
    titles = set(re.findall(r"20\d{2}年(?:半年度报告|年度报告|第一季度报告|第三季度报告|三季度报告)", cover))
    codes = set(re.findall(r"(?:股票|证券)代码:?([0-9]{6})(?![0-9])", "".join(normalized[:8])))
    if codes != {symbol} or len(titles) != 1:
        raise ValueError("NATIVE_SECURITY_OR_REPORT_IDENTITY_CONFLICT")
    exchange = re.findall(r"股票上市证券交易所([^公司]+)公司的", "".join(normalized[:8]))
    if exchange and exchange != ["深圳证券交易所"]:
        raise ValueError("NATIVE_SZ_REPORT_STRUCTURE_REQUIRED")
    kind, suffix = {"半年度报告": ("interim", "-06-30"), "年度报告": ("annual", "-12-31"),
        "第一季度报告": ("q1", "-03-31"), "第三季度报告": ("q3", "-09-30"), "三季度报告": ("q3", "-09-30")}[label]
    period = date.fromisoformat(year+suffix).isoformat()
    fields = ("ordinary_shares", "shares_before", "cancelled_shares",
        "declared_ordinary_dividend_cny", "dividend_fiscal_year", "cancellation_date",
        "cancellation_state", "interim_proposal_state", "report_approved_date")
    result = dict.fromkeys(fields, UNKNOWN)
    result.update(parser_version=VERSION, status="VERIFIED", symbol=symbol, issuer_name=issuer,
        report_kind=kind, report_period=period, period_end=period,
        verification_scope="IDENTIFIED_REPORT_AND_FIELD_OBSERVATIONS_NOT_CONTINUITY_OR_PAYMENT",
        published_date=UNKNOWN, available_at=UNKNOWN, historical_available_at=UNKNOWN,
        payment_completion_state=UNKNOWN, opening_pending_actions_complete=False,
        closing_continuity_proven=False, formal_eligibility=False, action="no_order",
        term_pages={}, evidence_refs=[])

    def evidence(field, page, text):
        result["term_pages"].setdefault(field, []).append(page)
        result["evidence_refs"].append(dict(field=field, physical_page=page,
            excerpt=_raw_excerpt(pages[page-1], text)))

    evidence("report_period", 1, cover)
    # A dated consolidated statement, when supplied, must agree with the cover.
    for text in normalized:
        for match in re.finditer(r"合并资产负债表(?:编制单位:[^0-9]+)?(20\d{2})年([0-9]{1,2})月([0-9]{1,2})日", text):
            if date(*map(int, match.groups())).isoformat() != period:
                raise ValueError("NATIVE_STATEMENT_REPORT_PERIOD_CONFLICT")

    # Only a quantity table with explicit before/change/after columns. An RMB
    # 股本 balance-sheet/note amount is never a share-count fallback.
    capital = []
    pattern = r"三、股份总数"+INTEGER+r"100(?:\.00)?%-"+INTEGER+r"-([0-9,]+)100(?:\.00)?%"
    for page, text in enumerate(normalized, 1):
        for match in re.finditer(pattern, text):
            header = "".join(normalized[max(0, page-2):page])
            if not all(word in header for word in ("单位:股", "本次变动前", "本次变动增减", "本次变动后", "其他", "小计")):
                raise ValueError("NATIVE_SHARE_TABLE_UNIT_OR_COLUMNS_UNSUPPORTED")
            before, reduction = map(_decimal, match.groups()[:2])
            joined = match[3]
            candidates = []
            for split in range(1, len(joined)):
                left, right = joined[:split], joined[split:]
                if re.fullmatch(INTEGER, left) and re.fullmatch(INTEGER, right):
                    subtotal, after = _decimal(left), _decimal(right)
                    if subtotal == reduction and before-reduction == after and min(before, after) > 0:
                        candidates.append(after)
            if len(candidates) != 1:
                raise ValueError("NATIVE_SHARE_ROLLFORWARD_CONFLICT")
            after = candidates[0]
            capital.append((page, match[0], before, reduction, after))
    if len(capital) > 1:
        raise ValueError("NATIVE_SHARE_TABLE_AMBIGUOUS")
    if capital:
        page, excerpt, before, reduction, after = capital[0]
        result.update(ordinary_shares=str(after), shares_before=str(before))
        evidence("ordinary_shares", page, excerpt)

    # Explicit dated completion of restricted-share cancellation, distinct
    # from a board proposal or general market buyback progress.
    cancellations = []
    cancellation_pattern = (r"截至(20\d{2})年([0-9]{1,2})月([0-9]{1,2})日,公司完成了"
        +INTEGER+r"股限制性股票回购注销工作")
    for page, text in enumerate(normalized, 1):
        for match in re.finditer(cancellation_pattern, text):
            completed = date(*map(int, match.groups()[:3]))
            if completed.year != int(year):
                continue
            amount = _decimal(match[4])
            if completed > date.fromisoformat(period) or amount <= 0:
                raise ValueError("NATIVE_CANCELLATION_PERIOD_OR_AMOUNT_CONFLICT")
            cancellations.append((page, match[0], completed.isoformat(), amount))
    if len(cancellations) > 1:
        raise ValueError("NATIVE_CANCELLATION_AMBIGUOUS")
    if cancellations:
        page, excerpt, completed, amount = cancellations[0]
        if capital and amount != capital[0][3]:
            raise ValueError("NATIVE_CANCELLATION_SHARE_TABLE_CONFLICT")
        result.update(cancelled_shares=str(amount), cancellation_date=completed,
            cancellation_state="REPORTED_RESTRICTED_SHARE_CANCELLATION_COMPLETED_BY_PERIOD_END")
        evidence("cancelled_shares", page, excerpt)

    for page, text in enumerate(normalized, 1):
        section = re.search(r"二、本报告期利润分配及资本公积金转增股本情况(.*?)三、", text)
        sentence = "公司计划半年度不派发现金红利,不送红股,不以公积金转增股本。"
        if kind == "interim" and section and sentence in section[1]:
            result["interim_proposal_state"] = "REPORTED_NO_INTERIM_DIVIDEND_OR_CAPITALIZATION_PLANNED"
            evidence("interim_proposal_state", page, sentence)

    dividends = []
    for page, text in enumerate(normalized, 1):
        section = re.search(r"[一二三四五六七八九十]+、资产负债表日后事项1、利润分配情况(.*?)2、销售退回", text)
        if not section:
            continue
        fiscal = re.search(r"审议通过(20\d{2})年度利润分配预案:", section[1])
        amounts = list(re.finditer(r"现金分红金额为"+MONEY+r"元\(含税\)", section[1]))
        if fiscal and len(amounts) == 1:
            amount = _decimal(amounts[0][1])
            if amount <= 0:
                raise ValueError("NATIVE_DIVIDEND_NONPOSITIVE")
            dividends.append((page, section[0], fiscal[1], amount))
    if len(dividends) > 1:
        raise ValueError("NATIVE_DIVIDEND_SCHEME_AMBIGUOUS")
    if dividends:
        page, excerpt, fiscal, amount = dividends[0]
        result.update(declared_ordinary_dividend_cny=str(amount), dividend_fiscal_year=fiscal,
            dividend_observation_basis="TAX_INCLUSIVE_FISCAL_SCHEME_TOTAL_NOT_PAYMENT")
        evidence("declared_ordinary_dividend_cny", page, excerpt)
    else:
        result["dividend_observation_basis"] = UNKNOWN

    approved = []
    for page, text in enumerate(normalized, 1):
        for match in re.finditer(r"本财务报表于(20\d{2})年([0-9]{1,2})月([0-9]{1,2})日由本公司董事会批准报出。", text):
            stamp = date(*map(int, match.groups())).isoformat()
            if stamp < period:
                raise ValueError("NATIVE_APPROVAL_BEFORE_REPORT_END")
            approved.append((page, match[0], stamp))
    if len(approved) > 1:
        raise ValueError("NATIVE_REPORT_APPROVAL_AMBIGUOUS")
    if approved:
        page, excerpt, stamp = approved[0]
        result["report_approved_date"] = stamp
        evidence("report_approved_date", page, excerpt)

    # Finite sentence grammar: exactly three named fiscal years, parent-profit
    # ratios and an explicit common CNY floor, preserving both qualifications.
    policy_pattern = (r"公司坚持实施积极的利润分配政策,在兼顾公司可持续发展的前提下.*?"
        r"公司制定了《(20\d{2})-(20\d{2})年度股东分红回报规划》:"
        r"\1-\2年度,公司每年度现金分红总额占当年归属于上市公司股东净利润的比例分别不低于"
        r"([0-9]+(?:\.[0-9]+)?)%、([0-9]+(?:\.[0-9]+)?)%、([0-9]+(?:\.[0-9]+)?)%,"
        r"且均不低于人民币([0-9]+(?:\.[0-9]+)?)亿元,原则上每年度可以进行两次现金分红。"
        r"未来,公司将在保证正常经营和长远发展的前提下,合理制定利润分配政策,切实让投资者分享企业的成长与发展成果。")
    policies = [(page, match) for page, text in enumerate(normalized, 1)
                for match in re.finditer(policy_pattern, text)]
    if len(policies) > 1:
        raise ValueError("NATIVE_DIVIDEND_POLICY_AMBIGUOUS")
    result["dividend_policy"] = dict(status=UNKNOWN, policies=[], evidence_pages=[],
        limitations=["仅财政年度政策原文观察；非滚动期下限、法律履约或付款完成证明。"])
    if policies:
        page, match = policies[0]
        first, last = int(match[1]), int(match[2])
        ratios = [Decimal(match[i])/100 for i in (3, 4, 5)]
        floor = Decimal(match[6])*Decimal(100000000)
        if last-first != 2 or not all(0 <= ratio <= 1 for ratio in ratios) or floor <= 0:
            raise ValueError("NATIVE_DIVIDEND_POLICY_RANGE_UNSUPPORTED")
        excerpt = _raw_excerpt(pages[page-1], match[0])
        result["dividend_policy"].update(status="VERIFIED", evidence_pages=[page],
            period_basis="FISCAL_YEAR_NOT_ROLLING", policies=[dict(fiscal_year=first+i,
                minimum_payout_ratio=str(ratio), minimum_distribution_cny=str(floor),
                currency="CNY", scope="consolidated_parent", physical_page=page, excerpt=excerpt)
                for i, ratio in enumerate(ratios)])
        evidence("dividend_policy", page, match[0])

    if kind in ("q1", "q3") and not capital and result["cancelled_shares"] != UNKNOWN:
        result["historical_cancelled_shares"] = result["cancelled_shares"]
        result["cancelled_shares"] = UNKNOWN
        result["cancellation_state"] = "HISTORICAL_RECALL_NOT_NEW_SHARE_REDUCTION"
    result["financial_update"] = _quarter_update(pages, normalized, period) if kind == "q3" else dict(status=UNKNOWN)
    result["unknowns"] = [field for field in (*fields, "published_date", "available_at",
        "historical_available_at", "payment_completion_state", "dividend_observation_basis")
        if result[field] == UNKNOWN]
    if result["dividend_policy"]["status"] == UNKNOWN:
        result["unknowns"].append("dividend_policy")
    result["kind"] = result["report_kind"]
    return result


def _quarter_update(pages, normalized, period):
    header = "本报告期本报告期比上年同期增减年初至报告期末年初至报告期末比上年同期增减"
    rows = []
    rate = r"-?[0-9]+(?:\.[0-9]+)?%"
    for page, text in enumerate(normalized, 1):
        if "主要会计数据和财务指标" not in text or header not in text:
            continue
        found = {}
        for field, label, scope in (("revenue_cny", "营业收入(元)", "consolidated"),
                ("parent_profit_cny", "归属于上市公司股东的净利润(元)", "consolidated_parent")):
            matches = list(re.finditer(re.escape(label)+MONEY+rate+MONEY+rate, text))
            if len(matches) != 1:
                return dict(status=UNKNOWN)
            match = matches[0]
            found[field] = dict(value=str(_decimal(match[2])), unit="CNY", scope=scope,
                physical_page=page, excerpt=_raw_excerpt(pages[page-1], match[0]))
        rows.append(found)
    if len(rows) > 1:
        raise ValueError("NATIVE_QUARTER_COLUMNS_AMBIGUOUS")
    if not rows:
        return dict(status=UNKNOWN)
    return dict(status="VERIFIED", period_start=period[:4]+"-01-01", period_end=period,
        period_basis="YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER", fields=rows[0],
        formal_eligibility=False, action="no_order")


def _announcement(pages, normalized, symbol):
    head = "".join(normalized[:2])
    codes = set(re.findall(r"证券代码:?([0-9]{6})(?![0-9])", head))
    names = re.findall(r"[\u4e00-\u9fff]+股份(?:有限公司|公司)", head)
    if codes != {symbol} or not names or "摘要" in normalized[0]:
        raise ValueError("NATIVE_NOTICE_ISSUER_IDENTITY_REQUIRED")
    issuer = names[0]
    signed = list(re.finditer(r"董事会(20\d{2})年([0-9]{1,2})月([0-9]{1,2})日$", normalized[-1]))
    if len(signed) != 1:
        raise ValueError("NATIVE_NOTICE_SIGNED_DATE_REQUIRED")
    signed_date = date(*map(int, signed[0].groups())).isoformat()
    is_dividend = re.search(r"(20\d{2})年度分红派息实施公告", normalized[0])
    is_unlock = "解除限售股份上市流通的提示性公告" in normalized[0]
    if not is_dividend and not is_unlock:
        raise ValueError("NATIVE_NOTICE_STRUCTURE_UNSUPPORTED")
    result = dict(parser_version=VERSION, status="VERIFIED", symbol=symbol, issuer_name=issuer,
        report_kind="dividend_implementation" if is_dividend else "share_unlock_notice",
        report_period=is_dividend[1]+"-12-31" if is_dividend else signed_date,
        observation_date=signed_date, published_date=UNKNOWN, available_at=UNKNOWN,
        historical_available_at=UNKNOWN, payment_completion_state=UNKNOWN,
        ordinary_shares=UNKNOWN, shares_before=UNKNOWN, cancelled_shares=UNKNOWN,
        historical_cancelled_shares=UNKNOWN, declared_ordinary_dividend_cny=UNKNOWN,
        dividend_fiscal_year=UNKNOWN, closing_continuity_proven=False,
        opening_pending_actions_complete=False, formal_eligibility=False, action="no_order",
        dividend_policy=dict(status=UNKNOWN, policies=[], evidence_pages=[]),
        financial_update=dict(status=UNKNOWN), term_pages={}, evidence_refs=[])
    result["period_end"] = result["report_period"]

    def record(field, page, excerpt):
        result["term_pages"].setdefault(field, []).append(page)
        result["evidence_refs"].append(dict(field=field, physical_page=page,
            excerpt=_raw_excerpt(pages[page-1], excerpt)))

    record("observation_date", len(pages), signed[0][0])
    if is_dividend:
        total = [(i, m) for i, text in enumerate(normalized, 1) for m in
                 re.finditer(r"现金分红金额为"+MONEY+r"元\(含税\)", text)]
        base = [(i, m) for i, text in enumerate(normalized, 1) if "二、本次实施的利润分配方案" in text
                for m in re.finditer(r"以公司现有总股本剔除已回购股份"+INTEGER+r"股后的"+INTEGER
                    +r"股为基数,向全体股东每10股派([0-9]+\.[0-9]+)元人民币现金", text)]
        roll = [(i, m) for i, text in enumerate(normalized, 1) for m in re.finditer(
            r"公司总股本由"+INTEGER+r"股变动至"+INTEGER+r"股", text)]
        if len(total) != 1 or len(base) != 1 or len(roll) != 1:
            raise ValueError("NATIVE_DIVIDEND_IMPLEMENTATION_FIELDS_UNSUPPORTED")
        old, new = map(_decimal, roll[0][1].groups())
        excluded, quantity = map(_decimal, base[0][1].groups()[:2])
        if min(old, new, quantity) <= 0 or excluded < 0 or new-excluded != quantity:
            raise ValueError("NATIVE_DIVIDEND_SHARE_BASE_CONFLICT")
        amount = _decimal(total[0][1][1])
        per_ten = Decimal(base[0][1][3])
        # Each printed amount represents a rounding interval, not an exact
        # multiplication identity. Propagate half of each last displayed unit.
        with localcontext() as arithmetic:
            arithmetic.prec = 80
            implied = per_ten*quantity/Decimal(10)
            tolerance = (Decimal(1).scaleb(per_ten.as_tuple().exponent)*quantity/Decimal(10)
                + Decimal(1).scaleb(amount.as_tuple().exponent))/Decimal(2)
            if amount <= 0 or per_ten <= 0 or abs(implied-amount) > tolerance:
                raise ValueError("NATIVE_DIVIDEND_AMOUNT_OUTSIDE_DISCLOSED_PRECISION")
        result.update(ordinary_shares=str(new), shares_before=str(old),
            distribution_base_shares=str(quantity), excluded_repurchase_shares=str(excluded),
            declared_ordinary_dividend_cny=str(_decimal(total[0][1][1])),
            dividend_fiscal_year=is_dividend[1], dividend_per_10_shares_cny=base[0][1][3],
            dividend_observation_basis="IMPLEMENTATION_ARRANGEMENT_NOT_ACCOUNT_RECEIPT",
            historical_cancelled_shares=str(old-new),
            cancellation_state="SCHEME_ADJUSTMENT_RECALL_NOT_ADDITIONAL_CANCELLATION")
        record("ordinary_shares", roll[0][0], roll[0][1][0])
        record("distribution_base_shares", base[0][0], base[0][1][0])
        record("declared_ordinary_dividend_cny", total[0][0], total[0][1][0])
        for field, pattern in (("record_date", r"股权登记日:"), ("ex_date", r"除权除息日:"),
                ("agency_payment_date", r"公司此次委托中国结算深圳分公司代派的A股股东现金红利将于")):
            matches = [(i, m) for i, text in enumerate(normalized, 1) for m in
                re.finditer(pattern+r"(20\d{2})年([0-9]{1,2})月([0-9]{1,2})日", text)]
            if len(matches) != 1:
                raise ValueError("NATIVE_DIVIDEND_SCHEDULE_UNSUPPORTED")
            page, match = matches[0]
            result[field] = date(*map(int, match.groups())).isoformat()
            record(field, page, match[0])
        if not signed_date <= result["record_date"] <= result["ex_date"] == result["agency_payment_date"]:
            raise ValueError("NATIVE_DIVIDEND_SCHEDULE_CONFLICT")
        result["payment_scope"] = "CSDC_AGENCY_SCHEDULE_WITH_COMPANY_SELF_DISTRIBUTION_NOT_ACCOUNT_RECEIPT"
    else:
        tables = [(i, text) for i, text in enumerate(normalized, 1)
                  if "五、本次解除限售股本结构变化情况" in text]
        if len(tables) != 1:
            raise ValueError("NATIVE_UNLOCK_QUANTITY_TABLE_REQUIRED")
        page, text = tables[0]
        header = "股份类别变动前本次变动(-/+,股)变动后股份数(股)比例(%)股份数(股)比例(%)"
        qualification = "以上股本结构实际变动结果以限制性股票解除限售事项完成后中国证券登记结算有限责任公司深圳分公司出具的股本结构表为准。"
        total = re.search(r"总计"+INTEGER+r"100-"+INTEGER+r"100", text)
        if header not in text or qualification not in text or total is None:
            raise ValueError("NATIVE_UNLOCK_COLUMNS_OR_QUALIFICATION_REQUIRED")
        before, after = map(_decimal, total.groups())
        if before <= 0 or before != after:
            raise ValueError("NATIVE_UNLOCK_TOTAL_SHARE_CHANGE_UNSUPPORTED")
        result.update(ordinary_shares=str(after), shares_before=str(before), net_share_change="0",
            share_observation_state="SCHEDULED_CLASS_TRANSFER_SUBJECT_TO_CSDC_STRUCTURE",
            share_table_qualification=_raw_excerpt(pages[page-1], qualification))
        record("ordinary_shares", page, total[0])
        record("share_table_qualification", page, qualification)
        dates = [(i, m) for i, text in enumerate(normalized, 1) for m in re.finditer(
            r"本次解除限售的限制性股票上市流通日为(20\d{2})年([0-9]{1,2})月([0-9]{1,2})日", text)]
        if len(dates) != 1:
            raise ValueError("NATIVE_UNLOCK_EFFECTIVE_DATE_REQUIRED")
        result["share_effective_date"] = date(*map(int, dates[0][1].groups())).isoformat()
        record("share_effective_date", dates[0][0], dates[0][1][0])
        historical = []
        for i, text in enumerate(normalized, 1):
            for match in re.finditer(r"限制性股票"+INTEGER+r"股,同时[^。]*。前述股份已于"
                    r"(20\d{2})年([0-9]{1,2})月([0-9]{1,2})日回购注销完成。", text):
                stamp = date(*map(int, match.groups()[1:])).isoformat()
                if stamp[:4] == signed_date[:4]:historical.append((i, match, stamp))
        if len(historical) != 1 or historical[0][2] > signed_date:
            raise ValueError("NATIVE_UNLOCK_HISTORICAL_CANCELLATION_UNSUPPORTED")
        i, match, stamp = historical[0]
        result.update(historical_cancelled_shares=str(_decimal(match[1])),
            historical_cancellation_date=stamp,
            cancellation_state="HISTORICAL_RECALL_NOT_NEW_SHARE_REDUCTION")
        record("historical_cancelled_shares", i, match[0])
    result["unknowns"] = [key for key, value in result.items() if isinstance(value, str) and value == UNKNOWN]
    result["unknowns"].append("dividend_policy")
    result["kind"] = result["report_kind"]
    return result

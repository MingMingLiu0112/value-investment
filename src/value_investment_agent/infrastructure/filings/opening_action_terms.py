"""Bounded original-body opening actions, not complete coverage or approval.

Caller must verify PDF bytes, official publication URL/date and availability.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
import re
import unicodedata

PARSER_VERSION = "opening-action-terms-v2"
ADJUSTMENT = "CONFIRMED_CANCELLATION_AND_ANNUAL_DISTRIBUTION_ADJUSTMENT"
AUTHORIZATION = "INTERIM_DISTRIBUTION_AUTHORIZATION"
NUM = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
DAY = r"20\d{2}年\d{1,2}月\d{1,2}日"


def _day(text):
    return date(*map(int, re.fullmatch(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text).groups()))


def _num(text):
    return Decimal(text.replace(",", ""))


def parse_opening_action_terms(pages, *, symbol):
    if (not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)
            or not isinstance(pages, list) or len(pages) not in (3, 7)
            or any(not isinstance(p, str) or not p.strip() for p in pages)
            or sum(map(len, pages)) > 100_000):
        raise ValueError("OPENING_BOUNDED_COMPLETE_ORIGINAL_REQUIRED")
    normalized = []
    for i, page in enumerate(pages, 1):
        lines = [s.strip() for s in page.splitlines() if s.strip()]
        if lines[0] != str(i):
            raise ValueError("OPENING_PAGE_SEQUENCE_REQUIRED")
        normalized.append(re.sub(r"\s+", "", unicodedata.normalize("NFKC", "".join(lines[1:]))))
    text = "".join(normalized)
    if any(word in text for word in ("更正", "修订", "撤销", "取消", "作废")):
        raise ValueError("OPENING_CHANGED_DOCUMENT_REQUIRES_REVIEW")
    if re.findall(r"证券代码:([0-9]{6})", text) != [symbol]:
        raise ValueError("OPENING_ISSUER_MISMATCH")
    term_pages = {}

    def find(pattern, field):
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise ValueError("OPENING_FIELD_MISSING_OR_AMBIGUOUS: " + field)
        match, offset, locations = matches[0], 0, []
        for i, page in enumerate(normalized, 1):
            if match.start() < offset + len(page) and match.end() > offset:
                locations.append(i)
            offset += len(page)
        term_pages[field] = locations
        return match

    issuer = find(r"(?:公告)?编号:临(20\d{2})-[0-9]+([\u4e00-\u9fff]+股份有限公司)", "issuer")
    footer = find(re.escape(issuer[2]) + r"董事会(" + DAY + r")$", "publication")
    published = _day(footer[1])
    if int(issuer[1]) != published.year:
        raise ValueError("OPENING_PUBLICATION_YEAR_CONFLICT")
    if len(pages) == 3:
        effective, terms = _adjustment(find, published)
        event_type = ADJUSTMENT
        summary = "原件确认回购股份已注销，并披露年度分配每股金额调整及舍入规则。"
        implication = "可补该次回购的期初注销及年度调整链；不是比较日股本或期间无分配证明。"
        fields = ["ordinary_shares", "treasury_shares", "opening_pending_actions", "annual_distribution_terms"]
    else:
        effective, terms = _authorization(find, published)
        event_type = AUTHORIZATION
        summary = "股东会通过年度分配，并有条件授权董事会制定中期方案及组织实施。"
        implication = "中期授权仍须跟踪；不是已定方案、已实施事件或确定现金义务。"
        fields = ["opening_pending_actions", "distribution_authorization", "annual_distribution_terms"]
    return dict(parser_version=PARSER_VERSION, published_date=published.isoformat(),
        event_type=event_type, effective_date=effective.isoformat(), symbol=symbol,
        summary=summary, implication=implication, terms=terms, affected_model_fields=fields,
        term_pages=term_pages, action="no_order", limitations=[
            "CALLER_MUST_BIND_ORIGINAL_HASH_OFFICIAL_URL_DATE_AND_ACTUAL_AVAILABILITY",
            "NO_COMPLETE_ACTION_OR_AMENDMENT_COVERAGE", "NO_COMPARISON_DATE_SHARE_CONTINUITY",
            "NO_PAYMENT_RECEIPT_OR_MODEL_INCLUSION_PROOF", "NO_MATERIALITY_OR_G3_APPROVAL"])


def _adjustment(find, published):
    title = find(r"关于调整(20\d{2})年年度利润分配方案每股分红金额的公告", "title")
    fiscal = int(title[1])
    changed = find(r"每股拟派发现金红利金额:由(" + NUM + r")元\(含税\)调整为(" + NUM + r")元\(含税\)。", "per_share_adjustment")
    current = find(r"截至本公告日,公司总股本为(" + NUM + r")股,回购专用证券账户内股份数为(" + NUM
        + r")股,总股本扣除回购专用证券账户内的股份数为(" + NUM + r")股。", "current_capital")
    cancel = find(r"(" + DAY + r"),公司披露了《关于股份回购实施结果暨股份变动的公告》,公司回购股份实施完成,实际回购公司股份(" + NUM
        + r")股,并于(" + DAY + r")在中国证券登记结算有限责任公司上海分公司将全部回购股份注销。截至本公告披露日,公司总股本为(" + NUM + r")股", "confirmed_cancellation")
    original = find(r"截至(" + DAY + r"),公司总股本为(" + NUM + r")股,回购专用账户内的股份数为(" + NUM
        + r")股,总股本扣除回购专用账户内的股份数为(" + NUM + r")股,以此计算合计拟派发现金红利(" + NUM + r")元\(含税\)。", "original_capital")
    board = find(r"公司于(" + DAY + r")召开第四届董事会(20\d{2})年度第六次会议,审议通过了《关于(20\d{2})年年度利润分配方案及(20\d{2})年中期利润分配安排的议案》", "original_board")
    original_dps = find(r"实施(20\d{2})年年度利润分配,向全体股东每股派发现金红利(" + NUM + r")元\(含税\),截至", "original_per_share")
    headline = find(r"公司将按照维持分配总额不变的原则,调整后每股派发现金红利(" + NUM + r")元\(含税\),共计派发现金红利(" + NUM + r")元\(含税\),与董事会决议金额不一致系每股现金红利的尾数四舍五入所致。", "headline_amounts")
    formula = find(r"调整后每股派发现金红利=原定利润分配总额÷\(公司总股本-回购专用证券账户内股份数\)=(" + NUM
        + r")÷\((" + NUM + r")-(" + NUM + r")\)=(" + NUM + r")元\(含税,四舍五入保留小数点后五位\)", "per_share_precision")
    total_formula = find(r"利润分配总额=调整后每股派发现金红利×\(公司总股本-回购专用证券账户内股份数\)=(" + NUM
        + r")×\((" + NUM + r")-(" + NUM + r")\)=(" + NUM + r")元\(含税,保留小数点后两位\)", "total_precision")
    closing = find(r"综上所述,公司(20\d{2})年年度利润分配以方案实施前总股本扣除回购专用证券账户内的股份数(" + NUM
        + r")股为基数,每股派发现金红利(" + NUM + r")元\(含税\),共计派发现金红利(" + NUM
        + r")元\(含税\),与董事会决议金额不一致系每股现金红利的尾数四舍五入所致。", "adjusted_scheme")
    issued, treasury, eligible = map(_num, current.groups())
    cancelled = _num(cancel[2])
    old_issued, old_treasury, old_eligible = map(_num, original.groups()[1:4])
    old_dps, dps, old_total, total = _num(changed[1]), _num(changed[2]), _num(original[5]), _num(total_formula[4])
    effective = _day(cancel[3])
    if (not _day(original[1]) <= _day(board[1]) <= _day(cancel[1]) <= effective <= published
            or published.year != fiscal + 1 or int(closing[1]) != fiscal
            or [int(board[2]), int(board[3]), int(board[4]), int(original_dps[1])]
            != [published.year, fiscal, published.year, fiscal]):
        raise ValueError("OPENING_ADJUSTMENT_DATE_OR_PERIOD_CONFLICT")
    shares = [issued, treasury, eligible, cancelled, old_issued, old_treasury, old_eligible]
    if (any(v < 0 or v != v.to_integral_value() for v in shares) or treasury != 0
            or min(issued, eligible, cancelled, old_issued, old_eligible) <= 0
            or issued - treasury != eligible or old_issued - old_treasury != old_eligible
            or old_issued - cancelled != issued or _num(cancel[4]) != issued):
        raise ValueError("OPENING_CAPITAL_RECONCILIATION_CONFLICT")
    with localcontext() as context:
        context.prec = 80
        if (min(old_dps, dps, old_total, total) <= 0
                or _num(original_dps[2]) != old_dps or list(map(_num, headline.groups())) != [dps, total]
                or (old_dps * old_eligible).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != old_total
                or (old_total / eligible).quantize(Decimal('.00001'), rounding=ROUND_HALF_UP) != dps
                or (dps * eligible).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != total
                or list(map(_num, formula.groups())) != [old_total, issued, treasury, dps]
                or list(map(_num, total_formula.groups())) != [dps, issued, treasury, total]
                or list(map(_num, closing.groups()[1:])) != [eligible, dps, total]
                or len(changed[2].split('.')[-1]) != 5):
            raise ValueError("OPENING_DISTRIBUTION_ARITHMETIC_OR_PRECISION_CONFLICT")
    return effective, dict(confirmed_cancellation_date=effective.isoformat(), cancelled_shares=str(cancelled),
        issued_shares=str(issued), treasury_shares=str(treasury), treasury_zero=True,
        capital_as_of=published.isoformat(), annual_distribution_year=fiscal,
        eligible_distribution_shares=str(eligible), previous_cash_per_share=str(old_dps),
        annual_cash_per_share=str(dps), original_annual_total_cash_cny=str(old_total),
        annual_total_cash_cny=str(total), currency="CNY", amount_basis="GROSS_PRETAX_PROPOSED_ADJUSTMENT",
        per_share_decimal_places=5, total_decimal_places=2, rounding="ROUND_HALF_UP",
        precision_text=formula[0], total_precision_text=total_formula[0],
        explanation_text="与董事会决议金额不一致系每股现金红利的尾数四舍五入所致。",
        implementation_verified=False, accounting_one_cent_difference_resolved=False, follow_up_required=True)



def _authorization(find, published):
    title = find(r"(20\d{2})年度股东会决议公告", "title")
    fiscal = int(title[1])
    meeting = find(r"股东会召开的时间:(" + DAY + r")", "meeting_date")
    effective = _day(meeting[1])
    # This layout prints nonzero vote counts in grouped thousands. Require
    # those cell boundaries rather than greedily consuming percentage digits.
    count = r"((?:[1-9][0-9]{0,2}(?:,[0-9]{3})+|0))"
    percent = r"((?:100|[1-9]?[0-9])\.[0-9]{4})"
    attendance = find(r"出席会议的股东所持有表决权的股份总数\(股\)(" + NUM + r")3\.", "eligible_votes")
    vote = find(r"4\.议案名称:《关于(20\d{2})年年度利润分配方案及(20\d{2})年中期利润分配安排的议案》"
        r"审议结果:通过表决情况:股东类型同意反对弃权票数比例\(%\)票数比例\(%\)票数比例\(%\)"
        r"A股" + (count + percent) * 3 + r"会议决定,", "annual_vote")
    eligible_votes = _num(attendance[1])
    votes = [_num(vote[i]) for i in (3, 5, 7)]
    percentages = [_num(vote[i]) for i in (4, 6, 8)]
    with localcontext() as context:
        context.prec = 80
        if (eligible_votes <= 0 or eligible_votes != eligible_votes.to_integral_value()
                or sum(votes) != eligible_votes or any(not 0 <= p <= 100 for p in percentages)
                or any((v * 100 / eligible_votes).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP) != p
                       for v, p in zip(votes, percentages))):
            raise ValueError("OPENING_VOTE_COUNTS_OR_PERCENTAGES_CONFLICT")
        # Supported ordinary, non-recused proposal: affirmative votes must
        # exceed half of all represented voting shares, including abstentions.
        if votes[0] * 2 <= eligible_votes:
            raise ValueError("OPENING_PASSED_LABEL_NOT_SUPPORTED_BY_VOTES")
    annual = find(r"会议决定,公司以实施权益分派股权登记日登记的总股本扣除回购专用账户内的股份为基数,实施(20\d{2})年年度利润分配,向全体股东每股派发现金红利(" + NUM
        + r")元\(含税\)。截至(" + DAY + r"),公司总股本为(" + NUM + r")股,回购专用账户内的股份数为(" + NUM
        + r")股,总股本扣除回购专用账户内的股份数为(" + NUM + r")股,以此计算合计拟派发现金红利(" + NUM
        + r")元\(含税\)。在实施权益分派的股权登记日前公司总股本扣除回购专用账户内的股份数如发生变动的,将维持分配总额不变,相应调整每股分配比例。", "annual_approved_terms")
    authority = find(r"股东会授权董事会在符合《公司章程》利润分配的条件下,结合公司生产经营状况、未来发展资金需求、经营现金流等因素,制定(20\d{2})年中期利润分配方案并组织实施,"
        r"分红金额上限不超过公司(20\d{2})年上半年实现归属于上市公司股东的净利润。", "interim_authorization")
    as_of = _day(annual[3])
    if (not as_of <= effective <= published or not published.year == effective.year == fiscal + 1
            or [int(vote[1]), int(vote[2]), int(annual[1]), int(authority[1]), int(authority[2])]
            != [fiscal, fiscal+1, fiscal, fiscal+1, fiscal+1]):
        raise ValueError("OPENING_AUTHORIZATION_DATE_OR_PERIOD_CONFLICT")
    issued, treasury, eligible = map(_num, annual.groups()[3:6])
    dps, total = _num(annual[2]), _num(annual[7])
    with localcontext() as context:
        context.prec = 80
        if (any(v != v.to_integral_value() for v in (issued, treasury, eligible))
                or treasury != 0 or min(issued, eligible, dps, total) <= 0 or issued - treasury != eligible
                or (dps * eligible).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != total):
            raise ValueError("OPENING_APPROVED_ANNUAL_TERMS_CONFLICT")
    return effective, dict(annual_distribution_year=fiscal,
        annual_vote=dict(eligible_votes=str(eligible_votes), agree_votes=str(votes[0]),
            against_votes=str(votes[1]), abstain_votes=str(votes[2]),
            percentages=[str(p) for p in percentages], percentage_decimal_places=4,
            simple_majority_verified=True),
        annual_cash_per_share=str(dps), annual_total_cash_cny=str(total),
        issued_shares=str(issued), treasury_shares=str(treasury), treasury_zero=True,
        eligible_distribution_shares=str(eligible), capital_as_of=as_of.isoformat(),
        currency="CNY", amount_basis="GROSS_PRETAX_ANNUAL_APPROVED_SCHEME",
        authorization_period_text=authority[1] + "年中期", authorization_text=authority[0],
        amount_cap_text="分红金额上限不超过公司" + authority[2] + "年上半年实现归属于上市公司股东的净利润。",
        authorization_expiry_date=None, authorization_expiry_status="NOT_DISCLOSED_IN_CLAUSE",
        authorization_status="CONDITIONAL_AUTHORIZATION_REQUIRES_FOLLOW_UP",
        scheme_determined=False, implementation_verified=False, cash_obligation_established=False,
        interim_cash_per_share=None, interim_total_cash_cny=None, follow_up_required=True)

"""Direct tests for bounded terms; optional original replay never changes inputs."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings.operating_event_terms import (
    VERSION, parse_operating_event_terms,
)

# TEST_ONLY complete prose fixtures; issuer/symbol differ from the real sources.
PRICE = ['证券代码：000777 证券简称：示例酒业 公告编号：临 2026-028\r\n示例酒业股份有限公司\r\n重大事项公告\r\n本公司董事会及全体董事保证本公告内容不存在任何虚假记载、误导性陈述或者\r\n重大遗漏，并对其内容的真实性、准确性和完整性承担法律责任。 根据《2026 年示例酒业酒市场化运营方案》，按照“随行就市、相对\r\n平稳、供需适配、量价平衡”的原则，为有效维护市场秩序，经研究决定，\r\n本公司自 2026 年 7 月 18 日零时起，将飞天 53%vol 500ml 示例酒业酒\r\n（2026）i 茅台平台零售价由 1539 元/瓶调整为 1639 元/瓶、销售合同价\r\n由 1269 元/瓶调整为 1369 元/瓶。\r\n此次价格调整将会对本公司经营业绩产生一定影响，敬请投资者理性\r\n投资，注意风险。\r\n特此公告。\r\n示例酒业股份有限公司董事会\r\n2026 年 7 月 18 日']

BOARD = ['1\r\n证券简称：示例酒业 证券代码：000777 编号：临 2026－029\r\n示例酒业股份有限公司\r\n第五届董事会 2026 年度第三次会议\r\n决议公告\r\n本公司董事会及全体董事保证本公告内容不存在任何虚假记载、误导性陈述或者重\r\n大遗漏，并对其内容的真实性、准确性和完整性承担法律责任。 一、董事会会议召开情况\r\n2026 年 7 月 6 日，示例酒业股份有限公司（以下简称“公司”）以直\r\n接送达或电子邮件的方式，向全体董事发出召开第五届董事会 2026 年度第\r\n三次会议（以下简称“会议”）的通知。2026 年 8 月 13 日，会议以现场结合\r\n通讯表决方式在公司会议中心召开。会议应出席董事 7 人，实际出席董事\r\n7 人（其中董事周雪因工作原因以通讯方式出席会议）。会议由董事长陈\r\n华主持，公司部分高级管理人员列席了会议。会议的召开符合《中华人民\r\n共和国公司法》等法律、行政法规和《公司章程》的规定。\r\n二、董事会会议审议情况\r\n（ 一 ）《 2026 年 半 年 度 报 告 》（ 详 见 上 海 证 券 交 易 所 网 站\r\nhttp://www.sse.com.cn）\r\n同意：7 票；反对：0 票；弃权：0 票。议案获得通过。\r\n公司董事会审计委员会事前已审议通过本议案，并同意提交董事会审\r\n议。\r\n（二）《关于将 i 茅台数字营销平台相关资产无偿划转至爱茅台数字科', '2\r\n技公司的议案》\r\n同意：7 票；反对：0 票；弃权：0 票。议案获得通过。\r\n会议决定，公司以无偿划转方式，向公司全资子公司贵州爱茅台数字\r\n科技有限公司（以下简称“数科公司”）划转 i 茅台数字营销平台相关信息\r\n系统及域名等，在授权范围内向数科公司转授权使用“DEMO”等商标。\r\n（三）《2026 年度“提质增效重回报”行动方案半年度评估报告》\r\n同意：7 票；反对：0 票；弃权：0 票。议案获得通过。\r\n特此公告。\r\n示例酒业股份有限公司董事会\r\n2026 年 8 月 15 日']

ACCOUNTING = ['1\r\n证券简称：示例酒业 证券代码：000777 编号：临 2026－030\r\n示例酒业股份有限公司\r\n关于会计政策变更的公告\r\n本公司董事会及全体董事保证本公告内容不存在任何虚假记载、误导性陈述或者\r\n重大遗漏，并对其内容的真实性、准确性和完整性承担法律责任。 重要内容提示：\r\n●示例酒业股份有限公司（以下简称“公司”）根据中华人民共和\r\n国财政部（以下简称“财政部”）相关规定进行的会计政策变更，不会对\r\n公司财务状况、经营成果和现金流量产生重大影响。\r\n一、本次会计政策变更概述\r\n（一）会计政策变更的原因\r\n2025 年 12 月 5 日，财政部发布了《企业会计准则解释第 19 号》（财\r\n会〔2025〕32 号），对“关于非同一控制下企业合并中补偿性资产的会计\r\n处理”、“关于处置原通过同一控制下企业合并取得子公司时相关资本公积\r\n的会计处理”、“关于采用电子支付系统结算的金融负债的终止确认”、“关\r\n于金融资产合同现金流量特征的评估及相关披露”和“关于指定为以公允\r\n价值计量且其变动计入其他综合收益的权益工具的披露”的内容进行进一\r\n步规范及明确，本解释自 2026 年 1 月 1 日起施行。', '2\r\n2026 年 6 月 4 日，财政部发布了《企业会计准则解释第 20 号》（财\r\n会〔2026〕7 号），对“关于金融资产合同现金流量特征的评估”、“关于\r\n货币缺乏可兑换性时的会计处理及相关披露”等内容进行进一步规范及明\r\n确。本解释自公布之日起施行，2026 年 1 月 1 日至本解释施行日新增的\r\n本解释规定的业务，企业应当根据本解释进行调整。\r\n（二）变更前采用的会计政策\r\n本次会计政策变更前，公司执行财政部发布的《企业会计准则——基\r\n本准则》和各项具体会计准则、企业会计准则应用指南、企业会计准则解\r\n释公告以及其他相关规定。\r\n（三）变更后采用的会计政策\r\n本次会计政策变更后，公司将按照财政部发布的《企业会计准则解释\r\n第 19 号》及《企业会计准则解释第 20 号》要求执行。除上述会计政策变\r\n更外，其余未变更部分，仍执行财政部发布的《企业会计准则——基本准\r\n则》和各项具体会计准则、企业会计准则应用指南、企业会计准则解释公\r\n告以及其他相关规定。\r\n（四）会计政策变更日期\r\n公司按照上述文件规定的施行时间执行变更后的相关会计政策。\r\n二、本次会计政策变更对公司的影响\r\n本次会计政策变更是公司根据财政部发布的《企业会计准则解释第\r\n19 号》（财会〔2025〕32 号）及《企业会计准则解释第 20 号》（财会〔2026〕', '3\r\n7 号）的要求进行的变更，变更后的会计政策能够更加客观、公允地反映\r\n公司的财务状况、经营成果和现金流量，本次会计政策变更不涉及对公司\r\n以前年度的追溯调整，对公司财务状况、经营成果和现金流量无重大影响，\r\n不存在损害公司及全体股东利益的情形。\r\n特此公告。\r\n示例酒业股份有限公司董事会\r\n2026 年 8 月 15 日']


def parse(pages):
    return parse_operating_event_terms(pages, symbol="000777")


def replace(pages, old, new):
    assert sum(page.count(old) for page in pages) >= 1
    return [page.replace(old, new) for page in pages]


def assert_evidence(result, pages):
    assert result["action"] == "no_order"
    assert result["parser_version"] == VERSION
    assert result["summary"] and result["implication"] and result["limitations"]
    assert result["affected_model_fields"]
    assert result["physical_pages"] == sorted({e["physical_page"] for e in result["evidence_excerpts"]})
    for excerpt in result["evidence_excerpts"]:
        assert excerpt["text"] in pages[excerpt["physical_page"] - 1]
        assert excerpt["field"]
    # No admission/absence gate is created by extraction.
    assert not {"materiality_approved", "capital_nochange", "model_validity", "formal_eligibility"} & result.keys()


def test_price_keeps_channels_dates_units_and_scope_separate():
    before = deepcopy(PRICE)
    result = parse(PRICE)
    terms = result["terms"]
    assert result["event_type"] == "OPERATING_PRICE_CHANGE"
    assert result["published_date"] == result["effective_date"] == "2026-07-18"
    assert terms["effective_at"] == "2026-07-18T00:00:00+08:00"
    assert terms["retail_price"]["before"] == "1539"
    assert terms["retail_price"]["after"] == "1639"
    assert terms["sales_contract_price"]["before"] == "1269"
    assert terms["sales_contract_price"]["after"] == "1369"
    assert terms["retail_price"]["unit"] == terms["sales_contract_price"]["unit"] == "CNY/bottle"
    assert "53%vol500ml" in terms["product_scope"]
    assert "(2026)" in terms["product_scope"]
    assert terms["retail_price"]["channel"] == "i茅台平台"
    assert terms["realized_revenue_effect"] is None
    assert terms["tax_basis"] == "NOT_DISCLOSED"
    assert result["physical_pages"] == [1]
    assert "不能" in result["implication"]
    assert_evidence(result, PRICE)
    assert PRICE == before


def test_parser_not_symbol_or_amount_hardcoded_and_dates_not_conflated():
    pages = replace(PRICE, "000777", "123456")
    pages = replace(pages, "1539", "1000.50")
    pages = replace(pages, "1369", "990.25")
    # The final disclosure date can differ from the expressly stated effective date.
    pages[-1] = pages[-1].rsplit("2026 年 7 月 18 日", 1)[0] + "2026 年 7 月 19 日"
    result = parse_operating_event_terms(pages, symbol="123456")
    assert result["symbol"] == "123456"
    assert result["issuer_name"] == "示例酒业股份有限公司"
    assert result["published_date"] == "2026-07-19"
    assert result["effective_date"] == "2026-07-18"
    assert result["terms"]["retail_price"]["before"] == "1000.50"
    assert result["terms"]["sales_contract_price"]["after"] == "990.25"


def test_board_is_resolution_not_completed_transfer_and_scope_is_preserved():
    result = parse(BOARD)
    terms = result["terms"]
    assert result["event_type"] == "INTERNAL_ASSET_TRANSFER_RESOLUTION"
    assert result["published_date"] == "2026-08-15"
    assert result["effective_date"] is None
    assert terms["resolution_date"] == "2026-08-13"
    assert terms["completion_date"] is terms["asset_value_cny"] is None
    assert terms["execution_status"] == "RESOLUTION_ONLY_COMPLETION_NOT_EVIDENCED"
    assert terms["recipient_relationship"] == "WHOLLY_OWNED_SUBSIDIARY"
    assert "信息系统及域名" in terms["asset_scope"]
    assert "在授权范围内" in terms["trademark_scope"]
    assert "DEMO" in terms["trademark_scope"]
    assert len(terms["other_resolutions"]) == 2
    assert result["physical_pages"] == [1, 2]
    assert "不证明已完成" in result["summary"]
    assert_evidence(result, BOARD)


def test_accounting_is_issuer_statement_with_two_effective_dates():
    result = parse(ACCOUNTING)
    terms = result["terms"]
    assert result["event_type"] == "ACCOUNTING_POLICY_IMPACT_STATEMENT"
    assert result["published_date"] == "2026-08-15"
    assert result["effective_date"] is None
    assert terms["standards"] == [
        {"interpretation": "19", "issued_date": "2025-12-05", "effective_date": "2026-01-01"},
        {"interpretation": "20", "issued_date": "2026-06-04", "effective_date": "2026-06-04",
         "transition_new_transactions_from": "2026-01-01"},
    ]
    assert terms["assessment_basis"] == "ISSUER_STATEMENT_NOT_INDEPENDENT_APPROVAL"
    assert "不涉及" in terms["issuer_prior_year_statement"]
    assert "无重大影响" in terms["issuer_impact_statement"]
    assert "不能据此批准" in result["implication"]
    assert result["physical_pages"] == [1, 2, 3]
    assert_evidence(result, ACCOUNTING)


@pytest.mark.parametrize("pages,old,new", [
    (PRICE, "1539", "0"),
    (PRICE, "1639", "-1639"),
    (PRICE, "元/瓶", "元/吨"),
    (PRICE, "零售价", "销售合同价"),
    (PRICE, "销售合同价", "出厂估计价"),
    (PRICE, "i 茅台平台", "所有渠道"),
    (PRICE, "2026 年 7 月 18 日零时", "2026 年 2 月 30 日零时"),
    (PRICE, "2026 年 7 月 18 日零时", "2027 年 7 月 18 日零时"),
    (PRICE, "一定影响", "无重大影响"),
    (BOARD, "会议决定", "公司已完成"),
    (BOARD, "无偿划转", "有偿划转"),
    (BOARD, "全资子公司", "控股子公司"),
    (BOARD, "在授权范围内", "永久无限制"),
    (BOARD, "等商标", "等商标所有权"),
    (BOARD, "2026 年 8 月 13 日", "2026 年 8 月 16 日"),
    (BOARD, "2026 年 7 月 6 日", "2026 年 9 月 6 日"),
    (BOARD, "反对：0 票", "反对：1 票"),
    (ACCOUNTING, "无重大影响", "有重大影响"),
    (ACCOUNTING, "不涉及对公司", "涉及对公司"),
    (ACCOUNTING, "2026 年 6 月 4 日", "2026 年 9 月 4 日"),
    (ACCOUNTING, "2025 年 12 月 5 日", "2027 年 12 月 5 日"),
    (ACCOUNTING, "以前年度", "所有期间"),
])
def test_changed_or_unsupported_prose_is_rejected(pages, old, new):
    with pytest.raises(ValueError, match="OPERATING_EVENT_"):
        parse(replace(pages, old, new))


@pytest.mark.parametrize("pages", [PRICE, BOARD, ACCOUNTING])
def test_identity_signature_extra_clause_and_truncation_fail_closed(pages):
    cases = [
        replace(pages, "000777", "999999"),
        [*pages[:-1], pages[-1].replace("示例酒业股份有限公司董事会", "其他酒业股份有限公司董事会")],
        [*pages[:-1], pages[-1].replace("特此公告。", "另有未披露的重大交易。特此公告。")],
        [*pages[:-1], pages[-1] + "\n本公告不再有效。"],
        [pages[0][:100]],
    ]
    for damaged in cases:
        with pytest.raises(ValueError, match="OPERATING_EVENT_"):
            parse(damaged)


@pytest.mark.parametrize("pages", [[], None, [" "], [1], ["公告"] * 4, ["x" * 40001]])
def test_bounded_complete_input_required(pages):
    with pytest.raises(ValueError, match="OPERATING_EVENT_"):
        parse(pages)


def test_page_sequence_and_missing_middle_page_rejected():
    with pytest.raises(ValueError, match="PHYSICAL_PAGE_SEQUENCE"):
        parse([BOARD[0], BOARD[1].replace("2", "3", 1)])
    with pytest.raises(ValueError, match="OPERATING_EVENT_"):
        parse([ACCOUNTING[0], ACCOUNTING[2]])
    with pytest.raises(ValueError, match="OPERATING_EVENT_"):
        parse([BOARD[1], BOARD[0]])


def test_title_alone_never_proves_no_impact():
    with pytest.raises(ValueError, match="OPERATING_EVENT_"):
        parse(["证券代码：000777 示例酒业股份有限公司 重大事项公告 无重大影响"])


@pytest.mark.parametrize("symbol", [None, "", 777, "00077", "000777.SH", "abcdef"])
def test_expected_symbol_is_required(symbol):
    with pytest.raises(ValueError, match="EXPECTED_SYMBOL_REQUIRED"):
        parse_operating_event_terms(PRICE, symbol=symbol)


@pytest.mark.parametrize("announcement_id,kind,published", [
    ("1225431263", "OPERATING_PRICE_CHANGE", "2026-07-18"),
    ("1225475862", "INTERNAL_ASSET_TRANSFER_RESOLUTION", "2026-08-15"),
    ("1225475864", "ACCOUNTING_POLICY_IMPACT_STATEMENT", "2026-08-15"),
])
def test_real_bound_originals(announcement_id, kind, published):
    configured = os.environ.get("VALUE_ALIGNMENT_REAL_ROOT")
    if not configured:
        pytest.skip("Set VALUE_ALIGNMENT_REAL_ROOT to replay retained originals")
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    root = Path(configured)
    base = root / "runtime/value-alignment-event-observation/20261030T034906348838Z"
    scan = json.loads((base / "event-scan.json").read_text(encoding="utf-8"))
    item = next(a for a in scan["announcements"] if a["announcement_id"] == announcement_id)
    source = item["evidence_refs"][0]
    path = root / source["path"]
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == source["sha256"]
    pages = extract_pages(path)
    result = parse_operating_event_terms(pages, symbol=scan["symbol"])
    assert result["event_type"] == kind
    assert result["published_date"] == item["published_at"][:10] == published
    assert f"/finalpage/{published}/" in item["source_url"]
    assert result["issuer_name"] == "贵州茅台酒股份有限公司"
    assert_evidence(result, pages)
    if kind == "OPERATING_PRICE_CHANGE":
        assert result["terms"]["retail_price"]["after"] == "1639"
        assert result["terms"]["sales_contract_price"]["after"] == "1369"
        assert result["effective_date"] == "2026-07-18"
    elif kind == "INTERNAL_ASSET_TRANSFER_RESOLUTION":
        assert result["terms"]["resolution_date"] == "2026-08-13"
        assert result["terms"]["recipient"] == "贵州爱茅台数字科技有限公司"
        assert result["effective_date"] is None
    else:
        assert result["terms"]["assessment_basis"] == "ISSUER_STATEMENT_NOT_INDEPENDENT_APPROVAL"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before

@pytest.mark.parametrize("votes", [
    "同意：0 票；反对：7 票；弃权：0 票",
    "同意：0 票；反对：0 票；弃权：7 票",
    "同意：6 票；反对：1 票；弃权：0 票",
])
def test_asserted_passage_requires_supported_unanimous_votes(votes):
    original = "同意：7 票；反对：0 票；弃权：0 票"
    # Damage just the asset resolution: report/other votes remain unanimous.
    pages = deepcopy(BOARD)
    assert original in pages[1]
    pages[1] = pages[1].replace(original, votes, 1)
    assert "议案获得通过" in pages[1]
    with pytest.raises(ValueError, match="BOARD_UNANIMOUS_PASSAGE_NOT_VERIFIED"):
        parse(pages)

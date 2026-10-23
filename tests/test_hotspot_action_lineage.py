"""Explicit relation semantics with TEST_ONLY counterexamples and real originals."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta, date
from hashlib import sha256
import os
import json
from pathlib import Path

import pytest

from value_investment_agent.domain.hotspot.action_lineage import relate_action_documents
from value_investment_agent.infrastructure.hotspot.action_lineage import parse_action_identity, inspect_action_lineage
from value_investment_agent.infrastructure.hotspot import cash_implementation
from value_investment_agent.application.hotspot.corporate_action_coverage import inspect_official_action_coverage
from value_investment_agent.application.hotspot.lifecycle_review import build_hotspot_lifecycle_review
from value_investment_agent.application.hotspot.report_text import render_hotspot_lifecycle_markdown


ORIGINAL = ["证券代码：301061 证券简称：TEST_ONLY 公告编号：2025-021\nTEST_ONLY股份有限公司\n"
    "2024年年度权益分派实施公告\nTEST_ONLY具体条款。董事会2025年5月20日"]
CORRECTION = ["证券代码：301061 证券简称：TEST_ONLY 公告编号：2025-022\nTEST_ONLY股份有限公司\n"
    "2024年年度权益分派实施的更正公告\n公司于2025年5月20日在巨潮资讯网上披露了"
    "《2024年年度权益分派实施公告》（公告编号2025-021），现更正如下："
    "更正前：七、股份变动情况表：TEST_ONLY旧条款。更正后：七、股份变动情况表：TEST_ONLY新条款。"
    "其他内容不变。董事会2025年5月20日"]


def identities(revision=CORRECTION):
    return parse_action_identity(ORIGINAL, symbol="301061"), parse_action_identity(revision, symbol="301061")


def safe(result):
    assert result["complete_chain_proven"] is result["comparison_allowed"] is False
    assert result["action"] == "no_order"


def test_historical_lineage_reader_rejects_unbound_or_future_originals(tmp_path):
    from value_investment_agent.application.product.historical_action_lineage import load_historical_action_lineage
    path = tmp_path / 'runtime/observation.json'
    path.parent.mkdir()
    path.write_bytes(b'{}')
    with pytest.raises(ValueError, match='Hash'):
        load_historical_action_lineage(root=tmp_path,
            observation_binding=dict(path='runtime/observation.json', sha256='f' * 64),
            now=datetime.now(timezone.utc))
    with pytest.raises(ValueError):
        load_historical_action_lineage(root=tmp_path,
            observation_binding=dict(path='../private.json', sha256='f' * 64),
            now=datetime.now(timezone.utc))


def test_real_historical_lineage_reader_is_not_a_current_candidate_or_pit():
    from value_investment_agent.application.product.historical_action_lineage import load_historical_action_lineage
    root = Path(os.environ.get('HOTSPOT_LINEAGE_ROOT', '.'))
    relative = 'runtime/swing-amendment-case-20261024/b7d9c8efcfc94bc0b30b4273268caa21/observation.json'
    if not (root / relative).is_file():
        pytest.skip('Explicit retained official observation is unavailable')
    binding = dict(path=relative, sha256='379c2c9a829494b39b5b3351d2fcec14fd6e499e40c60147902c7073b877cd89')
    result = load_historical_action_lineage(root=root, observation_binding=binding, now=datetime.now(timezone.utc))
    assert result['symbol'] == '301061'
    assert result['lineage_review']['links'][0]['cancellation_asserted_by_this_document'] is False
    assert result['historical_pit_proven'] is result['formal_eligibility'] is result['comparison_allowed'] is False
    assert result['scope'] == 'HISTORICAL_FILING_RELATION_NOT_CURRENT_CANDIDATE_OR_TRADE'
    with pytest.raises(ValueError):
        load_historical_action_lineage(root=root, observation_binding=binding,
            now=datetime(2026, 10, 23, tzinfo=timezone.utc))


@pytest.mark.parametrize('changed', ['observation', 'raw', 'index'])
def test_historical_reader_rechecks_all_sources_after_parsing(tmp_path, monkeypatch, changed):
    from value_investment_agent.application.product import historical_action_lineage as reader
    from hashlib import sha256
    directory = tmp_path / 'runtime'
    directory.mkdir()
    documents = {
        'observation': dict(schema_version='daily-event-observation-v1', action='no_order',
            symbol='301061', scan_from='2025-05-20', scan_to='2025-05-21'),
        'raw': {}, 'index': {},
    }
    references = []
    for name, body in documents.items():
        path = directory / f'{name}.json'
        path.write_text(json.dumps(body), encoding='utf-8')
        references.append(dict(path=f'runtime/{name}.json', sha256=sha256(path.read_bytes()).hexdigest()))

    def parsed_then_changed(**kwargs):
        result = dict(official_publication_coverage='COMPLETE', evidence_bindings=references,
            lineage_review=dict(action='no_order', complete_chain_proven=False,
                comparison_allowed=False, historical_availability_proven=False))
        (directory / f'{changed}.json').write_bytes(b'changed after parsing')
        return result

    monkeypatch.setattr(reader, 'inspect_official_action_coverage', parsed_then_changed)
    with pytest.raises(ValueError, match='changed during replay'):
        reader.load_historical_action_lineage(root=tmp_path, observation_binding=references[0],
            now=datetime.now(timezone.utc))


def test_explicit_correction_links_to_identity_without_declaring_event_cancelled():
    result = relate_action_documents(*identities())
    assert result["relation_status"] == "EXPLICIT_TARGET_MATCH"
    assert result["effect_status"] == "CORRECTION_DECLARED"
    assert result["changed_section"] == "七、股份变动情况表"
    assert result["cancellation_asserted_by_this_document"] is False
    assert result["requires_terms_revalidation"] is True
    assert result["intraday_publication_order_proven"] is False
    safe(result)


def test_page_number_and_blank_lines_do_not_replace_document_header():
    parsed = parse_action_identity(["1\n\n" + ORIGINAL[0]], symbol="301061")
    assert parsed["announcement_number"] == "2025-021" and parsed["kind"] == "IMPLEMENTATION"


@pytest.mark.parametrize("field,value", [("symbol", "600519"), ("announcement_number", "2025-999"),
    ("title", "2023年年度权益分派实施公告"), ("published_date", "2025-05-19")])
def test_wrong_original_identity_never_links(field, value):
    original, revision = identities()
    original[field] = value
    result = relate_action_documents(original, revision)
    assert result["relation_status"] == "UNRESOLVED"
    assert result["cancellation_asserted_by_this_document"] is None
    safe(result)


@pytest.mark.parametrize("change", ["missing", "ambiguous", "predates"])
def test_target_absence_ambiguity_and_date_conflict_remain_unknown(change):
    original, revision = identities()
    if change == "missing":
        revision["references"] = []
    elif change == "ambiguous":
        revision["references"].append(dict(revision["references"][0]))
    else:
        revision["published_date"] = "2025-05-19"
    result = relate_action_documents(original, revision)
    assert result["relation_status"] == "UNRESOLVED" and result["effect_status"] == "UNKNOWN"
    safe(result)


@pytest.mark.parametrize("statement,expected", [
    ("公司决定取消本次权益分派。", "CANCELLATION_DECLARED"),
    ("公司决定撤销上述权益分派实施公告。", "CANCELLATION_DECLARED"),
    ("公司未决定取消本次权益分派。", "UNKNOWN"),
    ("若公司决定取消本次权益分派。", "UNKNOWN"),
    ("原文记载“公司决定取消本次权益分派。”", "UNKNOWN"),
])
def test_cancellation_requires_operative_unquoted_nonnegated_statement(statement, expected):
    text = CORRECTION[0].replace("2024年年度权益分派实施的更正公告", "关于取消2024年年度权益分派实施公告的公告")
    text = text.split("，现更正如下：")[0] + "。" + statement + "董事会2025年5月20日"
    result = relate_action_documents(*identities([text]))
    assert result["relation_status"] == "EXPLICIT_TARGET_MATCH"
    assert result["effect_status"] == expected
    assert result["cancellation_asserted_by_this_document"] is (True if expected == "CANCELLATION_DECLARED" else None)
    safe(result)


def test_compound_change_does_not_claim_correction_only_or_clear_cancellation():
    original, revision = identities([CORRECTION[0].replace("其他内容不变。", "公司决定取消本次权益分派。")])
    result = relate_action_documents(original, revision)
    assert result["effect_status"] == "COMPOUND_CHANGE_REQUIRES_REVIEW"
    assert result["cancellation_asserted_by_this_document"] is None
    safe(result)


def test_cancellation_rumour_clarification_is_not_an_operative_cancellation():
    text = CORRECTION[0].replace("2024年年度权益分派实施的更正公告", "关于2024年年度权益分派实施公告取消传闻的澄清公告")
    text = text.split("，现更正如下：")[0] + "。公司决定取消本次权益分派。上述传闻不实。董事会2025年5月20日"
    result = relate_action_documents(*identities([text]))
    assert result["effect_status"] == "UNKNOWN"
    assert result["cancellation_asserted_by_this_document"] is None


def test_current_title_cannot_reassign_a_different_year_reference():
    text = CORRECTION[0].replace("2024年年度权益分派实施的更正公告", "2023年年度权益分派实施的更正公告")
    result = relate_action_documents(*identities([text]))
    assert result["relation_status"] == "UNRESOLVED"
    assert result["cancellation_asserted_by_this_document"] is None


@pytest.mark.parametrize("statement", [
    '此前公告记载：“公司曾召开会议。公司决定取消本次权益分派。”该段仅为历史引述，本次未作取消决定。',
    '此前公告记载：「公司曾召开会议；公司决定取消本次权益分派。」本次未作取消决定。',
    '此前公告记载：“会议讨论‘公司曾召开会议。公司决定取消本次权益分派。’后结束。”本次未作取消决定。',
    '此前公告记载："公司曾召开会议。公司决定取消本次权益分派。"本次未作取消决定。',
    '此前公告记载：“公司曾召开会议。公司决定取消本次权益分派。',
    '此前公告记载：“公司曾召开会议。公司决定取消本次权益分派。』',
    '此前公告记载：公司曾召开会议。”公司决定取消本次权益分派。',
    '公司决定取消本次权益分派。公司未决定取消本次权益分派。',
    '公司决定取消本次权益分派。本次未作取消决定。',
    '公司决定取消本次权益分派。本公司尚未作出任何取消决定。',
    '公司“历史文字”决定取消本次权益分派。',
])
def test_cross_sentence_quotes_or_current_denial_cannot_declare_cancellation(statement):
    text = CORRECTION[0].replace("2024年年度权益分派实施的更正公告", "关于取消2024年年度权益分派实施公告的公告")
    text = text.split("，现更正如下：")[0] + "。" + statement + "董事会2025年5月20日"
    original, candidate = identities([text])
    result = relate_action_documents(original, candidate)
    assert candidate["operative_cancellation"] is False
    assert result["relation_status"] == "EXPLICIT_TARGET_MATCH"
    assert result["effect_status"] == "UNKNOWN"
    assert result["cancellation_asserted_by_this_document"] is None
    safe(result)


def test_quoted_history_does_not_suppress_a_separate_unquoted_operative_decision():
    text = CORRECTION[0].replace("2024年年度权益分派实施的更正公告", "关于取消2024年年度权益分派实施公告的公告")
    text = text.split("，现更正如下：")[0] + '。此前说明：“本次未作取消决定”；公司决定取消本次权益分派。董事会2025年5月20日'
    result = relate_action_documents(*identities([text]))
    assert result["effect_status"] == "CANCELLATION_DECLARED"
    safe(result)


@pytest.mark.parametrize("word", ["不取消", "未取消", "拟取消"])
def test_negative_or_proposed_title_cannot_certify_cancellation(word):
    text = CORRECTION[0].replace("2024年年度权益分派实施的更正公告", f"关于{word}2024年年度权益分派实施公告的公告")
    text = text.split("，现更正如下：")[0] + "。公司决定取消本次权益分派。董事会2025年5月20日"
    result = relate_action_documents(*identities([text]))
    assert result["effect_status"] == "UNKNOWN" and result["cancellation_asserted_by_this_document"] is None


def test_source_bound_body_link_rejects_bad_hash_and_future_acquisition(tmp_path, monkeypatch):
    from pypdf import PdfWriter
    announcements = []
    for number, pages in ((21, ORIGINAL), (22, CORRECTION)):
        path = tmp_path / f"{number}.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with path.open("wb") as stream:
            writer.write(stream)
        announcements.append(dict(announcement_id=str(number), source_url=f"https://static.cninfo.com.cn/finalpage/2025-05-20/{number}.PDF",
            published_at="2025-05-20T08:00:00+08:00", evidence_bindings=[dict(path=path.name, sha256=sha256(path.read_bytes()).hexdigest())]))
    monkeypatch.setattr(cash_implementation, "extract_pages", lambda path, limit: ORIGINAL if path.name == "21.pdf" else CORRECTION)
    args = dict(root=tmp_path, symbol="301061", announcements=announcements,
        acquired_at="2026-10-23T00:00:00+08:00", now=datetime(2026, 10, 24, tzinfo=timezone.utc))
    result = inspect_action_lineage(**args)
    assert result["links"][0]["effect_status"] == "CORRECTION_DECLARED"
    corrupted = deepcopy(announcements)
    corrupted[0]["evidence_bindings"][0]["sha256"] = "0" * 64
    assert inspect_action_lineage(**{**args, "announcements": corrupted})["links"] == []
    assert inspect_action_lineage(**{**args, "acquired_at": "2099-01-01T00:00:00+00:00"})["links"] == []
    safe(result)


def test_real_official_pair_and_existing_lifecycle_consumer():
    configured = os.environ.get("HOTSPOT_LINEAGE_ROOT")
    if not configured:
        pytest.skip("Real sealed action and public-price evidence not configured")
    root = Path(configured)
    observation = root / "runtime/swing-amendment-case-20261024/b7d9c8efcfc94bc0b30b4273268caa21/observation.json"
    binding = dict(path=observation.relative_to(root).as_posix(), sha256=sha256(observation.read_bytes()).hexdigest())
    now = datetime.now(timezone.utc)
    coverage = inspect_official_action_coverage(root=root, symbol="301061", start=date(2025, 5, 20),
        end=date(2025, 5, 21), now=now, observation_binding=binding)
    link = coverage["lineage_review"]["links"][0]
    assert link["original_number"] == "2025-021" and link["amendment_number"] == "2025-022"
    assert link["effect_status"] == "CORRECTION_DECLARED"
    assert link["changed_section"] == "七、股份变动情况表"
    assert link["original_noncash_terms_present"] is True
    safe(link)
    case = root / "runtime/hotspot-current-price-cases/301061-2026-10-23-5848cc8c28544b7d92690fcdb07466a2/case.json"
    payload = json.loads(case.read_bytes())
    bundle = json.loads((root / payload["current_reference_close"]["bundle_path"]).read_bytes())
    acquired = max([datetime.fromisoformat(bundle["finished_at"]),
        *[datetime.fromisoformat(ref["fetched_at"]) for ref in payload["source_bindings"].values()]])
    review = build_hotspot_lifecycle_review(root=root, symbol="301061", now=acquired + timedelta(seconds=1),
        current_case_binding=dict(path=case.relative_to(root).as_posix(), sha256=sha256(case.read_bytes()).hexdigest()),
        official_event_observation_binding=binding)
    assert review["current_data_status"] == "CURRENT", review
    assert review["current_pit"] is False
    assert review["entry_case_binding"] is None and review["position_guidance"] is None
    assert review["price_comparability"]["status"] == "UNKNOWN"
    assert "2025-021" in render_hotspot_lifecycle_markdown(review)
    assert review["action"] == "no_order" and review["formal_eligibility"] is False

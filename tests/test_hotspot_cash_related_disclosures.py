"""TEST_ONLY raw archives and optional retained source replay; no new authority."""
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from test_hotspot_cash_basis_v2 import _fixture, _binding, PAGES
from value_investment_agent import disclosures
from value_investment_agent.application.product import daily_event_observation as collector
from value_investment_agent.application.hotspot.cash_action_window_v3 import inspect_cash_action_window_v3
from value_investment_agent.infrastructure.hotspot import cash_implementation as legacy
from value_investment_agent.infrastructure.hotspot.related_disclosure_identity import (
    _attachment_titles, _classify, _direct_identity, _page_texts, _references,
)
from value_investment_agent.quote_sessions import CHINA


NAME = "TEST_ONLY能源股份有限公司"
AUTHOR = "TEST_ONLY券商股份有限公司"
OPINION = AUTHOR + "关于" + NAME + "股东向特定机构投资者询价转让股份相关资格的核查意见"


def _item(pages, title=OPINION):
    return dict(pages=pages, texts=_page_texts(pages), title=title, published_date="2026-04-17")


def _opinion():
    return [OPINION + "\n" + AUTHOR + "（以下简称“TEST_ONLY”）受" + NAME
        + "股东TEST_ONLY出让方有限公司委托，组织实施本次TEST_ONLY股东向特定机构投资者询价转让。"]


def test_same_name_or_header_prefix_is_not_an_identity_route():
    for code, name in (("0000019", NAME), ("000001", NAME + "海外股份有限公司"), ("03750", NAME)):
        pages = [f"证券代码：{code} 证券简称：TEST_ONLY\n{name}\n普通材料\n{name}董事会2026年4月16日"]
        assert _direct_identity(pages, name=NAME, symbol="000001", published_date="2026-04-17") is None
    assert _classify(_item([NAME + "普通材料"]), name=NAME, symbol="000001", attachments={})["status"] == "UNRESOLVED"


def test_third_party_requires_exact_attachment_title_body_subject_and_mandate():
    anchors = {OPINION: [dict(path="runtime/TEST_ONLY-anchor.pdf", sha256="a" * 64)]}
    result = _classify(_item(_opinion()), name=NAME, symbol="000001", attachments=anchors)
    assert result["status"] == "BOUND_ISSUER_ATTACHMENT_AND_EXPLICIT_BODY_SUBJECT"
    assert result["document_role"] == "THIRD_PARTY_OPINION_NOT_ISSUER_AUTHORED"
    assert result["body_signature_date"] is None
    for pages, attached in ((_opinion(), {}), ([OPINION + "\n仅引用公司同名，不说明受托对象。"], anchors),
            ([page.replace("）受", "）未受") for page in _opinion()], anchors),
            ([page.replace(NAME, NAME + "海外股份有限公司") for page in _opinion()], anchors)):
        assert _classify(_item(pages), name=NAME, symbol="000001", attachments=attached)["status"] == "UNRESOLVED"
    duplicate = dict(_item(_opinion()), official_title_count=2)
    assert _classify(duplicate, name=NAME, symbol="000001", attachments=anchors)["status"] == "UNRESOLVED"


def test_attachment_text_cannot_hide_negation_or_duplicate_targets():
    assert _attachment_titles(["四、附件(一)《" + OPINION + "》特此公告"]) == [OPINION]
    assert _attachment_titles(["四、附件不包括以下文件(一)《" + OPINION + "》特此公告"]) == []
    assert _attachment_titles(["四、附件(一)《" + OPINION + "》(二)《" + OPINION + "》特此公告"]) == []


def test_body_date_is_not_official_publication_date_or_acquisition():
    pages = ["证券代码：000001 证券简称：TEST_ONLY\n" + NAME + "\n普通公告\n" + NAME + "董事会2026年4月16日"]
    result = _direct_identity(pages, name=NAME, symbol="000001", published_date="2026-04-17")
    assert result["body_signature_date"] == "2026-04-16"
    assert result["date_scope"] == "BODY_SIGNATURE_DATE_NOT_PUBLIC_AVAILABILITY"
    with pytest.raises(ValueError):
        _direct_identity([page.replace("4月16日", "4月18日") for page in pages],
            name=NAME, symbol="000001", published_date="2026-04-17")


@pytest.mark.parametrize("statement", ["股东投诉，并未受其委托。", "股东委托的说法不实。"])
def test_partial_mandate_words_do_not_override_explicit_denial(statement):
    anchors = {OPINION: [dict(path="runtime/TEST_ONLY-anchor.pdf", sha256="a" * 64)]}
    pages = [OPINION + AUTHOR + "（以下简称“TEST_ONLY”）受" + NAME + statement]
    assert _classify(_item(pages), name=NAME, symbol="000001", attachments=anchors)["status"] == "UNRESOLVED"
    pages = [page + "上述委托说法不实。" for page in _opinion()]
    assert _classify(_item(pages), name=NAME, symbol="000001", attachments=anchors)["status"] == "UNRESOLVED"


def test_explicit_reference_and_cues_do_not_certify_correction_or_no_change():
    for pages in (["普通经营信息"], ["《2025年度A股权益分派实施公告》公告编号2026-037，其他激励份额作废。"]):
        relation = _references(pages, "2025年度A股权益分派实施公告", "2026-037")
        assert relation["no_change"] is None and relation["revision_absence_proven"] is False
        assert relation["effect_status"] == "NOT_DETERMINED"


def test_hk_title_does_not_substitute_for_explicit_a_class_and_code():
    from test_hotspot_capital_disclosure import _pages
    pages = _pages()
    item = dict(_item(pages, "H股公告"), published_date="2026-10-22")
    result = _classify(item, name=NAME, symbol="300750", attachments={})
    assert result["status"] == "BOUND_EXPLICIT_A_CODE_IN_HK_FORM"
    with pytest.raises(ValueError):
        _classify(dict(_item([page.replace("股份類別 A", "股份類別 H") for page in pages], "H股公告"),
            published_date="2026-10-22"),
            name=NAME, symbol="300750", attachments={})


def _archive(root, monkeypatch, *, bad_first=False):
    registry, event = _fixture(root, monkeypatch)
    runtime = root / "runtime"
    runtime.mkdir()
    original = runtime / "TEST_ONLY-implementation.pdf"
    original.write_bytes((root / "TEST_ONLY-implementation.pdf").read_bytes())
    event["evidence"][0]["path"] = original.relative_to(root).as_posix()
    registry.write_text(json.dumps(dict(backtest_ready=False, events=[event])), encoding="utf-8")
    main_pages = [page.replace("2025年度A股权益分派实施公告", NAME + "\n2025年度A股权益分派实施公告")
        .replace("TEST_ONLY公司董事会", NAME + "董事会") for page in PAGES]
    plan = ["证券代码：000001 证券简称：TEST_ONLY\n" + NAME + "\n股东询价转让计划书\n四、附件（一）《"
        + OPINION + "》\n特此公告。\n" + NAME + "董事会2026年4月16日"]
    texts = {"999001": main_pages, "999002": plan, "999003": _opinion(), "999004": [""]}
    titles = {"999001": "2025年度A股权益分派实施公告", "999002": "股东询价转让计划书",
        "999003": OPINION, "999004": "TEST_ONLY图像原件"}
    if bad_first:
        texts["999005"] = ["证券代码：0000019 证券简称：TEST_ONLY\n" + NAME]
        titles["999005"] = "TEST_ONLY错误主体"
    rows = [dict(secCode="000001", orgId="TEST_ONLY_org", announcementId=identity,
        announcementTitle=titles[identity], adjunctUrl=f"finalpage/2026-04-{'15' if identity == '999001' else '17'}/{identity}.PDF",
        announcementTime=int(datetime(2026, 4, 15 if identity == "999001" else 17,
            tzinfo=timezone.utc).timestamp() * 1000)) for identity in reversed(list(texts))]

    def request(parameters, *, raw_response_sink):
        payload = dict(totalAnnouncement=len(rows), announcements=rows, hasMore=False)
        if not parameters["seDate"]:
            payload = dict(totalAnnouncement=1, announcements=[dict(secCode="000001", orgId="TEST_ONLY_org")])
        body = json.dumps(payload).encode()
        raw_response_sink(body, dict(url=disclosures.SEARCH_URL, method="POST", request=parameters,
            page=int(parameters["pageNum"]), acquired_at=datetime.now(timezone.utc).isoformat(),
            sha256=sha256(body).hexdigest(), size_bytes=len(body)))
        return payload

    monkeypatch.setattr(disclosures, "_request_json", request)
    monkeypatch.setattr(collector, "download_disclosure_pdf", lambda url, path:
        (path.write_bytes(original.read_bytes()), sha256(path.read_bytes()).hexdigest())[1])
    monkeypatch.setattr(legacy, "extract_pages", lambda path, limit: main_pages if path == original
        else texts[path.stem.split("-")[-1]])
    collector.collect_daily_event_observation(root=root, symbol="000001", issuer_name=NAME,
        start=date(2026, 4, 15), end=date(2026, 4, 22), output_dir=runtime / "official",
        retain_raw_index=True, retained_originals=[dict(path=original.relative_to(root).as_posix(),
            sha256=event["evidence"][0]["sha256"], source_url=event["evidence"][0]["url"])])
    path = runtime / "official/observation.json"
    return dict(root=root, symbol="000001", record_date=date(2026, 4, 21),
        registry_binding=_binding(registry, root, datetime.now(CHINA)), start=date(2026, 4, 15),
        end=date(2026, 4, 22), now=datetime.now(CHINA), observation_binding=dict(
            path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest()))


@pytest.mark.parametrize("bad_first", [False, True])
def test_native_archive_review_retains_every_identity_or_unreadable_gap(tmp_path, monkeypatch, bad_first):
    args = _archive(tmp_path, monkeypatch, bad_first=bad_first)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = inspect_cash_action_window_v3(**args)
    review = result["related_disclosure_review"]
    assert review is not None and review["reviewed_document_count"] == 3 + int(bad_first)
    assert review["bound_subject_count"] == 2
    assert review["unresolved_subject_count"] == 1 + int(bad_first)
    assert len(review["items"]) == 3 + int(bad_first)
    assert all(row["no_change"] is None and row["comparison_allowed"] is False for row in review["items"])
    assert result["mapping"] is None and result["price_comparability"] == "UNKNOWN"
    assert result["formal_eligibility"] is result["original_protection_adjusted"] is False
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_corrupted_official_archive_is_not_a_verified_body_reference_set(tmp_path, monkeypatch):
    args = _archive(tmp_path, monkeypatch)
    (tmp_path / "runtime/official/000001-999003.pdf").write_bytes(b"TEST_ONLY_CORRUPT")
    result = inspect_cash_action_window_v3(**args)
    assert result["related_disclosure_review"] is None
    assert result["formal_eligibility"] is False and result["price_comparability"] == "UNKNOWN"


def test_one_native_pdf_runtime_failure_does_not_hide_remaining_documents(tmp_path, monkeypatch):
    from value_investment_agent.application.hotspot import cash_related_disclosures as application
    args = _archive(tmp_path, monkeypatch)
    native = application._pdf

    def fault(root, binding, now):
        if binding["url"].endswith("/999003.PDF"):
            raise RuntimeError("TEST_ONLY native PDF extraction failed")
        return native(root, binding, now)

    monkeypatch.setattr(application, "_pdf", fault)
    result = inspect_cash_action_window_v3(**args)
    review = result["related_disclosure_review"]
    assert review["reviewed_document_count"] == 3
    indexed = {item["announcement_id"]: item for item in review["items"]}
    assert "TEST_ONLY native PDF" in indexed["999003"]["identity_review"]["reason"]
    assert indexed["999002"]["identity_review"]["status"].startswith("BOUND_")
    assert result["price_comparability"] == "UNKNOWN" and result["mapping"] is None


def test_native_extraction_failure_in_legacy_stage_is_explicitly_fail_closed(tmp_path, monkeypatch):
    from value_investment_agent.infrastructure.hotspot import cash_implementation as legacy
    args = _archive(tmp_path, monkeypatch)

    def fault(*args, **kwargs):
        raise RuntimeError("TEST_ONLY native extraction failure before related review")

    monkeypatch.setattr(legacy, "extract_pages", fault)
    result = inspect_cash_action_window_v3(**args)
    assert result["status"] == "LEGACY_REVIEW_FAILED"
    assert result["legacy_v2_review"] is None and result["related_disclosure_review"] is None
    assert "TEST_ONLY native extraction" in result["failure_reason"]
    assert result["formal_eligibility"] is False and result["mapping"] is None
    assert result["price_comparability"] == "UNKNOWN" and result["action"] == "no_order"


@pytest.mark.skipif(not os.environ.get("HOTSPOT_CASH_RELATED_ROOT"), reason="Optional existing eleven-source archive")
def test_existing_real_eleven_source_archive_reviews_all_ten_without_rewriting_v2():
    root = Path(os.environ["HOTSPOT_CASH_RELATED_ROOT"])
    path = root / "runtime/swing-cash-basis-v2-review-20261024/f13f1f622e5b43d79b34d6ad323d604f/receipt.json"
    raw = path.read_bytes()
    assert sha256(raw).hexdigest() == "1553db6bbcd8548b7a974baf6f1d2b6fe5510a5ac0a713dc87fdc1656985149a"
    receipt = json.loads(raw)
    before = {ref["path"]: sha256((root / ref["path"]).read_bytes()).hexdigest() for ref in receipt["source_bindings"]}
    result = inspect_cash_action_window_v3(root=root, symbol="300750", record_date=date(2026, 4, 21),
        registry_binding=receipt["registry_binding"], start=date(2026, 4, 15), end=date(2026, 4, 22),
        now=datetime.now(CHINA), observation_binding=receipt["official_observation_binding"])
    review = result["related_disclosure_review"]
    assert review["reviewed_document_count"] == 10 and review["bound_subject_count"] == 9
    assert review["unresolved_subject_count"] == 1
    indexed = {item["announcement_id"]: item for item in review["items"]}
    assert indexed["1225123059"]["identity_review"]["document_role"] == "THIRD_PARTY_OPINION_NOT_ISSUER_AUTHORED"
    assert indexed["1225107949"]["text_coverage"] == "UNAVAILABLE"
    assert indexed["1225123060"]["unreadable_pages"] == [4]
    assert indexed["1225107948"]["published_date"] == "2026-04-16"
    assert indexed["1225107948"]["identity_review"]["body_signature_date"] == "2026-04-15"
    assert result["legacy_v2_review"]["status"] == "BODY_VERIFIED_RELATED_REVIEW_PENDING"
    assert result["price_comparability"] == "UNKNOWN" and result["mapping"] is None
    assert before == {name: sha256((root / name).read_bytes()).hexdigest() for name in before}
    assert path.read_bytes() == raw

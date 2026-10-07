from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256

import pytest

from test_daily_quote_binding import FINISHED, _write_bundle
from product_workbench_candidate_fixture import materialize_synthetic_legacy_packet, synthetic_legacy_packet
from value_investment_agent.application.product.product_workbench_candidate import build_product_workbench_candidate_payload
from value_investment_agent.quote_session_conversion import quote_snapshot_from_bundle_file
from value_investment_agent.presentation.read_models.conditional_expectations import render_company_review_cards
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
from value_investment_agent.presentation.read_models.quote_observation import project_quote_observation


def test_archived_close_is_visible_without_price_bridge_or_decision_promotion(tmp_path):
    bundle = _write_bundle(tmp_path)
    digest = sha256(bundle.read_bytes()).hexdigest()
    packet = synthetic_legacy_packet("2026-09-26T03:00:00+00:00")
    materialize_synthetic_legacy_packet(tmp_path, packet)
    model = product_workbench_from_payload(build_product_workbench_candidate_payload(packet, root=tmp_path))
    quote = quote_snapshot_from_bundle_file(bundle, tmp_path, symbol="600519",
        ref_id="600519-test-close", expected_sha256=digest)
    assert quote.status == "verified_close"
    captured_at = datetime.fromisoformat(FINISHED)
    generated_at = datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc)
    current = project_quote_observation(model, quote,
        path=bundle.relative_to(tmp_path).as_posix(), sha256=digest,
        captured_at=captured_at, generated_at=generated_at)
    before = next(card for card in model.companies if card.symbol == "600519")
    after = next(card for card in current.companies if card.symbol == "600519")
    assert after.price == before.price
    assert after.valuation == before.valuation
    assert after.margin_of_safety == before.margin_of_safety
    assert after.decision_process == before.decision_process
    assert current.portfolio == model.portfolio
    assert current.action == "no_order"
    assert current.today_items[-1].symbol == "600519"
    assert current.as_of == date(2026, 9, 26)
    assert current.generated_at == generated_at
    assert current.audit_evidence[-1].available_at == date(2026, 9, 26)
    assert "2026-09-26 取得归档" in current.today_items[-1].what_happened
    assert "12.34" in dict(after.decision_review)["已核验收盘行情（未桥接估值）"]
    report = render_company_review_cards(current)
    assert report.index("### 行情观察（不是价格桥接）") < report.index("### 先看研究结论与反证")
    assert "https://qt.gtimg.cn" in report and "https://hq.sinajs.cn" in report
    assert report.count("### 行情观察（不是价格桥接）") == 1

    with pytest.raises(ValueError, match="already exists"):
        project_quote_observation(current, quote,
            path=bundle.relative_to(tmp_path).as_posix(), sha256=digest,
            captured_at=captured_at, generated_at=generated_at)
    with pytest.raises(ValueError, match="display cutoff"):
        project_quote_observation(replace(model, as_of=date(2026, 9, 27)), quote,
            path=bundle.relative_to(tmp_path).as_posix(), sha256=digest,
            captured_at=captured_at, generated_at=generated_at)
    with pytest.raises(ValueError, match="hash"):
        quote_snapshot_from_bundle_file(bundle, tmp_path, symbol="600519",
            ref_id="600519-test-close", expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="verified close"):
        project_quote_observation(model, replace(quote, status="unverified"),
            path=bundle.relative_to(tmp_path).as_posix(), sha256=digest,
            captured_at=captured_at, generated_at=generated_at)
    with pytest.raises(ValueError, match="existing company"):
        project_quote_observation(model, replace(quote, symbol="999999"),
            path=bundle.relative_to(tmp_path).as_posix(), sha256=digest,
            captured_at=captured_at, generated_at=generated_at)
    with pytest.raises(ValueError, match="timestamps are not ordered"):
        project_quote_observation(model, quote,
            path=bundle.relative_to(tmp_path).as_posix(), sha256=digest,
            captured_at=captured_at, generated_at=model.generated_at)

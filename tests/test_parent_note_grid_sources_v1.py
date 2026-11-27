"""Contract and retained-original tests for the opt-in note-column source version."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import company_profile_sources_v2 as profiles
from value_investment_agent.application.research import parent_note_grid_sources_v1 as sources
from value_investment_agent.application.research.parent_note_grid_agent_facts_v1 import read_note_grid_agent_facts
from value_investment_agent.application.research.direct_owner_cash_staged_v3 import staged_parent_cash_request_v3
from value_investment_agent.application.research.retained_parent_direct_observations import read_retained_parent_d2_preflight

PROJECT = Path(__file__).resolve().parents[1]
BASE = "runtime/600809-public-report-sources-20261127"
MANIFEST = BASE + "/parent-note-grid-source-manifest-v1.json"
MANIFEST_SHA = "e1f598f11595608e2078b0292a66d887d017487fcc3d1a43e015093d4cb0c835"
NOW = datetime(2026, 11, 27, 4, tzinfo=timezone.utc)


def test_review_binds_complete_chapter():
    chapter = "一、主营我公司生产白酒。"
    rule = dict(start="一、主营", end="二、行业", section_sha256=sha256(chapter.encode()).hexdigest())
    assert profiles._chapter("一、主营\n我公司生产白酒。\n二、行业\n同行生产药品。", rule) == chapter
    with pytest.raises(ValueError, match="chapter changed"):
        profiles._chapter("一、主营\n我公司停止生产白酒。\n二、行业", rule)
    with pytest.raises(ValueError, match="boundaries"):
        profiles._chapter("一、主营\n一、主营\n二、行业", rule)


def test_single_column_and_dash_keep_printed_scope():
    source = dict(path="runtime/test.pdf", sha256="a"*64, available_at=NOW.isoformat())
    grid = [(3, ["本行", "", "", "123.50"]), (4, ["另行", "", "-", "-"])]
    rows = sources._rows(grid, {"single": "本行", "dashes": "另行"}, source, "2026-06-30")
    assert (rows["single"]["current"], rows["single"]["comparative"]) == (None, "123.50")
    assert rows["single"]["source_refs"]["comparative_period"] == "2025-06-30"
    assert rows["dashes"]["classification"] == "UNKNOWN"
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        sources._rows(grid + grid, {"single": "本行"}, source, "2026-06-30")


def test_quarter_cannot_enter_fy_h1_reader(tmp_path):
    with pytest.raises(ValueError, match="FY_OR_H1"):
        sources.read_note_grid_parent_cash(root=tmp_path, symbol="600809", issuer_name="x",
            sources=[dict(period_end="2026-09-30", receipt_binding={})], evaluated_at=NOW)


@pytest.fixture(scope="module")
def real_root():
    if not os.environ.get("FENJIU_SOURCE_ROOT"):
        pytest.skip("Set FENJIU_SOURCE_ROOT to the retained public source root")
    return Path(os.environ["FENJIU_SOURCE_ROOT"]).resolve(strict=True)


def test_originals_through_d2_and_frozen_v3_request(real_root):
    pin = dict(path=MANIFEST, sha256=MANIFEST_SHA)
    manifest = json.loads((real_root / MANIFEST).read_bytes())
    annual, interim = manifest["owner_sources"]
    preflight = read_retained_parent_d2_preflight(root=real_root, symbol="600809", issuer_name=manifest["issuer_name"],
        annual_period=annual["period_end"], annual_receipt=annual["receipt_binding"],
        interim_period=interim["period_end"], interim_receipt=interim["receipt_binding"],
        supporting_root=None, supporting_sources={}, evaluated_at=NOW, source_adapter_version=sources.VERSION)
    fy, h1 = preflight["cash_source_bridge"]["statements"]
    assert all(all(s["checks"].values()) for s in (fy, h1))
    assert fy["cash_flow"]["cfo_cny"]["current"] == "9091509497.90"
    assert h1["cash_flow"]["cfo_cny"]["current"] == "6602075130.36"
    assert h1["cash_flow"]["closing_cash_and_equivalents_cny"]["current"] == "8854363451.85"
    mixed = h1["cash_flow"]["mixed_distribution_interest_paid_cny"]
    assert (mixed["current"], mixed["comparative"], mixed["physical_page"]) == (None, "3001111986.12", 33)
    assert fy["cash_flow"]["fx_cny"]["current"] is None
    facts = read_note_grid_agent_facts(root=real_root, source_binding=pin, now=NOW)
    assert facts["ordinary_shares"]["count"] == "1219964222"
    assert facts["matched_historical_second_half"]["cfo"] == "2468977705.99"
    assert facts["quarterly_parent_source"] is None and not facts["model_applicability_verified"]
    request = staged_parent_cash_request_v3(root=real_root, spec_binding=None, scenario="bear", stage="operating",
                                            generated_at=NOW, verified_context=facts)
    context = json.loads(request.user)["source_context"]
    assert context["facts"]["h1_cfo_cny"]["value_cny"] == "6602075130.36"
    assert context["facts"]["fy_cfo_cny"]["source_refs"]["physical_page"] == 58
    with pytest.raises(ValueError, match="binding rejected"):
        read_note_grid_agent_facts(root=real_root, source_binding=dict(pin, sha256="0"*64), now=NOW)


def test_registered_profile_real_public_route(real_root):
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    from value_investment_agent.application.product.value_transparent_workbench_v1 import _bindings
    expected = profiles.load_registered_source_profile(root=real_root, symbol="600809", now=NOW)
    with TestClient(create_app(PROJECT)) as client:
        response = client.get("/api/v1/research-profiles/600809")
    assert response.status_code == 200
    result = response.json()
    assert result["input_fingerprint"] == expected["input_fingerprint"]
    assert result["status"] == "SOURCE_BOUND_ROUTE_ONLY" and not result["economic_quality_proven"]
    assert result["template_candidate"] == "quality_compounder"
    assert [ref["physical_page"] for ref in result["evidence_refs"]] == [7, 6]
    assert len(_bindings(PROJECT, result)) == 9

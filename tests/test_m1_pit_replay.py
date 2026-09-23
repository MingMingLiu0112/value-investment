from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.m1_pit_replay import (
    ACTION_NO_ORDER,
    build_pit_replay_payload,
    replay_package_pit,
)
from value_investment_agent.m1_valuation_package_builder import (
    load_package_specs,
)


@pytest.fixture
def ROOT():
    return Path(__file__).resolve().parents[1]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_payload(source_id: str, digest: str, published_at: str) -> dict:
    period = "2025-12-31" if source_id.endswith("annual") else "2026-06-30"
    kind = "annual" if source_id.endswith("annual") else "interim"
    return {
        "id": source_id,
        "kind": "official_issuer_filing",
        "location": f"fixture/{period}-{kind}-{digest}.pdf",
        "sha256": digest,
        "published_at": published_at,
        "retrieved_at": "2026-09-23T00:00:00+00:00",
        "parser_version": "fixture-v1",
    }


def test_replay_excludes_future_disclosure_and_selects_latest_filing(tmp_path):
    annual_bytes = b"annual"
    interim_bytes = b"interim"
    annual_digest = _digest(annual_bytes)
    interim_digest = _digest(interim_bytes)
    (tmp_path / "fixture").mkdir()
    (tmp_path / "fixture" / f"2025-12-31-annual-{annual_digest}.pdf").write_bytes(
        annual_bytes
    )
    (tmp_path / "fixture" / f"2026-06-30-interim-{interim_digest}.pdf").write_bytes(
        interim_bytes
    )
    payload = {
        "symbol": "000001",
        "run_id": "fixture-m1",
        "sources": [
            _source_payload(
                "fixture_annual",
                annual_digest,
                "2026-03-31T00:00:00+08:00",
            ),
            _source_payload(
                "fixture_interim",
                interim_digest,
                "2026-08-28T00:00:00+08:00",
            ),
        ],
    }

    result = replay_package_pit(payload, root=tmp_path)

    assert result["package_id"] == "fixture-m1"
    assert [item["source_id"] for item in result["official_filings"]] == [
        "fixture_annual",
        "fixture_interim",
    ]
    decisions = result["decision_points"]
    assert decisions[0]["latest_selected_filing_id"] is None
    assert decisions[0]["excluded_future_filing_ids"] == [
        "fixture_annual",
        "fixture_interim",
    ]
    assert decisions[1]["latest_selected_filing_id"] == "fixture_annual"
    assert decisions[1]["excluded_future_filing_ids"] == ["fixture_interim"]
    assert decisions[-1]["latest_selected_filing_id"] == "fixture_interim"
    assert decisions[-1]["selected_filing_ids"] == [
        "fixture_annual",
        "fixture_interim",
    ]
    assert len(result["future_disclosure_rejections"]) == 3


def test_replay_fails_closed_when_source_hash_changes(tmp_path):
    data = b"official"
    digest = _digest(data)
    (tmp_path / "fixture").mkdir()
    wrong_digest = "0" * 64
    (tmp_path / "fixture" / f"2025-12-31-annual-{wrong_digest}.pdf").write_bytes(data)
    (tmp_path / "fixture" / f"2026-06-30-interim-{digest}.pdf").write_bytes(data)
    payload = {
        "symbol": "000001",
        "run_id": "fixture-m1",
        "sources": [
            _source_payload(
                "fixture_annual",
                wrong_digest,
                "2026-03-31T00:00:00+08:00",
            ),
            _source_payload(
                "fixture_interim",
                digest,
                "2026-08-28T00:00:00+08:00",
            ),
        ],
    }

    with pytest.raises(ValueError, match="source changed"):
        replay_package_pit(payload, root=tmp_path)


def test_real_m1_packages_replay_three_disclosure_boundaries(ROOT):
    payloads = {
        str(item["symbol"]): item
        for item in load_package_specs(ROOT)
        if item["symbol"] in {"000651", "600741", "600887"}
    }
    payload = build_pit_replay_payload(
        payloads,
        root=ROOT,
        generated_at=datetime(2026, 9, 23, 4, 30, tzinfo=timezone.utc),
    )

    assert payload["action"] == ACTION_NO_ORDER
    assert payload["package_count"] == 3
    for item in payload["packages"]:
        assert len(item["official_filings"]) == 2
        assert len(item["decision_points"]) == 4
        assert len(item["future_disclosure_rejections"]) == 3
        assert item["decision_points"][-1]["latest_selected_filing_id"]


def test_runner_receipt_is_jsonable_without_future_facts(ROOT):
    payloads = {
        str(item["symbol"]): item
        for item in load_package_specs(ROOT)
        if item["symbol"] in {"000651", "600741", "600887"}
    }
    payload = build_pit_replay_payload(
        payloads,
        root=ROOT,
        generated_at=datetime(2026, 9, 23, 4, 30, tzinfo=timezone.utc),
    )
    json.loads(json.dumps(payload, ensure_ascii=False))

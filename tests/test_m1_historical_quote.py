from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.m1_historical_quote import (
    SCHEMA_VERSION,
    latest_completed_szse_session,
    quote_snapshot_from_historical_close_manifest,
    sohu_daily_bar,
    tencent_daily_bar,
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _calendar_raw() -> bytes:
    return json.dumps(
        {
            "nowdate": "2026-09-23",
            "data": [
                {"jyrq": "2026-09-21", "jybz": "1"},
                {"jyrq": "2026-09-22", "jybz": "1"},
                {"jyrq": "2026-09-23", "jybz": "1"},
            ],
        }
    ).encode()


def _tencent_raw(close: str = "38.18") -> bytes:
    return json.dumps(
        {
            "code": 0,
            "data": {
                "sz000651": {
                    "day": [
                        ["2026-09-21", "38.55", "38.00", "38.55", "37.83", "489873.00", {}, "0.89"],
                        ["2026-09-22", "37.90", close, "38.32", "37.81", "343804.00", {}, "0.62"],
                        ["2026-09-23", "38.20", "38.32", "38.43", "38.15", "106600", "", "0.19"],
                    ]
                }
            },
        }
    ).encode()


def _sohu_raw(close: str = "38.18") -> bytes:
    return json.dumps(
        [
            {
                "status": 0,
                "hq": [
                    ["2026-09-21", "38.55", "38.00", "-0.55", "-1.43%", "37.83", "38.55", "489873", "186262.06", "0.89%", "130.00"],
                    ["2026-09-22", "37.90", close, "0.18", "0.47%", "37.81", "38.32", "343804", "131280.73", "0.62%", "161.00"],
                    ["2026-09-23", "38.20", "38.32", "0.14", "0.37%", "38.15", "38.43", "106600", "40856.81", "0.19%", "90.00"],
                ],
            }
        ]
    ).encode()


def _write_manifest(
    root: Path,
    *,
    tencent_raw: bytes,
    sohu_raw: bytes,
    calendar_raw: bytes,
    close: str,
) -> Path:
    files = {
        "tencent": root / "tencent.json",
        "sohu": root / "sohu.json",
        "calendar": root / "calendar.json",
    }
    raws = {
        "tencent": tencent_raw,
        "sohu": sohu_raw,
        "calendar": calendar_raw,
    }
    for key, path in files.items():
        path.write_bytes(raws[key])
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": "2026-09-23T04:10:00+00:00",
        "action": "no_order",
        "symbol": "000651",
        "quote_date": "2026-09-22",
        "verified_close": close,
        "tencent_close": close,
        "sohu_close": close,
        "tolerance": "0.01",
        "calendar_now_date": "2026-09-23",
        "provider_documents": {
            "tencent": {
                "path": "tencent.json",
                "sha256": _sha256(tencent_raw),
                "source_url": "https://proxy.finance.qq.com/tencent",
                "fetched_at": "2026-09-23T04:10:00+00:00",
            },
            "sohu": {
                "path": "sohu.json",
                "sha256": _sha256(sohu_raw),
                "source_url": "https://q.stock.sohu.com/sohu",
                "fetched_at": "2026-09-23T04:10:00+00:00",
            },
            "szse_calendar": {
                "path": "calendar.json",
                "sha256": _sha256(calendar_raw),
                "source_url": "https://www.szse.cn/calendar",
                "fetched_at": "2026-09-23T04:10:00+00:00",
            },
        },
    }
    path = root / "manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def test_historical_parsers_and_verified_snapshot(tmp_path: Path) -> None:
    calendar_raw = _calendar_raw()
    tencent_raw = _tencent_raw()
    sohu_raw = _sohu_raw()
    target = date(2026, 9, 22)

    assert latest_completed_szse_session(calendar_raw) == (
        target,
        date(2026, 9, 23),
    )
    assert tencent_daily_bar(tencent_raw, "000651", target)["close"] == "38.18"
    assert sohu_daily_bar(sohu_raw, "000651", target)["close"] == "38.18"

    manifest = _write_manifest(
        tmp_path,
        tencent_raw=tencent_raw,
        sohu_raw=sohu_raw,
        calendar_raw=calendar_raw,
        close="38.18",
    )
    snapshot = quote_snapshot_from_historical_close_manifest(
        manifest,
        tmp_path,
        expected_sha256=_sha256(manifest.read_bytes()),
    )
    assert snapshot.symbol == "000651"
    assert snapshot.quote_date == target
    assert snapshot.current_price == Decimal("38.18")
    assert snapshot.status == "verified_close"
    assert {ref["id"] for ref in snapshot.evidence_refs} >= {
        "m1_000651_2026-09-22_historical_close",
        "m1_000651_2026-09-22_tencent",
        "m1_000651_2026-09-22_sohu",
        "m1_000651_2026-09-22_szse_calendar",
    }


def test_historical_close_conflict_fails(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        tencent_raw=_tencent_raw("38.18"),
        sohu_raw=_sohu_raw("38.20"),
        calendar_raw=_calendar_raw(),
        close="38.18",
    )
    with pytest.raises(ValueError, match="differ by more than"):
        quote_snapshot_from_historical_close_manifest(manifest, tmp_path)


def test_historical_calendar_must_be_latest_completed_session(tmp_path: Path) -> None:
    calendar_raw = json.dumps(
        {
            "nowdate": "2026-09-23",
            "data": [
                {"jyrq": "2026-09-21", "jybz": "1"},
                {"jyrq": "2026-09-22", "jybz": "0"},
                {"jyrq": "2026-09-23", "jybz": "1"},
            ],
        }
    ).encode()
    manifest = _write_manifest(
        tmp_path,
        tencent_raw=_tencent_raw(),
        sohu_raw=_sohu_raw(),
        calendar_raw=calendar_raw,
        close="38.18",
    )
    with pytest.raises(ValueError, match="latest completed"):
        quote_snapshot_from_historical_close_manifest(manifest, tmp_path)

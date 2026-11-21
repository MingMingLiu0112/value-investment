from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest
import requests

from value_investment_agent.infrastructure.filings.sse_current_capital_snapshot_v1 import (
    CLASSIFICATION,
    RAW_FILENAME,
    RECEIPT_FILENAME,
    SQL_ID,
    SSECapitalAcquisitionError,
    acquire_sse_current_capital_snapshot,
    replay_sse_current_capital_snapshot,
)


NOW = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)


def official_payload():
    return {
        "actionErrors": [],
        "actionMessages": [],
        "fieldErrors": {},
        "isPagination": "false",
        "jsonCallBack": None,
        "locale": "en_CN",
        "pageHelp": {"total": 0},
        "pageNo": None,
        "pageSize": None,
        "queryDate": "",
        "result": [
            {
                "TOTAL_DOMESTIC_VOL": "632536.07",
                "A_LIMIT_VOL": "3143.09",
                "TRADE_DATE": "20261113",
                "B_VOL": "0.00",
                "SPECIAL_VOL": "-",
                "TOTAL_UNLIMIT_VOL": "629392.97",
                "A_UNLIMIT_VOL": "629392.97",
                "CDR_VOL": "0.00",
            }
        ],
        "securityCode": "",
        "sqlId": SQL_ID,
    }


class Response:
    def __init__(self, payload=None, *, status=200, content=None):
        self.status_code = status
        self.content = (
            json.dumps(payload, separators=(",", ":")).encode()
            if content is None
            else content
        )


def acquire(tmp_path: Path, payload=None, *, symbol="600887"):
    seen = []

    def get(url, **kwargs):
        seen.append((url, kwargs))
        return Response(official_payload() if payload is None else payload)

    output = tmp_path / "snapshot"
    receipt = acquire_sse_current_capital_snapshot(
        symbol=symbol,
        output_dir=output,
        allow_network=True,
        get=get,
        now=lambda: NOW,
    )
    return output, receipt, seen


def test_official_structure_is_archived_and_replayed_as_rounded_interval(tmp_path):
    output, receipt, seen = acquire(tmp_path)
    assert len(seen) == 1
    assert seen[0][1]["headers"]["Referer"] == "https://www.sse.com.cn/"
    assert seen[0][1]["timeout"] == 10.0
    raw = (output / RAW_FILENAME).read_bytes()
    assert receipt["raw_sha256"] == hashlib.sha256(raw).hexdigest()

    result = replay_sse_current_capital_snapshot(
        receipt_path=output / RECEIPT_FILENAME, symbol="600887", as_of=NOW
    )
    assert result["classification"] == CLASSIFICATION
    assert result["displayed_total_domestic_10k_shares"] == "632536.07"
    assert result["lower_bound_shares"] == 6_325_360_650
    assert result["upper_bound_shares"] == 6_325_360_749
    assert result["lower_bound_shares"] <= 6_325_360_667 <= result["upper_bound_shares"]
    assert result["exact_share_count"] is False
    assert result["precision_shares"] == 100
    assert result["trade_date"] == "2026-11-13"
    assert result["action"] == "no_order"
    # The display centre is not promoted to an exact-share assertion.
    assert "share_count" not in result


def test_replay_never_calls_network(tmp_path, monkeypatch):
    output, _, _ = acquire(tmp_path)
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("network used"))
    replay_sse_current_capital_snapshot(
        receipt_path=output / RECEIPT_FILENAME, symbol="600887", as_of=NOW
    )


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda p: p["result"].append(deepcopy(p["result"][0])), "RESULT_MUST_BE_UNIQUE"),
        (lambda p: p["result"][0].update(TRADE_DATE="20261131"), "TRADE_DATE_INVALID"),
        (lambda p: p["result"][0].update(TRADE_DATE="20261116"), "TRADE_DATE_IN_FUTURE"),
        (lambda p: p["result"][0].update(TOTAL_DOMESTIC_VOL="632536.07万股"), "VALUE_OR_UNIT_INVALID"),
        (lambda p: p.update(unit="万股"), "UNEXPECTED_UNIT_FIELD"),
        (lambda p: p["result"][0].update(A_LIMIT_VOL="1.00"), "COMPONENTS_INCONSISTENT"),
        (lambda p: p["result"][0].pop("B_VOL"), "RESULT_SCHEMA_INVALID"),
    ],
)
def test_invalid_official_payloads_are_rejected_without_output(tmp_path, mutation, message):
    payload = official_payload()
    mutation(payload)
    output = tmp_path / "snapshot"
    with pytest.raises(ValueError, match=message):
        acquire_sse_current_capital_snapshot(
            symbol="600887",
            output_dir=output,
            allow_network=True,
            get=lambda *a, **k: Response(payload),
            now=lambda: NOW,
        )
    assert not output.exists()


def test_wrong_symbol_url_sql_id_as_of_and_tampering_are_rejected(tmp_path):
    output, _, _ = acquire(tmp_path)
    receipt_path = output / RECEIPT_FILENAME
    with pytest.raises(ValueError, match="RECEIPT_IDENTITY_INVALID"):
        replay_sse_current_capital_snapshot(
            receipt_path=receipt_path, symbol="600519", as_of=NOW
        )

    original = json.loads(receipt_path.read_text())
    for key, value, message in (
        ("source_url", original["source_url"].replace("600887", "600519"), "SOURCE_URL_INVALID"),
        ("sql_id", "WRONG", "RECEIPT_IDENTITY_INVALID"),
    ):
        changed = deepcopy(original)
        changed[key] = value
        receipt_path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            replay_sse_current_capital_snapshot(
                receipt_path=receipt_path, symbol="600887", as_of=NOW
            )
    receipt_path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError, match="ACQUIRED_AFTER_AS_OF"):
        replay_sse_current_capital_snapshot(
            receipt_path=receipt_path,
            symbol="600887",
            as_of=datetime(2026, 11, 15, 17, 59, tzinfo=timezone.utc),
        )
    (output / RAW_FILENAME).write_bytes(b"{}")
    with pytest.raises(ValueError, match="RAW_HASH_MISMATCH"):
        replay_sse_current_capital_snapshot(
            receipt_path=receipt_path, symbol="600887", as_of=NOW
        )


@pytest.mark.parametrize(
    "factory, classification",
    [
        (lambda: Response(status=503, content=b"down"), "SSE_CAPITAL_HTTP_RETRYABLE"),
        (lambda: Response(status=403, content=b"no"), "SSE_CAPITAL_HTTP_REJECTED"),
        (lambda: (_ for _ in ()).throw(requests.Timeout()), "SSE_CAPITAL_TIMEOUT"),
        (lambda: (_ for _ in ()).throw(requests.ConnectionError()), "SSE_CAPITAL_CONNECTION_FAILED"),
    ],
)
def test_transport_failures_are_classified_and_do_not_pollute_existing_files(
    tmp_path, factory, classification
):
    old = tmp_path / "old"
    old.mkdir()
    old_file = old / "response.json"
    old_file.write_bytes(b"retained")
    output = tmp_path / "new"

    def get(*args, **kwargs):
        return factory()

    with pytest.raises(SSECapitalAcquisitionError) as caught:
        acquire_sse_current_capital_snapshot(
            symbol="600887",
            output_dir=output,
            allow_network=True,
            get=get,
            now=lambda: NOW,
        )
    assert caught.value.classification == classification
    assert old_file.read_bytes() == b"retained"
    assert not output.exists()


def test_existing_output_is_rejected_before_http(tmp_path):
    output = tmp_path / "snapshot"
    output.mkdir()
    retained = output / "response.json"
    retained.write_bytes(b"retained")
    with pytest.raises(FileExistsError):
        acquire_sse_current_capital_snapshot(
            symbol="600887",
            output_dir=output,
            allow_network=True,
            get=lambda *a, **k: pytest.fail("HTTP must not run"),
            now=lambda: NOW,
        )
    assert retained.read_bytes() == b"retained"

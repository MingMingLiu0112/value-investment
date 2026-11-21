"""Acquire and replay one rounded current-capital snapshot from SSE.

The SSE endpoint reports quantities in ten-thousand shares with two decimal
places.  Those display values are observations at 100-share precision, not
exact share counts.  This adapter therefore returns closed integer-share
bounds and never upgrades the displayed centre to an exact fact.

Acquisition and replay are deliberately separate.  ``replay`` is read-only
and never performs a network request or silently refreshes retained evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse

import requests


VERSION = "sse-current-capital-snapshot-v1"
SQL_ID = "COMMON_SSE_CP_GPJCTPZ_GPLB_GPGK_GBJG_C"
BASE_URL = "https://query.sse.com.cn/commonQuery.do"
REFERER = "https://www.sse.com.cn/"
CLASSIFICATION = "DERIVED_FACT_FROM_OFFICIAL_ROUNDED_SNAPSHOT"
DISPLAY_UNIT = "TEN_THOUSAND_SHARES"
DISPLAY_DECIMALS = 2
PRECISION_SHARES = 100
RAW_FILENAME = "response.json"
RECEIPT_FILENAME = "receipt.json"

_FIELDS = (
    "TOTAL_DOMESTIC_VOL",
    "TRADE_DATE",
    "A_LIMIT_VOL",
    "TOTAL_UNLIMIT_VOL",
    "A_UNLIMIT_VOL",
    "B_VOL",
    "CDR_VOL",
    "SPECIAL_VOL",
)
_QUANTITY_FIELDS = tuple(field for field in _FIELDS if field != "TRADE_DATE")
_DISPLAY_NUMBER = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{2}")
_SYMBOL = re.compile(r"[0-9]{6}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class SSECapitalAcquisitionError(RuntimeError):
    """Bounded transport failure with a stable caller-facing classification."""

    classification: str
    http_status: int | None = None

    def __str__(self) -> str:
        suffix = "" if self.http_status is None else f":HTTP_{self.http_status}"
        return self.classification + suffix


def _url(symbol: str) -> str:
    return BASE_URL + "?" + urlencode(
        {"isPagination": "false", "sqlId": SQL_ID, "COMPANY_CODE": symbol}
    )


def _aware_utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"SSE_CAPITAL_{label}_AWARE_DATETIME_REQUIRED")
    return value.astimezone(timezone.utc)


def _symbol(value: str) -> str:
    if not isinstance(value, str) or _SYMBOL.fullmatch(value) is None:
        raise ValueError("SSE_CAPITAL_SYMBOL_INVALID")
    return value


def _display_decimal(value: object, field: str) -> Decimal:
    # SSE uses '-' for a displayed zero in SPECIAL_VOL.  It is retained in the
    # raw payload and normalized only for interval arithmetic.
    if field == "SPECIAL_VOL" and value == "-":
        return Decimal("0.00")
    if not isinstance(value, str) or _DISPLAY_NUMBER.fullmatch(value) is None:
        raise ValueError("SSE_CAPITAL_DISPLAY_VALUE_OR_UNIT_INVALID:" + field)
    try:
        number = Decimal(value)
    except InvalidOperation as error:  # pragma: no cover - regex is the guard
        raise ValueError("SSE_CAPITAL_DISPLAY_VALUE_INVALID:" + field) from error
    if number < 0:
        raise ValueError("SSE_CAPITAL_NEGATIVE_QUANTITY:" + field)
    return number


def _integer_share_bounds(displayed_10k: Decimal) -> tuple[int, int]:
    centre = displayed_10k * Decimal(10_000)
    if centre != centre.to_integral_value():
        raise ValueError("SSE_CAPITAL_DISPLAY_PRECISION_INVALID")
    centre_shares = int(centre)
    # Round-to-nearest at 100-share display resolution.  Integer actual share
    # counts represented by x.xx ten-thousand shares form this closed interval.
    return max(0, centre_shares - 50), centre_shares + 49


def _interval_sum(intervals: list[tuple[int, int]]) -> tuple[int, int]:
    return sum(item[0] for item in intervals), sum(item[1] for item in intervals)


def _require_overlap(left: tuple[int, int], right: tuple[int, int], label: str) -> None:
    if max(left[0], right[0]) > min(left[1], right[1]):
        raise ValueError("SSE_CAPITAL_COMPONENTS_INCONSISTENT:" + label)


def _parse_payload(raw: bytes, *, symbol: str, as_of: datetime) -> dict:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("SSE_CAPITAL_RAW_JSON_INVALID") from error
    if not isinstance(payload, dict):
        raise ValueError("SSE_CAPITAL_RESPONSE_OBJECT_REQUIRED")
    if payload.get("sqlId") != SQL_ID or payload.get("isPagination") != "false":
        raise ValueError("SSE_CAPITAL_RESPONSE_CONTRACT_INVALID")
    # A declared unit would create an alternative contract.  The official
    # query's field contract is fixed to ten-thousand shares.
    if any("UNIT" in str(key).upper() for key in payload):
        raise ValueError("SSE_CAPITAL_UNEXPECTED_UNIT_FIELD")
    result = payload.get("result")
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
        raise ValueError("SSE_CAPITAL_RESULT_MUST_BE_UNIQUE")
    row = result[0]
    if set(row) != set(_FIELDS):
        raise ValueError("SSE_CAPITAL_RESULT_SCHEMA_INVALID")
    if "COMPANY_CODE" in row and row["COMPANY_CODE"] != symbol:
        raise ValueError("SSE_CAPITAL_RESULT_SYMBOL_MISMATCH")

    raw_date = row["TRADE_DATE"]
    if not isinstance(raw_date, str) or re.fullmatch(r"[0-9]{8}", raw_date) is None:
        raise ValueError("SSE_CAPITAL_TRADE_DATE_INVALID")
    try:
        observed = datetime.strptime(raw_date, "%Y%m%d").date()
    except ValueError as error:
        raise ValueError("SSE_CAPITAL_TRADE_DATE_INVALID") from error
    if observed > as_of.date():
        raise ValueError("SSE_CAPITAL_TRADE_DATE_IN_FUTURE")

    displayed = {field: _display_decimal(row[field], field) for field in _QUANTITY_FIELDS}
    bounds = {field: _integer_share_bounds(value) for field, value in displayed.items()}
    _require_overlap(
        bounds["TOTAL_DOMESTIC_VOL"],
        _interval_sum([bounds["A_LIMIT_VOL"], bounds["TOTAL_UNLIMIT_VOL"]]),
        "DOMESTIC_EQUALS_LIMITED_PLUS_UNLIMITED",
    )
    _require_overlap(
        bounds["TOTAL_UNLIMIT_VOL"],
        _interval_sum(
            [
                bounds["A_UNLIMIT_VOL"],
                bounds["B_VOL"],
                bounds["CDR_VOL"],
                bounds["SPECIAL_VOL"],
            ]
        ),
        "UNLIMITED_EQUALS_COMPONENTS",
    )
    total_lower, total_upper = bounds["TOTAL_DOMESTIC_VOL"]
    return {
        "schema_version": VERSION,
        "classification": CLASSIFICATION,
        "symbol": symbol,
        "trade_date": observed.isoformat(),
        "display_unit": DISPLAY_UNIT,
        "display_decimals": DISPLAY_DECIMALS,
        "displayed_total_domestic_10k_shares": format(
            displayed["TOTAL_DOMESTIC_VOL"], ".2f"
        ),
        "lower_bound_shares": total_lower,
        "upper_bound_shares": total_upper,
        "precision_shares": PRECISION_SHARES,
        "exact_share_count": False,
        "displayed_components_10k_shares": {
            field: format(value, ".2f") for field, value in displayed.items()
            if field != "TOTAL_DOMESTIC_VOL"
        },
        "component_bounds_shares": {
            field: {"lower": pair[0], "upper": pair[1]}
            for field, pair in bounds.items()
            if field != "TOTAL_DOMESTIC_VOL"
        },
        "formal_eligibility": False,
        "action": "no_order",
    }


def _validate_url(url: str, symbol: str) -> None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "query.sse.com.cn"
        or parsed.path != "/commonQuery.do"
        or parsed.params
        or parsed.fragment
        or query
        != {
            "isPagination": ["false"],
            "sqlId": [SQL_ID],
            "COMPANY_CODE": [symbol],
        }
    ):
        raise ValueError("SSE_CAPITAL_SOURCE_URL_INVALID")


def acquire_sse_current_capital_snapshot(
    *,
    symbol: str,
    output_dir: Path,
    allow_network: bool = False,
    timeout_seconds: float = 10.0,
    get: Callable[..., object] = requests.get,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict:
    """Acquire one response into a fresh directory; never mutate old evidence."""
    symbol = _symbol(symbol)
    if allow_network is not True:
        raise ValueError("SSE_CAPITAL_NETWORK_PERMISSION_REQUIRED")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError("SSE_CAPITAL_TIMEOUT_INVALID")
    timeout = float(timeout_seconds)
    if not 0.1 <= timeout <= 30.0:
        raise ValueError("SSE_CAPITAL_TIMEOUT_INVALID")
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError("SSE_CAPITAL_FRESH_OUTPUT_DIRECTORY_REQUIRED")
    url = _url(symbol)
    try:
        response = get(
            url,
            headers={"Referer": REFERER, "Accept": "application/json"},
            timeout=timeout,
        )
        status = getattr(response, "status_code", None)
        if type(status) is not int:
            raise SSECapitalAcquisitionError("SSE_CAPITAL_HTTP_RESPONSE_INVALID")
        if status < 200 or status >= 300:
            classification = (
                "SSE_CAPITAL_HTTP_RETRYABLE"
                if status == 429 or 500 <= status <= 599
                else "SSE_CAPITAL_HTTP_REJECTED"
            )
            raise SSECapitalAcquisitionError(classification, status)
        raw = getattr(response, "content", None)
        if not isinstance(raw, bytes) or not raw:
            raise SSECapitalAcquisitionError("SSE_CAPITAL_EMPTY_RESPONSE", status)
    except SSECapitalAcquisitionError:
        raise
    except requests.Timeout as error:
        raise SSECapitalAcquisitionError("SSE_CAPITAL_TIMEOUT") from error
    except requests.ConnectionError as error:
        raise SSECapitalAcquisitionError("SSE_CAPITAL_CONNECTION_FAILED") from error
    except requests.RequestException as error:
        raise SSECapitalAcquisitionError("SSE_CAPITAL_TRANSPORT_FAILED") from error

    # Timestamp receipt of the bytes, not the start of the HTTP attempt.
    acquired_at = _aware_utc(now(), "ACQUIRED_AT")
    parsed = _parse_payload(raw, symbol=symbol, as_of=acquired_at)
    digest = hashlib.sha256(raw).hexdigest()
    receipt = {
        "schema_version": VERSION,
        "status": "OFFICIAL_ROUNDED_SNAPSHOT_ACQUIRED",
        "symbol": symbol,
        "source_url": url,
        "sql_id": SQL_ID,
        "acquired_at": acquired_at.isoformat(),
        "raw_filename": RAW_FILENAME,
        "raw_sha256": digest,
        "observation": parsed,
        "formal_eligibility": False,
        "action": "no_order",
    }
    # Validate fully before the first filesystem write.  A transport or schema
    # failure therefore cannot corrupt or partially replace retained evidence.
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        (output_dir / RAW_FILENAME).write_bytes(raw)
        (output_dir / RECEIPT_FILENAME).write_text(
            json.dumps(receipt, ensure_ascii=True, indent=2, allow_nan=False),
            encoding="utf-8",
        )
    except Exception:
        # The directory was guaranteed fresh and belongs to this attempt.
        for path in (output_dir / RAW_FILENAME, output_dir / RECEIPT_FILENAME):
            if path.exists():
                path.unlink()
        output_dir.rmdir()
        raise
    return receipt


def replay_sse_current_capital_snapshot(
    *, receipt_path: Path, symbol: str, as_of: datetime
) -> dict:
    """Strictly replay retained bytes; this function performs no acquisition."""
    symbol = _symbol(symbol)
    as_of = _aware_utc(as_of, "AS_OF")
    receipt_path = Path(receipt_path).resolve()
    try:
        receipt = json.loads(receipt_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("SSE_CAPITAL_RECEIPT_INVALID") from error
    expected_receipt_fields = {
        "schema_version",
        "status",
        "symbol",
        "source_url",
        "sql_id",
        "acquired_at",
        "raw_filename",
        "raw_sha256",
        "observation",
        "formal_eligibility",
        "action",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_receipt_fields:
        raise ValueError("SSE_CAPITAL_RECEIPT_SCHEMA_INVALID")
    if (
        receipt["schema_version"] != VERSION
        or receipt["status"] != "OFFICIAL_ROUNDED_SNAPSHOT_ACQUIRED"
        or receipt["symbol"] != symbol
        or receipt["sql_id"] != SQL_ID
        or receipt["raw_filename"] != RAW_FILENAME
        or receipt["formal_eligibility"] is not False
        or receipt["action"] != "no_order"
        or not isinstance(receipt["raw_sha256"], str)
        or _SHA256.fullmatch(receipt["raw_sha256"]) is None
    ):
        raise ValueError("SSE_CAPITAL_RECEIPT_IDENTITY_INVALID")
    _validate_url(receipt["source_url"], symbol)
    try:
        acquired_at = _aware_utc(
            datetime.fromisoformat(receipt["acquired_at"]), "ACQUIRED_AT"
        )
    except (TypeError, ValueError) as error:
        raise ValueError("SSE_CAPITAL_ACQUIRED_AT_INVALID") from error
    if acquired_at > as_of:
        raise ValueError("SSE_CAPITAL_ACQUIRED_AFTER_AS_OF")
    raw_path = receipt_path.parent / receipt["raw_filename"]
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt["raw_sha256"]:
        raise ValueError("SSE_CAPITAL_RAW_HASH_MISMATCH")
    parsed = _parse_payload(raw, symbol=symbol, as_of=as_of)
    if parsed != receipt["observation"]:
        raise ValueError("SSE_CAPITAL_RECEIPT_OBSERVATION_MISMATCH")
    return {
        **parsed,
        "source_url": receipt["source_url"],
        "source_sha256": receipt["raw_sha256"],
        "acquired_at": acquired_at.isoformat(),
    }

"""Load and validate versioned M1 dividend-sustainability packages.

The package file owns official disclosure facts, lifecycle states, capacity
inputs and a low-confidence sustainability assessment.  This module performs
only the common source/hash and typed-domain conversion; it never creates an
order and never merges proposed, approved or paid lifecycle states.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .distribution import DividendResearchResult
from .research_artifact_codecs import DividendResearchCodec

PACKAGE_SCHEMA = "m1-distribution-package-v1"
DISTRIBUTION_DIRECTORY = "m1-distribution-packages-v1"


@dataclass(frozen=True)
class DividendPackageDescriptorAttempt:
    """One distribution-package conversion; failures stay isolated."""

    package_id: str
    symbol: str | None
    result: DividendResearchResult | None
    error: str | None

    def __post_init__(self) -> None:
        if not self.package_id.strip():
            raise ValueError("Dividend package attempt id is required")
        if (self.result is None) == (self.error is None):
            raise ValueError("Dividend package attempt must be success or failure")
        if self.symbol is not None and self.result is not None:
            if self.symbol != self.result.symbol:
                raise ValueError("Dividend package attempt symbol does not match")

    def as_policy(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "symbol": self.symbol,
            "action": "no_order",
            "error": self.error,
            "cash_return_status": (
                self.result.cash_return_status if self.result is not None else None
            ),
        }


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    return date.fromisoformat(value)


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed


def _verify_source(source: Mapping[str, Any], root: Path) -> dict[str, Any]:
    data = dict(source)
    source_id = _required_text(data.get("id"), "source.id")
    kind = _required_text(data.get("kind"), "source.kind")
    location = _required_text(data.get("location"), "source.location")
    expected = _required_text(data.get("sha256"), "source.sha256").lower()
    target = (root / location).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Distribution source escapes project root: {source_id}")
    if not target.exists():
        raise ValueError(f"Distribution source is missing: {source_id}")
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Distribution source hash changed: {source_id}")
    return {
        "id": source_id,
        "kind": kind,
        "location": location,
        "sha256": expected,
        "published_at": (
            _datetime(data["published_at"], f"source.{source_id}.published_at")
            if data.get("published_at") else None
        ),
        "retrieved_at": (
            _datetime(data["retrieved_at"], f"source.{source_id}.retrieved_at")
            if data.get("retrieved_at") else None
        ),
        "parser_version": (
            _required_text(data["parser_version"], f"source.{source_id}.parser_version")
            if data.get("parser_version") else None
        ),
    }


def build_dividend_result(
    payload: Mapping[str, Any],
    *,
    root: Path,
) -> DividendResearchResult:
    """Convert one verified package into the typed distribution artifact."""
    data = dict(payload)
    if data.get("schema_version") != PACKAGE_SCHEMA:
        raise ValueError(
            f"Unknown dividend package schema: {data.get('schema_version')}"
        )
    symbol = _required_text(data.get("symbol"), "package.symbol")
    name = _required_text(data.get("name"), "package.name")
    sources = [
        _verify_source(item, root)
        for item in data.get("sources") or []
    ]
    if not sources:
        raise ValueError("Dividend package requires at least one verified source")
    if len({source["id"] for source in sources}) != len(sources):
        raise ValueError("Dividend package source ids must be unique")
    if data.get("action") != "no_order":
        raise ValueError("Dividend package must remain no_order")

    result_payload = data.get("dividend_result")
    if not isinstance(result_payload, Mapping):
        raise ValueError("Dividend package requires a typed dividend_result")
    result = DividendResearchCodec().from_payload(dict(result_payload))
    if result.symbol != symbol:
        raise ValueError("Dividend package result symbol does not match package")
    if result.profile_id != _required_text(data.get("profile_id"), "package.profile_id"):
        raise ValueError("Dividend package result profile does not match package")
    if result.as_of > _required_date(data.get("research_as_of"), "package.research_as_of"):
        raise ValueError("Dividend package result as-of follows research as-of")
    return result


def load_dividend_package_attempts(
    root: Path,
) -> tuple[DividendPackageDescriptorAttempt, ...]:
    package_dir = root / "config" / DISTRIBUTION_DIRECTORY
    if not package_dir.exists():
        return ()
    attempts: list[DividendPackageDescriptorAttempt] = []
    for path in sorted(package_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            attempts.append(DividendPackageDescriptorAttempt(
                package_id=path.stem,
                symbol=None,
                result=None,
                error="dividend package must be a JSON object",
            ))
            continue
        symbol = (
            str(payload["symbol"])
            if isinstance(payload.get("symbol"), str) and payload["symbol"]
            else None
        )
        package_id = str(payload.get("run_id") or path.stem)
        try:
            result = build_dividend_result(payload, root=root)
        except Exception as error:
            attempts.append(DividendPackageDescriptorAttempt(
                package_id=package_id,
                symbol=symbol,
                result=None,
                error=f"{type(error).__name__}: {error}",
            ))
        else:
            attempts.append(DividendPackageDescriptorAttempt(
                package_id=package_id,
                symbol=result.symbol,
                result=result,
                error=None,
            ))
    return tuple(attempts)


def dividend_results_by_symbol(
    root: Path,
) -> dict[str, DividendResearchResult]:
    results: dict[str, DividendResearchResult] = {}
    for attempt in load_dividend_package_attempts(root):
        if attempt.error is not None:
            raise ValueError(
                f"Dividend package is invalid: {attempt.package_id}: {attempt.error}"
            )
        if attempt.symbol is None or attempt.result is None:
            raise ValueError(f"Dividend package has no symbol/result: {attempt.package_id}")
        if attempt.symbol in results:
            raise ValueError(f"Duplicate dividend package symbol: {attempt.symbol}")
        results[attempt.symbol] = attempt.result
    return results


def optional_dividend_result_for_symbol(
    root: Path,
    symbol: str,
) -> DividendResearchResult | None:
    if not (root / "config" / DISTRIBUTION_DIRECTORY).exists():
        return None
    return dividend_results_by_symbol(root).get(symbol)

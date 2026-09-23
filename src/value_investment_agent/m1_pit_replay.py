"""Replay official-filing availability boundaries for fixed-sample packages.

This module deliberately replays only which issuer filing is knowable at a
historical decision time. It never interpolates financial facts from the later
filing and never emits an execution instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "m1-pit-source-replay-v1"
ACTION_NO_ORDER = "no_order"

_LOCATION_PERIOD = re.compile(
    r"/(?P<period>\d{4}-\d{2}-\d{2})-"
    r"(?P<kind>annual|interim|first_quarter|third_quarter)-"
    r"(?P<hash>[0-9a-f]{64})\.pdf$"
)


def _required_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


@dataclass(frozen=True)
class FilingRecord:
    source_id: str
    period: date
    published_at: datetime
    retrieved_at: datetime | None
    location: str
    sha256: str


@dataclass(frozen=True)
class DecisionPoint:
    decision_at: datetime
    boundary_label: str
    selected_filing_ids: tuple[str, ...]
    excluded_future_filing_ids: tuple[str, ...]
    latest_selected_filing_id: str | None

    def as_policy(self) -> dict[str, Any]:
        return {
            "decision_at": self.decision_at.isoformat(),
            "boundary_label": self.boundary_label,
            "selected_filing_ids": list(self.selected_filing_ids),
            "excluded_future_filing_ids": list(
                self.excluded_future_filing_ids
            ),
            "latest_selected_filing_id": self.latest_selected_filing_id,
        }


def _parse_filing_period(location: str) -> date:
    match = _LOCATION_PERIOD.search(location)
    if match is None:
        raise ValueError(
            f"Official filing path has no period token: {location}"
        )
    return date.fromisoformat(match.group("period"))


def _official_filing_record(
    source: Mapping[str, Any],
    *,
    root: Path,
) -> FilingRecord | None:
    if source.get("kind") != "official_issuer_filing":
        return None
    source_id = str(source["id"])
    location = str(source["location"])
    published_at = source.get("published_at")
    retrieved_at = source.get("retrieved_at")
    if published_at is None:
        raise ValueError(
            f"Official filing {source_id} requires published_at"
        )
    published = datetime.fromisoformat(str(published_at))
    retrieved = (
        datetime.fromisoformat(str(retrieved_at))
        if retrieved_at is not None
        else None
    )
    for timestamp, label in ((published, "published_at"), (retrieved, "retrieved_at")):
        if timestamp is not None and timestamp.utcoffset() is None:
            raise ValueError(
                f"Official filing {source_id} {label} requires timezone"
            )
    expected = str(source["sha256"]).lower()
    if len(expected) != 64 or any(
        char not in "0123456789abcdef" for char in expected
    ):
        raise ValueError(f"Official filing {source_id} has an invalid SHA-256")
    source_path = root / location
    if not source_path.is_file():
        raise FileNotFoundError(f"Official filing source missing: {source_path}")
    actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"Official filing source changed: {source_id}")
    return FilingRecord(
        source_id=source_id,
        period=_parse_filing_period(location),
        published_at=published,
        retrieved_at=retrieved,
        location=location,
        sha256=expected,
    )


def replay_package_pit(
    payload: Mapping[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    data = _required_mapping(payload, "valuation package")
    symbol = str(data["symbol"])
    sources = data.get("sources")
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
        raise ValueError("Package sources must be a list")

    filings: list[FilingRecord] = []
    for item in sources:
        record = _official_filing_record(
            _required_mapping(item, "package.source"),
            root=root,
        )
        if record is not None:
            filings.append(record)
    if len(filings) < 2:
        raise ValueError(
            f"Package {symbol} requires at least two official filings"
        )
    filings.sort(key=lambda item: (item.published_at, item.period))

    moments: list[tuple[datetime, str, str]] = []
    for filing in filings:
        moments.append(
            (
                filing.published_at,
                f"after_{filing.source_id}",
                filing.source_id,
            )
        )
        moments.append(
            (
                filing.published_at - timedelta(seconds=1),
                f"before_{filing.source_id}",
                filing.source_id,
            )
        )
    moments.sort(key=lambda item: (item[0], item[2]))

    decisions: list[DecisionPoint] = []
    for decision_at, label, boundary_source_id in moments:
        selected = [
            item
            for item in filings
            if item.published_at <= decision_at
        ]
        selected.sort(key=lambda item: (item.period, item.published_at))
        excluded = [
            item
            for item in filings
            if item.published_at > decision_at
        ]
        excluded.sort(key=lambda item: (item.published_at, item.period))
        decisions.append(
            DecisionPoint(
                decision_at=decision_at,
                boundary_label=label,
                selected_filing_ids=tuple(item.source_id for item in selected),
                excluded_future_filing_ids=tuple(
                    item.source_id for item in excluded
                ),
                latest_selected_filing_id=(
                    selected[-1].source_id if selected else None
                ),
            )
        )

    return {
        "symbol": symbol,
        "package_id": str(data.get("package_id", data["run_id"])),
        "official_filings": [
            {
                "source_id": item.source_id,
                "period": item.period.isoformat(),
                "published_at": item.published_at.isoformat(),
                "retrieved_at": (
                    item.retrieved_at.isoformat()
                    if item.retrieved_at is not None
                    else None
                ),
                "location": item.location,
                "sha256": item.sha256,
            }
            for item in filings
        ],
        "decision_points": [item.as_policy() for item in decisions],
        "future_disclosure_rejections": [
            item.as_policy()
            for item in decisions
            if item.excluded_future_filing_ids
        ],
        "policy": [
            "availability is selected from official published_at, never retrieved_at",
            "a later filing is excluded at every earlier decision boundary",
            "selection identifies only knowable source identity; no later facts are interpolated",
        ],
    }


def build_pit_replay_payload(
    packages: Mapping[str, Mapping[str, Any]],
    *,
    root: Path,
    generated_at: datetime,
) -> dict[str, Any]:
    if not packages:
        raise ValueError("At least one valuation package is required")
    results = [
        replay_package_pit(payload, root=root)
        for payload in packages.values()
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "package_count": len(results),
        "packages": results,
        "limits": [
            "This is source-availability replay, not valuation replay.",
            "published_at is taken from the hash-pinned descriptor and is a conservative upper bound where intraday precision is unknown.",
            "Original pre-correction filings remain historical facts and are not rewritten.",
        ],
    }


def write_pit_replay_runtime(
    payload: dict[str, Any],
    *,
    root: Path,
    package_payloads: Mapping[str, Mapping[str, Any]],
    script_path: Path,
) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / "runtime" / f"m1-pit-source-replay-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    evidence = target / "evidence.json"
    evidence.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": payload["generated_at"],
        "action": ACTION_NO_ORDER,
        "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "package_sha256s": {
            symbol: hashlib.sha256(
                json.dumps(
                    package_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            for symbol, package_payload in package_payloads.items()
        },
        "script_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pointer = {
        "path": str(target.relative_to(root)),
        "sha256": manifest["evidence_sha256"],
    }
    (root / "runtime" / "m1-pit-source-replay-latest.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "evidence_path": str(evidence.relative_to(root)),
        "manifest_path": str((target / "manifest.json").relative_to(root)),
        "pointer_path": "runtime/m1-pit-source-replay-latest.json",
    }

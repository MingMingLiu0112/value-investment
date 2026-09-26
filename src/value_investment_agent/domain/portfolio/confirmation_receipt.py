"""Canonical M4 receipt for one human-confirmed portfolio reconciliation.

The receipt is a byte-bound record of a human assertion: it binds the exact
reconciliation bytes, account scope, snapshot date and confirmation string, but
it carries no signature, signer identity or external trust root.  It therefore
has no acceptance authority.  ``M4_PERSONALIZED_ACCEPTANCE`` stays with the
human milestone process and can never be satisfied by this object alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import re
from typing import Any, Mapping


PORTFOLIO_CONFIRMATION_RECEIPT_SCHEMA = "m4-portfolio-confirmation-receipt-v1"
PORTFOLIO_CONFIRMATION_FINGERPRINT_SCHEMA = "m4-portfolio-confirmation-fingerprint-v1"
USER_CONFIRMED_RECONCILIATION = "USER_CONFIRMED_RECONCILIATION"
ACTION_NO_ORDER = "no_order"
CONFIRMATION_AUTHENTICATION_BASIS = "UNSIGNED_HUMAN_ASSERTION"
CONFIRMATION_ACCEPTANCE_AUTHORITY = "NONE"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PRIVATE_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "action",
        "reconciliation_sha256",
        "account_scope",
        "snapshot_date",
        "user_confirmation",
        "confirmed_at",
        "confirmation_id",
        "receipt_sha256",
    }
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _required_date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _canonical_body(
    *,
    reconciliation_sha256: str,
    account_scope: str,
    snapshot_date: date,
    user_confirmation: str,
    confirmed_at: datetime,
    confirmation_id: str,
) -> dict[str, str]:
    return {
        "schema_version": PORTFOLIO_CONFIRMATION_RECEIPT_SCHEMA,
        "action": ACTION_NO_ORDER,
        "reconciliation_sha256": reconciliation_sha256,
        "account_scope": account_scope,
        "snapshot_date": snapshot_date.isoformat(),
        "user_confirmation": user_confirmation,
        "confirmed_at": confirmed_at.isoformat(),
        "confirmation_id": confirmation_id,
    }


def _body_bytes(body: Mapping[str, str]) -> bytes:
    return json.dumps(
        dict(body),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class PortfolioConfirmationReceipt:
    reconciliation_sha256: str
    account_scope: str
    snapshot_date: date
    user_confirmation: str
    confirmed_at: datetime
    confirmation_id: str
    receipt_sha256: str
    schema_version: str = PORTFOLIO_CONFIRMATION_RECEIPT_SCHEMA
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != PORTFOLIO_CONFIRMATION_RECEIPT_SCHEMA:
            raise ValueError("Unknown portfolio confirmation receipt schema")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Portfolio confirmation receipt must remain no_order")
        if not _SHA256.fullmatch(self.reconciliation_sha256):
            raise ValueError("reconciliation_sha256 must be lowercase SHA-256 hex")
        object.__setattr__(self, "account_scope", _required_text(self.account_scope, "account_scope"))
        _required_date(self.snapshot_date, "snapshot_date")
        if self.user_confirmation != USER_CONFIRMED_RECONCILIATION:
            raise ValueError("user_confirmation must explicitly confirm reconciliation")
        _required_datetime(self.confirmed_at, "confirmed_at")
        object.__setattr__(
            self,
            "confirmation_id",
            _required_text(self.confirmation_id, "confirmation_id"),
        )
        if not _SHA256.fullmatch(self.receipt_sha256):
            raise ValueError("receipt_sha256 must be lowercase SHA-256 hex")
        if self.receipt_sha256 != hashlib.sha256(self.canonical_bytes()).hexdigest():
            raise ValueError("portfolio confirmation receipt hash mismatch")

    def canonical_bytes(self) -> bytes:
        return _body_bytes(
            _canonical_body(
                reconciliation_sha256=self.reconciliation_sha256,
                account_scope=self.account_scope,
                snapshot_date=self.snapshot_date,
                user_confirmation=self.user_confirmation,
                confirmed_at=self.confirmed_at,
                confirmation_id=self.confirmation_id,
            )
        )

    def as_private_policy(self) -> dict[str, Any]:
        return {
            **json.loads(self.canonical_bytes().decode("utf-8")),
            "receipt_sha256": self.receipt_sha256,
        }

    def as_public_fingerprint(self) -> dict[str, str]:
        return {
            "schema_version": PORTFOLIO_CONFIRMATION_FINGERPRINT_SCHEMA,
            "action": ACTION_NO_ORDER,
            "receipt_schema_version": self.schema_version,
            "receipt_sha256": self.receipt_sha256,
            "sensitivity": "PUBLIC_FINGERPRINT_ONLY",
            "authentication_basis": CONFIRMATION_AUTHENTICATION_BASIS,
            "acceptance_authority": CONFIRMATION_ACCEPTANCE_AUTHORITY,
        }


def build_portfolio_confirmation_receipt(
    *,
    reconciliation_bytes: bytes,
    reconciliation_payload: Mapping[str, Any],
    user_confirmation: str,
    confirmed_at: datetime,
    confirmation_id: str,
) -> PortfolioConfirmationReceipt:
    if not isinstance(reconciliation_bytes, bytes) or not reconciliation_bytes:
        raise ValueError("reconciliation_bytes must be nonempty bytes")
    if not isinstance(reconciliation_payload, Mapping):
        raise ValueError("reconciliation payload must be an object")
    if reconciliation_payload.get("status") != "MATCH_PENDING_HUMAN_CONFIRMATION":
        raise ValueError("only a matching reconciliation can be confirmed")
    if reconciliation_payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("reconciliation payload must remain no_order")
    account_scope = _required_text(
        reconciliation_payload.get("account_scope"), "reconciliation account_scope"
    )
    snapshot_date = date.fromisoformat(
        _required_text(reconciliation_payload.get("as_of"), "reconciliation as_of")
    )
    body = _canonical_body(
        reconciliation_sha256=hashlib.sha256(reconciliation_bytes).hexdigest(),
        account_scope=account_scope,
        snapshot_date=snapshot_date,
        user_confirmation=_required_text(user_confirmation, "user_confirmation"),
        confirmed_at=_required_datetime(confirmed_at, "confirmed_at"),
        confirmation_id=_required_text(confirmation_id, "confirmation_id"),
    )
    return PortfolioConfirmationReceipt(
        reconciliation_sha256=body["reconciliation_sha256"],
        account_scope=body["account_scope"],
        snapshot_date=snapshot_date,
        user_confirmation=body["user_confirmation"],
        confirmed_at=confirmed_at,
        confirmation_id=body["confirmation_id"],
        receipt_sha256=hashlib.sha256(_body_bytes(body)).hexdigest(),
    )


def portfolio_confirmation_receipt_from_payload(
    payload: Mapping[str, Any],
) -> PortfolioConfirmationReceipt:
    if not isinstance(payload, Mapping) or set(payload) != _PRIVATE_RECEIPT_KEYS:
        raise ValueError("portfolio confirmation receipt has an invalid contract")
    return PortfolioConfirmationReceipt(
        schema_version=str(payload["schema_version"]),
        action=str(payload["action"]),
        reconciliation_sha256=str(payload["reconciliation_sha256"]),
        account_scope=str(payload["account_scope"]),
        snapshot_date=date.fromisoformat(str(payload["snapshot_date"])),
        user_confirmation=str(payload["user_confirmation"]),
        confirmed_at=datetime.fromisoformat(str(payload["confirmed_at"])),
        confirmation_id=str(payload["confirmation_id"]),
        receipt_sha256=str(payload["receipt_sha256"]),
    )

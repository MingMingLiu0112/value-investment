"""WEB-D1 manual private portfolio intake, fill lifecycle and reconciliation.

This module is the single durable authority for trades the user records by hand.
It stores an append-only, hash-chained journal in a private directory outside
the repository, and every cash, cost, sellable-share and realized-profit figure
comes from the existing pure reconciliation arithmetic. It never submits an
order, never asks a broker, and never invents a price or a market value.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from ...domain.portfolio.dual_sleeve_records import canonical_bytes
from ...portfolio_contracts import (
    NAMESPACE_ACTUAL,
    PortfolioHolding,
    PortfolioSnapshot,
    QUANTITY_HUMAN_CONFIRMED,
    RECONCILIATION_RECONCILED,
)
from ...private_portfolio_intake import require_private_data_path
from .private_journal_lock import InterProcessLock, LockTimeout
from .web_reconciliation import (
    SLEEVES,
    Fill,
    Reconciliation,
    confirm,
    initialize,
    portfolio_snapshot,
    prepare,
)

SCHEMA_VERSION = "private-portfolio-journal-v1"
PRIVATE_ROOT_ENV = "VALUE_INVESTMENT_PRIVATE_ROOT"
DEFAULT_PRIVATE_DIRECTORY = "value-investment-private"
JOURNAL_RELATIVE_PATH = Path("portfolio") / "journal.jsonl"
RECORD_KINDS = frozenset({
    "BASELINE_CONFIRMED", "FILL_PREPARED", "FILL_CONFIRMED", "FILL_CANCELLED",
    "RECONCILED_CONFIRMED",
})
EXCHANGES = frozenset({"SSE", "SZSE", "BSE"})
SIDES = frozenset({"BUY", "SELL"})
POLICY_DECIMAL_FIELDS = (
    "investable_assets_cny",
    "minimum_cash_cny",
    "emergency_cash_cny",
    "liquidity_needs_cny",
    "max_single_security_pct",
    "max_single_industry_pct",
    "dividend_income_goal_cny",
)
POLICY_TEXT_FIELDS = ("risk_tolerance",)
PRICE_ADMISSION_REASON = "尚未接入经核验的当前行情，无法计算市值、浮动盈亏与仓位权重"


class PrivateStoreUnavailable(RuntimeError):
    """The private root is missing or unsafe on this machine (HTTP 503)."""


class JournalValidationError(ValueError):
    """User input or a stored record failed validation (HTTP 422)."""


class JournalConflict(RuntimeError):
    """A business conflict that must stay visible to the client (HTTP 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _decimal(
    value: object,
    field: str,
    *,
    positive: bool = False,
    maximum: Decimal | None = None,
) -> Decimal:
    """Read a user supplied amount without floats, locale or silent coercion."""
    if isinstance(value, bool) or value is None:
        raise JournalValidationError(f"{field} 必须是十进制数字")
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        amount = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise JournalValidationError(f"{field} 不能为空")
        try:
            amount = Decimal(text)
        except InvalidOperation as error:
            raise JournalValidationError(f"{field} 不是合法十进制数字") from error
    else:
        raise JournalValidationError(f"{field} 必须是十进制数字")
    if not amount.is_finite():
        raise JournalValidationError(f"{field} 必须是有限数字")
    if amount < 0:
        raise JournalValidationError(f"{field} 不能为负数")
    if positive and amount == 0:
        raise JournalValidationError(f"{field} 必须大于零")
    if maximum is not None and amount > maximum:
        raise JournalValidationError(f"{field} 不能超过 {maximum}")
    return amount


def _whole_shares(value: object, field: str) -> Decimal:
    amount = _decimal(value, field, positive=True)
    assert amount is not None
    if amount != amount.to_integral_value():
        raise JournalValidationError(f"{field} 必须是整数股")
    return amount


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JournalValidationError(f"{field} 必须是非空文本")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _date_value(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise JournalValidationError(f"{field} 必须是 YYYY-MM-DD 字符串")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as error:
        raise JournalValidationError(f"{field} 不是合法日期") from error


def _aware_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise JournalValidationError(f"{field} 必须是带时区的 ISO8601 字符串")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise JournalValidationError(f"{field} 不是合法时间") from error
    if parsed.utcoffset() is None:
        raise JournalValidationError(f"{field} 必须包含时区偏移")
    return parsed


def _symbol(value: object) -> str:
    text = _text(value, "symbol")
    if len(text) != 6 or not text.isdigit():
        raise JournalValidationError("证券代码必须是 6 位数字")
    return text


def _exchange(value: object) -> str:
    text = _text(value, "exchange").upper()
    if text not in EXCHANGES:
        raise JournalValidationError("exchange 必须是 SSE、SZSE 或 BSE")
    return text


def _sleeve(value: object) -> str:
    text = _text(value, "sleeve").upper()
    if text not in SLEEVES:
        raise JournalValidationError("sleeve 必须是 CORE_VALUE 或 HOTSPOT_SATELLITE")
    return text


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise JournalValidationError(f"{field} 必须是对象")
    return value


def _sequence(value: object, field: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise JournalValidationError(f"{field} 必须是数组")
    return tuple(value)


def _idempotency_key(request: Mapping[str, Any]) -> str:
    return _text(request.get("idempotency_key"), "idempotency_key")


def _expected_revision(request: Mapping[str, Any]) -> int:
    value = request.get("expected_revision")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise JournalValidationError("expected_revision 必须是非负整数")
    return value


def request_digest(request: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes({str(key): value for key, value in request.items()})).hexdigest()


def resolve_private_root(*, repository_root: Path, environ: Mapping[str, str] | None = None) -> Path:
    """Resolve and validate the private root without creating anything."""
    environment = os.environ if environ is None else environ
    configured = environment.get(PRIVATE_ROOT_ENV)
    root = Path(configured).expanduser() if configured else Path.home() / DEFAULT_PRIVATE_DIRECTORY
    root = root.resolve()
    if not root.is_dir():
        raise PrivateStoreUnavailable(
            f"私人数据目录 {root} 不存在；请在仓库与同步目录之外创建该目录，或设置环境变量 {PRIVATE_ROOT_ENV}"
        )
    try:
        return require_private_data_path(
            root / JOURNAL_RELATIVE_PATH,
            private_root=root,
            repository_root=repository_root,
        )
    except ValueError as error:
        raise PrivateStoreUnavailable(str(error)) from error


@dataclass(frozen=True)
class ReplayedPortfolio:
    revision: int
    state: Reconciliation
    policy: dict[str, Any]
    trades: tuple[dict[str, Any], ...]
    snapshot: dict[str, Any] | None
    pending: dict[str, Any] | None
    draft: Reconciliation | None


class PrivateJournal:
    """Append-only JSONL journal with a per-record hash chain."""

    def __init__(self, path: Path, *, lock_timeout_seconds: float = 10.0) -> None:
        self.path = path
        self.lock_timeout_seconds = lock_timeout_seconds
        self._thread_lock = threading.RLock()
        self._lock = InterProcessLock(
            path.with_name(path.name + ".lock"), timeout_seconds=lock_timeout_seconds
        )

    @contextmanager
    def transaction(self) -> Iterator[list[dict[str, Any]]]:
        """Hold the cross-process lock across read, validation and append.

        Business methods must do their whole read-check-commit inside this
        block. Appending outside it lets two processes pass the same revision
        check and then both write, which corrupts the hash chain and can
        double-count a confirmed fill.
        """
        with self._thread_lock:
            try:
                self._lock.acquire()
            except LockTimeout as error:
                raise PrivateStoreUnavailable(str(error)) from error
            try:
                yield self.read()
            finally:
                self._lock.release()

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        previous: str | None = None
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise JournalValidationError(f"私人流水第 {line_number} 行不是合法 JSON") from error
            self._validate_record(record, line_number=line_number, previous=previous)
            previous = record["record_sha256"]
            records.append(record)
        return records

    @staticmethod
    def _validate_record(record: object, *, line_number: int, previous: str | None) -> None:
        if not isinstance(record, dict):
            raise JournalValidationError(f"私人流水第 {line_number} 行不是对象")
        if record.get("schema_version") != SCHEMA_VERSION:
            raise JournalValidationError(f"私人流水第 {line_number} 行 schema 无法识别")
        if record.get("action") != "no_order":
            raise JournalValidationError(f"私人流水第 {line_number} 行 action 被篡改")
        if record.get("kind") not in RECORD_KINDS:
            raise JournalValidationError(f"私人流水第 {line_number} 行记录类型未知")
        if record.get("previous_record_sha256") != previous:
            raise JournalValidationError(f"私人流水第 {line_number} 行哈希链断裂")
        digest = record.get("record_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise JournalValidationError(f"私人流水第 {line_number} 行缺少摘要")
        payload = {key: value for key, value in record.items() if key != "record_sha256"}
        if hashlib.sha256(canonical_bytes(payload)).hexdigest() != digest:
            raise JournalValidationError(f"私人流水第 {line_number} 行内容与摘要不一致")

    def append(
        self,
        *,
        kind: str,
        body: Mapping[str, Any],
        response: Mapping[str, Any],
        idempotency_key: str,
        request_sha256: str,
        recorded_at: datetime,
        changes_holdings: bool,
    ) -> dict[str, Any]:
        if kind not in RECORD_KINDS:
            raise JournalValidationError("未知的私人流水类型")
        if self._lock.held_by_current_thread():
            return self._append_locked(
                kind=kind, body=body, response=response, idempotency_key=idempotency_key,
                request_sha256=request_sha256, recorded_at=recorded_at,
                changes_holdings=changes_holdings,
            )
        with self.transaction():
            return self._append_locked(
                kind=kind, body=body, response=response, idempotency_key=idempotency_key,
                request_sha256=request_sha256, recorded_at=recorded_at,
                changes_holdings=changes_holdings,
            )

    def _append_locked(
        self,
        *,
        kind: str,
        body: Mapping[str, Any],
        response: Mapping[str, Any],
        idempotency_key: str,
        request_sha256: str,
        recorded_at: datetime,
        changes_holdings: bool,
    ) -> dict[str, Any]:
        records = self.read()
        previous = records[-1]["record_sha256"] if records else None
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "sequence": len(records) + 1,
            "recorded_at": recorded_at.isoformat(),
            "kind": kind,
            "previous_record_sha256": previous,
            "idempotency_key": idempotency_key,
            "request_sha256": request_sha256,
            "action": "no_order",
            "changes_holdings": changes_holdings,
            "body": json.loads(canonical_bytes(dict(body))),
            "response": json.loads(canonical_bytes(dict(response))),
        }
        record["record_sha256"] = hashlib.sha256(canonical_bytes(record)).hexdigest()
        self._write_line(record)
        return record

    def _write_line(self, record: Mapping[str, Any]) -> None:
        """Append one record and fsync it. Callers must hold the journal lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            stream.write(canonical_bytes(record) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())


def _evidence_ref(identifier: str, kind: str) -> dict[str, str]:
    return {"id": identifier, "kind": kind}


def _baseline_snapshot(body: Mapping[str, Any]) -> PortfolioSnapshot:
    evidence = _evidence_ref(f"private-intake-{body['snapshot_id']}", "user_confirmation")
    holdings = []
    for row in _sequence(body["holdings"], "holdings"):
        row = _mapping(row, "holding")
        holdings.append(
            PortfolioHolding(
                symbol=_symbol(row.get("symbol")),
                exchange=_exchange(row.get("exchange")),
                quantity=_whole_shares(row.get("quantity"), "quantity"),
                cost_basis_cny=_decimal(row.get("cost_basis_cny"), "cost_basis_cny"),
                market_value_cny=None,
                quantity_source=QUANTITY_HUMAN_CONFIRMED,
                corporate_action_adjusted=False,
                evidence_refs=(evidence,),
            )
        )
    return PortfolioSnapshot(
        snapshot_id=str(body["snapshot_id"]),
        snapshot_version="v1",
        as_of=_date_value(body["as_of"], "as_of"),
        available_at=_aware_datetime(body["available_at"], "available_at"),
        account_scope=str(body["account_scope"]),
        namespace=NAMESPACE_ACTUAL,
        cash_cny=_decimal(body["cash_cny"], "cash_cny"),
        holdings=tuple(holdings),
        reconciliation_status=RECONCILIATION_RECONCILED,
        reconciled_at=_aware_datetime(body["available_at"], "available_at"),
        evidence_refs=(evidence,),
    )


def _allocations(body: Mapping[str, Any]) -> dict[tuple[str, str], Decimal]:
    allocations: dict[tuple[str, str], Decimal] = {}
    for symbol, sleeves in _mapping(body.get("sleeve_allocations", {}), "sleeve_allocations").items():
        symbol = _symbol(symbol)
        for sleeve, quantity in _mapping(sleeves, "sleeve_allocations entry").items():
            allocations[( _sleeve(sleeve), symbol)] = _whole_shares(quantity, "sleeve allocation")
    return allocations


def _fill_from_body(body: Mapping[str, Any]) -> Fill:
    fill = _mapping(body["fill"], "fill")
    side = _text(fill.get("side"), "side").upper()
    if side not in SIDES:
        raise JournalValidationError("side 必须是 BUY 或 SELL")
    next_sell = fill.get("next_sell_session")
    trading_unit = fill.get("trading_unit")
    corporate_action = fill.get("corporate_action", False)
    if not isinstance(corporate_action, bool):
        raise JournalValidationError("corporate_action 必须是布尔值")
    return Fill(
        transaction_id=_text(fill.get("transaction_id"), "transaction_id"),
        side=side,
        sleeve=_sleeve(fill.get("sleeve")),
        symbol=_symbol(fill.get("symbol")),
        exchange=_exchange(fill.get("exchange")),
        quantity=_whole_shares(fill.get("quantity"), "quantity"),
        price_cny=_decimal(fill.get("price_cny"), "price_cny", positive=True),
        fees_cny=_decimal(fill.get("fees_cny", "0"), "fees_cny"),
        trade_date=_date_value(fill.get("trade_date"), "trade_date"),
        next_sell_session=_date_value(next_sell, "next_sell_session") if next_sell is not None else None,
        trading_unit=_whole_shares(trading_unit, "trading_unit") if trading_unit is not None else None,
        corporate_action=corporate_action,
    )


class PrivatePortfolioService:
    """Durable manual portfolio authority reused by the Web workbench."""

    def __init__(self, journal: PrivateJournal) -> None:
        self.journal = journal

    def records(self) -> list[dict[str, Any]]:
        return self.journal.read()

    def _find_idempotent(self, records: Sequence[Mapping[str, Any]], key: str, digest: str) -> Mapping[str, Any] | None:
        for record in records:
            if record.get("idempotency_key") == key:
                if record.get("request_sha256") != digest:
                    raise JournalConflict("IDEMPOTENCY_CONFLICT", "同一幂等键提交了不同内容")
                return record
        return None

    def _replay(self, records: Sequence[Mapping[str, Any]]) -> ReplayedPortfolio | None:
        state: Reconciliation | None = None
        policy: dict[str, Any] = {}
        trades: list[dict[str, Any]] = []
        snapshot: dict[str, Any] | None = None
        pending: dict[str, Any] | None = None
        draft: Reconciliation | None = None
        for record in records:
            kind = record["kind"]
            body = record["body"]
            if kind == "BASELINE_CONFIRMED":
                state = initialize(_baseline_snapshot(body), _allocations(body))
                policy = json.loads(canonical_bytes(dict(body["policy"])))
            elif kind == "FILL_PREPARED":
                if state is None:
                    raise JournalValidationError("私人流水缺少初始组合")
                draft = prepare(state, _fill_from_body(body), expected_version=state.version)
                pending = {
                    "status": "DRAFT_UNRECONFIRMED",
                    "prepared_record_sha256": record["record_sha256"],
                    "fill": json.loads(canonical_bytes(dict(body["fill"]))),
                    "cash_cny": str(draft.cash_cny),
                    "realized_pnl_cny": str(draft.realized_pnl_cny),
                    "context": (body.get("note") if isinstance(body.get("note"), str) else None),
                    "positions": self._positions(draft, self._sellable_as_of(draft, None)),
                }
            elif kind == "FILL_CONFIRMED":
                if state is None:
                    raise JournalValidationError("私人流水缺少初始组合")
                fill = _fill_from_body(body)
                if body.get("prepared_record_sha256") != (pending or {}).get("prepared_record_sha256"):
                    raise JournalValidationError("确认记录与待确认草稿不一致")
                confirmation = _mapping(body["confirmation"], "confirmation")
                confirmed_draft = prepare(state, fill, expected_version=state.version)
                state = confirm(
                    confirmed_draft,
                    expected_version=confirmed_draft.version,
                    confirmed_at=_aware_datetime(confirmation.get("confirmed_at"), "confirmed_at"),
                    evidence_ref=dict(body["evidence_ref"]),
                )
                trades.append({
                    "transaction_id": fill.transaction_id,
                    "side": fill.side,
                    "sleeve": fill.sleeve,
                    "symbol": fill.symbol,
                    "exchange": fill.exchange,
                    "quantity": str(fill.quantity),
                    "price_cny": str(fill.price_cny),
                    "fees_cny": str(fill.fees_cny),
                    "trade_date": fill.trade_date.isoformat(),
                    "next_sell_session": fill.next_sell_session.isoformat() if fill.next_sell_session else None,
                    "confirmed_at": str(confirmation.get("confirmed_at")),
                    "record_sha256": record["record_sha256"],
                })
                pending = None
                draft = None
            elif kind == "FILL_CANCELLED":
                if pending is None or body.get("prepared_record_sha256") != pending.get("prepared_record_sha256"):
                    raise JournalValidationError("作废记录与待确认草稿不一致")
                pending = None
                draft = None
            elif kind == "RECONCILED_CONFIRMED":
                snapshot = json.loads(canonical_bytes(dict(body["snapshot"])))
        if state is None:
            return None
        return ReplayedPortfolio(len(records), state, policy, tuple(trades), snapshot, pending, draft)

    @staticmethod
    def _sellable_as_of(state: Reconciliation, requested: date | None) -> date:
        if requested is not None:
            return requested
        return max(state.last_trade_date, datetime.now().astimezone().date())

    def _positions(self, state: Reconciliation, sellable_as_of: date) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for lot in state.lots:
            entry = grouped.setdefault((lot.symbol, lot.exchange), {
                "symbol": lot.symbol,
                "exchange": lot.exchange,
                "quantity": Decimal(0),
                "cost_cny": Decimal(0),
                "sleeves": {},
            })
            entry["quantity"] += lot.quantity
            entry["cost_cny"] += lot.cost_cny
            sleeve = entry["sleeves"].setdefault(lot.sleeve, {
                "sleeve": lot.sleeve,
                "quantity": Decimal(0),
                "cost_cny": Decimal(0),
                "sellable_quantity": Decimal(0),
                "next_sell_session": None,
            })
            sleeve["quantity"] += lot.quantity
            sleeve["cost_cny"] += lot.cost_cny
            if lot.sellable_on <= sellable_as_of:
                sleeve["sellable_quantity"] += lot.quantity
            elif sleeve["next_sell_session"] is None or lot.sellable_on > sleeve["next_sell_session"]:
                sleeve["next_sell_session"] = lot.sellable_on
        positions = []
        for entry in grouped.values():
            sleeves = []
            for sleeve in entry["sleeves"].values():
                quantity = sleeve["quantity"]
                cost = sleeve["cost_cny"]
                sleeves.append({
                    "sleeve": sleeve["sleeve"],
                    "quantity": str(quantity),
                    "cost_cny": str(cost),
                    "average_cost_cny": str(cost / quantity),
                    "sellable_quantity": str(sleeve["sellable_quantity"]),
                    "next_sell_session": sleeve["next_sell_session"].isoformat() if sleeve["next_sell_session"] else None,
                })
            sleeves.sort(key=lambda row: row["sleeve"])
            quantity = entry["quantity"]
            cost = entry["cost_cny"]
            positions.append({
                "symbol": entry["symbol"],
                "exchange": entry["exchange"],
                "quantity": str(quantity),
                "cost_cny": str(cost),
                "average_cost_cny": str(cost / quantity),
                "sleeves": sleeves,
                "market_value_cny": None,
                "floating_pnl_cny": None,
                "weight_pct": None,
            })
        positions.sort(key=lambda row: row["symbol"])
        return positions

    def _portfolio_payload(self, replayed: ReplayedPortfolio, *, today: date | None = None) -> dict[str, Any]:
        state = replayed.state
        sellable_as_of = self._sellable_as_of(state, today)
        return {
            "action": "no_order",
            "revision": replayed.revision,
            "as_of": state.baseline.as_of.isoformat(),
            "cash_cny": str(state.cash_cny),
            "realized_pnl_cny": str(state.realized_pnl_cny),
            "positions": self._positions(state, sellable_as_of),
            "trades": [dict(trade) for trade in replayed.trades],
            "policy": dict(replayed.policy),
            "pending_draft": replayed.pending,
            "latest_snapshot": replayed.snapshot,
            "sellable_as_of": sellable_as_of.isoformat(),
            "valuation": {"status": "PRICE_NOT_ADMITTED", "reason": PRICE_ADMISSION_REASON},
            "blockers": ["PRICE_NOT_ADMITTED"],
        }

    def portfolio_view(self, *, today: date | None = None) -> dict[str, Any]:
        records = self.records()
        if not records:
            return {
                "action": "no_order",
                "status": "NOT_CONNECTED",
                "revision": 0,
                "as_of": None,
                "cash_cny": None,
                "realized_pnl_cny": None,
                "positions": [],
                "trades": [],
                "policy": None,
                "pending_draft": None,
                "latest_snapshot": None,
                "valuation": {"status": "NOT_CONNECTED", "reason": "尚未确认真实私人持仓"},
                "blockers": ["PRIVATE_PORTFOLIO_NOT_CONNECTED", "PRICE_NOT_ADMITTED"],
            }
        replayed = self._replay(records)
        assert replayed is not None
        payload = self._portfolio_payload(replayed, today=today)
        payload["status"] = "CONNECTED"
        return payload

    @staticmethod
    def _policy_body(policy: object) -> dict[str, Any]:
        source = _mapping(policy if policy is not None else {}, "policy")
        body: dict[str, Any] = {"action": "no_order"}
        for field in POLICY_DECIMAL_FIELDS:
            if source.get(field) is not None:
                maximum = Decimal(100) if field.endswith("_pct") else None
                body[field] = str(_decimal(source[field], field, maximum=maximum))
        for field in POLICY_TEXT_FIELDS:
            if source.get(field) is not None:
                body[field] = _text(source[field], field)
        restrictions = source.get("restrictions", ["no_order"])
        body["restrictions"] = [_text(item, "restrictions") for item in _sequence(restrictions, "restrictions")]
        return body

    def _initialize_body(self, request: Mapping[str, Any]) -> dict[str, Any]:
        confirmed_at = _aware_datetime(request.get("confirmed_at"), "confirmed_at")
        as_of = _date_value(request.get("as_of"), "as_of")
        account_scope = _text(request.get("account_scope"), "account_scope")
        holdings = []
        for row in _sequence(request.get("holdings"), "holdings"):
            entry = _mapping(row, "holding")
            holdings.append({
                "symbol": _symbol(entry.get("symbol")),
                "exchange": _exchange(entry.get("exchange")),
                "quantity": str(_whole_shares(entry.get("quantity"), "quantity")),
                "cost_basis_cny": str(_decimal(entry.get("cost_basis_cny"), "cost_basis_cny")),
            })
        if not holdings:
            raise JournalValidationError("初始化至少需要一只已确认持仓")
        if len({row["symbol"] for row in holdings}) != len(holdings):
            raise JournalValidationError("初始化持仓不能重复同一证券")
        allocations: dict[str, dict[str, str]] = {}
        for symbol, sleeves in _mapping(request.get("sleeve_allocations", {}), "sleeve_allocations").items():
            code = _symbol(symbol)
            allocations[code] = {
                _sleeve(sleeve): str(_whole_shares(quantity, "sleeve allocation"))
                for sleeve, quantity in _mapping(sleeves, "sleeve_allocations entry").items()
            }
        return {
            "snapshot_id": _text(request.get("snapshot_id", f"private-{as_of.isoformat()}"), "snapshot_id"),
            "account_scope": account_scope,
            "as_of": as_of.isoformat(),
            "available_at": confirmed_at.isoformat(),
            "cash_cny": str(_decimal(request.get("cash_cny"), "cash_cny")),
            "holdings": holdings,
            "sleeve_allocations": allocations,
            "policy": self._policy_body(request.get("policy")),
            "confirmation": {
                "note": _text(request.get("confirmation_note"), "confirmation_note"),
                "confirmed_at": confirmed_at.isoformat(),
            },
            "evidence_ref": _evidence_ref(f"private-intake-{account_scope}", "user_confirmation"),
        }

    @staticmethod
    def _fill_body(request: Mapping[str, Any]) -> dict[str, Any]:
        fill = _fill_from_body(request)
        return {
            "transaction_id": fill.transaction_id,
            "side": fill.side,
            "sleeve": fill.sleeve,
            "symbol": fill.symbol,
            "exchange": fill.exchange,
            "quantity": str(fill.quantity),
            "price_cny": str(fill.price_cny),
            "fees_cny": str(fill.fees_cny),
            "trade_date": fill.trade_date.isoformat(),
            "next_sell_session": fill.next_sell_session.isoformat() if fill.next_sell_session else None,
            "trading_unit": str(fill.trading_unit) if fill.trading_unit is not None else None,
            "corporate_action": fill.corporate_action,
        }

    def _existing(self, records, request) -> tuple[dict[str, Any], str] | None:
        key = _idempotency_key(request)
        digest = request_digest(request)
        record = self._find_idempotent(records, key, digest)
        if record is None:
            return None
        return dict(record["response"]), str(record["record_sha256"])

    def _require_revision(self, records, request) -> int:
        revision = len(records)
        expected = _expected_revision(request)
        if expected != revision:
            raise JournalConflict("VERSION_CONFLICT", f"当前 revision 为 {revision}，请求为 {expected}")
        return revision

    def initialize(self, request: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        with self.journal.transaction() as records:
            return self._initialize(records, request)

    def _initialize(
        self, records: Sequence[Mapping[str, Any]], request: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        existing = self._existing(records, request)
        if existing is not None:
            return existing
        if records:
            raise JournalConflict("ALREADY_INITIALIZED", "私人组合已初始化，不能重复初始化")
        self._require_revision(records, request)
        body = self._initialize_body(request)
        state = initialize(_baseline_snapshot(body), _allocations(body))
        replayed = ReplayedPortfolio(1, state, body["policy"], (), None, None, None)
        payload = self._portfolio_payload(replayed)
        payload["status"] = "BASELINE_CONFIRMED"
        record = self.journal.append(
            kind="BASELINE_CONFIRMED",
            body=body,
            response=payload,
            idempotency_key=_idempotency_key(request),
            request_sha256=request_digest(request),
            recorded_at=datetime.now().astimezone(),
            changes_holdings=True,
        )
        return dict(record["response"]), str(record["record_sha256"])

    def prepare_fill(self, request: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        with self.journal.transaction() as records:
            return self._prepare_fill(records, request)

    def _prepare_fill(
        self, records: Sequence[Mapping[str, Any]], request: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        existing = self._existing(records, request)
        if existing is not None:
            return existing
        if not records:
            raise JournalConflict("NOT_CONNECTED", "私人组合尚未初始化，无法记录成交")
        revision = self._require_revision(records, request)
        replayed = self._replay(records)
        assert replayed is not None
        if replayed.pending is not None:
            raise JournalConflict("PENDING_DRAFT_EXISTS", "存在未确认的成交草稿，请先确认")
        fill = _fill_from_body(request)
        try:
            draft = prepare(replayed.state, fill, expected_version=replayed.state.version)
        except ValueError as error:
            message = str(error)
            if "duplicate" in message:
                raise JournalConflict("DUPLICATE_TRANSACTION", "该成交编号已经确认过") from error
            raise JournalValidationError(message) from error
        body = {
            "fill": self._fill_body(request),
            "prepared_at": datetime.now().astimezone().isoformat(),
            "note": _optional_text(request.get("note"), "note"),
        }
        payload = {
            "action": "no_order",
            "status": "FILL_PREPARED",
            "revision": revision + 1,
            "draft": {
                "status": "DRAFT_UNRECONFIRMED",
                "fill": dict(body["fill"]),
                "cash_cny": str(draft.cash_cny),
                "realized_pnl_cny": str(draft.realized_pnl_cny),
                "positions": self._positions(draft, self._sellable_as_of(draft, None)),
            },
        }
        record = self.journal.append(
            kind="FILL_PREPARED",
            body=body,
            response=payload,
            idempotency_key=_idempotency_key(request),
            request_sha256=request_digest(request),
            recorded_at=datetime.now().astimezone(),
            changes_holdings=False,
        )
        return dict(record["response"]), str(record["record_sha256"])

    def confirm_fill(self, request: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        with self.journal.transaction() as records:
            return self._confirm_fill(records, request)

    def _confirm_fill(
        self, records: Sequence[Mapping[str, Any]], request: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        existing = self._existing(records, request)
        if existing is not None:
            return existing
        if not records:
            raise JournalConflict("NOT_CONNECTED", "私人组合尚未初始化，无法确认成交")
        revision = self._require_revision(records, request)
        replayed = self._replay(records)
        assert replayed is not None
        if replayed.pending is None or replayed.draft is None:
            raise JournalConflict("NO_CONFIRMABLE_DRAFT", "没有待确认的成交草稿")
        prepared_digest = _text(request.get("prepared_record_sha256"), "prepared_record_sha256")
        if prepared_digest != replayed.pending["prepared_record_sha256"]:
            raise JournalConflict("NO_CONFIRMABLE_DRAFT", "草稿摘要与当前待确认成交不一致")
        prepared = records[-1]
        if prepared["kind"] != "FILL_PREPARED":
            raise JournalConflict("NO_CONFIRMABLE_DRAFT", "最后一条记录不是成交草稿")
        fill = _fill_from_body(prepared["body"])
        confirmed_at = _aware_datetime(request.get("confirmed_at"), "confirmed_at")
        evidence = _evidence_ref(f"fill-{str(prepared['record_sha256'])[:16]}", "user_confirmation")
        confirmation = {
            "note": _text(request.get("confirmation_note"), "confirmation_note"),
            "confirmed_at": confirmed_at.isoformat(),
        }
        try:
            state = confirm(
                replayed.draft,
                expected_version=replayed.draft.version,
                confirmed_at=confirmed_at,
                evidence_ref=evidence,
            )
        except ValueError as error:
            raise JournalValidationError(str(error)) from error
        trade = {
            "transaction_id": fill.transaction_id,
            "side": fill.side,
            "sleeve": fill.sleeve,
            "symbol": fill.symbol,
            "exchange": fill.exchange,
            "quantity": str(fill.quantity),
            "price_cny": str(fill.price_cny),
            "fees_cny": str(fill.fees_cny),
            "trade_date": fill.trade_date.isoformat(),
            "next_sell_session": fill.next_sell_session.isoformat() if fill.next_sell_session else None,
            "confirmed_at": confirmed_at.isoformat(),
        }
        body = {
            "fill": dict(prepared["body"]["fill"]),
            "prepared_record_sha256": str(prepared["record_sha256"]),
            "confirmation": confirmation,
            "evidence_ref": evidence,
            "trade": trade,
        }
        replayed_after = ReplayedPortfolio(
            revision + 1, state, replayed.policy, replayed.trades + (trade,), replayed.snapshot, None, None
        )
        payload = self._portfolio_payload(replayed_after)
        payload["status"] = "FILL_CONFIRMED"
        payload["confirmed_transaction_id"] = fill.transaction_id
        record = self.journal.append(
            kind="FILL_CONFIRMED",
            body=body,
            response=payload,
            idempotency_key=_idempotency_key(request),
            request_sha256=request_digest(request),
            recorded_at=datetime.now().astimezone(),
            changes_holdings=True,
        )
        return dict(record["response"]), str(record["record_sha256"])

    def reconcile(self, request: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        with self.journal.transaction() as records:
            return self._reconcile(records, request)

    def _reconcile(
        self, records: Sequence[Mapping[str, Any]], request: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        existing = self._existing(records, request)
        if existing is not None:
            return existing
        if not records:
            raise JournalConflict("NOT_CONNECTED", "私人组合尚未初始化，无法对账")
        revision = self._require_revision(records, request)
        replayed = self._replay(records)
        assert replayed is not None
        if replayed.pending is not None:
            raise JournalConflict("PENDING_DRAFT_EXISTS", "存在未确认的成交草稿，请先确认")
        if replayed.state.version == 0:
            raise JournalConflict("NO_CONFIRMABLE_DRAFT", "至少需要一笔已确认成交才能生成对账快照")
        confirmed_records = [record for record in records if record["kind"] == "FILL_CONFIRMED"]
        evidence = dict(confirmed_records[-1]["body"]["evidence_ref"])
        reconciled_at = _aware_datetime(request.get("reconciled_at"), "reconciled_at")
        try:
            snapshot = portfolio_snapshot(
                replayed.state,
                snapshot_id=f"private-snapshot-{revision + 1}",
                available_at=reconciled_at,
                evidence_ref=evidence,
            )
        except ValueError as error:
            raise JournalValidationError(str(error)) from error
        snapshot_payload = snapshot.as_policy()
        body = {
            "snapshot": snapshot_payload,
            "confirmation": {
                "note": _text(request.get("confirmation_note"), "confirmation_note"),
                "reconciled_at": reconciled_at.isoformat(),
            },
            "evidence_ref": evidence,
            "confirmed_fill_count": replayed.state.version,
        }
        payload = {
            "action": "no_order",
            "status": "RECONCILED",
            "revision": revision + 1,
            "snapshot": snapshot_payload,
            "portfolio": {
                "status": "CONNECTED",
                "cash_cny": str(replayed.state.cash_cny),
                "realized_pnl_cny": str(replayed.state.realized_pnl_cny),
            },
        }
        record = self.journal.append(
            kind="RECONCILED_CONFIRMED",
            body=body,
            response=payload,
            idempotency_key=_idempotency_key(request),
            request_sha256=request_digest(request),
            recorded_at=datetime.now().astimezone(),
            changes_holdings=False,
        )
        return dict(record["response"]), str(record["record_sha256"])
    def cancel_fill(self, request: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        """Append an audit record that voids the pending draft; nothing is deleted."""
        with self.journal.transaction() as records:
            return self._cancel_fill(records, request)

    def _cancel_fill(
        self, records: Sequence[Mapping[str, Any]], request: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        existing = self._existing(records, request)
        if existing is not None:
            return existing
        if not records:
            raise JournalConflict("NOT_CONNECTED", "私人组合尚未初始化，无法作废成交草稿")
        revision = self._require_revision(records, request)
        replayed = self._replay(records)
        assert replayed is not None
        if replayed.pending is None:
            raise JournalConflict("NO_CONFIRMABLE_DRAFT", "没有待作废的成交草稿")
        prepared_digest = _text(request.get("prepared_record_sha256"), "prepared_record_sha256")
        if prepared_digest != replayed.pending["prepared_record_sha256"]:
            raise JournalConflict("NO_CONFIRMABLE_DRAFT", "草稿摘要与当前待确认成交不一致")
        cancelled_at = _aware_datetime(request.get("cancelled_at"), "cancelled_at")
        body = {
            "prepared_record_sha256": prepared_digest,
            "cancellation": {
                "reason": _text(request.get("reason"), "reason"),
                "cancelled_at": cancelled_at.isoformat(),
            },
            "voided_fill": json.loads(canonical_bytes(dict(replayed.pending["fill"]))),
        }
        payload = {
            "action": "no_order",
            "status": "FILL_CANCELLED",
            "revision": revision + 1,
            "cancelled_transaction_id": str(replayed.pending["fill"]["transaction_id"]),
        }
        record = self.journal.append(
            kind="FILL_CANCELLED",
            body=body,
            response=payload,
            idempotency_key=_idempotency_key(request),
            request_sha256=request_digest(request),
            recorded_at=datetime.now().astimezone(),
            changes_holdings=False,
        )
        return dict(record["response"]), str(record["record_sha256"])



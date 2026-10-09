"""D5 synthetic-only contracts; no sentiment model or strategy is implemented."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .sleeves import PortfolioSleeve, SharedSleeveBudget


SIGNAL_STATES = frozenset({
    "NO_THEME", "WATCH", "ENTRY_REVIEW", "HOLD_REVIEW", "REDUCE_REVIEW",
    "EXIT_REVIEW", "NOT_PROVEN", "INSUFFICIENT_EVIDENCE", "SHADOW_REQUIRED",
})


@dataclass(frozen=True)
class SentimentFeatureSnapshot:
    as_of: date
    available_at: datetime
    sector_relative_strength: Decimal | None
    market_breadth: Decimal | None
    turnover_change: Decimal | None
    volume_price_confirmation: Decimal | None
    theme_persistence: Decimal | None
    crowding: Decimal | None
    event_confirmation: Decimal | None
    market_regime: str
    evidence_refs: tuple[str, ...]
    scope: str = "SYNTHETIC_CONTRACT_ONLY"

    def __post_init__(self) -> None:
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ValueError("Sentiment features require a timezone-aware availability")
        if self.available_at.astimezone(ZoneInfo("Asia/Shanghai")).date() < self.as_of:
            raise ValueError("Sentiment features cannot be available before their as-of date")
        for name in (
            "sector_relative_strength", "market_breadth", "turnover_change",
            "volume_price_confirmation", "theme_persistence", "crowding",
            "event_confirmation",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                raise ValueError(f"{name} must be a finite Decimal or absent")
        if not self.market_regime.strip() or not self.evidence_refs:
            raise ValueError("Sentiment features require regime and traceable evidence")
        if self.scope != "SYNTHETIC_CONTRACT_ONLY":
            raise ValueError("D5 production sentiment inputs are not implemented")


@dataclass(frozen=True)
class SentimentSignal:
    symbol: str
    status: str
    features: SentimentFeatureSnapshot
    issuer_identity_passed: bool
    financial_sanity_passed: bool
    value_risk_floor_passed: bool
    liquidity_passed: bool
    event_risk_reviewed: bool
    action: str = "no_order"

    def __post_init__(self) -> None:
        if len(self.symbol) != 6 or not self.symbol.isdigit():
            raise ValueError("Sentiment signal requires a six-digit security code")
        if self.status not in SIGNAL_STATES:
            raise ValueError("Unknown sentiment signal state")
        if self.status == "ENTRY_REVIEW" and not all((
            self.issuer_identity_passed, self.financial_sanity_passed,
            self.value_risk_floor_passed, self.liquidity_passed,
            self.event_risk_reviewed,
        )):
            raise ValueError("Tactical entry review cannot bypass basic value and risk gates")
        if self.action != "no_order":
            raise ValueError("Sentiment signal is never an order")


@dataclass(frozen=True)
class TacticalRiskPolicy:
    budget: SharedSleeveBudget
    liquidity_floor: Decimal
    max_holding_days: int
    scope: str = "SYNTHETIC_POLICY_ONLY"

    def __post_init__(self) -> None:
        if self.budget.policy_scope != "SYNTHETIC_POLICY_ONLY" or self.scope != "SYNTHETIC_POLICY_ONLY":
            raise ValueError("D5 real tactical policy is not admitted")
        if not isinstance(self.liquidity_floor, Decimal) or not self.liquidity_floor.is_finite() or self.liquidity_floor < 0:
            raise ValueError("Tactical liquidity floor must be finite and nonnegative")
        if self.max_holding_days < 1:
            raise ValueError("Tactical holding horizon must be positive")


@dataclass(frozen=True)
class SwingTradePlan:
    signal: SentimentSignal
    policy: TacticalRiskPolicy
    entry_trigger: str
    stop_rule: str
    profit_take_rule: str
    time_exit: str
    slippage_model: str
    failure_conditions: tuple[str, ...]
    sleeve: PortfolioSleeve = PortfolioSleeve.TACTICAL_HOTSPOT
    action: str = "no_order"

    def __post_init__(self) -> None:
        if self.sleeve != PortfolioSleeve.TACTICAL_HOTSPOT:
            raise ValueError("Swing plan must remain in the tactical sleeve")
        if self.signal.status != "ENTRY_REVIEW":
            raise ValueError("Swing plan requires a synthetic entry-review signal")
        if not all((self.entry_trigger.strip(), self.stop_rule.strip(),
                    self.profit_take_rule.strip(), self.time_exit.strip(),
                    self.slippage_model.strip(), self.failure_conditions)):
            raise ValueError("Swing plan requires explicit entry, exit, cost and failure rules")
        if self.action != "no_order":
            raise ValueError("Swing plan cannot place an order")


__all__ = [
    "SentimentFeatureSnapshot", "SentimentSignal", "SwingTradePlan",
    "TacticalRiskPolicy", "SIGNAL_STATES",
]

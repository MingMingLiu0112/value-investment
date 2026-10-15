"""Private risk UX orchestration; existing journal and engine remain authoritative."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .private_portfolio_service import (
    PrivatePortfolioService, JournalConflict, JournalValidationError,
    _aware_datetime, _text, _idempotency_key, request_digest,
)
from .private_risk_projection import review_private_risk_rehearsal
from .security_attributes import load_verified_security_attributes

COST_FIELDS = (
    "buy_fee_fraction", "sell_fee_fraction", "minimum_buy_fee_cny", "minimum_sell_fee_cny",
)


class PrivateRiskExperienceService(PrivatePortfolioService):
    """Routes must apply the existing private authentication/CSRF boundary."""

    def confirm_costs(self, request, *, now: datetime):
        if now.utcoffset() is None:
            raise JournalValidationError("服务时间必须包含时区")
        if set(request) - {"idempotency_key", "expected_revision", "acknowledged", "costs",
                           "confirmed_at", "valid_until", "confirmation_note"}:
            raise JournalValidationError("成本确认包含不支持的字段")
        with self.journal.transaction() as records:
            existing = self._existing(records, request)
            if existing is not None:
                return existing
            revision = self._require_revision(records, request)
            replayed = self._replay(records)
            if replayed is None:
                raise JournalConflict("NOT_CONNECTED", "请先建立私人组合")
            if request.get("acknowledged") is not True:
                raise JournalValidationError("请本人明确确认成本假设")
            costs = request.get("costs")
            if not isinstance(costs, dict) or set(costs) != set(COST_FIELDS):
                raise JournalValidationError("请填写四项成本，不接受滑点、压力或交易规则作为可复用成本")
            normalized = {}
            for key in COST_FIELDS:
                value = costs[key]
                try:
                    amount = Decimal(str(value))
                except (InvalidOperation, ValueError) as error:
                    raise JournalValidationError("成本必须是明确的非负数字") from error
                if isinstance(value, bool) or not amount.is_finite() or amount < 0:
                    raise JournalValidationError("成本必须是明确的非负数字")
                if key.endswith("fraction") and amount > 1:
                    raise JournalValidationError("费用比率必须在 0 到 1 之间")
                normalized[key] = str(amount)
            confirmed = _aware_datetime(request.get("confirmed_at"), "confirmed_at")
            expires = _aware_datetime(request.get("valid_until"), "valid_until")
            baseline = replayed.state.confirmed_at or replayed.state.baseline.available_at
            if not baseline <= confirmed <= now < expires:
                raise JournalValidationError("确认时间不得早于账本或晚于当前时间，有效期必须在未来")
            body = {
                "account_scope": replayed.state.baseline.account_scope,
                "costs": normalized, "confirmed_at": confirmed.isoformat(),
                "valid_until": expires.isoformat(),
                "confirmation_note": _text(request.get("confirmation_note"), "confirmation_note"),
            }
            response = {"action": "no_order", "status": "COST_ASSUMPTIONS_CONFIRMED",
                "revision": revision + 1, "cost_profile": body, "changes_holdings": False}
            record = self.journal.append(kind="COST_ASSUMPTIONS_CONFIRMED", body=body,
                response=response, idempotency_key=_idempotency_key(request),
                request_sha256=request_digest(request), recorded_at=now, changes_holdings=False)
            return dict(record["response"]), record["record_sha256"]

    def context(self, *, symbol, repository_root, now: datetime):
        if now.utcoffset() is None:
            raise JournalValidationError("服务时间必须包含时区")
        if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isdigit():
            raise JournalValidationError("请填写六位证券代码")
        with self.journal.transaction() as records:
            replayed = self._replay(records)
            profile = None
            policy = None
            if replayed:
                for record in records:
                    if record["kind"] == "COST_ASSUMPTIONS_CONFIRMED":
                        body = record["body"]
                        # The latest confirmation supersedes older profiles even if expired.
                        profile = None
                        if (body["account_scope"] == replayed.state.baseline.account_scope
                                and _aware_datetime(body["confirmed_at"], "confirmed_at") <= now
                                < _aware_datetime(body["valid_until"], "valid_until")):
                            profile = {**body, "record_sha256": record["record_sha256"]}
                stored = replayed.policy
                if (stored.get("_confirmed_at") and stored.get("effective_date")
                        and stored["effective_date"] <= now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                        and _aware_datetime(stored["_confirmed_at"], "confirmed_at") <= now):
                    policy = stored
            attributes = load_verified_security_attributes(repository_root, {symbol}, now=now)
            return {"action": "no_order", "symbol": symbol, "revision": len(records),
                "policy": policy, "cost_profile": profile, "security_attributes": attributes,
                # No admitted lot-size rule exists in the current attribute chain.
                "verified_rules": {}, "rule_gaps": ["交易单位尚无已核验规则，请明确填写试算假设"]}

    def confirm_reconciliation(self, request):
        """Require granular human acknowledgement, then delegate atomic replay/append."""
        if any(request.get(key) is not True for key in
               ("cash_checked", "positions_checked", "fills_checked")):
            raise JournalValidationError("请逐项核对现金、持仓成本与成交记录")
        return self.reconcile(request)


def risk_facts_and_gaps(journal, *, repository_root, now):
    """Do not recompute or erase partial facts when the engine blocks sizing."""
    return review_private_risk_rehearsal(journal, repository_root=repository_root, generated_at=now)

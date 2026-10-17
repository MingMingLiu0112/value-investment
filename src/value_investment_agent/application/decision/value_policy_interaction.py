"""Local user policy review; never publishes or changes research admission."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from . import value_price_policy as policy_contract
from .value_action_plan import replay_published_value_decision
from ..portfolio.private_journal_lock import InterProcessLock
from ..product.publication_chain import bound_object
from ...domain.decision.value_price_policy import draft_value_price_policy, payload_hash, policy_basis
from ...domain.decision.value_action_plan import (
    RegisteredValueActionPolicy, ValuePriceRule, build_value_action_plan,
)

PERMISSION = "value_policy:confirm"


class PolicyAccessDenied(PermissionError):
    pass


class PolicyConflict(ValueError):
    pass


@dataclass(frozen=True)
class PolicyPrincipal:
    actor_id: str
    permissions: frozenset[str]


def require_policy_authority(principal):
    if (not isinstance(principal, PolicyPrincipal) or not isinstance(principal.actor_id, str)
            or not principal.actor_id.strip()
            or PERMISSION not in principal.permissions):
        raise PolicyAccessDenied("当前身份没有价格政策确认权限")


class ValuePolicyInteractionService:
    """Explicitly configured append-only local store, outside publication chains.

    Root supplies an authenticated principal, never request JSON. Isolated mode
    is constructor-only and permanently marks every record and returned plan.
    """

    def __init__(self, root, *, storage_relative, isolated=False):
        self.root = Path(root).resolve()
        relative = Path(storage_relative)
        self.store = (self.root / relative).resolve()
        allowed = self.root / (".tmp" if isolated else "runtime") / "value-policy-review"
        if (relative.is_absolute() or ".." in relative.parts
                or not self.store.is_relative_to(self.root)
                or not self.store.is_relative_to(allowed.resolve())
                or self.store == allowed.resolve()):
            raise ValueError("Use a dedicated value-policy-review subdirectory")
        self.scope = "ISOLATED_TEST" if isolated else "LOCAL_USER_POLICY"
        self.lock = InterProcessLock(self.store / ".lock")

    def _put(self, payload):
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        path = self.store / (digest + ".json")
        self.store.mkdir(parents=True, exist_ok=True)
        staging = self.store / (".staging-" + uuid4().hex)
        try:
            with staging.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(staging, path)
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise PolicyConflict("不可变记录完整性校验失败")
        finally:
            staging.unlink(missing_ok=True)
        return dict(path=path.relative_to(self.root).as_posix(), sha256=digest)

    def _read(self, digest):
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("无效预览标识")
        path = (self.store / (digest + ".json")).resolve()
        if not path.is_relative_to(self.store):
            raise ValueError("Policy record outside dedicated store")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise PolicyConflict("不可变政策记录已变化")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Policy record must be object")
        return result

    def _confirmation_loader(self, root, binding):
        if (Path(root).resolve() != self.root or not isinstance(binding, dict)
                or set(binding) != {"path", "sha256"}):
            raise ValueError("Invalid local confirmation binding")
        expected = (self.store / (binding["sha256"] + ".json")).relative_to(self.root).as_posix()
        if binding["path"] != expected:
            raise ValueError("Confirmation outside dedicated policy store")
        return self._read(binding["sha256"])

    @staticmethod
    def _clock(now):
        if now.utcoffset() is None:
            raise ValueError("Policy clock requires timezone")

    @staticmethod
    def _registered_selection(prepared):
        return dict(draft=deepcopy(prepared["draft"]),
            draft_prices=deepcopy(prepared["draft_prices"]),
            price_scope="PRIVATE_POLICY_ARITHMETIC_NOT_ADMITTED")

    def review_handoff(self, symbol, *, principal, now):
        require_policy_authority(principal)
        self._clock(now)
        from ..product.research_review_wizard import build_external_review_handoff
        return build_external_review_handoff(root=self.root, symbol=symbol, now=now)

    def preview(self, symbol, selection, *, principal, now):
        require_policy_authority(principal)
        self._clock(now)
        expected = {"effective_from", "effective_through", "rationale",
                    "dividend_coverage_risk", "rules"}
        if not isinstance(selection, dict) or set(selection) != expected:
            raise ValueError("请明确填写有效期、理由、分红风险及动作规则")
        if not isinstance(selection["rules"], list) or len(selection["rules"]) > 4:
            raise ValueError("最多四条动作规则")
        for row in selection["rules"]:
            if (not isinstance(row, dict) or set(row) != {
                    "action", "scenario", "value_fraction", "comparison", "rationale"}
                    or not all(isinstance(v, str) and v.strip() for v in row.values())):
                raise ValueError("每个动作须明确选择情景、比例、比较条件与复核理由")
        review = policy_contract.load_value_policy_review(self.root, symbol, now)
        template = review["draft"]
        identity = uuid4().hex
        draft = draft_value_price_policy(
            {**template["basis"], "action": "no_order", "source_bindings": template["source_bindings"]},
            draft_id="user-draft-" + identity, policy_id="user-policy-" + identity,
            rule_version="user-policy-v1", profile_id=template["profile_id"],
            effective_from=date.fromisoformat(selection["effective_from"]),
            effective_through=date.fromisoformat(selection["effective_through"]),
            rationale=selection["rationale"], dividend_coverage_risk=selection["dividend_coverage_risk"],
            rules=selection["rules"], thesis_reviews=template.get("thesis_reviews", []))
        prepared = policy_contract.prepare_value_price_policy(self.root, draft, now=now)
        envelope = dict(schema_version="value-policy-user-preview-v1", actor_id=principal.actor_id,
            scope=self.scope, prepared=prepared, review_bindings=review["source_bindings"],
            expires_at=(now + timedelta(minutes=30)).isoformat(), action="no_order")
        binding = self._put(envelope)
        return dict(action="no_order", status=prepared["status"], scope=self.scope,
            preview_id=binding["sha256"], expires_at=envelope["expires_at"],
            preparation=prepared, formal_eligibility=False, portfolio_eligibility=None,
            position_guidance=None)

    def confirm(self, preview_id, confirmation, *, principal, now):
        require_policy_authority(principal)
        self._clock(now)
        if (not isinstance(confirmation, dict) or set(confirmation) != {"acknowledged", "note"}
                or confirmation["acknowledged"] is not True
                or not isinstance(confirmation["note"], str) or not confirmation["note"].strip()):
            raise ValueError("请本人勾选确认并填写确认意见")
        with self.lock:
            envelope = self._read(preview_id)
            if envelope.get("actor_id") != principal.actor_id or envelope.get("scope") != self.scope:
                raise PolicyAccessDenied("只能确认本人在当前环境中预览的政策")
            # A deterministic commit marker makes retries/restarts idempotent.
            marker_key = payload_hash(dict(preview_id=preview_id, role="confirmation"))
            marker = self.store / ("confirmed-" + marker_key + ".json")
            if marker.exists():
                binding = json.loads(marker.read_bytes())
                result = self._read(binding["sha256"])
                if (result.get("preview_id") != preview_id or result.get("scope") != self.scope
                        or result.get("actor_id") != principal.actor_id):
                    raise PolicyConflict("登记关联校验失败")
                if result["confirmation"] != confirmation:
                    raise PolicyConflict("该预览已登记不同确认意见，请重新预览")
                return {**result, "registered_policy": self._registered_selection(envelope["prepared"])}
            if now > datetime.fromisoformat(envelope["expires_at"]):
                raise PolicyConflict("预览已过期，请重新预览")
            prepared = envelope["prepared"]
            if now < datetime.fromisoformat(prepared["prepared_at"]):
                raise PolicyConflict("确认不能早于预览")
            current = policy_contract.load_value_policy_review(self.root, prepared["draft"]["basis"]["symbol"], now)
            if current["source_bindings"] != envelope["review_bindings"]:
                raise PolicyConflict("复核材料已变化，请重新预览")
            receipt = dict(schema_version="value-price-policy-user-confirmation-v1",
                action="no_order", decision="CONFIRM", actor=principal.actor_id,
                scope=self.scope, draft_sha256=prepared["draft_sha256"],
                prepared_sha256=prepared["prepared_sha256"], confirmed_at=now.isoformat(),
                note=confirmation["note"])
            receipt_binding = self._put(receipt)
            registry = policy_contract.confirm_value_price_policy(self.root, prepared,
                confirmation_binding=receipt_binding,
                authorize_confirmation=lambda r: r == receipt, now=now,
                confirmation_loader=self._confirmation_loader)
            registry["scope"] = self.scope
            registry_binding = self._put(registry)
            plan = self._conditional_plan(prepared, registry, registry_binding, now)
            result = dict(schema_version="value-policy-user-registration-v1",
                confirmed_at=now.isoformat(), action="no_order", status="REGISTERED", scope=self.scope,
                actor_id=principal.actor_id, preview_id=preview_id, confirmation=deepcopy(confirmation),
                registered_policy=self._registered_selection(prepared),
                registry_binding=registry_binding, receipt_binding=receipt_binding,
                conditional_plan=plan, formal_eligibility=False, portfolio_eligibility=None,
                position_guidance=None, production_published=False, research_approval_changed=False)
            result_binding = self._put(result)
            staging = self.store / (".commit-" + uuid4().hex)
            try:
                with staging.open("xb") as stream:
                    stream.write(json.dumps(result_binding).encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(staging, marker)
            finally:
                staging.unlink(missing_ok=True)
            return result

    def status(self, symbol, *, principal, now):
        """Read only this actor's latest registration, revalidating live evidence.

        An obsolete latest policy never silently falls back to an older policy.
        Persisted plans are historical; current plans are always reprojected.
        """
        require_policy_authority(principal)
        self._clock(now)
        if not isinstance(symbol, str) or re.fullmatch(r"[0-9]{6}", symbol) is None:
            raise ValueError("Invalid policy security")
        candidates = []
        for path in self.store.glob("confirmed-*.json"):
            binding = json.loads(path.read_bytes())
            result = self._read(binding["sha256"])
            if (result.get("schema_version") != "value-policy-user-registration-v1"
                    or result.get("actor_id") != principal.actor_id or result.get("scope") != self.scope):
                continue
            envelope = self._read(result["preview_id"])
            if envelope["prepared"]["draft"]["basis"]["symbol"] == symbol:
                candidates.append(result)
        if not candidates:
            return dict(action="no_order", status="NOT_REGISTERED", scope=self.scope,
                        conditional_plan=None, formal_eligibility=False, portfolio_eligibility=None)
        latest = max(candidates, key=lambda r: (datetime.fromisoformat(r["confirmed_at"]), r["preview_id"]))
        envelope = self._read(latest["preview_id"])
        prepared = envelope["prepared"]
        try:
            if envelope["actor_id"] != principal.actor_id or envelope["scope"] != self.scope:
                raise PolicyConflict("登记人或环境不一致")
            if datetime.fromisoformat(latest["confirmed_at"]) > now:
                raise PolicyConflict("登记晚于当前查询时点")
            current = policy_contract.load_value_policy_review(self.root, symbol, now)
            if current["source_bindings"] != envelope["review_bindings"]:
                raise PolicyConflict("复核材料已更新")
            fresh = policy_contract.prepare_value_price_policy(self.root, prepared["draft"], now=now)
            if fresh["blockers"]:
                raise PolicyConflict("研究依据变化或政策已过期")
            registry = self._confirmation_loader(self.root, latest["registry_binding"])
            receipt = self._confirmation_loader(self.root, latest["receipt_binding"])
            if (receipt["actor"] != principal.actor_id or receipt["scope"] != self.scope
                    or receipt["prepared_sha256"] != prepared["prepared_sha256"]):
                raise PolicyConflict("登记回执关联校验失败")
            plan = self._conditional_plan(prepared, registry, latest["registry_binding"], now)
        except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
            return dict(action="no_order", status="REVIEW_REQUIRED", scope=self.scope,
                preview_id=latest["preview_id"], confirmed_at=latest["confirmed_at"],
                detail="已登记政策的依据、有效期或行情需要重新复核，请重新预览",
                conditional_plan=None, formal_eligibility=False, portfolio_eligibility=None)
        return {**latest, "registered_policy": self._registered_selection(prepared), "conditional_plan": plan}

    def _conditional_plan(self, prepared, registry, binding, now):
        draft = prepared["draft"]
        current = policy_contract._current_plan(self.root, draft["basis"]["symbol"], now)
        if policy_basis(current) != draft["basis"]:
            raise PolicyConflict("计划研究依据已变化，请重新预览")
        matches = [b for b in current["source_bindings"]
                   if b["path"].endswith("-value-decision-explanation.json")]
        if len(matches) != 1:
            raise PolicyConflict("缺少唯一的绑定研究说明，不能生成条件性计划")
        explanation = bound_object(self.root, matches[0])
        restored, _ = replay_published_value_decision(self.root, explanation, now=now)
        # Use the already verified current plan's model identity and quote.
        explanation = {**explanation, "model_id": current["model_id"]}
        row = registry["policies"][0]
        policy = RegisteredValueActionPolicy(
            policy_id=row["policy_id"], rule_version=row["rule_version"], symbol=row["symbol"],
            profile_id=row["profile_id"], model_id=row["model_id"], model_version=row["model_version"],
            effective_from=date.fromisoformat(row["effective_from"]),
            effective_through=date.fromisoformat(row["effective_through"]),
            registered_at=datetime.fromisoformat(row["registered_at"]), source_binding=binding,
            rules=tuple(ValuePriceRule(**{**r, "value_fraction": Decimal(r["value_fraction"])}) for r in row["rules"]))
        quote = {}
        if current.get("reference_close") is not None:
            quote = dict(symbol=row["symbol"], price=current["reference_close"],
                quote_date=current["market_trade_date"],
                status="verified_close" if current.get("current_quote_verified") is True else "not_current_verified",
                comparison_eligible=current.get("price_comparison_eligible") is True)
        plan = build_value_action_plan(explanation=explanation, policy=policy, reference_quote=quote,
            repository_replayed=restored is not None,
            verified_predecision=(None if restored is None else restored.dependency_objects.get("pre_decision")),
            source_bindings=tuple([*current["source_bindings"], binding]),
            decision_as_of=now.astimezone(policy_contract.CHINA).date()).as_policy()
        plan.update(scope=self.scope, research_approval_changed=False, production_published=False)
        return plan

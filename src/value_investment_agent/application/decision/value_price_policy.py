"""Read-only policy preparation and externally authorized registration payloads."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from ...domain.decision.value_action_plan import RegisteredValueActionPolicy
from ...domain.decision.value_price_policy import (
    PREPARED_SCHEMA, payload_hash, policy_basis, preview_draft_prices, validate_draft,
)
from ..product.publication_chain import bound_object
from .value_action_plan import load_registered_value_action_plans

CHINA = ZoneInfo("Asia/Shanghai")
REVIEW_MANIFEST_PATH = "artifacts/current/tl11-p5-20261014/value-policy-review-manifest.json"


def _current_plan(root, symbol, now):
    if now.utcoffset() is None:
        raise ValueError("Policy clock requires timezone")
    result = load_registered_value_action_plans(root, now=now, symbols=[symbol])
    matches = [p for p in result["items"] if p["symbol"] == symbol]
    if result["blockers"] or len(matches) != 1:
        raise ValueError("Current bound value research unavailable")
    return matches[0]


def _verify_sources(root, draft):
    if not draft.get("source_bindings"):
        raise ValueError("Policy draft requires bound public research")
    root = Path(root).resolve()
    for binding in draft["source_bindings"]:
        path = (root / binding["path"]).resolve()
        if Path(binding["path"]).is_absolute() or not path.is_relative_to(root):
            raise ValueError("Policy source must stay under repository")
        if hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError("Policy source hash mismatch")


def prepare_value_price_policy(root, draft, *, now):
    """Bind exact current economics without approving G3, IPS or action prices.

    Missing model identity or selected thresholds blocks preparation. Existing
    research gates are reported separately: policy confirmation never clears them.
    """
    validate_draft(draft)
    _verify_sources(root, draft)
    plan = _current_plan(root, draft["basis"]["symbol"], now)
    blockers = []
    if policy_basis(plan) != draft["basis"]:
        blockers.append("VALUE_POLICY_RESEARCH_BASIS_CHANGED")
    if not draft["basis"].get("model_id"):
        blockers.append("VALUE_POLICY_MODEL_IDENTITY_MISSING")
    if plan.get("profile_id") != draft["profile_id"]:
        blockers.append("VALUE_POLICY_PROFILE_NOT_APPLICABLE")
    for field in ("model_version", "valuation_input_version", "research_version"):
        if not draft["basis"].get(field):
            blockers.append("VALUE_POLICY_BASIS_MISSING:" + field)
    if not draft["rules"]:
        blockers.append("VALUE_POLICY_EXPLICIT_ACTION_RULES_REQUIRED")
    if any(draft["basis"].get(key) is None for key in ("bear", "base", "bull")):
        blockers.append("VALUE_POLICY_SCENARIOS_UNAVAILABLE")
    if date.fromisoformat(draft["effective_through"]) < now.astimezone(CHINA).date():
        blockers.append("VALUE_POLICY_EXPIRED")
    payload = dict(schema_version=PREPARED_SCHEMA,
        status="BLOCKED" if blockers else "PREPARED_PENDING_USER_CONFIRMATION",
        draft=deepcopy(draft), draft_sha256=payload_hash(draft),
        prepared_at=now.isoformat(), blockers=blockers,
        draft_prices=preview_draft_prices(draft), price_scope="UNAPPROVED_DRAFT_ARITHMETIC_ONLY",
        existing_research_blockers=deepcopy(plan.get("blockers", [])),
        formal_eligibility=False, portfolio_eligibility=None, registered=False, action="no_order")
    payload["prepared_sha256"] = payload_hash(payload)
    return payload


def confirm_value_price_policy(root, prepared, *, confirmation_binding,
                               authorize_confirmation, now, confirmation_loader=bound_object):
    """Return a registry candidate only after Root verifies real user authority.

    authorize_confirmation is a trusted application dependency, never a request
    field or boolean supplied by the researcher. It receives the hash-bound
    receipt and must verify authenticated user authority. Root owns immutable
    publication and registry pointer writing. This function does not sign receipts.
    confirmation_loader is a trusted storage adapter; the default remains the
    public runtime binding reader. Never accept a reader from request fields.
    """
    if prepared.get("schema_version") != PREPARED_SCHEMA or prepared.get("status") != "PREPARED_PENDING_USER_CONFIRMATION":
        raise ValueError("Policy not prepared for confirmation")
    sealed = {k: v for k, v in prepared.items() if k != "prepared_sha256"}
    if payload_hash(sealed) != prepared.get("prepared_sha256"):
        raise ValueError("Prepared policy changed")
    draft = prepared["draft"]
    if payload_hash(draft) != prepared["draft_sha256"]:
        raise ValueError("Draft changed after preparation")
    fresh = prepare_value_price_policy(root, draft, now=now)
    if fresh["blockers"]:
        raise ValueError("Policy basis no longer confirmable")
    receipt = confirmation_loader(Path(root).resolve(), confirmation_binding)
    if (receipt.get("schema_version") != "value-price-policy-user-confirmation-v1"
            or receipt.get("action") != "no_order"
            or receipt.get("decision") != "CONFIRM"
            or receipt.get("draft_sha256") != prepared["draft_sha256"]
            or receipt.get("prepared_sha256") != prepared["prepared_sha256"]):
        raise ValueError("User receipt must bind exact draft and preparation")
    confirmed_at = datetime.fromisoformat(receipt["confirmed_at"])
    if (confirmed_at.utcoffset() is None or confirmed_at > now
            or confirmed_at < datetime.fromisoformat(prepared["prepared_at"])):
        raise ValueError("Confirmation time invalid")
    if not callable(authorize_confirmation) or authorize_confirmation(deepcopy(receipt)) is not True:
        raise ValueError("Authenticated authorized user confirmation required")
    rules = validate_draft(draft)
    RegisteredValueActionPolicy(policy_id=draft["policy_id"], rule_version=draft["rule_version"],
        symbol=draft["basis"]["symbol"], profile_id=draft["profile_id"],
        model_id=draft["basis"]["model_id"], model_version=draft["basis"]["model_version"],
        effective_from=date.fromisoformat(draft["effective_from"]),
        effective_through=date.fromisoformat(draft["effective_through"]),
        registered_at=confirmed_at, rules=rules, source_binding=confirmation_binding)
    row = {key: deepcopy(draft[key]) for key in (
        "policy_id", "rule_version", "profile_id", "effective_from", "effective_through",
        "rules", "currency", "share_basis", "rationale", "dividend_coverage_risk", "thesis_reviews")}
    row.update(symbol=draft["basis"]["symbol"], model_id=draft["basis"]["model_id"],
        model_version=draft["basis"]["model_version"], registered_at=confirmed_at.isoformat(),
        research_basis=deepcopy(draft["basis"]), confirmation_binding=deepcopy(confirmation_binding))
    return dict(schema_version="registered-value-action-policies-v1", status="REGISTERED",
        policies=[row], action="no_order")


def load_value_policy_review(root, symbol, now):
    """Read only public, hash-bound review material; raise ValueError fail closed.

    Root owns API error mapping and publication identity. The returned bindings
    include the manifest itself; no preparation, confirmation or registration
    occurs while reading. A saved blocked preparation remains blocked.
    """
    root = Path(root).resolve()
    if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("Review requires a six-digit security")
    if now.utcoffset() is None:
        raise ValueError("Review clock requires timezone")
    manifest_path = root / REVIEW_MANIFEST_PATH
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
        if (manifest.get("schema_version") != "value-policy-review-manifest-v1"
                or manifest.get("action") != "no_order"):
            raise ValueError("Invalid public review manifest")
        bindings = manifest["items"][symbol]
        if set(bindings) != {"model_review", "draft", "preparation"}:
            raise ValueError("Incomplete public review bindings")
        artifacts = {}
        for role, binding in bindings.items():
            if (not isinstance(binding, dict) or set(binding) != {"path", "sha256"}
                    or not isinstance(binding["path"], str)
                    or not isinstance(binding["sha256"], str)
                    or re.fullmatch(r"[0-9a-f]{64}", binding["sha256"]) is None):
                raise ValueError("Invalid public artifact binding")
            target = (root / binding["path"]).resolve()
            if (Path(binding["path"]).is_absolute() or ".." in Path(binding["path"]).parts
                    or target.parent != manifest_path.parent.resolve()
                    or not target.name.startswith("value-") or target.suffix != ".json"):
                raise ValueError("Review binding outside public artifact scope")
            content = target.read_bytes()
            if hashlib.sha256(content).hexdigest() != binding["sha256"]:
                raise ValueError("Public review artifact hash mismatch")
            artifacts[role] = json.loads(content)
            if not isinstance(artifacts[role], dict):
                raise ValueError("Public review artifact must be object")
        review, draft, prepared = (artifacts[k] for k in ("model_review", "draft", "preparation"))
        if (review.get("schema_version") != "tl11-p5-value-model-review-v1"
                or review.get("symbol") != symbol or review.get("action") != "no_order"
                or review.get("formal_eligibility") is not False
                or review.get("portfolio_eligibility") is not None):
            raise ValueError("Invalid unapproved model review")
        validate_draft(draft)
        if draft["basis"]["symbol"] != symbol:
            raise ValueError("Review draft issuer mismatch")
        if (prepared.get("schema_version") != PREPARED_SCHEMA
                or prepared.get("status") not in {"BLOCKED", "PREPARED_PENDING_USER_CONFIRMATION"}
                or prepared.get("draft") != draft
                or prepared.get("draft_sha256") != payload_hash(draft)
                or prepared.get("action") != "no_order" or prepared.get("registered") is not False
                or prepared.get("formal_eligibility") is not False
                or prepared.get("portfolio_eligibility") is not None):
            raise ValueError("Review preparation contract mismatch")
        if payload_hash({k: v for k, v in prepared.items() if k != "prepared_sha256"}) != prepared.get("prepared_sha256"):
            raise ValueError("Review preparation hash mismatch")
        if prepared.get("draft_prices") != preview_draft_prices(draft):
            raise ValueError("Review draft prices mismatch")
        for stamp in (review["reviewed_at"], prepared["prepared_at"]):
            moment = datetime.fromisoformat(stamp)
            if moment.utcoffset() is None or moment > now:
                raise ValueError("Review material not yet available")
        source_rows = [*draft["source_bindings"], *review["direct_hash_checks"]]
        for row in source_rows:
            path = row["path"]
            if (not path.startswith(("runtime/", "config/", "src/", "docs/", "artifacts/"))
                    or re.search(r"private|journal|secret|credential|\.tmp/|\.env", path, re.I)
                    or Path(path).suffix.lower() in {".xlsx", ".xls", ".db", ".sqlite", ".sql"}):
                raise ValueError("Review references non-public source")
        _verify_sources(root, draft)
        for check in review["direct_hash_checks"]:
            _verify_sources(root, {"source_bindings": [dict(path=check["path"], sha256=check["sha256"])]})
        basis = draft["basis"]
        for field in ("model_id", "model_type", "model_version", "valuation_input_version", "valuation_date"):
            if review.get(field) != basis.get(field):
                raise ValueError("Model review and draft basis mismatch")
        if review.get("scenarios") != {key: basis.get(key) for key in ("bear", "base", "bull")}:
            raise ValueError("Model review scenario mismatch")
        plan = _current_plan(root, symbol, now)
        if policy_basis(plan) != basis:
            raise ValueError("Current research changed since review")
        if review.get("model_identity_evidence") != plan.get("model_identity_evidence"):
            raise ValueError("Model catalog identity changed since review")
        artifacts["source_bindings"] = [dict(path=REVIEW_MANIFEST_PATH, sha256=hashlib.sha256(raw).hexdigest()),
                                         *bindings.values()]
        replay_info = review.get("isolated_replay")
        if replay_info:
            binding = replay_info["receipt_binding"]
            path = (root / binding["path"]).resolve()
            if path.parent != manifest_path.parent.resolve() or not path.name.startswith("value-"):
                raise ValueError("Replay receipt outside public review scope")
            _verify_sources(root, {"source_bindings": [binding]})
            receipt = json.loads(path.read_bytes())
            if (receipt.get("schema_version") != "value-direct-input-isolated-replay-v1"
                    or receipt.get("symbol") != symbol or receipt.get("action") != "no_order"
                    or receipt.get("expected_valuation_sha256") != basis["valuation_input_version"]
                    or receipt.get("replayed_valuation_sha256") != basis["valuation_input_version"]
                    or receipt.get("status") != "EXACT_VALUATION_REPLAY"
                    or receipt.get("full_payload_match") is not True):
                raise ValueError("Replay receipt does not prove current valuation arithmetic")
            artifacts["source_bindings"].append(binding)
        return deepcopy(artifacts)
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Public value policy review unavailable: " + str(error)) from error

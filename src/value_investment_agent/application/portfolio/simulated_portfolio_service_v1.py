"""Persistent manual hypotheses over the existing journal, never an actual account."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from .private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, SimulatedAccountContext, JournalValidationError,
)
from .personal_entry_thesis import resolve_personal_entry_thesis, _sources
from .private_risk_projection import _snapshot_payload, _policy_payload


def _safe_child(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise JournalValidationError("Relative project-local simulation path required")
    target = root
    for part in path.parts:
        target = target / part
        if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
            raise JournalValidationError("Simulation paths cannot traverse links")
    if not target.resolve().is_relative_to(root):
        raise JournalValidationError("Simulation path escaped project")
    return target


class SimulatedPortfolioServiceV1:
    """Construct via the server factory; requests never select namespace or storage."""

    def __init__(self, *, project, context, research_sources, clock):
        self._project = project
        self._context = context
        self._research_sources = deepcopy(research_sources)
        self._clock = clock
        self._path = _safe_child(project,
            Path("runtime/simulated-portfolios-v1") / context.account_id / "journal.jsonl")
        self._ledger = PrivatePortfolioService(PrivateJournal(self._path),
            account_context=context, clock=clock)
        self._check()

    def _check(self):
        if _safe_child(self._project, self._path.relative_to(self._project)) != self._path:
            raise JournalValidationError("Simulation storage changed")
        self._ledger.records()
        _safe_child(self._project, self._path.with_suffix(".jsonl.lock").relative_to(self._project))

    def _request(self, request):
        self._check()
        result = deepcopy(dict(request))
        if result.pop("confirmed_hypothetical", None) is not True:
            raise JournalValidationError("Explicit hypothetical confirmation required")
        forbidden = {"path", "root", "journal_path", "namespace", "account_id", "account_scope",
            "account_context", "repository_root", "risk_preview", "account_evidence"}
        if forbidden & result.keys():
            raise JournalValidationError("Client cannot select account storage or authority")
        return result

    def initialize(self, request):
        payload = self._request(request)
        payload["account_scope"] = self._context.account_scope
        return self._ledger.initialize(payload)

    def prepare_fill(self, request):
        return self._ledger.prepare_fill(self._request(request))

    def confirm_fill(self, request):
        return self._ledger.confirm_fill(self._request(request))

    def cancel_fill(self, request):
        return self._ledger.cancel_fill(self._request(request))

    def prepare_policy(self, request):
        return self._ledger.prepare_policy(self._request(request))

    def confirm_policy(self, request):
        return self._ledger.confirm_policy(self._request(request))

    def reconcile(self, request):
        return self._ledger.reconcile(self._request(request))

    def correct_confirmed_fill(self, request):
        self._check()
        raise JournalValidationError("CONFIRMED_FILL_CORRECTION_UNSUPPORTED")

    def _source(self, source_id, symbol):
        return self._verify_source(deepcopy(self._research_sources.get(source_id)), symbol)

    def _verify_source(self, ref, symbol):
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "available_at", "symbol"}:
            raise JournalValidationError("Server-bound research source required")
        if ref["symbol"] != symbol:
            raise JournalValidationError("Research source security mismatch")
        allowed = ("runtime/source-native-pending/", "runtime/hotspot-current-price-cases/",
            "runtime/swing-simulated-lifecycle/", "runtime/public-research/", "artifacts/current/")
        if not isinstance(ref["path"], str) or not ref["path"].startswith(allowed):
            raise JournalValidationError("Public retained research reference required")
        moment = datetime.fromisoformat(ref["available_at"])
        if moment.utcoffset() is None or moment > self._ledger._now():
            raise JournalValidationError("Research reference unavailable at confirmation")
        path = _safe_child(self._project, ref["path"])
        if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            raise JournalValidationError("Research reference missing or too large")
        if sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
            raise JournalValidationError("Research reference hash mismatch")
        return ref

    def confirm_entry_hypothesis(self, request):
        payload = self._request(request)
        source_id = payload.pop("source_id", None)
        narrative = payload.pop("narrative", None)
        allowed = {"idempotency_key", "expected_revision", "fill_record_sha256",
            "confirmation_note", "supersedes_record_sha256"}
        if set(payload) - allowed or not isinstance(narrative, dict) or set(narrative) != {
                "thesis", "hold_logic", "invalidation_conditions"}:
            raise JournalValidationError("Manual hypothesis fields required; approval is unsupported")
        records = self._ledger.records()
        matches = [r for r in records if r["record_sha256"] == payload.get("fill_record_sha256")
            and r["kind"] == "FILL_CONFIRMED"]
        if len(matches) != 1:
            raise JournalValidationError("Confirmed fill must belong to this simulated account")
        source = self._source(source_id, matches[0]["body"]["fill"]["symbol"])
        encoded = json.dumps(source, separators=(",", ":"), ensure_ascii=False)
        if len(encoded) > 500:
            raise JournalValidationError("Source binding exceeds existing narrative contract")
        payload.update(binding_mode="HISTORICAL_RECONSTRUCTION", read_and_confirmed=True,
            reconstruction=dict(narrative, research_version=encoded,
                strategy_version="SIMULATED_MANUAL_HYPOTHESIS_NOT_STRATEGY_APPROVAL"))
        return self._ledger.confirm_entry_thesis(payload,
            authenticated_subject=self._context.account_scope, repository_root=self._project)

    def read(self):
        self._check()
        records = self._ledger.records()
        replayed = self._ledger._replay(records)
        entries = []
        if records:
            resolved = resolve_personal_entry_thesis(records=records,
                account_scope=self._context.account_scope, expected_revision=len(records),
                as_of=self._ledger._now(), authenticated_subject=self._context.account_scope)
            for row in resolved["items"]:
                binding = row["current_binding"]
                if binding:
                    self._verify_source(json.loads(binding["reconstruction"]["research_version"]), row["symbol"])
                entries.append(dict(transaction_id=row["transaction_id"], symbol=row["symbol"],
                    sleeve=row["sleeve"], remaining_quantity=row["remaining_quantity"],
                    fill_record_sha256=row["fill_record_sha256"],
                    hypothesis=deepcopy(binding["reconstruction"]) if binding else None,
                    entry_confirmation_sha256=binding["record_sha256"] if binding else None,
                    original_pit_proven=False, advisory_eligible=False))
        snapshot = _snapshot_payload(replayed) if replayed else None
        snapshot_binding = (dict(account_context=deepcopy(records[0]["body"]["account_context"]),
            baseline_record_sha256=records[0]["record_sha256"],
            journal_tip_sha256=records[-1]["record_sha256"],
            snapshot_sha256=sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()) if records else None)
        return dict(schema_version=self._context.version, account_context=self._context.as_dict(),
            namespace="SIMULATED", account_id=self._context.account_id, action="no_order",
            status="CONNECTED" if replayed else "NOT_INITIALIZED", revision=len(records),
            journal_tip_sha256=records[-1]["record_sha256"] if records else None,
            portfolio=self._ledger._portfolio_payload(replayed) if replayed else None,
            risk_snapshot=snapshot, risk_snapshot_binding=snapshot_binding,
            policy=dict(_policy_payload(replayed), sensitivity="SIMULATED_EXPLICIT_HYPOTHESIS") if replayed else None,
            entries=entries, formal_eligibility=False, actual_account_used=False,
            ownership_verified=False, position_guidance=None,
            confirmed_fill_correction="UNSUPPORTED",
            source_scope="HASH_BOUND_REFERENCE_NOT_STRATEGY_OR_MARKET_PRICE_ADMISSION")

    def entry_consumption(self, *, sell_fill_sha256):
        """Reference the existing FIFO lineage; no second cash/lot calculation."""
        self._check()
        records = self._ledger.records()
        matches = [i for i, r in enumerate(records) if r["record_sha256"] == sell_fill_sha256
            and r["kind"] == "FILL_CONFIRMED" and r["body"]["fill"]["side"] == "SELL"]
        if len(matches) != 1:
            raise JournalValidationError("Confirmed sell must belong to this account")
        index = matches[0]
        before = _sources(records[:index])[0]
        after = _sources(records[:index + 1])[0]
        # Existing FIFO reconciliation has already validated every transition.
        consumed = []
        for digest, original in before.items():
            if original["remaining_quantity"] != after[digest]["remaining_quantity"]:
                consumed.append(digest)
        return dict(namespace="SIMULATED", action="no_order", sell_fill_sha256=sell_fill_sha256,
            consumed_entry_fill_sha256=consumed, before=before, after=after,
            formal_eligibility=False)


def create_simulated_portfolio_service(*, repository_root: Path, account_id: str,
        research_sources=None, clock=None) -> SimulatedPortfolioServiceV1:
    """Server factory: one fixed project-local root; no client path/namespace option."""
    project = Path(repository_root).resolve(strict=True)
    if not project.is_dir():
        raise JournalValidationError("Project directory required")
    return SimulatedPortfolioServiceV1(project=project, context=SimulatedAccountContext(account_id),
        research_sources=research_sources or {}, clock=clock)

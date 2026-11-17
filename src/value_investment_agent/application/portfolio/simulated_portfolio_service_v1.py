"""Persistent manual hypotheses over the existing journal, never an actual account."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from .private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, SimulatedAccountContext, JournalValidationError,
    JournalConflict, RECORD_KINDS, _fill_from_body, request_digest, simulated_context_from_records,
)
from .personal_entry_thesis import resolve_personal_entry_thesis, _sources
from .private_risk_projection import _snapshot_payload, _policy_payload
from ...domain.portfolio.dual_sleeve_records import canonical_bytes

CORRECTION_KIND = "SIMULATED_FILL_CORRECTED_V1"
CORRECTION_SCHEMA = "simulated-confirmed-fill-correction-v1"
CORRECTABLE_FIELDS = frozenset({"price_cny", "fees_cny", "quantity"})


class SimulatedCorrectionJournal(PrivateJournal):
    """Only the explicitly selected SIM adapter accepts this extra event kind."""

    _record_kinds = RECORD_KINDS | {CORRECTION_KIND}


def effective_simulated_records(records, *, cutoff=None):
    """In-memory interpretation, NEVER rewritten journal bytes or new fill identities.

    Original record hashes remain lineage identifiers, not hashes of these derived
    bodies. Validate the original hash chain before projecting any correction.
    """
    context = simulated_context_from_records(records)
    if context is None:
        raise JournalValidationError("Versioned SIM context required for corrections")
    effective = deepcopy(list(records))
    fills, versions, lineage = {}, {}, {}
    previous = None
    previous_at = None
    for index, record in enumerate(records):
        SimulatedCorrectionJournal._validate_record(record, line_number=index + 1, previous=previous)
        stamp = datetime.fromisoformat(record["recorded_at"])
        if (stamp.utcoffset() is None or (cutoff is not None and stamp > cutoff)
                or (previous_at is not None and stamp < previous_at)
                or record.get("sequence") != index + 1):
            raise JournalValidationError("Correction journal chronology/sequence invalid")
        previous, previous_at = record["record_sha256"], stamp
        if record["kind"] == "FILL_CONFIRMED":
            fills[record["record_sha256"]] = index
        if record["kind"] != CORRECTION_KIND:
            continue
        body = record["body"]
        expected_fields = {"schema_version", "account_context", "target_fill_record_sha256",
            "expected_original_version", "expected_revision", "changes", "confirmed_at", "reason",
            "confirmed_hypothetical"}
        if (set(body) != expected_fields or body["schema_version"] != CORRECTION_SCHEMA
                or body["account_context"] != context.as_dict()
                or body["confirmed_hypothetical"] is not True
                or type(body["expected_revision"]) is not int or body["expected_revision"] != index
                or not isinstance(body["reason"], str) or not body["reason"].strip()
                or record.get("changes_holdings") is not True):
            raise JournalValidationError("Invalid simulated correction contract")
        target = body["target_fill_record_sha256"]
        if target not in fills or body["expected_original_version"] != versions.get(target, target):
            raise JournalValidationError("Correction original fill/version mismatch")
        confirmed = datetime.fromisoformat(body["confirmed_at"])
        if (confirmed.utcoffset() is None or not datetime.fromisoformat(records[index-1]["recorded_at"])
                <= confirmed <= stamp):
            raise JournalValidationError("Invalid correction confirmation time")
        changes = body["changes"]
        if not isinstance(changes, dict) or not changes or set(changes) - CORRECTABLE_FIELDS:
            raise JournalValidationError("Only price, quantity and fees may be corrected")
        original_index = fills[target]
        fill = deepcopy(effective[original_index]["body"]["fill"])
        if all(str(fill[key]) == str(value) for key, value in changes.items()):
            raise JournalValidationError("Correction must change a value")
        fill.update(changes)
        _fill_from_body({"fill": fill})
        prepared_hash = records[original_index]["body"]["prepared_record_sha256"]
        prepared = [i for i, r in enumerate(records[:original_index])
                    if r["record_sha256"] == prepared_hash and r["kind"] == "FILL_PREPARED"]
        if len(prepared) != 1:
            raise JournalValidationError("Correction lacks original prepared fill")
        effective[original_index]["body"]["fill"] = fill
        effective[prepared[0]]["body"]["fill"] = deepcopy(fill)
        versions[target] = record["record_sha256"]
        item = lineage.setdefault(target, dict(original_fill=deepcopy(records[original_index]["body"]["fill"]),
            correction_record_sha256s=[]))
        item.update(effective_fill=deepcopy(fill), effective_version_sha256=record["record_sha256"])
        item["correction_record_sha256s"].append(record["record_sha256"])
    return effective, lineage


def revalidate_simulated_budget(replayed):
    """Reuse the native sleeve projection at every historical state transition."""
    from .private_risk_projection import _sleeve_policy
    _, sleeves, reserve = _sleeve_policy(replayed)
    if sleeves is None:
        return "NOT_ASSESSABLE_NO_CONFIRMED_IPS"
    floor = max(Decimal(reserve), Decimal(replayed.policy.get("minimum_cash_cny") or "0"))
    if (replayed.state.cash_cny < floor
            or any(Decimal(row["cash_cny"]) < 0 for row in sleeves.values())):
        raise JournalValidationError("Correction violates historical sleeve/shared cash budget")
    return "REVALIDATED_CONFIRMED_HYPOTHETICAL_IPS"


def replay_corrected_simulation(service, records, *, validate_theses):
    effective, lineage = effective_simulated_records(records, cutoff=service._now())
    replayed = service._replay(effective, _validate_theses=False, _apply_corrections=False,
        _revalidate_simulated_budgets=True)
    if validate_theses:
        resolve_personal_entry_thesis(records=records,
            account_scope=service.account_context.account_scope, expected_revision=len(records), as_of=service._now())
    latest = max(i for i, r in enumerate(records) if r["kind"] == CORRECTION_KIND)
    last_snapshot = max((i for i, r in enumerate(records) if r["kind"] == "RECONCILED_CONFIRMED"), default=-1)
    # Fills keep their original IDs/count. The new revision invalidates older
    # reconciliations even when quantity happened not to change.
    if last_snapshot < latest:
        replayed = replace(replayed, snapshot=None, snapshot_version=None, snapshot_scope=None)
    state = replace(replayed.state, confirmed_at=max(replayed.state.confirmed_at,
        datetime.fromisoformat(records[latest]["body"]["confirmed_at"])))
    trades = tuple(dict(trade, fill_correction=deepcopy(lineage[trade["record_sha256"]]))
        if trade["record_sha256"] in lineage else trade for trade in replayed.trades)
    return replace(replayed, state=state, trades=trades)


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
        self._ledger = PrivatePortfolioService(SimulatedCorrectionJournal(self._path),
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
        payload = self._request(request)
        fields = {"idempotency_key", "expected_revision", "target_fill_record_sha256",
            "expected_original_version", "changes", "confirmed_at", "reason"}
        if set(payload) != fields:
            raise JournalValidationError("Exact correction fields required")
        changes = payload["changes"]
        if not isinstance(changes, dict) or not changes or set(changes) - CORRECTABLE_FIELDS:
            raise JournalValidationError("Only price, quantity and fees may be corrected")
        with self._ledger.journal.transaction() as records:
            self._ledger._validate_account_context(records)
            existing = self._ledger._existing(records, payload)
            if existing is not None:
                response, digest = existing
                return dict(response, effective_version_sha256=digest), digest
            revision = self._ledger._require_revision(records, payload)
            current = self._ledger._replay(records)
            if current is None or current.pending is not None or current.pending_policy is not None:
                raise JournalValidationError("Correction requires confirmed state without drafts")
            moment = self._ledger._now()
            confirmed = datetime.fromisoformat(payload["confirmed_at"])
            if (confirmed.utcoffset() is None or not datetime.fromisoformat(records[-1]["recorded_at"])
                    <= confirmed <= moment):
                raise JournalValidationError("Explicit current correction confirmation required")
            body = dict(schema_version=CORRECTION_SCHEMA, account_context=self._context.as_dict(),
                target_fill_record_sha256=payload["target_fill_record_sha256"],
                expected_original_version=payload["expected_original_version"], expected_revision=revision,
                changes=deepcopy(changes), confirmed_at=confirmed.isoformat(), reason=payload["reason"],
                confirmed_hypothetical=True)
            provisional = dict(schema_version="private-portfolio-journal-v1", sequence=revision + 1,
                recorded_at=moment.isoformat(), kind=CORRECTION_KIND,
                previous_record_sha256=records[-1]["record_sha256"], idempotency_key=payload["idempotency_key"],
                request_sha256=request_digest(payload), action="no_order", changes_holdings=True,
                body=body, response={})
            provisional["record_sha256"] = sha256(canonical_bytes(provisional)).hexdigest()
            try:
                candidate = self._ledger._replay([*records, provisional])
            except ValueError as error:
                raise JournalValidationError("Corrected history rejected: " + str(error)) from error
            response = dict(status=CORRECTION_KIND, namespace="SIMULATED", action="no_order",
                revision=revision + 1, target_fill_record_sha256=payload["target_fill_record_sha256"],
                previous_version_sha256=payload["expected_original_version"],
                cash_cny=str(candidate.state.cash_cny), realized_pnl_cny=str(candidate.state.realized_pnl_cny),
                snapshot_status="INVALIDATED_RECONCILIATION_REQUIRED", entry_review_required=True,
                budget_revalidation=revalidate_simulated_budget(candidate), formal_eligibility=False)
            record = self._ledger.journal.append(kind=CORRECTION_KIND, body=body, response=response,
                idempotency_key=payload["idempotency_key"], request_sha256=request_digest(payload),
                recorded_at=moment, changes_holdings=True)
            return dict(response, effective_version_sha256=record["record_sha256"]), record["record_sha256"]

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
        corrections = effective_simulated_records(records)[1] if any(r["kind"] == CORRECTION_KIND for r in records) else {}
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
                    fill_correction=deepcopy(corrections.get(row["fill_record_sha256"])),
                    hypothesis_review_status="ACCOUNT_HISTORY_CORRECTED_REVIEW_REQUIRED" if corrections else "UNCHANGED",
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
            confirmed_fill_correction="PRICE_QUANTITY_FEES_ONLY_V1", fill_corrections=corrections,
            correction_reconciliation_status=("INVALIDATED_RECONCILIATION_REQUIRED" if replayed.snapshot is None
                or replayed.snapshot_version != replayed.state.version
                else "RECONCILED_AFTER_CORRECTION") if corrections else "NOT_APPLICABLE",
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
        before = _sources(records, through_index=index)[0]
        after = _sources(records, through_index=index + 1)[0]
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

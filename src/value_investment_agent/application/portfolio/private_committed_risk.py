"""Authenticated private declarations on the existing journal and risk contract."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from ...domain.portfolio.dual_sleeve_records import canonical_bytes
from ...domain.portfolio.dual_sleeve_risk import decimal, review_dual_sleeve_risk
from ...private_portfolio_intake import require_private_data_path
from ..product.dual_sleeve_risk import _strict_json
from .personal_entry_thesis import _clock, _journal, _subject
from .private_portfolio_service import PrivatePortfolioService, JournalConflict, JournalValidationError, request_digest
from .private_risk_projection import build_risk_input, _account_time_blockers


def _sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _text(value, label):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= 8000:
        raise JournalValidationError(label + " requires bounded nonempty text")
    return value


def _immutable_file(path, content):
    """Publish complete bytes without ever replacing an existing file."""
    temporary = path.with_name(".p-" + uuid4().hex[:16])
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise JournalValidationError("Immutable committed-risk file differs") from None
    finally:
        temporary.unlink(missing_ok=True)


def validate_committed_risk_event(record, *, account_scope, ips_record_sha256, lots):
    """Validate replayed non-accounting facts without requiring auxiliary files."""
    body = record["body"]
    required = {"context", "amounts", "authenticated_subject", "confirmed_at", "read_and_confirmed",
        "confirmation_note", "idempotency_key", "request_sha256", "input_sha256"}
    if set(body) != required or record.get("changes_holdings") is not False or body["read_and_confirmed"] is not True:
        raise JournalValidationError("Invalid committed-risk declaration event")
    context = body["context"]
    expected_namespace = "SIMULATED" if any(marker in account_scope.upper().replace("-", "_") for marker in
        ("TEST_ONLY", "SIMULATED", "SYNTHETIC")) else "ACTUAL"
    grouped = {}
    for lot in lots:
        row = grouped.setdefault((lot.sleeve, lot.symbol), dict(sleeve=lot.sleeve, symbol=lot.symbol,
            exchange=lot.exchange, quantity=decimal("0", "quantity"), cost_basis_cny=decimal("0", "cost")))
        row["quantity"] += lot.quantity
        row["cost_basis_cny"] += lot.cost_cny
    expected_rows = [{**row, "quantity": str(row["quantity"]), "cost_basis_cny": str(row["cost_basis_cny"])}
        for row in grouped.values()]
    if (set(context) != {"account_scope", "revision", "journal_tip_sha256", "ips_record_sha256", "namespace", "allocations"}
            or context["account_scope"] != account_scope or type(context["revision"]) is not int
            or context["revision"] != record["sequence"] - 1
            or context["journal_tip_sha256"] != record["previous_record_sha256"]
            or context["ips_record_sha256"] != ips_record_sha256 or context["namespace"] != expected_namespace
            or context["allocations"] != expected_rows):
        raise JournalValidationError("Committed-risk event differs from journal/IPS/lots")
    _subject(body["authenticated_subject"])
    _text(body["confirmation_note"], "confirmation_note")
    if (_clock(body["confirmed_at"]) > _clock(record["recorded_at"])
            or body["idempotency_key"] != record["idempotency_key"]
            or body["request_sha256"] != record["request_sha256"]):
        raise JournalValidationError("Invalid committed-risk event confirmation")
    from ...domain.portfolio.dual_sleeve_risk import digest
    digest(body["input_sha256"], "input_sha256")
    PrivateCommittedRiskService._amounts(body["amounts"], context)


class PrivateCommittedRiskService:
    """Routes supply trusted subject/time/paths; never expose source paths to Web.

    Confirmations append non-accounting events under the existing journal lock.
    Current market evidence can materialize a new immutable derived input, but
    cannot change the amounts, evidence or confirmed journal/IPS/lot identity.
    """

    def __init__(self, journal, *, repository_root, private_root):
        self.journal = journal
        self.root, self.private_root = Path(repository_root), Path(private_root)

    def _path(self, path, *, must_exist=False):
        return require_private_data_path(Path(path), private_root=self.private_root,
            repository_root=self.root, must_exist=must_exist)

    def _prepare(self, authenticated_subject, now):
        _subject(authenticated_subject)
        moment = _clock(now)
        self._path(self.journal.path)
        return moment

    def _context(self, records, now):
        if not records:
            raise JournalValidationError("Confirmed private account required")
        account = records[0]["body"]["account_scope"]
        _journal(records, account_scope=account, expected_revision=len(records), as_of=now)
        replayed = PrivatePortfolioService(self.journal)._replay(records)
        namespace = ("SIMULATED" if any(marker in account.upper().replace("-", "_") for marker in
            ("TEST_ONLY", "SIMULATED", "SYNTHETIC")) else "ACTUAL")
        payload = build_risk_input(replayed, sellable_as_of=now.astimezone(ZoneInfo("Asia/Shanghai")).date(),
            repository_root=self.root, generated_at=now)
        if namespace == "SIMULATED":
            payload["namespace"] = namespace
            payload["portfolio"]["snapshot"]["namespace"] = namespace
            payload["portfolio"]["policy"]["sensitivity"] = "SIMULATED_DEMONSTRATION"
            if payload["shared_budget"] is not None:
                payload["shared_budget"]["policy_scope"] = "SYNTHETIC_POLICY_ONLY"
        exchanges = {lot.symbol: lot.exchange for lot in replayed.state.lots}
        allocations = [{"sleeve": row["sleeve"], "symbol": row["symbol"],
            "exchange": exchanges[row["symbol"]], "quantity": row["quantity"],
            "cost_basis_cny": row["cost_basis_cny"]} for row in payload["allocations"]]
        context = dict(account_scope=account, revision=len(records),
            journal_tip_sha256=records[-1]["record_sha256"],
            ips_record_sha256=replayed.policy.get("_record_sha256"), namespace=namespace,
            allocations=allocations)
        key = hashlib.sha256(str(self.journal.path.resolve()).encode("utf-8")).hexdigest()[:24]
        folder = self._path(self.private_root / "committed-risk" / key / records[-1]["record_sha256"])
        return context, payload, folder, replayed

    def _saved(self, folder, context, subject, now, records):
        if records[-1]["kind"] != "COMMITTED_RISK_CONFIRMED":
            return None
        expected = {**context, "revision": len(records) - 1,
            "journal_tip_sha256": records[-1]["previous_record_sha256"]}
        declaration = _strict_json(self._path(folder / "declaration.json", must_exist=True))
        if (declaration != records[-1]["body"] or declaration.get("context") != expected
                or declaration.get("authenticated_subject") != subject
                or _clock(declaration["confirmed_at"]) > now
                or declaration.get("read_and_confirmed") is not True):
            raise JournalValidationError("Committed-risk declaration identity differs")
        original = self._path(folder / "input.json", must_exist=True)
        if hashlib.sha256(original.read_bytes()).hexdigest() != declaration["input_sha256"]:
            raise JournalValidationError("Committed-risk input hash mismatch")
        amounts = self._amounts(declaration["amounts"], context)
        original_payload = _strict_json(original)
        original_amounts = [{key: row[key] for key in
            ("symbol", "sleeve", "committed_risk_cny", "evidence_ref")}
            for row in original_payload["allocations"]]
        if (self._amounts(original_amounts, context) != amounts
                or original_payload["namespace"] != context["namespace"]):
            raise JournalValidationError("Saved declaration differs from its immutable input")
        return declaration

    @staticmethod
    def _amounts(values, context):
        if not isinstance(values, list):
            raise JournalValidationError("Explicit per-sleeve amounts required")
        rows = {}
        for row in values:
            if not isinstance(row, dict) or set(row) != {"symbol", "sleeve", "committed_risk_cny", "evidence_ref"}:
                raise JournalValidationError("Exact declaration amount fields required")
            if not isinstance(row["sleeve"], str) or not isinstance(row["symbol"], str):
                raise JournalValidationError("Risk declaration allocation identity requires text")
            key = (row["sleeve"], row["symbol"])
            if key in rows:
                raise JournalValidationError("Duplicate risk declaration allocation")
            amount = decimal(row["committed_risk_cny"], "committed_risk_cny")
            rows[key] = {**row, "committed_risk_cny": str(amount),
                "evidence_ref": _text(row["evidence_ref"], "evidence_ref")}
        expected = {(row["sleeve"], row["symbol"]) for row in context["allocations"]}
        if set(rows) != expected:
            raise JournalValidationError("Declare every current held sleeve/security exactly once")
        return [rows[key] for key in sorted(rows)]

    @staticmethod
    def _apply(payload, amounts):
        rows = {(row["sleeve"], row["symbol"]): row for row in amounts}
        for row in payload["allocations"]:
            value = rows[(row["sleeve"], row["symbol"])]
            row.update(committed_risk_cny=value["committed_risk_cny"], evidence_ref=value["evidence_ref"])

    def _view(self, records, subject, now):
        if not records:
            return dict(status="NOT_CONNECTED", action="no_order", sensitivity="PRIVATE", account_scope=None,
                revision=0, journal_tip_sha256=None, ips_record_sha256=None, namespace=None, allocations=[],
                confirmation_status="NOT_CONFIRMED", qualification_status="BLOCKED_PRIVATE_INPUT",
                blockers=["PRIVATE_PORTFOLIO_NOT_CONNECTED"], confirmation_sha256=None, formal_eligibility=False,
                ledger_written=False, changes_holdings=False, broker_execution_permission=False), None, None
        context, payload, folder, replayed = self._context(records, now)
        if records[-1]["kind"] == "COMMITTED_RISK_CONFIRMED":
            folder = self._path(folder.with_name(records[-1]["previous_record_sha256"]))
        saved = self._saved(folder, context, subject, now, records)
        amounts = saved["amounts"] if saved else []
        by_key = {(row["sleeve"], row["symbol"]): row for row in amounts}
        allocations = [{**row, "committed_risk_cny": by_key.get((row["sleeve"], row["symbol"]), {}).get("committed_risk_cny"),
            "evidence_ref": by_key.get((row["sleeve"], row["symbol"]), {}).get("evidence_ref")}
            for row in context["allocations"]]
        if saved:
            self._apply(payload, amounts)
        try:
            report = review_dual_sleeve_risk(payload, generated_at=now,
                allow_synthetic=context["namespace"] == "SIMULATED")
            blockers = list(report["blockers"])
            complete = report["status"] in {"RISK_REVIEW_CALCULATED", "REVIEW_REQUIRED"}
        except (ValueError, KeyError, TypeError):
            blockers, complete = ["CURRENT_RISK_CONTRACT_INCOMPLETE"], False
        blockers.extend(_account_time_blockers(replayed, now))
        pending = replayed.pending is not None or replayed.pending_policy is not None
        if pending:
            blockers.append("PENDING_DRAFT_EXISTS")
        if not saved:
            blockers.append("COMMITTED_RISK_CONFIRMATION_REQUIRED")
        qualification = ("TEST_ONLY_NOT_ACTUAL" if context["namespace"] != "ACTUAL" else
            "ACTUAL_CONTRACT_VERIFIED" if saved and complete and not pending and not _account_time_blockers(replayed, now)
            else "BLOCKED_PRIVATE_INPUT")
        view = {**context, "allocations": allocations, "action": "no_order", "sensitivity": "PRIVATE",
            "status": "CONFIRMED" if saved else "CONFIRMATION_REQUIRED",
            "confirmation_status": "CONFIRMED" if saved else "NOT_CONFIRMED",
            "qualification_status": qualification, "blockers": list(dict.fromkeys(blockers)),
            "confirmation_sha256": _sha(saved) if saved else None,
            "formal_eligibility": False, "ledger_written": False,
            "changes_holdings": False, "broker_execution_permission": False}
        return view, payload, folder

    def read(self, *, authenticated_subject, now):
        moment = self._prepare(authenticated_subject, now)
        with self.journal.transaction() as records:
            return self._view(records, authenticated_subject, moment)[0]

    def confirm(self, payload, *, authenticated_subject, now):
        moment = self._prepare(authenticated_subject, now)
        required = {"expected_revision", "account_scope", "journal_tip_sha256", "amounts",
            "read_and_confirmed", "confirmation_note", "idempotency_key"}
        if not isinstance(payload, dict) or set(payload) != required or payload["read_and_confirmed"] is not True:
            raise JournalValidationError("Exact acknowledged risk confirmation required")
        _text(payload["confirmation_note"], "confirmation_note")
        _text(payload["idempotency_key"], "idempotency_key")
        with self.journal.transaction() as records:
            service = PrivatePortfolioService(self.journal)
            trusted = {**payload, "authenticated_subject": authenticated_subject}
            existing = service._existing(records, trusted)
            if existing is not None:
                if existing[1] != records[-1]["record_sha256"]:
                    raise JournalConflict("REVISION_CONFLICT", "Confirmed risk binding is no longer current")
                return {**self._view(records, authenticated_subject, moment)[0], "status": "COMMITTED_RISK_CONFIRMED", "ledger_written": True,
                    "request_binding": {key: payload[key] for key in ("expected_revision", "account_scope", "journal_tip_sha256")}}
            context, contract, folder, replayed = self._context(records, moment)
            if replayed.pending is not None or replayed.pending_policy is not None:
                raise JournalConflict("PENDING_DRAFT_EXISTS", "Finish pending draft before risk declaration")
            if (type(payload["expected_revision"]) is not int or payload["expected_revision"] != len(records)
                    or payload["journal_tip_sha256"] != context["journal_tip_sha256"]
                    or payload["account_scope"] != context["account_scope"]):
                raise JournalConflict("REVISION_CONFLICT", "Risk confirmation requires current account/revision/tip")
            amounts = self._amounts(payload["amounts"], context)
            request_sha = request_digest(trusted)
            self._apply(contract, amounts)
            content = canonical_bytes(contract)
            declaration = dict(context=context, amounts=amounts, authenticated_subject=authenticated_subject,
                confirmed_at=moment.isoformat(), read_and_confirmed=True, confirmation_note=payload["confirmation_note"],
                idempotency_key=payload["idempotency_key"], request_sha256=request_sha,
                input_sha256=hashlib.sha256(content).hexdigest())
            if folder.exists():
                saved = _strict_json(self._path(folder / "declaration.json", must_exist=True))
                if saved["request_sha256"] != request_sha or saved["context"] != context:
                    raise JournalConflict("COMMITTED_RISK_CONFIRMATION_CONFLICT", "Uncommitted immutable declaration differs")
                if any(saved.get(key) != declaration[key] for key in (
                        "amounts", "authenticated_subject", "read_and_confirmed", "confirmation_note", "idempotency_key")):
                    raise JournalValidationError("Uncommitted risk declaration differs from explicit request")
                if hashlib.sha256((folder / "input.json").read_bytes()).hexdigest() != saved["input_sha256"]:
                    raise JournalValidationError("Uncommitted risk input hash mismatch")
                validate_committed_risk_event(dict(body=saved, changes_holdings=False, sequence=len(records) + 1,
                    previous_record_sha256=context["journal_tip_sha256"], recorded_at=moment.isoformat(),
                    idempotency_key=payload["idempotency_key"], request_sha256=request_sha),
                    account_scope=context["account_scope"], ips_record_sha256=context["ips_record_sha256"],
                    lots=replayed.state.lots)
                declaration = saved
            else:
                folder.parent.mkdir(parents=True, exist_ok=True)
                staging = self._path(folder.with_name(".p-" + uuid4().hex[:16]))
                staging.mkdir()
                try:
                    _immutable_file(staging / "input.json", content)
                    _immutable_file(staging / "declaration.json", canonical_bytes(declaration))
                    os.rename(staging, folder)
                finally:
                    if staging.exists():
                        for name in ("input.json", "declaration.json"):
                            (staging / name).unlink(missing_ok=True)
                        staging.rmdir()
            record = self.journal.append(kind="COMMITTED_RISK_CONFIRMED", body=declaration,
                response={"action": "no_order", "status": "COMMITTED_RISK_CONFIRMED", "revision": len(records)+1,
                    "changes_holdings": False}, idempotency_key=payload["idempotency_key"],
                request_sha256=request_sha, recorded_at=moment, changes_holdings=False)
            return {**self._view([*records, record], authenticated_subject, moment)[0], "status": "COMMITTED_RISK_CONFIRMED", "ledger_written": True,
                "request_binding": {key: payload[key] for key in ("expected_revision", "account_scope", "journal_tip_sha256")}}

    def source(self, *, authenticated_subject, now):
        with self.journal.transaction() as records:
            if not records or records[-1]["kind"] != "COMMITTED_RISK_CONFIRMED":
                return None
            moment = self._prepare(authenticated_subject, now)
            view, payload, folder = self._view(records, authenticated_subject, moment)
            if view["qualification_status"] != "ACTUAL_CONTRACT_VERIFIED":
                return None
            content = canonical_bytes(payload)
            digest = hashlib.sha256(content).hexdigest()
            path = self._path(folder / ("input-" + digest[:24] + ".json"))
            _immutable_file(path, content)
            return dict(input_path=str(path), input_sha256=digest, private_root=str(self.private_root),
                journal_revision=len(records), journal_tip_sha256=view["journal_tip_sha256"])

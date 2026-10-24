"""Bounded manual public observations, never an admitted M5 monitoring run."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from .intraday_monitor import _atomic_write
from .intraday_completed_plan import project_completed_plan
from .intraday_observation import project_intraday_observation
from .intraday_plan_observation import evaluate_quote_plan
from .public_condition_notifications import project_notification_inbox, OPERATIONS
from ..portfolio.private_journal_lock import InterProcessLock, LockTimeout
from ...quote_session_collection import collect_session_bundle, resolve_session_reference
from ...infrastructure.hotspot.intraday_bars import collect_intraday_bar_documents
from ...infrastructure.hotspot.sina_price_case import PERIODS


SCHEMA = "local-public-observation-session-v1"
PLAN_SCHEMA = "local-public-observation-session-v2"
COMPLETED_PLAN_SCHEMA = "local-public-observation-session-v3"
SCHEMAS = {SCHEMA, PLAN_SCHEMA, COMPLETED_PLAN_SCHEMA}
MAX_BYTES = 8_000_000
AGE = timedelta(seconds=120)
CONFIRMATION_FIELDS = {"confirmation_scope", "pending_confirmations",
                       "price_conditions_observed", "structure_confirmation"}


def _legacy_completed(expected, plan):
    """Reconstruct the exact pre-V5 result from source-replayed current cursors."""
    legacy = {key: deepcopy(value) for key, value in expected.items()
              if key not in CONFIRMATION_FIELDS | {"result_sha256"}}
    if (expected["status"] == "WAITING_CONFIRMATION"
            and expected["price_conditions_observed"]
            and plan.get("opportunity_quality", {}).get("structure_tier")
                == "STRUCTURE_QUALIFIED_OBSERVATION"):
        legacy["status"] = "STRUCTURE_CONFIRMED_OBSERVATION"
    legacy["result_sha256"] = _sha(_bytes(legacy))
    return legacy


def _completed_view(result):
    if CONFIRMATION_FIELDS <= result.keys():
        return deepcopy(result)
    current = deepcopy(result)
    current.update(audit_result_sha256=result["result_sha256"],
        audit_status=result["status"], structure_confirmation=False,
        confirmation_scope="COMPLETED_CLOSE_VS_FROZEN_PRIMARY_PRICE_REFERENCES_ONLY",
        pending_confirmations=["PRIOR_FIVE_VOLUME_RULE", "PER_PERIOD_BREAKOUT_RULES",
                               "DAILY_60M_15M_STRUCTURE_REASSESSMENT"],
        price_conditions_observed=all(
            item["status"] == "COMPLETED_BAR_VERIFIED"
            and item["states"][0]["state"]["status"] == "CONDITION_REVIEW"
            for item in result["periods"].values()))
    if current["status"] == "STRUCTURE_CONFIRMED_OBSERVATION":
        current["status"] = "WAITING_CONFIRMATION"
    current.pop("result_sha256")
    current["result_sha256"] = _sha(_bytes(current))
    return current


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path, digest=None):
    if path.is_symlink():
        raise ValueError("Observation artifacts cannot be symbolic links")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Observation artifact exceeds bounds")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES or (digest is not None and _sha(raw) != digest):
        raise ValueError("Observation artifact integrity failure")
    return json.loads(raw)


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Invalid observation artifact identity")
    return value


def _stamp(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Aware server clock required")
    return value.astimezone(timezone.utc)


def _refs(bundle, symbol):
    """Verify every retained document, including negative/non-session samples."""
    if not isinstance(bundle, dict) or bundle.get("version") != "quote-session-collection-v1":
        raise ValueError("Invalid collection bundle")
    documents = bundle["documents"]
    if not isinstance(documents, dict) or len(documents) > 10:
        raise ValueError("Invalid document count")
    for identity, document in documents.items():
        if not isinstance(document, dict):
            raise ValueError("Invalid document")
        url = urlsplit(document["source_url"])
        if (url.scheme != "https" or url.hostname not in {
                "qt.gtimg.cn", "hq.sinajs.cn", "www.szse.cn", "www.sse.com.cn"}
                or url.username or url.password or url.fragment or url.port not in {None, 443}
                or not isinstance(document["raw_base64"], str)
                or len(document["raw_base64"]) > 1_333_336):
            raise ValueError("Unsafe or oversized retained source")
        expected = _sha((document["source_url"] + "\n" + document["fetched_at"]
                         + "\n" + document["sha256"]).encode())
        raw = base64.b64decode(document["raw_base64"], validate=True)
        if identity != expected or len(raw) > 1_000_000 or _sha(raw) != document["sha256"]:
            raise ValueError("Raw document integrity failure")
    # Partial collections may lack one provider; their projection must fail closed.
    reference = bundle.get("references", {}).get(symbol)
    refs = []
    if reference is not None:
        linked = reference.get("document_refs", {})
        for provider in ("tencent", "sina"):
            identity = linked.get(provider)
            if identity is not None:
                document = documents[identity]
                # Provider parsers validate full URLs on positive observations.
                # Suppress arbitrary query parameters on failed collections.
                url = urlsplit(document["source_url"])
                expected_prefix = "/q=" if provider == "tencent" else "/list="
                if (url.query or not re.fullmatch(re.escape(expected_prefix) + r"(?:sh|sz)[0-9]{6}", url.path)
                        or url.hostname != ("qt.gtimg.cn" if provider == "tencent" else "hq.sinajs.cn")):
                    raise ValueError("Unexpected provider URL")
                refs.append({"source_url": document["source_url"], "sha256": document["sha256"]})
        if all(linked.get(key) for key in ("tencent", "sina")):
            resolve_session_reference(reference, documents)
    return refs


def _sample(bundle, *, identity, symbol, checked):
    refs = _refs(bundle, symbol)
    projected = project_intraday_observation(bundle, symbol=symbol, now=checked, max_age=AGE)
    sample = {"sample_id": identity, "symbol": symbol, "checked_at": checked.isoformat(),
              "status": projected["status"], "reason": projected["reason"], "source_refs": refs}
    if projected["observation"] is not None:
        sample["observation"] = projected["observation"]
    return sample


class PublicObservationSession:
    def __init__(self, root: Path, *, clock=None, collector=None, bar_collector=None,
                 interval_seconds=60, max_samples=10):
        if (isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float))
                or not math.isfinite(interval_seconds) or interval_seconds <= 0
                or type(max_samples) is not int or not 1 <= max_samples <= 10):
            raise ValueError("Positive interval and sample bound 1..10 required")
        self.root = Path(root).resolve()
        self.directory = self.root / "runtime/intraday-monitor/public-observation"
        self._check_directory()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.collector = collector or collect_session_bundle
        self.bar_collector = bar_collector or collect_intraday_bar_documents
        self.interval = interval_seconds
        self.limit = max_samples
        self._mutex = threading.RLock()
        self._thread = None
        self._stop = threading.Event()
        self._closed = False
        self._current = None
        self._failure = False

    def _check_directory(self):
        if self.directory.resolve() != self.directory:
            raise ValueError("Observation directory cannot redirect through symbolic links")

    def _persist(self):
        self._check_directory()
        pointer_path = self.directory / "current.json"
        entries = self._entries(_read(pointer_path)) if pointer_path.exists() else []
        report_id = str(uuid4())
        raw = _bytes(self._current)
        if len(raw) > MAX_BYTES:
            raise ValueError("Observation report exceeds bounds")
        with (self.directory / (report_id + ".report.json")).open("xb") as stream:
            stream.write(raw)
            stream.flush()
        entry = {"session_id": self._current["session_id"], "report_id": report_id, "sha256": _sha(raw)}
        entries = [row for row in entries if row["session_id"] != entry["session_id"]] + [entry]
        if len(entries) > 1000:
            raise ValueError("Observation session history capacity reached")
        _atomic_write(pointer_path, {"schema_version": self._current["schema_version"],
            "report_id": report_id, "sha256": _sha(raw), "sessions": entries})

    def _entries(self, pointer):
        current = _uuid(pointer["report_id"])
        entries = pointer.get("sessions")
        if entries is None:
            old = _read(self.directory / (current + ".report.json"), pointer["sha256"])
            entries = [{"session_id": old["session_id"], "report_id": current, "sha256": pointer["sha256"]}]
        if not isinstance(entries, list) or not 1 <= len(entries) <= 1000:
            raise ValueError("Invalid observation history index")
        seen = set()
        for entry in entries:
            if (set(entry) != {"session_id", "report_id", "sha256"}
                    or _uuid(entry["session_id"]) in seen or not isinstance(entry["sha256"], str)
                    or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])):
                raise ValueError("Invalid observation history binding")
            _uuid(entry["report_id"])
            seen.add(entry["session_id"])
        if not any(row["report_id"] == current and row["sha256"] == pointer["sha256"] for row in entries):
            raise ValueError("Current observation and history index differ")
        return entries

    def start(self, symbol, *, plan_binding=None) -> dict:
        if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
            raise ValueError("Exact symbol required")
        plan_binding = deepcopy(plan_binding)
        if plan_binding is not None:
            if not isinstance(plan_binding, dict) or plan_binding.get("symbol") != symbol:
                raise ValueError("Plan and observation security differ")
            evaluate_quote_plan(plan_binding, None, previous=None, now=_stamp(self.clock()))
        with self._mutex:
            self._check_directory()
            if self._closed:
                raise ValueError("Observation session is closed")
            if self._thread is not None:
                raise ValueError("Observation session already running or stopping")
            lock_path = self.directory / "session.lock"
            if lock_path.is_symlink():
                raise ValueError("Observation lock cannot be a symbolic link")
            lock = InterProcessLock(lock_path, timeout_seconds=0.05)
            try:
                lock.acquire()
            except LockTimeout:
                raise ValueError("Another public observation session is active") from None
            except Exception:
                raise ValueError("Unable to lock public observation session") from None
            try:
                existing = self.read()
                if existing["status"] == "CORRUPT":
                    raise ValueError("Existing observation history is corrupt")
                cursors = {}
                pointer_path = self.directory / "current.json"
                if plan_binding is not None and pointer_path.exists():
                    reports = self._verified_reports(self._entries(_read(pointer_path)), cursors)
                    # The API may bind the identical verified plan again at a
                    # later request time. Keep the original cursor identity.
                    for report in reversed(reports):
                        old_binding = report.get("plan_binding") or {}
                        if old_binding.get("plan_sha256") == plan_binding["plan_sha256"]:
                            plan_binding = deepcopy(old_binding)
                            break
                seed = cursors.get((plan_binding or {}).get("binding_sha256"))
                self._seed_conditions = seed["condition_result"] if seed else None
                self._seed_completed = seed.get("completed_plan_result") if seed else None
                self._stop = threading.Event()
                self._failure = False
                schema = COMPLETED_PLAN_SCHEMA if plan_binding is not None else SCHEMA
                self._current = {"schema_version": schema, "session_id": str(uuid4()),
                    "symbol": symbol, "status": "RUNNING", "detail": "LOCAL_PUBLIC_OBSERVATION_ONLY",
                    "samples": [], "bindings": []}
                if plan_binding is not None:
                    self._current.update(plan_binding=plan_binding,
                        cursor_policy="CONTINUE_SAME_PLAN_BINDING_V1")
                self._persist()
                self._thread = threading.Thread(target=self._work, args=(symbol, lock),
                                                name="public-observation", daemon=True)
                self._thread.start()
            except Exception:
                self._thread = None
                lock.release()
                raise ValueError("Unable to start public observation session") from None
            return self._view(self._current)

    def _work(self, symbol, lock):
        try:
            for index in range(self.limit):
                # Passing this gate admits one in-flight collection. stop/close
                # cancel later admissions, not an already admitted network call.
                with self._mutex:
                    self._check_directory()
                    if self._stop.is_set():
                        break
                identity = str(uuid4())
                bundle = None
                bar_documents, bar_bindings = {}, {}
                try:
                    bundle = deepcopy(self.collector([symbol]))
                    if self._current["schema_version"] == COMPLETED_PLAN_SCHEMA:
                        try:
                            bar_documents = deepcopy(self.bar_collector(symbol))
                            if not isinstance(bar_documents, dict):
                                raise ValueError("Bar collector must return a period mapping")
                            for period, document in bar_documents.items():
                                if period not in PERIODS or not isinstance(document, dict):
                                    raise ValueError("Unknown or invalid bar period")
                                encoded = _bytes(document)
                                if len(encoded) > MAX_BYTES:
                                    raise ValueError("Retained bar document exceeds bounds")
                                path = self.directory / f"{identity}.{period}.bar.json"
                                with path.open("xb") as stream:
                                    stream.write(encoded)
                                bar_bindings[period] = _sha(encoded)
                            if bar_bindings and set(bar_bindings) != set(PERIODS):
                                raise ValueError("Both 60m and 15m bar documents required")
                        except Exception:
                            bar_documents, bar_bindings = {}, {}
                    # Bars are fetched after the quote. Seal the sample only after
                    # both collection calls complete so their receipts cannot
                    # appear to come from the future relative to this sample.
                    checked = _stamp(self.clock())
                    sample = _sample(bundle, identity=identity, symbol=symbol, checked=checked)
                    raw = _bytes(bundle)
                    if len(raw) > MAX_BYTES:
                        raise ValueError("Collection exceeds bounds")
                    with (self.directory / (identity + ".bundle.json")).open("xb") as stream:
                        stream.write(raw)
                    binding = {"sample_id": identity, "sha256": _sha(raw)}
                    if self._current["schema_version"] == COMPLETED_PLAN_SCHEMA:
                        sample.update(bar_bindings=bar_bindings,
                            bar_collection_status="CAPTURED" if bar_bindings else "UNAVAILABLE")
                except Exception:
                    checked = _stamp(self.clock())
                    sample = {"sample_id": identity, "symbol": symbol, "checked_at": checked.isoformat(),
                              "status": "STALE_OR_UNAVAILABLE", "reason": "COLLECTION_OR_EVIDENCE_FAILED",
                              "source_refs": []}
                    if self._current["schema_version"] == COMPLETED_PLAN_SCHEMA:
                        sample.update(bar_bindings={}, bar_collection_status="UNAVAILABLE")
                    binding = {"sample_id": identity, "sha256": None}
                with self._mutex:
                    if (self._current["samples"] and checked < datetime.fromisoformat(
                            self._current["samples"][-1]["checked_at"])):
                        raise ValueError("Server observation clock regressed")
                    if self._current["schema_version"] in {PLAN_SCHEMA, COMPLETED_PLAN_SCHEMA}:
                        sample["condition_result"] = evaluate_quote_plan(
                            self._current["plan_binding"], sample.get("observation"),
                            previous=(self._current["samples"][-1]["condition_result"]
                                if self._current["samples"] else self._seed_conditions), now=checked)
                    if self._current["schema_version"] == COMPLETED_PLAN_SCHEMA:
                        sample["completed_plan_result"] = project_completed_plan(
                            self._current["plan_binding"], bar_documents,
                            previous=(self._current["samples"][-1]["completed_plan_result"]
                                if self._current["samples"] else self._seed_completed), now=checked,
                            include_documents=False)
                    self._current["samples"].append(sample)
                    self._current["bindings"].append(binding)
                    self._persist()
                if sample["reason"] == "OUTSIDE_EXCHANGE_SESSION":
                    break
                if index + 1 < self.limit and self._stop.wait(self.interval):
                    break
        except BaseException:
            with self._mutex:
                self._failure = True
        finally:
            with self._mutex:
                self._current["status"] = "FAILED" if self._failure else "STOPPED"
                self._current["detail"] = "WORKER_FAILED" if self._failure else "LOCAL_PUBLIC_OBSERVATION_STOPPED"
                try:
                    self._persist()
                except BaseException:
                    self._failure = True
                finally:
                    lock.release()
                    self._thread = None

    def _view(self, report):
        running = self._thread is not None
        status = "FAILED" if self._failure else report["status"]
        detail = "WORKER_OR_STORAGE_FAILED" if self._failure else report["detail"]
        if running and self._stop.is_set():
            status, detail = "STOPPING", "WAITING_FOR_IN_FLIGHT_COLLECTION"
        elif not running and status == "RUNNING":
            status, detail = "STOPPED", "RETAINED_OBSERVATIONS_NO_LOCAL_WORKER"
        result = {"status": status, "monitor_running": running, "symbol": report["symbol"],
                "session_id": report["session_id"],
                "detail": detail, "samples": deepcopy(report["samples"]),
                "action": "no_order", "eligibility": False, "m5_admitted": False}
        if report["schema_version"] in {PLAN_SCHEMA, COMPLETED_PLAN_SCHEMA}:
            results = [sample["condition_result"] for sample in report["samples"]]
            result.update(plan_binding=deepcopy(report["plan_binding"]),
                condition_observation=deepcopy(results[-1]) if results else None,
                condition_transitions=[deepcopy(item) for batch in results for item in batch["transitions"]])
        if report["schema_version"] == COMPLETED_PLAN_SCHEMA:
            completed = [sample["completed_plan_result"] for sample in report["samples"]]
            result["completed_plan_observation"] = _completed_view(completed[-1]) if completed else None
            for sample in result["samples"]:
                sample["completed_plan_result"] = _completed_view(sample["completed_plan_result"])
        return result

    def _verified_reports(self, entries, cursors=None):
        cursors = {} if cursors is None else cursors
        reports = []
        for entry in entries:
            report = self._verified_report(entry, cursors)
            reports.append(report)
            if report.get("plan_binding") and report["samples"]:
                cursors[report["plan_binding"]["binding_sha256"]] = report["samples"][-1]
        return reports

    def _verified_report(self, entry, cursors=None):
        report = _read(self.directory / (_uuid(entry["report_id"]) + ".report.json"), entry["sha256"])
        if (report["schema_version"] not in SCHEMAS
                or report["status"] not in {"RUNNING", "STOPPED", "FAILED"}
                or report["session_id"] != entry["session_id"]
                or not re.fullmatch(r"[0-9]{6}", report["symbol"])
                or len(report["samples"]) > 10 or len(report["bindings"]) != len(report["samples"])):
            raise ValueError("Invalid observation report")
        if report["schema_version"] in {PLAN_SCHEMA, COMPLETED_PLAN_SCHEMA}:
            if report["plan_binding"]["symbol"] != report["symbol"]:
                raise ValueError("Plan security mismatch")
            evaluate_quote_plan(report["plan_binding"], None, previous=None, now=_stamp(self.clock()))
        ids, previous, previous_conditions, previous_completed = set(), None, None, None
        policy = report.get("cursor_policy")
        if policy is not None:
            if policy != "CONTINUE_SAME_PLAN_BINDING_V1" or "plan_binding" not in report:
                raise ValueError("Unknown observation cursor policy")
            seed = (cursors or {}).get(report["plan_binding"]["binding_sha256"])
            if seed:
                previous_conditions = seed["condition_result"]
                previous_completed = seed.get("completed_plan_result")
                previous = _stamp(datetime.fromisoformat(seed["checked_at"]))
        for sample, binding in zip(report["samples"], report["bindings"]):
            identity = _uuid(sample["sample_id"])
            checked = _stamp(datetime.fromisoformat(sample["checked_at"]))
            if (identity in ids or binding["sample_id"] != identity or sample["symbol"] != report["symbol"]
                    or (previous is not None and checked < previous)):
                raise ValueError("Observation sample identity mismatch")
            ids.add(identity)
            previous = checked
            if binding["sha256"] is not None:
                bundle = _read(self.directory / (identity + ".bundle.json"), binding["sha256"])
                expected = _sample(bundle, identity=identity, symbol=report["symbol"], checked=checked)
            else:
                expected = {"sample_id": identity, "symbol": report["symbol"], "checked_at": checked.isoformat(),
                    "status": "STALE_OR_UNAVAILABLE", "reason": "COLLECTION_OR_EVIDENCE_FAILED", "source_refs": []}
            if report["schema_version"] in {PLAN_SCHEMA, COMPLETED_PLAN_SCHEMA}:
                previous_conditions = evaluate_quote_plan(report["plan_binding"], expected.get("observation"),
                    previous=previous_conditions, now=checked)
                expected["condition_result"] = previous_conditions
            if report["schema_version"] == COMPLETED_PLAN_SCHEMA:
                bar_bindings = sample.get("bar_bindings")
                if (not isinstance(bar_bindings, dict) or not set(bar_bindings).issubset(set(PERIODS))
                        or (bar_bindings and set(bar_bindings) != set(PERIODS))
                        or sample.get("bar_collection_status") != (
                            "CAPTURED" if bar_bindings else "UNAVAILABLE")):
                    raise ValueError("Invalid completed-bar binding")
                bar_documents = {}
                for period, digest in bar_bindings.items():
                    bar_documents[period] = _read(self.directory / f"{identity}.{period}.bar.json", digest)
                previous_completed = project_completed_plan(report["plan_binding"], bar_documents,
                    previous=previous_completed, now=checked, include_documents=False)
                expected["bar_bindings"] = deepcopy(bar_bindings)
                expected["bar_collection_status"] = sample["bar_collection_status"]
                expected["completed_plan_result"] = previous_completed
                if not CONFIRMATION_FIELDS.intersection(sample["completed_plan_result"]):
                    expected["completed_plan_result"] = _legacy_completed(
                        previous_completed, report["plan_binding"]["plan"])
            if expected != sample:
                raise ValueError("Observation replay mismatch")
        return report

    def read(self) -> dict:
        with self._mutex:
            try:
                self._check_directory()
                pointer_path = self.directory / "current.json"
                if not pointer_path.exists():
                    if self._current is not None:
                        raise ValueError("Observation pointer missing")
                    return {"status": "NOT_STARTED", "monitor_running": False,
                            "detail": "LOCAL_PUBLIC_OBSERVATION_ONLY", "samples": [],
                            "action": "no_order", "eligibility": False, "m5_admitted": False}
                pointer = _read(pointer_path)
                if pointer["schema_version"] not in SCHEMAS:
                    raise ValueError("Unknown pointer schema")
                entries = self._entries(pointer)
                reports = self._verified_reports(entries)
                report = next(row for entry, row in zip(entries, reports) if entry["report_id"] == pointer["report_id"])
                if report["schema_version"] != pointer["schema_version"]:
                    raise ValueError("Observation pointer schema mismatch")
                if self._thread is not None and self._current["session_id"] != report["session_id"]:
                    raise ValueError("Active observation pointer changed")
                try:
                    now = _stamp(self.clock())
                except (TypeError, ValueError):
                    return {**self._view(report), "notification_inbox": {
                        "status": "CLOCK_UNAVAILABLE", "alerts": [], "history": [], "action": "no_order"}}
                inbox = project_notification_inbox(reports, now=now, snapshot_sha256=_sha(_bytes(pointer)))
                # Keep audit event/action identities while withdrawing legacy
                # price-only confirmation credit from the public presentation.
                for event in inbox["history"]:
                    if event["event_type"] == "STRUCTURE_CONFIRMED_OBSERVATION":
                        event.update(audit_event_type=event["event_type"],
                                     event_type="BAR_CONFIRMATION_PENDING", structure_confirmation=False)
                return {**self._view(report), "notification_inbox": inbox}
            except Exception:
                return {"status": "CORRUPT", "monitor_running": self._thread is not None,
                        "detail": "RETAINED_EVIDENCE_VERIFICATION_FAILED", "samples": [],
                        "action": "no_order", "eligibility": False, "m5_admitted": False}

    def transition_notification(self, *, alert_id, operation, expected_snapshot_sha256):
        if operation not in OPERATIONS or not isinstance(expected_snapshot_sha256, str):
            raise ValueError("Observation notification operation invalid")
        with self._mutex:
            if not (self.directory / "current.json").exists():
                raise ValueError("No observation history")
            lock = None
            if self._thread is None:
                lock = InterProcessLock(self.directory / "session.lock", timeout_seconds=.05)
                lock.acquire()
            try:
                view = self.read()
                inbox = view.get("notification_inbox")
                if inbox:
                    pointer = _read(self.directory / "current.json")
                    reports = self._verified_reports(self._entries(pointer))
                    if any(receipt.get("alert_id") == alert_id and receipt.get("operation") == operation
                           and receipt.get("expected_snapshot_sha256") == expected_snapshot_sha256
                           for report in reports for receipt in report.get("notification_actions", [])):
                        return view
                if not inbox or inbox["snapshot_sha256"] != expected_snapshot_sha256:
                    raise ValueError("Observation notification version changed")
                alert = next((row for row in inbox["alerts"] if row["alert_id"] == alert_id), None)
                if alert is None:
                    raise ValueError("Unknown observation notification")
                if alert["status"] == OPERATIONS[operation]:
                    return view
                if operation not in alert["available_operations"]:
                    raise ValueError("Observation notification transition unavailable")
                pointer = _read(self.directory / "current.json")
                if self._thread is None:
                    entries = self._entries(pointer)
                    reports = self._verified_reports(entries)
                    self._current = next(report for entry, report in zip(entries, reports)
                        if entry["report_id"] == pointer["report_id"])
                self._current.setdefault("notification_actions", []).append({
                    "alert_id": alert_id, "operation": operation,
                    "occurred_at": _stamp(self.clock()).isoformat(),
                    "expected_snapshot_sha256": expected_snapshot_sha256})
                self._persist()
                return self.read()
            finally:
                if lock is not None:
                    lock.release()

    def stop(self, *, expected_session_id=None) -> dict:
        with self._mutex:
            if expected_session_id is not None and self.read().get("session_id") != expected_session_id:
                raise ValueError("Observation session changed; refresh before stopping")
            self._stop.set()
            return self.read()

    def close(self) -> None:
        with self._mutex:
            self._closed = True
            self._stop.set()

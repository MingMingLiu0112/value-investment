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
from .intraday_observation import project_intraday_observation
from .intraday_plan_observation import evaluate_quote_plan
from ..portfolio.private_journal_lock import InterProcessLock, LockTimeout
from ...quote_session_collection import collect_session_bundle, resolve_session_reference


SCHEMA = "local-public-observation-session-v1"
PLAN_SCHEMA = "local-public-observation-session-v2"
MAX_BYTES = 8_000_000
AGE = timedelta(seconds=120)


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
    def __init__(self, root: Path, *, clock=None, collector=None,
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
        report_id = str(uuid4())
        raw = _bytes(self._current)
        if len(raw) > MAX_BYTES:
            raise ValueError("Observation report exceeds bounds")
        with (self.directory / (report_id + ".report.json")).open("xb") as stream:
            stream.write(raw)
            stream.flush()
        _atomic_write(self.directory / "current.json",
                      {"schema_version": self._current["schema_version"], "report_id": report_id, "sha256": _sha(raw)})

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
                self._stop = threading.Event()
                self._failure = False
                self._current = {"schema_version": SCHEMA, "session_id": str(uuid4()),
                    "symbol": symbol, "status": "RUNNING", "detail": "LOCAL_PUBLIC_OBSERVATION_ONLY",
                    "samples": [], "bindings": []}
                if plan_binding is not None:
                    self._current.update(schema_version=PLAN_SCHEMA, plan_binding=plan_binding)
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
                try:
                    bundle = deepcopy(self.collector([symbol]))
                    checked = _stamp(self.clock())
                    sample = _sample(bundle, identity=identity, symbol=symbol, checked=checked)
                    raw = _bytes(bundle)
                    if len(raw) > MAX_BYTES:
                        raise ValueError("Collection exceeds bounds")
                    with (self.directory / (identity + ".bundle.json")).open("xb") as stream:
                        stream.write(raw)
                    binding = {"sample_id": identity, "sha256": _sha(raw)}
                except Exception:
                    checked = _stamp(self.clock())
                    sample = {"sample_id": identity, "symbol": symbol, "checked_at": checked.isoformat(),
                              "status": "STALE_OR_UNAVAILABLE", "reason": "COLLECTION_OR_EVIDENCE_FAILED",
                              "source_refs": []}
                    binding = {"sample_id": identity, "sha256": None}
                with self._mutex:
                    if (self._current["samples"] and checked < datetime.fromisoformat(
                            self._current["samples"][-1]["checked_at"])):
                        raise ValueError("Server observation clock regressed")
                    if self._current["schema_version"] == PLAN_SCHEMA:
                        sample["condition_result"] = evaluate_quote_plan(
                            self._current["plan_binding"], sample.get("observation"),
                            previous=(self._current["samples"][-1]["condition_result"]
                                if self._current["samples"] else None), now=checked)
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
        if report["schema_version"] == PLAN_SCHEMA:
            results = [sample["condition_result"] for sample in report["samples"]]
            result.update(plan_binding=deepcopy(report["plan_binding"]),
                condition_observation=deepcopy(results[-1]) if results else None,
                condition_transitions=[deepcopy(item) for batch in results for item in batch["transitions"]])
        return result

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
                if pointer["schema_version"] not in {SCHEMA, PLAN_SCHEMA}:
                    raise ValueError("Unknown pointer schema")
                report = _read(self.directory / (_uuid(pointer["report_id"]) + ".report.json"), pointer["sha256"])
                if (report["schema_version"] != pointer["schema_version"] or report["status"] not in {"RUNNING", "STOPPED", "FAILED"}
                        or not re.fullmatch(r"[0-9]{6}", report["symbol"])
                        or len(report["samples"]) > 10 or len(report["bindings"]) != len(report["samples"])):
                    raise ValueError("Invalid observation report")
                _uuid(report["session_id"])
                if report["schema_version"] == PLAN_SCHEMA:
                    if report["plan_binding"]["symbol"] != report["symbol"]:
                        raise ValueError("Plan security mismatch")
                    evaluate_quote_plan(report["plan_binding"], None, previous=None,
                        now=_stamp(self.clock()))
                ids = set()
                previous = None
                previous_conditions = None
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
                        expected_sample = _sample(bundle, identity=identity, symbol=report["symbol"], checked=checked)
                    else:
                        expected_sample = {"sample_id": identity, "symbol": report["symbol"], "checked_at": checked.isoformat(),
                                    "status": "STALE_OR_UNAVAILABLE", "reason": "COLLECTION_OR_EVIDENCE_FAILED", "source_refs": []}
                    if report["schema_version"] == PLAN_SCHEMA:
                        if report["plan_binding"]["symbol"] != report["symbol"]:
                            raise ValueError("Plan security mismatch")
                        previous_conditions = evaluate_quote_plan(report["plan_binding"], expected_sample.get("observation"),
                            previous=previous_conditions, now=checked)
                        expected_sample["condition_result"] = previous_conditions
                    if expected_sample != sample:
                        raise ValueError("Observation replay mismatch")
                if self._thread is not None and self._current["session_id"] != report["session_id"]:
                    raise ValueError("Active observation pointer changed")
                return self._view(report)
            except Exception:
                return {"status": "CORRUPT", "monitor_running": self._thread is not None,
                        "detail": "RETAINED_EVIDENCE_VERIFICATION_FAILED", "samples": [],
                        "action": "no_order", "eligibility": False, "m5_admitted": False}

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

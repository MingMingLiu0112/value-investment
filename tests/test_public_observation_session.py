"""TEST_ONLY local collection sessions; all collectors injected, no network."""
import base64
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
import threading
import time

import pytest

from test_intraday_observation import NOW, bundle, doc
from value_investment_agent.application.hotspot.public_observation_session import PublicObservationSession
from value_investment_agent.infrastructure.hotspot.sina_price_case import ENDPOINT


def bars(now, value="14"):
    result = {}
    for period in ("60m", "15m"):
        rows = [dict(day="2026-09-28 10:30:00", open=value, high=value,
                     low=value, close=value, volume="100", amount="1400")]
        raw = ("/*TEST_ONLY*/=(" + json.dumps(rows) + ");").encode()
        result[period] = dict(raw_base64=base64.b64encode(raw).decode(),
            sha256=hashlib.sha256(raw).hexdigest(),
            source_url=ENDPOINT + f"?symbol=sh600519&scale={period[:-1]}&ma=no&datalen=8",
            http_status=200, fetched_at=(now - timedelta(seconds=1)).isoformat())
    return result


def wait_stopped(session):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = session.read()
        if not result["monitor_running"]:
            return result
        time.sleep(.005)
    pytest.fail("TEST_ONLY worker did not stop")


def service(tmp_path, collector=None, **kwargs):
    return PublicObservationSession(tmp_path, clock=lambda: NOW,
        collector=collector or (lambda symbols: bundle(symbol=symbols[0])),
        interval_seconds=kwargs.pop("interval_seconds", .001), **kwargs)


def files(root):
    return {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def current_paths(session):
    pointer = session.directory / "current.json"
    data = json.loads(pointer.read_text())
    report = session.directory / (data["report_id"] + ".report.json")
    return pointer, report, json.loads(report.read_text())


def rewrite_report(session, data):
    pointer, path, _ = current_paths(session)
    raw = json.dumps(data).encode()
    path.write_bytes(raw)
    ref = json.loads(pointer.read_text())
    ref["sha256"] = hashlib.sha256(raw).hexdigest()
    pointer.write_text(json.dumps(ref))


def test_read_is_side_effect_free_and_never_starts_collector(tmp_path):
    calls = []
    s = service(tmp_path, collector=lambda symbols: calls.append(symbols))
    before = files(tmp_path)
    assert s.read()["status"] == "NOT_STARTED"
    assert files(tmp_path) == before and not calls
    s.close()
    with pytest.raises(ValueError, match="closed"):
        s.start("600519")


def test_stale_page_cannot_stop_successor_observation_session(tmp_path):
    s = service(tmp_path, max_samples=1)
    old = s.start("600519")["session_id"]
    wait_stopped(s)
    entered, release = threading.Event(), threading.Event()
    def collect(symbols):
        entered.set()
        assert release.wait(3)
        return bundle(symbol=symbols[0])
    s.collector = collect
    current = s.start("600519")["session_id"]
    try:
        assert entered.wait(2) and old != current
        with pytest.raises(ValueError, match="session changed"):
            s.stop(expected_session_id=old)
        assert not s._stop.is_set() and s.read()["monitor_running"]
        assert s.stop(expected_session_id=current)["status"] == "STOPPING"
    finally:
        release.set()
        wait_stopped(s)
        s.close()


def test_bound_plan_crossings_persist_replay_and_reject_rewritten_history(tmp_path):
    from test_current_price_registry import register
    from test_hotspot_current_price_case import NOW as BOUND_AT
    from test_intraday_plan_observation import NOW as PLAN_NOW
    from test_intraday_observation import field
    from value_investment_agent.application.hotspot.current_registry import load_price_conditions
    from value_investment_agent.application.hotspot.intraday_plan_observation import bind_quote_plan
    register(tmp_path)
    plan = load_price_conditions(tmp_path, now=BOUND_AT, research_version="TEST_ONLY")["items"][0]["price_action_plan"]
    binding = bind_quote_plan(plan, symbol="600519", now=BOUND_AT)
    values = iter(["14", "14", "10"])
    at = [PLAN_NOW]
    def collector(symbols):
        at[0] += timedelta(seconds=1)
        data = bundle(now=at[0])
        price = next(values)
        field(data, "tencent", 3, price)
        field(data, "sina", 3, price)
        return data
    s = PublicObservationSession(tmp_path, clock=lambda: at[0], collector=collector,
        bar_collector=lambda symbol: bars(at[0]),
        max_samples=3, interval_seconds=.001)
    try:
        s.start("600519", plan_binding=binding)
        result = wait_stopped(s)
        assert result["status"] == "STOPPED"
        assert result["condition_observation"]["binding_sha256"] == binding["binding_sha256"]
        assert result["samples"][1]["condition_result"]["transitions"] == []
        assert all(item["m5_admitted"] is False for item in result["condition_transitions"])
        assert result["condition_observation"]["states"][1]["status"] == "RISK_REVIEW"
        restored = PublicObservationSession(tmp_path, clock=lambda: at[0])
        assert restored.read() == result
        _, _, report = current_paths(s)
        report["samples"][0]["condition_result"]["states"][0]["condition"]["threshold"] = "999"
        rewrite_report(s, report)
        assert restored.read()["status"] == "CORRUPT"
        restored.close()
    finally:
        s.close()


@pytest.mark.parametrize("symbol", ["600519", "000333"])
def test_real_contract_bounded_storage_replay_and_restart(tmp_path, symbol):
    calls = []
    def collect(symbols):
        calls.append(symbols)
        return bundle(symbol=symbols[0])
    s = service(tmp_path, collector=collect)
    try:
        started = s.start(symbol)
        assert started["monitor_running"] and started["status"] == "RUNNING"
        result = wait_stopped(s)
        assert result["status"] == "STOPPED" and len(result["samples"]) == 10
        assert calls == [[symbol]] * 10
        assert result["action"] == "no_order" and result["eligibility"] is False and result["m5_admitted"] is False
        assert len({sample["sample_id"] for sample in result["samples"]}) == 10
        for sample in result["samples"]:
            assert sample["status"] == "QUOTE_VERIFIED" and len(sample["source_refs"]) == 2
            assert sample["observation"]["admitted"] is False
        before = files(tmp_path)
        result["samples"][0]["observation"]["price"] = "mutated return"
        assert s.read()["samples"][0]["observation"]["price"] == "60"
        assert files(tmp_path) == before
        restored = service(tmp_path)
        assert restored.read() == s.read()
        assert len(list(s.directory.glob("*.bundle.json"))) == 10
        restored.close()
        # Explicit restart is allowed and never overwrites old immutable artifacts.
        s.start(symbol)
        assert len(wait_stopped(s)["samples"]) == 10
        assert len(list(s.directory.glob("*.bundle.json"))) == 20
        assert not any("m5" in str(path).lower() for path in tmp_path.rglob("*"))
    finally:
        s.close()


def test_stop_in_flight_is_truthful_and_close_prevents_another_request(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def collect(symbols):
        calls.append(symbols)
        entered.set()
        assert release.wait(3)
        return bundle()
    s = service(tmp_path, collector=collect)
    try:
        s.start("600519")
        assert entered.wait(2)
        with pytest.raises(ValueError, match="already"):
            s.start("000333")
        result = s.stop()
        assert result["status"] == "STOPPING" and result["monitor_running"]
        other = service(tmp_path)
        with pytest.raises(ValueError, match="Another"):
            other.start("600519")
        s.close()
        release.set()
        final = wait_stopped(s)
        assert len(final["samples"]) == 1 and calls == [["600519"]]
        with pytest.raises(ValueError, match="closed"):
            s.start("600519")
        other.start("600519")
        assert wait_stopped(other)["status"] == "STOPPED"
        other.close()
    finally:
        release.set()
        s.close()


def test_stop_interrupts_wait_not_new_request(tmp_path):
    completed = threading.Event()
    calls = []
    def collect(symbols):
        calls.append(symbols)
        completed.set()
        return bundle()
    s = service(tmp_path, collector=collect, interval_seconds=60)
    s.start("600519")
    assert completed.wait(2)
    s.stop()
    assert wait_stopped(s)["status"] == "STOPPED"
    assert len(calls) == 1
    s.close()


def test_outside_session_retains_one_negative_then_stops(tmp_path):
    closed = NOW.replace(hour=12)
    calls = []
    def collect(symbols):
        calls.append(symbols)
        return bundle(now=closed)
    s = PublicObservationSession(tmp_path, clock=lambda: closed, collector=collect, interval_seconds=.001)
    s.start("600519")
    final = wait_stopped(s)
    assert len(calls) == len(final["samples"]) == 1
    assert final["samples"][0]["reason"] == "OUTSIDE_EXCHANGE_SESSION"
    assert "observation" not in final["samples"][0]
    s.close()


@pytest.mark.parametrize("failure", ["network", "hash", "future", "stale", "price_conflict", "unsafe_url"])
def test_failures_explicit_no_trigger_or_secret_leak(tmp_path, failure):
    data = bundle()
    if failure == "hash":
        doc(data)["raw_base64"] = "corrupt"
    elif failure == "future":
        data = bundle(now=NOW + timedelta(hours=1))
    elif failure == "stale":
        data = bundle(now=NOW - timedelta(minutes=3))
    elif failure == "price_conflict":
        from test_intraday_observation import field
        field(data, "sina", 3, "61")
    elif failure == "unsafe_url":
        doc(data)["source_url"] = "https://secret:password@qt.gtimg.cn/q=sh600519"
    def collect(symbols):
        if failure == "network":
            raise RuntimeError("credential=DO_NOT_EXPOSE")
        return deepcopy(data)
    s = service(tmp_path, collector=collect, max_samples=1)
    s.start("600519")
    final = wait_stopped(s)
    assert final["status"] == "STOPPED"
    sample = final["samples"][0]
    assert sample["status"] == "STALE_OR_UNAVAILABLE" and "observation" not in sample
    assert "password" not in json.dumps(final) and "DO_NOT_EXPOSE" not in json.dumps(final)
    s.close()


@pytest.mark.parametrize("target", ["pointer", "report", "bundle", "missing_bundle", "oversized"])
def test_corrupt_retained_artifacts_fail_closed_without_writing(tmp_path, target):
    s = service(tmp_path, max_samples=1)
    s.start("600519")
    wait_stopped(s)
    pointer, report, data = current_paths(s)
    raw = s.directory / (data["samples"][0]["sample_id"] + ".bundle.json")
    if target == "pointer":
        pointer.write_text("not JSON")
    elif target == "report":
        report.write_text("{}")
    elif target == "bundle":
        raw.write_text("{}")
    elif target == "missing_bundle":
        raw.unlink()
    else:
        with raw.open("wb") as stream:
            stream.truncate(8_000_001)
    before = files(tmp_path)
    result = s.read()
    assert result["status"] == "CORRUPT" and not result["samples"]
    assert files(tmp_path) == before
    s.close()


@pytest.mark.parametrize("change", ["price", "refs", "symbol", "traversal", "raw_rehashed"])
def test_rehashed_report_cannot_forge_verified_observation(tmp_path, change):
    s = service(tmp_path, max_samples=1)
    s.start("600519")
    wait_stopped(s)
    _, _, report = current_paths(s)
    if change == "price":
        report["samples"][0]["observation"]["price"] = "999"
    elif change == "refs":
        report["samples"][0]["source_refs"] = []
    elif change == "symbol":
        report["symbol"] = "000333"
    elif change == "traversal":
        report["samples"][0]["sample_id"] = "../../outside"
    else:
        path = s.directory / (report["samples"][0]["sample_id"] + ".bundle.json")
        data = json.loads(path.read_text())
        doc(data)["raw_base64"] = "Zm9yZ2Vk"
        raw = json.dumps(data).encode()
        path.write_bytes(raw)
        report["bindings"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
    rewrite_report(s, report)
    assert s.read()["status"] == "CORRUPT"
    s.close()


def test_worker_clock_failure_visible_and_releases_lock(tmp_path):
    s = PublicObservationSession(tmp_path, clock=lambda: NOW.replace(tzinfo=None),
                                 collector=lambda symbols: bundle(), max_samples=1)
    s.start("600519")
    assert wait_stopped(s)["status"] == "FAILED"
    other = service(tmp_path, max_samples=1)
    other.start("600519")
    assert wait_stopped(other)["status"] == "STOPPED"
    s.close()
    other.close()


def test_worker_abrupt_exit_is_visible_and_cannot_silently_stop(tmp_path):
    def collect(symbols):
        raise SystemExit("TEST_ONLY worker termination")
    s = service(tmp_path, collector=collect, max_samples=1)
    s.start("600519")
    result = wait_stopped(s)
    assert result["status"] == "FAILED" and not result["monitor_running"]
    assert "termination" not in str(result)
    s.close()


def test_worker_storage_failure_visible(tmp_path, monkeypatch):
    s = service(tmp_path, max_samples=1)
    entered, release = threading.Event(), threading.Event()
    def collect(symbols):
        entered.set()
        assert release.wait(3)
        return bundle()
    s.collector = collect
    s.start("600519")
    assert entered.wait(2)
    def broken():
        raise OSError("secret storage path")
    monkeypatch.setattr(s, "_persist", broken)
    release.set()
    final = wait_stopped(s)
    assert final["status"] == "FAILED" and "secret" not in str(final)
    s.close()


@pytest.mark.parametrize("kwargs", [{"max_samples": 11}, {"max_samples": 0}, {"max_samples": True},
    {"interval_seconds": 0}, {"interval_seconds": float("nan")}, {"interval_seconds": True}])
def test_invalid_bounds_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        PublicObservationSession(tmp_path, **kwargs)


def test_invalid_symbol_does_not_write(tmp_path):
    s = service(tmp_path)
    with pytest.raises(ValueError):
        s.start("../600519")
    assert not list(tmp_path.iterdir())


def test_whole_session_lock_blocks_another_process(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def collect(symbols):
        entered.set()
        assert release.wait(5)
        return bundle()
    s = service(tmp_path, collector=collect, max_samples=1)
    s.start("600519")
    try:
        assert entered.wait(2)
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        code = (
            "from pathlib import Path\n"
            "from value_investment_agent.application.portfolio.private_journal_lock import InterProcessLock, LockTimeout\n"
            "import sys\n"
            "try:\n"
            "    with InterProcessLock(Path(sys.argv[1]), timeout_seconds=.05):\n"
            "        sys.exit(2)\n"
            "except LockTimeout:\n"
            "    sys.exit(0)\n"
        )
        result = subprocess.run([sys.executable, "-c", code, str(s.directory / "session.lock")],
                                env=env, capture_output=True, timeout=4)
        assert result.returncode == 0, result.stderr.decode()
    finally:
        s.stop()
        release.set()
        wait_stopped(s)
        s.close()


def test_concurrent_start_only_admits_one_worker(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls, results = [], []
    barrier = threading.Barrier(3)
    def collect(symbols):
        calls.append(symbols)
        entered.set()
        assert release.wait(3)
        return bundle()
    s = service(tmp_path, collector=collect, max_samples=1)
    def start():
        barrier.wait()
        try:
            results.append(s.start("600519")["status"])
        except ValueError:
            results.append("CONFLICT")
    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(2)
    try:
        assert sorted(results) == ["CONFLICT", "RUNNING"]
        assert entered.wait(2)
    finally:
        s.close()
        release.set()
        wait_stopped(s)
    assert len(calls) == 1


def test_default_collector_and_freshness_contract(tmp_path, monkeypatch):
    import value_investment_agent.application.hotspot.public_observation_session as module
    calls, ages = [], []
    def collect(symbols):
        calls.append(symbols)
        return bundle()
    original = module.project_intraday_observation
    def project(data, **kwargs):
        ages.append(kwargs["max_age"])
        return original(data, **kwargs)
    monkeypatch.setattr(module, "collect_session_bundle", collect)
    monkeypatch.setattr(module, "project_intraday_observation", project)
    s = PublicObservationSession(tmp_path, clock=lambda: NOW, max_samples=1)
    assert s.interval == 60
    s.start("600519")
    assert wait_stopped(s)["samples"][0]["status"] == "QUOTE_VERIFIED"
    assert calls == [["600519"]] and set(ages) == {timedelta(seconds=120)}
    s.close()


def test_source_clock_regression_fails_worker_instead_of_committing_bad_history(tmp_path):
    at = [NOW]
    calls = []
    def collector(symbols):
        calls.append(symbols)
        at[0] = NOW if len(calls) == 1 else NOW - timedelta(seconds=1)
        return bundle()
    s = PublicObservationSession(tmp_path, clock=lambda: at[0], collector=collector,
                                 max_samples=2, interval_seconds=.001)
    s.start("600519")
    result = wait_stopped(s)
    assert result["status"] == "FAILED" and len(result["samples"]) == 1
    s.close()

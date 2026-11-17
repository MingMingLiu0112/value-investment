"""Synthetic source binding and explicit opt-in real source replay."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

import test_official_dividend_split_receipt_v2 as captures
from test_official_dividend_split_receipt_v2 import _source_mode
from test_operating_horizon_task_v10_live import task
from test_operating_horizon_split_v8 import split_context
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import (
    operating_q3_issuer_dividend_split_loader_v9_600519 as loader,
    operating_horizon_task_v15_live as v15,
)

NOW = datetime.fromisoformat("2026-11-12T12:00:00+08:00")
REAL_ROOT = os.environ.get("DIVIDEND_SPLIT_PROJECT_ROOT")


@pytest.fixture
def prepared(task, monkeypatch):
    old, original, _ = task
    root = old.root
    directory = root / loader.CAPTURE_DIR
    directory.mkdir(parents=True)
    for aid in loader.IDS:
        for suffix in loader.SUFFIXES:
            shutil.copyfile(captures.EVIDENCE / (aid + suffix), directory / (aid + suffix))
    base = deepcopy(original)
    base["as_of"] = NOW.isoformat()
    def v8_source(*, root, symbol, now, binding=None):
        if symbol != "600519" or binding not in (None, original["source_binding"]):
            raise ValueError("TEST_V8_BINDING_CHANGED")
        return deepcopy(base)
    monkeypatch.setattr(loader.prior, "load_current", v8_source)
    return root, base


def test_three_historical_rows_and_v8_projection(prepared):
    root, base = prepared
    result = loader.load_current(root=root, symbol="600519", now=NOW)
    assert loader.load_current(root=root, symbol="600519", now=NOW,
        binding=result["source_binding"]) == result
    assert base["source_binding"] == result["source_binding"]["base"]
    assert result["schema_version"] == loader.prior.VERSION
    assert result.get("prior_source_binding") == base.get("prior_source_binding")
    assert result["evidence"][:len(base["evidence"])] == base["evidence"]
    assert [row["period"] for row in result["evidence"][-3:]] == list(loader.PERIOD_ENDS)
    assert [row["period_basis"] for row in result["evidence"][-3:]] == list(loader.PERIODS)
    assert all("2027" in row["text"] and "不证明" in row["text"]
               for row in result["evidence"][-3:])
    assert result["source_binding"]["implementation_sha256"] == loader.implementation()
    projected = v15.official.project_research_context(result)
    assert [row["id"] for row in projected["evidence"][-3:]] == [
        row["id"] for row in result["evidence"][-3:]]
    assert result["action"] == "no_order" and result["formal_eligibility"] is False


def test_v15_test_only_create_and_read_with_injected_loader(prepared):
    root, base = prepared
    calls = []
    service = v15.OperatingHorizonTaskService(root, source_loader=loader.load_current,
        source_loader_version=loader.VERSION,
        test_provider=SimpleNamespace(complete=lambda request: calls.append(request)))
    queued = service.create(symbol="600519", request_key="TEST_V9_SPLIT", years=[2027], now=NOW)
    spec, state, _ = service._load(queued["task_id"])
    assert spec["source_loader_binding"]["version"] == loader.VERSION
    assert spec["source_binding"]["base"] == base["source_binding"]
    assert spec["source_binding"]["implementation_sha256"] == loader.implementation()
    assert service.read(queued["task_id"])["status"] == "QUEUED"
    assert state["provider_requests"] == 0 and calls == []


@pytest.mark.parametrize("aid", loader.IDS)
@pytest.mark.parametrize("key", loader.KEYS)
def test_changed_each_capture_fails_closed(prepared, aid, key):
    root, _ = prepared
    binding = loader.load_current(root=root, symbol="600519", now=NOW)["source_binding"]
    entry = next(row for row in binding["split"] if row["announcement_id"] == aid)
    path = root / entry["files"][key]["path"]
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="V9_SPLIT_BYTES_CHANGED"):
        loader.load_current(root=root, symbol="600519", now=NOW, binding=binding)


def test_future_and_old_binding_rejected(prepared):
    root, base = prepared
    with pytest.raises(ValueError, match="SPLIT_NOT_AVAILABLE_AS_OF"):
        loader.load_current(root=root, symbol="600519", now=NOW - timedelta(days=1))
    with pytest.raises(ValueError, match="V9_SPLIT_BINDING_INVALID"):
        loader.load_current(root=root, symbol="600519", now=NOW,
            binding=base["source_binding"])


@pytest.mark.skipif(not REAL_ROOT, reason="set DIVIDEND_SPLIT_PROJECT_ROOT explicitly")
def test_explicit_real_project_root_replays_all_three():
    root = Path(REAL_ROOT).resolve()
    assert (root / loader.CAPTURE_DIR).is_dir()
    result = loader.load_current(root=root, symbol="600519", now=NOW)
    assert [row["period"] for row in result["evidence"][-3:]] == list(loader.PERIOD_ENDS)
    assert loader.load_current(root=root, symbol="600519", now=NOW,
        binding=result["source_binding"]) == result


@pytest.mark.skipif(not captures.REAL_ROOT,
                    reason="set DIVIDEND_SPLIT_EVIDENCE_ROOT explicitly")
def test_explicit_real_capture_root_through_v8_adapter(prepared):
    # prepared copies the 12 unmodified files from the opt-in evidence root
    # into ignored, root-local runtime; the official reader remains unmocked.
    root, _ = prepared
    result = loader.load_current(root=root, symbol="600519", now=NOW)
    assert [row["pdf_sha256"] for row in result["evidence"][-3:]] == [
        captures.EXPECTED[aid][-1] for aid in loader.IDS]
    assert loader.load_current(root=root, symbol="600519", now=NOW,
        binding=result["source_binding"]) == result

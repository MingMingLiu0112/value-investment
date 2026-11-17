"""Income-input revalidation must propagate readonly through every nested extraction."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from test_income_source_correlation_integration import correlated_income, income_inputs, balance_inputs, source, NOW
from value_investment_agent.application.research import income_source_correlation as income
from value_investment_agent.application.research import value_evidence_enrichment_v1 as enrichment
from value_investment_agent.infrastructure.screening.value_evidence_enrichment_v1 import RetainedAnnualSource


@contextmanager
def forbid_writes_and_network():
    def denied(*args, **kwargs):
        raise AssertionError("Readonly income replay attempted write/network")
    with patch.object(Path, "mkdir", denied), patch.object(Path, "write_bytes", denied),          patch.object(Path, "write_text", denied), patch.object(requests.sessions.Session, "request", denied):
        yield


def snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(),p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def copy_originals(old, target, official, secondary):
    paths = [official.path, secondary["path"], secondary["receipt"]["path"]]
    for relative in paths:
        path = target / relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((old/relative).read_bytes())


@pytest.mark.parametrize("entry", ["correlate", "reverify", "enrich", "consume"])
def test_income_input_empty_cache_never_attempts_write(tmp_path, correlated_income, entry):
    official, _, points, secondary, _ = correlated_income
    root = tmp_path / "cold-replay"
    copy_originals(tmp_path,root,official,secondary)
    assert points and all(p["data_point_id"].startswith("income-input:") for p in points)
    assert not (root/".tmp").exists()
    before = snapshot(root)
    with forbid_writes_and_network():
        if entry == "correlate":
            assert income.correlate_income_inputs(root,official,secondary,evaluation_at=NOW,write_cache=False) == points
        elif entry == "reverify":
            income.reverify_income_inputs(root,official,points,evaluation_at=NOW,write_cache=False)
        elif entry == "enrich":
            result = enrichment.enrich_retained_company(root,official,points,evaluation_at=NOW,
                cache_dir=root/".tmp/cold",write_cache=False)
            assert {p["field_name"] for p in result["adopted_points"]} >= {"revenue_yoy","net_income_yoy"}
        else:
            merged, reports = enrichment.consume_retained_enrichment(root,points,[asdict(official)],
                evaluation_at=NOW,write_cache=False)
            assert reports and {p["field_name"] for p in merged} >= {"revenue_yoy","net_income_yoy"}
    assert not (root/".tmp").exists() and snapshot(root) == before
    # Omitting the option retains the original cache-writing behavior and exact points.
    assert income.correlate_income_inputs(root,official,secondary,evaluation_at=NOW) == points
    assert list((root/".tmp/value-enrichment-extraction").glob("*.json"))


def test_income_readonly_does_not_weaken_secondary_hash(tmp_path, correlated_income):
    official, _, points, secondary, _ = correlated_income
    root = tmp_path/"cold-invalid"
    copy_originals(tmp_path,root,official,secondary)
    path = root/secondary["path"]
    path.write_bytes(path.read_bytes()+b" ")
    before = snapshot(root)
    with forbid_writes_and_network(), pytest.raises(ValueError,match="backing hash mismatch"):
        enrichment.enrich_retained_company(root,official,points,evaluation_at=NOW,
            cache_dir=root/".tmp/cold",write_cache=False)
    assert snapshot(root) == before and not (root/".tmp").exists()


def test_real_600323_income_points_empty_cache_readonly(tmp_path):
    configured = os.environ.get("INCOME_COMPARATIVE_REAL_ROOT")
    if not configured:
        if os.environ.get("INCOME_COMPARATIVE_REAL_REQUIRED") == "1":
            pytest.fail("INCOME_COMPARATIVE_REAL_ROOT required")
        pytest.skip("Explicit original root required; no real acceptance without it")
    original_root = Path(configured)
    base = Path("runtime/sse-value-research/sse-research-20261102T122836/queue-inputs/enrichment")
    official_receipt_path = original_root/base/"600323-official-original/receipt.json"
    acquired_path = original_root/base/"600323-income-original/acquisition.json"
    official = RetainedAnnualSource(**json.loads(official_receipt_path.read_bytes())["source"])
    acquired = json.loads(acquired_path.read_bytes())
    secondary = {k: acquired[k] for k in ("path","sha256","acquired_at")}
    secondary.update(source_url=acquired["url"],receipt=dict(
        path=acquired_path.relative_to(original_root).as_posix(),
        sha256=hashlib.sha256(acquired_path.read_bytes()).hexdigest()))
    originals = [official_receipt_path, acquired_path, original_root/official.path, original_root/secondary["path"]]
    original_before = {p:(p.read_bytes(),p.stat().st_mtime_ns) for p in originals}
    copy_originals(original_root,tmp_path,official,secondary)
    now = datetime(2026,11,3,tzinfo=timezone.utc)
    before = snapshot(tmp_path)
    assert not (tmp_path/".tmp").exists()
    with forbid_writes_and_network():
        points = income.correlate_income_inputs(tmp_path,official,secondary,evaluation_at=now,write_cache=False)
        assert len(points) == 4 and all(p["data_point_id"].startswith("income-input:") for p in points)
        merged,reports = enrichment.consume_retained_enrichment(tmp_path,points,[asdict(official)],
            evaluation_at=now,write_cache=False)
        assert {p["field_name"] for p in merged} >= {"revenue_yoy","net_income_yoy"}
        assert reports[0]["formal_eligibility"] is False
    assert snapshot(tmp_path) == before and not (tmp_path/".tmp").exists()
    assert original_before == {p:(p.read_bytes(),p.stat().st_mtime_ns) for p in originals}
    default = enrichment.consume_retained_enrichment(tmp_path,points,[asdict(official)],evaluation_at=now)
    assert default == (merged,reports)
    assert list((tmp_path/".tmp/value-enrichment-extraction").glob("*.json"))

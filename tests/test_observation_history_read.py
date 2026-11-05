"""Public history must replay sources and never publish arbitrary receipt fields."""
from datetime import date, datetime
import hashlib
import json

import pytest

from test_current_price_registry import register
from test_hotspot_current_price_case import NOW
from value_investment_agent.application.hotspot.observation_continuity import compare_observation_continuity
from value_investment_agent.application.product.daily_refresh import read_observation_changes


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return dict(path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def registered_history(root):
    register(root)
    pointer = root / "config/current-price-conditions.json"
    registry = json.loads(pointer.read_bytes())
    watch = root / "runtime/watch.json"
    write(watch, dict(schema_version="hotspot-observation-report-v1", action="no_order",
        dated_quote_observations=[dict(symbol="600519", quote_date="2026-09-24",
            status="DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION")]))
    registry["watch_source_binding"]["sha256"] = hashlib.sha256(watch.read_bytes()).hexdigest()
    folder = root / "runtime/hotspot-current-refresh/TEST_ONLY"
    snapshot = folder / "registry-snapshot.json"
    write(snapshot, registry)
    binding = dict(path=snapshot.relative_to(root).as_posix(), sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest())
    result = compare_observation_continuity(root=root, current_binding=binding,
        previous_binding=None, completed_session=date(2026, 9, 24), now=NOW)
    receipt = folder / "observation-continuity.json"
    write(receipt, result)
    registry["observation_continuity"] = dict(status="SOURCE_BOUND_OBSERVATION_ONLY",
        path=receipt.relative_to(root).as_posix(), sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())
    write(pointer, registry)
    return pointer, receipt, watch


def test_source_replayed_public_history(tmp_path):
    registered_history(tmp_path)
    result = read_observation_changes(tmp_path, now=NOW)
    assert result["status"] == "SOURCE_REVALIDATED"
    assert result["formal_eligibility"] is False
    assert result["items"][0]["symbol"] == "600519"
    assert "observation" not in result["items"][0]


@pytest.mark.parametrize("mutation", ["source", "receipt", "forged_rehash", "pointer", "future"])
def test_changes_reject_stale_or_forged_bindings(tmp_path, mutation):
    pointer, receipt, watch = registered_history(tmp_path)
    now = NOW
    if mutation == "source":
        watch.write_bytes(watch.read_bytes() + b" ")
    elif mutation == "pointer":
        registry = json.loads(pointer.read_bytes())
        registry["items"][0]["company_name"] = "changed"
        write(pointer, registry)
    elif mutation == "future":
        now = datetime(2026, 9, 24, tzinfo=NOW.tzinfo)
    else:
        value = json.loads(receipt.read_bytes())
        value["items"][0]["transition"] = "triggered"
        value["private_account"] = "must not leak"
        write(receipt, value)
        if mutation == "forged_rehash":
            registry = json.loads(pointer.read_bytes())
            registry["observation_continuity"]["sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
            write(pointer, registry)
    result = read_observation_changes(tmp_path, now=now)
    assert result["status"] == "UNAVAILABLE" and result["items"] == []
    assert "must not leak" not in json.dumps(result)


def test_malformed_previous_registry_and_wrong_publication_degrade_safely(tmp_path):
    pointer, receipt, _ = registered_history(tmp_path)
    assert read_observation_changes(tmp_path, now=NOW, expected_registry_sha256="f" * 64)["status"] == "UNAVAILABLE"
    write(receipt.with_name("previous-registry.json"), [])
    assert read_observation_changes(tmp_path, now=NOW)["status"] == "UNAVAILABLE"


def test_registry_replacement_during_replay_cannot_be_published(tmp_path, monkeypatch):
    from value_investment_agent.application.hotspot import observation_continuity as service
    pointer, _, _ = registered_history(tmp_path)
    original = service.compare_observation_continuity
    def replacing(**kwargs):
        result = original(**kwargs)
        pointer.write_bytes(pointer.read_bytes() + b" ")
        return result
    monkeypatch.setattr(service, "compare_observation_continuity", replacing)
    assert read_observation_changes(tmp_path, now=NOW)["status"] == "UNAVAILABLE"

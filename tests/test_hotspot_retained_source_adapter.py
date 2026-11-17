"""Isolated adapter mechanics plus an optional real retained-original replay."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from value_investment_agent.application.hotspot import retained_source_replay as adapter
from value_investment_agent.application.hotspot import validation_evidence
from test_hotspot_event_replay import bars, spec, trigger
from test_hotspot_review_handoff import synthetic_validation_report


NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def write(root, name, value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return dict(path=name, sha256=sha256(raw).hexdigest())


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """The case-verifier seam is synthetic; domain signal replay remains real."""
    def load(*, root, symbol, case_path, expected_sha256, now):
        raw = (root / case_path).read_bytes()
        assert sha256(raw).hexdigest() == expected_sha256
        result = json.loads(raw)
        assert result["symbol"] == symbol
        assert now.isoformat() == "2026-07-10T16:25:00+08:00"
        return result

    monkeypatch.setattr(adapter, "load_current_price_case", load)

    def make(namespace="TEST_ONLY", values=None):
        values = deepcopy(values or bars())
        if not any(row["close"] == "12" for row in values["60m"]):
            trigger(values, "2026-07-01 10:30:00")
        cases = []
        for index in range(5):
            symbol = f"60000{index}"
            folder = f"runtime/hotspot-current-price-cases/{symbol}-isolated"
            sources = {period: dict(**write(tmp_path, f"{folder}/sina-{period}.jsonp", b"isolated raw"),
                fetched_at="2026-07-10T16:25:00+08:00") for period in ("60m", "15m")}
            sources["daily"] = sources["60m"]
            bundle = dict(namespace=namespace, finished_at="2026-07-10T16:20:00+08:00",
                references={symbol: dict(document_refs=dict(tencent="t", sina="s", calendar_documents=["c"]))},
                documents={key: dict(fetched_at="2026-07-10T16:15:00+08:00") for key in ("t", "s", "c")})
            quote = write(tmp_path, f"runtime/quote/{symbol}.json", bundle)
            binding = write(tmp_path, f"{folder}/case.json", dict(namespace=namespace, symbol=symbol,
                market_trade_date="2026-07-10", bars=values, source_bindings=sources,
                current_reference_close=dict(bundle_path=quote["path"], bundle_sha256=quote["sha256"])))
            cases.append(dict(symbol=symbol, case_path=binding["path"], case_sha256=binding["sha256"]))
        rules = [write(tmp_path, name, Path(module.__file__).read_bytes())
                 for name, module in adapter.FROZEN_RULES.items()]
        selection = write(tmp_path, "config/current-price-conditions.json", dict(items=[]))
        protocol = spec() | dict(namespace=namespace, registered_at="2026-07-11T00:00:00+08:00",
            cases=cases, rule_bindings=rules, selection_binding=selection)
        binding = write(tmp_path, "artifacts/frozen-protocol.json", protocol)
        # Deliberately advance the live pointer, reproducing the audited failure.
        write(tmp_path, selection["path"], dict(items=[], changed=True))
        return binding

    return make


def retain(root, binding, namespace="TEST_ONLY", now=NOW):
    return adapter.retain_hotspot_descriptive_sources(root=root, protocol_binding=binding,
        namespace=namespace, now=now)


def test_snapshot_survives_live_source_removal_and_keeps_historical_hash(isolated, tmp_path):
    historical = isolated()
    before = (tmp_path / historical["path"]).read_bytes()
    with pytest.raises(ValueError, match="hash mismatch.*current-price"):
        validation_evidence.build_hotspot_quantitative_validation(root=tmp_path,
            protocol_binding=historical, now=NOW)
    binding = retain(tmp_path, historical)
    assert (tmp_path / historical["path"]).read_bytes() == before
    manifest = json.loads((tmp_path / binding["path"]).read_bytes())
    for row in manifest["files"]:
        original, copy = row["original_binding"], row["retained_binding"]
        assert (tmp_path / original["path"]).read_bytes() == (tmp_path / copy["path"]).read_bytes()
        (tmp_path / original["path"]).unlink()
    report = validation_evidence.build_hotspot_quantitative_validation(root=tmp_path,
        protocol_binding=binding, now=NOW)
    assert report["historical_protocol_binding"] == historical
    assert report["namespace"] == "TEST_ONLY" and report["scope"] == "DESCRIPTIVE"
    assert report["metrics_scope"] == "SIGNAL_PRICE_PATH_ONLY"
    assert report["signal_event_count"] > 0
    assert report["trade_count"] is report["execution_metrics"]["trade_count"] is None
    assert report["execution_metrics"]["cost_sensitivity"] is None
    assert report["historical_selection_status"] == "NOT_REVALIDATED_RETAINED_CASES_ONLY"
    assert report["strict_oos_admitted"] is report["formal_eligibility"] is False
    assert report["evidence_sha256"] == validation_evidence._recomputed_digest(report, "evidence_sha256")
    assert all(row["source_verification_at"] == "2026-07-10T16:25:00+08:00" for row in report["results"])
    assert all(sha256((tmp_path / b["path"]).read_bytes()).hexdigest() == b["sha256"]
               for b in report["source_bindings"])


def test_repeated_retention_is_append_only(isolated, tmp_path):
    historical = isolated()
    first = retain(tmp_path, historical)
    second = retain(tmp_path, historical)
    assert first["path"] != second["path"]
    assert sha256((tmp_path / first["path"]).read_bytes()).hexdigest() == first["sha256"]


@pytest.mark.parametrize("running_eol,archived_eol", [(b"\n", b"\r\n"), (b"\r\n", b"\n")])
def test_running_rules_allow_only_checkout_newline_difference(isolated, tmp_path, monkeypatch,
                                                            running_eol, archived_eol):
    historical = isolated()
    protocol = json.loads((tmp_path / historical["path"]).read_bytes())
    running_rules = {}
    for index, (name, module) in enumerate(adapter.FROZEN_RULES.items()):
        source = Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")
        running = tmp_path / f"running-rule-{index}.py"
        running.write_bytes(source.replace(b"\n", running_eol))
        running_rules[name] = SimpleNamespace(__file__=str(running))
        archived = write(tmp_path, name, source.replace(b"\n", archived_eol))
        protocol["rule_bindings"][index] = archived
        assert sha256(running.read_bytes()).hexdigest() != archived["sha256"]
    monkeypatch.setattr(adapter, "FROZEN_RULES", running_rules)
    historical = write(tmp_path, historical["path"], protocol)
    retained = retain(tmp_path, historical)
    report = adapter.build_retained_descriptive_validation(root=tmp_path,
        manifest_binding=retained, now=NOW)
    assert report["signal_event_count"] > 0
    assert report["rule_identity_scope"] == "ARCHIVE_RAW_SHA256_EXACT_RUNNING_PYTHON_CRLF_TO_LF_ONLY"
    assert report["trade_count"] is None and report["formal_eligibility"] is False


@pytest.mark.parametrize("change", [b" ", b"\r", b"# changed rule\n", b"\xef\xbb\xbf"])
def test_running_rule_non_newline_changes_rejected(isolated, tmp_path, monkeypatch, change):
    historical = isolated()
    retained = retain(tmp_path, historical)
    name, module = next(iter(adapter.FROZEN_RULES.items()))
    running = tmp_path / "altered-rule.py"
    running.write_bytes(Path(module.__file__).read_bytes().replace(b"\r\n", b"\n") + change)
    monkeypatch.setattr(adapter, "FROZEN_RULES", {
        **adapter.FROZEN_RULES, name: SimpleNamespace(__file__=str(running))})
    with pytest.raises(ValueError, match="Running rule differs"):
        retain(tmp_path, historical)
    with pytest.raises(ValueError, match="Running rule differs"):
        adapter.build_retained_descriptive_validation(root=tmp_path, manifest_binding=retained, now=NOW)


def test_archive_rule_newline_change_still_fails_raw_hash(isolated, tmp_path):
    retained = retain(tmp_path, isolated())
    manifest = json.loads((tmp_path / retained["path"]).read_bytes())
    rule = next(row for row in manifest["files"] if row["original_binding"]["path"].endswith(".py"))
    path = tmp_path / rule["retained_binding"]["path"]
    raw = path.read_bytes()
    changed = raw.replace(b"\r\n", b"\n") if b"\r\n" in raw else raw.replace(b"\n", b"\r\n")
    assert changed != raw
    path.write_bytes(changed)
    with pytest.raises(ValueError, match="hash mismatch"):
        adapter.build_retained_descriptive_validation(root=tmp_path, manifest_binding=retained, now=NOW)


def test_public_export_preserves_bytes_and_replays_without_runtime(isolated, tmp_path):
    retained = retain(tmp_path, isolated())
    old_manifest_bytes = (tmp_path / retained["path"]).read_bytes()
    old = json.loads(old_manifest_bytes)
    exported = adapter.export_retained_descriptive_sources(root=tmp_path, manifest_binding=retained, now=NOW)
    assert exported["path"].startswith(adapter.PUBLIC_FOLDER + "/")
    assert (tmp_path / retained["path"]).read_bytes() == old_manifest_bytes
    public = json.loads((tmp_path / exported["path"]).read_bytes())
    assert public["original_manifest_binding"] == retained
    assert public["exported_at"] == NOW.isoformat()
    assert [row["original_binding"] for row in public["files"]] == [row["original_binding"] for row in old["files"]]
    for source, copy in zip(old["files"], public["files"]):
        assert (tmp_path / source["retained_binding"]["path"]).read_bytes() == (tmp_path / copy["retained_binding"]["path"]).read_bytes()
    # Remove every original runtime/protocol/rule dependency from this isolated
    # root. Public replay must rely exclusively on its newly bound copies.
    public_files = {tmp_path / exported["path"],
                    *(tmp_path / row["retained_binding"]["path"] for row in public["files"])}
    for path in tmp_path.rglob("*"):
        if path.is_file() and path not in public_files:
            path.unlink()
    summary = adapter.load_retained_replay_summary(root=tmp_path, manifest_binding=exported, now=NOW)
    assert summary["signal_event_count"] > 0
    assert summary["trade_count"] is None and summary["formal_eligibility"] is False


@pytest.mark.parametrize("kind", ["raw", "escape_copy", "escape_original", "future_export", "past_export"])
def test_public_export_tampering_is_rejected(isolated, tmp_path, kind):
    exported = adapter.export_retained_descriptive_sources(root=tmp_path,
        manifest_binding=retain(tmp_path, isolated()), now=NOW)
    manifest = json.loads((tmp_path / exported["path"]).read_bytes())
    if kind == "raw":
        path = tmp_path / manifest["files"][0]["retained_binding"]["path"]
        path.write_bytes(path.read_bytes() + b"changed")
    elif kind == "escape_copy":
        manifest["files"][0]["retained_binding"]["path"] = "../outside.json"
    elif kind == "escape_original":
        manifest["original_manifest_binding"]["path"] = "../outside/manifest.json"
    elif kind == "future_export":
        manifest["exported_at"] = "2026-10-22T00:00:00+00:00"
    else:
        manifest["exported_at"] = "2026-07-10T00:00:00+00:00"
    exported = write(tmp_path, exported["path"], manifest)
    with pytest.raises(ValueError):
        adapter.build_retained_descriptive_validation(root=tmp_path, manifest_binding=exported, now=NOW)


@pytest.mark.parametrize("parent", ["runtime/other", "artifacts/current/other", "artifacts/current/dual-strategy-v5/other"])
def test_only_exact_manifest_parents_are_accepted(isolated, tmp_path, parent):
    retained = retain(tmp_path, isolated())
    raw = (tmp_path / retained["path"]).read_bytes()
    misplaced = write(tmp_path, parent + "/" + "a" * 32 + "/manifest.json", raw)
    with pytest.raises(ValueError, match="outside append-only source directory"):
        adapter.build_retained_descriptive_validation(root=tmp_path, manifest_binding=misplaced, now=NOW)


@pytest.mark.parametrize("kind", ["copied_raw", "omitted_provenance", "future_copy", "escaping_original"])
def test_tampering_fails_closed_even_with_rebound_manifest(isolated, tmp_path, kind):
    binding = retain(tmp_path, isolated())
    manifest = json.loads((tmp_path / binding["path"]).read_bytes())
    if kind == "copied_raw":
        source = next(row for row in manifest["files"] if row["original_binding"]["path"].endswith("60m.jsonp"))
        path = tmp_path / source["retained_binding"]["path"]
        path.write_bytes(path.read_bytes() + b"changed")
    elif kind == "omitted_provenance":
        manifest["files"] = [row for row in manifest["files"]
            if not row["original_binding"]["path"].endswith("60m.jsonp")]
    elif kind == "future_copy":
        manifest["retained_at"] = "2026-10-22T00:00:00+00:00"
    else:
        manifest["files"][0]["original_binding"]["path"] = "../escape"
    binding = write(tmp_path, binding["path"], manifest)
    with pytest.raises(ValueError):
        adapter.build_retained_descriptive_validation(root=tmp_path, manifest_binding=binding, now=NOW)


def test_actual_namespace_cannot_relabel_test_sources(isolated, tmp_path):
    historical = isolated()
    with pytest.raises(ValueError, match="TEST_ONLY"):
        retain(tmp_path, historical, namespace="ACTUAL")
    assert not (tmp_path / adapter.FOLDER).exists()


def test_future_evidence_and_naive_clock_are_rejected(isolated, tmp_path):
    historical = isolated()
    with pytest.raises(ValueError, match="timezone"):
        retain(tmp_path, historical, now=NOW.replace(tzinfo=None))
    protocol = json.loads((tmp_path / historical["path"]).read_bytes())
    protocol["registered_at"] = "2026-07-01T00:00:00+08:00"
    historical = write(tmp_path, historical["path"], protocol)
    with pytest.raises(ValueError, match="not yet available"):
        retain(tmp_path, historical, now=datetime(2026, 7, 10, 7, tzinfo=timezone.utc))


def test_future_prices_change_outcomes_but_not_existing_signals(isolated, tmp_path):
    first = adapter.build_retained_descriptive_validation(root=tmp_path,
        manifest_binding=retain(tmp_path, isolated()), now=NOW)
    initial = first["results"][0]["events"]["validation"][0]
    changed = bars()
    trigger(changed, initial["cutoff"])
    for period, rows in changed.items():
        for row in rows:
            closed = row["time"] + " 15:00:00" if period == "daily" else row["time"]
            if closed > initial["cutoff"]:
                row.update(open="100", high="110", low="90", close="100", volume="10000")
    second = adapter.build_retained_descriptive_validation(root=tmp_path,
        manifest_binding=retain(tmp_path, isolated(values=changed)), now=NOW)
    after = second["results"][0]["events"]["validation"][0]
    assert all(initial[key] == after[key] for key in ("cutoff", "signal_state", "levels", "completed_context"))
    assert initial["outcome"] != after["outcome"]
    assert first["trade_count"] is second["trade_count"] is None


def test_unsigned_actual_contract_handoff_never_admits(isolated, monkeypatch, tmp_path):
    """ACTUAL-labeled synthetic schema test, not an actual market sample."""
    structure = synthetic_validation_report(tmp_path)
    monkeypatch.setattr(validation_evidence, "build_hotspot_structure_validation", lambda **kwargs: structure)
    binding = retain(tmp_path, isolated(namespace="ACTUAL"), namespace="ACTUAL")
    result = validation_evidence.build_hotspot_review_handoff(root=tmp_path, evaluated_at=NOW,
        quantitative_protocol_binding=binding)
    assert result["quantitative_validation"]["scope"] == "DESCRIPTIVE"
    assert result["formal_eligibility"] is result["risk_review_eligible"] is False
    assert result["authorization_requirements"]["signature"] is None
    assert result["formal_release_status"] == "NOT_REQUESTED"
    assert all(row["status"] == "PENDING_REVIEW" for row in result["review_requirements"])
    assert not (tmp_path / "config/current-hotspot-independent-admission-v1.json").exists()
    assert binding in result["source_bindings"]
    for source in result["source_bindings"]:
        assert sha256((tmp_path / source["path"]).read_bytes()).hexdigest() == source["sha256"]


def test_test_namespace_cannot_enter_actual_handoff(isolated, monkeypatch, tmp_path):
    structure = synthetic_validation_report(tmp_path)
    monkeypatch.setattr(validation_evidence, "build_hotspot_structure_validation", lambda **kwargs: structure)
    with pytest.raises(ValueError, match="ACTUAL review"):
        validation_evidence.build_hotspot_review_handoff(root=tmp_path, evaluated_at=NOW,
            quantitative_protocol_binding=retain(tmp_path, isolated()))


def test_real_five_retained_sources_reproduce_161_signals_not_trades(tmp_path_factory):
    # Preserve original paths inside the copy without exceeding Windows MAX_PATH.
    tmp_path = tmp_path_factory.mktemp("real")
    name = "artifacts/current/tl11-p8-20261016/strategy/current-five-retrospective-spec.json"

    def copy(name):
        source = ROOT / name
        if not source.is_file():
            pytest.skip("Local retained original absent: " + name)
        return write(tmp_path, name, source.read_bytes())

    historical = copy(name)
    protocol = json.loads((tmp_path / name).read_bytes())
    for rule in protocol["rule_bindings"]:
        copy(rule["path"])
    for item in protocol["cases"]:
        copy(item["case_path"])
        case = json.loads((tmp_path / item["case_path"]).read_bytes())
        for source in case["source_bindings"].values():
            copy(source["path"])
        copy(case["current_reference_close"]["bundle_path"])
    binding = retain(tmp_path, historical, namespace="ACTUAL")
    manifest = json.loads((tmp_path / binding["path"]).read_bytes())
    for row in manifest["files"]:
        (tmp_path / row["original_binding"]["path"]).unlink()
    summary = adapter.load_retained_replay_summary(root=tmp_path, manifest_binding=binding, now=NOW)
    assert summary["namespace"] == "ACTUAL" and summary["scope"] == "DESCRIPTIVE"
    assert summary["signal_event_count"] == 161
    assert summary["mature_five_session_count"] == 150
    assert summary["right_censored_count"] == 11
    assert summary["trade_count"] is summary["execution_metrics"]["trade_count"] is None
    assert [row["symbol"] for row in summary["items"]] == [row["symbol"] for row in protocol["cases"]]
    assert summary["formal_eligibility"] is summary["strict_oos_admitted"] is False


def test_public_retained_archive_replays_without_legacy_originals(tmp_path_factory):
    """Mandatory committed archive evidence: absence or corruption must fail CI."""
    root = tmp_path_factory.mktemp("pub")
    config = json.loads((ROOT / "config/hotspot-replay-review-v1.json").read_bytes())
    binding = config["retained_manifest_binding"]
    assert binding["path"].startswith(adapter.PUBLIC_FOLDER + "/")
    raw = (ROOT / binding["path"]).read_bytes()
    assert sha256(raw).hexdigest() == binding["sha256"]
    manifest = json.loads(raw)
    assert len(manifest["files"]) == 19
    assert manifest["namespace"] == "ACTUAL"
    write(root, binding["path"], raw)
    for row in manifest["files"]:
        copied = row["retained_binding"]
        raw = (ROOT / copied["path"]).read_bytes()
        assert sha256(raw).hexdigest() == copied["sha256"]
        write(root, copied["path"], raw)
        assert not (root / row["original_binding"]["path"]).exists()
    assert len([path for path in root.rglob("*") if path.is_file()]) == 20
    assert not (root / "runtime").exists()
    assert not (root / "config/current-price-conditions.json").exists()
    # Evaluate at the recorded archive cutoff, rather than the synthetic tests'
    # midnight clock, which predates this real archive's acquisition.
    summary = adapter.load_retained_replay_summary(root=root, manifest_binding=binding,
        now=datetime.fromisoformat(manifest["exported_at"]))
    assert summary["namespace"] == "ACTUAL" and summary["scope"] == "DESCRIPTIVE"
    assert summary["signal_event_count"] == 161
    assert summary["mature_five_session_count"] == 150
    assert summary["right_censored_count"] == 11
    assert summary["trade_count"] is summary["execution_metrics"]["trade_count"] is None
    assert summary["formal_eligibility"] is summary["strict_pit_admitted"] is summary["strict_oos_admitted"] is False

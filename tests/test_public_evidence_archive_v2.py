"""Archive v2 direct tests; synthetic mechanisms are separate from required real replay."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

from value_investment_agent.application.research import public_evidence as app
from value_investment_agent.infrastructure import public_evidence_archive_v2 as archive
from test_public_evidence_consumer import bundle as synthetic_bundle


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def forbidden(*args, **kwargs):
    raise AssertionError("No acquisition/network/current publication allowed")


@pytest.fixture
def case(tmp_path, monkeypatch):
    args, packet, _ = synthetic_bundle(tmp_path, monkeypatch)
    monkeypatch.setattr(app, "publish_public_evidence", forbidden)
    ref = dict(path=args["bundle_path"].relative_to(tmp_path).as_posix(), sha256=args["bundle_sha256"])
    return tmp_path, ref, packet


def pack(case):
    root, ref, _ = case
    return app.archive_public_evidence(root=root, bundle_binding=ref,
                                       output_dir="runtime/archive-test")


def restore(root, ref, dest=".tmp/restored"):
    return app.restore_public_evidence(root=root, manifest_binding=ref, destination=dest)


def test_explicit_closure_atomic_restore_and_idempotence(case):
    root, ref, before = case
    result = pack(case)
    assert app.archive_public_evidence(root=root, bundle_binding=ref,
        output_dir="runtime/archive-test") == result
    first = restore(root, result["manifest_ref"])
    assert restore(root, result["manifest_ref"]) == first
    assert app.load_bundle(root / first["destination"], ref) == before
    assert not (root / "runtime/public-evidence/current.json").exists()
    refs = app.public_evidence_closure(root=root, bundle_binding=ref)
    assert result["file_count"] == len(refs)
    for item in refs:
        assert (root / item["path"]).read_bytes() == (root / first["destination"] / item["path"]).read_bytes()


@pytest.mark.parametrize("damage", ["object", "missing", "manifest_hash", "target", "escape", "extra"])
def test_bad_archive_or_destination_never_publishes(case, damage):
    root, _, _ = case
    ref = pack(case)["manifest_ref"]
    path = root / ref["path"]
    packet = json.loads(path.read_bytes())
    if damage in {"object", "missing"}:
        obj = path.parent / packet["items"][-1]["archive_path"]
        if damage == "missing":
            obj.unlink()
        else:
            obj.write_bytes(b"bad")
    elif damage == "manifest_hash":
        ref = dict(ref, sha256="0" * 64)
    elif damage in {"escape", "extra"}:
        if damage == "escape":
            packet["items"][-1]["original_path"] = "runtime/../escape"
        else:
            row = dict(packet["items"][-1], original_path="runtime/unbound-extra")
            packet["items"].append(row)
        path.write_text(json.dumps(packet), encoding="utf-8")
        ref = dict(ref, sha256=sha(path))
    else:
        (root / ".tmp/restored").mkdir(parents=True)
        (root / ".tmp/restored/sentinel").write_bytes(b"existing")
    with pytest.raises((ValueError, FileNotFoundError, FileExistsError)):
        restore(root, ref)
    target = root / ".tmp/restored"
    if damage == "target":
        assert list(target.iterdir()) == [target / "sentinel"]
        assert (target / "sentinel").read_bytes() == b"existing"
    else:
        assert not target.exists()
    assert not (root / ".tmp/restored.restore-lock").exists()


def test_staged_failure_is_not_partial_publication_and_can_retry(case, monkeypatch):
    root, _, _ = case
    ref = pack(case)["manifest_ref"]
    original = archive.restore_public_archive
    def fail(repo, manifest, target):
        original(repo, manifest, target)
        raise OSError("TEST_ONLY interrupted before publication")
    monkeypatch.setattr(archive, "restore_public_archive", fail)
    with pytest.raises(OSError):
        restore(root, ref)
    assert not (root / ".tmp/restored").exists()
    assert not (root / ".tmp/restored.restore-lock").exists()
    monkeypatch.setattr(archive, "restore_public_archive", original)
    assert restore(root, ref)["status"] == "PUBLIC_EVIDENCE_RESTORED_AND_VERIFIED"


def test_predecessor_closure_and_partial_gaps_survive(case):
    root, ref, old = case
    new = deepcopy(old)
    gap = dict(symbol="600519", issuer_name="TEST_ONLY unavailable", period="2025-12-31", exchange="SSE")
    new["requests"].append(gap)
    new["items"].append(dict(request=gap, status="MISSING", receipt=None, reused=False,
                            fresh_index_checked=False, adopted_fact_count=0,
                            fact_snapshot=None, fact_status="NOT_RUN", reason="TEST_ONLY source unavailable"))
    new.update(status="PARTIAL", previous_bundle=ref)
    path = root / "runtime/next.json"
    path.write_text(json.dumps(new), encoding="utf-8")
    newref = dict(path="runtime/next.json", sha256=sha(path))
    result = app.archive_public_evidence(root=root, bundle_binding=newref, output_dir="runtime/partial-archive")
    restored = restore(root, result["manifest_ref"])
    dest = root / restored["destination"]
    assert app.load_bundle(dest, newref) == new
    assert app.load_bundle(dest, ref) == old
    assert app.load_bundle(dest, newref)["items"][-1]["receipt"] is None


def test_source_change_refused_before_archive_write(case):
    root, ref, packet = case
    receipt = json.loads((root / packet["items"][0]["receipt"]["path"]).read_bytes())
    (root / receipt["source"]["path"]).write_bytes(b"corrupt original")
    with pytest.raises(ValueError):
        pack(case)
    assert not (root / "runtime/archive-test").exists()


def test_existing_restored_original_cannot_be_repaired_silently(case):
    root, _, _ = case
    ref = pack(case)["manifest_ref"]
    first = restore(root, ref)
    manifest = json.loads((root / ref["path"]).read_bytes())
    target = root / first["destination"] / manifest["items"][0]["original_path"]
    target.write_bytes(b"changed")
    with pytest.raises(ValueError, match="RESTORED_ORIGINAL_DIFFERS"):
        restore(root, ref)
    assert target.read_bytes() == b"changed"


def cli(monkeypatch, root):
    path = Path(__file__).resolve().parents[1] / "scripts/current/collect_public_evidence.py"
    spec = importlib.util.spec_from_file_location("archive_cli_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "run_public_evidence", forbidden)
    monkeypatch.setattr(mod, "publish_public_evidence", forbidden)
    return mod


@pytest.mark.parametrize("args", [
    ["--mode", "archive", "--publish-status"],
    ["--mode", "restore", "--allow-public-downloads"],
    ["--mode", "restore", "--refresh"],
    ["--mode", "archive", "--bundle", "runtime/missing.json"],
    ["--mode", "restore", "--manifest", "runtime/a/manifest.json"],
    ["--mode", "collect", "--bundle", "runtime/a.json"],
])
def test_cli_rejects_invalid_modes_before_io(case, monkeypatch, args):
    root, _, _ = case
    mod = cli(monkeypatch, root)
    monkeypatch.setattr(mod, "archive_public_evidence", forbidden)
    monkeypatch.setattr(mod, "restore_public_evidence", forbidden)
    monkeypatch.setattr(sys, "argv", ["collect", *args])
    with pytest.raises(SystemExit) as caught:
        mod.main()
    assert caught.value.code == 2


def test_cli_archive_restore_use_actual_functions(case, monkeypatch, capsys):
    root, ref, _ = case
    mod = cli(monkeypatch, root)
    monkeypatch.setattr(sys, "argv", ["collect", "--mode", "archive", "--bundle", ref["path"],
        "--bundle-sha256", ref["sha256"], "--output", "runtime/cli-archive"])
    assert mod.main() == 0
    result = json.loads(capsys.readouterr().out)
    manifest = result["manifest_ref"]
    monkeypatch.setattr(sys, "argv", ["collect", "--mode", "restore", "--manifest", manifest["path"],
        "--manifest-sha256", manifest["sha256"], "--destination", ".tmp/cli-restored"])
    assert mod.main() == 0
    assert json.loads(capsys.readouterr().out)["bundle_ref"] == ref


def test_real_600519_600887_archive_restore_and_existing_consumer(monkeypatch):
    location = os.environ.get("PUBLIC_EVIDENCE_ARCHIVE_REAL_ROOT")
    if not location:
        if os.environ.get("PUBLIC_EVIDENCE_ARCHIVE_REAL_REQUIRED") == "1":
            pytest.fail("PUBLIC_EVIDENCE_ARCHIVE_REAL_ROOT required; no synthetic substitute")
        pytest.skip("Explicit real root required")
    root = Path(location).resolve(strict=True)
    import requests
    from value_investment_agent.infrastructure.screening.financial_export_v2 import load_retained_financial_export
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import consume_retained_enrichment
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(app, "acquire_official_report", forbidden)
    monkeypatch.setattr(app, "publish_public_evidence", forbidden)
    accepted = json.loads((root / "artifacts/current/public-evidence-a-20261030.json").read_bytes())
    ref = accepted["bundle"]
    before = app.load_bundle(root, ref)
    closure = app.public_evidence_closure(root=root, bundle_binding=ref)
    old_hashes = {item["path"]: sha(root / item["path"]) for item in closure}
    run = uuid4().hex
    result = app.archive_public_evidence(root=root, bundle_binding=ref,
        output_dir="runtime/public-evidence-archives/" + run)
    restored = restore(root, result["manifest_ref"], ".tmp/value-mainline-p0/real-restore-" + run)
    dest = root / restored["destination"]
    assert app.load_bundle(dest, ref) == before
    export = before["financial_export"]
    now = datetime.now(timezone.utc)
    results = []
    for base in (root, dest):
        app.validate_queue_public_evidence(root=base, bundle_path=ref["path"],
            bundle_sha256=ref["sha256"], financial_export_path=export["path"],
            financial_export_sha256=export["sha256"])
        points, raw = load_retained_financial_export(base / export["path"], evaluation_at=now)
        results.append(consume_retained_enrichment(base, points, raw["value_enrichment_sources"], evaluation_at=now))
    assert results[0] == results[1]
    points, reports = results[1]
    assert {p["symbol"] for p in points} == {"600519", "600887"}
    assert all(p["field_name"] == "debt_ratio" for p in points)
    assert len(points) == 2
    for item in closure:
        assert sha(root / item["path"]) == sha(dest / item["path"]) == old_hashes[item["path"]]
    assert not (dest / app.POINTER).exists()
    assert restore(root, result["manifest_ref"], restored["destination"]) == restored
    receipt = dict(action="no_order", scope="REAL_600519_600887_OFFLINE_ARCHIVE_RESTORE",
        archive=result, restore=restored, closure_files=len(closure),
        load_bundle_equal=True, consumer_equal=True, original_hashes_unchanged=True,
        consumed=[dict(symbol=p["symbol"], field=p["field_name"], value=str(p["value"])) for p in points])
    target = root / ".tmp/value-mainline-p0" / ("archive-real-acceptance-" + run + ".json")
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REAL_ACCEPTANCE=" + str(target))


@pytest.mark.parametrize("destination", ["runtime/existing", ".", ".tmp", "../outside", "config"])
def test_restore_only_accepts_isolated_root(case, destination):
    root, _, _ = case
    ref = pack(case)["manifest_ref"]
    with pytest.raises(ValueError):
        restore(root, ref, destination)


def test_archive_publication_failure_leaves_no_partial_archive(case, monkeypatch):
    root, _, _ = case
    original = archive._publish
    def fail(*args):
        raise OSError("TEST_ONLY atomic publish failure")
    monkeypatch.setattr(archive, "_publish", fail)
    with pytest.raises(OSError):
        pack(case)
    assert not (root / "runtime/archive-test").exists()
    assert not (root / "runtime/archive-test.archive-lock").exists()
    monkeypatch.setattr(archive, "_publish", original)
    assert pack(case)["status"] == "PUBLIC_EVIDENCE_ARCHIVED"


def test_default_collect_cli_still_uses_existing_contract(case, monkeypatch, capsys):
    root, ref, packet = case
    mod = cli(monkeypatch, root)
    request = root / "requests.json"
    request.write_text(json.dumps(packet["requests"]), encoding="utf-8")
    calls = []
    def collect(**kwargs):
        calls.append(kwargs)
        return ref
    monkeypatch.setattr(mod, "run_public_evidence", collect)
    monkeypatch.setattr(sys, "argv", ["collect", "--requests", str(request), "--output", "runtime/new"])
    assert mod.main() == 0
    assert json.loads(capsys.readouterr().out) == dict(bundle=ref, action="no_order")
    assert calls[0]["allow_network"] is False and calls[0]["previous_binding"] is None

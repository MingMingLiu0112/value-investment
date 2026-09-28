from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil

import pytest

from value_investment_agent.application.product.prospective_observation import (
    _observation_classification, append_cninfo_observation,
    append_reviewed_cninfo_notice_observation, load_verified_observation_ledger,
    observations_at,
)
from value_investment_agent.application.product import prospective_observation as observation_module
from value_investment_agent.domain.research.prospective_registration import prospective_registration_from_payload


ROOT = Path(__file__).resolve().parents[1]
RUN = Path("runtime/prospective-public-event-20260927/20260927T004835372Z")
REGISTRATION = Path("runtime/prospective-v2-fc1e811/receipt.json")
MIDEA_RUN = Path("runtime/prospective-public-event-20260927/gapfill-000333-20260927T172744007289Z")


def _project(tmp_path: Path, monkeypatch, *, include_prior: bool = False) -> Path:
    root = tmp_path / "project"
    paths = [
        REGISTRATION, RUN / "receipt.json", RUN / "interpretation.json",
        RUN / "600887-page1.raw.json", RUN / "000333-page1.raw.json",
        RUN / "600887-1225578520.pdf",
    ]
    if include_prior:
        paths.append(Path("runtime/prospective-observations/600887/prospective-2c9c950216328f270a1614e9f357fce5.json"))
    for path in paths:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, root / path)
    def verify_registration(*, root, receipt_path, receipt_sha256, plan_path):
        raw = (root / receipt_path).read_bytes()
        assert __import__("hashlib").sha256(raw).hexdigest() == receipt_sha256
        receipt = json.loads(raw)
        policy = prospective_registration_from_payload({"schema_version": "prospective-research-registration-v2", **receipt["registration"]})
        return receipt, policy
    monkeypatch.setattr(observation_module, "verify_prospective_registration_receipt", verify_registration)
    return root


def _append(root: Path, **changes):
    args = dict(
        root=root, registration_path=REGISTRATION.as_posix(),
        registration_sha256="8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5",
        scan_receipt_path=(RUN / "receipt.json").as_posix(),
        scan_receipt_sha256="730ea9ced3609192b659539f32757cc5dd0b3eb72e71b985cbdfab593fbfd3cf",
        interpretation_path=(RUN / "interpretation.json").as_posix(),
        interpretation_sha256="4bcade44b280400396644ba7e698133ac479013d05d257b470affc50f406b18e",
        symbol="600887", document_id="1225578520",
        output_dir=root / "runtime/prospective-observations/600887",
    )
    return append_cninfo_observation(**(args | changes))


def _rewrite_scan_receipt(root: Path, update) -> str:
    path = root / RUN / "receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    update(receipt)
    encoded = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    return __import__("hashlib").sha256(encoded).hexdigest()


def test_post_start_discovery_is_not_retroactively_visible(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    row = _append(root)
    assert row["classification"] == "PREEXISTING_PUBLIC_DOCUMENT_REOBSERVED_AFTER_START"
    assert row["source_available_at"] == "2026-09-25T00:00:00+08:00"
    assert row["materiality"] == "UNDETERMINED"
    assert row["schema_version"] == "prospective-public-observation-v2"
    created = datetime.fromisoformat(row["record_created_at"])
    folder = root / "runtime/prospective-observations/600887"
    assert observations_at(
        root=root, directory=folder, case_id=row["case_id"],
        evaluation_cutoff=datetime.fromisoformat("2026-09-27T08:47:00+08:00"),
        trusted_hashes={row["observation_id"]: row["sha256"]},
    ) == ()
    assert len(observations_at(
        root=root, directory=folder, case_id=row["case_id"],
        evaluation_cutoff=created - timedelta(microseconds=1),
        trusted_hashes={row["observation_id"]: row["sha256"]},
    )) == 0
    assert len(observations_at(
        root=root, directory=folder, case_id=row["case_id"],
        evaluation_cutoff=created,
        trusted_hashes={row["observation_id"]: row["sha256"]},
    )) == 1
    assert _append(root)["observation_id"] == row["observation_id"]


def test_legacy_v1_observation_remains_visible_at_later_cutoff(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, include_prior=True)
    prior_path = root / "runtime/prospective-observations/600887" / "prospective-2c9c950216328f270a1614e9f357fce5.json"
    prior_sha = __import__("hashlib").sha256(prior_path.read_bytes()).hexdigest()
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    rows = observations_at(
        root=root, directory=prior_path.parent, case_id=prior["case_id"],
        evaluation_cutoff=datetime.now(timezone.utc),
        trusted_hashes={prior["observation_id"]: prior_sha},
    )
    assert [row["observation_id"] for row in rows] == [prior["observation_id"]]


def test_preexisting_document_available_exactly_at_start_is_not_misclassified():
    start = datetime.fromisoformat("2026-09-25T00:00:00+08:00")
    assert _observation_classification(start, start) == "PREEXISTING_PUBLIC_DOCUMENT_REOBSERVED_AFTER_START"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt: receipt.update(created_utc="2026-09-27T08:48:36.000000+08:00"),
        lambda receipt: receipt["indexes"][1].update(received_utc="2026-09-27T08:48:36.100000+08:00"),
    ],
    ids=["receipt-created-before-pdf-received", "index-response-after-pdf-request"],
)
def test_inconsistent_scan_receipt_time_order_fails_closed(tmp_path, monkeypatch, mutate):
    root = _project(tmp_path, monkeypatch)
    digest = _rewrite_scan_receipt(root, mutate)
    with pytest.raises(ValueError, match="time order|observed within"):
        _append(root, scan_receipt_sha256=digest)


def test_superseding_record_corrects_discovery_semantics_and_hides_old_record(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, include_prior=True)
    prior_id = "prospective-2c9c950216328f270a1614e9f357fce5"
    prior_path = root / "runtime/prospective-observations/600887" / f"{prior_id}.json"
    prior_sha = __import__("hashlib").sha256(prior_path.read_bytes()).hexdigest()
    corrected = _append(root, supersedes_observation_id=prior_id)
    assert corrected["observation_id"] != prior_id
    assert corrected["classification"] == "PREEXISTING_PUBLIC_DOCUMENT_REOBSERVED_AFTER_START"
    assert corrected["supersedes_observation_sha256"] == prior_sha
    rows = observations_at(
        root=root, directory=prior_path.parent, case_id=corrected["case_id"],
        evaluation_cutoff=datetime.fromisoformat(corrected["record_created_at"]),
        trusted_hashes={prior_id: prior_sha, corrected["observation_id"]: corrected["sha256"]},
    )
    assert [row["observation_id"] for row in rows] == [corrected["observation_id"]]
    assert [row["observation_id"] for row in observations_at(
        root=root, directory=prior_path.parent, case_id=corrected["case_id"],
        evaluation_cutoff=datetime.fromisoformat(corrected["record_created_at"]) - timedelta(microseconds=1),
        trusted_hashes={prior_id: prior_sha, corrected["observation_id"]: corrected["sha256"]},
    )] == [prior_id]


def test_original_pdf_tamper_fails_closed(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    source = root / RUN / "600887-1225578520.pdf"
    source.write_bytes(source.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="original PDF byte hash mismatch"):
        _append(root)


def test_issuer_mismatch_and_missing_predecessor_fail_closed(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="issuer is not in|identity"):
        _append(root, symbol="000333")
    with pytest.raises(FileNotFoundError):
        _append(root, supersedes_observation_id="prospective-not-present")


def test_late_source_cannot_be_added_to_earlier_evaluation(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    row = _append(root)
    path = root / "runtime/prospective-observations/600887" / f"{row['observation_id']}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source_available_at"] = "2026-09-28T00:00:00+08:00"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="pinned SHA-256"):
        observations_at(
            root=root, directory=path.parent, case_id=row["case_id"],
            evaluation_cutoff=datetime.fromisoformat("2026-09-27T23:00:00+08:00"),
            trusted_hashes={row["observation_id"]: row["sha256"]},
        )


def test_observation_reader_rejects_future_evaluation_cutoff(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="evaluation cutoff cannot be in the future"):
        observations_at(
            root=root,
            directory=root / "runtime/prospective-observations/600887",
            case_id="prospective-600887-20260927",
            evaluation_cutoff=datetime.now(timezone.utc) + timedelta(days=1),
            trusted_hashes={},
        )


def test_supersession_fork_is_rejected(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, include_prior=True)
    prior_id = "prospective-2c9c950216328f270a1614e9f357fce5"
    first = _append(root, supersedes_observation_id=prior_id)
    replay = _append(root, supersedes_observation_id=prior_id)
    assert replay["observation_id"] == first["observation_id"]
    assert replay["sha256"] == first["sha256"]

    changed_receipt_hash = _rewrite_scan_receipt(
        root,
        lambda receipt: (
            receipt["pdf"].update(received_utc="2026-09-27T08:48:36.4933281+08:00"),
            receipt.update(created_utc="2026-09-27T08:48:36.5076161+08:00"),
        ),
    )
    with pytest.raises(ValueError, match="fork or duplicate"):
        _append(root, supersedes_observation_id=prior_id, scan_receipt_sha256=changed_receipt_hash)


def test_observation_reader_rejects_hash_bound_supersession_fork(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, include_prior=True)
    prior_id = "prospective-2c9c950216328f270a1614e9f357fce5"
    folder = root / "runtime/prospective-observations/600887"
    prior_path = folder / f"{prior_id}.json"
    prior_hash = __import__("hashlib").sha256(prior_path.read_bytes()).hexdigest()
    successor = _append(root, supersedes_observation_id=prior_id)
    fork = json.loads((folder / f"{successor['observation_id']}.json").read_text(encoding="utf-8"))
    fork_id = "prospective-" + "a" * 32
    fork["observation_id"] = fork_id
    fork_bytes = (json.dumps(fork, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (folder / f"{fork_id}.json").write_bytes(fork_bytes)
    trusted = {
        prior_id: prior_hash,
        successor["observation_id"]: successor["sha256"],
        fork_id: __import__("hashlib").sha256(fork_bytes).hexdigest(),
    }
    with pytest.raises(ValueError, match="supersession fork"):
        observations_at(
            root=root, directory=folder, case_id=successor["case_id"],
            evaluation_cutoff=datetime.fromisoformat("2026-09-27T08:49:00+08:00"),
            trusted_hashes=trusted,
        )


def test_reviewed_notice_writer_rejects_source_before_conservative_availability(tmp_path, monkeypatch):
    root = tmp_path / "project"
    sources = [
        REGISTRATION,
        Path("config/prospective-research-observation-plan-v2.json"),
        MIDEA_RUN / "scan-receipt.json",
        MIDEA_RUN / "index.json",
        MIDEA_RUN / "000333-page-1.raw.json",
        MIDEA_RUN / "1225582141.PDF",
        MIDEA_RUN / "document-review-1225582141.json",
    ]
    for relative in sources:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    def verify_registration(*, root, receipt_path, receipt_sha256, plan_path):
        raw = (root / receipt_path).read_bytes()
        assert __import__("hashlib").sha256(raw).hexdigest() == receipt_sha256
        receipt = json.loads(raw)
        policy = prospective_registration_from_payload({
            "schema_version": "prospective-research-registration-v2",
            **receipt["registration"],
        })
        return receipt, policy

    monkeypatch.setattr(observation_module, "verify_prospective_registration_receipt", verify_registration)
    kwargs = dict(
        root=root, registration_path=REGISTRATION.as_posix(),
        registration_sha256="8b76312225712d13f7c5ceffa7e2447d0df2e230a9baed5a9d04748f82608da5",
        scan_receipt_path=(MIDEA_RUN / "scan-receipt.json").as_posix(),
        scan_receipt_sha256="664bf165ba847a8da902cd8d8efa32b92a1588d5447c93ff678940cf03673021",
        document_review_path=(MIDEA_RUN / "document-review-1225582141.json").as_posix(),
        document_review_sha256="39e3efcc41a6612b579a891c638a699fe41802288a2f26fad28d312ddb263b75",
        symbol="000333", document_id="1225582141",
        output_dir=root / "runtime/prospective-observations/000333",
    )
    with pytest.raises(ValueError, match="conservatively available"):
        append_reviewed_cninfo_notice_observation(**kwargs)
    assert not kwargs["output_dir"].exists()


def test_verified_ledger_never_loads_midea_observation_before_source_availability(tmp_path, monkeypatch):
    record_rel = Path(
        "runtime/prospective-observations/000333/"
        "prospective-676926f96e284002045c12b9a7142b56.json"
    )
    record_bytes = (ROOT / record_rel).read_bytes()
    record_sha = __import__("hashlib").sha256(record_bytes).hexdigest()
    assert record_sha == "379046d99cb5b1f6a7353397b63ec4133a58125c38bbc3180728e8eb4bc82f8f"
    record = json.loads(record_bytes)
    assert datetime.fromisoformat(record["observed_at"]) < datetime.fromisoformat(record["source_available_at"])

    root = tmp_path / "project"
    for relative in (
        record_rel,
        MIDEA_RUN / "000333-page-1.raw.json",
        MIDEA_RUN / "1225582141.PDF",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    manifest = {
        "schema_version": "prospective-observation-ledger-v1",
        "action": "no_order",
        "records": [{
            "case_id": record["case_id"],
            "observation_id": record["observation_id"],
            "path": record_rel.as_posix(),
            "sha256": record_sha,
        }],
    }
    manifest_path = root / "config" / "prospective-observation-ledger-v1.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)

    class AfterAvailability(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime.fromisoformat("2026-09-29T00:01:00+08:00")
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(observation_module, "datetime", AfterAvailability)
    rows = load_verified_observation_ledger(
        root=root,
        manifest_path=Path("config/prospective-observation-ledger-v1.json"),
        manifest_sha256=__import__("hashlib").sha256(manifest_bytes).hexdigest(),
        evaluation_cutoff=AfterAvailability.fromisoformat("2026-09-29T00:01:00+08:00"),
    )
    assert rows == ()


def test_observation_reader_rejects_future_creation_timestamp(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    row = _append(root)
    path = root / "runtime/prospective-observations/600887" / f"{row['observation_id']}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["receipt_created_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    with pytest.raises(ValueError, match="future process"):
        observations_at(
            root=root, directory=path.parent, case_id=row["case_id"],
            evaluation_cutoff=datetime.now(timezone.utc),
            trusted_hashes={row["observation_id"]: __import__("hashlib").sha256(encoded).hexdigest()},
        )


def test_cninfo_observation_supports_hash_bound_supersession(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    first = _append(root)
    successor = _append(root, supersedes_observation_id=first["observation_id"])
    assert successor["supersedes_observation_id"] == first["observation_id"]
    assert successor["supersedes_observation_sha256"] == first["sha256"]


def test_hash_pinned_manifest_loads_only_explicit_observations(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    row = _append(root)
    manifest_path = root / "config" / "prospective-observation-ledger-v1.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "prospective-observation-ledger-v1",
        "action": "no_order",
        "records": [{
            "case_id": row["case_id"],
            "observation_id": row["observation_id"],
            "path": (Path("runtime/prospective-observations/600887") / f"{row['observation_id']}.json").as_posix(),
            "sha256": row["sha256"],
        }],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha = __import__("hashlib").sha256(manifest_bytes).hexdigest()
    created = datetime.fromisoformat(row["record_created_at"])

    visible = load_verified_observation_ledger(
        root=root, manifest_path=Path("config/prospective-observation-ledger-v1.json"),
        manifest_sha256=manifest_sha, evaluation_cutoff=created,
    )
    assert [item["observation_id"] for item in visible] == [row["observation_id"]]
    assert visible[0]["_ledger_path"].endswith(f"{row['observation_id']}.json")


def test_hash_pinned_manifest_rejects_tampering_and_incomplete_inputs(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    row = _append(root)
    manifest_path = root / "config" / "ledger.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "schema_version": "prospective-observation-ledger-v1",
        "action": "no_order",
        "records": [{
            "case_id": row["case_id"], "observation_id": row["observation_id"],
            "path": f"runtime/prospective-observations/600887/{row['observation_id']}.json",
            "sha256": row["sha256"],
        }],
    }), encoding="utf-8")
    digest = __import__("hashlib").sha256(manifest_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="manifest SHA-256 mismatch"):
        load_verified_observation_ledger(
            root=root, manifest_path=Path("config/ledger.json"),
            manifest_sha256="0" * 64, evaluation_cutoff=datetime.now(timezone.utc),
        )
    with pytest.raises(ValueError, match="future"):
        load_verified_observation_ledger(
            root=root, manifest_path=Path("config/ledger.json"),
            manifest_sha256=digest,
            evaluation_cutoff=datetime.now(timezone.utc) + timedelta(days=1),
        )


def test_repository_observation_manifest_replays_current_cutoff() -> None:
    manifest_path = ROOT / "config" / "prospective-observation-ledger-v1.json"
    digest = __import__("hashlib").sha256(manifest_path.read_bytes()).hexdigest()
    rows = load_verified_observation_ledger(
        root=ROOT,
        manifest_path=Path("config/prospective-observation-ledger-v1.json"),
        manifest_sha256=digest,
        evaluation_cutoff=datetime.fromisoformat("2026-09-28T00:26:44+00:00"),
    )
    assert [row["symbol"] for row in rows] == ["600887"]
    assert [row["observation_id"] for row in rows] == [
        "prospective-cd9d6cc7382f67d1565132787949682b"
    ]

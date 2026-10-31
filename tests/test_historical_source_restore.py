"""Content-addressed closure tests for historical v3 research dependencies."""
from hashlib import sha256
from types import SimpleNamespace

import pytest

from value_investment_agent.application.product.historical_source_restore import (
    verify_or_restore_package_sources,
)


def payload(path, content):
    return {"sources": [{"id": "assumption", "local_path": path,
        "sha256": sha256(content).hexdigest()}]}


def test_repository_research_dependency_is_read_from_retained_blob_after_drift(tmp_path):
    source = tmp_path / "config" / "research-assumptions" / "case.json"
    source.parent.mkdir(parents=True)
    original = b'{"assumption":"original"}\n'
    source.write_bytes(original)
    restore_dir = tmp_path / "runtime" / "candidate" / "historical-source-code"

    created = verify_or_restore_package_sources(
        tmp_path, payload("config/research-assumptions/case.json", original),
        restore_dir=restore_dir,
    )
    assert created[0][0] == restore_dir / f"{sha256(original).hexdigest()}.blob"

    source.write_bytes(b'{"assumption":"new checkout"}\n')
    restored = verify_or_restore_package_sources(
        tmp_path, payload("config/research-assumptions/case.json", original),
        restore_dir=restore_dir, create=False,
    )
    assert restored == created
    assert restored[0][0].read_bytes() == original


def test_retained_repository_dependency_fails_closed_on_blob_drift(tmp_path):
    source = tmp_path / "docs" / "review.md"
    source.parent.mkdir(parents=True)
    original = b"review v1\n"
    source.write_bytes(original)
    restore_dir = tmp_path / "runtime" / "candidate" / "historical-source-code"
    created = verify_or_restore_package_sources(
        tmp_path, payload("docs/review.md", original), restore_dir=restore_dir,
    )
    created[0][0].write_bytes(b"tampered")
    with pytest.raises(ValueError, match="restore drift"):
        verify_or_restore_package_sources(
            tmp_path, payload("docs/review.md", original),
            restore_dir=restore_dir, create=False,
        )


def test_duplicate_source_identity_reuses_one_content_addressed_blob(tmp_path):
    source = tmp_path / "config" / "research-assumptions" / "case.json"
    source.parent.mkdir(parents=True)
    original = b'{"assumption":"shared"}\n'
    source.write_bytes(original)
    digest = sha256(original).hexdigest()
    package = {"sources": [
        {"id": "assumption-a", "local_path": "config/research-assumptions/case.json",
         "sha256": digest},
        {"id": "assumption-b", "local_path": "config/research-assumptions/case.json",
         "sha256": digest},
    ]}
    restore_dir = tmp_path / "runtime" / "candidate" / "historical-source-code"

    verified = verify_or_restore_package_sources(
        tmp_path, package, restore_dir=restore_dir,
    )

    retained = restore_dir / f"{digest}.blob"
    assert verified == ((retained, digest), (retained, digest))
    assert list(restore_dir.iterdir()) == [retained]


def test_drifted_config_can_be_recovered_from_fixed_baseline(tmp_path, monkeypatch):
    source = tmp_path / "config" / "research-assumptions" / "case.json"
    source.parent.mkdir(parents=True)
    historical = b'{"assumption":"historical"}\n'
    source.write_bytes(b'{"assumption":"current"}\n')
    digest = sha256(historical).hexdigest()
    restore_dir = tmp_path / "runtime" / "candidate" / "historical-source-code"
    calls = []

    def baseline(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=historical)

    monkeypatch.setattr(
        "value_investment_agent.application.product.historical_source_restore.subprocess.run",
        baseline,
    )
    verified = verify_or_restore_package_sources(
        tmp_path,
        {"sources": [{
            "id": "historical-assumption",
            "local_path": "config/research-assumptions/case.json",
            "sha256": digest,
        }]},
        restore_dir=restore_dir,
    )

    retained = restore_dir / f"{digest}.blob"
    assert verified == ((retained, digest),)
    assert retained.read_bytes() == historical
    assert calls[0][-1].endswith(":config/research-assumptions/case.json")

"""Content-addressed closure tests for historical v3 research dependencies."""
from hashlib import sha256

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

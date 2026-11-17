"""Optional real archives must not hide broken or mandatory synthetic evidence."""
import json

import pytest

from hotspot_retained_originals import require_retained_originals


def test_missing_retained_handle_is_an_explicit_skip(tmp_path):
    with pytest.raises(pytest.skip.Exception, match="Local retained original absent"):
        require_retained_originals(tmp_path, tmp_path / "runtime/missing.json")


def test_partial_archive_checks_transitive_originals(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(dict(source_bindings={"60m": {"path": "runtime/missing.raw"}})), encoding="utf-8")
    with pytest.raises(pytest.skip.Exception, match="runtime/missing.raw"):
        require_retained_originals(tmp_path, registry)


def test_present_but_corrupt_retained_json_is_not_skipped(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text("broken JSON", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        require_retained_originals(tmp_path, registry)

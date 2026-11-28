"""Bounded retained CNINFO PDF replay; no download or publication."""
from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from test_retained_event_coverage import archive, archive_mode, verify
from value_investment_agent.application.product.daily_event_observation import (
    verify_retained_event_coverage, verify_retained_event_snapshot,
)


MIB = 1024 * 1024
REAL_ROOT = Path(__file__).resolve().parents[1]
REAL_OBSERVATION = (REAL_ROOT / "runtime/direct-cash-600887-recovery-"
    "20261117T172437931869Z-073bd450-full-window/observation.json")


@pytest.mark.parametrize("limit", [True, False, 32 * MIB - 1, 128 * MIB + 1,
                                    32.0 * MIB, "128MiB", None])
@pytest.mark.parametrize("verifier", [verify_retained_event_coverage,
                                      verify_retained_event_snapshot])
def test_pdf_limit_requires_bounded_plain_integer(verifier, limit):
    with pytest.raises(ValueError, match="PDF byte limit"):
        verifier(Path("."), {}, symbol="600887", required_from=date(2025, 12, 31),
                 required_to=date(2026, 11, 17), now=datetime.now(timezone.utc),
                 pdf_byte_limit=limit)


def test_default_and_explicit_limit_keep_small_archive_behavior(tmp_path, monkeypatch):
    observation = archive(tmp_path, monkeypatch, populated=True)
    baseline = verify(tmp_path, observation)
    assert verify(tmp_path, observation, pdf_byte_limit=32 * MIB) == baseline
    assert verify(tmp_path, observation, pdf_byte_limit=128 * MIB) == baseline


def test_snapshot_explicit_limit_preserves_snapshot_semantics(tmp_path, monkeypatch):
    observation = archive_mode(tmp_path, monkeypatch, snapshot=True, populated=True)
    baseline = verify(tmp_path, observation, snapshot=True,
                      now=datetime(2020, 1, 2, 10, tzinfo=timezone.utc))
    assert verify(tmp_path, observation, snapshot=True, pdf_byte_limit=128 * MIB,
                  now=datetime(2020, 1, 2, 10, tzinfo=timezone.utc)) == baseline


@pytest.mark.skipif(not REAL_OBSERVATION.is_file(), reason="retained full-window originals unavailable")
def test_retained_600887_full_pdf_requires_explicit_larger_limit():
    observation = json.loads(REAL_OBSERVATION.read_text(encoding="utf-8"))
    kwargs = dict(symbol="600887", required_from=date.fromisoformat(observation["scan_from"]),
                  required_to=date.fromisoformat(observation["scan_to"]),
                  now=datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="exceeds byte bounds"):
        verify_retained_event_coverage(REAL_ROOT, observation, **kwargs)
    with pytest.raises(ValueError, match="exceeds byte bounds"):
        verify_retained_event_coverage(REAL_ROOT, observation, pdf_byte_limit=64 * MIB, **kwargs)
    verified = verify_retained_event_coverage(
        REAL_ROOT, observation, pdf_byte_limit=128 * MIB, **kwargs)
    assert verified["coverage_status"] == "COMPLETE"
    assert verified["materiality_approved"] is False

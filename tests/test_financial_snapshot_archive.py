from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from value_investment_agent.cli import archive_financial_records
from value_investment_agent.models import SourceRecord
from value_investment_agent import tracking_collection


def record(field):
    return SourceRecord(symbol='000027', field_name=field, period_label='2026-06-30',
        value=Decimal('1'), unit='CNY', source_name='test', source_url='https://example.test',
        published_at=None, fetched_at=datetime.now(timezone.utc), parser_version='test',
        raw_payload=b'{"income":1}')


def test_archive_deduplicates_and_retains_exact_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking_collection.shutil, 'disk_usage', lambda _: SimpleNamespace(free=4*1024**3))
    inputs = [record('net_income'), record('revenue')]
    outputs = archive_financial_records(inputs, tmp_path)
    assert outputs[0].local_path == outputs[1].local_path
    path = Path(outputs[0].local_path)
    assert path.parent.name == 'financial_snapshots'
    assert path.read_bytes() == inputs[0].raw_payload
    assert path.stem == hashlib.sha256(inputs[0].raw_payload).hexdigest()
    assert all(r.local_path is None for r in inputs)
    assert len(list(path.parent.glob('*.json'))) == 1


def test_archive_preserves_database_disk_reserve(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking_collection.shutil, 'disk_usage', lambda _: SimpleNamespace(free=1024))
    with pytest.raises(OSError, match='reserve'):
        archive_financial_records([record('net_income')], tmp_path)
    assert not list(tmp_path.rglob('*.json'))


def test_existing_corrupt_archive_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking_collection.shutil, 'disk_usage', lambda _: SimpleNamespace(free=4*1024**3))
    outputs = archive_financial_records([record('net_income')], tmp_path)
    path = Path(outputs[0].local_path)
    path.write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='hash mismatch'):
        archive_financial_records([record('net_income')], tmp_path)
    assert path.read_bytes() == b'corrupted'

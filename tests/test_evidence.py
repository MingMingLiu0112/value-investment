import json
from pathlib import Path

import pytest

from value_investment_agent.evidence import load_evidence_manifest


def write_manifest(tmp_path: Path, **overrides: object) -> Path:
    (tmp_path / 'annual-report.pdf').write_bytes(b'official filing')
    payload = {
        'source_name': 'Shanghai Stock Exchange annual report',
        'source_url': 'https://www.sse.com.cn/disclosure/listedinfo/announcement/',
        'source_type': 'exchange',
        'published_at': '2026-03-30T18:00:00+08:00',
        'evidence_file': 'annual-report.pdf',
        'validation_status': 'verified',
        'human_reviewed': True,
        'reviewed_by': 'researcher@example.com',
        'reviewed_at': '2026-09-02T10:00:00+08:00',
        'points': [{
            'symbol': '600519', 'field_name': 'fair_value', 'period_label': '2026-09-02',
            'value': '1600', 'unit': 'CNY/share', 'calculation_method': 'DCF',
            'calculation_formula': 'discounted owner earnings',
            'assumptions': {'discount_rate': '10%', 'growth_rate': '4%'},
            'valuation_as_of': '2026-09-02',
        }],
    }
    payload.update(overrides)
    manifest = tmp_path / 'evidence.json'
    manifest.write_text(json.dumps(payload), encoding='utf-8')
    return manifest


def test_verified_exchange_evidence_captures_valuation_basis(tmp_path: Path) -> None:
    records, status, reviewed = load_evidence_manifest(write_manifest(tmp_path))

    assert status == 'verified'
    assert reviewed is True
    assert records[0].point_metadata['source_type'] == 'exchange'
    assert records[0].point_metadata['valuation']['calculation_method'] == 'DCF'


def test_verified_evidence_rejects_unapproved_exchange_host(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path, source_url='https://example.test/fake.pdf')

    with pytest.raises(ValueError, match='approved exchange disclosure host'):
        load_evidence_manifest(manifest)


def test_fair_value_requires_calculation_basis(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    del payload['points'][0]['assumptions']
    manifest.write_text(json.dumps(payload), encoding='utf-8')

    with pytest.raises(ValueError, match='fair_value requires: assumptions'):
        load_evidence_manifest(manifest)

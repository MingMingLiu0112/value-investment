"""Adopt retained annual evidence without rewriting source or verification state."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

from ...financial_quality import _accepted
from ...m2_discovery_engine import _point_available_at
from ...m2_opportunity_discovery import discovery_receipt_from_payload


def load_retained_financial_export(path: Path, *, evaluation_at=None):
    if not path.exists():
        return [], {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    points = payload.get("points") or []
    if evaluation_at is not None and 'annual_points' in payload:
        points, adoption = adopt_annual_export(path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            evaluation_at=evaluation_at, base_points=points)
        payload = dict(payload, annual_evidence_adoption=adoption)
    return points, payload


def financial_fetched_at(payload):
    generated_at = payload.get("retained_generated_at") or payload.get("generated_at")
    if generated_at:
        return datetime.fromisoformat(str(generated_at))
    point_times = [
        str(point.get("fetched_at") or point.get("created_at") or "")
        for point in payload.get("points") or []
        if point.get("fetched_at") or point.get("created_at")
    ]
    if point_times:
        return datetime.fromisoformat(max(point_times))
    raise RuntimeError("Retained financial export has no generated_at or point timestamp")


def retained_run_clock(output_dir: Path):
    """Recover the original PIT clock instead of restamping retained inputs."""
    receipt_path = output_dir / "receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError(
            "--reuse-inputs requires an existing receipt.json; refusing to relabel "
            "retained inputs with the current clock"
        )
    receipt = discovery_receipt_from_payload(json.loads(receipt_path.read_text(encoding="utf-8")))
    return receipt.generated_at, receipt.quote_date or receipt.as_of.isoformat(), receipt.run_id


def adopt_annual_export(path: Path, *, sha256: str, evaluation_at, base_points):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError('supplementary financial export hash mismatch')
    payload = json.loads(raw)
    annual = payload.get('annual_points')
    if not isinstance(annual, list):
        raise ValueError('supplementary export requires annual_points')
    merged = list(base_points)
    identities = {p['data_point_id']: p for p in merged if p.get('data_point_id')}
    added = []
    excluded = Counter()
    for point in annual:
        identity = point.get('data_point_id')
        if not identity:
            raise ValueError('annual fact has no retained data_point_id')
        if not str(point.get('period_label', '')).endswith('-12-31'):
            raise ValueError('nonannual fact in annual_points')
        if _point_available_at(point, evaluation_at) is None:
            excluded['not_available_at_cutoff'] += 1
            continue
        if identity in identities:
            if identities[identity] != point:
                raise ValueError('conflicting retained financial identity')
            excluded['already_present'] += 1
            continue
        identities[identity] = point
        merged.append(point)
        added.append(point)
    return merged, {
        'source_path': str(path), 'sha256': sha256, 'annual_rows': len(annual),
        'added_rows': len(added), 'added_symbols': len({p['symbol'] for p in added}),
        'added_accepted_rows': sum(_accepted(p) for p in added),
        'added_official_rows': sum(p.get('source_name') == 'CNINFO statutory disclosure' for p in added),
        'added_accepted_official_rows': sum(_accepted(p) and p.get('source_name') == 'CNINFO statutory disclosure' for p in added),
        'added_fields': dict(Counter(p['field_name'] for p in added)), 'excluded': dict(excluded),
        'new_verification_or_approval_count': 0,
    }

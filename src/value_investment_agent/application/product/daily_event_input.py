"""Bind an acquired M1 scan to daily inputs without inventing scan coverage."""
from datetime import datetime, timezone, timedelta, time
from pathlib import Path

from ...event_scan import load_event_scan_payload
from .common import load_json_object, require_inside, sha256_file


def project_daily_event_input(*, root: Path, path: Path, expected_sha256: str,
                              symbol: str, now: datetime) -> dict:
    root = root.resolve()
    path = require_inside(root, path, 'daily event scan')
    if now.utcoffset() is None:
        raise ValueError('daily event acquisition clock requires timezone')
    ref = dict(id='daily-original-' + expected_sha256, symbol=symbol,
               path=path.relative_to(root).as_posix(), sha256=expected_sha256)
    scan = load_event_scan_payload(ref, root=root)
    if scan.retrieved_at > now:
        raise ValueError('event scan acquisition is in the future')
    cst = timezone(timedelta(hours=8))
    if scan.scan_to > scan.retrieved_at.astimezone(cst).date():
        raise ValueError('event scan end follows acquisition day')
    raw = load_json_object(path, 'daily event scan')
    sources = [dict(path=ref['path'], sha256=expected_sha256,
                    observed_at=scan.retrieved_at.isoformat(), role='raw_scan')]
    refs = list(scan.evidence_refs)
    if raw.get('index_binding'):
        refs.append(raw['index_binding'])
    for item in refs:
        source = require_inside(root, root / item['path'], 'daily event original')
        if sha256_file(source) != item['sha256']:
            raise ValueError('daily event original hash mismatch')
        sources.append(dict(path=source.relative_to(root).as_posix(),
            sha256=item['sha256'], observed_at=scan.retrieved_at.isoformat(),
            role='scan_bound_original', observation_basis='SCAN_BATCH_ACQUISITION_NOT_PUBLICATION'))
    watermark = raw.get('covered_through')
    point = datetime.fromisoformat(watermark) if watermark else None
    if point is not None and (point.utcoffset() is None or point > scan.retrieved_at):
        raise ValueError('event coverage watermark requires timezone and cannot follow acquisition')
    complete = (scan.coverage_status == 'COMPLETE' and point is not None
        and point.astimezone(cst).date() == scan.scan_to
        and point.astimezone(cst).time() >= time(15, 5))
    return dict(schema_version='shadow-daily-event-input-v1', action='no_order',
        simulation_only=False, symbols=[symbol], observed_at=scan.retrieved_at.isoformat(),
        scan_as_of=(point or scan.retrieved_at).isoformat(),
        scan_cutoff_basis='EXPLICIT_PROVIDER_WATERMARK' if point else 'ACQUISITION_ONLY_NOT_COVERAGE_CUTOFF',
        coverage_complete=bool(complete), coverage_status=scan.coverage_status,
        scan_from=scan.scan_from.isoformat(), scan_to=scan.scan_to.isoformat(),
        materiality_approved=False, raw_scan=ref, source_bindings=sources,
        blockers=list(scan.blockers), action_scope='INPUT_PROJECTION_NOT_RESEARCH_APPROVAL')

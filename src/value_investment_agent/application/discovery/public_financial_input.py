"""Supplement missing financial coverage without replacing admitted retained facts."""
from datetime import datetime, timezone
from pathlib import Path

from ...infrastructure.screening.financial_export_v2 import load_retained_financial_export
from ...infrastructure.screening.public_financial_snapshot import (
    collect_public_annual_summary, load_public_annual_summary,
)


def build_financial_input(*, root: Path, output_dir: Path, collect_public: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    points, retained = load_retained_financial_export(
        root / 'runtime/server-export-payload.json', evaluation_at=now)
    payload = dict(points=points, retained_generated_at=retained.get('generated_at'),
        input_adapter_version='financial-export-v2',
        annual_evidence_adoption=retained.get('annual_evidence_adoption'),
        status='RETAINED_POINTS_NOT_NEW_APPROVAL' if points else 'NOT_AVAILABLE',
        gap_reason=None if points else 'MISSING_OR_EMPTY_RETAINED_FINANCIAL_EXPORT')
    if not collect_public:
        return payload
    period = str(now.year - (1 if now.month >= 5 else 2)) + '-12-31'
    try:
        binding = collect_public_annual_summary(root=root, output_dir=output_dir / 'public-financial-originals',
                                              period=period, allow_network=True)
        public_points, info = load_public_annual_summary(root=root, binding=binding,
                                                        evaluation_at=datetime.now(timezone.utc))
    except (ValueError, KeyError, OSError) as error:
        payload['public_financial_input'] = dict(status='ACQUISITION_FAILED',
            error_type=type(error).__name__, action='no_order')
        return payload
    # Supplemental observations must not win an existing company's period/value selection.
    retained_symbols = {p['symbol'] for p in points}
    supplements = [p for p in public_points if p['symbol'] not in retained_symbols]
    info['retained_symbols_preserved'] = sorted(retained_symbols)
    info['adopted_observation_count'] = len(supplements)
    payload.update(points=[*points, *supplements], public_financial_input=info)
    if supplements:
        payload.update(status='RETAINED_AND_PROVIDER_OBSERVATIONS' if points else 'PROVIDER_OBSERVATIONS_ONLY',
                       gap_reason='OFFICIAL_FINANCIAL_ADMISSION_NOT_GRANTED',
                       input_adapter_version='financial-export-v2+public-annual-summary-v1',
                       retained_generated_at=retained.get('generated_at') or info['generated_at'])
    return payload


def verify_public_supplement(*, root: Path, payload: dict, evaluation_at: datetime):
    info = payload.get('public_financial_input')
    public = [p for p in payload.get('points', []) if str(p.get('data_point_id', '')).startswith('public-summary-')]
    if not info or info.get('status') == 'ACQUISITION_FAILED':
        if public:
            raise ValueError('public financial observations without complete source binding')
        return
    expected, recomputed = load_public_annual_summary(root=root, binding=info['manifest'], evaluation_at=evaluation_at)
    retained = {p['symbol'] for p in payload['points'] if not str(p.get('data_point_id', '')).startswith('public-summary-')}
    expected = [p for p in expected if p['symbol'] not in retained]
    recomputed.update(retained_symbols_preserved=sorted(retained), adopted_observation_count=len(expected))
    if recomputed != info or public != expected:
        raise ValueError('financial observations differ from retained originals')

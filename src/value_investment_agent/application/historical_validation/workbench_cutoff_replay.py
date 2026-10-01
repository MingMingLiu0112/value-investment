"""Replay observed result availability, never historical investment effectiveness."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ..product.workbench import load_existing_workbench_for_presentation
from ..product.common import write_new_json


def _aware(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.utcoffset() is None:
        raise ValueError("replay timestamps require timezone")
    return parsed.astimezone(timezone.utc)


def replay_workbench_cutoffs(*, root: Path, workbench_path: Path, workbench_sha256: str,
                             cutoffs: Sequence[datetime], output: Path | None = None) -> dict:
    """Do not backdate a produced workbench or derive availability from report date."""
    points = tuple(_aware(point) for point in cutoffs)
    if not points or tuple(sorted(set(points))) != points:
        raise ValueError("cutoffs must be nonempty, unique and increasing")
    payload = load_existing_workbench_for_presentation(
        root=root, path=workbench_path, expected_sha256=workbench_sha256)
    research = payload['research']
    if (research.get('action') != 'no_order' or research.get('suggested_state') != 'NOT_READY'
            or research.get('position_guidance') is not None):
        raise ValueError("cutoff replay cannot admit investment decisions")
    known_at = max([_aware(payload['generated_at']),
                    _aware(research['dependency_view']['observed_at']),
                    *(_aware(record['observed_at']) for record in research['source_records'])])
    rows = []
    for point in points:
        known = point >= known_at
        rows.append(dict(cutoff=point.isoformat(), symbol=payload['symbol'],
            status='EXISTING_RESEARCH_ONLY' if known else 'RESULT_NOT_YET_OBSERVED',
            valuation=research['valuation'] if known else None,
            evidence_refs=[dict(path=record['path'], sha256=record['sha256'])
                           for record in research['source_records']] if known else [],
            blockers=list(research['blockers']) if known else ['Pinned workbench result was produced after this cutoff.'],
            suggested_state='NOT_READY', position_guidance=None, current_price=None,
            action='no_order', orders=[], fills=[]))
    result = dict(schema_version='observed-workbench-cutoff-replay-v1',
        scope='OBSERVED_RESULT_AVAILABILITY_ONLY', symbol=payload['symbol'],
        workbench_sha256=workbench_sha256, result_known_at=known_at.isoformat(), rows=rows,
        action='no_order', strict_pit_admitted=False, historical_execution_validated=False,
        performance_claim_allowed=False, contemporaneous_rule_proven=False,
        limitation='Replays when this retained result was observed; does not reconstruct earlier public information or validate a trading strategy.')
    if output is not None:
        resolved = output.resolve()
        if not resolved.is_relative_to(root.resolve() / 'runtime'):
            raise ValueError('replay output must remain under runtime')
        write_new_json(resolved, result)
    return result

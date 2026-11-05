"""Reverify a bounded official filing example, never a current stock candidate."""
from datetime import date, datetime
from pathlib import Path
import json
import re

from ..hotspot.corporate_action_coverage import inspect_official_action_coverage
from .common import normalize_symbol, require_inside, sha256_file


def load_historical_action_lineage(*, root: Path, observation_binding: dict, now: datetime) -> dict:
    root = root.resolve()
    if now.utcoffset() is None or set(observation_binding) != {'path', 'sha256'}:
        raise ValueError('Exact public observation and aware review clock required')
    relative = observation_binding['path']
    if (not isinstance(relative, str) or not relative.startswith('runtime/')
            or not re.fullmatch(r'[a-f0-9]{64}', str(observation_binding['sha256']))):
        raise ValueError('Invalid official observation binding')
    path = require_inside(root, root / relative, 'historical official observation')
    if path.stat().st_size > 4 * 1024**2 or sha256_file(path) != observation_binding['sha256']:
        raise ValueError('Historical official observation Hash mismatch')
    observation = json.loads(path.read_bytes())
    if (observation['schema_version'] != 'daily-event-observation-v1'
            or observation['action'] != 'no_order' or not isinstance(observation['symbol'], str)):
        raise ValueError('Unsupported official observation')
    symbol = normalize_symbol(observation['symbol'])
    coverage = inspect_official_action_coverage(root=root, symbol=symbol,
        start=date.fromisoformat(observation['scan_from']), end=date.fromisoformat(observation['scan_to']),
        now=now, observation_binding=observation_binding)
    if coverage['official_publication_coverage'] != 'COMPLETE' or not coverage.get('lineage_review'):
        raise ValueError('Official original window cannot be replayed')
    lineage = coverage['lineage_review']
    if (lineage['action'] != 'no_order' or lineage['complete_chain_proven'] is not False
            or lineage['comparison_allowed'] is not False or lineage['historical_availability_proven'] is not False):
        raise ValueError('Historical example must not grant price or PIT authority')
    references = coverage['evidence_bindings']
    if not isinstance(references, list) or not 1 <= len(references) <= 64:
        raise ValueError('Historical evidence closure is invalid')
    # Parsing reads several originals; recheck the entire closure before publishing it.
    for reference in [observation_binding, *references]:
        source = require_inside(root, root / reference['path'], 'historical original')
        if sha256_file(source) != reference['sha256']:
            raise ValueError('Historical evidence changed during replay')
    return dict(schema_version='historical-official-action-lineage-v1', action='no_order',
        status='HISTORICAL_SOURCE_REPLAYED', symbol=symbol, evaluated_at=now.isoformat(),
        scope='HISTORICAL_FILING_RELATION_NOT_CURRENT_CANDIDATE_OR_TRADE',
        source_available_at=coverage['source_available_at'], filing_window=coverage['publication_window'],
        observation_binding=dict(observation_binding), lineage_review=lineage,
        evidence_bindings=coverage['evidence_bindings'],
        complete_chain_proven=False, comparison_allowed=False, historical_pit_proven=False,
        formal_eligibility=False, strategy_validation='NOT_PROVEN',
        limitations=['原件取得时点不等于历史决策时点，不能回填历史PIT。',
            '单份明确关联不证明完整修订链、期初公司行动状态或非现金价格口径。',
            '本例不是当前候选、持仓、原始Entry或加减仓指令。'])

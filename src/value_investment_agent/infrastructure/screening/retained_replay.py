"""Hash-checked, read-only investigation of retained four-channel inputs."""
from collections import Counter
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from ...financial_quality import GENERAL_FIELDS, _accepted
from ...m2_discovery_engine import M2ScreeningPolicy, _point_available_at
from .evidence_screen_v3 import build_discovery_receipt, evaluate_financial_quality
from .financial_export_v2 import adopt_annual_export
from ...m2_opportunity_discovery import discovery_receipt_from_payload


def replay_retained(root: Path, directory: Path, *, annual_export: Path | None = None,
                    annual_export_sha256: str | None = None) -> tuple[dict, dict]:
    """Rebuild at the original clock; never promote facts or publish pointers."""
    raw = (directory / 'receipt.json').read_bytes()
    original = discovery_receipt_from_payload(json.loads(raw))
    refs = {ref.id: ref for ref in original.evidence_refs}
    payloads = {}
    for key in ('official', 'tencent', 'sina', 'dividend', 'financial'):
        ref = refs[key]
        path = (root / ref.path).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError('source outside repository')
        source = path.read_bytes()
        if hashlib.sha256(source).hexdigest() != ref.sha256:
            raise ValueError(f'{key} source hash mismatch')
        payloads[key] = json.loads(source)
    policy_payload = json.loads((directory / 'policy.json').read_bytes())
    policy = M2ScreeningPolicy(**{k: (v if isinstance(v, int) or k == 'rule_version' else Decimal(v))
                                  for k, v in policy_payload.items()})
    adoption = None
    if annual_export is None and isinstance(payloads['financial'].get('annual_points'), list):
        annual_export = root / refs['financial'].path
        annual_export_sha256 = refs['financial'].sha256
    if annual_export is not None:
        export_payload = json.loads(annual_export.read_bytes())
        if export_payload.get('points') != payloads['financial']['points']:
            raise ValueError('annual export base points differ from retained snapshot')
        merged, adoption = adopt_annual_export(annual_export, sha256=annual_export_sha256,
            evaluation_at=original.generated_at, base_points=payloads['financial']['points'])
        payloads['financial']['points'] = merged
        refs['financial'] = replace(refs['financial'], path=str(annual_export.relative_to(root)),
            sha256=annual_export_sha256, fetched_at=datetime.fromisoformat(export_payload['generated_at']),
            source_name='Retained financial export points + annual_points v2')
    receipt = build_discovery_receipt(
        run_id=original.run_id, generated_at=original.generated_at,
        official_payload=payloads['official'], tencent_payload=payloads['tencent'],
        sina_payload=payloads['sina'], dividend_payload=payloads['dividend'],
        financial_points=payloads['financial']['points'], quote_date=original.quote_date,
        run_refs=refs, policy=policy, quote_date_verified=False,
    )
    points = payloads['financial']['points']
    code_paths = ('financial_quality.py', 'm2_discovery_engine.py',
                  'infrastructure/screening/retained_replay.py',
                  'infrastructure/screening/evidence_screen_v3.py',
                  'infrastructure/screening/financial_export_v2.py')
    package_root = Path(__file__).resolve().parents[2]
    universe = {row.symbol: row for row in original.universe.records}
    grouped = {}
    for point in points:
        if _point_available_at(point, original.generated_at) is not None:
            grouped.setdefault(point['symbol'], []).append(point)
    missing = Counter()
    periods = Counter()
    quality_states = Counter()
    accepted_fields = Counter()
    for symbol, rows in grouped.items():
        if symbol not in universe:
            continue
        company = universe[symbol]
        result = evaluate_financial_quality(symbol, company.name, company.official_industry, rows,
                                           evaluation_date=original.generated_at.date())
        quality_states[result.quality_status] += 1
        if result.model_type != 'general_enterprise':
            continue
        periods[str(result.calculation_details.get('period'))] += 1
        missing.update(result.calculation_details.get('missing_fields', []))
        accepted_fields.update(result.calculation_details.get('accepted_fields', []))

    def channel_counts(run):
        return {key: {'statuses': dict(Counter(row.status for row in channel.evaluations)),
                      'displayed_candidates': len(channel.candidates)}
                for key, channel in run.channel_results.items()}

    return {
        'action': 'no_order', 'mode': 'HISTORICAL_REPLAY_NOT_CURRENT_SCREEN',
        'evaluation_at': original.generated_at.isoformat(), 'quote_date': original.quote_date,
        'original_receipt_sha256': hashlib.sha256(raw).hexdigest(),
        'policy_sha256': hashlib.sha256((directory / 'policy.json').read_bytes()).hexdigest(),
        'implementation_sha256': {name: hashlib.sha256((package_root / name).read_bytes()).hexdigest()
                                  for name in code_paths},
        'sources': [ref.as_policy() for ref in refs.values()],
        'original_sources': [ref.as_policy() for ref in original.evidence_refs],
        'annual_evidence_adoption': adoption,
        'universe_count': len(universe), 'financial_point_count': len(points),
        'financial_symbols_raw': len({p['symbol'] for p in points}),
        'symbols_with_nonprice_points': len({p['symbol'] for p in points if p['field_name'] != 'current_price'}),
        'symbols_with_general_quality_fields': len({p['symbol'] for p in points if p['field_name'] in GENERAL_FIELDS}),
        'point_fields': dict(Counter(p['field_name'] for p in points)),
        'financial_symbols_available_in_universe': len(set(grouped) & set(universe)),
        'universe_without_available_financial_points': len(set(universe) - set(grouped)),
        'quality_states': dict(quality_states), 'selected_general_periods': dict(periods),
        'missing_latest_period_fields': dict(missing), 'accepted_latest_period_fields': dict(accepted_fields),
        'debt_points': len([p for p in points if p['field_name'] == 'interest_bearing_debt']),
        'accepted_debt_points': len([p for p in points if p['field_name'] == 'interest_bearing_debt' and _accepted(p)]),
        'roic_points': len([p for p in points if p['field_name'] == 'roic']),
        'accepted_roic_points': len([p for p in points if p['field_name'] == 'roic' and _accepted(p)]),
        'roic_in_quality_score': 'roic' in GENERAL_FIELDS,
        'before': channel_counts(original), 'after': channel_counts(receipt),
        'before_deduplicated_leads': len(original.candidate_pool()),
        'after_deduplicated_leads': len(receipt.candidate_pool()),
        'candidate_signature_unchanged': receipt.candidate_signature == original.candidate_signature,
        'data_health': receipt.data_health.as_policy(),
    }, receipt.as_policy()

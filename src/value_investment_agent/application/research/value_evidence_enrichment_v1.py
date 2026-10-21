"""Versioned debt-scope validation and retained-fact quality re-evaluation."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from ...financial_quality import _accepted
from ...infrastructure.screening.evidence_screen_v3 import evaluate_financial_quality
from ...infrastructure.screening.value_evidence_enrichment_v1 import (
    DEBT_LABELS, RetainedAnnualSource, extract_retained_annual,
)
from ...m2_discovery_engine import _point_available_at

VERSION = 'value-debt-scope-enrichment-v1'
CORRELATION_METHOD = 'official_pdf_plus_independent_structured_source'
STRUCTURED_SOURCES = {
    'AkShare / Sina detailed financial statements',
    'AkShare / Sina financial indicators',
}


def validate_debt_scope(symbol: str, period: str, components: list[dict], *,
                        evaluation_at: datetime) -> dict:
    """Validate existing verified classifications, never infer scope from blanks.

    Components are mutually exclusive financing buckets. Current maturities
    include current leases; only NONCURRENT leases/payables may be added again.
    The final scope review must address notes, factoring and other financing.
    """
    issues = []
    grouped = {}
    total = Decimal('0')
    fact_ids = []
    for row in components:
        field = row.get('field_name')
        if field not in DEBT_LABELS:
            issues.append(f'UNEXPECTED_COMPONENT:{field}')
            continue
        if field in grouped:
            issues.append(f'DUPLICATE_COMPONENT:{field}')
        grouped[field] = row
    for field in DEBT_LABELS:
        row = grouped.get(field)
        if row is None:
            issues.append(f'MISSING_COMPONENT:{field}')
            continue
        meta = row.get('metadata') or {}
        if row.get('symbol') != symbol or row.get('period_label') != period:
            issues.append(f'IDENTITY_OR_PERIOD_MISMATCH:{field}')
        if (row.get('unit') != 'CNY' or meta.get('currency') != 'CNY'
                or meta.get('statement_scope') != 'consolidated'):
            issues.append(f'UNIT_CURRENCY_OR_SCOPE_MISMATCH:{field}')
        if not _accepted(row) or _point_available_at(row, evaluation_at) is None:
            issues.append(f'UNVERIFIED_OR_UNAVAILABLE:{field}')
        if not row.get('data_point_id') or not row.get('source_id'):
            issues.append(f'MISSING_FACT_IDENTITY:{field}')
        if not all(meta.get(k) for k in ('secondary_data_point_id', 'secondary_source_id', 'secondary_source_url')):
            issues.append(f'MISSING_INDEPENDENT_CORRELATION:{field}')
        binding = meta.get('official_evidence') or {}
        if (not binding.get('sha256') or len(str(binding.get('sha256'))) != 64
                or not isinstance(binding.get('page'), int) or binding.get('page', 0) < 1
                or not binding.get('excerpt') or not binding.get('source_url')):
            issues.append(f'MISSING_OFFICIAL_BINDING:{field}')
        classification = meta.get('debt_classification')
        if classification not in {'included', 'excluded', 'not_applicable', 'scope_review'}:
            issues.append(f'UNRESOLVED_CLASSIFICATION:{field}')
        if not meta.get('classification_reason') or meta.get('debt_scope_reviewed') is not True:
            issues.append(f'MISSING_SCOPE_REVIEW:{field}')
        try:
            reviewed = datetime.fromisoformat(meta.get('debt_scope_reviewed_at', ''))
            if reviewed.tzinfo is None or reviewed > evaluation_at:
                raise ValueError
        except (ValueError, TypeError):
            issues.append(f'SCOPE_REVIEW_UNAVAILABLE_AT_CUTOFF:{field}')
        if field == 'other_financing_scope':
            if classification != 'scope_review' or meta.get('other_financing_exhaustive') is not True:
                issues.append('OTHER_FINANCING_NOT_EXHAUSTIVELY_REVIEWED')
        elif classification == 'scope_review':
            issues.append(f'AMOUNT_BUCKET_REQUIRES_CLASSIFICATION:{field}')
        if field == 'current_portion_long_term_debt' and meta.get('debt_only_including_current_leases') is not True:
            issues.append('CURRENT_MATURITIES_SCOPE_UNRESOLVED')
        if field in {'lease_liabilities_noncurrent', 'financing_payables_noncurrent'} and meta.get('noncurrent_only') is not True:
            issues.append(f'POSSIBLE_CURRENT_PORTION_DOUBLE_COUNT:{field}')
        if classification == 'included' and meta.get('financing_only') is not True:
            issues.append(f'OPERATING_LIABILITIES_NOT_EXCLUDED:{field}')
        if classification != 'scope_review':
            try:
                value = Decimal(str(row.get('value')))
                if not value.is_finite() or value < 0:
                    raise InvalidOperation
                if classification == 'included':
                    total += value
            except (InvalidOperation, ValueError):
                issues.append(f'INVALID_AMOUNT:{field}')
        fact_ids.append(row.get('data_point_id'))
    if len(set(fact_ids)) != len(fact_ids):
        issues.append('REUSED_COMPONENT_FACT_ID')
    complete = not issues
    return dict(version=VERSION, symbol=symbol, period=period,
                status='SCOPE_CONTRACT_VALIDATED_PENDING_SOURCE_BINDING' if complete else 'DATA_GAP',
                scope_contract_complete=complete, complete_debt_verified=False,
                value=str(total) if complete else None,
                unit='CNY', input_fact_ids=fact_ids, issues=issues,
                automatic_cross_source_verification_created=False)


def enrich_retained_company(root: Path, source: RetainedAnnualSource, points: list[dict], *,
                            evaluation_at: datetime, cache_dir: Path,
                            name: str | None = None, sector: str | None = None,
                            components: list[dict] | None = None) -> dict:
    """Extract, match existing facts, validate scope and re-run unchanged scoring.

    Candidate matches never change a fact's original validation flags. Only
    already admitted PIT facts enter re-evaluation. No database/pointer writes.
    """
    original = deepcopy(points)
    packet = extract_retained_annual(root, source, evaluation_at=evaluation_at, cache_dir=cache_dir)
    company = [deepcopy(p) for p in points if p.get('symbol') == source.symbol
               and _point_available_at(p, evaluation_at) is not None]
    before = evaluate_financial_quality(source.symbol, name, sector, company,
                                        evaluation_date=evaluation_at.date())
    if components is None:
        # Existing numeric balances remain unclassified until note review.
        components = [p for p in company if p.get('field_name') in DEBT_LABELS
                      and p.get('period_label') == source.period]
    scope = validate_debt_scope(source.symbol, source.period, components,
                                evaluation_at=evaluation_at)
    binding_issues = []
    for component in components:
        meta = component.get('metadata') or {}
        retained = [p for p in company if p.get('data_point_id') == component.get('data_point_id')]
        if len(retained) != 1 or retained[0] != component:
            binding_issues.append(f'CLASSIFIED_COMPONENT_NOT_RETAINED:{component.get("field_name")}')
        binding = meta.get('official_evidence') or {}
        page = binding.get('page')
        excerpt = ''.join(str(binding.get('excerpt', '')).split())
        if (binding.get('sha256') != source.sha256 or binding.get('source_url') != source.source_url
                or not isinstance(page, int) or not 1 <= page <= packet['page_count']
                or not excerpt or excerpt not in ''.join(packet['page_texts'][page - 1].split())):
            binding_issues.append(f'ORIGINAL_BINDING_MISMATCH:{component.get("field_name")}')
        elif ((component.get('metadata') or {}).get('debt_classification') == 'included'
              and str(component.get('value')).replace(',', '') not in excerpt.replace(',', '')):
            binding_issues.append(f'AMOUNT_NOT_BOUND_TO_EXCERPT:{component.get("field_name")}')
        secondary = [p for p in company if p.get('data_point_id') == meta.get('secondary_data_point_id')]
        if len(secondary) != 1:
            binding_issues.append(f'INDEPENDENT_FACT_NOT_RETAINED:{component.get("field_name")}')
        else:
            second = secondary[0]
            if (second.get('source_id') != meta.get('secondary_source_id')
                    or second.get('source_id') == component.get('source_id')
                    or second.get('source_url') != meta.get('secondary_source_url')
                    or urlparse(str(second.get('source_url', ''))).hostname == urlparse(source.source_url).hostname
                    or second.get('sha256') in (None, source.sha256)
                    or second.get('field_name') != component.get('field_name')
                    or second.get('period_label') != source.period
                    or second.get('unit') != component.get('unit')
                    or second.get('value') != component.get('value')
                    or (second.get('metadata') or {}).get('statement_scope') != 'consolidated'
                    or (second.get('metadata') or {}).get('evidence_quarantine')):
                binding_issues.append(f'INDEPENDENT_CORRELATION_MISMATCH:{component.get("field_name")}')
            if not _accepted(second) or _point_available_at(second, evaluation_at) is None:
                binding_issues.append(f'INDEPENDENT_FACT_UNVERIFIED_OR_UNAVAILABLE:{component.get("field_name")}')
            # Different hosts/hashes alone establish no independence. Use the
            # existing registered official-plus-structured method and backing
            # bytes; mirrors of the statutory PDF cannot satisfy this method.
            if (meta.get('verification_method') != CORRELATION_METHOD
                    or second.get('source_name') not in STRUCTURED_SOURCES
                    or urlparse(str(second.get('source_url', ''))).hostname not in {
                        'vip.stock.finance.sina.com.cn', 'money.finance.sina.com.cn'}):
                binding_issues.append(f'INDEPENDENT_METHOD_NOT_ESTABLISHED:{component.get("field_name")}')
            source_path = second.get('source_path') or (second.get('metadata') or {}).get('source_path')
            try:
                if not source_path:
                    raise ValueError('missing backing path')
                backing = (root / source_path).resolve()
                if not backing.is_relative_to(root.resolve()) or backing.stat().st_size > 30_000_000:
                    raise ValueError('backing path/budget invalid')
                if hashlib.sha256(backing.read_bytes()).hexdigest() != second.get('sha256'):
                    raise ValueError('backing hash mismatch')
            except (OSError, ValueError, TypeError):
                binding_issues.append(f'INDEPENDENT_BACKING_BYTES_UNVERIFIED:{component.get("field_name")}')
    if binding_issues:
        scope.update(status='DATA_GAP', complete_debt_verified=False, value=None,
                     issues=scope['issues'] + binding_issues)
    elif scope['scope_contract_complete']:
        scope.update(status='COMPLETE_SCOPE_VALIDATED', complete_debt_verified=True)
    matches = []
    for candidate in packet['candidates'] + packet['debt_balance_candidates']:
        ids = [p['data_point_id'] for p in company
               if p.get('data_point_id') and p.get('period_label') == source.period
               and p.get('field_name') == candidate['field_name']
               and p.get('unit') == candidate['unit']
               and Decimal(str(p.get('value'))) == Decimal(candidate['value'])]
        matches.append(dict(candidate=candidate, matching_retained_fact_ids=ids,
                            verification_created=False))
    # Complete scope is necessary but not sufficient to manufacture the scorer's
    # independent verification flag. Retain the existing aggregate's assurance.
    adopted = []
    if scope['complete_debt_verified']:
        for p in company:
            if (p['field_name'] == 'interest_bearing_debt' and p['period_label'] == source.period
                    and p.get('unit') == 'CNY' and Decimal(str(p['value'])) == Decimal(scope['value'])
                    and p.get('validation_status') == 'verified'
                    and (p.get('metadata') or {}).get('statement_scope') == 'consolidated'
                    and (p.get('metadata') or {}).get('currency') == 'CNY'
                    and (p.get('metadata') or {}).get('automatic_cross_source_verification') is True
                    and not (p.get('metadata') or {}).get('evidence_quarantine')):
                meta = p.setdefault('metadata', {})
                meta.update(complete_debt_verified=True, debt_scope_validation=scope,
                            derivation_formula=VERSION)
                adopted.append(p['data_point_id'])
    after = evaluate_financial_quality(source.symbol, name, sector, company,
                                       evaluation_date=evaluation_at.date())
    assert points == original
    return dict(version=VERSION, symbol=source.symbol, period=source.period,
                evaluation_at=evaluation_at.isoformat(), mode='RETAINED_SOURCE_REEVALUATION',
                source_extraction=packet, candidate_matches=matches, debt_scope=scope,
                before=asdict(before), after=asdict(after), adopted_debt_fact_ids=adopted,
                input_points_sha256=hashlib.sha256(json.dumps(points, sort_keys=True, default=str).encode()).hexdigest(),
                state='QUALITY_EVALUATED' if after.total_score is not None else 'DATA_UNAVAILABLE',
                next_action=('RETAIN_CURRENT_RESEARCH_GATES' if after.total_score is not None
                             else 'VERIFY_MISSING_SAME_PERIOD_FACTS_AND_DEBT_NOTE_CLASSIFICATIONS'),
                verification_created=False, formal_eligibility=False, action='no_order')

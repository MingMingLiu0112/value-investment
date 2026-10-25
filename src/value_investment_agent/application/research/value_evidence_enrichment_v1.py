"""Versioned debt-scope validation and retained-fact quality re-evaluation."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
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
RATIO_VERSION = 'value-sourced-balance-ratio-v1'
GROWTH_VERSION = 'value-sourced-income-growth-v1'
PUBLIC_PROFIT_VERSION = 'value-official-public-parent-profit-v1'
OFFICIAL_BALANCE_VERSION = 'OFFICIAL_BALANCE_RECONCILIATION_V1'
DERIVED_VERSIONS = {VERSION, RATIO_VERSION, GROWTH_VERSION, PUBLIC_PROFIT_VERSION, OFFICIAL_BALANCE_VERSION}
CORRELATION_METHOD = 'official_pdf_plus_independent_structured_source'
STRUCTURED_SOURCES = {
    'AkShare / Sina detailed financial statements',
    'AkShare / Sina financial indicators',
}
FINANCIAL_FUNDING_FIELDS = frozenset({
    'financial_deposits_and_interbank', 'central_bank_borrowings',
    'interbank_borrowings', 'repurchase_financing',
})


def _public_profit_binding(points, source, explicit=None):
    bindings = [p['metadata'].get('public_summary_binding') for p in points
        if p.get('symbol') == source.symbol and p.get('period_label') == source.period
        and (p.get('metadata') or {}).get('derivation_formula') == PUBLIC_PROFIT_VERSION]
    if explicit is not None:
        bindings.append(explicit)
    if not bindings:
        return None
    if (not isinstance(bindings[0], dict) or set(bindings[0]) != {'path', 'sha256'}
            or any(binding != bindings[0] for binding in bindings)):
        raise ValueError('Conflicting or missing public profit source binding')
    return deepcopy(bindings[0])


def _correlate_public_parent_profit(root, source, packet, binding, evaluation_at):
    """Recheck provider bytes plus an official parent-profit row, not E1 flags."""
    if binding is None:
        return [], dict(status='NOT_REQUESTED', issues=[])
    from ...infrastructure.screening.public_financial_snapshot import load_public_annual_summary

    points, _ = load_public_annual_summary(root=root, binding=binding, evaluation_at=evaluation_at)
    matches = [p for p in points if p['symbol'] == source.symbol
        and p['period_label'] == source.period and p['field_name'] == 'net_income'
        and p['unit'] == 'CNY' and p['currency'] == 'CNY']
    candidates = [c for c in packet['candidates'] if c['field_name'] == 'net_income'
        and c['unit'] == 'CNY' and c.get('source_label') in {
            '\u5f52\u5c5e\u4e8e\u4e0a\u5e02\u516c\u53f8\u80a1\u4e1c\u7684\u51c0\u5229\u6da6',
            '\u5f52\u5c5e\u4e8e\u6bcd\u516c\u53f8\u80a1\u4e1c\u7684\u51c0\u5229\u6da6'}]
    amounts = {Decimal(c['value']) for c in candidates}
    if (len(matches) != 1 or len(amounts) != 1
            or not all(amount.is_finite() for amount in amounts)):
        return [], dict(status='DATA_GAP', issues=['PARENT_PROFIT_MISSING_OR_AMBIGUOUS'])
    secondary, amount = matches[0], next(iter(amounts))
    if Decimal(secondary['value']) != amount:
        return [], dict(status='SOURCE_CONFLICT', issues=['PARENT_PROFIT_EXACT_AMOUNT_CONFLICT'])
    known_at = max(datetime.fromisoformat(source.available_at),
                   datetime.fromisoformat(secondary['available_at'])).isoformat()
    refs = [dict(id='official-parent-profit:' + str(c['page']), path=source.path,
        sha256=source.sha256, source_url=source.source_url, page=c['page'],
        excerpt=c['excerpt'], label=c['source_label']) for c in candidates]
    secondary_binding = secondary['metadata']['source_binding']
    refs.extend([dict(id=secondary['data_point_id'], path=secondary_binding['path'],
        sha256=secondary_binding['sha256'], source_url=secondary['source_url'],
        source_row=secondary['metadata']['source_row'], period_label=source.period),
        dict(id='public-summary-manifest', **binding)])
    identity = dict(version=PUBLIC_PROFIT_VERSION, source=asdict(source),
        public_summary_binding=binding, secondary=secondary, official_rows=candidates,
        parser=packet['identity']['implementation_sha256'])
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    point = dict(symbol=source.symbol, field_name='net_income', period_label=source.period,
        value=str(amount), unit='CNY', source_id='official-parent-profit:' + source.sha256,
        source_name='CNINFO statutory disclosure', source_url=source.source_url,
        source_path=source.path, sha256=source.sha256, data_point_id='value-parent-profit:' + digest,
        available_at=known_at, fetched_at=known_at, created_at=known_at,
        validation_status='verified', human_reviewed=False,
        metadata=dict(derivation_formula=PUBLIC_PROFIT_VERSION,
            verification_method='official_pdf_plus_independent_structured_source',
            automatic_cross_source_verification=True, statement_scope='consolidated',
            profit_basis='attributable_to_parent', currency='CNY',
            input_fact_ids=[secondary['data_point_id']], evidence_refs=refs,
            public_summary_binding=deepcopy(binding),
            secondary_source_binding=deepcopy(secondary_binding),
            historical_pit_admission='NOT_ADMITTED', economic_approval=False,
            assurance_basis='OFFICIAL_PARENT_PROFIT_EXACT_RETAINED_PROVIDER_REPLAY'))
    return [point], dict(status='FACT_ADMITTED', field_name='net_income',
        issues=[], input_fact_ids=[secondary['data_point_id']], evidence_refs=refs)


def _source_financial_funding_scope(packet, source):
    # Keep the legacy extraction bytes/cache identity and income IDs unchanged.
    from ...infrastructure.filings.financial_funding_scope import (
        extract_financial_funding_observations, extract_funding_cash_context,
    )

    observations = extract_financial_funding_observations(packet['page_texts'], source.period)
    required = set()
    for row in observations:
        field = row.get('field_name')
        # The single helper omits empty template rows. A returned unknown row
        # requires scope resolution; it proves neither zero nor applicability.
        if field in FINANCIAL_FUNDING_FIELDS:
            required.add(field)
    unknown = any(row.get('value') is None for row in observations)
    result = dict(status=('UNKNOWN_FINANCIAL_FUNDING_AMOUNT_OR_SCOPE' if unknown else
                        'PENDING_EXPLICIT_FUNDING_CLASSIFICATION') if required else
                    'NO_AMOUNT_EVIDENCE_OF_FINANCIAL_FUNDING_NOT_A_SCOPE_CLEARANCE',
        symbol=source.symbol, period_label=source.period, observations=deepcopy(observations),
        required_fields=sorted(required), unresolved_fields=sorted(required),
        source_binding={key: getattr(source, key) for key in
                        ('path', 'sha256', 'source_url', 'available_at')},
        action='no_order', financial_fact_admitted=False)
    context_rows = extract_funding_cash_context(packet['page_texts'], source.period)
    if context_rows:
        binding = result['source_binding']
        rows = []
        for row in context_rows:
            identity = dict(symbol=source.symbol, source_binding=binding, observation=row)
            digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
            rows.append(dict(row, symbol=source.symbol, available_at=source.available_at,
                source_binding=deepcopy(binding), observation_id='funding-context:' + digest,
                evidence_kind='SOURCE_BOUND_OBSERVATION', financial_fact_admitted=False,
                formal_eligibility=False, action='no_order'))
        by_field = {row['field_name']: row for row in rows}
        derivations, blockers = [], []
        numerator = by_field.get('controlling_group_deposits')
        denominator = by_field.get('financial_deposits_and_interbank')
        if numerator and denominator:
            with localcontext() as context:
                context.prec = 48
                top, bottom = Decimal(numerator['value']), Decimal(denominator['value'])
                if 0 <= top <= bottom and bottom > 0:
                    derivations.append(dict(field_name='controlling_group_deposit_concentration',
                        value=str(top / bottom), unit='ratio', symbol=source.symbol,
                        period_label=source.period, statement_scope='consolidated_funding',
                        formula='controlling_group_deposits / financial_deposits_and_interbank',
                        input_observation_ids=[numerator['observation_id'], denominator['observation_id']],
                        available_at=source.available_at, source_binding=deepcopy(binding),
                        evidence_kind='DERIVED_RESEARCH_OBSERVATION',
                        financial_fact_admitted=False, formal_eligibility=False, action='no_order'))
                else:
                    blockers.append('CONCENTRATION_INPUTS_INCONSISTENT')
        required = {'controlling_group_deposits', 'financial_deposits_and_interbank',
                    'consolidated_cash_and_equivalents', 'issuer_parent_cash_and_equivalents'}
        missing = sorted(required - by_field.keys())
        result['research_context'] = dict(schema_version='funding-cash-research-observations-v1',
            symbol=source.symbol, period_label=source.period, source_binding=deepcopy(binding),
            status='PARTIAL' if missing or blockers else 'SOURCE_BOUND_RESEARCH_OBSERVATIONS',
            observations=rows, derivations=derivations, missing_fields=missing, blockers=blockers,
            parser_version='funding-cash-context-v1',
            parser_sha256=hashlib.sha256(Path(extract_funding_cash_context.__code__.co_filename).read_bytes()).hexdigest(),
            limitations=['SAME_PDF_NOT_INDEPENDENT_SECOND_SOURCE',
                         'GROUP_CASH_NOT_ISSUER_PARENT_DISTRIBUTABLE_CASH',
                         'CONTROLLING_GROUP_DEPOSITOR_NOT_ISSUER_PARENT_CASH',
                         'CROSS_PERIOD_CHANGE_REQUIRES_BOTH_SOURCE_CLOSURES',
                         'NO_DEBT_COMPLETENESS_OR_CASH_ACCESS_APPROVAL'],
            financial_fact_admitted=False, formal_eligibility=False, action='no_order')
    return result


def _derive_balance_ratio(source, company, packet, evaluation_at):
    """Arithmetic inherits admitted input assurance, never promotes candidates."""
    inputs, refs, issues = [], [], []
    for field in ('total_assets', 'total_liabilities'):
        eligible = []
        for point in company:
            if (point.get('field_name') != field or point.get('period_label') != source.period
                    or not _accepted(point) or point.get('unit') != 'CNY'
                    or point.get('sha256') != source.sha256
                    or point.get('source_url') != source.source_url
                    or (point.get('metadata') or {}).get('statement_scope') == 'parent'):
                continue
            candidates = [c for c in packet.get('balance_total_candidates', []) if c['field_name'] == field
                and c['unit'] == 'CNY' and Decimal(c['value']) == Decimal(str(point['value']))]
            if candidates:
                eligible.append((point, candidates[0]))
        if len(eligible) != 1:
            issues.append('MISSING_OR_AMBIGUOUS_ADMITTED_OFFICIAL_INPUT:' + field)
            continue
        point, candidate = eligible[0]
        inputs.append(point)
        refs.append(dict(id=point['data_point_id'], field_name=field, value=point['value'],
            unit='CNY', path=source.path, sha256=source.sha256, source_url=source.source_url,
            page=candidate['page'], excerpt=candidate['excerpt']))
    if issues:
        return [], {'version': RATIO_VERSION, 'status': 'REJECTED_WITH_REASON', 'issues': issues}
    assets, liabilities = (Decimal(str(p['value'])) for p in inputs)
    if not assets.is_finite() or not liabilities.is_finite() or assets <= 0 or liabilities < 0:
        return [], {'version': RATIO_VERSION, 'status': 'REJECTED_WITH_REASON',
                    'issues': ['INVALID_BALANCE_RATIO_INPUT']}
    clocks = [datetime.fromisoformat(source.available_at)]
    for point in inputs:
        clocks.extend(datetime.fromisoformat(str(point[k])) for k in
            ('available_at', 'created_at', 'fetched_at') if point.get(k))
    if any(c.utcoffset() is None or c > evaluation_at for c in clocks):
        raise ValueError('Balance ratio input unavailable at cutoff')
    known_at = max(clocks).isoformat()
    binding = dict(version=RATIO_VERSION, source=asdict(source), inputs=inputs,
                   parser=packet['identity']['implementation_sha256'])
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True, default=str).encode()).hexdigest()
    point = dict(symbol=source.symbol, field_name='debt_ratio', period_label=source.period,
        data_point_id='value-ratio:' + digest, value=str(liabilities / assets * 100), unit='percent',
        source_id='derived:' + digest, source_name='Derived from admitted official balances',
        source_url=source.source_url, sha256=source.sha256, source_path=source.path,
        created_at=known_at, fetched_at=known_at, available_at=known_at,
        validation_status='verified', human_reviewed=False,
        metadata=dict(automatic_cross_source_verification=True,
            assurance_basis='INHERITED_FROM_EXISTING_ADMITTED_INPUTS_NOT_NEW_SOURCE_VERIFICATION',
            derivation_formula=RATIO_VERSION, formula='total_liabilities / total_assets * 100',
            input_fact_ids=[p['data_point_id'] for p in inputs], evidence_refs=refs,
            statement_scope='consolidated', currency='CNY',
            derivation_rule_pit_status='NOT_ADMITTED'))
    return [point], dict(version=RATIO_VERSION, status='FACT_ADMITTED', issues=[],
                         input_fact_ids=point['metadata']['input_fact_ids'], evidence_refs=refs)


def _reconcile_official_balance_ratio(source, company, packet):
    """Two printed balance identities, not independent-source or audit assurance."""
    def rejected(reason, status='REJECTED_WITH_REASON'):
        return [], dict(version=OFFICIAL_BALANCE_VERSION, status=status, issues=[reason])

    fields = ('total_assets', 'total_liabilities', 'total_equity')
    rows = packet.get('balance_reconciliation_candidates', [])
    grouped = [[r for r in rows if r['field_name'] == field] for field in fields]
    if any(len(group) != 1 for group in grouped):
        return rejected('MISSING_OR_AMBIGUOUS_PRINTED_BALANCE_TOTALS')
    rows = [group[0] for group in grouped]
    identity_keys = ('issuer', 'statement_evidence_page', 'statement_title', 'period_label',
                     'prior_period_label', 'unit', 'currency', 'unit_evidence_page', 'unit_evidence_excerpt',
                     'currency_evidence_page', 'currency_evidence_excerpt',
                     'period_evidence_page', 'period_evidence_excerpt', 'prior_period_basis',
                     'owner_evidence', 'table_context_id')
    if (any(not rows[0].get(key) for key in identity_keys)
            or any(any(r.get(key) != rows[0][key] for key in identity_keys) for r in rows)
            or any(r.get('statement_scope') != 'consolidated' or r.get('unit') != 'CNY'
                   or r.get('currency') != 'CNY' or r.get('period_label') != source.period for r in rows)
            or rows[0].get('prior_period_label') != str(int(source.period[:4])-1)+'-12-31'
            or [r.get('source_label') for r in rows] != ['资产总计', '负债合计', '所有者权益合计']):
        return rejected('BALANCE_IDENTITY_SCOPE_UNIT_OR_PERIOD_MISMATCH')
    owner = rows[0]['owner_evidence']
    if (owner.get('legal_name') != rows[0]['issuer'] or owner.get('compiler_name') != rows[0]['issuer']
            or owner.get('security_code') != source.symbol
            or any(not owner.get(key) for key in ('legal_name_page', 'legal_name_excerpt',
                'security_code_page', 'security_code_excerpt', 'compiler_page', 'compiler_excerpt'))):
        return rejected('ISSUER_LEGAL_NAME_TABLE_OWNER_MISMATCH')
    try:
        current = [Decimal(r['value']) for r in rows]
        prior = [Decimal(r['prior_value']) for r in rows]
        if any(not v.is_finite() for v in current + prior):
            return rejected('NONFINITE_BALANCE_INPUT')
        # Currency amounts are exact decimals; precision must not hide a residual.
        with localcontext() as context:
            context.prec = max(48, max(len(v.as_tuple().digits) for v in current + prior) + 8)
            residuals = [str(a-l-e) for a,l,e in (current, prior)]
            if any(a <= 0 or l < 0 or a != l+e for a,l,e in (current, prior)):
                return rejected('TWO_PERIOD_BALANCE_IDENTITY_FAILED')
        with localcontext() as context:
            context.prec = 48
            value = str(current[1] / current[0] * 100)
    except (InvalidOperation, ValueError, TypeError, KeyError):
        return rejected('INVALID_OR_MISSING_BALANCE_AMOUNT')
    expected = dict(zip(fields, current), debt_ratio=Decimal(value))
    for point in company:
        field = point.get('field_name')
        if field not in expected or point.get('period_label') != source.period or not _accepted(point):
            continue
        try:
            agrees = (point.get('unit') == ('percent' if field == 'debt_ratio' else 'CNY')
                and (point.get('metadata') or {}).get('statement_scope') == 'consolidated'
                and Decimal(str(point['value'])).is_finite()
                and Decimal(str(point['value'])) == expected[field])
        except (InvalidOperation, ValueError, TypeError, KeyError):
            agrees = False
        if not agrees:
            return rejected('EXISTING_ADMITTED_BALANCE_CONFLICT:' + field, 'SOURCE_CONFLICT')
    source_binding = dict(asdict(source), issuer=rows[0]['issuer'])
    refs, ids = [], []
    for row in rows:
        row_digest = hashlib.sha256(json.dumps(dict(source=source_binding, row=row), sort_keys=True).encode()).hexdigest()
        input_id = 'official-reported-balance:' + row_digest
        ids.append(input_id)
        refs.append(dict(source_binding, **row, id=input_id))
    proof = dict(status='TWO_PERIOD_EXACT_RECONCILIATION', current_residual=residuals[0],
        prior_residual=residuals[1], equity_basis='TOTAL_EQUITY_INCLUDING_NCI_AND_OTHER_EQUITY',
        balance_rows=rows, source_binding=source_binding, owner_evidence=owner,
        table_context_id=rows[0]['table_context_id'],
        accounting_identity_basis=dict(revision_year=2014, article=26,
            url='https://www.mof.gov.cn/zcsjtsgb/gztsgb/201407/t20140723_3578373.htm'))
    binding = dict(version=OFFICIAL_BALANCE_VERSION, source=source_binding, reconciliation=proof,
        formula='total_liabilities / total_assets * 100', decimal_precision=48,
        input_fact_ids=ids, parser=packet['identity']['implementation_sha256'], value=value)
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    point = dict(symbol=source.symbol, field_name='debt_ratio', period_label=source.period,
        value=value, unit='percent', data_point_id='official-balance-ratio:' + digest,
        source_id='official-balance-reconciliation:' + source.sha256,
        source_name='Official reported consolidated balance reconciliation (single source)',
        source_path=source.path, source_url=source.source_url, sha256=source.sha256,
        created_at=source.available_at, available_at=source.available_at, fetched_at=source.available_at,
        validation_status='verified', human_reviewed=False,
        metadata=dict(verification_method=OFFICIAL_BALANCE_VERSION, derivation_formula=OFFICIAL_BALANCE_VERSION,
            single_source_balance_verification=True, automatic_cross_source_verification=False,
            assurance_basis='source_reported_only', statement_scope='consolidated', currency='CNY',
            formula=binding['formula'], decimal_precision=48, input_fact_ids=ids, evidence_refs=refs,
            balance_reconciliation=proof, derivation_rule_pit_status='NOT_ADMITTED',
            economic_approval=False, complete_debt_verified=False))
    return [point], dict(version=OFFICIAL_BALANCE_VERSION, status='FACT_ADMITTED', issues=[],
        assurance_basis='source_reported_only', input_fact_ids=ids, evidence_refs=refs,
        reconciliation=proof)


def _derive_income_growth(source, company, packet):
    admitted, observations, reports = [], [], []
    for field, output in (('revenue', 'revenue_yoy'), ('net_income', 'net_income_yoy')):
        rows = [row for row in packet.get('income_comparatives', []) if row['field_name'] == field]
        issues = []
        if len(rows) != 1:
            reports.append(dict(field_name=output, status='REJECTED_WITH_REASON',
                                issues=['INCOME_COMPARATIVE_MISSING_OR_AMBIGUOUS']))
            continue
        row = rows[0]
        current, prior = Decimal(row['value']), Decimal(row['prior_value'])
        if not current.is_finite() or not prior.is_finite() or prior <= 0:
            reports.append(dict(field_name=output, status='REJECTED_WITH_REASON',
                                issues=['NONPOSITIVE_OR_INVALID_GROWTH_DENOMINATOR']))
            continue
        inputs = []
        for period, value in ((source.period, current), (row['prior_period_label'], prior)):
            matches = [p for p in company if p.get('field_name') == field
                and p.get('period_label') == period and p.get('unit') == 'CNY'
                and _accepted(p) and Decimal(str(p['value'])) == value
                and (p.get('metadata') or {}).get('statement_scope') != 'parent']
            if len(matches) != 1:
                issues.append('ADMITTED_INPUT_MISSING_OR_AMBIGUOUS:' + field + ':' + period)
            else:
                inputs.append(matches[0])
        with localcontext() as ctx:
            ctx.prec = 28
            value = str((current / prior - 1) * 100)
        ref = dict(id='income-comparative:' + output, path=source.path, sha256=source.sha256,
            source_url=source.source_url, **row)
        binding = dict(version=GROWTH_VERSION, source=asdict(source), comparative=row,
            inputs=inputs, parser=packet['identity']['implementation_sha256'])
        digest = hashlib.sha256(json.dumps(binding, sort_keys=True, default=str).encode()).hexdigest()
        clocks = [datetime.fromisoformat(source.available_at)]
        for p in inputs:
            clocks.extend(datetime.fromisoformat(str(p[k])) for k in
                ('available_at', 'created_at', 'fetched_at') if p.get(k))
        known_at = max(clocks).isoformat()
        point = dict(symbol=source.symbol, field_name=output, period_label=source.period,
            data_point_id='value-growth:' + digest, value=value, unit='percent',
            source_id='derived:' + digest, source_name='Derived from official income comparative',
            source_url=source.source_url, sha256=source.sha256, source_path=source.path,
            available_at=known_at, created_at=known_at, fetched_at=known_at,
            validation_status='pending' if issues else 'verified', human_reviewed=False,
            metadata=dict(derivation_formula=GROWTH_VERSION, formula='(current / prior - 1) * 100',
                automatic_cross_source_verification=not issues,
                assurance_basis='BOTH_RETAINED_INPUTS_REQUIRED_FOR_INHERITED_ASSURANCE',
                statement_scope='consolidated', currency='CNY',
                input_fact_ids=[p['data_point_id'] for p in inputs], evidence_refs=[ref],
                prior_period_label=row['prior_period_label'], source_observation_verified=True,
                rejection_reasons=issues, derivation_rule_pit_status='NOT_ADMITTED'))
        (observations if issues else admitted).append(point)
        reports.append(dict(field_name=output, status='SOURCE_VERIFIED_PENDING_INPUT_ADMISSION' if issues else 'FACT_ADMITTED',
                            value=value, issues=issues, evidence_refs=[ref]))
    return admitted, observations, reports


def validate_debt_scope(symbol: str, period: str, components: list[dict], *,
                        evaluation_at: datetime,
                        financial_funding_requirements: list[dict] | None = None) -> dict:
    """Validate existing verified classifications, never infer scope from blanks.

    Components are mutually exclusive financing buckets. Current maturities
    include current leases; only NONCURRENT leases/payables may be added again.
    The final scope review must address notes, factoring and other financing.
    """
    issues = []
    grouped = {}
    total = Decimal('0')
    fact_ids = []
    requirements = financial_funding_requirements or []
    required_financial = {row.get('field_name') for row in requirements
                          if row.get('field_name') in FINANCIAL_FUNDING_FIELDS}
    financial_fields = required_financial | {row.get('field_name') for row in components
                                            if row.get('field_name') in FINANCIAL_FUNDING_FIELDS}
    expected_fields = [*DEBT_LABELS, *sorted(financial_fields)]
    for row in components:
        field = row.get('field_name')
        if field not in expected_fields:
            issues.append(f'UNEXPECTED_COMPONENT:{field}')
            continue
        if field in grouped:
            issues.append(f'DUPLICATE_COMPONENT:{field}')
        grouped[field] = row
    for field in expected_fields:
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
        if field in required_financial:
            observed = [item for item in requirements if item.get('field_name') == field]
            if len(observed) != 1:
                issues.append(f'AMBIGUOUS_FINANCIAL_FUNDING_SOURCE:{field}')
            else:
                item = observed[0]
                observed_period = item.get('period_label', item.get('period'))
                observed_scope = item.get('statement_scope', item.get('scope'))
                try:
                    amount = Decimal(str(item.get('value')))
                    if (not amount.is_finite() or amount < 0
                            or amount != Decimal(str(row.get('value')))):
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    issues.append(f'FINANCIAL_FUNDING_AMOUNT_UNKNOWN_OR_MISMATCH:{field}')
                if (observed_period != period or item.get('unit') != 'CNY'
                        or item.get('currency') != 'CNY' or observed_scope != 'consolidated'):
                    issues.append(f'FINANCIAL_FUNDING_SOURCE_SCOPE_MISMATCH:{field}')
                if classification == 'not_applicable':
                    try:
                        if Decimal(str(item.get('value'))) != 0:
                            raise InvalidOperation
                    except (InvalidOperation, ValueError):
                        issues.append(f'FINANCIAL_FUNDING_REQUIRES_AMOUNT_CLASSIFICATION:{field}')
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
                            components: list[dict] | None = None,
                            public_summary_binding: dict | None = None) -> dict:
    """Extract, match existing facts, validate scope and re-run unchanged scoring.

    Candidate matches never change a fact's original validation flags. Only
    already admitted PIT facts enter re-evaluation. No database/pointer writes.
    """
    original = deepcopy(points)
    public_summary_binding = _public_profit_binding(points, source, public_summary_binding)
    packet = extract_retained_annual(root, source, evaluation_at=evaluation_at, cache_dir=cache_dir,
                                     verify_cache=True)
    profit_points, profit_adoption = _correlate_public_parent_profit(
        root, source, packet, public_summary_binding, evaluation_at)
    funding_scope = _source_financial_funding_scope(packet, source)
    company = [deepcopy(p) for p in points if p.get('symbol') == source.symbol
               and _point_available_at(p, evaluation_at) is not None
               and (p.get('metadata') or {}).get('derivation_formula') not in DERIVED_VERSIONS]
    from .income_source_correlation import reverify_income_inputs
    reverify_income_inputs(root, source, company, evaluation_at=evaluation_at)
    before = evaluate_financial_quality(source.symbol, name, sector, company,
                                        evaluation_date=evaluation_at.date())
    existing_profit = [p for p in company if p.get('field_name') == 'net_income'
                       and p.get('period_label') == source.period and _accepted(p)]
    if profit_points and existing_profit:
        expected = Decimal(profit_points[0]['value'])
        try:
            agrees = all(p.get('unit') == 'CNY'
                and (p.get('metadata') or {}).get('statement_scope') == 'consolidated'
                and Decimal(str(p['value'])).is_finite()
                and Decimal(str(p['value'])) == expected for p in existing_profit)
        except (InvalidOperation, ValueError, TypeError):
            agrees = False
        profit_points = []
        profit_adoption = dict(status='EXISTING_ADMITTED_INPUT_PRESENT' if agrees else 'SOURCE_CONFLICT',
            field_name='net_income', issues=[] if agrees else ['EXISTING_ADMITTED_PARENT_PROFIT_CONFLICT'])
    if components is None:
        # Existing numeric balances remain unclassified until note review.
        components = [p for p in company if p.get('field_name') in {*DEBT_LABELS, *FINANCIAL_FUNDING_FIELDS}
                      and p.get('period_label') == source.period
                      and p.get('source_id') != (p.get('metadata') or {}).get('secondary_source_id')]
    industrial_components = [p for p in components if p.get('field_name') not in FINANCIAL_FUNDING_FIELDS]
    scope = validate_debt_scope(source.symbol, source.period, industrial_components,
                               evaluation_at=evaluation_at)
    financial_components = [p for p in components if p.get('field_name') in FINANCIAL_FUNDING_FIELDS]
    funding_scope['required_fields'] = sorted(set(funding_scope['required_fields']) |
        {p['field_name'] for p in financial_components})
    funding_scope['unresolved_fields'] = list(funding_scope['required_fields'])
    enforce_funding = bool(financial_components) or scope['scope_contract_complete']
    requirements = [row for row in funding_scope['observations']
                    if row.get('field_name') in funding_scope['required_fields']]
    if enforce_funding:
        scope = validate_debt_scope(source.symbol, source.period, components,
            evaluation_at=evaluation_at, financial_funding_requirements=requirements)
    binding_issues = []
    for component in components:
        meta = component.get('metadata') or {}
        retained = [p for p in company if p.get('data_point_id') == component.get('data_point_id')]
        if len(retained) != 1 or retained[0] != component:
            binding_issues.append(f'CLASSIFIED_COMPONENT_NOT_RETAINED:{component.get("field_name")}')
        binding = meta.get('official_evidence') or {}
        financial = component.get('field_name') in FINANCIAL_FUNDING_FIELDS
        if financial:
            observed = [row for row in requirements if row.get('field_name') == component.get('field_name')]
            if (len(observed) != 1 or binding.get('page') != observed[0].get('page')
                    or ''.join(str(observed[0].get('excerpt', '')).split()) not in
                    ''.join(str(binding.get('excerpt', '')).split())):
                binding_issues.append(f'FINANCIAL_FUNDING_NOT_BOUND_TO_OBSERVATION:{component.get("field_name")}')
        page = binding.get('page')
        excerpt = ''.join(str(binding.get('excerpt', '')).split())
        if (binding.get('sha256') != source.sha256 or binding.get('source_url') != source.source_url
                or not isinstance(page, int) or not 1 <= page <= packet['page_count']
                or not excerpt or excerpt not in ''.join(packet['page_texts'][page - 1].split())):
            binding_issues.append(f'ORIGINAL_BINDING_MISMATCH:{component.get("field_name")}')
        elif ((financial or (component.get('metadata') or {}).get('debt_classification') == 'included')
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
    if enforce_funding and funding_scope['required_fields']:
        unresolved = [field for field in funding_scope['required_fields']
                      if any(field in issue for issue in scope['issues'])]
        funding_scope['unresolved_fields'] = unresolved
        funding_scope['status'] = ('SOURCE_BOUND_CLASSIFICATIONS_VALIDATED_NOT_NEW_FACT_ADMISSION'
            if scope['complete_debt_verified'] else 'FINANCIAL_FUNDING_SCOPE_DATA_GAP')
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
    adopted_points = []
    if scope['complete_debt_verified']:
        for p in company:
            if (p['field_name'] == 'interest_bearing_debt' and p['period_label'] == source.period
                    and p.get('unit') == 'CNY' and Decimal(str(p['value'])) == Decimal(scope['value'])
                    and p.get('validation_status') == 'verified'
                    and (p.get('metadata') or {}).get('statement_scope') == 'consolidated'
                    and (p.get('metadata') or {}).get('currency') == 'CNY'
                    and (p.get('metadata') or {}).get('automatic_cross_source_verification') is True
                    and not (p.get('metadata') or {}).get('evidence_quarantine')
                    and (p.get('metadata') or {}).get('derivation_formula') != VERSION):
                derived = deepcopy(p)
                meta = derived.setdefault('metadata', {})
                clocks = [datetime.fromisoformat(source.available_at)]
                secondary_ids = {(item.get('metadata') or {}).get('secondary_data_point_id') for item in components}
                secondary_points = [item for item in company if item.get('data_point_id') in secondary_ids]
                for input_point in [p, *components, *secondary_points]:
                    for key in ('available_at', 'fetched_at', 'created_at'):
                        if input_point.get(key):
                            clocks.append(datetime.fromisoformat(str(input_point[key])))
                    reviewed = (input_point.get('metadata') or {}).get('debt_scope_reviewed_at')
                    if reviewed:
                        clocks.append(datetime.fromisoformat(reviewed))
                if any(clock.utcoffset() is None or clock > evaluation_at for clock in clocks):
                    raise ValueError('Derived debt input availability is invalid at cutoff')
                known_at = max(clocks).isoformat()
                meta.update(complete_debt_verified=True, debt_scope_validation=scope,
                            derivation_formula=VERSION, supersedes_id=p['data_point_id'],
                            input_fact_ids=[p['data_point_id'], *scope['input_fact_ids'],
                                            *sorted(identity for identity in secondary_ids if identity)],
                            derivation_available_at=known_at,
                            availability_basis='MAX_BOUND_INPUT_CLOCKS_NOT_FIRST_COMPUTATION',
                            derivation_rule_pit_status='NOT_ADMITTED')
                version_hash = hashlib.sha256(json.dumps(dict(source=asdict(source), scope=scope,
                    original=p, components=components, independent_points=secondary_points),
                    sort_keys=True, default=str).encode()).hexdigest()
                derived.update(data_point_id=p['data_point_id'] + ':scope:' + version_hash,
                    created_at=known_at, available_at=known_at)
                adopted.append(derived['data_point_id'])
                adopted_points.append(derived)
    official_ratio, official_adoption = _reconcile_official_balance_ratio(source, company, packet)
    if official_adoption['status'] == 'SOURCE_CONFLICT':
        ratio_points, ratio_adoption = [], official_adoption
    else:
        ratio_points, ratio_adoption = _derive_balance_ratio(source, company, packet, evaluation_at)
        if not ratio_points and official_ratio:
            ratio_points, ratio_adoption = official_ratio, official_adoption
    adopted_points.extend(ratio_points)
    growth_points, growth_observations, growth_adoption = _derive_income_growth(
        source, company + profit_points, packet)
    adopted_points.extend(growth_points)
    adopted_points.extend(profit_points)
    after = evaluate_financial_quality(source.symbol, name, sector, company + adopted_points,
                                       evaluation_date=evaluation_at.date())
    assert points == original
    return dict(version=VERSION, symbol=source.symbol, period=source.period,
                company_name=name, sector=sector,
                evaluation_at=evaluation_at.isoformat(), mode='RETAINED_SOURCE_REEVALUATION',
                source_extraction=packet, candidate_matches=matches, debt_scope=scope,
                source_financial_funding_scope=funding_scope,
                before=asdict(before), after=asdict(after), adopted_debt_fact_ids=adopted,
                adopted_points=adopted_points,
                balance_ratio_adoption=ratio_adoption,
                official_balance_reconciliation=official_adoption,
                income_growth_adoption=growth_adoption,
                public_summary_binding=public_summary_binding,
                public_profit_adoption=profit_adoption,
                sourced_arithmetic_points=growth_observations,
                input_points_sha256=hashlib.sha256(json.dumps(points, sort_keys=True, default=str).encode()).hexdigest(),
                state='QUALITY_EVALUATED' if after.total_score is not None else 'DATA_UNAVAILABLE',
                next_action=('RETAIN_CURRENT_RESEARCH_GATES' if after.total_score is not None
                             else 'VERIFY_MISSING_SAME_PERIOD_FACTS_AND_DEBT_NOTE_CLASSIFICATIONS'),
                verification_created=False, formal_eligibility=False, action='no_order')


def consume_retained_enrichment(root: Path, points: list[dict], sources: list[dict], *,
                               evaluation_at: datetime) -> tuple[list[dict], list[dict]]:
    """Re-run original and independent-source checks, never trust saved PASS flags.

    Source declarations belong to the hash-bound financial export. Existing
    admitted facts retain their IDs and assurance; only debt scope is derived.
    """
    if not isinstance(sources, list) or len(sources) > 128:
        raise ValueError('retained enrichment sources require a bounded list of at most 128')
    claimed_balances = [p for p in points if any([
        (p.get('metadata') or {}).get('derivation_formula') == OFFICIAL_BALANCE_VERSION,
        (p.get('metadata') or {}).get('verification_method') == OFFICIAL_BALANCE_VERSION,
        (p.get('metadata') or {}).get('single_source_balance_verification') is True])]
    merged = [deepcopy(p) for p in points if (p.get('metadata') or {}).get('derivation_formula') not in DERIVED_VERSIONS]
    reports, seen = [], set()
    for declaration in sources:
        source = RetainedAnnualSource(**declaration)
        identity = (source.symbol, source.period)
        if identity in seen:
            raise ValueError('duplicate retained enrichment source identity')
        seen.add(identity)
        result = enrich_retained_company(root, source, merged, evaluation_at=evaluation_at,
            cache_dir=root / '.tmp/value-enrichment-consumption',
            public_summary_binding=_public_profit_binding(points, source))
        identities = {p['data_point_id']: p for p in merged if p.get('data_point_id')}
        for point in result['adopted_points']:
            if point['data_point_id'] in identities:
                if identities[point['data_point_id']] != point:
                    raise ValueError('conflicting derived financial fact identity')
            else:
                merged.append(point)
                identities[point['data_point_id']] = point
        reports.append({'symbol': source.symbol, 'period': source.period,
            'source': declaration, 'debt_scope': result['debt_scope'],
            'adopted_debt_fact_ids': result['adopted_debt_fact_ids'],
            'adopted_fact_ids': [p['data_point_id'] for p in result['adopted_points']],
            'balance_ratio_adoption': result['balance_ratio_adoption'],
            'official_balance_reconciliation': result['official_balance_reconciliation'],
            'income_growth_adoption': result['income_growth_adoption'],
            'public_profit_adoption': result['public_profit_adoption'],
            'verification_created': False, 'formal_eligibility': False})
    for claim in claimed_balances:
        rebuilt = [p for p in merged if p.get('data_point_id') == claim.get('data_point_id')
                   and (p.get('metadata') or {}).get('derivation_formula') == OFFICIAL_BALANCE_VERSION]
        if len(rebuilt) != 1 or rebuilt[0] != claim:
            raise ValueError('Official balance ratio does not match cold-revalidated original')
    return merged, reports


def register_enriched_research(result: dict, *, root: Path, points: list[dict],
                              repository, case, facts, run_id: str) -> dict:
    """Consume admitted enrichment through existing typed research codecs.

    The caller supplies its case/model contract. Financial completeness and
    economic approval are deliberately not inferred from source admission.
    """
    from ...research_artifacts import ResearchArtifactIdentity, parse_stored_artifact_payload
    from ...research_artifact_codecs import artifact_payload

    if case.symbol != result['symbol'] or facts.symbol != result['symbol']:
        raise ValueError('Enrichment research identity mismatch')
    if facts.as_of > case.as_of:
        raise ValueError('Research facts exceed case date')
    cutoff = datetime.fromisoformat(result['evaluation_at'])
    if case.generated_at > cutoff or case.as_of > cutoff.date():
        raise ValueError('Research case unavailable at enrichment cutoff')
    source = RetainedAnnualSource(**result['source_extraction']['identity']['source'])
    checked = enrich_retained_company(root, source, points, evaluation_at=cutoff,
        cache_dir=root / '.tmp/value-enrichment-extraction',
        name=result.get('company_name'), sector=result.get('sector'),
        public_summary_binding=result.get('public_summary_binding'))
    # JSON normalization allows persisted Decimal values to be revalidated.
    for field in ('adopted_points', 'sourced_arithmetic_points', 'after', 'input_points_sha256', 'debt_scope'):
        normalize = lambda value: json.loads(json.dumps(value, default=str))
        if normalize(checked[field]) != normalize(result[field]):
            raise ValueError('Research admission differs from revalidated source facts: ' + field)
    points = result['adopted_points']
    if not points:
        return {'status': 'REJECTED_WITH_REASON', 'issues': ['NO_ADMITTED_ENRICHMENT_FACTS'],
                'artifacts': [], 'formal_eligibility': False, 'action': 'no_order'}
    refs = {ref['id']: ref for ref in facts.evidence_refs}
    inputs = dict(facts.operating_inputs)
    for point in points:
        if _point_available_at(point, cutoff) is None or not _accepted(point):
            raise ValueError('Unadmitted enrichment fact cannot enter research')
        inputs[point['field_name']] = Decimal(str(point['value']))
        refs[point['data_point_id']] = dict(id=point['data_point_id'],
            value=point['value'], unit=point['unit'], period_label=point['period_label'],
            source_url=point['source_url'], sha256=point['sha256'],
            input_fact_ids=point['metadata']['input_fact_ids'],
            evidence_refs=point['metadata'].get('evidence_refs', []))
    blockers = list(dict.fromkeys([*facts.blockers, 'ECONOMIC_REVIEW_NOT_GRANTED_BY_ENRICHMENT']))
    from dataclasses import fields
    cleared = {name: None for name in ('scenario_inputs', 'valuation_timing')
               if name in {field.name for field in fields(facts)}}
    updated_facts = replace(facts, operating_inputs=inputs, evidence_refs=list(refs.values()),
                            blockers=blockers, verified=False, **cleared)
    kind, _ = artifact_payload(updated_facts)
    identity = ResearchArtifactIdentity('security', case.symbol, kind, 'c3-v1', case.as_of, cutoff)
    stored_facts = repository.save_object(updated_facts, identity=identity,
        evidence_refs=list(refs.values()), run_id=run_id, advance_head=False)
    repository.verify(stored_facts)
    # Decode the stored payload before creating the dependent case: this binds
    # research consumption to the repository version, not a parallel dict.
    from ...research_input import facts_from_payload
    consumed = facts_from_payload(parse_stored_artifact_payload(stored_facts))
    case_ref = dict(id='value-enrichment-financial-facts', artifact_id=stored_facts.artifact_id,
                    sha256=stored_facts.envelope.payload_sha256)
    summary = dict(case.financial_summary, value_enrichment=dict(
        financial_facts=case_ref, admitted_fact_ids=[p['data_point_id'] for p in points],
        operating_inputs=consumed.operating_inputs, quality=result['after'],
        sourced_arithmetic_observations=result.get('sourced_arithmetic_points', []),
        complete_debt_verified=checked['debt_scope']['complete_debt_verified'],
        economic_admission='NOT_PROVEN', action='no_order'))
    case_refs = {ref['id']: ref for ref in case.evidence_refs}
    case_refs[case_ref['id']] = case_ref
    updated_case = replace(case, financial_summary=summary, evidence_refs=list(case_refs.values()),
        research_status='DATA_CHECK', valuation_status='NOT_ASSESSED',
        research_version=case.research_version + ':' + stored_facts.envelope.payload_sha256[:16],
        generated_at=cutoff, run_id=run_id,
        blockers=list(dict.fromkeys([*case.blockers, *blockers])))
    stored_case = repository.save_object(updated_case,
        identity=ResearchArtifactIdentity('security', case.symbol, 'research_case', 'c3-v1', case.as_of, cutoff),
        evidence_refs=updated_case.evidence_refs, run_id=run_id, advance_head=False)
    repository.verify(stored_case)
    return dict(status='RESEARCH_INPUTS_UPDATED', artifacts=[asdict(stored_facts), asdict(stored_case)],
        financial_facts_artifact_id=stored_facts.artifact_id,
        research_case_artifact_id=stored_case.artifact_id,
        financial_facts_sha256=stored_facts.envelope.payload_sha256,
        research_case_sha256=stored_case.envelope.payload_sha256,
        consumed_operating_inputs=consumed.operating_inputs,
        formal_eligibility=False, economic_admission='NOT_PROVEN', action='no_order')


def verify_enrichment_adoption(*, root: Path, result_binding: dict,
                              financial_export_path: Path, financial_export_sha256: str,
                              evaluation_at: datetime) -> dict:
    """Verify bound immutable inputs; shared hash-keyed extraction cache may write.

    Original bytes and clocks are checked on every cache hit. Cached extraction
    is keyed by source and parser implementation; economic status is not cached.
    """
    from ..product.common import require_inside
    from .value_research_queue import _load_bound
    from ...infrastructure.screening.financial_export_v2 import load_retained_financial_export
    from ...research_artifacts import ResearchArtifactEnvelope, ResearchArtifactIdentity

    root = root.resolve()
    if evaluation_at.utcoffset() is None:
        raise ValueError('Adoption verification cutoff must include timezone')
    path = require_inside(root / 'runtime', root / result_binding['path'], 'enrichment result')
    if path.stat().st_size > 32_000_000:
        raise ValueError('enrichment result exceeds verification budget')
    result = _load_bound(path, result_binding['sha256'])
    stamp = datetime.fromisoformat(result['evaluation_at'])
    if stamp.utcoffset() is None or stamp > evaluation_at or result.get('action') != 'no_order':
        raise ValueError('Enrichment result unavailable at verification cutoff')
    export = require_inside(root / 'runtime', financial_export_path, 'financial export')
    _load_bound(export, financial_export_sha256)
    points, _ = load_retained_financial_export(export, evaluation_at=stamp)
    source = RetainedAnnualSource(**result['source_extraction']['identity']['source'])
    checked = enrich_retained_company(root, source, points, evaluation_at=stamp,
        cache_dir=root / '.tmp/value-enrichment-extraction',
        name=result.get('company_name'), sector=result.get('sector'),
        public_summary_binding=result.get('public_summary_binding'))
    for field in ('adopted_points', 'sourced_arithmetic_points', 'after', 'input_points_sha256', 'debt_scope'):
        if json.loads(json.dumps(checked[field], default=str)) != result[field]:
            raise ValueError('Enrichment result differs from revalidated source facts: ' + field)
    registration = result.get('research_registration')
    registered = False
    if registration and registration.get('status') == 'RESEARCH_INPUTS_UPDATED':
        artifacts = {}
        for stored in registration['artifacts']:
            raw = stored['envelope']
            ident = raw['identity']
            identity = ResearchArtifactIdentity(**dict(ident,
                as_of=datetime.fromisoformat(ident['as_of']).date(),
                available_at=datetime.fromisoformat(ident['available_at'])))
            if identity.scope_key != source.symbol or identity.available_at != stamp:
                raise ValueError('Registered enrichment artifact identity mismatch')
            envelope = ResearchArtifactEnvelope(identity=identity, canonical_payload=raw['canonical_payload'],
                payload_sha256=raw['payload_sha256'], evidence_refs=tuple(raw['evidence_refs']), run_id=raw['run_id'])
            kind = identity.artifact_type
            if kind in artifacts:
                raise ValueError('Duplicate registered enrichment artifact')
            artifacts[kind] = (stored['artifact_id'], envelope)
        facts_id, facts = artifacts['financial_facts']
        case_id, case = artifacts['research_case']
        if (facts_id != registration['financial_facts_artifact_id']
                or case_id != registration['research_case_artifact_id']
                or facts.payload_sha256 != registration['financial_facts_sha256']
                or case.payload_sha256 != registration['research_case_sha256']):
            raise ValueError('Registered enrichment artifact binding mismatch')
        facts_payload = facts.payload_object()
        from ...research_input import facts_from_payload
        consumed = facts_from_payload(facts_payload)
        for point in checked['adopted_points']:
            if consumed.operating_inputs.get(point['field_name']) != Decimal(str(point['value'])):
                raise ValueError('Registered facts did not consume admitted enrichment')
        case_link = case.payload_object()['financial_summary']['value_enrichment']['financial_facts']
        if case_link.get('artifact_id') != facts_id or case_link.get('sha256') != facts.payload_sha256:
            raise ValueError('Registered research case did not consume financial facts version')
        observations = case.payload_object()['financial_summary']['value_enrichment'].get(
            'sourced_arithmetic_observations', [])
        if observations != checked.get('sourced_arithmetic_points', []):
            raise ValueError('Registered research observations differ from sourced arithmetic')
        complete_debt = case.payload_object()['financial_summary']['value_enrichment'].get('complete_debt_verified')
        if complete_debt is not checked['debt_scope']['complete_debt_verified']:
            raise ValueError('Registered research debt scope differs from revalidated source')
        registered = True
    return dict(status='VERIFIED_FACT_ADOPTION', symbol=source.symbol,
        adopted_fact_ids=[p['data_point_id'] for p in checked['adopted_points']],
        adopted_fact_count=len(checked['adopted_points']), research_inputs_updated=registered,
        sourced_arithmetic_observation_count=len(checked.get('sourced_arithmetic_points', [])),
        quality_coverage_before=str(checked['before']['coverage_ratio']),
        quality_coverage_after=str(checked['after']['coverage_ratio']),
        complete_debt_verified=checked['debt_scope']['complete_debt_verified'],
        source_financial_funding_scope=checked['source_financial_funding_scope'],
        new_fact_approvals=0, formal_eligibility=False, action='no_order')

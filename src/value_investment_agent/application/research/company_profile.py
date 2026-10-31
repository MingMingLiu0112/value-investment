"""Read-only economic-profile projection of existing source-bound research.

No research case, model, approval or symbol-to-formula mapping is created here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import re
import hashlib
import json

from ...financial_institutions import provisional_financial_type
from ...research_profile import PROFILES
from ...valuation_router import route_profile
from ..product.common import load_json_object, normalize_symbol
from ..product.source_bound_inputs import source_catalog_sha256, verify_package_local_sources
from .v4_input_adapter import build_descriptor_for_package
from .value_research_analysis import _available, _bound, project_value_research_analysis
from ..product.pending_candidate_supplement import load_current_pending_candidate_supplement
from ..product.pending_replay_publication import load_current_pending_replay

SCHEMA = 'company-research-profile-v1'
INVALIDATION = [
    'SOURCE_HASH_OR_BINDING_CHANGED', 'ISSUER_OR_REPORT_PERIOD_CHANGED',
    'BUSINESS_STRUCTURE_OR_CAPITAL_ALLOCATION_CHANGED', 'REQUIRED_MODEL_INPUTS_CHANGED',
    'COUNTEREVIDENCE_OR_THESIS_BREAKER_TRIGGERED',
]


def _texts(rows):
    result = []
    for row in rows:
        if isinstance(row, str):
            text = row
        elif isinstance(row, dict):
            text = next((row[key] for key in ('text', 'statement', 'description', 'reason', 'claim', 'title')
                         if isinstance(row.get(key), str) and row[key].strip()), None)
        else:
            text = None
        if text and text not in result:
            result.append(text)
    return result


def _empty(symbol, blockers):
    return dict(schema_version=SCHEMA, schema=SCHEMA, symbol=symbol, status='UNASSESSABLE',
        profile=None, business_model=None, economic_type=None, route=None, as_of=None,
        evidence_refs=[], source_bindings=[], counter_evidence=[], supporting_evidence=[],
        invalidation_conditions=list(INVALIDATION), blockers=list(blockers),
        moat_status='NOT_PROVEN_BY_PROFILE', action='no_order', formal_eligibility=False,
        research_admitted=False, approval_changed=False)


# These are reported product/operating activities, not moat or valuation approvals.
# No issuer code participates in this classification.
BUSINESS_TERMS = {
    'consumer_products': ('白酒', '系列酒', '乳制品', '乳品', '液态奶', '液体乳', '配方奶粉'),
    'manufacturing': ('家用电器', '家电', '汽车零部件', '空调', '智能制造'),
    'commodity_operations': ('煤炭开采', '煤炭生产', '煤炭业务', '煤炭销售', '综合能源'),
}
PROFILE_FAMILY = dict(quality_compounder='consumer_products', mature_manufacturing='manufacturing',
    cyclical_cash_return='commodity_operations')
BUSINESS_SECTION = re.compile(r'公司主要业务是|公司主要从事|公司主营业务|公司从事的业务|主要业务及经营模式|主要业务、主要产品')


OWN_BUSINESS = re.compile(r'(?:本公司|公司|本集团)(?:的)?(?:主要业务(?:是|为)|主要从事|主营业务(?:是|为)?)([^。；]{1,600})')
SECTION_END = re.compile(r'[一二三四五六七八九十]+、(?:报告期内)?(?:核心竞争力|主要经营情况|经营情况的讨论|经营情况讨论|风险因素|公司治理)')
FINANCIAL_BUSINESS = re.compile(r'商业银行|存贷款|吸收存款|发放贷款|证券经纪|保险业务|承保业务')
OTHER_ACTOR = re.compile(r'主要客户|客户包括|客户为|客户是|供应商|供应客户|服务于|为[^，。；]{0,80}(?:提供|供应)')
NEGATED_ACTIVITY = re.compile(r'不从事|未从事|不涉及|并非|不再|停止|从未|不是|不生产|不销售|非(?:家电|煤炭|乳品|白酒)')


def _reported_activities(pages):
    """Collect all own-issuer activities in a bounded, demonstrably closed main section."""
    compact_pages = [re.sub(r'\s+', '', page) for page in pages[:40]]
    text = '\n'.join(compact_pages)
    first = OWN_BUSINESS.search(text)
    if first is None:
        return []
    end = SECTION_END.search(text, first.end())
    if end is None and len(pages) > 40:
        raise ValueError('BUSINESS_SECTION_COMPLETENESS_UNKNOWN')
    section_end = end.start() if end else len(text)
    rows = []
    for match in OWN_BUSINESS.finditer(text, first.start(), section_end):
        statement = match.group(1)
        # Separate the issuer's activity before applying financial or product rules.
        role = OTHER_ACTOR.search(statement)
        own = statement[:role.start()] if role else statement
        if FINANCIAL_BUSINESS.search(own):
            raise ValueError('FINANCIAL_MAIN_BUSINESS_REQUIRES_SPECIALIZED_MODEL')
        if NEGATED_ACTIVITY.search(own):
            continue
        kinds = ({key for key, terms in BUSINESS_TERMS.items() if any(term in own for term in terms)}
                 if re.search(r'生产|制造|销售|开采|产销', own) else set())
        # An explicit own business outside the registered families is evidence too.
        # Keep its locator so it cannot silently disappear beside a known business.
        page = text.count('\n', 0, match.start()) + 1
        rows.append((page, text[match.start():match.end()], kinds))
    return rows


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def validate_company_profile_for_package(*, root: Path, package: dict, now: datetime) -> dict:
    """Nonrecursive pre-route check of bound official business text against the requested profile.

    Does not load a registry, research analysis, router or model; never writes/restores sources.
    A caller must retain its existing full source-contract/descriptor validation as well.
    """
    from ...infrastructure.filings.pdf_text import extract_pages
    root = root.resolve()
    if now.utcoffset() is None:
        raise ValueError('Company profile requires a timezone-aware cutoff')
    if package.get('schema_version') != 'm1-valuation-package-v2' or not package.get('source_contract'):
        raise ValueError('Company profile requires a source-bound v2 package')
    symbol = normalize_symbol(package['symbol'])
    case, contract = package['research_case'], package['source_contract']
    if (case['symbol'] != symbol or case['name'] != package['name']
            or case.get('financial_period') != package['point_in_time']['report_period']):
        raise ValueError('Company profile issuer or financial period mismatch')
    if contract.get('source_catalog_sha256') != source_catalog_sha256(package['sources']):
        raise ValueError('Company profile source catalog hash mismatch')
    for stamp in (contract['cutoff_at'], package['point_in_time']['available_at'],
                  package['point_in_time']['computed_at'], case['generated_at']):
        _available(stamp, now)
    cutoff = datetime.fromisoformat(contract['cutoff_at'])
    refs, observed, gaps = [], set(), []
    for source in package['sources']:
        if source['kind'] not in {'official_issuer_filing', 'official_exchange_filing'}:
            continue
        try:
            verified = verify_package_local_sources(root, dict(package, sources=[source]))
        except (ValueError, OSError) as error:
            raise ValueError('Company profile source rejected: ' + str(source.get('local_path')) + ': ' + str(error)) from error
        identity = source.get('issuer_identity') or {}
        if not identity.get('security_code'):
            gaps.append('SOURCE_NOT_USED_FOR_BUSINESS_IDENTITY:' + source['id'])
            continue
        if identity['security_code'] != symbol:
            raise ValueError('Company profile source issuer ambiguous or mismatched: ' + source['id'])
        if not source.get('source_available_at') or not source.get('availability_basis'):
            raise ValueError('Company profile source availability missing: ' + source['id'])
        for field in ('source_available_at', 'published_at', 'retrieved_at'):
            if source.get(field):
                _available(source[field], now if field == 'retrieved_at' else min(now, cutoff))
        if source.get('report_period') and source['report_period'] > case['financial_period']:
            raise ValueError('Company profile source report period mismatch: ' + source['id'])
        path = verified[0][0]
        if path.suffix.lower() != '.pdf':
            continue  # A JSON claim or industry label cannot replace the official report text.
        pages = extract_pages(path, limit=41)
        cover = re.sub(r'\s+', '', '\n'.join(pages[:4]))
        cover_codes = set(re.findall(r'(?:公司|证券|股票)代码[:：]?([0-9]{6})(?!\d)', cover))
        activities = _reported_activities(pages)
        if activities:
            issuer_name = re.sub(r'\s+', '', identity.get('issuer_name') or '')
            if cover_codes != {symbol} or not issuer_name or issuer_name not in cover:
                raise ValueError('Company profile official cover issuer mismatch: ' + source['id'])
        for page, excerpt, kinds in activities:
            observed.update(kinds)
            refs.append(dict(id=source['id'], path=source['local_path'], sha256=source['sha256'],
                hash=source['sha256'], source_url=source['location'], url=source['location'],
                page=page, physical_page=page, excerpt=excerpt,
                source_available_at=source['source_available_at'],
                economic_types=sorted(kinds), classification='REPORTED_OWN_BUSINESS_NOT_MOAT_PROOF',
                section_coverage='CLOSED_SECTION_OR_COMPLETE_DOCUMENT_WITHIN_40_PAGES'))
    financial = provisional_financial_type(package['name'], case['industry'])
    if financial:
        raise ValueError('FINANCIAL_INSTITUTION_SPECIALIZED_RESEARCH_REQUIRED')
    unknown = [ref for ref in refs if not ref['economic_types']]
    if unknown:
        detail = '; '.join(ref['id'] + ':page=' + str(ref['page']) + ':' + ref['excerpt']
                           for ref in unknown)
        raise ValueError('UNSUPPORTED_OWN_BUSINESS_BLOCKS_SINGLE_PROFILE: ' + detail)
    if len(observed) != 1:
        raise ValueError('AMBIGUOUS_OR_UNSUPPORTED_SOURCE_ECONOMIC_PROFILE')
    economic_type = next(iter(observed))
    requested = package.get('profile_id')
    if PROFILE_FAMILY.get(requested) != economic_type or any(case.get(key) not in (None, requested)
            for key in ('profile_id', 'economic_type')):
        raise ValueError('SOURCE_ECONOMIC_PROFILE_MISMATCH: requested=' + str(requested) + ', reported=' + economic_type)
    # Protect against a report changing while it was decoded.
    for ref in refs:
        _bound(root, dict(path=ref['path'], sha256=ref['sha256']))
    summary = case.get('financial_summary') or {}
    economics = []
    for key in ('operating_mechanism_research', 'product_operating_research', 'product_ten_year_research',
                'financial_scope_review', 'verified_financial_review', 'financial_equity_bridge',
                'pending_joint_capital_research', 'pending_model_limits'):
        if summary.get(key):
            economics.append(dict(field='research_case.financial_summary.' + key,
                value=deepcopy(summary[key]), evidence_refs=deepcopy(case.get('evidence_refs', [])),
                classification='EXISTING_SOURCE_BOUND_RESEARCH_NOT_NEW_APPROVAL'))
    inputs = package['facts'].get('operating_inputs')
    if inputs:
        economics.append(dict(field='facts.operating_inputs', value=deepcopy(inputs),
            evidence_refs=deepcopy(package['facts'].get('evidence_refs', [])),
            consumed_fact_bindings=deepcopy(contract.get('consumed_fact_bindings', [])),
            fact_anchors=deepcopy(contract.get('fact_anchors', [])),
            classification='EXISTING_MODEL_INPUTS_RETAIN_ORIGINAL_ASSURANCE'))
    if not economics:
        raise ValueError('ECONOMIC_INPUTS_AND_CAPITAL_CONSTRAINT_RESEARCH_REQUIRED')
    result = dict(status='REPORTED_BUSINESS_TEMPLATE_CANDIDATE', profile_id=requested,
        economic_type=economic_type, reported_business_family=economic_type,
        template_candidate=requested,
        route_qualification=dict(status='CONDITIONAL_RESEARCH_ONLY_NOT_ECONOMIC_QUALITY_PROOF',
            required_economic_inputs=list(PROFILES[requested].required_financial_metrics),
            explanation='Reported products constrain the existing template; durable returns, normalized earnings and distributable cash remain subject to the existing case counterevidence and capital/funding constraints.',
            economic_quality_proven=False, moat_proven=False, approved=False),
        evidence_refs=refs, economic_evidence=economics,
        business_model='；'.join(ref['excerpt'][:240] for ref in refs[:2]),
        explanation=case['return_driver'], gaps=gaps,
        action='no_order', formal_eligibility=False,
        moat_status='NOT_PROVEN_BY_PROFILE')

    result['implementation_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['package_content_sha256'] = _fingerprint(package)
    result['validation_sha256'] = _fingerprint(result)
    return result


def project_company_profile(*, root: Path, package_binding: dict, now: datetime) -> dict:
    """Project an exact existing package; invalid sources raise, never seek an older one."""
    if now.utcoffset() is None:
        raise ValueError('Company profile requires a timezone-aware cutoff')
    root = root.resolve()
    path = _bound(root, package_binding)
    package = load_json_object(path, 'company profile package')
    symbol = normalize_symbol(package['symbol'])
    if package.get('schema_version') != 'm1-valuation-package-v2' or not package.get('source_contract'):
        raise ValueError('Company profile requires a source-bound v2 package: ' + package_binding['path'])
    contract = package['source_contract']
    if contract.get('source_catalog_sha256') != source_catalog_sha256(package['sources']):
        raise ValueError('Company profile source catalog differs: ' + package_binding['path'])
    # Preserve the existing historical-code restore contract; this read never restores/writes.
    if (package.get('dependencies') or {}).get('model_version') in {
            'residual-income-equity-path-v3', 'residual-income-equity-path-v4'}:
        from ..product.historical_source_restore import verify_or_restore_package_sources
        local = verify_or_restore_package_sources(root, package,
            restore_dir=path.parent / 'historical-source-code', create=False)
    else:
        # Report the precise damaged source without weakening the shared verifier.
        for source in package['sources']:
            try:
                verify_package_local_sources(root, dict(package, sources=[source]))
            except (ValueError, OSError) as error:
                raise ValueError('Company profile source rejected: ' + str(source.get('local_path')) + ': ' + str(error)) from error
        local = verify_package_local_sources(root, package)
    for stamp in (package['point_in_time']['available_at'], package['point_in_time']['computed_at'], contract['cutoff_at']):
        _available(stamp, now)
    for source in package['sources']:
        for field in ('source_available_at', 'retrieved_at', 'published_at'):
            if source.get(field):
                _available(source[field], now)
    case = package['research_case']
    if case['symbol'] != symbol or case['name'] != package['name']:
        raise ValueError('Company profile research issuer differs from package: ' + package_binding['path'])
    period = package['point_in_time']['report_period']
    if case.get('financial_period') != period:
        raise ValueError('Company profile research financial period differs from package: ' + package_binding['path'])
    _available(case['generated_at'], now)
    official = [source for source in package['sources'] if source['kind'] in {'official_issuer_filing', 'official_exchange_filing'}]
    if not official:
        return _empty(symbol, ['OFFICIAL_ISSUER_EVIDENCE_REQUIRED'])
    for source in official:
        identity = source.get('issuer_identity') or {}
        if identity.get('security_code') not in (None, symbol):
            raise ValueError('Company profile source issuer ambiguous or mismatched: ' + source['id'])
        if source.get('report_period') and source['report_period'] > period:
            raise ValueError('Company profile source report period follows research: ' + source['id'])
    if provisional_financial_type(package['name'], case['industry']):
        return _empty(symbol, ['FINANCIAL_INSTITUTION_SPECIALIZED_RESEARCH_REQUIRED'])
    profile_id = package['profile_id']
    if profile_id not in PROFILES:
        return _empty(symbol, ['NO_REGISTERED_ECONOMIC_PROFILE'])
    if any(case.get(key) not in (None, profile_id) for key in ('profile_id', 'economic_type')):
        return _empty(symbol, ['AMBIGUOUS_ECONOMIC_PROFILE'])
    business_validation = validate_company_profile_for_package(root=root, package=package, now=now)
    effective = deepcopy(package)
    effective['facts'].setdefault('kind', effective['facts'].get('facts_type'))
    descriptor = build_descriptor_for_package(effective, root=root)
    route = route_profile(descriptor.profile_id, descriptor.requested_model).as_policy()
    refs = []
    for source in package['sources']:
        locations = [ref for ref in case.get('evidence_refs', []) if ref.get('id') == source['id']]
        item = dict(source, path=source['local_path'], hash=source['sha256'],
            source_url=source['location'], url=source['location'], references=deepcopy(locations))
        for ref in locations:
            for key in ('page', 'physical_page', 'table', 'excerpt'):
                if key in ref and key not in item:
                    item[key] = ref[key]
        refs.append(item)
    blockers = list(dict.fromkeys([*case.get('blockers', []), *package.get('blockers', []),
        *route['blockers'], 'PROFILE_ROUTING_NOT_ECONOMIC_APPROVAL', 'MOAT_AND_NORMALIZED_RETURNS_NOT_PROVEN_BY_PROFILE']))
    result = dict(_empty(symbol, blockers),
        status='SOURCE_BOUND_PROFILE' if route['status'] == 'SUPPORTED' else 'UNASSESSABLE',
        profile=asdict(PROFILES[profile_id]), business_model=business_validation['business_model'],
        business_explanation=business_validation['explanation'], economic_evidence=business_validation['economic_evidence'],
        gaps=business_validation['gaps'],
        profile_validation_sha256=business_validation['validation_sha256'],
        implementation_sha256=business_validation['implementation_sha256'],
        economic_type=business_validation['economic_type'],
        reported_business_family=business_validation['reported_business_family'],
        template_candidate=business_validation['template_candidate'],
        route_qualification=dict(business_validation['route_qualification'], required_inputs=route['required_inputs']),
        route=route, as_of=case['as_of'],
        company_name=package['name'], industry=case['industry'], thesis=case['thesis'],
        return_driver=case['return_driver'], report_period=period,
        available_at=package['point_in_time']['available_at'],
        input_descriptor_sha256=descriptor.input_sha256, evidence_refs=business_validation['evidence_refs'],
        source_catalog=refs, profile_validation=business_validation['status'],
        counter_evidence=_texts(case.get('counter_evidence', [])),
        supporting_evidence=_texts(case.get('positives', [])),
        invalidation_conditions=list(dict.fromkeys([*_texts(case.get('thesis_breakers', [])), *INVALIDATION])),
        source_verification=dict(status='SOURCE_CONTRACT_VERIFIED',
            assurance='BYTE_AND_INPUT_CONSISTENCY_NOT_ECONOMIC_APPROVAL',
            strict_contemporaneous_pit=contract.get('strict_contemporaneous_pit', 'NOT_PROVEN')),
        source_bindings=[dict(package_binding), *[dict(path=p.relative_to(root).as_posix(), sha256=d) for p, d in local]])
    for binding in result['source_bindings']:
        _bound(root, binding)
    result['input_fingerprint'] = _fingerprint(dict(package=package_binding,
        descriptor=descriptor.input_sha256, validation=business_validation['validation_sha256'],
        sources=result['source_bindings']))
    result['profile_input_sha256'] = result['input_fingerprint']
    return result


def load_company_profile(*, root: Path, symbol: str, now: datetime) -> dict:
    """Reuse the current research precedence and verification; no filesystem search fallback."""
    symbol = normalize_symbol(symbol)
    if now.utcoffset() is None:
        raise ValueError('Company profile requires a timezone-aware cutoff')
    current = load_current_pending_candidate_supplement(root=root, symbol=symbol)
    if current is not None:
        bindings = current
    else:
        current = load_current_pending_replay(root=root, symbol=symbol)
        if current is None:
            return _empty(symbol, ['NO_CURRENT_SOURCE_BOUND_RESEARCH'])
        bindings = current['publication']
        _available(bindings['generated_at'], now)
    _available(current['candidate']['generated_at'], now)
    result = project_company_profile(root=root, now=now, package_binding=bindings['package_binding'])
    if result['symbol'] != symbol:
        raise ValueError('Company profile differs from the current consumed research')
    if result['status'] == 'SOURCE_BOUND_PROFILE':
        analysis = project_value_research_analysis(root=root, now=now,
            package_binding=bindings['package_binding'], workbench_binding=bindings['workbench_binding'])
        if (analysis['symbol'] != symbol or analysis['input_descriptor_sha256'] != result['input_descriptor_sha256']
                or analysis['input_descriptor_sha256'] != current['candidate']['model_context']['input_descriptor_sha256']):
            raise ValueError('Company profile differs from the current consumed research descriptor')
        result['route'] = deepcopy(analysis['model_applicability']['route'])
        result['route_qualification']['required_inputs'] = result['route']['required_inputs']
        result['consumption_status'] = 'C_PROFILE_VALIDATED_AND_EXISTING_ANALYSIS_REPLAYED'
        result['source_bindings'] = deepcopy(analysis['source_bindings'])
    else:
        result['consumption_status'] = 'NOT_ADMITTED_BY_C_PROFILE'
    for key in ('registry_binding', 'publication_binding'):
        if current.get(key):
            _bound(root.resolve(), current[key])
            result['source_bindings'].append(dict(current[key]))
    if result.get('profile_validation_sha256'):
        result['input_fingerprint'] = _fingerprint(dict(descriptor=result['input_descriptor_sha256'],
            validation=result['profile_validation_sha256'], sources=result['source_bindings']))
        result['profile_input_sha256'] = result['input_fingerprint']
    return result

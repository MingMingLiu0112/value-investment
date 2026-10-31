"""Source-only C adapter: exact official receipts to conditional existing routes.

No ResearchCase, model execution, source discovery or old-consumer replacement.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from ...domain.research.profile_applicability_v1 import contract_for_profile
from ...research_profile import PROFILES
from ...valuation_router import route_profile
from ...infrastructure.filings import official_report_acquisition as acquisition
from ...infrastructure.filings.pdf_text import extract_pages
from ..product.common import normalize_symbol, require_inside, sha256_file
from . import company_profile as inherited

SCHEMA = 'source-company-profile-v1'
REGISTRY_SCHEMA = 'source-company-profile-registry-v1'
REGISTRY_PATH = 'config/company-profile-sources-v1.json'
CAPITAL_TERMS = re.compile(r'资本开支|资本性支出|资本支出|维护投入|营运资本|资金需求|资金来源|偿债|现金流量|财务公司|借款|现金分红|资本管理|采矿权')


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _bound(root, binding, *, limit=None):
    if (not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}
            or not isinstance(binding['path'], str) or not isinstance(binding['sha256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', binding['sha256'])):
        raise ValueError('Source C requires an exact path/SHA256 binding')
    relative = Path(binding['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Source C binding must be project relative: ' + binding['path'])
    path = require_inside(root, root / relative, 'source C input')
    raw = path.read_bytes()
    if ((limit is not None and len(raw) > limit)
            or hashlib.sha256(raw).hexdigest() != binding['sha256']):
        raise ValueError('Source C binding rejected: ' + binding['path'])
    return raw


def _available(value, now):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError('Source C receipt not available at cutoff')
    return stamp


def _empty(symbol):
    return dict(schema_version=SCHEMA, symbol=symbol, status='UNASSESSABLE',
        profile=None, route=None, applicability_contract=None, business_model=None,
        economic_type=None, reported_business_family=None, template_candidate=None,
        evidence_refs=[], economic_evidence=[], source_bindings=[], missing_inputs=[],
        missing_economic_inputs=[], input_assessment=[], economic_input_assessment=[],
        blockers=['NO_EXPLICIT_REGISTERED_OFFICIAL_SOURCE'],
        counter_evidence=[], invalidation_conditions=list(inherited.INVALIDATION),
        valuation_status='VALUATION_INPUTS_PENDING', consumption_status='SOURCE_ONLY_NOT_MODEL_REPLAY',
        classification_reason='NO_EXPLICIT_REGISTERED_OFFICIAL_SOURCE',
        action='no_order', formal_eligibility=False, research_admitted=False,
        approval_changed=False, economic_quality_proven=False, moat_status='NOT_PROVEN_BY_PROFILE')


def _ref(packet, page, excerpt, classification):
    source = packet['source']
    return dict(id=packet['source_id'], path=source['path'], sha256=source['sha256'],
        hash=source['sha256'], source_url=source['source_url'], url=source['source_url'],
        page=page, physical_page=page, excerpt=excerpt, period=source['period'],
        published_date=packet['published_date'], available_at=source['available_at'],
        retrieved_at=packet.get('original_retrieved_at',packet['fetched_at']),
        available_at_basis=packet.get('available_at_basis','ACTUAL_OFFICIAL_ACQUISITION_TIME'), classification=classification)


def _own_refs(packet, pages):
    # Reuse the inherited own-business grammar for locators, not another classifier.
    text = '\n'.join(re.sub(r'\s+', '', page) for page in pages[:40])
    return [_ref(packet, text.count('\n', 0, match.start()) + 1, match.group(0),
                 'REPORTED_BUSINESS_LOCATOR_NOT_ECONOMIC_APPROVAL')
            for match in inherited.OWN_BUSINESS.finditer(text)]


def _implementation_hashes():
    from ...domain.research import profile_applicability_v1, research_profile
    from ... import valuation_router
    return {module.__name__: sha256_file(Path(module.__file__)) for module in
        (inherited, acquisition, profile_applicability_v1, research_profile, valuation_router)} | {
            __name__: sha256_file(Path(__file__))}


def _finish(root, result, closure):
    # Recheck originals, raw index responses and registration after all decoding.
    for binding in closure:
        _bound(root, binding)
    result['source_bindings'] = closure
    result['implementation_sha256'] = _implementation_hashes()
    result['input_fingerprint'] = _fingerprint(result)
    result['profile_input_sha256'] = result['input_fingerprint']
    return result


FIXED_RECEIPT_SCHEMA = 'c-fixed-sample-source-receipt-v1'
FIXED_SECTION_REVIEW_VERSION = 'c-fixed-three-section-review-v1'
# FROZEN CASE DATA: these three independently reviewed source sections close this
# bounded sample only. Do not accumulate further stock/section hashes here.
# New cases or changed sections require a separately versioned review contract.
# This is not a general classifier, quality assessment or new valuation model.
# Reviewed complete original sections, not issuer-code dispatch or a configurable family claim.
# A changed section must be reviewed/versioned; it cannot gain support by adding keywords.
FIXED_SECTION_POLICIES = {'cd468c9424bf7e3327a1717a40ed7c91b4432cdad47594b0694035fae387952b': {'family': 'manufacturing', 'scopes': ['智能家居', '工业技术', '楼宇科技', '机器人与自动化', '新能源', '健康医疗', '智慧物流'], 'limitation': 'ToC/ToB、工业与财务公司、外汇及衍生工具范围仍须拆分；不得将合并现金直接作为母公司可分配现金。'}, '3fed51e59cf4b40efad78dcbe46d17d818c38235c90ad491ea1b62f4b2f7638f': {'family': 'commodity_operations', 'scopes': ['煤炭', '电力', '铁路', '港口', '航运', '煤制烯烃'], 'limitation': '一体化业务仅支持条件周期研究；分部/SOTP、煤电及运输正常化、维护资本开支与可持续分配均待补证，不能当作纯煤炭或峰值盈利续推。'}, 'f8c715217a8c2a0bf70b3e6099c101ffc36b64b58f2dfad5b2bb2ebebe4a4436': {'family': 'financial_institution', 'scopes': ['批发及零售银行产品和服务', '资金业务'], 'limitation': '金融主营需要专用模型；现有通用企业画像及估值模型不适用。'}}


def _load_fixed(root, entry, packet, symbol, now, closure):
    """Validate the finite C lineage independently; never relabel an A failure as success."""
    period = entry.get('period')
    if (not isinstance(period, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', period)
            or period[4:] not in ('-12-31', '-06-30')):
        raise ValueError('Fixed C report period requires exact YYYY-MM-DD annual or half-year end')
    datetime.strptime(period, '%Y-%m-%d')
    source = packet['source']
    if (packet.get('schema_version') != FIXED_RECEIPT_SCHEMA or packet.get('action') != 'no_order'
            or packet.get('formal_eligibility') is not False or packet.get('strict_historical_pit') is not False
            or packet.get('historical_available_at') is not None or packet.get('symbol') != symbol
            or packet.get('issuer_name') != entry['issuer_name'] or packet.get('period') != entry['period']
            or source.get('symbol') != symbol or source.get('period') != entry['period']):
        raise ValueError('Fixed C receipt issuer/period/assurance mismatch')
    available = _available(source['available_at'], now)
    for field in ('reverified_at', 'acquired_completed_at'):
        if packet.get(field):
            _available(packet[field], now)
    url_match = re.fullmatch(r'https://static\.cninfo\.com\.cn/finalpage/(\d{4}-\d{2}-\d{2})/(\d+)\.PDF', source['source_url'])
    if not url_match or packet['source_id'] != 'cninfo:' + url_match[2]:
        raise ValueError('Fixed C original URL/source identity mismatch')
    original = dict(path=source['path'], sha256=source['sha256'])
    _bound(root, original)
    acquisition.validate_pdf_original(root / source['path'])
    if packet.get('reused') is True:
        origin = packet.get('origin') or {}
        binding = packet.get('origin_manifest') or origin.get('manifest')
        if not binding or packet.get('original_retrieved_at') is not None:
            raise ValueError('Fixed C retained origin manifest/retrieval boundary missing')
        manifest = json.loads(_bound(root, binding, limit=20_000_000))
        closure.append(dict(binding))
        items = [item for item in manifest['items']
                 if item.get('sha256') == source['sha256']
                 and item.get('expected_sha256') == source['sha256']
                 and item.get('actual_sha256') == source['sha256']]
        if not items or (origin.get('item') is not None and origin['item'] not in items):
            raise ValueError('Fixed C original hash is absent from bound origin manifest')
        archived = dict(path=items[0]['archive_path'], sha256=source['sha256'])
        _bound(root, archived)
        closure.append(archived)
        if not packet.get('available_at_basis', '').startswith('ACTUAL_LOCAL_MATERIALIZATION'):
            raise ValueError('Fixed C retained availability must remain materialization, not historical PIT')
    elif packet.get('reused') is False:
        failure_binding = packet['acquisition_failure_receipt']
        failure = json.loads(_bound(root, failure_binding, limit=512_000))
        closure.append(dict(failure_binding))
        if (failure.get('schema_version') != acquisition.VERSION or failure.get('status') != 'FAILED'
                or failure.get('action') != 'no_order'
                or failure.get('error') != 'ValueError:Official PDF issuer or reporting-period cover mismatch'
                or failure['completed_at'] != source['available_at']
                or packet.get('acquired_completed_at') != source['available_at']
                or packet.get('index_bindings') != failure['index_bindings']):
            raise ValueError('Fixed C failed A provenance or availability mismatch')
        position = 0
        refs = failure['index_bindings']
        def query(parameters):
            nonlocal position
            if position >= len(refs):
                raise ValueError('Fixed C raw index incomplete')
            ref = refs[position]
            position += 1
            meta = ref['metadata']
            if (meta['request'] != parameters or meta['url'] != acquisition.disclosures.SEARCH_URL
                    or meta['sha256'] != ref['sha256']):
                raise ValueError('Fixed C raw index request mismatch')
            _available(meta['acquired_at'], available)
            binding = dict(path=ref['path'], sha256=ref['sha256'])
            closure.append(binding)
            return json.loads(_bound(root, binding, limit=2_000_000))
        kind = 'annual' if entry['period'].endswith('-12-31') else 'interim'
        row, published = acquisition._discover(query, symbol=symbol, issuer_name=entry['issuer_name'],
            period=entry['period'], kind=kind, today=available.astimezone(acquisition.CHINA).date())
        if (position != len(refs) or source['source_url'] != acquisition.disclosures.PDF_BASE_URL + row['adjunctUrl']
                or packet['source_id'] != 'cninfo:' + str(row['announcementId'])
                or published.isoformat() != url_match[1]):
            raise ValueError('Fixed C official index differs from original receipt')
    else:
        raise ValueError('Fixed C requires explicit retained or failed-acquisition provenance')
    section_binding, evidence_binding = entry['main_business_section'], entry['evidence_pages']
    section = json.loads(_bound(root, section_binding, limit=2_000_000))
    evidence = json.loads(_bound(root, evidence_binding, limit=10_000_000))
    closure.extend([dict(section_binding), dict(evidence_binding)])
    for payload, schema in ((section,'c-official-main-business-section-v1'),
                            (evidence,'c-official-full-evidence-pages-v1')):
        if (payload.get('schema_version') != schema or payload.get('action') != 'no_order'
                or payload.get('symbol') != symbol or payload.get('period') != entry['period']
                or payload.get('source_binding') != original):
            raise ValueError('Fixed C section/evidence metadata source mismatch')
    if (section.get('issuer_name') != entry['issuer_name'] or section.get('source_id') != packet['source_id']
            or section.get('available_at') != source['available_at']
            or section.get('source_url') != source['source_url']
            or section.get('complete_selected_section') is not True
            or section.get('whitespace_normalized_only') is not True):
        raise ValueError('Fixed C complete business-section metadata invalid')
    start, end = section['physical_page_start'], section['physical_page_end']
    identity_pages = entry.get('identity_pages', list(range(1,13)))
    page_numbers = [row['physical_page'] for row in evidence['pages']]
    if (type(start) is not int or type(end) is not int or not 1 <= start <= end <= 400
            or not identity_pages or any(type(n) is not int or not 1 <= n <= 400 for n in [*identity_pages,*page_numbers])):
        raise ValueError('Fixed C physical page budget invalid')
    pages = extract_pages(root/source['path'], limit=max(end, *identity_pages, *page_numbers))
    cover = re.sub(r'\s+', '', ''.join(pages[n-1] for n in identity_pages))
    if (not re.search(r'(?:公司|证券|股票|A股)代码[:：]?' + symbol + r'(?!\d)',cover)
            or re.sub(r'\s+','',entry['issuer_name']) not in cover):
        raise ValueError('Fixed C actual PDF issuer identity mismatch')
    title = entry['period'][:4] + (r'年?年度报告' if entry['period'].endswith('-12-31') else r'年?半年度报告')
    if not re.search(title,cover) or '报告摘要' in cover:
        raise ValueError('Fixed C actual report title/period mismatch')
    for row in evidence['pages']:
        if row['full_text'] != pages[row['physical_page']-1]:
            raise ValueError('Fixed C bound full evidence page differs from original decoding')
    joined = '\n'.join(re.sub(r'\s+','',text) for text in pages[start-1:end])
    a, b = section['start_marker'], section['end_marker']
    if joined.count(a) != 1 or joined.count(b) != 1 or joined.index(b) <= joined.index(a):
        raise ValueError('Fixed C complete section boundary is ambiguous')
    text = joined[joined.index(a):joined.index(b)]
    if text != section['full_text']:
        raise ValueError('Fixed C full business section differs from original decoding')
    packet = dict(packet, published_date=url_match[1], fetched_at=source['available_at'],
        original_retrieved_at=packet.get('original_retrieved_at'), index_bindings=packet.get('index_bindings', []))
    return packet,pages,section,evidence


def load_source_company_profile(*, root: Path, symbol: str, now: datetime,
                                registry_binding: dict | None = None) -> dict:
    """Read one explicit registration; corrupt current evidence raises, never falls back.

    Missing registration is UNASSESSABLE. Lawful financial/unknown/mixed originals
    return an evidenced refusal. Missing model values are never extracted or valued here.
    """
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    if now.utcoffset() is None:
        raise ValueError('Source C requires an aware cutoff')
    if registry_binding is None:
        path = root / REGISTRY_PATH
        if not path.exists():
            return _empty(symbol)
        registry_binding = dict(path=REGISTRY_PATH, sha256=sha256_file(path))
    registry = json.loads(_bound(root, registry_binding, limit=512_000))
    if (not isinstance(registry, dict) or set(registry) != {'schema_version', 'action', 'entries'}
            or registry['schema_version'] != REGISTRY_SCHEMA or registry['action'] != 'no_order'
            or not isinstance(registry['entries'], dict)):
        raise ValueError('Invalid source C registry')
    result = _empty(symbol)
    closure = [dict(registry_binding)]
    entry = registry['entries'].get(symbol)
    if entry is None:
        return _finish(root, result, closure)
    if (not isinstance(entry, dict) or not {'issuer_name', 'period', 'receipt_binding'} <= set(entry)
            or set(entry) - {'issuer_name', 'period', 'receipt_binding', 'main_business_section', 'evidence_pages', 'identity_pages'}
            or not isinstance(entry['issuer_name'], str) or not entry['issuer_name'].strip()
            or not isinstance(entry['period'], str)):
        raise ValueError('Invalid source C issuer/period registration')
    receipt_binding = entry['receipt_binding']
    receipt = json.loads(_bound(root, receipt_binding, limit=512_000))
    fixed = receipt.get('schema_version') == FIXED_RECEIPT_SCHEMA
    section = evidence = None
    if fixed:
        packet,pages,section,evidence = _load_fixed(root,entry,receipt,symbol,now,closure)
    else:
        packet = acquisition.load_retained_official_report(root=root, receipt_binding=receipt_binding,
            symbol=symbol, issuer_name=entry['issuer_name'], period=entry['period'])
        for field in ('started_at', 'fetched_at', 'completed_at'):
            _available(packet[field], now)
    _available(packet['source']['available_at'], now)
    closure += [dict(receipt_binding), dict(path=packet['source']['path'], sha256=packet['source']['sha256'])]
    closure += [dict(path=ref['path'], sha256=ref['sha256']) for ref in packet['index_bindings']]
    if not fixed:
        pages = extract_pages(root / packet['source']['path'], limit=41)
    refs = ([_ref(packet, section['physical_page_start'], section['full_text'],
        'VERIFIED_COMPLETE_FIXED_MAIN_BUSINESS_SECTION')] if fixed else _own_refs(packet, pages))
    if fixed:
        refs[0]['physical_page_end'] = section['physical_page_end']
    # Keep raw official business evidence even if the inherited classifier rejects.
    result.update(company_name=entry['issuer_name'], as_of=entry['period'], report_period=entry['period'],
        available_at=packet['source']['available_at'], retrieved_at=packet.get('original_retrieved_at',packet['fetched_at']),
        published_date=packet['published_date'], evidence_refs=refs,
        business_model='；'.join(ref['excerpt'] for ref in refs[:2]) or None,
        business_explanation='主营描述来自已核验的官方原件，仅用于条件模型路径匹配；资本现金约束及必需输入仍待核验，尚未形成估值或经济研究批准。',
        classification_method='INHERITED_OWN_BUSINESS_CLASSIFIER',
        source_verification=dict(status='EXACT_OFFICIAL_RECEIPT_AND_ORIGINAL_REVALIDATED',
            strict_historical_pit=False, historical_available_at=None,
            text_scope='FIRST_40_PAGES_WITH_INHERITED_MAIN_SECTION_COMPLETENESS_CHECK'))
    capital = []
    capital_pages = ([(row['physical_page'],row['full_text']) for row in evidence['pages']]
                     if fixed else list(enumerate(pages[:40],1)))
    for page, text in capital_pages:
        compact = re.sub(r'\s+', '', text)
        for match in CAPITAL_TERMS.finditer(compact):
            capital.append(_ref(packet, page, compact[max(0, match.start()-60):match.end()+160],
                'REPORTED_CAPITAL_CLAUSE_NOT_EXTRACTED_MODEL_INPUT'))
            if len(capital) >= 12:
                break
        if len(capital) >= 12:
            break
    result['economic_evidence'] = capital
    policy = (FIXED_SECTION_POLICIES.get(hashlib.sha256(section['full_text'].encode('utf-8')).hexdigest())
              if fixed else None)
    if fixed:
        result.update(classification_method='FIXED_SOURCE_SECTION_REVIEW_NOT_GENERAL_CLASSIFIER',
            reviewed_section_sha256=hashlib.sha256(section['full_text'].encode('utf-8')).hexdigest(),
            fixed_section_review_version=FIXED_SECTION_REVIEW_VERSION,
            fixed_review_scope='FROZEN_THREE_SOURCE_SECTIONS_ONLY_NEW_CASE_REQUIRES_VERSIONED_REVIEW')
        result['source_verification'].update(status='FIXED_C_ORIGIN_IDENTITY_AND_FULL_SECTION_REVALIDATED',
            receipt_schema=FIXED_RECEIPT_SCHEMA, a_success_receipt=False,
            text_scope='EXACT_BOUND_COMPLETE_SECTION_AND_FULL_EVIDENCE_PAGES',
            available_at_basis=packet['available_at_basis'], original_retrieved_at=packet.get('original_retrieved_at'))
        if policy is None:
            result.update(classification_reason='UNREVIEWED_FIXED_MAIN_BUSINESS_SECTION',
                          blockers=['UNREVIEWED_FIXED_MAIN_BUSINESS_SECTION'])
            return _finish(root,result,closure)
        result['operating_scopes'] = list(policy['scopes'])
        result['counter_evidence'] = [policy['limitation']]
        result['fixed_section_rule_version'] = FIXED_RECEIPT_SCHEMA
    try:
        if fixed:
            if policy['family'] == 'financial_institution':
                raise ValueError('FINANCIAL_MAIN_BUSINESS_REQUIRES_SPECIALIZED_MODEL')
            activities = [(section['physical_page_start'],section['full_text'],{policy['family']})]
        else:
            activities = inherited._reported_activities(pages)
    except ValueError as error:
        reason = str(error)
        if reason == 'FINANCIAL_MAIN_BUSINESS_REQUIRES_SPECIALIZED_MODEL':
            result.update(status='MODEL_NOT_APPLICABLE', valuation_status='MODEL_NOT_APPLICABLE',
                classification_reason=reason, blockers=[reason],
                refusal_conditions=['金融主营需专用模型（' + reason + '）；原件第' + str(ref['page']) + '页：' + ref['excerpt'] for ref in refs],
                refusal_evidence=dict(reason=reason, pages=sorted({ref['page'] for ref in refs}),
                    evidence_refs=refs), reported_business_family='financial_institution')
        elif reason == 'BUSINESS_SECTION_COMPLETENESS_UNKNOWN':
            result.update(classification_reason=reason, blockers=[reason], refusal_conditions=[reason])
        else:
            raise
        return _finish(root, result, closure)
    families = set().union(*(row[2] for row in activities)) if activities else set()
    if not activities or any(not row[2] for row in activities) or len(families) != 1:
        reason = 'UNKNOWN_OR_MIXED_OWN_BUSINESS'
        result.update(classification_reason=reason, blockers=[reason], refusal_conditions=[reason])
        return _finish(root, result, closure)
    family = next(iter(families))
    matches = [key for key, value in inherited.PROFILE_FAMILY.items() if value == family]
    if len(matches) != 1:
        raise ValueError('Source C business family has no unambiguous registered template')
    profile_id = matches[0]
    route = route_profile(profile_id).as_policy()
    contract = contract_for_profile(profile_id)
    if route['status'] != 'SUPPORTED' or route['selected_model'] != contract['primary_model']:
        raise ValueError('Source C route differs from registered applicability contract')
    business = [_ref(packet, page, excerpt, 'REPORTED_OWN_BUSINESS_NOT_MOAT_PROOF')
                for page, excerpt, _ in activities]
    if fixed:
        business[0]['physical_page_end'] = section['physical_page_end']
    result.update(status='SOURCE_BOUND_ROUTE_ONLY', profile=asdict(PROFILES[profile_id]), route=route,
        applicability_contract=contract, reported_business_family=family, economic_type=family,
        template_candidate=profile_id, classification_reason='REPORTED_BUSINESS_TEMPLATE_CANDIDATE',
        evidence_refs=business, business_model='；'.join(ref['excerpt'] for ref in business[:2]),
        applicability_conditions=contract['applicability_conditions'],
        refusal_conditions=contract['refusal_conditions'],
        missing_inputs=list(route['required_inputs']),
        input_assessment=[dict(name=name, status='MISSING', reason='来源画像适配未提取该模型计算输入')
                          for name in route['required_inputs']],
        missing_economic_inputs=list(contract['required_economic_inputs']),
        economic_input_assessment=[dict(name=name, status='MISSING', reason='来源画像适配未核验该经济输入')
                                   for name in contract['required_economic_inputs']],
        blockers=['VALUATION_INPUTS_PENDING', 'ECONOMIC_QUALITY_AND_DISTRIBUTABLE_CASH_NOT_VERIFIED'],
        counter_evidence=[*result['counter_evidence'], '披露主营不等于已证明正常化回报、护城河持续期或自由可分配现金；资本投入、偿债和分配约束仍需独立核验。'],
        route_qualification=dict(status='SOURCE_ONLY_CONDITIONAL_ROUTE_NOT_MODEL_REPLAY',
            economic_quality_proven=False, approved=False, required_inputs=route['required_inputs']))
    return _finish(root, result, closure)

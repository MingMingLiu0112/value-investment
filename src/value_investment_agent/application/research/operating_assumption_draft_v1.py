"""D2 source-bound operating assumptions from existing v4 research inputs.

Replays original financial statements and existing source-node contracts only.
Does not compile a valuation, construct a ResearchCase, publish, or call an LLM.
The predecessor package is a bound identity/history context, not a reapproved model.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

from ..product import neutral_valuation_proposal as neutral
from ..product.pending_research_candidate import _joint_cash_replay_inputs
from ..product.common import encode_json_bytes, require_inside
from . import operating_earnings_bridge as bridge

SCHEMA = 'operating-assumption-draft-v1'
INPUT_SCHEMA = 'joint-capital-cash-path-inputs-v4'
SCENARIOS = ('bear','base','bull')


# Field identity, not optional metadata, determines original-statement proof.
STATEMENT_FIELDS = dict(revenue='operating_revenue', cost='cost_of_sales',
    surcharges='taxes_surcharges', selling='selling', admin='administration',
    research='research', pre_tax_profit='profit_before_tax', tax='income_tax',
    parent_profit='parent_profit', nonrecurring='nonrecurring_parent_difference')


def _source_times(inputs, package, specs, now):
    cutoff = _available(inputs['generated_at'], now)
    consumed = {ref['sha256'] for ref in inputs['source_bindings']} | {s['sha256'] for s in specs}
    rows = [row for row in package['sources'] if row.get('sha256') in consumed]
    clocks = ('source_available_at', 'retrieved_at', 'original_retrieved_at',
              'original_source_available_at', 'published_at', 'available_at', 'original_acquired_at')
    for row in [*rows, *inputs['source_bindings'], *specs]:
        for key in clocks:
            if row.get(key) is not None:
                try:
                    _available(row[key], cutoff)
                except (ValueError, TypeError) as error:
                    raise ValueError('D2 consumed source time invalid: '+str(row.get('id',row.get('source_id')))+': '+key) from error
    for spec in specs:
        official = [r for r in rows if r.get('id') == spec['source_id']]
        if len(official) != 1 or official[0]['sha256'] != spec['sha256']:
            raise ValueError('D2 statement/catalog original identity mismatch')
        source = official[0]
        publication = datetime.strptime(spec['published_date'],'%Y-%m-%d').replace(tzinfo=timezone(timedelta(hours=8)))
        _available((publication+timedelta(days=1)).isoformat(),cutoff)
        if source.get('published_at') and _available(source['published_at'],cutoff) != publication:
            raise ValueError('D2 statement/catalog publication time mismatch')
        disclosure = source.get('original_source_available_at')
        if source.get('availability_basis') == 'retained_conservative_disclosure_bound':
            disclosure = source.get('source_available_at')
        if disclosure and _available(disclosure,cutoff) != publication+timedelta(days=1):
            raise ValueError('D2 statement/catalog disclosure time mismatch')
        # Later observations of identical bytes do not claim the same acquisition.
        if spec.get('original_acquired_at') and source.get('original_retrieved_at'):
            if _available(spec['original_acquired_at'],cutoff) != _available(source['original_retrieved_at'],cutoff):
                raise ValueError('D2 same original acquisition time mismatch')
        if source.get('location','').startswith('https:') and source['location'] != spec['source_url']:
            raise ValueError('D2 statement/catalog original URL mismatch')
    return dict(scope='CONSUMED_SOURCE_CLOCKS_CHECKED_NOT_SAME_ACQUISITION_OR_HISTORICAL_PIT',
        original_acquisition_unknown=[s['source_id'] for s in specs if s.get('original_acquired_at') is None])


class _MissingSource(Exception):
    def __init__(self, path, digest=None):
        self.binding = dict(path=str(path),sha256=digest)


def _fingerprint(value):
    return hashlib.sha256(encode_json_bytes(value)).hexdigest()


def _path(root, relative):
    if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('D2 requires project-relative sources')
    return require_inside(root,root/relative,'D2 source')


def _select(root, supplied, default):
    if supplied is not None:
        return dict(supplied)
    path = _path(root,default)
    if not path.is_file():
        raise _MissingSource(default)
    return dict(path=default,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _read(root, binding, closure, *, as_json=True):
    if (not isinstance(binding,dict) or set(binding) != {'path','sha256'}
            or not isinstance(binding['sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',binding['sha256'])):
        raise ValueError('D2 source requires exact path/SHA256 binding')
    path = _path(root,binding['path'])
    if not path.is_file():
        raise _MissingSource(binding['path'],binding['sha256'])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding['sha256']:
        raise ValueError('D2 source hash mismatch: '+binding['path'])
    if binding not in closure:
        closure.append(dict(binding))
    return json.loads(raw) if as_json else raw


def _available(value,now):
    # Reuse the neutral proposal's aware-cutoff rule; no historical restamping.
    return neutral._cash_available(value,now)


def _base(symbol):
    return dict(schema_version=SCHEMA,symbol=symbol,status='UNASSESSABLE',
        action='no_order',formal_eligibility=False,formal_fact_count=0,
        assumptions_approved=False,research_admitted=False,approval_changed=False,
        valuation_computed=False,e2_new_company_compilation=False,
        scope='EXISTING_V4_RESEARCH_INPUT_ADAPTER_NOT_E2_NEW_COMPANY_COMPILATION',
        assumption_scope='RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST',
        source_bindings=[],missing_sources=[],branches=[],fact_anchors=[],
        historical_observations=[],unknowns=[],blockers=[],invalidation_conditions=[])


def load_operating_assumption_draft(*, root: Path, symbol: str, now: datetime,
        assumption_binding: dict | None = None, proposal_binding: dict | None = None) -> dict:
    """Revalidate two existing input families by exact bindings, without writing anything.

    Missing bytes return MISSING_SOURCE with the precise binding; bad hashes,
    wrong issuers/periods and future inputs raise ValueError and never fall back.
    """
    root = root.resolve()
    if not isinstance(symbol,str) or not re.fullmatch(r'[0-9]{6}',symbol) or now.utcoffset() is None:
        raise ValueError('D2 requires a six-digit symbol and aware cutoff')
    result,closure = _base(symbol),[]
    try:
        assumptions_ref = _select(root,assumption_binding,
            f'config/research-assumptions/{symbol}-joint-capital-cash-path-v4.json')
        policy_ref = _select(root,proposal_binding,
            f'config/research-proposals/{symbol}-joint-capital-cash-path-v4.json')
        inputs = _read(root,assumptions_ref,closure)
        policy = _read(root,policy_ref,closure)
        if (inputs.get('schema_version') != INPUT_SCHEMA or inputs.get('action') != 'no_order'
                or inputs.get('symbol') != symbol or policy.get('schema_version') != neutral.JOINT_CASH_V4_SCHEMA):
            raise ValueError('D2 assumption identity/schema mismatch')
        for data in (inputs,policy):
            _available(data['generated_at'],now)
            if data.get('assumption_scope') != 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST':
                raise ValueError('D2 research assumptions cannot become official facts')
        package_ref = inputs['package_binding']
        package = _read(root,package_ref,closure)
        neutral.validate_proposal_policy_identity(policy=policy,package=package,
            package_sha256=package_ref['sha256'],candidate_symbol=symbol)
        if (package.get('schema_version') != 'm1-valuation-package-v2'
                or package['research_case']['symbol'] != symbol or package.get('name') != inputs['name']
                or package['research_case']['financial_period'] != inputs['financial_basis']
                or package['point_in_time']['report_period'] != inputs['financial_basis']):
            raise ValueError('D2 predecessor issuer/financial period mismatch')
        for field in ('available_at','computed_at'):
            _available(package['point_in_time'][field],now)
        matched = [ref for ref in policy['rationale_bindings']
            if ref['path']==assumptions_ref['path'] and ref['sha256']==assumptions_ref['sha256']]
        if len(matched)!=1 or matched[0]['available_at']!=inputs['generated_at']:
            raise ValueError('D2 proposal does not bind the exact assumption version/availability')
        for ref in inputs['source_bindings']:
            _read(root,{key:ref[key] for key in ('path','sha256')},closure,as_json=False)
        specs = inputs['historical_statement_specs']
        if len(specs)!=2 or any(spec['symbol']!=symbol for spec in specs):
            raise ValueError('D2 original statement issuer/period mismatch')
        for spec in specs:
            _read(root,{key:spec[key] for key in ('path','sha256')},closure,as_json=False)
        source_time_scope = _source_times(inputs,package,specs,now)
        consumed_hashes = {r['sha256'] for r in inputs['source_bindings']} | {s['sha256'] for s in specs}
        for source in package['sources']:
            if source.get('sha256') in consumed_hashes:
                _read(root,dict(path=source['local_path'],sha256=source['sha256']),closure,as_json=False)
        replay = bridge.research_from_retained_sources(root=root,specs=specs,now=_available(inputs['generated_at'],now))
        saved = inputs['historical_statement_replay']
        if encode_json_bytes({k:v for k,v in replay.items() if k!='observed_at'}) != encode_json_bytes(
                {k:v for k,v in saved.items() if k!='observed_at'}):
            raise ValueError('D2 saved historical statement bridge differs from original recomputation')
        source_checks = []
        historical = _joint_cash_replay_inputs(policy,package,source_checks,root,neutral.JOINT_CASH_V4_SCHEMA)
        for path,digest in source_checks:
            _read(root,dict(path=path.relative_to(root).as_posix(),sha256=digest),closure,as_json=False)
        for field,line in STATEMENT_FIELDS.items():
            item = inputs['observations'].get(field,{})
            if (item.get('statement_field') != line
                    or bridge._number(item['value']) != bridge._number(replay['ttm']['lines_cny'][line])
                    or bridge._number(policy['joint_historical'][field]['value']) != bridge._number(replay['ttm']['lines_cny'][line])):
                raise ValueError('D2 required historical statement mapping/value mismatch: '+field)
        choice_ids = [choice['id'] for choice in policy['choices']]
        if (not 1<=len(choice_ids)<=3 or len(set(choice_ids))!=len(choice_ids)
                or set(choice_ids)!=set(inputs['scenarios'])
                or set(choice_ids)!=set(inputs['scenario_explanations'])):
            raise ValueError('D2 branch identity mismatch')
        if (inputs['parameter_basis'].get('classification')!='ASSUMPTION'
                or not inputs['parameter_basis'].get('rationale') or not inputs['limitations']):
            raise ValueError('D2 parameter rationale and limitations required')
        branches=[]
        for choice in policy['choices']:
            explanation=inputs['scenario_explanations'][choice['id']]
            if (explanation.get('classification')!='ASSUMPTION'
                    or not explanation.get('rationale') or not explanation.get('counter_evidence')
                    or not choice.get('rationale') or not choice.get('countercase')):
                raise ValueError('D2 branch requires economic rationale and counterevidence')
            scenarios={}
            for key in ('joint_drivers','terminal_policy','cost_of_equity','scenario_bindings'):
                neutral._cash_keys(choice[key],'bear base bull',key)
            if set(inputs['scenarios'][choice['id']])!=set(SCENARIOS):
                raise ValueError('D2 branch requires exact bear/base/bull inputs')
            for name in SCENARIOS:
                expected=dict(drivers=choice['joint_drivers'][name],terminal_policy=choice['terminal_policy'][name],
                              cost_of_equity=choice['cost_of_equity'][name])
                binding=choice['scenario_bindings'][name]
                if (binding!=dict(source_id=matched[0]['id'],field_path=['scenarios',choice['id'],name])
                        or encode_json_bytes(inputs['scenarios'][choice['id']][name])!=encode_json_bytes(expected)):
                    raise ValueError('D2 scenario differs from exact source-bound operating/capital inputs')
                scenarios[name]=dict(deepcopy(expected),classification='RESEARCH_ASSUMPTION',
                    evidence_ref=dict(assumptions_ref,field_path=binding['field_path']))
            try:
                # Existing ledger compiler only: no model.value or discounting call.
                _,ledgers=neutral.compile_joint_cash_choice_v4(choice=choice,historical=historical,
                    book=bridge._number(package['facts']['operating_inputs']['start_book_equity']))
            except (ValueError,KeyError,TypeError) as error:
                raise ValueError('D2 operating/capital path invalid for branch '+choice['id']+': '+str(error)) from error
            for name in SCENARIOS:
                scenarios[name]['operating_capital_path']=neutral._json_numbers(ledgers[name])
                scenarios[name]['path_status']='RECOMPUTED_CONDITIONAL_CAPITAL_PATH_NOT_VALUATION'
            branches.append(dict(branch_id=choice['id'],title=explanation.get('title',choice['id']),
                economic_rationale=explanation['rationale'],proposal_rationale=choice['rationale'],
                counter_evidence=[explanation['counter_evidence'],choice['countercase']],
                scenarios=scenarios,classification='ASSUMPTION',confidence=explanation.get('confidence','LOW')))
        observations=[]
        for field,item in inputs['observations'].items():
            line=item.get('statement_field')
            if line:
                if line not in replay['ttm']['lines_cny'] or bridge._number(item['value'])!=bridge._number(replay['ttm']['lines_cny'][line]):
                    raise ValueError('D2 historical observation differs from recomputed statement: '+field)
                status='DERIVED_FROM_REPLAYED_ORIGINAL_STATEMENTS_NOT_NORMALIZED_FORECAST'
            else:
                status='SOURCE_BOUND_MAPPING_NOT_ADMITTED_FACT'
            observations.append(dict(field=field,declared=deepcopy(item),verification_status=status))
        facts=[]
        for statement in replay['original_statements']:
            for field,row in statement['rows'].items():
                facts.append(dict(field=field,classification='REPORTED_ORIGINAL_NOT_FORMAL_FACT_ADMISSION',
                    **deepcopy(row)))
        result.update(status='SOURCE_BOUND_D2_DRAFT',company_name=inputs['name'],
            as_of=inputs['financial_basis'],available_at=inputs['generated_at'],
            source_time_verification=source_time_scope,
            parameter_basis=deepcopy(inputs['parameter_basis']),branches=branches,
            fact_anchors=facts,historical_observations=observations,
            historical_statement_replay=replay,source_replay_status='ORIGINAL_STATEMENTS_RECOMPUTED_AND_MATCHED',
            source_replay_scope='HISTORICAL_ACCOUNTING_NOT_NORMALIZED_EARNINGS_OR_DISTRIBUTABLE_CASH',
            predecessor_package_binding=deepcopy(package_ref),
            predecessor_scope='EXACT_PACKAGE_IDENTITY_AND_HISTORY_CONTEXT_NOT_REVALIDATED_OLD_VALUATION',
            capital_path_recomputed=True,valuation_input_compilation_status='NOT_E2_NEW_COMPANY_COMPILATION',
            limitations=deepcopy(inputs['limitations']),economic_review_items=deepcopy(policy['economic_review_items']),
            assurance_limits=deepcopy(policy['assurance_limits']),
            unknowns=([dict(field=field,value=None,status='NORMALIZATION_NOT_ESTABLISHED',
                reason='历史重算不等于正常化盈利或区间已被证明')
                for field in ('normalized_parent_profit_cny','normalized_range') if replay.get(field) is None]+
                [dict(field=row['field']+'.'+key,value=None,status='ECONOMIC_ATTRIBUTION_NOT_ESTABLISHED',
                    reason='单项税后归母归属、重复项或加回资格未证实；不表示情景没有税率或归属假设')
                    for row in replay['normalization_open_items']
                    for key in ('after_tax_parent_adjustment_cny','overlap_with_ex_nonrecurring','proposed_addback_cny')
                    if key in row and row[key] is None]+
                [dict(field=row['field']+'.recurrence',value=row['recurrence'],status='RECURRENCE_NOT_ESTABLISHED',
                    reason='历史项目的持续性及情景稳定性未证实')
                    for row in replay['normalization_open_items'] if row.get('recurrence')=='NOT_ESTABLISHED']),
            normalization_open_items=deepcopy(replay['normalization_open_items']),
            invalidation_conditions=['来源哈希、主体、期间、会计口径或假设版本变更时失效并重新校验']+
                ['出现支持以下反证的新证据时重审：'+text for branch in branches for text in branch['counter_evidence']],
            blockers=['D2_ASSUMPTIONS_NOT_APPROVED','NOT_E2_NEW_COMPANY_COMPILATION',
                      'NORMALIZED_EARNINGS_AND_LEGAL_DISTRIBUTION_NOT_ESTABLISHED'])
        # Recheck every actually consumed input after all parsing and source replay.
        for ref in list(closure):
            _read(root,ref,[],as_json=False)
        result['source_bindings']=closure
        result['input_fingerprint']=_fingerprint(dict(schema_version=SCHEMA,symbol=symbol,
            sources=closure,implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            original_replay={k:v for k,v in replay.items() if k!='observed_at'}))
        result['draft_sha256']=result['input_fingerprint']
        return result
    except _MissingSource as missing:
        result.update(status='MISSING_SOURCE',source_bindings=closure,missing_sources=[missing.binding],
                      blockers=['SOURCE_MISSING:'+missing.binding['path']])
        return result


def build_operating_assumption_draft(*, root: Path, symbol: str, now: datetime,
        assumption_binding: dict | None = None, proposal_binding: dict | None = None) -> dict:
    """Pure-read public D2 entry; no source collection, mutation, approval or valuation."""
    return load_operating_assumption_draft(root=root,symbol=symbol,now=now,
        assumption_binding=assumption_binding,proposal_binding=proposal_binding)

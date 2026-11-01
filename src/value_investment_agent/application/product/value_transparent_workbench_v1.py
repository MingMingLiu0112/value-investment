"""Public, read-only composition of native value research; no new financial math."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import hashlib
from itertools import islice
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

from .common import require_inside
from ..discovery.value_candidate_selection import select_current_value_candidates
from ..research.company_profile import load_company_profile
from ..research.company_profile_sources_v1 import load_source_company_profile
from ..research.operating_assumption_draft_v1 import load_operating_assumption_draft
from ..research.value_research_analysis import load_current_value_research_analysis
from .first_research_input_view_v1 import read_first_research_input
from ..research.main_valuation_revalidation_v1 import read_main_valuation_revalidation
from ..research.operating_cash_consumption_v1 import read_operating_cash_consumption
from ..research.agent_review.operating_task_v2 import LiveOperatingTaskService
from ..decision.value_action_plan import load_registered_value_action_plans

VERSION = 'value-transparent-workbench-v1'
SECTION_IDS = ('selection', 'profile', 'research', 'assumptions', 'cash',
               'valuation', 'price', 'decision', 'continuity', 'evidence')
ERRORS = (ValueError, OSError, KeyError, TypeError, RuntimeError, ArithmeticError)
BAD = {'UNASSESSABLE', 'FAILED', 'CONFLICT', 'SOURCE_REVALIDATION_FAILED'}
ABSENT = {'NOT_STARTED', 'MISSING_SOURCE', 'UNAVAILABLE'}


def _json(value):
    if isinstance(value, (datetime, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


def _bindings(root, value):
    """Recheck explicit native bindings, not arbitrary manifest-relative locators.

    Native consumers own resolution/verification of their internal PDF locators.
    Their exported source/spec/receipt bindings are project-relative raw hashes.
    """
    result = {}
    singular = {'source_binding', 'source_spec', 'receipt_binding', 'package_binding',
                'proposal_binding', 'spec_binding', 'record_binding', 'candidate_binding',
                'registry_binding', 'publication_binding', 'bundle_binding'}
    plural = {'source_bindings', 'evidence_bindings'}
    def check(item):
        if not isinstance(item, dict):
            raise ValueError('PUBLIC_SOURCE_BINDING_MUST_BE_OBJECT')
        digest = item.get('sha256')
        name = item.get('path', item.get('local_path'))
        if (name is None and isinstance(item.get('source_id'), str)
                and isinstance(item.get('pdf_sha256'), str)
                and re.fullmatch('[0-9a-f]{64}', item['pdf_sha256'])):
            # A role's evidence-identity binding is not a file locator. The
            # native response validator checks it against the cold source context.
            return
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ValueError('PUBLIC_SOURCE_BINDING_REQUIRES_PATH_AND_HASH')
        name = name.replace('\\', '/')
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('PUBLIC_SOURCE_BINDING_HASH_REQUIRED')
        if PureWindowsPath(name).drive or PurePosixPath(name).is_absolute():
            candidate = Path(name)
            if not candidate.is_absolute():
                raise ValueError('PUBLIC_SOURCE_BINDING_DRIVE_RELATIVE')
            path = require_inside(root, candidate, 'public workbench source')
            name = path.relative_to(root).as_posix()
        else:
            if any(p in {'', '.', '..'} for p in name.split('/')):
                raise ValueError('PUBLIC_SOURCE_BINDING_MUST_BE_PROJECT_RELATIVE:' + name)
            path = require_inside(root, root / name, 'public workbench source')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('PUBLIC_SOURCE_BINDING_CHANGED:' + name)
        if name in result and result[name] != digest:
            raise ValueError('PUBLIC_SOURCE_BINDING_CONFLICT:' + name)
        result[name] = digest
    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if key in singular and child is not None:
                    check(child)
                elif key in plural:
                    if not isinstance(child, list):
                        raise ValueError('PUBLIC_SOURCE_BINDING_LIST_REQUIRED')
                    for binding in child:
                        check(binding)
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
    visit(value)
    return [dict(path=p, sha256=h) for p, h in sorted(result.items())]


def _call(root, symbol, operation):
    try:
        value = operation()
        if value is None:
            return dict(status='NOT_STARTED', reason='NO_REGISTERED_NATIVE_RESULT')
        if not isinstance(value, dict):
            raise ValueError('NATIVE_PUBLIC_RESULT_MUST_BE_OBJECT')
        if value.get('symbol', symbol) != symbol:
            raise ValueError('NATIVE_PUBLIC_RESULT_SYMBOL_MISMATCH')
        if value.get('action', 'no_order') != 'no_order':
            raise ValueError('NATIVE_PUBLIC_RESULT_ACTION_MISMATCH')
        _bindings(root, value)
        return deepcopy(value)
    except ERRORS as error:
        return dict(status='UNASSESSABLE', reason=str(error), error_type=type(error).__name__)


def _profile(root, symbol, now):
    value = load_company_profile(root=root, symbol=symbol, now=now)
    # Exactly the existing public API fallback: damaged current research never falls back.
    if value.get('blockers') == ['NO_CURRENT_SOURCE_BOUND_RESEARCH']:
        return load_source_company_profile(root=root, symbol=symbol, now=now)
    return value


def _live(root, symbol, now):
    """Same bounded native discovery, without read/list lock-file side effects."""
    service = LiveOperatingTaskService(root)
    if not service.base.exists():
        return dict(symbol=symbol, status='NOT_STARTED', reason='NO_VERIFIED_LIVE_RESEARCH_RESULT')
    children = list(islice(service.base.iterdir(), 101))
    if len(children) > 100:
        raise ValueError('RESEARCH_TASK_DISCOVERY_LIMIT_EXCEEDED: max_entries=100')
    rows = []
    for path in sorted(children):
        if not path.is_dir() or not path.name.startswith('rt-'):
            continue
        spec, state, pin = service._load(path.name, recover=False)
        if spec['symbol'] != symbol:
            continue
        if len(rows) >= 20:
            raise ValueError('RESEARCH_TASK_RESULT_LIMIT_EXCEEDED: max_results=20')
        rows.append((state['updated_at'], path.name, spec, state, pin))
    if not rows:
        return dict(symbol=symbol, status='NOT_STARTED', reason='NO_VERIFIED_LIVE_RESEARCH_RESULT')
    _, task_id, spec, state, pin = max(rows, key=lambda r: (r[0], r[1]))
    task = service._view(spec, state, pin, now)
    # Head/source changes never cause a fallback to an older successful task.
    if service._load(task_id, recover=False)[2] != pin:
        raise ValueError('LIVE_TASK_CHANGED_DURING_PUBLIC_READ')
    partial = (bool(task.get('research_draft'))
               and task.get('error_code') not in {'SOURCE_OR_IMPLEMENTATION_CHANGED', 'LIVE_CHECKPOINT_INVALID'})
    if (task.get('scope') != 'LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED'
            or (task['status'] != 'SUCCEEDED' and not partial)):
        raise ValueError(task.get('error_code') or 'LATEST_TASK_NOT_VERIFIED_LIVE_RESEARCH')
    keys = ('symbol', 'status', 'task_id', 'scope', 'model_id', 'research_draft',
            'context_fingerprint', 'source_binding', 'research_as_of', 'research_completeness',
            'operating_driver_bridge', 'record_binding')
    public = {k: task[k] for k in keys if k in task}
    if task['status'] != 'SUCCEEDED':
        public.update(status='PARTIAL', execution_status=task['status'], reason=task.get('error_code'))
    return public, task


def _blockers(results):
    rows = []
    for name, value in results.items():
        if value.get('reason'):
            rows.append(dict(source=name, reason=value['reason']))
        for item in value.get('blockers', []):
            rows.append(dict(source=name, reason=deepcopy(item)))
        for item in value.get('items', []):
            if isinstance(item, dict):
                for reason in item.get('blockers', []):
                    rows.append(dict(source=name + '.items', symbol=item.get('symbol'),
                                     reason=deepcopy(reason)))
    return rows


def _project_native(value, fields):
    """Retain native version/assurance and selected fields without reinterpreting them."""
    common = ('status', 'reason', 'error_type', 'blockers', 'source_bindings', 'source_binding',
              'source_spec', 'receipt_binding', 'review_binding', 'input_descriptor_sha256',
              'input_fingerprint', 'research_as_of', 'research_version', 'financial_basis',
              'valuation_date', 'latest_actual_period', 'available_at', 'computed_at')
    return {key: deepcopy(value[key]) for key in (*common, *fields) if key in value}


def _existing_cash(value):
    fields = ('joint_capital_review', 'source_native_cash_review')
    result = _project_native(value, fields)
    # These are outputs of the already verified native consumer, never a second formula.
    summary = value.get('financial_summary') or {}
    material = {k: deepcopy(summary[k]) for k in ('pending_joint_capital_research',
                'verified_financial_review', 'js2_economic_review') if k in summary}
    if material:
        result['financial_material'] = material
    if (value.get('status') not in BAD | ABSENT and not material
            and not any(value.get(key) for key in fields)):
        result.update(status='NOT_STARTED', reason='EXISTING_ANALYSIS_HAS_NO_CONSUMED_CASH_MATERIAL')
    result['origin'] = 'EXISTING_CONSUMED_RESEARCH_NOT_NEW_LIVE_EXECUTION'
    return result


def _native_decision(value):
    result = _project_native(value, ('research_case', 'investment_conclusion',
        'decision_recommendation', 'decision', 'candidate_action', 'items',
        'economic_review_status', 'economic_assumptions_reviewed', 'valuation_status',
        'research_admitted', 'strategy_admitted', 'action_admitted', 'formal_eligibility',
        'price_comparison_eligible', 'current_comparable', 'main_range_adopted',
        'approval_changed', 'model_validity', 'current_alignment', 'price_policy',
        'dated_research_review_thresholds'))
    joint = value.get('joint_capital_review') or {}
    if 'conditional_price' in joint:
        result['conditional_price'] = deepcopy(joint['conditional_price'])
    result['native_statuses'] = dict(
        research={k: deepcopy(value[k]) for k in ('status', 'economic_review_status',
                  'valuation_status', 'investment_conclusion') if k in value},
        price={k: deepcopy(result[k]) for k in ('current_alignment', 'conditional_price',
               'price_policy', 'dated_research_review_thresholds') if k in result},
        approval={k: deepcopy(value[k]) for k in ('formal_eligibility', 'research_admitted',
                  'strategy_admitted', 'action_admitted', 'economic_assumptions_reviewed',
                  'main_range_adopted', 'approval_changed') if k in value},
        decision={k: deepcopy(value[k]) for k in ('decision_recommendation', 'decision',
                  'candidate_action', 'items') if k in value})
    return result


def _section(root, ident, title, summary, results, interpretations):
    statuses = [r.get('status', r.get('data_status', 'UNKNOWN')) for r in results.values()]
    usable = [s for s in statuses if s not in BAD | ABSENT]
    status = ('UNASSESSABLE' if any(s in BAD for s in statuses) and not usable else
              'PARTIAL' if any(s in BAD | ABSENT | {'PARTIAL'} for s in statuses) and usable else
              'NOT_STARTED' if not usable else 'SOURCE_BOUND_RESULTS')
    try:
        bindings = _bindings(root, results)
    except ERRORS as error:
        return dict(id=ident, title=title, status='UNASSESSABLE', summary=summary,
                    data=None, blockers=[dict(reason=str(error), error_type=type(error).__name__)])
    return dict(id=ident, title=title, status=status, summary=summary,
                data=dict(native_results=deepcopy(results), knowledge_types=interpretations,
                          source_bindings=bindings), blockers=_blockers(results))


def read_value_transparent_workbench(*, root, symbol, now):
    """GET composition only. No acquisition, provider, task recovery, or file writes."""
    root = Path(root).resolve()
    if not isinstance(symbol, str) or re.fullmatch('[0-9]{6}', symbol) is None:
        raise ValueError('VALUE_WORKBENCH_SIX_DIGIT_SYMBOL_REQUIRED')
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('VALUE_WORKBENCH_AWARE_CLOCK_REQUIRED')
    read = lambda operation: _call(root, symbol, operation)
    def selection():
        value = select_current_value_candidates(root=root, now=now, limit=200)
        return dict(symbol=symbol, status=value.get('data_status', 'UNKNOWN'),
                    blockers=deepcopy(value.get('blockers', [])),
                    observed_scope_status='IN_OBSERVED_SCOPE' if any(x['symbol'] == symbol for x in value['items']) else 'NOT_IN_OBSERVED_SCOPE',
                    items=[x for x in value['items'] if x['symbol'] == symbol],
                    context={k: value[k] for k in ('coverage', 'screening_scope', 'as_of', 'quote_date',
                        'available_at', 'snapshot_status', 'refresh_status', 'source_bindings', 'blockers') if k in value})
    selected = read(selection)
    profile = read(lambda: _profile(root, symbol, now))
    legacy = read(lambda: load_current_value_research_analysis(root=root, symbol=symbol, now=now))
    first = read(lambda: read_first_research_input(root=root, symbol=symbol, now=now))
    main = read(lambda: read_main_valuation_revalidation(root=root, symbol=symbol, now=now))
    old_draft = read(lambda: load_operating_assumption_draft(root=root, symbol=symbol, now=now))
    core_decision = read(lambda: load_registered_value_action_plans(root, now=now, symbols=[symbol]))
    task_holder = []
    def live():
        result = _live(root, symbol, now)
        if isinstance(result, tuple):
            public, task = result
            task_holder.append(task)
            return public
        return result
    research = read(live)
    cash = (read(lambda: read_operating_cash_consumption(root=root, task=task_holder[0], now=now))
            if task_holder and research.get('status') != 'UNASSESSABLE' else
            dict(status='NOT_STARTED', reason='VERIFIED_LIVE_DRIVER_TASK_REQUIRED'))
    facts = dict(type='FACT', title='来源事实', explanation='仅原生消费者已核验的披露字段；历史事实不代表当前完整资料。')
    derived = dict(type='DERIVED', title='代码推导', explanation='原生消费者的历史算术、逐年现金及条件估值；不在本层重算。')
    assumption = dict(type='ASSUMPTION', title='研究假设', explanation='未来经营驱动、资金可达、资本及终端是条件输入，不是事实或批准。')
    unknown = dict(type='UNKNOWN', title='未知与拒绝', explanation='原生缺口、失败和未批准原样保留，不以旧成功或默认零替代。')
    sections = []
    def add(ident, title, summary, results, kinds):
        sections.append(_section(root, ident, title, summary, results, kinds))
    add('selection', '为何进入研究范围', '四通道原始理由、排除与范围；未出现于观察范围不等于全市场不合格。', {'selection': selected}, [facts, unknown])
    add('profile', '企业画像与模型适用性', '来源主营与条件路由不等于护城河、质量或估值批准。', {'profile': profile}, [facts, assumption, unknown])
    existing_research = _project_native(legacy, ('thesis', 'return_driver', 'supporting_evidence',
        'counter_evidence', 'thesis_breakers', 'next_events', 'human_review_items', 'assurance_limits'))
    existing_research['origin'] = 'EXISTING_SOURCE_BOUND_RESEARCH_NOT_NEW_AI'
    add('research', '公开经营研究与反证', '旧来源研究与新AI执行分别呈现；新AI未执行不表示从未研究，任何执行成功也不等于经济批准。',
        {'existing_research': existing_research, 'first_input_research': _project_native(first, ('research_case',)),
         'new_live_research': research}, [facts, assumption, unknown])
    add('assumptions', '经营假设及未知', '既有包假设、旧草案与新经营驱动分别呈现；不把来源引用当预测已证明。',
        {'existing_analysis': _project_native(legacy, ('assumptions',)), 'existing_draft': old_draft,
         'first_input': _project_native(first, ('operating_assumptions',)), 'live': research}, [assumption, unknown])
    add('cash', '利润如何成为股东现金', '既有v4现金账与新消费分别保留；新live未启动不表示旧现金账缺失。清偿旧应付款不是新股东分配。',
        {'existing_analysis': _existing_cash(legacy), 'operating_cash': cash,
         'first_input': first, 'main_revalidation': main}, [facts, derived, assumption, unknown])
    add('valuation', '三情景条件估值', '各版本期间及原始三情景分别保留，不挑最新成功覆盖失败，不视为已采用主区间。', {'existing_analysis': legacy, 'first_input': first, 'main_revalidation': main}, [derived, assumption, unknown])
    def prices(value):
        return {k: deepcopy(value[k]) for k in ('status', 'reason', 'source_spec', 'input_descriptor_sha256',
            'financial_basis', 'latest_actual_period', 'valuation_date', 'price_policy', 'dated_research_review_thresholds',
            'current_alignment', 'current_comparable', 'main_range_adopted') if k in value}
    old_price = prices(legacy)
    joint = legacy.get('joint_capital_review') or {}
    if 'conditional_price' in joint:
        old_price['conditional_price'] = deepcopy(joint['conditional_price'])
    add('price', '条件价格与当前可比资格', 'dated草案、历史估值与当前价格分开；未选择规则不制造数字买价。', {'existing_analysis': old_price, 'main_revalidation': prices(main)}, [derived, assumption, unknown])
    add('decision', '原生决定、资格与阻断', '原生研究、价格、批准和决定逐版本单列；WAIT、NO_TRADE、未知及拒绝不互相替代。顶层不授权仅是工作台边界，不覆盖原决定。',
        {'public_core': _native_decision(core_decision), 'existing_analysis': _native_decision(legacy),
         'first_input': _native_decision(first), 'main_revalidation': _native_decision(main)}, [unknown])
    if sections[-1]['data'] is not None:
        sections[-1]['data']['workbench_authority'] = dict(action='no_order', formal_eligibility=False,
            quantity=None, scope='WORKBENCH_GRANTS_NO_AUTHORITY_NOT_A_NATIVE_DECISION')
    sections.append(dict(id='continuity', title='持仓与持续跟踪', status='PRIVATE_CONTEXT_REQUIRED',
        summary='个性化持有逻辑需要另行提供私人上下文；本公开读取不检查账户、持仓或成交。',
        data=None, blockers=['PRIVATE_CONTEXT_REQUIRED']))
    # Recheck after every consumer finished, so a mid-read change invalidates affected sections.
    evidence = {}
    for section in sections:
        if section['data'] is None:
            continue
        try:
            for item in _bindings(root, section['data']):
                prior = evidence.get(item['path'])
                if prior is not None and prior != item['sha256']:
                    raise ValueError('PUBLIC_SOURCE_BINDING_CONFLICT:' + item['path'])
                evidence[item['path']] = item['sha256']
        except ERRORS as error:
            section.update(status='UNASSESSABLE', data=None,
                           blockers=[dict(reason=str(error), error_type=type(error).__name__)])
    sections.append(dict(id='evidence', title='来源、期间与版本', status='BOUND_SOURCES' if evidence else 'NO_VERIFIED_BINDINGS',
        summary='仅汇总本次公开消费者已核验的绑定；披露/取得/计算日期及历史PIT限制以各原生结果为准。',
        data=dict(source_bindings=[dict(path=p, sha256=h) for p, h in sorted(evidence.items())],
                  knowledge_types=[facts, derived, assumption, unknown]), blockers=[] if evidence else ['NO_VERIFIED_BINDINGS']))
    result = _json(dict(schema_version=VERSION, action='no_order', symbol=symbol,
                        sections=sections, formal_eligibility=False, quantity=None))
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    return result

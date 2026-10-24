"""Readable economic questions bound to the existing unsigned review contract."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json

from ..research.value_economic_assessment import load_current_value_economic_assessment
from ..research.value_research_analysis import _bound
from .source_native_review_adapter_v2 import prepare_pending_review_response
from .common import load_json_object, sha256_file
from .neutral_valuation_proposal import JOINT_SCHEMA


SCHEMA = 'value-economic-review-materials-v1'


def _joint_capital_review(*, root, handoff, now):
    return project_joint_capital_review(root=root, binding=handoff['candidate_binding'],
        symbol=handoff['symbol'], model_context=handoff['model_context'], now=now)


def project_joint_capital_review(*, root, binding, symbol, model_context, now):
    """Project public consumed capital ledgers, without constructing a signing handoff."""
    from ..research.value_research_analysis import _available

    root = root.resolve()
    _bound(root, binding)
    from .source_native_candidate_v2 import verify_review_candidate
    candidate = verify_review_candidate(root=root, path=root / binding['path'],
        expected_sha256=binding['sha256'])
    _available(candidate['generated_at'], now)
    if candidate.get('input_mode') != JOINT_SCHEMA:
        return None
    if candidate['symbol'] != symbol or candidate['model_context'] != model_context:
        raise ValueError('Joint review differs from the exact selected candidate')
    proposal_path = (root / binding['path']).parent / 'valuation-proposal.json'
    proposal_binding = dict(path=proposal_path.relative_to(root).as_posix(),
        sha256=sha256_file(proposal_path))
    if proposal_binding not in candidate['source_bindings']:
        raise ValueError('Joint review proposal is not bound to the candidate')
    proposal = load_json_object(_bound(root, proposal_binding), 'joint review proposal')
    policy = load_json_object(_bound(root, candidate['economic_policy_binding']), 'joint review policy')
    _available(proposal['generated_at'], now)
    _available(policy['generated_at'], now)
    selected = next(row for row in proposal['choices'] if row['id'] == candidate['selected_choice'])
    policy_choice = next(row for row in policy['choices'] if row['id'] == candidate['selected_choice'])
    timing = candidate['candidate_valuation']['assumptions'].get('valuation_timing')
    # The candidate verifier already recompiles the ledger and model outputs.
    # Projection copies those consumed values, never recalculates a forecast.
    result = dict(schema_version='joint-capital-review-v1', symbol=candidate['symbol'],
        action='no_order', status='CONDITIONAL_PATH_NOT_APPROVED',
        scope='RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS',
        candidate_binding=deepcopy(binding), proposal_binding=proposal_binding,
        policy_binding=deepcopy(candidate['economic_policy_binding']),
        input_descriptor_sha256=candidate['model_context']['input_descriptor_sha256'],
        selected_choice=candidate['selected_choice'],
        date_scope='DATED_CONDITIONAL_MODEL' if timing else 'UNDATED_CONDITIONAL_MODEL',
        basis_at=timing['basis_at'] if timing else None,
        valuation_at=timing['valuation_at'] if timing else None,
        scenarios=[dict(scenario=name, drivers=deepcopy(policy_choice['joint_drivers'][name]),
            ledger=deepcopy(selected['joint_capital_ledgers'][name]),
            valuation_per_share=candidate['candidate_valuation'][name + '_value'])
            for name in ('bear', 'base', 'bull')])
    for source in (binding, *candidate['source_bindings'], *candidate['implementation_bindings']):
        _bound(root, source)
    return result


def _display(value, *, percent=False):
    """Round display strings only; full-precision assessment inputs are retained."""
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError('Economic display requires a finite value')
    return format(number, '.2%' if percent else ',.2f')


def _group_material(group, assessment, materiality):
    earnings = assessment['earnings']
    bridge = assessment['accounting_bridge_review']
    scenarios = assessment['scenarios']
    observations, assumptions, questions = [], [], []
    name = group['id']
    if name == 'EARNINGS':
        title = '\u53ef\u6301\u7eed\u76c8\u5229'
        historical = earnings['historical_bridge']
        if historical['status'] == 'HISTORICAL_RECONCILED_NOT_NORMALIZED':
            observations.append('\u6263\u975e\u5f52\u6bcd\u5229\u6da6 TTM \u5df2\u6309\u6765\u6e90\u671f\u95f4\u590d\u7b97\uff1a'
                + _display(historical['computed_ttm_cny']) + ' CNY\uff1b\u8fd9\u4e0d\u662f\u6b63\u5e38\u5316\u5229\u6da6\u8ba4\u5b9a\u3002')
        else:
            observations.append('\u672c\u7248\u5c1a\u65e0\u5b8c\u6574\u53ef\u590d\u7b97\u7684\u5386\u53f2\u76c8\u5229\u6865\u3002')
        assumptions = [f"{s['scenario']}: \u6a21\u578b\u9996\u5e74\u5229\u6da6 {_display(s['first_year_profit_cny'])} CNY"
            for s in scenarios]
        questions.append('\u54ea\u4e9b\u6536\u76ca\u53ef\u91cd\u590d\uff1f\u7a0e\u540e\u5f52\u5c5e\u3001\u51cf\u503c\u4e0e\u7ef4\u6301\u7ecf\u8425\u6295\u5165\u8c03\u6574\u662f\u5426\u6709\u8bc1\u636e\uff1f\u672a\u5b8c\u6210\u6b63\u5e38\u5316\u65f6\uff0c\u5e94\u62d2\u7edd\u6216\u9650\u5b9a\u4ee3\u7406\u76c8\u5229\u7684\u7528\u9014\u3002')
    elif name == 'DURATION':
        title = '\u7ade\u4e89\u4f18\u52bf\u4e0e\u8870\u51cf'
        observations.append('\u4ee5\u4e0b\u5e74\u9650\u4e0e\u56de\u62a5\u8def\u5f84\u6765\u81ea\u5f53\u524d\u6a21\u578b\u8f93\u5165\uff0c\u4e0d\u662f\u5df2\u88ab\u8bc1\u660e\u7684\u7ade\u4e89\u4f18\u52bf\u671f\u3002')
        assumptions = [f"{s['scenario']}: \u663e\u5f0f\u671f {s['explicit_years']} \u5e74\uff0c\u5176\u4e2d ROE \u9ad8\u4e8e\u6743\u76ca\u6210\u672c {s['years_above_equity_cost']} \u5e74\uff0c\u7ec8\u503c\u8d85\u989d ROE {_display(s['terminal_excess_roe'], percent=True)}"
            for s in scenarios]
        questions.append('\u5b9a\u4ef7\u6743\u3001\u5ba2\u6237\u7559\u5b58\u3001\u7ade\u4e89\u683c\u5c40\u4e0e\u518d\u6295\u8d44\u8bc1\u636e\u662f\u5426\u652f\u6301\u672c\u7248\u5e74\u9650\u53ca\u8870\u51cf\u8def\u5f84\uff1f\u96f6\u7ec8\u503c\u8d85\u989d\u56de\u62a5\u672c\u8eab\u4e0d\u8bc1\u660e\u5047\u8bbe\u4e2d\u6027\u3002')
    elif name == 'DISTRIBUTION':
        title = '\u73b0\u91d1\u5206\u914d\u80fd\u529b'
        count = len(bridge['bridge_results'])
        observations.append((f'\u5386\u53f2\u73b0\u91d1\u53ca\u6743\u76ca\u6865\u5df2\u590d\u7b97 {count} \u6761\uff1b\u53ea\u8bc1\u660e\u5df2\u7ed1\u5b9a\u7814\u7a76\u6570\u636e\u7684\u7b97\u672f\u5173\u7cfb\u3002'
            if count else '\u672c\u7248\u672a\u8986\u76d6\u652f\u6301\u7684\u73b0\u91d1\u53ca\u6743\u76ca\u6865\uff0c\u4e0d\u8868\u793a\u6ca1\u6709\u98ce\u9669\u6216\u5206\u914d\u80fd\u529b\u5df2\u7ecf\u9a8c\u8bc1\u3002'))
        assumptions = [f"{s['scenario']}: \u9996\u5e74\u6a21\u578b\u5206\u7ea2 {_display(s['first_year_dividend_assumption_cny'])} CNY\uff0c\u6d3e\u606f\u6bd4\u4f8b {_display(s['first_year_payout_ratio'], percent=True)}"
            for s in scenarios]
        questions.append('\u5b50\u516c\u53f8\u4e0a\u5212\u3001\u5fc5\u9700\u6d41\u52a8\u6027\u3001\u8d44\u672c\u5f00\u652f\u3001\u507f\u503a\u4e0e\u6cd5\u5b9a\u9650\u5236\u540e\uff0c\u80a1\u4e1c\u53ef\u5f97\u73b0\u91d1\u662f\u5426\u8db3\u4ee5\u652f\u6301\u5047\u8bbe\uff1f\u5386\u53f2\u5bf9\u5e73\u4e0d\u80fd\u4ee3\u66ff\u672a\u6765\u5206\u914d\u5224\u65ad\u3002')
    elif name == 'COST_TERMINAL':
        title = '\u6743\u76ca\u6210\u672c\u4e0e\u7ec8\u503c'
        observations.append('\u8d44\u672c\u6210\u672c\u4e0e\u7ec8\u503c\u654f\u611f\u6027\u6765\u81ea\u7ed1\u5b9a\u60c5\u666f\u590d\u7b97\uff0c\u4e0d\u4ee3\u8868\u5e02\u573a\u5df2\u9690\u542b\u8fd9\u4e9b\u9884\u671f\u3002')
        assumptions = [f"{s['scenario']}: \u6743\u76ca\u6210\u672c {_display(s['cost_of_equity'], percent=True)}\uff0c\u7ec8\u503c\u589e\u957f {_display(s['terminal_growth'], percent=True)}\uff0c\u6298\u73b0\u4e0e\u589e\u957f\u5dee {_display(s['terminal_spread'], percent=True)}"
            for s in scenarios]
        questions.append('\u65e0\u98ce\u9669\u5229\u7387\u3001ERP\u3001beta\u7684\u65e5\u671f\u3001\u5e01\u79cd\u548c\u4ee3\u7406\u9002\u7528\u6027\u662f\u5426\u5408\u7406\uff1f\u7ec8\u503c\u589e\u957f\u4e0e\u518d\u6295\u8d44\u3001\u7ade\u4e89\u8870\u51cf\u662f\u5426\u4e00\u81f4\uff1f')
    elif name == 'EVENT_MODEL':
        title = '\u4e8b\u4ef6\u4e0e\u6a21\u578b\u6709\u6548\u6027'
        observations.append('\u672c\u7248\u72ec\u7acb\u4e8b\u4ef6\u5ba1\u6838\u4ea4\u63a5\u72b6\u6001\uff1a' + materiality['status'])
        if materiality.get('reason'):
            observations.append(materiality['reason'])
        questions.append('\u5b8c\u6574\u516c\u544a\u626b\u63cf\u662f\u5426\u7ed1\u5b9a\u6b64\u6a21\u578b\u7248\u672c\uff1f\u54ea\u4e9b\u4e8b\u4ef6\u6539\u53d8\u4e86\u5047\u8bbe\u6216\u89e6\u53d1\u53cd\u8bc1\uff1f\u8be5\u7ec4\u56de\u7b54\u4e0d\u66ff\u4ee3\u72ec\u7acb\u6750\u6599\u6027\u5ba1\u6838\u3002')
    else:
        title = group.get('question') or name
        questions.append('\u672c\u7ec4\u4f7f\u7528\u539f\u5019\u9009\u7684\u95ee\u9898\u4e0e\u5b57\u6bb5\u8303\u56f4\uff0c\u4e0d\u4ece\u5176\u4ed6\u516c\u53f8\u501f\u7528\u7ecf\u6d4e\u7ed3\u8bba\u3002')
    if group.get('question'):
        questions.insert(0, group['question'])
    if group.get('support'):
        # A candidate author's support is an assertion to review, not a verified fact.
        assumptions.append(group['support'])
    return dict(id=name, title=title, field_paths=list(group['field_paths']),
        verified_observations=observations, conditional_assumptions=assumptions,
        counter_evidence=[group['countercase']] if group.get('countercase') else [],
        judgment_questions=questions, evidence_refs=list(assessment['source_bindings']))


def build_economic_review_materials(*, root, handoff, analysis, now):
    """Revalidate the current assessment against the exact handoff, without signing."""
    assessment = load_current_value_economic_assessment(root=root, symbol=handoff['symbol'], now=now)
    expected = dict(candidate_binding=handoff['candidate_binding'],
        model_context=handoff['model_context'],
        valuation_artifact_sha256=handoff['valuation_artifact_sha256'])
    current_response = prepare_pending_review_response(root=root,
        candidate_path=root / handoff['candidate_binding']['path'],
        candidate_sha256=handoff['candidate_binding']['sha256'])
    if (assessment is None or assessment['symbol'] != handoff['symbol']
            or assessment['action'] != 'no_order'
            or any(assessment[key] is not False for key in
                ('primary_valuation_usable', 'approval_changed', 'strategy_admitted', 'action_admitted'))
            or any(assessment[key] != analysis[key] for key in ('symbol', 'input_descriptor_sha256'))
            or any(assessment['review_binding'].get(key) != analysis['review_binding'].get(key)
                for key in ('candidate_binding', 'model_context', 'package_binding',
                    'workbench_binding', 'review_packet_binding'))
            or any(assessment['review_binding'].get(key) != expected[key]
                for key in ('candidate_binding', 'model_context'))
            or any(current_response.get(key) != value for key, value in expected.items())
            or assessment['input_descriptor_sha256'] != handoff['model_context']['input_descriptor_sha256']):
        raise ValueError('Economic review materials differ from the exact pending candidate')
    assessment = {key: value for key, value in assessment.items() if key != 'assessed_at'}
    groups = handoff['review_questions']
    response_groups = handoff['unsigned_response']['groups']
    if (len({g['id'] for g in groups}) != len(groups)
            or handoff['unsigned_response'] != current_response
            or [(g['id'], g['field_paths']) for g in groups] !=
               [(g['id'], g['field_paths']) for g in response_groups]):
        raise ValueError('Economic material questions differ from signed response scope')
    result = dict(schema_version=SCHEMA, symbol=handoff['symbol'], action='no_order',
        status=('STRESS_ONLY_NOT_PRIMARY' if assessment['model_applicability']['assessment'] == 'STRESS_ONLY'
            else 'PENDING_ECONOMIC_JUDGMENT'), **expected,
        input_descriptor_sha256=assessment['input_descriptor_sha256'],
        assessment_sha256=assessment['assessment_sha256'],
        primary_valuation_usable=False, approval_changed=False,
        groups=[_group_material(g, assessment, handoff['materiality_handoff']) for g in groups],
        economic_assessment=assessment, source_bindings=assessment['source_bindings'])
    joint = _joint_capital_review(root=root, handoff=handoff, now=now)
    if joint is not None:
        result['joint_capital_review'] = joint
    native = analysis.get('source_native_cash_review')
    if native is not None:
        if native['candidate_binding'] != handoff['candidate_binding'] or native['model_context'] != handoff['model_context']:
            raise ValueError('Native cash materials differ from the selected review candidate')
        result['source_native_cash_review'] = deepcopy(native)
        for binding in native['source_bindings']:
            if binding not in result['source_bindings']:
                result['source_bindings'].append(binding)
    for binding in result['source_bindings']:
        _bound(root, binding)
    result['materials_sha256'] = sha256(json.dumps(result, sort_keys=True,
        separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')).hexdigest()
    return result

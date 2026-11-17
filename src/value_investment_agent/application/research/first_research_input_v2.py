"""First v4 input compilation, without a predecessor, registration or approval.

Financial numbers come exclusively from the injected/server-owned cold PDF replay.
The source manifest's `verified`/PASS fields are never admission credentials.
This module only assembles existing contracts; it owns no financial formulas.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from ..product.common import encode_json_bytes, require_inside, write_new_bytes
from ..product.neutral_valuation_proposal import compile_joint_cash_choice_v4, _json_numbers
from ..product.source_bound_inputs import source_catalog_sha256
from ...domain.valuation.joint_capital_cash_path_v4 import HISTORICAL_FIELDS, SCOPE
from ...research_input import build_research_run_spec
from ...research_application import ResearchApplicationService
from .v4_input_adapter import build_v4_descriptor, scenario_payload, MODEL_VERSION
from .v4_valuation_router import build_v4_valuation_router

SCHEMA = 'first-research-input-spec-v1'
ASSUMPTIONS_SCHEMA = 'first-research-assumptions-v1'
RECEIPT_SCHEMA = 'first-research-input-receipt-v2'
MODEL = 'residual_income_or_equity_value'
COMPILATION_SCOPE = 'condition_scenarios_not_adopted_main_range'
NARRATIVE = {'industry', 'investment_path', 'thesis', 'return_driver',
             'mispricing_hypothesis', 'positives', 'counter_evidence', 'thesis_breakers', 'next_events'}


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(root, binding, closure):
    if (not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}
            or not isinstance(binding['path'], str) or not isinstance(binding['sha256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', binding['sha256'])
            or Path(binding['path']).is_absolute() or '..' in Path(binding['path']).parts):
        raise ValueError('First compilation requires exact project-relative path/hash bindings')
    path = require_inside(root, root / binding['path'], 'first input source')
    raw = path.read_bytes()
    if _digest(raw) != binding['sha256']:
        raise ValueError('First input source hash mismatch: ' + binding['path'])
    if binding not in closure:
        closure.append(dict(binding))
    return raw


def _time(value, ceiling):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > ceiling:
        raise ValueError('First input source follows cutoff or lacks timezone')
    return stamp


def _number(value):
    if not isinstance(value, str):
        raise ValueError('Financial values require explicit Decimal strings')
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('Invalid financial number') from error
    if not result.is_finite():
        raise ValueError('Nonfinite financial number')
    return result


def _binding(root, path, payload):
    raw = encode_json_bytes(payload)
    return dict(path=path.relative_to(root).as_posix(), sha256=_digest(raw)), raw


def _implementations():
    from . import first_research_input_v1
    from importlib.resources import files
    from ... import research_application
    from ...infrastructure.filings import first_research_fact_replay_v2
    from ...domain.valuation import joint_capital_cash_path_v4
    from ...valuation_models import residual_income_path_v4
    from ..product import source_bound_inputs, neutral_valuation_proposal
    from . import v4_input_adapter
    modules = (research_application, joint_capital_cash_path_v4, residual_income_path_v4,
               source_bound_inputs, neutral_valuation_proposal, v4_input_adapter,
               first_research_fact_replay_v2)
    return {**{module.__name__: _digest(Path(module.__file__).read_bytes()) for module in modules},
            'value_investment_agent.domain.research.issuer_identity_registry.json':
                _digest(files('value_investment_agent.domain.research')
                        .joinpath('issuer_identity_registry.json').read_bytes()),
            __name__: _digest(Path(__file__).read_bytes()),
            first_research_input_v1.__name__: _digest(Path(first_research_input_v1.__file__).read_bytes())}


def _default_fact_replay(**kwargs):
    # A server implementation, never a dynamic import named by a submitted spec.
    from ...infrastructure.filings.first_research_fact_replay_v2 import replay_first_research_facts
    return replay_first_research_facts(**kwargs)


from .first_research_input_v1 import _prepare

def replay_first_research_input_v2(*, root: Path, receipt_binding: dict, now: datetime,
                                fact_replay=None) -> dict:
    """Cold-reparse originals, recompile D2 inputs and execute the existing v4 service."""
    if now.utcoffset() is None:
        raise ValueError('Aware cold-recompilation clock required')
    root = root.resolve()
    closure = []
    receipt = json.loads(_read(root, receipt_binding, closure))
    if receipt.get('schema_version') != RECEIPT_SCHEMA or receipt.get('action') != 'no_order':
        raise ValueError('Invalid first compilation receipt')
    if receipt.get('implementation_sha256') != _implementations():
        raise ValueError('First compilation implementation changed; create a new version')
    output = _path_from_binding(root, receipt['package_binding']).parent
    prepared, spec, inputs = _prepare(root, receipt['spec_binding'], output, now,
                                      fact_replay or _default_fact_replay)
    if spec is None:
        raise ValueError('Cold first compilation has missing inputs')
    if prepared['cold_replay_fingerprint'] != receipt['cold_replay_fingerprint']:
        raise ValueError('Cold facts changed since first compilation')
    if _read(root, prepared['proposal_binding'], closure) != prepared['proposal_bytes']:
        raise ValueError('Cold proposal differs')
    package = json.loads(_read(root, receipt['package_binding'], closure))
    if encode_json_bytes(package) != encode_json_bytes(prepared['package']):
        raise ValueError('Cold package differs from actual source and D2 consumption')
    descriptor = build_v4_descriptor(package, root=root)
    outcome = ResearchApplicationService(router=build_v4_valuation_router(), now_utc=lambda: now).run_company_research(
        build_research_run_spec(descriptor))
    if descriptor.input_sha256 != receipt['input_descriptor_sha256']:
        raise ValueError('Cold input descriptor differs')
    for binding in inputs + closure:
        _read(root, binding, [])
    from ..product.company_research import _serialize_outcome
    research_result = _serialize_outcome(outcome)
    source_bindings = []
    for binding in inputs + closure:
        if binding not in source_bindings:
            source_bindings.append(binding)
    fingerprint = _digest(encode_json_bytes(dict(descriptor=descriptor.input_sha256,
        sources=source_bindings, cold_facts=receipt['cold_replay_fingerprint'],
        implementation=receipt['implementation_sha256'])))
    return dict(status='COLD_RECOMPILED', action='no_order', formal_eligibility=False,
        formal_fact_count=0, approval_changed=False, economic_quality_proven=False,
        input_descriptor_sha256=descriptor.input_sha256, issuer_identity_status=outcome.issuer_identity_status,
        valuation_status=outcome.valuation.status if outcome.valuation else 'NOT_READY',
        valuation=json.loads(outcome.valuation.to_json()) if outcome.valuation else None,
        input_fingerprint=fingerprint, source_bindings=source_bindings,
        package_binding=receipt['package_binding'], proposal_binding=receipt['proposal_binding'],
        research_case=package['research_case'], research_result=research_result,
        artifact_bundle=research_result['artifact_bundle'], blockers=research_result['blockers'],
        annual_ledgers=prepared['proposal']['choices'][0]['joint_capital_ledgers'],
        scope='FIRST_SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_APPROVAL',
        compilation_scope=COMPILATION_SCOPE, main_range_adopted=False,
        main_valuation_range=None, external_acceptance_required=True,
        external_acceptance_scope='NOT_GRANTED_BY_THIS_COMPILER',
        scenario_label_scope='V4_COMPATIBILITY_KEYS_NOT_ADOPTED_MAIN_BEAR_BASE_BULL_RANGE')


def _path_from_binding(root, binding):
    return require_inside(root / 'runtime', root / binding['path'], 'first compilation output')


def build_first_research_input_v2(*, root: Path, spec_binding: dict, output_dir: Path,
                               now: datetime, fact_replay=None) -> dict:
    """Publish only new proposal/package/cold receipt; never register a current candidate."""
    if now.utcoffset() is None:
        raise ValueError('Aware first compilation clock required')
    root = root.resolve()
    output = require_inside(root / 'runtime', output_dir.resolve(), 'first compilation output')
    if output.exists():
        raise FileExistsError('First compilation output must be new')
    prepared, spec, closure = _prepare(root, spec_binding, output, now, fact_replay or _default_fact_replay)
    if spec is None:
        return prepared
    write_new_bytes(output / 'proposal.json', prepared['proposal_bytes'])
    descriptor = build_v4_descriptor(prepared['package'], root=root)
    package_binding, package_bytes = _binding(root, output / 'package.json', prepared['package'])
    write_new_bytes(output / 'package.json', package_bytes)
    receipt = dict(schema_version=RECEIPT_SCHEMA, action='no_order', formal_eligibility=False,
        formal_fact_count=0, approval_changed=False, economic_quality_proven=False,
        compilation_scope=COMPILATION_SCOPE, main_range_adopted=False,
        external_acceptance_required=True, external_acceptance_scope='NOT_GRANTED_BY_THIS_COMPILER',
        status='FIRST_INPUT_COMPILED', symbol=spec['symbol'], spec_binding=deepcopy(spec_binding),
        proposal_binding=prepared['proposal_binding'], package_binding=package_binding,
        input_descriptor_sha256=descriptor.input_sha256,
        cold_replay_fingerprint=prepared['cold_replay_fingerprint'],
        source_bindings=closure, predecessor_package=None, approvals_created=0,
        market_inputs_consumed=False, account_inputs_consumed=False,
        implementation_sha256=_implementations())
    rb, raw = _binding(root, output / 'receipt.json', receipt)
    write_new_bytes(output / 'receipt.json', raw)
    cold = replay_first_research_input_v2(root=root, receipt_binding=rb, now=now, fact_replay=fact_replay)
    cold_binding, cold_bytes = _binding(root, output / 'cold-recompile.json', cold)
    write_new_bytes(output / 'cold-recompile.json', cold_bytes)
    return dict(receipt, receipt_binding=rb, cold_receipt_binding=cold_binding,
                cold_recompile=cold, input_fingerprint=cold['input_fingerprint'],
                artifact_bundle=cold['artifact_bundle'], research_result=cold['research_result'],
                research_case=cold['research_case'], annual_ledgers=cold['annual_ledgers'],
                source_bindings=cold['source_bindings'], external_acceptance_required=True)

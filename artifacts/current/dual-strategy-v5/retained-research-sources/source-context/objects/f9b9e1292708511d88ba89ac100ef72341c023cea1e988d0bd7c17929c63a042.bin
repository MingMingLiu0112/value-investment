"""Compile a finite proposal into shared research inputs, without approval."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

from .common import load_json_object, require_inside, sha256_file, write_new_json
from .neutral_valuation_proposal import build_neutral_valuation_proposal
from .source_bound_inputs import verify_package_local_sources
from .financial_review_attachment import load_financial_review_attachment
from .workbench import build_current_workbench_for_symbol
from .research_review_packet import build_research_review_packet
from ...m1_valuation_package_builder import build_descriptor
from ...research_input import build_research_run_spec
from .research_reviews import build_research_review_model_context


def prepare_pending_research_candidate(*, root: Path, package_path: Path,
        package_sha256: str, policy_path: Path, policy_sha256: str,
        choice_id: str, output_dir: Path, schedule_request: dict,
        schedule_request_sha256: str, computed_at: datetime | None = None) -> dict:
    """Use actual calculation time, retaining old versions and event debt.

    This prepares a new research version, not historical contemporaneous input.
    Market inputs and approvals are deliberately not inherited across versions.
    The ordinary scheduler and application still decide whether the run is legal.
    """
    root = root.resolve()
    output_dir = require_inside(root / 'runtime', output_dir, 'pending candidate')
    if output_dir.exists():
        raise FileExistsError('pending candidate directory already exists')
    if computed_at is not None:
        raise ValueError('actual candidate preparation does not accept an injected computation time')
    now = datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError('candidate computation time requires timezone')
    source = load_json_object(package_path, 'candidate source package')
    policy = load_json_object(policy_path, 'candidate economic policy')
    if choice_id not in {row['id'] for row in policy.get('choices', [])}:
        raise ValueError('candidate must select an existing finite choice')
    if schedule_request.get('symbol') != source['symbol']:
        raise ValueError('candidate schedule issuer mismatch')
    day = now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    if day < source['point_in_time']['research_as_of']:
        raise ValueError('candidate cannot predate the retained research version')
    output_dir.mkdir(parents=True)
    proposal_path = output_dir / 'valuation-proposal.json'
    proposal = build_neutral_valuation_proposal(root=root, package_path=package_path,
        package_sha256=package_sha256, policy_path=policy_path,
        policy_sha256=policy_sha256, output_path=proposal_path)
    if computed_at is None:
        now = datetime.now(timezone.utc)
        day = now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    choice = next(row for row in proposal['choices'] if row['id'] == choice_id)
    inputs = choice['actual_calculation_inputs']
    candidate = deepcopy(source)
    version = f"pending-{source['symbol']}-{day}-{choice_id}-{policy_sha256[:12]}"
    candidate.update(schema_version='m1-valuation-package-v2', package_version=version,
                     descriptor_version=version, run_id=version)
    candidate['point_in_time'].update(research_as_of=day, valuation_date=day,
        available_at=now.isoformat(), computed_at=now.isoformat())
    catalog = {}
    official_identities = {}
    index_bindings = policy.get('issuer_index_bindings', [])
    for binding in index_bindings:
        index_path = require_inside(root, root / binding['path'], 'candidate issuer index')
        if sha256_file(index_path) != binding['sha256']:
            raise ValueError('candidate issuer index hash mismatch')
        index = load_json_object(index_path, 'candidate issuer index')
        for row in index.get('announcements', []):
            if str(row.get('secCode')) != source['symbol']:
                continue
            identity = dict(venue='CNINFO', security_code=str(row['secCode']),
                issuer_name=row.get('secName'), organization_id=row.get('orgId'))
            if not identity['issuer_name'] or not identity['organization_id']:
                raise ValueError('candidate issuer index identity fields missing')
            url = urljoin('https://static.cninfo.com.cn/', row.get('adjunctUrl', ''))
            if not url.endswith('/' + str(row.get('announcementId')) + '.PDF'):
                raise ValueError('candidate issuer index announcement/attachment mismatch')
            if url in official_identities and official_identities[url] != identity:
                raise ValueError('candidate issuer index conflicting identity')
            official_identities[url] = identity

    def add_source(item):
        item = deepcopy(item)
        local = item.get('local_path', item['location'])
        path = require_inside(root, root / local, 'candidate source')
        if not path.is_file() or sha256_file(path) != item['sha256']:
            raise ValueError('candidate requires original identical local bytes')
        item['local_path'] = path.relative_to(root).as_posix()
        if not item.get('source_available_at'):
            published = item.get('published_at')
            # Old date-level official disclosure gets a conservative next-day
            # boundary, not an invented intraday time. New research is known now.
            available = (datetime.fromisoformat(published) + timedelta(days=1)
                if item['kind'] == 'official_issuer_filing' and published else now)
            item['source_available_at'] = available.isoformat()
            item['availability_basis'] = ('conservative_next_day_disclosure'
                if item['kind'] == 'official_issuer_filing' and published else 'current_candidate_acquisition')
        if datetime.fromisoformat(item['source_available_at']) > now:
            raise ValueError('candidate source is after actual computation cutoff')
        previous = catalog.get(item['id'])
        if previous and (previous['local_path'], previous['sha256']) != (item['local_path'], item['sha256']):
            raise ValueError('candidate source identity conflict')
        catalog[item['id']] = item

    for item in source['sources']:
        add_source(item)
    for index, binding in enumerate(index_bindings):
        add_source(dict(id=f'candidate-official-index-{index}', kind='research_artifact',
            location=binding['path'], local_path=binding['path'], sha256=binding['sha256'],
            source_available_at=now.isoformat(), availability_basis='current_candidate_acquisition',
            source_url='https://www.cninfo.com.cn/new/hisAnnouncement/query'))
    proposal_ref = dict(id='pending-economic-proposal', path=proposal_path.relative_to(root).as_posix(),
                        sha256=sha256_file(proposal_path))
    for index, binding in enumerate(proposal['source_bindings'] + [proposal_ref]):
        add_source(dict(id=binding.get('id', f'candidate-lineage-{index}'),
            kind='research_artifact', location=binding['path'], local_path=binding['path'],
            sha256=binding['sha256'], source_available_at=now.isoformat(),
            availability_basis='current_candidate_acquisition', retrieved_at=now.isoformat(),
            parser_version='pending-finite-research-candidate-v1'))
    add_source(dict(id=proposal_ref['id'], kind='research_artifact', location=proposal_ref['path'],
        sha256=proposal_ref['sha256'], source_available_at=now.isoformat(),
        availability_basis='current_candidate_acquisition'))
    refs = [proposal_ref]
    rebase = proposal.get('financial_rebase')
    financial_review = None
    if rebase:
        financial_review = load_financial_review_attachment(root=root, symbol=source['symbol'],
            manifest_path=root / rebase['manifest_path'], manifest_sha256=rebase['manifest_sha256'])
        for item in financial_review['source_bindings']:
            if item.get('id') and item.get('source_url'):
                add_source(dict(id=item['id'], kind='official_issuer_filing', location=item['source_url'],
                    local_path=item['path'], sha256=item['sha256'],
                    source_available_at=item['available_at_conservative'],
                    availability_basis='retained_conservative_disclosure_bound',
                    issuer_identity=official_identities.get(item['source_url'])))
        for legacy in catalog.values():
            if legacy.get('kind') != 'official_issuer_filing' or legacy.get('issuer_identity'):
                continue
            matches = [item for item in financial_review['source_bindings']
                if item['sha256'] == legacy['sha256']
                and item.get('source_url') in official_identities]
            if len(matches) == 1:
                matched = matches[0]
                legacy['location'] = matched['source_url']
                legacy['issuer_identity'] = deepcopy(official_identities[matched['source_url']])
                legacy['identity_basis'] = 'exact_announcement_index_and_identical_retained_pdf_bytes'

    case = candidate['research_case']
    case.update(as_of=day, run_id=version, generated_at=now.isoformat(), research_version=version,
                quote_date=None, valuation_status='CONDITIONAL_RESEARCH_PENDING_REVIEW')
    case.setdefault('missing_date_reasons', {})['quote_date'] = 'New pending model has no admitted quote.'
    case['blockers'] = list(dict.fromkeys([*case.get('blockers', []),
        'pending_economic_model_review', 'pending_complete_event_materiality_review']))
    case['blockers'] = [
        '本候选优势期和全资本衰减未获主模型批准'
        if item == '现有强衰减压力情景不是中性主估值' else item
        for item in case['blockers']]
    case['evidence_refs'].append(proposal_ref)
    case['thesis'] += ' 本候选实际消费既有有限方案：' + choice['rationale']
    case['counter_evidence'].append(dict(kind='hypothesis', text=choice['countercase'],
                                        evidence_refs=[proposal_ref['id']]))
    summary = case['financial_summary']
    summary.update(parent_equity_cny=inputs['start_book_equity'], ordinary_shares=inputs['ordinary_shares'])
    summary[inputs['profit_anchor_field']] = inputs['profit_anchor']
    summary['normalized_parent_profit_cny'] = None
    summary['pending_model_choice'] = choice_id
    summary['pending_model_limits'] = proposal['assurance_limits']
    if financial_review:
        summary['verified_financial_review'] = financial_review
        summary['financial_equity_bridge'] = rebase.get('equity_bridge_result')
    facts = candidate['facts']
    facts.update(as_of=day, confidence='低', kind='quality_compounder')
    facts['operating_inputs'].update(start_book_equity=inputs['start_book_equity'],
                                     ordinary_shares=inputs['ordinary_shares'])
    facts['scenario_inputs'] = {name: {**values, 'forecast_roes': values['forecast_roe']}
                               for name, values in inputs['scenarios'].items()}
    for values in facts['scenario_inputs'].values():
        values.pop('forecast_roe')
    timing = inputs.get('valuation_timing')
    if timing:
        timing = deepcopy(timing)
        timing['valuation_at'] = now.isoformat()
        timing['evidence_refs'] = refs
        facts['valuation_timing'] = timing
        candidate['dependencies']['model_version'] = 'residual-income-equity-shared-dated-v2'
    facts['evidence_refs'] = list({ref['id']: ref for ref in [*facts['evidence_refs'], proposal_ref]}.values())
    if financial_review:
        consumed_financial_ids = {ref['id'] for ref in
            inputs.get('valuation_timing', {}).get('evidence_refs', [])}
        official_refs = [dict(id=item['id'], path=catalog[item['id']]['local_path'], sha256=item['sha256'])
            for item in financial_review['source_bindings'] if item.get('id') in consumed_financial_ids
            and item.get('source_url')]
        if not official_refs or any(not catalog[ref['id']].get('issuer_identity') for ref in official_refs):
            raise ValueError('rebased financial inputs require exact official issuer index bindings')
        # Old sources remain immutable lineage; operative rebased facts use the
        # independently verified official IDs rather than legacy local aliases.
        facts['evidence_refs'] = [proposal_ref, *official_refs]
    names = ['cost_of_equity', 'terminal_roe', 'terminal_growth', 'retention']
    count = len(facts['scenario_inputs']['base']['forecast_roes'])
    names += [f'forecast_roes_{i}' for i in range(count)]
    assumptions, bindings = [], []
    for name in names:
        index = int(name[len('forecast_roes_'):]) if name.startswith('forecast_roes_') else None
        field = f'forecast_roes.{index}' if index is not None else name
        values = {key: scenario[name] if index is None else scenario['forecast_roes'][index]
                  for key, scenario in facts['scenario_inputs'].items()}
        numbers = [Decimal(values[key]) for key in ('bear', 'base', 'bull')]
        ordering = 'ascending' if numbers[0] <= numbers[1] <= numbers[2] else 'descending'
        assumptions.append(dict(name=name, unit='ratio', **values,
            basis='pending_finite_shared_model_choice_not_official_forecast',
            rationale=choice['rationale'] + ' 反证：' + choice['countercase'],
            confidence='low', sensitivity='high', ordering=ordering,
            evidence_refs=refs, blockers=[]))
        bindings.extend(dict(assumption_name=name, scenario=key, field_path=field,
            expected_value=value, evidence_refs=refs) for key, value in values.items())
    candidate['assumptions'] = dict(assumptions=assumptions, evidence_refs=refs,
        blockers=['Selected finite model assumptions remain pending economic approval.'
            if item == 'Strong-fade stress assumptions are not admitted as the neutral main valuation.' else item
            for item in source['assumptions'].get('blockers', [])])
    candidate['assumption_bindings'] = bindings
    candidate['quote'] = None
    candidate.pop('entry_thesis', None)
    candidate.pop('investment_consistency_review', None)
    candidate['model_validity_input'] = dict(model_id=candidate['dependencies']['model_version'],
        valid_from=day, events=[], blockers=['pending_complete_event_materiality_review'])
    candidate['dependencies']['scan_watermark'] = None
    contract = deepcopy(source.get('source_contract', {}))
    contract.update(schema_version='source-bound-research-inputs-v1', cutoff_at=now.isoformat(),
        distribution_input_status='NOT_ADMITTED', strict_contemporaneous_pit='NOT_PROVEN',
        fact_semantics_scope='source_anchored_capital_and_historical_profit_not_normalized_forecast')
    if rebase:
        contract['fact_anchors'] = [dict(field=field, source_id=rebase[field]['source_id'],
            physical_page=rebase[field]['physical_page'], source_value=rebase[field]['value'],
            unit=rebase[field]['unit'], scope=('consolidated_parent_equity' if field == 'start_book_equity'
                else 'issued_ordinary_shares'), period_end=rebase[field]['period_end'])
            for field in ('start_book_equity', 'ordinary_shares')]
    candidate['source_contract'] = contract
    candidate['sources'] = list(catalog.values())
    candidate['supersedes'] = dict(path=package_path.relative_to(root).as_posix(),
        sha256=package_sha256, reason='new pending finite research candidate, not approved/current admission')
    candidate['recommendation_schema_version'] = 'advisory-decision-recommendation-v3'
    verify_package_local_sources(root, candidate)
    descriptor = build_descriptor(candidate, root=root)
    context = build_research_review_model_context(descriptor=descriptor,
                                                 spec=build_research_run_spec(descriptor))
    package_output = output_dir / 'package.json'
    write_new_json(package_output, candidate)
    workbench_path = output_dir / 'workbench.json'
    workbench = build_current_workbench_for_symbol(root=root, symbol=source['symbol'],
        package_path=package_output, output_path=workbench_path, schedule_request=schedule_request,
        schedule_request_sha256=schedule_request_sha256,
        recommendation_schema_version='advisory-decision-recommendation-v3')['result']
    if workbench.get('decision_recommendation'):
        build_research_review_packet(root=root, package_path=package_output,
            package_sha256=sha256_file(package_output), workbench_path=workbench_path,
            workbench_sha256=sha256_file(workbench_path), output_path=output_dir / 'consumed-review.json')
    result = dict(schema_version='pending-research-candidate-v1', symbol=source['symbol'],
        status='PENDING_REVIEW', action='no_order', generated_at=now.isoformat(),
        candidate_research_as_of=day, financial_period=source['point_in_time']['report_period'],
        prior_research_as_of=source['point_in_time']['research_as_of'],
        selected_choice=choice_id, choice_rationale=choice['rationale'], countercase=choice['countercase'],
        retained_date_valuation=choice['valuation'], candidate_valuation=workbench.get('valuation'),
        model_context=context, approval_changed=False, research_admitted=False,
        model_context_scope=('ACTUALLY_CONSUMED' if workbench.get('decision_recommendation')
                             else 'PREPARED_NOT_CONSUMED'),
        execution_status=workbench.get('suggested_state'),
        schedule_gate=workbench.get('schedule_gate'),
        research_blockers=workbench.get('research_blockers', []),
        price_admitted=False, position_guidance=None, canonical_written=False,
        registered_current_case_changed=False, strict_contemporaneous_pit='NOT_PROVEN',
        event_coverage='NOT_REVIEWED_FOR_NEW_CANDIDATE',
        date_semantics='New unapproved research computed at actual time; old report basis and raw public dates retained; no historical PIT/current data admission.',
        model_limits=proposal['assurance_limits'], review_questions=proposal['economic_review_items'],
        review_groups=deepcopy(policy.get('human_review_groups', [])),
        economic_policy_binding=dict(path=policy_path.relative_to(root).as_posix(), sha256=policy_sha256),
        source_bindings=[dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
            for path in (package_path, policy_path, proposal_path, package_output, workbench_path)],
        implementation_bindings=[dict(path=name, sha256=sha256_file(root / name))
            for name in ('src/value_investment_agent/application/product/pending_research_candidate.py',)
            if (root / name).is_file()],
        recommendation_type=workbench.get('suggested_state'),
        decision_blockers=list(dict.fromkeys([
            *(workbench.get('decision_recommendation') or {}).get('blockers', []),
            *workbench.get('research_blockers', [])])))
    for group in result['review_groups']:
        if (not isinstance(group, dict) or not all(isinstance(group.get(key), str) and group[key].strip()
                for key in ('id', 'question', 'support', 'countercase', 'impact'))
                or not isinstance(group.get('field_paths'), list) or not group['field_paths']):
            raise ValueError('economic review groups require concrete questions, evidence and scope')
        for field_path in group['field_paths']:
            value = candidate
            for key in field_path.split('.'):
                if not isinstance(value, dict) or key not in value:
                    raise ValueError('economic review group references an absent candidate field')
                value = value[key]
    all_sources = {item['path']: item for item in result['source_bindings']}
    for path, digest in verify_package_local_sources(root, candidate):
        if sha256_file(path) != digest:
            raise ValueError('candidate source changed during shared application run')
        relative = path.relative_to(root).as_posix()
        all_sources[relative] = dict(path=relative, sha256=digest)
    result['source_bindings'] = list(all_sources.values())
    write_new_json(output_dir / 'candidate.json', result)
    return result


def verify_pending_research_candidate(*, root: Path, path: Path, expected_sha256: str) -> dict:
    """Bind visible candidate values to actual shared application artifacts."""
    from .decision_surface import verify_current_decision_workbench

    root = root.resolve()
    path = require_inside(root / 'runtime', path, 'pending candidate receipt')
    if sha256_file(path) != expected_sha256:
        raise ValueError('pending candidate receipt hash mismatch')
    data = load_json_object(path, 'pending candidate')
    if (data.get('schema_version') != 'pending-research-candidate-v1'
            or data.get('status') != 'PENDING_REVIEW' or data.get('action') != 'no_order'
            or any(data.get(key) is not False for key in ('approval_changed', 'research_admitted',
                'price_admitted', 'canonical_written', 'registered_current_case_changed'))
            or data.get('position_guidance') is not None
            or data.get('strict_contemporaneous_pit') != 'NOT_PROVEN'):
        raise ValueError('pending candidate admission boundary mismatch')
    sources = data.get('source_bindings')
    if not isinstance(sources, list) or not sources:
        raise ValueError('pending candidate source bindings missing')
    for item in sources:
        original = require_inside(root, root / item['path'], 'pending candidate source')
        if sha256_file(original) != item['sha256']:
            raise ValueError('pending candidate source drift')
    for item in data.get('implementation_bindings', []):
        implementation = require_inside(root, root / item['path'], 'candidate implementation')
        if sha256_file(implementation) != item['sha256']:
            raise ValueError('pending candidate implementation drift')
    package_path = path.parent / 'package.json'
    workbench_path = path.parent / 'workbench.json'
    if not {package_path.relative_to(root).as_posix(), workbench_path.relative_to(root).as_posix()}.issubset(
            {item['path'] for item in sources}):
        raise ValueError('pending candidate actual inputs and outputs not bound')
    package = load_json_object(package_path, 'candidate package')
    policy_binding = data['economic_policy_binding']
    policy_path = require_inside(root, root / policy_binding['path'], 'candidate economic policy')
    if policy_binding not in sources or sha256_file(policy_path) != policy_binding['sha256']:
        raise ValueError('candidate economic policy binding mismatch')
    policy = load_json_object(policy_path, 'candidate economic policy')
    if data.get('review_groups') != policy.get('human_review_groups', []):
        raise ValueError('candidate review questions differ from economic policy')
    descriptor = build_descriptor(package, root=root)
    context = build_research_review_model_context(descriptor=descriptor, spec=build_research_run_spec(descriptor))
    workbench = load_json_object(workbench_path, 'candidate actual workbench')
    consumed = bool(workbench.get('decision_recommendation'))
    if (data['symbol'] != package['symbol'] or workbench['symbol'] != package['symbol']
            or data['candidate_research_as_of'] != package['point_in_time']['research_as_of']
            or data['model_context'] != context
            or data['candidate_valuation'] != workbench.get('valuation')
            or data.get('model_context_scope') != ('ACTUALLY_CONSUMED' if consumed else 'PREPARED_NOT_CONSUMED')
            or data.get('execution_status') != workbench.get('suggested_state')
            or data.get('research_blockers') != workbench.get('research_blockers', [])
            or data.get('schedule_gate') != workbench.get('schedule_gate')):
        raise ValueError('pending candidate differs from exact research inputs or outputs')
    if workbench.get('decision_recommendation'):
        verify_current_decision_workbench(workbench)
        if workbench.get('input_descriptor_sha256') != descriptor.input_sha256:
            raise ValueError('pending candidate descriptor differs from actual consumption')
    if sha256_file(path) != expected_sha256:
        raise ValueError('pending candidate changed during verification')
    return data

"""Compose verified daily outputs into the existing public product contract."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from ..application.product.common import load_json_object, require_inside, sha256_file, write_new_json
from ..application.product.daily_product_update import semantic_digest
from ..application.product.decision_surface import project_verified_decision_workbench, verify_current_decision_workbench
from ..application.product.value_decision_explanation import project_value_decision_explanation
from ..application.product.research_publication_input import prepare_research_publication_input
from .daily_trade_assistant import _project_quote_gate
from .read_models.existing_research_report import public_workbench_payload_from_snapshot
from .read_models.product_workbench import product_workbench_from_payload


def _load(root, binding):
    path = require_inside(root/'runtime', root/binding['path'], 'daily product source')
    if sha256_file(path) != binding['sha256']:
        raise ValueError('daily product source hash mismatch')
    return load_json_object(path, 'daily product source')


def classify_product_changes(previous, current):
    if previous is None:
        return ['PRODUCT_LAYOUT_INITIALIZATION']
    changes = set()
    if previous.get('layout_version') != current.get('layout_version'):
        changes.add('PRODUCT_LAYOUT_CHANGE')
    for symbol in set(previous.get('companies', {})) | set(current.get('companies', {})):
        old = previous.get('companies', {}).get(symbol, {})
        new = current.get('companies', {}).get(symbol, {})
        if old.get('quote') != new.get('quote'):
            changes.add('QUOTE_CHANGE')
        if old.get('event') != new.get('event'):
            changes.add('OFFICIAL_EVENT_OBSERVATION_CHANGE')
        if old.get('inputs') != new.get('inputs'):
            changes.add('RESEARCH_FACT_ASSUMPTION_OR_REVIEW_CHANGE')
        if old.get('decision') != new.get('decision'):
            changes.add('VALUATION_OR_DECISION_CHANGE')
    for role in set(previous.get('extensions', {})) | set(current.get('extensions', {})):
        if semantic_digest(previous.get('extensions', {}).get(role)) != semantic_digest(current.get('extensions', {}).get(role)):
            changes.add('HOTSPOT_OBSERVATION_CHANGE' if role == 'hotspot_report' else 'PORTFOLIO_RISK_CHANGE')
    return sorted(changes)


def compose_daily_product(*, root: Path, folder: Path, published: dict,
                          batch: dict, extensions: dict | None = None):
    pointer = published['pointer']
    state_binding = pointer.get('daily_product_state_binding')
    prior = _load(root, state_binding) if state_binding else None
    publication_receipt = _load(root, dict(path=pointer['current_publication']['receipt'],
                                         sha256=pointer['current_publication']['receipt_sha256']))
    source_document = _load(root, dict(path=publication_receipt['source_bindings_path'],
                                     sha256=publication_receipt['source_bindings_sha256']))
    parent_binding = source_document['publication_input_binding']
    parent_envelope = _load(root, _load(root, parent_binding)['read_model_binding'])
    envelope = deepcopy(parent_envelope)
    extensions = dict(envelope.get('product_extensions', {}), **(extensions or {}))
    envelope.pop('decision_workbench_binding', None)
    selected = {(binding['path'], binding['sha256']) for binding in
                load_json_object(root/'config/user-research-workflow-v1.json', 'workflow')['review_candidates'].values()}
    envelope['research_supplement_bindings'] = [binding for binding in
        envelope.get('research_supplement_bindings', []) if binding.get('role') != 'pending_research_candidate'
        or (binding['path'], binding['sha256']) in selected]
    payload = public_workbench_payload_from_snapshot(published['snapshot'])
    payload['generated_at'] = datetime.now(timezone.utc).isoformat()
    receipts = []
    content = deepcopy(prior['content']) if prior else {'companies': {}, 'extensions': {}}
    content['layout_version'] = 'dual-strategy-product-v1'
    dates = {row['research_as_of'] for row in batch['cases']}
    if len(dates) != 1:
        raise ValueError('研究时点不同，不可将多个版本拼成一个正式产品')
    payload['as_of'] = dates.pop()
    for row in batch['cases']:
        receipt = _load(root, row['receipt'])
        if (receipt.get('action') != 'no_order' or receipt['symbol'] != row['symbol']
                or receipt['status'] != 'RESEARCH_RUN_COMPLETED_WITH_ADMISSION_STATUS'):
            raise ValueError('daily company receipt identity or completion mismatch')
        workbench_binding = receipt['outputs']['workbench']
        workbench = _load(root, workbench_binding)
        project_verified_decision_workbench(payload, root=root,
            path=root/workbench_binding['path'], expected_sha256=workbench_binding['sha256'])
        quote = receipt['quote_check']
        quote_id = f"daily-quote-{row['symbol']}-{quote.get('bundle_sha256', '')[:16]}"
        if not any(item['evidence_id'] == quote_id for item in payload['audit']['evidence']):
            _project_quote_gate(payload, symbol=row['symbol'], quote_check=quote)
        card = next(c for c in payload['companies'] if c['symbol'] == row['symbol'])
        card['decision_review'] = [entry for entry in card['decision_review'] if entry['label'] not in {
            '当前操作依据', '加仓复核边界', '减仓与退出依据', '本次行情更新'}]
        from ..application.product.research_reviews import verify_human_approval_transport_provenance
        restored = verify_current_decision_workbench(
            workbench,
            human_approval_provenance_verifier=lambda approval: (
                verify_human_approval_transport_provenance(root, approval)
            ),
        )
        explanation = project_value_decision_explanation(restored,
            evidence_scope='RETAINED_RESEARCH')
        explanation_path = folder/(row['symbol']+'-value-decision-explanation.json')
        write_new_json(explanation_path, explanation)
        envelope.setdefault('additional_evidence_bindings', []).append(dict(
            path=explanation_path.relative_to(root).as_posix(), sha256=sha256_file(explanation_path)))
        card['decision_review'].append(dict(label='当前操作依据', value=explanation['candidate_explanation']))
        card['decision_review'].append(dict(label='加仓复核边界', value='原论点和新证据仍成立、模型与价格符合规则，并核对实际组合容量；不因下跌自动加仓。'))
        card['decision_review'].append(dict(label='减仓与退出依据', value='论点削弱或失效、重大反证、财务或集中度风险触发人工复核；普通价格波动不自动触发卖出。'))
        if receipt['quote_check']['status'] in {'NOT_ADMITTED', 'PENDING_EXTERNAL_DATA'}:
            card['decision_review'].append(dict(label='本次行情更新', value=receipt['quote_check'].get('reason', '未完成')))
        receipts.append(row['receipt'])
        decision = workbench.get('decision_recommendation') or {}
        semantic_decision = {key: decision.get(key) for key in (
            'recommendation_type', 'valuation_range', 'model_validity', 'price_bridge_status',
            'price_attractiveness_status', 'entry_zone', 'reduce_zone', 'blockers', 'thesis',
            'counter_evidence', 'thesis_breakers', 'next_events', 'recommendation_reasons',
            'exit_conditions', 'thesis_consistency_status')}
        # Package/review pins capture changes to facts and approved assumptions;
        # quote transport timestamps and per-run paths are not market changes.
        content['companies'][row['symbol']] = dict(
            inputs={key: value for key, value in receipt['inputs'].items()
                    if key not in {'previous_daily_receipt', 'previous_workbench', 'publication_input'}},
            decision=semantic_decision,
            quote={key: receipt['quote_check'].get(key) for key in
                   ('quote_date', 'display_price', 'status', 'display_scope')})
        for role in ('event_observation', 'financial_review', 'research_review', 'monthly_review'):
            binding = receipt['outputs'].get(role)
            if binding:
                supplement = _load(root, binding)
                old = envelope.get('research_supplement_bindings', [])
                envelope['research_supplement_bindings'] = [b for b in old
                    if not (b.get('role') == role and _load(root, b).get('symbol') == row['symbol'])]
                envelope['research_supplement_bindings'].append(dict(role=role, **binding))
                if role == 'event_observation':
                    content['companies'][row['symbol']]['event'] = {
                        key: supplement.get(key) for key in
                        ('collection_status', 'announcement_count', 'scan_from', 'scan_to', 'error')}
                    scan_binding = supplement.get('scan_binding')
                    if scan_binding:
                        scan = _load(root, scan_binding)
                        content['companies'][row['symbol']]['event']['announcements'] = [
                            {key: item.get(key) for key in ('announcement_id', 'published_at',
                                'title', 'source_url', 'review_status', 'materiality_candidate')}
                            | {'original_hashes': sorted(ref['sha256'] for ref in item.get('evidence_refs', []))}
                            for item in scan.get('announcements', [])]
    extension_values = {}
    for role, binding in (extensions or {}).items():
        value = _load(root, binding)
        if value.get('action') != 'no_order':
            raise ValueError('product extension must be no_order')
        extension_values[role] = value
        content['extensions'][role] = value.get('semantic_content', value)
    envelope.update(snapshot=json.loads(json.dumps(asdict(product_workbench_from_payload(payload)), default=str)),
                    publication_input_binding=parent_binding,
                    daily_batch_bindings=receipts,
                    product_extensions=extensions or {})
    envelope.setdefault('additional_evidence_bindings', []).extend(
        dict(path=p.relative_to(root).as_posix(), sha256=sha256_file(p)) for p in (
            root/'scripts/current/render_dual_strategy_artifact_pages.mjs',
            root/'src/value_investment_agent/presentation/daily_product_composition.py'))
    read_path = folder/'product-read-model.json'
    write_new_json(read_path, envelope)
    handoff_path = folder/'product-publication-input.json'
    handoff = prepare_research_publication_input(root=root, read_model_path=read_path,
                expected_sha256=sha256_file(read_path), output_path=handoff_path)
    current_hash = semantic_digest(content)
    old_hash = prior.get('semantic_sha256') if prior else None
    changed = current_hash != old_hash
    categories = classify_product_changes(prior.get('content') if prior else None, content)
    state = dict(action='no_order', semantic_sha256=current_hash, content=content)
    state_path = folder/'product-update-state.json'
    write_new_json(state_path, state)
    return dict(handoff=handoff, handoff_path=handoff_path, model=product_workbench_from_payload(payload),
                state_binding=dict(path=state_path.relative_to(root).as_posix(), sha256=sha256_file(state_path)),
                extension_values=extension_values), dict(material_change=changed,
                classification='PRODUCT_OR_EVIDENCE_CHANGE' if changed else 'NO_MATERIAL_CHANGE',
                categories=categories if changed else [],
                previous_semantic_sha256=old_hash, current_semantic_sha256=current_hash)

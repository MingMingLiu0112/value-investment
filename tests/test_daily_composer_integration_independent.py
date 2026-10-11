"""Execute the composer with isolated pinned inputs; never publish externally."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
import json
import pytest

from test_pending_review_response import signed  # noqa: F401
from test_product_workbench_excel import _payload
from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.presentation import daily_product_composition as composer
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload


@pytest.mark.parametrize('same_workbench', [False, True], ids=['new-run-same-semantics', 'exact-repeat'])
def test_composer_schema_single_company_inheritance_and_repeat_nochange(signed, monkeypatch, same_workbench):
    root = signed['root']
    canonical = root / 'canonical.xlsx'
    canonical.write_bytes(b'synthetic canonical sentinel; not a real workbook')
    canonical_before = canonical.read_bytes()
    write_new_json(root / 'config/user-research-workflow-v1.json', dict(review_candidates={}))
    symbol = signed['candidate']['symbol']
    other = '600519' if symbol != '600519' else '600887'

    def retain(name, value):
        path = root / 'runtime/composer-fixture' / name
        write_new_json(path, value)
        return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))

    payload = _payload()
    for row in payload['opportunities']:
        row['symbol'] = symbol
    card = payload['companies'][0]
    card['symbol'] = symbol
    card['decision_review'] = [dict(label='当前操作依据', value='old'),
                               dict(label='本次行情更新', value='old'),
                               dict(label='独立保留项', value='retained')]
    untouched = deepcopy(card)
    untouched.update(symbol=other, name='Synthetic unselected issuer')
    payload['companies'].append(untouched)
    payload['audit']['evidence'].append(dict(payload['audit']['evidence'][0],
        evidence_id=f'daily-quote-{symbol}-'))
    snapshot = json.loads(json.dumps(asdict(product_workbench_from_payload(payload)), default=str))
    expected_other = next(c for c in composer.public_workbench_payload_from_snapshot(snapshot)['companies']
                          if c['symbol'] == other)
    envelope = retain('parent-read.json', {})
    parent = retain('parent-input.json', dict(read_model_binding=envelope))
    sources = retain('sources.json', dict(publication_input_binding=parent))
    receipt = retain('publication.json', dict(source_bindings_path=sources['path'],
                                             source_bindings_sha256=sources['sha256']))
    prior_content = dict(layout_version='dual-strategy-product-v1',
        companies={other: dict(inputs={'package_sha256': 'b' * 64},
                               decision={'recommendation_type': 'NO_ACTION'},
                               event={'announcements': [{'announcement_id': 'retained'}]})},
        extensions={})
    prior = retain('prior-state.json', dict(content=prior_content, semantic_sha256='a' * 64))
    pointer = dict(daily_product_state_binding=prior,
        current_publication=dict(receipt=receipt['path'], receipt_sha256=receipt['sha256']))
    workbench = signed['path'].parent / 'workbench.json'
    daily = retain('daily.json', dict(action='no_order', symbol=symbol,
        status='RESEARCH_RUN_COMPLETED_WITH_ADMISSION_STATUS',
        inputs={'package_sha256': 'c' * 64},
        outputs={'workbench': dict(path=workbench.relative_to(root).as_posix(),
                                  sha256=sha256_file(workbench))},
        quote_check=dict(status='NOT_ADMITTED', reason='Synthetic missing quote')))
    batch = dict(cases=[dict(symbol=symbol, research_as_of='2026-10-11', receipt=daily)])
    handoffs = []

    def isolated_handoff(*, root, read_model_path, expected_sha256, output_path):
        assert sha256_file(read_model_path) == expected_sha256
        value = dict(action='no_order', read_model_binding=dict(
            path=read_model_path.relative_to(root).as_posix(), sha256=expected_sha256))
        write_new_json(output_path, value)
        handoffs.append(value)
        return value

    monkeypatch.setattr(composer, 'prepare_research_publication_input', isolated_handoff)
    for path in ('scripts/current/render_dual_strategy_artifact_pages.mjs',
                 'src/value_investment_agent/presentation/daily_product_composition.py'):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('synthetic code binding', encoding='utf-8')
    published = dict(pointer=pointer, snapshot=snapshot)
    retained = deepcopy(published)
    first_folder = root / 'runtime/composer-first'
    first_folder.mkdir()
    first, changes = composer.compose_daily_product(root=root, folder=first_folder,
        published=published, batch=batch)
    assert published == retained
    assert changes['material_change'] is True
    state = json.loads((root / first['state_binding']['path']).read_text(encoding='utf-8'))
    assert state['content']['companies'][other] == prior_content['companies'][other]
    first_envelope = json.loads((first_folder / 'product-read-model.json').read_text(encoding='utf-8'))
    actual = composer.public_workbench_payload_from_snapshot(first_envelope['snapshot'])
    selected = next(c for c in actual['companies'] if c['symbol'] == symbol)
    labels = [entry['label'] for entry in selected['decision_review']]
    for label in ('当前操作依据', '加仓复核边界', '减仓与退出依据', '本次行情更新'):
        assert labels.count(label) == 1
    assert all(set(entry) == {'label', 'value'} for entry in selected['decision_review'])
    assert dict(label='独立保留项', value='retained') in selected['decision_review']
    assert next(c for c in actual['companies'] if c['symbol'] == other) == expected_other
    second_folder = root / 'runtime/composer-second'
    second_folder.mkdir()
    repeated = dict(pointer=dict(pointer, daily_product_state_binding=first['state_binding']),
                    snapshot=first_envelope['snapshot'])
    if not same_workbench:
        next_workbench = json.loads(workbench.read_text(encoding='utf-8'))
        next_workbench['generated_at'] = (datetime.fromisoformat(next_workbench['generated_at'])
                                          - timedelta(seconds=1)).isoformat()
        next_binding = retain('next-workbench.json', next_workbench)
        next_daily = json.loads((root / daily['path']).read_text(encoding='utf-8'))
        next_daily['outputs']['workbench'] = next_binding
        batch = dict(cases=[dict(symbol=symbol, research_as_of='2026-10-11',
                                receipt=retain('next-daily.json', next_daily))])
    if same_workbench:
        # A repeated audit ID is contractually rejected; only a new run with
        # identical economic inputs is expected to reach semantic nochange.
        before_rejection = deepcopy(repeated)
        with pytest.raises(ValueError, match='Decision workbench evidence id already exists'):
            composer.compose_daily_product(root=root, folder=second_folder,
                published=repeated, batch=batch)
        assert repeated == before_rejection
        assert canonical.read_bytes() == canonical_before
        assert not (second_folder / 'product-read-model.json').exists()
        assert not (second_folder / 'product-update-state.json').exists()
        assert len(handoffs) == 1
        return
    second, repeat_changes = composer.compose_daily_product(root=root, folder=second_folder,
        published=repeated, batch=batch)
    assert repeat_changes['material_change'] is False
    assert repeat_changes['classification'] == 'NO_MATERIAL_CHANGE'
    assert repeat_changes['categories'] == []
    assert repeat_changes['current_semantic_sha256'] == changes['current_semantic_sha256']
    repeated_payload = composer.public_workbench_payload_from_snapshot(
        json.loads((second_folder / 'product-read-model.json').read_text(encoding='utf-8'))['snapshot'])
    assert next(c for c in repeated_payload['companies'] if c['symbol'] == symbol)['decision_review'] == selected['decision_review']
    assert len(handoffs) == 2 and second['handoff']['action'] == 'no_order'
    assert canonical.read_bytes() == canonical_before

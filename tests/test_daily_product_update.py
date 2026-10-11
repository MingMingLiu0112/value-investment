from pathlib import Path
import pytest

from value_investment_agent.application.product.common import write_new_json
from value_investment_agent.application.product.daily_product_update import run_product_update, semantic_digest


def run(tmp_path, *, fail=False, changed=True, publish=True, publisher=None):
    def research(folder):
        folder.mkdir(parents=True)
        path = folder/'batch-receipt.json'
        write_new_json(path, dict(action='no_order', failed_case_count=int(fail),
            blocked_asset_count=0, partial_product_count=0))
        return path
    return run_product_update(root=tmp_path, output_dir=tmp_path/'runtime/update',
        published={'pointer': {'canonical_workbook_sha256': 'a'*64}},
        research_runner=research,
        composer=lambda *args: ({'action': 'no_order'}, {'material_change': changed}),
        publisher=publisher or (lambda *args: {'status': 'PUBLISHED_WPS_READONLY_VERIFIED'}),
        publish=publish)


def test_failed_company_does_not_publish_successful_partial_batch(tmp_path):
    result = run(tmp_path, fail=True, publisher=lambda *args: pytest.fail('must not publish'))
    assert result['status'] == 'UPDATE_FAILED' and not result['canonical_written']
    assert result['blockers']


def test_identical_input_never_overwrites_excel(tmp_path):
    result = run(tmp_path, changed=False, publisher=lambda *args: pytest.fail('must not publish'))
    assert result['status'] == 'NO_MATERIAL_CHANGE' and not result['canonical_written']


def test_publish_failure_retains_failure_not_ready_status(tmp_path):
    def fail(*args): raise ValueError('WPS failed or sync conflict')
    result = run(tmp_path, publisher=fail)
    assert not result['canonical_written'] and 'WPS' in result['blockers'][0]


def test_publish_success_and_explicit_update_only_are_separate(tmp_path):
    assert run(tmp_path)['canonical_written']
    assert run(tmp_path/'other', publish=False)['status'] == 'UPDATED_NOT_PUBLISHED'


def test_retry_requires_new_directory_never_overwrites_receipt(tmp_path):
    run(tmp_path)
    with pytest.raises(FileExistsError): run(tmp_path)


def test_transport_time_is_not_improved_company_value():
    assert semantic_digest({'price': '10', 'quote_date': '2026-10-09', 'generated_at': 'a'}) == semantic_digest(
        {'price': '10', 'quote_date': '2026-10-09', 'generated_at': 'b'})
    assert semantic_digest({'price': '10', 'quote_date': '2026-10-09'}) != semantic_digest(
        {'price': '11', 'quote_date': '2026-10-09'})
    assert semantic_digest({'inputs': {'package': 'a'}}) != semantic_digest({'inputs': {'package': 'b'}})


def test_changed_original_evidence_is_not_erased_from_semantic_identity():
    assert semantic_digest({'evidence_refs': [{'sha256': 'a'}]}) != semantic_digest(
        {'evidence_refs': [{'sha256': 'b'}]})


def test_product_runtime_paths_need_not_be_json_serializable(tmp_path):
    result = run_product_update(root=tmp_path, output_dir=tmp_path/'runtime/paths',
        published={'pointer': {'canonical_workbook_sha256': 'a'*64}},
        research_runner=lambda folder: _receipt(folder),
        composer=lambda *args: ({'handoff_path': Path('local.json')},
            {'material_change': True, 'current_semantic_sha256': 'b'*64}),
        publisher=lambda *args: pytest.fail('report only'), publish=False)
    assert result['status'] == 'UPDATED_NOT_PUBLISHED'
    assert result['semantic_sha256'] == 'b'*64


def _receipt(folder):
    folder.mkdir(parents=True)
    path = folder/'batch-receipt.json'
    write_new_json(path, dict(action='no_order', failed_case_count=0,
        blocked_asset_count=0, partial_product_count=0))
    return path

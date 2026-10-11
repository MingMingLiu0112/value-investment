"""Synthetic fixtures only: local consent and public aggregate boundary."""
from copy import deepcopy
import json

import pytest

from test_dual_sleeve_risk import synthetic_input, review
from value_investment_agent.application.product import dual_sleeve_public_summary as module
from value_investment_agent.application.product.common import sha256_file


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    from value_investment_agent import private_portfolio_intake
    # Repository-local synthetic test storage only; production check is unchanged.
    monkeypatch.setattr(private_portfolio_intake, '_containing_git_root', lambda path: None)
    root = tmp_path/'repository'
    root.mkdir()
    private = tmp_path/'private'
    private.mkdir()
    # Only the IO seam is stubbed; these are never actual portfolio declarations.
    report = review(synthetic_input())
    report.update(namespace='ACTUAL', sensitivity='PRIVATE_USER_CONFIRMED')
    source = private/'input.json'
    source.write_text('{"synthetic_test_only":true}', encoding='utf-8')
    config = dict(schema_version='dual-sleeve-local-release-v1', action='no_order',
        private_root=str(private), input_path=str(source), input_sha256=sha256_file(source),
        approved_summary_sha256=None)
    path = private/'release.json'
    def save():
        path.write_text(json.dumps(config), encoding='utf-8')
        return sha256_file(path)
    def validate(**kwargs):
        if sha256_file(kwargs['input_path']) != kwargs['input_sha256']:
            raise ValueError('input hash mismatch')
        return deepcopy(report)
    monkeypatch.setattr(module, 'run_dual_sleeve_review', validate)
    return root, private, report, source, config, path, save


def test_preview_no_consent_no_write_and_exact_release(isolated):
    root, private, report, source, config, path, save = isolated
    pin = save()
    summary, approved = module.prepare_private_risk_summary(root=root, config_path=path, config_sha256=pin)
    assert approved is None and not (root/'runtime').exists()
    output = root/'runtime/summary.json'
    with pytest.raises(ValueError, match='consent'):
        module.export_private_risk_summary(root=root, config_path=path, config_sha256=pin, output_path=output)
    assert not output.exists()
    config['approved_summary_sha256'] = module.public_summary_sha256(summary)
    result = module.export_private_risk_summary(root=root, config_path=path, config_sha256=save(), output_path=output)
    assert result == summary
    raw = output.read_text(encoding='utf-8')
    for forbidden in ('600519', 'holdings', 'risk_input_semantics', 'input_binding', str(private),
            'existing_risk_assessment', 'duplicated_security_exposure', 'research_version_sha256'):
        assert forbidden not in raw
    assert result['aggregate']['total_assets_cny'] == '10000'
    assert result['trade_eligible'] is False and result['hotspot_quantity_review'] is None
    with pytest.raises(FileExistsError):
        module.export_private_risk_summary(root=root, config_path=path, config_sha256=sha256_file(path), output_path=output)


@pytest.mark.parametrize('change', ['config', 'source', 'summary', 'scope', 'repository'])
def test_tamper_or_unsafe_config_cannot_export(isolated, change):
    root, private, report, source, config, path, save = isolated
    config['approved_summary_sha256'] = module.public_summary_sha256(module.project_public_risk_summary(report))
    pin = save()
    if change == 'config': path.write_text('{}', encoding='utf-8')
    if change == 'source': source.write_text('{}', encoding='utf-8')
    if change == 'summary': report['aggregate']['cash_cny'] = '123'
    if change == 'scope':
        config['action'] = 'order'
        pin = save()
    if change == 'repository':
        path = root/'release.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        pin = sha256_file(path)
    with pytest.raises(ValueError):
        module.export_private_risk_summary(root=root, config_path=path, config_sha256=pin,
            output_path=root/'runtime/summary.json')
    assert not (root/'runtime').exists()


@pytest.mark.parametrize('field,value', [('namespace', 'SIMULATED'),
    ('status', 'NOT_CONNECTED'), ('status', 'BLOCKED_PRIVATE_INPUT'), ('trade_eligible', True)])
def test_no_simulated_or_incomplete_release(isolated, field, value):
    report = isolated[2]
    report[field] = value
    with pytest.raises(ValueError): module.project_public_risk_summary(report)


def test_free_text_and_unknown_fields_never_projected(isolated):
    report = isolated[2]
    report['status'] = 'REVIEW_REQUIRED'
    report['blockers'] = ['private-account-name:600519']
    report['unexpected'] = 'SECRET'
    summary = module.project_public_risk_summary(report)
    assert summary['blockers'] == ['private_risk_review_required']
    assert 'SECRET' not in json.dumps(summary) and '600519' not in json.dumps(summary)


def test_actual_validator_still_requires_input_pin(tmp_path, monkeypatch):
    from value_investment_agent import private_portfolio_intake
    monkeypatch.setattr(private_portfolio_intake, '_containing_git_root', lambda path: None)
    from value_investment_agent.application.product.dual_sleeve_risk import run_dual_sleeve_review
    root, private = tmp_path/'repo', tmp_path/'private'
    root.mkdir()
    private.mkdir()
    source = private/'input.json'
    source.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        run_dual_sleeve_review(root=root, private_root=private, input_path=source)

"""Explicit local release of an allowlisted aggregate; private details never exported."""
from hashlib import sha256
import json
from pathlib import Path

from .common import sha256_file, require_inside, write_new_json
from .dual_sleeve_risk import _storage_path, _strict_json, run_dual_sleeve_review

SLEEVE_FIELDS = ('budget_cny', 'equity_cny', 'used_funds_cny', 'cash_cny',
    'available_funds_cny', 'risk_budget_cny', 'committed_risk_cny', 'available_risk_cny')


def project_public_risk_summary(report):
    if (report.get('namespace') != 'ACTUAL'
            or report.get('sensitivity') != 'PRIVATE_USER_CONFIRMED'
            or report.get('status') not in ('RISK_REVIEW_CALCULATED', 'REVIEW_REQUIRED')
            or report.get('action') != 'no_order' or report.get('trade_eligible') is not False):
        raise ValueError('only validated actual risk can be released')
    return dict(schema_version='dual-sleeve-risk-review-v1', action='no_order',
        namespace='ACTUAL', status=report['status'], sensitivity='USER_AUTHORIZED_AGGREGATE',
        release_scope='AGGREGATE_ONLY_NO_HOLDINGS_OR_SIZING',
        aggregate={key: report['aggregate'][key] for key in
            ('total_assets_cny', 'cash_cny', 'reserve_cny')},
        sleeves={name: {key: report['sleeves'][name][key] for key in SLEEVE_FIELDS}
            for name in ('CORE_VALUE', 'HOTSPOT_SATELLITE')},
        blockers=['private_risk_review_required'] if report['status'] == 'REVIEW_REQUIRED' else [],
        hotspot_quantity_review=None, position_guidance=None, expected_return=None,
        trade_eligible=False, acceptance_authority='NONE')


def public_summary_sha256(summary):
    return sha256(json.dumps(summary, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def prepare_private_risk_summary(*, root, config_path, config_sha256, generated_at=None):
    """Config and source stay private; absent consent returns a preview in memory only."""
    config_path = Path(config_path)
    if sha256_file(config_path) != config_sha256:
        raise ValueError('private release config hash mismatch')
    config = _strict_json(config_path)
    required = {'schema_version', 'action', 'private_root', 'input_path',
        'input_sha256', 'approved_summary_sha256'}
    if (set(config) != required or config['schema_version'] != 'dual-sleeve-local-release-v1'
            or config['action'] != 'no_order'):
        raise ValueError('private release config scope mismatch')
    private_root = Path(config['private_root'])
    _storage_path(root, config_path, namespace='ACTUAL', private_root=private_root, must_exist=True)
    report = run_dual_sleeve_review(root=root, input_path=Path(config['input_path']),
        input_sha256=config['input_sha256'], private_root=private_root, generated_at=generated_at)
    summary = project_public_risk_summary(report)
    if sha256_file(config_path) != config_sha256:
        raise ValueError('private release config changed during validation')
    return summary, config['approved_summary_sha256']


def export_private_risk_summary(*, root, config_path, config_sha256, output_path, generated_at=None):
    summary, approved = prepare_private_risk_summary(root=root, config_path=config_path,
        config_sha256=config_sha256, generated_at=generated_at)
    if approved != public_summary_sha256(summary):
        raise ValueError('aggregate risk summary lacks exact user release consent')
    output = require_inside(root/'runtime', root/output_path, 'authorized aggregate summary')
    write_new_json(output, summary)
    return summary

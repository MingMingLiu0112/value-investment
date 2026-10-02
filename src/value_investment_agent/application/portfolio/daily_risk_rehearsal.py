"""Run existing risk policy on explicit simulated inputs, never private accounts."""
from datetime import date, datetime
from pathlib import Path

from ..product.common import require_inside, load_json_object, sha256_file
from ...portfolio_contracts import portfolio_input_bundle_from_payload
from ...portfolio_risk import build_portfolio_risk_assessment, security_risk_attributes_from_payload


def evaluate_daily_risk_rehearsal(*, root: Path, path: Path, expected_sha256: str,
                                 now: datetime, assessment_id: str) -> dict:
    path = require_inside(root, path, 'simulated portfolio risk input')
    if sha256_file(path) != expected_sha256:
        raise ValueError('simulated portfolio input hash mismatch')
    payload = load_json_object(path, 'simulated portfolio risk input')
    if (payload.get('schema_version') != 'm4-portfolio-risk-demo-v1'
            or payload.get('assessment_namespace') != 'SIMULATED'
            or payload.get('snapshot', {}).get('namespace') != 'SIMULATED'
            or payload.get('action') != 'no_order'):
        raise ValueError('daily rehearsal accepts explicit SIMULATED risk demos only')
    bundle = portfolio_input_bundle_from_payload(payload)
    result = build_portfolio_risk_assessment(bundle=bundle,
        security_attributes={symbol: security_risk_attributes_from_payload(value)
            for symbol, value in payload['security_attributes'].items()},
        as_of=date.fromisoformat(payload['as_of']), generated_at=now,
        assessment_id=assessment_id, assessment_namespace='SIMULATED')
    if sha256_file(path) != expected_sha256:
        raise ValueError('simulated portfolio input changed during assessment')
    return dict(risk_assessment=result.as_policy(), input_sha256=expected_sha256,
        input_as_of=payload['as_of'], action='no_order', simulation_only=True,
        personal_capacity_confirmed=False, position_guidance=None)

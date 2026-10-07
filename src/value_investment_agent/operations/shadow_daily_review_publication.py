"""Re-render a source-bound isolated daily review without rerunning research."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..application.product.common import load_json_object, require_inside, sha256_file
from ..application.product.event_followup import read_event_followup
from ..presentation.read_models.shadow_daily_review import render_shadow_company_review
from .shadow_daily_input import audit_shadow_daily_input


def render_bound_daily_review(*, root: Path, manifest_path: Path,
                              manifest_sha256: str, now: datetime) -> str:
    root = root.resolve()
    manifest_path = require_inside(root, manifest_path, 'daily review manifest')
    audit = audit_shadow_daily_input(root=root, path=manifest_path,
        expected_sha256=manifest_sha256, now=now)
    manifest = load_json_object(manifest_path, 'daily review manifest')
    artifacts = {}
    for role in ('research', 'model', 'decision', 'product'):
        binding = manifest['bindings'].get(role)
        if not isinstance(binding, dict):
            raise ValueError(f'daily review requires {role} binding')
        path = require_inside(root, root / binding['path'], f'daily review {role}')
        if sha256_file(path) != binding['sha256']:
            raise ValueError(f'daily review {role} hash mismatch')
        artifacts[role] = load_json_object(path, f'daily review {role}')
    research, model, decision, product = (artifacts[role]
        for role in ('research', 'model', 'decision', 'product'))
    if any(item.get('action') != 'no_order' or item.get('orders') or item.get('broker_called')
           for item in artifacts.values()):
        raise ValueError('daily review cannot render orders or broker activity')
    run_id = research.get('run_id')
    day = audit['session_date']
    if (not run_id or any(item.get('run_id') != run_id or item.get('session_date') != day
                          for item in artifacts.values())
            or research.get('result', {}).get('symbol') not in manifest['symbols']):
        raise ValueError('daily review run/symbol binding mismatch')
    if (audit['input_consistency_status'] != 'PASS'
            and decision.get('suggested_state') != 'NOT_READY'):
        raise ValueError('incomplete daily input cannot render a positive decision state')
    explanation = product.get('source_anchored_explanation')
    if explanation is not None:
        if (not isinstance(explanation, dict) or explanation.get('symbol') != research['result']['symbol']
                or explanation.get('action') != 'no_order'):
            raise ValueError('daily review explanation scope mismatch')
        source = require_inside(root, root / explanation['path'], 'daily explanation')
        if sha256_file(source) != explanation['sha256']:
            raise ValueError('daily review explanation hash mismatch')
        # Rebuild the display from the original pages instead of trusting copied rows.
        verified = read_event_followup(
            root=root, path=source, expected_sha256=explanation['sha256'],
            cutoff=min(datetime.fromisoformat(day).date(),
                       now.astimezone(timezone(timedelta(hours=8))).date()),
        )
        if explanation != verified:
            raise ValueError('daily review explanation differs from verified originals')
    card = render_shadow_company_review(research=research, model=model,
        decision=decision, product=product, audit=audit)
    if sha256_file(manifest_path) != manifest_sha256:
        raise ValueError('daily review manifest changed during rendering')
    for role in artifacts:
        binding = manifest['bindings'][role]
        if sha256_file(root / binding['path']) != binding['sha256']:
            raise ValueError(f'daily review {role} changed during rendering')
    return card + f'\n输入清单 SHA-256：{manifest_sha256}\n'

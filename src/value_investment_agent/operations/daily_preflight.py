"""Join explicit daily content consumption to the existing read-only preflight."""
from datetime import datetime, timezone
from pathlib import Path

from ..m6_operational_readiness import build_preflight_receipt as build_existing_preflight
from .shadow_daily_input import consume_shadow_daily_input


def build_preflight_receipt(root: Path, config: Path, *,
                            daily_input: Path | None = None,
                            daily_input_sha256: str | None = None,
                            daily_operational_inputs: Path | None = None,
                            daily_operational_inputs_sha256: str | None = None,
                            **kwargs) -> dict:
    if bool(daily_input) != bool(daily_input_sha256):
        raise ValueError('daily preflight input requires paired path/hash')
    if bool(daily_operational_inputs) != bool(daily_operational_inputs_sha256):
        raise ValueError('daily operational inputs require paired path/hash')
    if daily_operational_inputs is not None and daily_input is None:
        raise ValueError('daily operational inputs require a daily manifest')
    consumed = None
    if daily_input is not None:
        consumed = consume_shadow_daily_input(root=root, path=daily_input,
            expected_sha256=daily_input_sha256, now=datetime.now(timezone.utc),
            operational_inputs=daily_operational_inputs,
            operational_inputs_sha256=daily_operational_inputs_sha256)
    receipt = build_existing_preflight(root, config, **kwargs)
    if receipt.get('action') != 'no_order':
        raise ValueError('preflight must retain no_order')
    if consumed is not None:
        # Neither gate grants the other one's admission or production authorization.
        receipt['daily_input_consumption'] = consumed
        receipt['daily_input_manifest_sha256'] = daily_input_sha256
        receipt['daily_input_required'] = True
        if consumed['daily_consumer_status'] != 'ADMITTED':
            receipt['summary']['blockers'] = list(dict.fromkeys([
                *receipt['summary']['blockers'], *consumed['blockers']]))
    return receipt

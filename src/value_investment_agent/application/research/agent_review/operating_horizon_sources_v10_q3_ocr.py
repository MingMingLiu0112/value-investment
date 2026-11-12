"""Fixed-source Q3 OCR supplement and pinned v10 manifest over sealed FY/H1 v1.

Initial versioned creation publishes a new manifest; bound replay is read-only.
Neither path changes an older task or treats 9M as parent cash or policy.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import os
import re

from . import operating_horizon_sources_v1 as v1
from .task_execution_v1 import _bytes, _hash
from .. import quarter_financial_ocr_v1 as q3_verifier
from .. import quarter_financial_read_model_v1 as q3_read_model
from ...product.common import require_inside

VERSION = 'operating-horizon-sources-v10-q3-ocr'
SCOPE = q3_verifier.SUPPORTED_SCOPE
_SCOPE_MATCH = re.fullmatch(r'FIXED_SOURCE_(\d{6})_Q3_\d{4}', SCOPE)
if _SCOPE_MATCH is None:
    raise ValueError('D2_Q3_FIXED_SOURCE_CONTRACT_INVALID')
SUPPORTED_SYMBOL = _SCOPE_MATCH[1]
FIELDS = (('revenue', 'revenue_ytd_cny', '营业收入'),
          ('parent_profit', 'attributable_profit_ytd_cny', '归属于上市公司股东的净利润'))
MAX_CONTEXT_CHARS = 76000


def implementation():
    return {**v1.implementation(),
            q3_verifier.__name__: _hash(Path(q3_verifier.__file__).read_bytes()),
            q3_read_model.__name__: _hash(Path(q3_read_model.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


def build_q3_ocr_source_context(*, root, symbol, now, base_binding):
    """Replay a sealed v1 base and append exactly two 9M observation rows."""
    root = Path(root).resolve()
    if symbol != SUPPORTED_SYMBOL or not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('D2_Q3_FIXED_SOURCE_IDENTITY_OR_CLOCK_INVALID')
    manifest = v1._bound(root, base_binding)
    if manifest.get('schema_version') != v1.VERSION or manifest.get('symbol') != symbol:
        raise ValueError('D2_Q3_BASE_MANIFEST_INVALID')
    base_as_of = datetime.fromisoformat(manifest['as_of'])
    if base_as_of.utcoffset() is None or base_as_of > now:
        raise ValueError('D2_Q3_BASE_AFTER_CUTOFF')
    base = v1.build_operating_horizon_source_context(
        root=root, symbol=symbol, now=base_as_of, binding=base_binding)
    if (base.get('financial_basis') != '2026-06-30' or
            base.get('source_binding') != base_binding or
            base.get('action') != 'no_order' or
            base.get('formal_eligibility') is not False):
        raise ValueError('D2_Q3_BASE_BOUNDARY_INVALID')
    registry_path = require_inside(root, root / q3_read_model.REGISTRY, 'D2 Q3 selection')
    registry_raw = registry_path.read_bytes()
    quarter = q3_read_model.read_quarter_financial_ocr(root, symbol, now)
    if registry_path.read_bytes() != registry_raw:
        raise ValueError('D2_Q3_SELECTION_CHANGED_DURING_READ')
    observation = quarter.get('ytd_9m_observation')
    if (quarter.get('status') != 'VERIFIED_OBSERVATION_ONLY' or
            quarter.get('supported_scope') != SCOPE or
            not isinstance(observation, dict) or
            observation.get('supported_scope') != SCOPE or
            observation.get('period_basis') != 'YTD_9M' or
            observation.get('valuation_admitted') is not False or
            observation.get('formal_eligibility') is not False):
        raise ValueError('D2_Q3_OCR_OBSERVATION_NOT_VERIFIED')
    bindings = deepcopy(quarter['source_bindings'])
    bindings['ocr_registry'] = dict(path=q3_read_model.REGISTRY, sha256=_hash(registry_raw))
    source_url = bindings['original']['source_url']
    source_match = re.fullmatch(r'https://static\.cninfo\.com\.cn/finalpage/\d{4}-\d{2}-\d{2}/(\d+)\.PDF', source_url)
    if source_match is None:
        raise ValueError('D2_Q3_OFFICIAL_SOURCE_ID_INVALID')
    source_id = 'cninfo:' + source_match[1]
    receipt_ref = bindings['receipt']
    receipt_path = require_inside(root, root / receipt_ref['path'], 'D2 Q3 receipt')
    raw = receipt_path.read_bytes()
    if _hash(raw) != receipt_ref['sha256']:
        raise ValueError('D2_Q3_RECEIPT_CHANGED')
    receipt = json.loads(raw)
    generated = []
    for entry in receipt['files']:
        ocr_path = require_inside(root, receipt_path.parent / entry['ocr'], 'D2 Q3 OCR')
        ocr_raw = ocr_path.read_bytes()
        if _hash(ocr_raw) != entry['ocr_sha256']:
            raise ValueError('D2_Q3_OCR_CHANGED')
        stamp = datetime.fromisoformat(json.loads(ocr_raw)['generated_at'])
        if stamp.utcoffset() is None:
            raise ValueError('D2_Q3_OCR_CLOCK_INVALID')
        generated.append(stamp)
    available = max(datetime.fromisoformat(bindings['original']['available_at']), *generated)
    if available > now:
        raise ValueError('D2_Q3_OBSERVATION_AFTER_CUTOFF')
    facts = observation.get('facts', {})
    if set(facts) != {item[1] for item in FIELDS}:
        raise ValueError('D2_Q3_EXACT_TWO_FIELDS_REQUIRED')
    result = deepcopy(base)
    rows = []
    for field, key, label in FIELDS:
        value = facts[key]
        text = f'{label} | 年初至报告期末 | {value} 元'
        rows.append(dict(id=f'{source_id}:q3-ocr:{field}',
                         source_id=source_id,
                         pdf_sha256=bindings['original']['sha256'],
                         available_at=available.isoformat(), period='2026-09-30',
                         period_basis='YTD_9M', scope='ISSUER_CONSOLIDATED',
                         unit='CNY', field=field, value=value, text=text,
                         text_sha256=_hash(text.encode('utf-8')), physical_page=1,
                         text_composition='OCR_ROW_TOKENS_NOT_CONTIGUOUS_QUOTE',
                         kind='VERIFIED_REPORTED_Q3_UNAUDITED_OBSERVATION_NOT_POLICY',
                         receipt_binding=deepcopy(receipt_ref),
                         registration_binding=deepcopy(bindings['registration'])))
    if len(result['evidence']) + 2 > 100 or {r['id'] for r in rows} & {r['id'] for r in result['evidence']}:
        raise ValueError('D2_Q3_EVIDENCE_LIMIT_OR_DUPLICATE')
    result['evidence'].extend(rows)
    result['supplemental_sources'].append(dict(
        source_id=source_id, path=bindings['original']['path'],
        sha256=bindings['original']['sha256'], source_url=bindings['original']['source_url'],
        available_at=available.isoformat(), period='2026-09-30',
        scope='CONSOLIDATED_YTD_9M_TWO_FIELDS_ONLY',
        receipt_binding=deepcopy(receipt_ref),
        registration_binding=deepcopy(bindings['registration'])))
    result['limitations'].append(
        'Q3 OCR revenue and attributable profit are not CFO, parent cash, payout policy, capacity, forecast, or valuation admission')
    result.update(schema_version=VERSION, as_of=now.isoformat(),
                  base_source_binding=deepcopy(base_binding),
                  q3_source_bindings=deepcopy(bindings),
                  supported_scope=SCOPE, implementation_sha256=implementation(),
                  formal_eligibility=False, valuation_admitted=False,
                  action='no_order')
    # No source_binding: the old task dispatcher has no v10 contract or replay route.
    result.pop('source_binding', None)
    result['snapshot_fingerprint'] = _hash(_bytes({k: v for k, v in result.items()
                                                   if k != 'snapshot_fingerprint'}))
    if len(_bytes(result).decode('utf-8')) > MAX_CONTEXT_CHARS:
        raise ValueError('D2_Q3_CONTEXT_OVER_BUDGET')
    return result


def build_operating_horizon_source_context(*, root, symbol, now, binding=None,
                                           base_binding=None):
    """Versioned manifest entry; replay requires an exact pinned v10 binding."""
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('D2_Q3_AWARE_CLOCK_REQUIRED')
    if binding is None:
        if base_binding is None:
            raise ValueError('D2_Q3_EXPLICIT_BASE_BINDING_REQUIRED')
        context = build_q3_ocr_source_context(
            root=root, symbol=symbol, now=now, base_binding=base_binding)
        manifest = dict(schema_version=VERSION, action='no_order', symbol=symbol,
                        as_of=now.isoformat(), base_binding=deepcopy(base_binding),
                        base_context_sha256=_hash(_bytes(context)),
                        q3_source_bindings=deepcopy(context['q3_source_bindings']),
                        implementation_sha256=implementation())
        raw = _bytes(manifest)
        path = require_inside(root / 'runtime', root / 'runtime' / VERSION /
                              (_hash(raw) + '.json'), 'D2 Q3 v10 manifest')
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            v1._bound(root, binding)
        else:
            # Exclusive create works on WPS filesystems that reject hard links.
            # A partial file can never replay because its content hash is pinned.
            with path.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
    else:
        if not isinstance(binding, dict) or not str(binding.get('path', '')).startswith(
                'runtime/' + VERSION + '/'):
            raise ValueError('D2_Q3_V10_BINDING_REQUIRED')
        manifest = v1._bound(root, binding)
        if (manifest.get('schema_version') != VERSION or manifest.get('action') != 'no_order'
                or manifest.get('symbol') != symbol or manifest.get('as_of') != now.isoformat()
                or manifest.get('implementation_sha256') != implementation()
                or (base_binding is not None and base_binding != manifest.get('base_binding'))):
            raise ValueError('D2_Q3_V10_MANIFEST_CHANGED')
        context = build_q3_ocr_source_context(
            root=root, symbol=symbol, now=now, base_binding=manifest['base_binding'])
        if (_hash(_bytes(context)) != manifest['base_context_sha256'] or
                context['q3_source_bindings'] != manifest['q3_source_bindings']):
            raise ValueError('D2_Q3_V10_SOURCE_CHANGED')
    context['source_binding'] = deepcopy(binding)
    context['snapshot_fingerprint'] = _hash(_bytes({k: v for k, v in context.items()
                                                   if k != 'snapshot_fingerprint'}))
    return context

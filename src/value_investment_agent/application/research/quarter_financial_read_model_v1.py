"""Read model for one fixed 600519 Q3 2026 source; no general update or admission."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath
import re

from .current_capital_observation_v1 import REGISTRY as CAPITAL_REGISTRY
from .quarter_financial_ocr_v1 import SUPPORTED_SCOPE, replay_quarter_financial_ocr

REGISTRY = 'config/quarter-financial-ocr-v1.json'
VERSION = 'quarter-financial-ocr-read-model-v1'


def _inside(root, name):
    if (not isinstance(name, str) or not name or Path(name).is_absolute() or
            PureWindowsPath(name).drive or '\\' in name or
            '..' in PureWindowsPath(name).parts):
        raise ValueError('INVALID_REGISTERED_PATH')
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError('INVALID_REGISTERED_PATH')
    return path


def _json(path):
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('REGISTRY_TOO_LARGE')
    return json.loads(path.read_bytes())


def read_quarter_financial_ocr(root, symbol, now):
    if not isinstance(symbol, str) or re.fullmatch(r'\d{6}', symbol) is None:
        raise ValueError('INVALID_SYMBOL')
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    root = Path(root).resolve()
    result = dict(schema_version=VERSION, symbol=symbol, status='NOT_STARTED',
                  supported_scope=SUPPORTED_SCOPE,
                  action='no_order', formal_eligibility=False,
                  valuation_admitted=False, current_comparison_changed=False,
                  ytd_9m_observation=None)
    if symbol != '600519':
        result.update(status='NOT_SUPPORTED', reason='FIXED_SOURCE_SCOPE_ONLY')
        return result
    registry_path = _inside(root, REGISTRY)
    if not registry_path.is_file():
        return result
    try:
        registry = _json(registry_path)
        if (set(registry) != {'schema_version', 'action', 'cases'} or
                registry['schema_version'] != 'quarter-financial-ocr-registry-v1' or
                registry['action'] != 'no_order' or not isinstance(registry['cases'], dict)):
            raise ValueError('INVALID_OCR_REGISTRY')
        case = registry['cases'].get(symbol)
        if case is None:
            return result
        if set(case) != {'capital_source_sha256', 'receipt', 'registration'}:
            raise ValueError('INVALID_OCR_CASE')
        capital_path = _inside(root, CAPITAL_REGISTRY)
        capital = _json(capital_path)
        if capital.get('schema_version') != 'current-capital-observations-v1':
            raise ValueError('INVALID_CAPITAL_REGISTRY')
        sources = capital['cases'][symbol]['sources']
        matched = [source for source in sources if source.get('sha256') == case['capital_source_sha256']]
        if len(matched) != 1 or matched[0].get('kind') != 'q3' or matched[0].get('report_period') != '2026-09-30':
            raise ValueError('CAPITAL_SOURCE_NOT_REGISTERED')
        source = matched[0]
        receipt_ref, registration_ref = case['receipt'], case['registration']
        if (set(receipt_ref) != {'path', 'sha256'} or
                set(registration_ref) != {'path', 'sha256'} or
                not all(isinstance(ref['sha256'], str) and re.fullmatch('[0-9a-f]{64}', ref['sha256'])
                        for ref in (receipt_ref, registration_ref))):
            raise ValueError('INVALID_OCR_BINDING')
        original_path = _inside(root, source['path'])
        receipt_path = _inside(root, receipt_ref['path'])
        registration_path = _inside(root, registration_ref['path'])
        available = datetime.fromisoformat(source['available_at'])
        if available.utcoffset() is None:
            raise ValueError('REGISTERED_TIMEZONE_REQUIRED')
        result['source_bindings'] = dict(
            capital_registry={'path': CAPITAL_REGISTRY, 'sha256': sha256(capital_path.read_bytes()).hexdigest()},
            original={'path': source['path'], 'sha256': source['sha256'], 'source_url': source['source_url'],
                      'available_at': source['available_at']},
            receipt=receipt_ref, registration=registration_ref)
        observation = replay_quarter_financial_ocr(
            receipt_path=receipt_path, receipt_sha256=receipt_ref['sha256'],
            original_sha256=source['sha256'], original_path=original_path,
            registration_path=registration_path, registration_sha256=registration_ref['sha256'],
            registered_available_at=available, as_of=now)
        if (observation.get('symbol') != symbol or
                observation.get('supported_scope') != SUPPORTED_SCOPE or
                observation.get('valuation_admitted') is not False):
            raise ValueError('OBSERVATION_BOUNDARY_MISMATCH')
        result['status'] = 'VERIFIED_OBSERVATION_ONLY'
        result['ytd_9m_observation'] = observation
        return result
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        result.update(status='UNASSESSABLE', reason=str(error) if isinstance(error, ValueError)
                      else type(error).__name__, ytd_9m_observation=None)
        return result

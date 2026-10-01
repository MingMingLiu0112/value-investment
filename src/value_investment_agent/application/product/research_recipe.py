"""Resolve an immutable research input recipe; never author or publish Excel."""
from datetime import date
from pathlib import Path
import re
from .common import require_inside, sha256_file, load_json_object


def load_research_recipe(*, root: Path, path: Path, expected_sha256: str) -> dict:
    path = require_inside(root, path, 'research recipe')
    if sha256_file(path) != expected_sha256:
        raise ValueError('research recipe hash mismatch')
    value = load_json_object(path, 'research recipe')
    allowed = {'schema_version', 'action', 'scope', 'symbol', 'presentation_as_of', 'base',
               'workbench', 'expectations', 'metrics', 'cash_change_periods', 'event_scan',
               'recovered_event_originals', 'dividend_package', 'historical_closure',
               'historical_execution_replay', 'research_readiness'}
    if (set(value) - allowed or value.get('schema_version') != 'shared-research-recipe-v1'
            or value.get('action') != 'no_order' or value.get('scope') != 'READ_ONLY_RESEARCH_EXPLANATION'
            or not re.fullmatch(r'\d{6}', value.get('symbol', ''))):
        raise ValueError('unsupported research recipe scope or keys')
    date.fromisoformat(value['presentation_as_of'])
    bindings = [value['base'], value['workbench'], *value.get('metrics', [])]
    bindings.extend(value[key] for key in (
        'expectations', 'event_scan', 'dividend_package', 'historical_closure',
        'historical_execution_replay', 'research_readiness'
    ) if value.get(key))
    for binding in bindings:
        if set(binding) != {'path', 'sha256'} or not re.fullmatch(r'[a-f0-9]{64}', binding['sha256']):
            raise ValueError('recipe bindings require exact path/hash contracts')
        source = require_inside(root, root / binding['path'], 'recipe source')
        if sha256_file(source) != binding['sha256']:
            raise ValueError('recipe source hash mismatch')
    if len({item['path'] for item in value.get('metrics', [])}) != len(value.get('metrics', [])):
        raise ValueError('recipe metric transcriptions must be unique')
    recoveries = value.get('recovered_event_originals', [])
    if recoveries and not value.get('event_scan'):
        raise ValueError('recipe recovery requires event scan')
    if len({item['id'] for item in recoveries}) != len(recoveries):
        raise ValueError('duplicate recipe recovery reference')
    for item in recoveries:
        if set(item) != {'id', 'path'} or not item['id']:
            raise ValueError('recipe recovery requires explicit reference and path')
        require_inside(root, root / item['path'], 'recipe recovered original')
    if value.get('cash_change_periods') is not None and (
            len(value['cash_change_periods']) != 2 or not value.get('metrics')
            or value['cash_change_periods'][0] == value['cash_change_periods'][1]):
        raise ValueError('recipe cash bridge requires distinct periods and metrics')
    workbench = load_json_object(root / value['workbench']['path'], 'recipe workbench')
    if workbench.get('symbol') != value['symbol']:
        raise ValueError('recipe workbench symbol mismatch')
    if value.get('historical_closure'):
        closure = load_json_object(
            root / value['historical_closure']['path'], 'recipe historical closure'
        )
        if closure.get('symbol') != value['symbol']:
            raise ValueError('recipe historical closure symbol mismatch')
    if value.get('historical_execution_replay'):
        replay = load_json_object(
            root / value['historical_execution_replay']['path'],
            'recipe historical execution replay',
        )
        if replay.get('symbol') != value['symbol']:
            raise ValueError('recipe historical execution replay symbol mismatch')
    if value.get('research_readiness'):
        from .workbench import load_stopped_workbench_for_presentation
        binding = value['research_readiness']
        readiness = load_stopped_workbench_for_presentation(
            root=root, path=root / binding['path'], expected_sha256=binding['sha256'])
        if readiness['result']['symbol'] != value['symbol']:
            raise ValueError('recipe research readiness symbol mismatch')
    if sha256_file(path) != expected_sha256:
        raise ValueError('research recipe changed during read')
    return value

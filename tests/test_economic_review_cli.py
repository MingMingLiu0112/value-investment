"""Economic review audits sources without creating approval records."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


def command(root, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'scripts/current/review_research.py'
    spec = importlib.util.spec_from_file_location('economic_review_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', root)
    return module


def test_audit_records_nonadmission_without_signatures(tmp_path, monkeypatch):
    from value_investment_agent.application.research import economic_review_bundle as bundle
    monkeypatch.setattr(bundle, 'build_current_economic_review_bundle', lambda **kw:
        dict(symbol=kw['symbol'], action='no_order', primary_valuation_usable=False))
    module = command(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, 'argv', ['review_research.py', '--symbol', '600519',
        '--verify-economics', '--output', 'runtime/review.json'])
    assert module.main() == 2
    assert json.loads((tmp_path / 'runtime/review.json').read_bytes())['primary_valuation_usable'] is False
    assert not list(tmp_path.rglob('*signature*'))
    with pytest.raises(FileExistsError):
        module.main()


def test_audit_excludes_approval_and_external_output(tmp_path, monkeypatch):
    module = command(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, 'argv', ['review_research.py', '--symbol', '600519',
        '--verify-economics', '--output', 'runtime/review.json', '--signed-review-response', 'signed.json'])
    with pytest.raises(SystemExit):
        module.main()
    monkeypatch.setattr(sys, 'argv', ['review_research.py', '--symbol', '600519',
        '--verify-economics', '--output', '../outside.json'])
    with pytest.raises(ValueError, match='project root'):
        module.main()

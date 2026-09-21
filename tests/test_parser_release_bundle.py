import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'parser_bundle', Path(__file__).parents[1] / 'scripts/build_parser_release_bundle.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_only_reviewed_function_and_helper_are_changed():
    production = "PREFIX = 'production'\ndef store_filing_candidates(row):\n    return row['excerpt'][:1000]\n\ndef untouched():\n    return 7\n"
    local = "PREFIX = 'unpublished'\ndef candidate_evidence_excerpt(row):\n    return row['excerpt']\n\ndef store_filing_candidates(row):\n    return candidate_evidence_excerpt(row)\n"
    result = module.build_db(production, local)
    assert "PREFIX = 'production'" in result
    assert 'return 7' in result
    assert 'unpublished' not in result
    assert 'def candidate_evidence_excerpt' in result


def test_unrelated_store_behavior_is_rejected():
    production = "def store_filing_candidates(row):\n    return row['excerpt'][:1000]\n"
    local = "def store_filing_candidates(row):\n    return None\n"
    with pytest.raises(ValueError, match='Unexpected'):
        module.build_db(production, local)

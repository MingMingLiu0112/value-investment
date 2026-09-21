import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('archived_maturity_audit', SCRIPTS / 'audit_archived_current_maturities.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def source():
    return {'symbol': '001386', 'sha256': 'a' * 64, 'archive_hash_matched': True,
            'audit': {'path': 'fixture.pdf'}}


def test_identical_archive_is_only_selected_once():
    manifest = {'reports': [source()]}
    assert len(module.select([manifest, manifest])) == 1


def test_different_version_is_not_silently_chosen():
    with pytest.raises(ValueError, match='Ambiguous'):
        module.select([{'reports': [source(), {**source(), 'sha256': 'b' * 64}]}])


def test_missing_archive_verification_rejects():
    with pytest.raises(ValueError, match='Unverified'):
        module.select([{'reports': [{**source(), 'archive_hash_matched': False}]}])


def test_empty_and_oversized_batch_rejects():
    for rows in ([], [{**source(), 'symbol': str(i)} for i in range(51)]):
        with pytest.raises(ValueError, match='1-50'):
            module.select([{'reports': rows}])

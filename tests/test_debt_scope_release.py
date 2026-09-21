import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('debt_scope_release', SCRIPTS / 'install_debt_scope_gate.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_patch_is_exactly_the_explicit_scope_change(monkeypatch):
    original = (b'def gate(point, metadata):\n'
                b"    if (point.get('field_name') == 'interest_bearing_debt'\n"
                + module.OLD + b'\n        return False\n    return True\n')
    monkeypatch.setattr(module, 'OLD_HASH', hashlib.sha256(original).hexdigest())
    updated = module.patched_bytes(original)
    assert updated.replace(module.NEW, module.OLD) == original
    namespace = {}
    exec(compile(updated, 'fixture', 'exec'), namespace)
    assert not namespace['gate']({'field_name': 'interest_bearing_debt'}, {})
    assert namespace['gate']({'field_name': 'interest_bearing_debt'}, {'complete_debt_verified': True})
    with pytest.raises(ValueError, match='changed'):
        module.patched_bytes(updated)


def test_unrecognized_hash_never_patches():
    with pytest.raises(ValueError, match='changed'):
        module.patched_bytes(b'changed baseline')


def test_installer_uses_existing_image_bounded_resources_and_no_network():
    source = (SCRIPTS / 'install_debt_scope_gate.py').read_text(encoding='utf-8')
    for constraint in ("'--pull=never'", "'--network', 'none'", "'--memory=384m'",
                       "'--memory-swap=512m'", 'fcntl.LOCK_EX | fcntl.LOCK_NB',
                       'replace_bytes(target, original, mode)', 'pta_pid() != before_pid'):
        assert constraint in source

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('installer', Path(__file__).parents[1] / 'scripts/install_parser_release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(tmp_path):
    bundle, target, backup = [tmp_path / name for name in ('bundle', 'target', 'backup')]
    bundle.mkdir()
    target.mkdir()
    files = []
    for name in sorted(module.NAMES):
        if name != 'combined_balance.py':
            (target / name).write_text('OLD = True\n')
        (bundle / name).write_text('NEW = True\n')
        files.append(dict(name=name, before_sha256=module.digest(target / name), after_sha256=module.digest(bundle / name)))
    (bundle / 'manifest.json').write_text(json.dumps(dict(files=files)))
    return bundle, target, backup


def test_installs_and_preserves_backup(tmp_path):
    bundle, target, backup = fixture(tmp_path)
    result = module.install(bundle, target, backup, lambda: None)
    assert result['installed_replay_passed']
    assert (target / 'combined_balance.py').exists()
    assert (backup / 'db.py').read_text() == 'OLD = True\n'


def test_failed_probe_restores_old_files_and_removes_new_module(tmp_path):
    bundle, target, backup = fixture(tmp_path)
    def fail():
        raise RuntimeError('probe failed')
    with pytest.raises(RuntimeError, match='probe failed'):
        module.install(bundle, target, backup, fail)
    assert not (target / 'combined_balance.py').exists()
    assert all((target / name).read_text() == 'OLD = True\n' for name in module.NAMES - {'combined_balance.py'})


def test_changed_production_aborts_without_backup_or_writes(tmp_path):
    bundle, target, backup = fixture(tmp_path)
    (target / 'db.py').write_text('USER_CHANGE = True\n')
    with pytest.raises(ValueError, match='Production changed'):
        module.install(bundle, target, backup, lambda: None)
    assert not backup.exists()
    assert (target / 'db.py').read_text() == 'USER_CHANGE = True\n'

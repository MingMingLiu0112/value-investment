import pytest

from scripts import m6_operational_control as cli


def test_arbitrary_authorization_id_cannot_advance_local_m6_state(tmp_path):
    state_path = tmp_path / 'm6-state.json'
    missing_bundle = tmp_path / 'missing-bundle.json'
    missing_root = tmp_path / 'missing-root.json'
    with pytest.raises(FileNotFoundError):
        cli.main([
            '--state', str(state_path), 'advance', '--target', 'STAGING',
            '--authorization-bundle', str(missing_bundle),
            '--authorization-trust-root', str(missing_root), '--reason', 'test',
            '--operator', 'local-user',
        ])
    assert not state_path.exists()

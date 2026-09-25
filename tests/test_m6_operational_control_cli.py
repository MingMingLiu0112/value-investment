import pytest

from scripts import m6_operational_control as cli


def test_arbitrary_authorization_id_cannot_advance_local_m6_state(tmp_path):
    state_path = tmp_path / 'm6-state.json'
    with pytest.raises(RuntimeError, match='not a verified user authorization receipt'):
        cli.main([
            '--state', str(state_path), 'advance', '--target', 'STAGING',
            '--authorization-id', 'self-declared', '--reason', 'test',
            '--operator', 'local-user',
        ])
    assert not state_path.exists()

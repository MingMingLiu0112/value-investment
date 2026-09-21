import pytest

from value_investment_agent.backup import validate_restore_target, verify_restore


SOURCE = 'postgresql://user@127.0.0.1:5432/value_agent'
TARGET = 'postgresql://user@127.0.0.1:5433/value_agent_restore'


def test_explicit_local_drill_target_allowed():
    validate_restore_target(SOURCE, TARGET)
    validate_restore_target(SOURCE, 'host=127.0.0.1 port=5433 dbname=value_agent_restore user=user')


@pytest.mark.parametrize('target', [SOURCE,
    'postgresql://other@localhost:5432/value_agent',
    'postgresql://127.0.0.1:5432/value_agent_restore',
    'postgresql:///value_agent_restore',
    TARGET + '?hostaddr=10.0.0.1', TARGET + '?service=production',
    TARGET + '?options=-csearch_path=public', 'not a connection string'])
def test_unsafe_target_refused_before_reading_backup(tmp_path, target):
    with pytest.raises(RuntimeError):
        verify_restore(SOURCE, target, tmp_path / 'nonexistent.json')


def test_source_must_have_distinct_explicit_database():
    with pytest.raises(RuntimeError):
        validate_restore_target('postgresql://127.0.0.1:5432/value_agent_restore', TARGET)
    with pytest.raises(RuntimeError):
        validate_restore_target('postgresql://127.0.0.1', TARGET)

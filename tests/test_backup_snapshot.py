import pytest

from value_investment_agent.backup_snapshot import compare_checks


def test_matching_snapshot_does_not_require_live_source():
    checks = {'data_points': {'rows': 42, 'sha256': 'a' * 64}}
    compare_checks(checks, checks.copy())


@pytest.mark.parametrize('actual', [{},
    {'data_points': {'rows': 42, 'sha256': 'b' * 64}},
    {'data_points': {'rows': 43, 'sha256': 'a' * 64}},
    {'other_table': {'rows': 42, 'sha256': 'a' * 64}}])
def test_missing_tables_counts_and_same_count_corruption_fail(actual):
    with pytest.raises(RuntimeError):
        compare_checks({'data_points': {'rows': 42, 'sha256': 'a' * 64}}, actual)

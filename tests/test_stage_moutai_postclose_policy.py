from pathlib import Path


def test_postclose_policy_staging_is_explicitly_nonactivating():
    script = (Path(__file__).parents[1] / "scripts" / "stage_moutai_postclose_policy.py").read_text(encoding="utf-8")
    assert 'policy["staged_only"] = True' in script
    assert 'policy["event_coverage_date"] = receipt["through"]' in script
    assert 'new_or_changed_announcements") != 0' in script

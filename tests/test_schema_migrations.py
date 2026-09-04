from pathlib import Path


def test_candidate_status_migration_converts_rows_before_new_constraint() -> None:
    schema = (Path(__file__).parents[1] / 'sql' / '001_init.sql').read_text(encoding='utf-8')

    drop_at = schema.index('ALTER TABLE filing_candidates DROP CONSTRAINT')
    update_at = schema.index("UPDATE filing_candidates SET status = 'candidate_pending_automated_verification'")
    add_at = schema.index('ALTER TABLE filing_candidates ADD CONSTRAINT filing_candidates_status_check')

    assert drop_at < update_at < add_at

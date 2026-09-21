import pytest

from value_investment_agent.db import claim_disclosures_for_extraction, finish_disclosure_extraction, mark_disclosures_cold_archived
from value_investment_agent.filing_extract import ANNUAL_BACKFILL_PARSER_VERSION


class _Result:
    def fetchall(self) -> list[dict]:
        return []


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[tuple] = []
        self.commits = 0

    def execute(self, statement: str, params: tuple = ()) -> _Result:
        self.statements.append(statement)
        self.params.append(params)
        return _Result()

    def commit(self) -> None:
        self.commits += 1


def test_claim_reclaims_only_stale_claims_and_refreshes_claim_time() -> None:
    connection = _Connection()

    assert claim_disclosures_for_extraction(connection, 10) == []

    statement = connection.statements[0]
    assert "WHERE archive_status = 'server_resident'" in statement
    assert "AND review_status <> 'rejected' AND (extraction_status = 'pending'" in statement
    assert "OR (extraction_status = 'failed' AND extraction_attempts < 5))" in statement
    assert "extraction_claimed_at < now() - interval '3 hours'" in statement
    assert "extraction_status = 'failed' AND extraction_attempts < 5" in statement
    assert "extraction_parser_version IS DISTINCT FROM %s" in statement
    assert "CASE extraction_status WHEN 'failed' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END" in statement
    assert "m.symbol=official_disclosures.symbol" in statement
    assert "m.screen_date=(SELECT max(screen_date) FROM market_screen_results)" in statement
    assert "THEN CASE WHEN report_kind='annual' THEN 0 ELSE 1 END ELSE 2 END" in statement
    assert statement.index('report_period DESC') < statement.index('CASE extraction_status')
    assert 'FOR UPDATE SKIP LOCKED LIMIT %s' in statement
    assert 'fetched_at < now()' not in statement
    assert "extraction_claimed_at = now()" in statement
    assert "extraction_attempts = o.extraction_attempts + 1" in statement
    assert connection.params == [(ANNUAL_BACKFILL_PARSER_VERSION, 10)]
    assert connection.commits == 1


def test_finish_clears_claim_time_after_success_or_failure() -> None:
    connection = _Connection()

    finish_disclosure_extraction(connection, 'disclosure-id', candidates=2)

    assert 'extraction_claimed_at = NULL' in connection.statements[0]
    assert connection.params == [('extracted', None, ANNUAL_BACKFILL_PARSER_VERSION, 'disclosure-id')]
    assert connection.commits == 1


def test_candidate_write_records_current_parser_version():
    from value_investment_agent.db import store_filing_candidates

    class Connection:
        def cursor(self):
            return self

        def executemany(self, statement, rows):
            self.statement = statement
            self.rows = rows

    connection = Connection()
    row = dict(field_name='cash', value='100', unit='CNY', page=2,
               source_label='cash', excerpt='evidence', status='candidate_pending_automated_verification')
    assert store_filing_candidates(connection, 'disclosure-id', [row]) == 1
    assert connection.rows[0][8] == ANNUAL_BACKFILL_PARSER_VERSION
    assert 'filing-extract-v3' not in connection.statement


def test_cold_archive_requires_verified_complete_server_records() -> None:
    class Connection(_Connection):
        def execute(self, statement: str, params: tuple = ()) -> _Result:
            self.statements.append(statement)
            self.params.append(params)
            return type('Result', (), {'fetchall': lambda self: [{'disclosure_id': '00000000-0000-0000-0000-000000000001'}]})()

    connection = Connection()
    digest = 'a' * 64

    assert mark_disclosures_cold_archived(
        connection, manifest_sha256=digest, archive_uri='local-cold://20260918',
        disclosure_ids=['00000000-0000-0000-0000-000000000001'],
    ) == 1

    statement = connection.statements[0]
    assert "archive_status = 'cold_archived'" in statement
    assert "archive_status = 'server_resident'" in statement
    assert "extraction_status IN ('extracted', 'no_candidates')" in statement
    assert connection.params[0] == ('local-cold://20260918', digest, ['00000000-0000-0000-0000-000000000001'])


def test_cold_archive_rejects_invalid_manifest_digest() -> None:
    with pytest.raises(ValueError, match='SHA-256'):
        mark_disclosures_cold_archived(_Connection(), manifest_sha256='not-a-digest',
                                       archive_uri='local-cold://20260918', disclosure_ids=['x'])


def test_manual_candidate_review_requires_restore_for_cold_archives() -> None:
    from value_investment_agent.candidate_review import _candidate

    class Connection:
        def execute(self, statement, params):
            return type('Result', (), {'fetchone': lambda self: {
                'archive_status': 'cold_archived', 'archive_uri': 'local-cold://server-copy-20260918',
            }})()

    with pytest.raises(ValueError, match='requires cold archive restore'):
        _candidate(Connection(), 'candidate-id')

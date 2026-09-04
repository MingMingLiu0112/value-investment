from value_investment_agent.db import claim_disclosures_for_extraction, finish_disclosure_extraction


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
    assert "extraction_claimed_at < now() - interval '3 hours'" in statement
    assert 'fetched_at < now()' not in statement
    assert "extraction_claimed_at = now()" in statement
    assert connection.params == [(10,)]
    assert connection.commits == 1


def test_finish_clears_claim_time_after_success_or_failure() -> None:
    connection = _Connection()

    finish_disclosure_extraction(connection, 'disclosure-id', candidates=2)

    assert 'extraction_claimed_at = NULL' in connection.statements[0]
    assert connection.params == [('extracted', 'disclosure-id')]
    assert connection.commits == 1

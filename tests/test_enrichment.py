from value_investment_agent.db import finish_financial_enrichment


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.commits = 0

    def execute(self, query: str, params: tuple) -> None:
        self.calls.append((query, params))

    def commit(self) -> None:
        self.commits += 1


def test_financial_enrichment_completion_casts_nullable_error_for_postgres() -> None:
    connection = FakeConnection()

    finish_financial_enrichment(connection, "600519")

    query, params = connection.calls[0]
    assert "%s::text IS NULL" in query
    assert params == (None, None, "600519")
    assert connection.commits == 1


def test_financial_enrichment_failure_keeps_error_for_retry() -> None:
    connection = FakeConnection()

    finish_financial_enrichment(connection, "600519", "network timeout")

    _, params = connection.calls[0]
    assert params == ("network timeout", "network timeout", "600519")

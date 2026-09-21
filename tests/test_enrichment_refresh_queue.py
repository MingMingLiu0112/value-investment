from value_investment_agent.db import claim_financial_enrichment_batch


class Connection:
    def execute(self, sql, params):
        self.sql, self.params = sql, params
        return self

    def fetchall(self):
        return [{'symbol': '000333'}]

    def commit(self):
        self.committed = True


def test_archived_candidates_reenter_bounded_oldest_first_queue():
    connection = Connection()
    assert claim_financial_enrichment_batch(connection, 40) == [{'symbol': '000333'}]
    sql = connection.sql
    assert "q.status = 'official_filings_archived'" in sql
    assert "q.updated_at < now() - interval '1 day'" in sql
    assert 'm.symbol = q.symbol' in sql
    assert 'SELECT max(screen_date) FROM market_screen_results' in sql
    assert 'ORDER BY q.updated_at, q.priority_score DESC, q.symbol' in sql
    assert 'FOR UPDATE SKIP LOCKED' in sql
    assert "q.status = 'processing' AND q.updated_at < now() - interval '3 hours'" in sql
    assert 'LIMIT %s' in sql
    assert connection.params == (40,)
    assert connection.committed

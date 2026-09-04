import json
from datetime import datetime, timezone

from value_investment_agent.db import store_market_screen
from value_investment_agent.market import MarketCandidate


class _Result:
    def __init__(self, row: dict | None = None) -> None:
        self.row = row or {'document_id': 'source-id'}

    def fetchone(self) -> dict:
        return self.row


class _Cursor:
    def executemany(self, statement: str, rows: list[tuple]) -> None:
        self.statement = statement
        self.rows = rows


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.cursor_instance = _Cursor()

    def execute(self, statement: str, params: tuple) -> _Result:
        self.calls.append((statement, params))
        return _Result()

    def cursor(self) -> _Cursor:
        return self.cursor_instance


def test_market_snapshot_persists_fallback_and_industry_audit_metadata() -> None:
    connection = _Connection()
    raw = json.dumps({
        'source': 'AkShare / Tencent all-A market snapshot',
        'fallback_reason': 'primary unavailable', 'industry_mapping_count': 0,
        'industry_mapping_error': None,
    }).encode()
    candidate = MarketCandidate('600001', '样例', '待行业映射', '主板', 10, 10, None, 10_000_000_000, 50)

    assert store_market_screen(connection, [candidate], raw, datetime.now(timezone.utc)) == 1

    metadata = json.loads(connection.calls[0][1][-1])
    assert metadata['snapshot_source'] == 'AkShare / Tencent all-A market snapshot'
    assert metadata['fallback_reason'] == 'primary unavailable'
    assert metadata['industry_mapping_count'] == 0

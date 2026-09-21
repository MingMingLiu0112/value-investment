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


def test_raw_document_conflict_refreshes_audit_metadata() -> None:
    connection = _Connection()
    from value_investment_agent.db import _store_document

    _store_document(
        connection, source_name='new source', source_url='https://example.test/new',
        published_at=None, fetched_at=datetime.now(timezone.utc), parser_version='v2',
        raw_payload=b'same payload', metadata={'fallback_reason': 'ConnectionError:'},
        local_path='/app/evidence/financial_snapshots/example.json',
    )

    statement = connection.calls[0][0]
    assert 'metadata = EXCLUDED.metadata' in statement
    assert 'source_name = EXCLUDED.source_name' in statement
    assert "local_path = COALESCE(NULLIF(EXCLUDED.local_path, ''), raw_documents.local_path)" in statement
    assert connection.calls[0][1][7] == '/app/evidence/financial_snapshots/example.json'


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
    assert metadata['industry_mapping_source'] is None
    assert metadata['valuation_cross_check'] is None


def test_accepted_cross_check_creates_auditable_verified_market_price() -> None:
    connection = _Connection()
    raw = json.dumps({
        'source': 'Tencent all-A market snapshot + Sina valuation cross-check',
        'rows':[{'symbol':'600001','price_cross_check':{'status':'matched','tencent_price':'10','sina_price':'10'}}],
        'valuation_cross_check': {
            'sina_status': 'accepted',
            'price_tolerance': 'max(CNY 0.03, 2% of Tencent price)',
        },
    }).encode()
    candidate = MarketCandidate('600001', '样例', '行业', '主板', 10, 10, 1, 10_000_000_000, 50)

    store_market_screen(connection, [candidate], raw, datetime.now(timezone.utc))

    assert "'current_price'" in connection.cursor_instance.statement
    point = connection.cursor_instance.rows[0]
    assert point[1] == '600001'
    metadata = json.loads(point[-1])
    assert metadata['automatic_cross_source_verification'] is True
    assert metadata['verification_method'] == 'tencent_all_market_price_plus_sina_snapshot'
    assert metadata['per_symbol_price_evidence']['sina_price']=='10'


def test_batch_success_without_symbol_proof_does_not_promote_a_price():
    connection=_Connection()
    candidate=MarketCandidate('600001','样例','机械','主板',10,10,1,10_000_000_000,50)
    raw=json.dumps({'valuation_cross_check':{'sina_status':'accepted'}}).encode()
    store_market_screen(connection,[candidate],raw,datetime.now(timezone.utc))
    assert connection.cursor_instance.rows==[]

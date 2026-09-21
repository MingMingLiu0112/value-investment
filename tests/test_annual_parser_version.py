from contextlib import nullcontext
from pathlib import Path
import runpy
import sys

from value_investment_agent import db, filing_extract


def test_selector_uses_current_parser_version_with_file_hash(monkeypatch):
    calls = []

    class Connection:
        def execute(self, sql, params=None):
            calls.append((sql, params))
            return self

        def fetchall(self):
            return []

    connection = Connection()
    monkeypatch.setattr(db, 'connect', lambda _: nullcontext(connection))
    monkeypatch.setattr(db, 'current_market_candidate_symbols', lambda _: ['000729'])
    monkeypatch.setitem(sys.modules, 'filing_extract', filing_extract)
    monkeypatch.setattr(sys, 'argv', ['select_annual_batch.py', '--limit', '5'])
    namespace = runpy.run_path(str(Path(__file__).parents[1] / 'scripts/select_annual_batch.py'))
    sql, params = calls[-1]
    assert params == (['000729'], filing_extract.ANNUAL_BACKFILL_PARSER_VERSION)
    assert "r.details->>'official_sha256'=o.sha256" in sql
    assert "r.details->>'parser_version'=%s" in sql
    select = namespace['balanced_reports']
    rows = [{'symbol': s} for s in ['000001', '000002', '000003', '300001', '688001', '920001']]
    first = select(rows, 4)
    assert len({namespace['board_for_symbol'](r['symbol']) for r in first}) == 4
    assert len(select(rows, 20)) == len(rows)
    assert select([], 20) == []
    assert select(rows, 0) == []
    assert select(list(reversed(rows)), 4) == first


def test_writer_and_audit_share_parser_version():
    root = Path(__file__).parents[1]
    for name in ['reextract_annual_samples.py', 'audit_annual_coverage.py']:
        source = (root / 'scripts' / name).read_text(encoding='utf-8')
        assert 'from filing_extract import ANNUAL_BACKFILL_PARSER_VERSION' in source
        assert 'filing-extract-v4-pdfium-units' not in source

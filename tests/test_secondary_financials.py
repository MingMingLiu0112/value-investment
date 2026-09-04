from pathlib import Path


def test_secondary_financial_collection_is_part_of_scheduled_filing_pipeline() -> None:
    script = (Path(__file__).parents[1] / 'deploy' / 'server' / 'run_collect_filings.source.sh').read_text(encoding='utf-8')

    assert 'collect-secondary-financials --limit 25' in script
    assert script.index('collect-secondary-financials --limit 25') < script.index('auto-verify-filings --limit 200')
    assert '--add-host="money.finance.sina.com.cn:116.133.8.236"' in script

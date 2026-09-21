import hashlib

from value_investment_agent import pdf_text
from value_investment_agent.filing_extract import ANNUAL_BACKFILL_PARSER_VERSION, extract_candidates


def test_production_entrypoint_uses_shared_decoder_and_retains_hash(tmp_path, monkeypatch):
    path = tmp_path / 'report.pdf'
    raw = b'%PDF fixture for decoder boundary'
    path.write_bytes(raw)
    calls = []

    def decode(value):
        calls.append(value)
        return ['\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u5143\n'
                '\u8d27\u5e01\u8d44\u91d1 \u4e94\uff08\u4e00\uff091 634,149,047.10 283,502,522.87']

    monkeypatch.setattr(pdf_text, 'extract_pages', decode)
    packet = extract_candidates(path)
    assert calls == [path]
    assert packet['sha256'] == hashlib.sha256(raw).hexdigest()
    assert packet['parser_version'] == ANNUAL_BACKFILL_PARSER_VERSION
    assert packet['page_count'] == 1
    assert packet['candidates'][0]['value'] == '634149047.10'

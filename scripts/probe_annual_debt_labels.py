"""Read-only original-page probe for three nonzero annual debt gaps."""
import hashlib
import json
from pathlib import Path
import re

from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.filing_extract import extract_candidates_from_pages


def main():
    symbols = ['600496', '000544', '601800']
    with connect(get_settings().database_url) as db:
        db.execute('SET TRANSACTION READ ONLY')
        db.execute("SET LOCAL statement_timeout='20s'")
        reports = db.execute('''SELECT symbol, report_period, source_url, sha256, local_path
            FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
            AND report_period='2025-12-31' ORDER BY symbol''', (symbols,)).fetchall()
    label = r'\s*'.join(map(re.escape, '一年内到期的非流动负债'))
    for report in reports:
        path = Path(report['local_path'])
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != report['sha256']:
                raise ValueError('Original hash mismatch')
        pages = extract_pages(path)
        candidates = [r for r in extract_candidates_from_pages(pages)
                      if r['field_name'] == 'current_portion_long_term_debt']
        contexts = []
        for index, page in enumerate(pages):
            match = re.search(label, page)
            if match:
                contexts.append({'pdf_page': index + 1,
                                 'text': page[max(0, match.start() - 250):match.end() + 320]})
            if len(contexts) == 3:
                break
        print(json.dumps({'report': report, 'current_parser_candidates': candidates,
                          'first_label_contexts': contexts, 'read_only': True},
                         ensure_ascii=False, default=str), flush=True)


if __name__ == '__main__':
    main()

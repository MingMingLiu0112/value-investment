"""Compare candidate extraction from two decoders of the same retained PDF."""
import hashlib
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.filing_extract import extract_candidates_from_pages


def main():
    path = Path(sys.argv[1])
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    result = {'file': str(path), 'sha256': digest, 'engines': {}}
    for engine in ('pypdf', 'pdfium'):
        pages = ([page.extract_text() or '' for page in PdfReader(path).pages]
                 if engine == 'pypdf' else extract_pages(path))
        candidates = extract_candidates_from_pages(pages)
        result['engines'][engine] = {
            'pages': len(pages), 'candidates': len(candidates),
            'fields': dict(Counter(c['field_name'] for c in candidates)),
            'values': [{k: c[k] for k in ('field_name','value','unit','page')} for c in candidates],
        }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

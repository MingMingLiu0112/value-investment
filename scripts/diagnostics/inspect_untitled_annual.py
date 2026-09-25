"""Read an official abbreviated-title annual cover; do not infer its fiscal year."""
from pathlib import Path
import json

from value_investment_agent.disclosures import _download, _sha256_file, _is_complete_pdf
from value_investment_agent.pdf_text import extract_pages

url = 'https://static.cninfo.com.cn/finalpage/2026-03-28/1225048147.PDF'
path = Path('/app/evidence/600754/cninfo-1225048147.pdf')
digest = _sha256_file(path) if _is_complete_pdf(path) else _download(url, path)
pages = extract_pages(path)
print(json.dumps({'url': url, 'sha256': digest, 'path': str(path), 'first_pages': pages[:2]}, ensure_ascii=False))

"""Compare an alternative PDF text engine to the retained source PDF."""
import hashlib
import json
from pathlib import Path
import sys
import pypdfium2 as pdfium

path = Path(sys.argv[1])
expected = sys.argv[2]
assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
document = pdfium.PdfDocument(path)
for index in [4,7,8,9,14]:
    page = document[index]
    text_page = page.get_textpage()
    text = text_page.get_text_range()
    print(json.dumps({'page':index+1,'text':text[:5500]},ensure_ascii=False),flush=True)
    if index == 8:
        bitmap = page.render(scale=2)
        bitmap.to_pil().save(path.with_suffix('.page9.png'))
        bitmap.close()
    text_page.close()
    page.close()
document.close()

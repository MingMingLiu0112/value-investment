"""PDFium text decoding for issuer PDFs with nonstandard embedded fonts."""
from pathlib import Path

import pypdfium2 as pdfium


def extract_pages(path: Path, limit: int | None = None) -> list[str]:
    document = pdfium.PdfDocument(path)
    pages = []
    try:
        for index in range(min(len(document),limit) if limit else len(document)):
            page = document[index]
            try:
                text_page = page.get_textpage()
                try:
                    pages.append(text_page.get_text_range())
                finally:
                    text_page.close()
            finally:
                page.close()
    finally:
        document.close()
    return pages

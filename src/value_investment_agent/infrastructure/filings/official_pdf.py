"""Bounded official PDF acquisition without trusting redirects or HTML bodies."""
import hashlib
from pathlib import Path
from urllib.parse import urlparse

import requests
import pypdfium2 as pdfium


def validate_pdf_original(path: Path) -> None:
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-4096:]:
        raise ValueError("Official original is not a complete PDF")
    try:
        document = pdfium.PdfDocument(path)
        try:
            if not len(document):
                raise ValueError("Official PDF contains no pages")
        finally:
            document.close()
    except Exception as error:
        raise ValueError("Official original PDF cannot be parsed") from error


def download_official_pdf(url: str, target: Path) -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != "static.cninfo.com.cn"
            or parsed.username or parsed.password):
        raise ValueError("Official PDF URL is outside approved disclosure host")
    with requests.Session() as session:
        session.trust_env = False
        with session.get(url, timeout=(15, 60), stream=True, allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Official PDF redirects are not admitted")
            total = 0
            with target.open("xb") as output:
                for block in response.iter_content(64 * 1024):
                    total += len(block)
                    if total > 32 * 1024 * 1024:
                        raise ValueError("Official PDF byte budget exceeded")
                    output.write(block)
    validate_pdf_original(target)
    return hashlib.sha256(target.read_bytes()).hexdigest()

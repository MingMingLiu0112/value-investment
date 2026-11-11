"""Offline OCR packet sealing for an official half-year share table."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

import pypdfium2 as pdfium


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(original, output, package_dir, *, source_url):
    original, output, package_dir = map(Path, (original, output, package_dir))
    sys.path.insert(0, str(package_dir))
    from rapidocr import RapidOCR

    engine = RapidOCR()
    output.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(original)
    package_files = sorted(package_dir.glob("rapidocr-3.10.0.dist-info/METADATA"))
    if not package_files:
        raise ValueError("RAPIDOCR_VERSION_UNVERIFIED")
    package_hashes = {
        str(p.relative_to(package_dir)).replace("\\", "/"): _sha(p)
        for p in package_files + sorted((package_dir / "rapidocr/models").glob("*.onnx"))
    }
    try:
        for page_no in (22, 23):
            page = doc[page_no - 1]
            try:
                bitmap = page.render(scale=3)
                try:
                    raw_sha = hashlib.sha256(bytes(bitmap.buffer)).hexdigest()
                    image = output / f"page-{page_no}.png"
                    bitmap.to_pil().save(image, format="PNG")
                finally:
                    bitmap.close()
            finally:
                page.close()
            result = engine(str(image))
            rows = [
                {"text": str(text), "confidence": float(score)}
                for text, score in zip(result.txts, result.scores)
            ]
            packet = {
                "schema_version": "official-halfyear-shares-ocr-artifact-v2",
                "engine": "rapidocr-3.10.0",
                "package_sha256": package_hashes,
                "render_engine": "pypdfium2",
                "render_version": version("pypdfium2"),
                "render_scale": 3,
                "render_raw_sha256": raw_sha,
                "original_sha256": _sha(original),
                "source_url": source_url,
                "physical_page": page_no,
                "image_sha256": _sha(image),
                "status": "OCR_REQUIRES_VISUAL_VERIFICATION",
                "rows": rows,
            }
            (output / f"page-{page_no}.ocr.json").write_text(
                json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    finally:
        doc.close()

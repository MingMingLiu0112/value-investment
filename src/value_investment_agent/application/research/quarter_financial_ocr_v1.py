"""Fixed-source 600519 Q3 2026 OCR verifier, not a general extractor or A closure."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re

import pypdfium2 as pdfium

from ...infrastructure.filings.pdfium_runtime import serialized_pdfium

VERSION = 'core-value-f2-quarter-financial-ocr-v1'
SUPPORTED_SCOPE = 'FIXED_SOURCE_600519_Q3_2026'
RECEIPT_SCHEMA = 'official-quarter-pdfium-ocr-receipt-v1'
OCR_SCHEMA = 'official-quarter-ocr-raw-v1'
REGISTRATION_SHA256 = '3754bc057d2e4162f4aeb64285dd2c9cf13aa24ae7f6a961324f68f576ba6851'
MODELS = {
    'PP-OCRv6_det_small.onnx': '090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f',
    'PP-OCRv6_rec_small.onnx': '6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884',
    'ch_ppocr_mobile_v2.0_cls_mobile.onnx': 'e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c',
}
AMOUNTS = {'revenue_ytd_cny': ('营业收入', '130,970,743,649.04'),
           'attributable_profit_ytd_cny': ('归属于上市公司股东的', '64,467,425,981.95')}


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _hash(path):
    return sha256(path.read_bytes()).hexdigest()


def _row(rows, value):
    hits = [row for row in rows if row.get('text') == value]
    _require(len(hits) == 1, 'OCR_ROW_MISSING_OR_DUPLICATE:' + value)
    row = hits[0]
    _require(isinstance(row.get('confidence'), (float, int)) and row['confidence'] >= .98,
             'OCR_CONFIDENCE_LOW:' + value)
    box = row.get('box')
    _require(isinstance(box, list) and len(box) == 4 and
             all(isinstance(p, list) and len(p) == 2 and
                 all(isinstance(v, (int, float)) for v in p) for p in box),
             'OCR_GEOMETRY_INVALID:' + value)
    return (min(p[0] for p in box), min(p[1] for p in box),
            max(p[0] for p in box), max(p[1] for p in box))


@serialized_pdfium
def _render_and_native(path, page_numbers):
    doc = pdfium.PdfDocument(path)
    out = {}
    try:
        for number in page_numbers:
            page = doc[number - 1]
            try:
                image = page.render(scale=3).to_pil()
                textpage = page.get_textpage()
                try:
                    native = textpage.get_text_range()
                finally:
                    textpage.close()
                out[number] = (image.size, sha256(image.tobytes()).hexdigest(), native)
            finally:
                page.close()
    finally:
        doc.close()
    return out


def replay_quarter_financial_ocr(*, receipt_path: Path, receipt_sha256: str,
                                 original_sha256: str, as_of: datetime,
                                 registration_path: Path,
                                 registration_sha256: str,
                                 registered_available_at: datetime,
                                 original_path: Path | None = None):
    """Replay a pinned official receipt; return two YTD observations only."""
    receipt_path = Path(receipt_path)
    _require(as_of.tzinfo is not None, 'AS_OF_TIMEZONE_REQUIRED')
    _require(registered_available_at.tzinfo is not None, 'REGISTERED_TIMEZONE_REQUIRED')
    _require(registration_sha256 == REGISTRATION_SHA256 and
             _hash(Path(registration_path)) == registration_sha256,
             'REGISTRATION_HASH_CHANGED')
    registration = json.loads(Path(registration_path).read_text(encoding='utf-8'))
    _require(registration.get('parser_version') == 'cninfo-announcement-window-v1',
             'REGISTRATION_INVALID')
    recorded = datetime.fromisoformat(registration['retrieved_at'].replace('Z', '+00:00'))
    _require(recorded.tzinfo is not None and recorded == registered_available_at,
             'REGISTRATION_TIME_UNVERIFIED')
    _require(as_of >= recorded, 'NOT_AVAILABLE_AS_OF')
    _require(_hash(receipt_path) == receipt_sha256, 'RECEIPT_HASH_CHANGED')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    _require(receipt.get('schema_version') == RECEIPT_SCHEMA and
             receipt.get('status') == 'UNADMITTED_OCR_EVIDENCE' and
             receipt.get('action') == 'no_order' and
             receipt.get('scope') == 'PAGE_IMAGES_AND_OCR_ONLY_NOT_FINANCIAL_FACT_OR_SHARE_CONTINUITY',
             'RECEIPT_SCOPE_INVALID')
    _require(receipt.get('report_period') == '2026-09-30' and
             receipt.get('source_url') ==
             'https://static.cninfo.com.cn/finalpage/2026-10-31/1225649896.PDF',
             'REPORT_IDENTITY_INVALID')
    _require(as_of.astimezone(timezone.utc).date().isoformat() >= '2026-10-31',
             'NOT_AVAILABLE_AS_OF')
    original = Path(original_path) if original_path is not None else Path(receipt['original_path'])
    _require(original.name == Path(receipt['original_path']).name,
             'ORIGINAL_IDENTITY_CHANGED')
    _require(receipt.get('original_sha256') == original_sha256 and
             _hash(original) == original_sha256, 'ORIGINAL_HASH_CHANGED')
    _require(any(row.get('id') == 'cninfo:1225649896' and
                 row.get('sha256') == original_sha256 and
                 row.get('source_url') == receipt['source_url'] and
                 Path(row.get('path', '')).name == original.name
                 for row in registration.get('evidence_refs', [])),
             'REGISTRATION_SOURCE_UNVERIFIED')
    files = receipt.get('files')
    _require(isinstance(files, list) and [f.get('physical_page') for f in files] == [1, 7],
             'RECEIPT_PAGES_INVALID')
    rendered = _render_and_native(original, [1, 7])
    ocr = {}
    for entry in files:
        number = entry['physical_page']
        _require(entry.get('image') == f'page-{number}.png' and
                 entry.get('ocr') == f'page-{number}.ocr.json', 'RECEIPT_FILE_INVALID')
        image_path = receipt_path.parent / entry['image']
        ocr_path = receipt_path.parent / entry['ocr']
        _require(_hash(image_path) == entry['image_sha256'] and
                 _hash(ocr_path) == entry['ocr_sha256'], 'EVIDENCE_HASH_CHANGED')
        data = json.loads(ocr_path.read_text(encoding='utf-8'))
        size, pixel_hash, native = rendered[number]
        _require(data.get('schema_version') == OCR_SCHEMA and
                 data.get('status') == 'OCR_REQUIRES_SOURCE_RECONCILIATION' and
                 data.get('ocr_engine') == 'rapidocr-3.10.0' and
                 data.get('model_sha256') == MODELS and
                 data.get('render_engine') == 'pypdfium2' and
                 data.get('render_scale') == 3 and
                 data.get('physical_page') == number and
                 data.get('symbol') == '600519' and
                 data.get('report_period') == '2026-09-30' and
                 data.get('original_sha256') == original_sha256 and
                 data.get('image_sha256') == entry['image_sha256'] and
                 data.get('pixel_sha256') == entry['pixel_sha256'] == pixel_hash and
                 data.get('image_size') == list(size), 'OCR_BINDING_INVALID')
        generated = datetime.fromisoformat(data['generated_at'].replace('Z', '+00:00'))
        _require(generated.tzinfo is not None and generated <= as_of and
                 generated.date().isoformat() >= '2026-10-31', 'NOT_AVAILABLE_AS_OF')
        _require(len(data.get('rows', [])) == entry['rows'], 'OCR_ROW_COUNT_CHANGED')
        _require(any('贵州茅台酒股份有限公司' in row.get('text', '') for row in data['rows']) and
                 any('2026年第三季度报告' in row.get('text', '') for row in data['rows']),
                 'OCR_ISSUER_PERIOD_INVALID')
        _require('600519' in native or number == 7, 'ORIGINAL_ISSUER_UNVERIFIED')
        ocr[number] = data
    rows = ocr[1]['rows']
    header = _row(rows, '年初至报告期末')
    unit = _row(rows, '单位：元币种：人民币')
    _require(1050 < header[0] < 1350 and header[1] < 1900 and
             unit[1] < header[1], 'YTD_COLUMN_OR_UNIT_INVALID')
    native = rendered[1][2]
    _require('130,970,743,649.04' in native and '64,467,425,981.95' in native,
             'ORIGINAL_NUMBERS_UNVERIFIED')
    facts = {}
    for key, (label, value) in AMOUNTS.items():
        box = _row(rows, value)
        label_boxes = [_row(rows, label)] if key == 'revenue_ytd_cny' else [
            _row([r for r in rows if r.get('text') == label and
                  2000 < min(p[1] for p in r.get('box', [[0, 0]])) < 2100], label)]
        _require(1050 < box[0] < 1350 and abs(box[1] - label_boxes[0][1]) < 45 and
                 box[1] > header[1] and re.fullmatch(r'[\d,]+\.\d{2}', value),
                 'YTD_ROW_OR_COLUMN_INVALID:' + key)
        _require(native.count(value) == 1, 'ORIGINAL_NUMBER_AMBIGUOUS:' + key)
        facts[key] = value.replace(',', '')
    return {'version': VERSION, 'supported_scope': SUPPORTED_SCOPE,
            'status': 'VERIFIED_REPORTED_Q3_UNAUDITED_OBSERVATION',
            'symbol': '600519', 'issuer': '贵州茅台酒股份有限公司',
            'report_period': '2026-09-30', 'period_basis': 'YTD_9M',
            'currency': 'CNY', 'unit': 'yuan', 'facts': facts,
            'source_sha256': original_sha256, 'receipt_sha256': receipt_sha256,
            'formal_eligibility': False, 'valuation_admitted': False, 'action': 'no_order'}

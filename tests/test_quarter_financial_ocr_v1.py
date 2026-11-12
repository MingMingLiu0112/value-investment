from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import shutil

import pytest

from value_investment_agent.application.research.quarter_financial_ocr_v1 import replay_quarter_financial_ocr
from value_investment_agent.application.research.quarter_financial_ocr_v1 import _row

SEALED = Path('D:/GPTProject/value-investment/.tmp/vf1/runtime/value-q3-pdfium-ocr-600519-20261111')
ORIGINAL = Path('D:/GPTProject/value-investment/.tmp/vf1/runtime/value-alignment-event-observation/600519-20261030-20261110-20261111T025324Z/600519-1225649896.pdf')
REGISTRATION = ORIGINAL.parent / 'event-scan.json'
REGISTRATION_SHA = '3754bc057d2e4162f4aeb64285dd2c9cf13aa24ae7f6a961324f68f576ba6851'
REGISTERED_AT = datetime(2026, 11, 11, 2, 53, 26, 730420, tzinfo=timezone.utc)
RECEIPT_SHA = '72955918b4c6fc2f297a366a371e40a7f0c9cdf63c3462aac54d568237f18f81'
ORIGINAL_SHA = '96ba51ebf414f841bce79b3ba019927df2f795142392e12e96a9d559e96ebb9b'
AS_OF = datetime(2026, 11, 11, 5, tzinfo=timezone.utc)


def test_row_geometry_contract_without_runtime():
    assert _row([{'text': '营业收入', 'confidence': .99,
                  'box': [[1, 2], [5, 2], [5, 6], [1, 6]]}], '营业收入') == (1, 2, 5, 6)
    with pytest.raises(ValueError, match='OCR_GEOMETRY_INVALID'):
        _row([{'text': '营业收入', 'confidence': .99, 'box': [[1, 2]]}], '营业收入')


def test_row_confidence_rejected_without_runtime():
    with pytest.raises(ValueError, match='OCR_CONFIDENCE_LOW'):
        _row([{'text': '营业收入', 'confidence': .97,
               'box': [[1, 2], [5, 2], [5, 6], [1, 6]]}], '营业收入')


def test_row_duplicate_rejected_without_runtime():
    row = {'text': '营业收入', 'confidence': .99,
           'box': [[1, 2], [5, 2], [5, 6], [1, 6]]}
    with pytest.raises(ValueError, match='OCR_ROW_MISSING_OR_DUPLICATE'):
        _row([row, row.copy()], '营业收入')


def _require_sealed_inputs():
    missing = [str(path) for path in (SEALED / 'receipt.json', ORIGINAL, REGISTRATION,
                SEALED / 'page-1.ocr.json', SEALED / 'page-7.ocr.json',
                SEALED / 'page-1.png', SEALED / 'page-7.png') if not path.is_file()]
    if missing:
        pytest.skip('local sealed OCR acceptance inputs unavailable: ' + ', '.join(missing))


def test_missing_local_seal_skips_acceptance(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), 'SEALED', tmp_path / 'missing')
    with pytest.raises(pytest.skip.Exception, match='local sealed OCR acceptance inputs unavailable'):
        _require_sealed_inputs()


def _replay(path, **changes):
    args = dict(receipt_path=path, receipt_sha256=sha256(path.read_bytes()).hexdigest(),
                original_sha256=ORIGINAL_SHA, as_of=AS_OF,
                registration_path=REGISTRATION, registration_sha256=REGISTRATION_SHA,
                registered_available_at=REGISTERED_AT)
    args.update(changes)
    return replay_quarter_financial_ocr(**args)


@pytest.fixture
def packet(tmp_path):
    _require_sealed_inputs()
    for name in ('receipt.json', 'page-1.ocr.json', 'page-7.ocr.json',
                 'page-1.png', 'page-7.png'):
        shutil.copy2(SEALED / name, tmp_path / name)
    shutil.copy2(ORIGINAL, tmp_path / ORIGINAL.name)
    receipt = json.loads((tmp_path / 'receipt.json').read_text(encoding='utf-8'))
    receipt['original_path'] = str(tmp_path / ORIGINAL.name)
    (tmp_path / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
    return tmp_path


def _rewrite_ocr(packet, page, edit):
    path = packet / f'page-{page}.ocr.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    edit(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    receipt_path = packet / 'receipt.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    entry = next(f for f in receipt['files'] if f['physical_page'] == page)
    entry['ocr_sha256'] = sha256(path.read_bytes()).hexdigest()
    entry['rows'] = len(data['rows'])
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')


def test_real_sealed_cold_replay():
    _require_sealed_inputs()
    assert sha256((SEALED / 'receipt.json').read_bytes()).hexdigest() == RECEIPT_SHA
    assert sha256(REGISTRATION.read_bytes()).hexdigest() == REGISTRATION_SHA
    result = replay_quarter_financial_ocr(
        receipt_path=SEALED / 'receipt.json', receipt_sha256=RECEIPT_SHA,
        original_sha256=ORIGINAL_SHA, as_of=AS_OF,
        registration_path=REGISTRATION, registration_sha256=REGISTRATION_SHA,
        registered_available_at=REGISTERED_AT)
    assert result['facts'] == {'revenue_ytd_cny': '130970743649.04',
                               'attributable_profit_ytd_cny': '64467425981.95'}
    assert result['period_basis'] == 'YTD_9M'
    assert result['supported_scope'] == 'FIXED_SOURCE_600519_Q3_2026'
    assert result['valuation_admitted'] is False and result['formal_eligibility'] is False


def test_before_report_date_and_before_registration(packet):
    path = packet / 'receipt.json'
    for instant in (datetime(2026, 10, 30, 23, 59, tzinfo=timezone.utc),
                    datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc),
                    REGISTERED_AT.replace(microsecond=730419)):
        with pytest.raises(ValueError, match='NOT_AVAILABLE_AS_OF'):
            _replay(path, as_of=instant)
    with pytest.raises(ValueError, match='REGISTRATION_TIME_UNVERIFIED'):
        _replay(path, registered_available_at=datetime(2026, 10, 31, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match='REGISTRATION_HASH_CHANGED'):
        _replay(path, registration_sha256='0' * 64)


def test_tampered_receipt_image_original_and_pixel(packet):
    path = packet / 'receipt.json'
    with pytest.raises(ValueError, match='RECEIPT_HASH_CHANGED'):
        _replay(path, receipt_sha256='0' * 64)
    (packet / 'page-1.png').write_bytes(b'tamper')
    with pytest.raises(ValueError, match='EVIDENCE_HASH_CHANGED'):
        _replay(path)
    shutil.copy2(SEALED / 'page-1.png', packet / 'page-1.png')
    _rewrite_ocr(packet, 1, lambda d: d.update(pixel_sha256='0' * 64))
    with pytest.raises(ValueError, match='OCR_BINDING_INVALID'):
        _replay(path)
    (packet / ORIGINAL.name).write_bytes(b'%PDF-tampered')
    with pytest.raises(ValueError, match='ORIGINAL_HASH_CHANGED'):
        _replay(path)


def test_wrong_column_unit_confidence_future_and_duplicate(packet):
    path = packet / 'receipt.json'
    _rewrite_ocr(packet, 1, lambda d: next(r for r in d['rows'] if r['text'] ==
                 '130,970,743,649.04')['box'].__setitem__(0, [650, 1926]))
    with pytest.raises(ValueError, match='YTD_ROW_OR_COLUMN_INVALID'):
        _replay(path)
    shutil.copy2(SEALED / 'page-1.ocr.json', packet / 'page-1.ocr.json')
    _rewrite_ocr(packet, 1, lambda d: next(r for r in d['rows'] if r['text'] ==
                 '单位：元币种：人民币').update(text='单位：股'))
    with pytest.raises(ValueError, match='OCR_ROW_MISSING_OR_DUPLICATE'):
        _replay(path)
    shutil.copy2(SEALED / 'page-1.ocr.json', packet / 'page-1.ocr.json')
    _rewrite_ocr(packet, 1, lambda d: next(r for r in d['rows'] if r['text'] ==
                 '64,467,425,981.95').update(confidence=.5))
    with pytest.raises(ValueError, match='OCR_CONFIDENCE_LOW'):
        _replay(path)
    with pytest.raises(ValueError, match='NOT_AVAILABLE_AS_OF'):
        _replay(path, as_of=datetime(2026, 10, 30, tzinfo=timezone.utc))
    shutil.copy2(SEALED / 'page-1.ocr.json', packet / 'page-1.ocr.json')
    _rewrite_ocr(packet, 1, lambda d: d['rows'].append(next(r.copy() for r in d['rows']
                 if r['text'] == '130,970,743,649.04')))
    with pytest.raises(ValueError, match='OCR_ROW_MISSING_OR_DUPLICATE'):
        _replay(path)


def test_unverified_original_rejected(packet):
    path = packet / 'receipt.json'
    with pytest.raises(ValueError, match='ORIGINAL_HASH_CHANGED'):
        _replay(path, original_sha256='0' * 64)
    _rewrite_ocr(packet, 1, lambda d: next(r for r in d['rows'] if r['text'] ==
                 '130,970,743,649.04').update(text='130,970,743,649.05'))
    with pytest.raises(ValueError, match='OCR_ROW_MISSING_OR_DUPLICATE'):
        _replay(path)

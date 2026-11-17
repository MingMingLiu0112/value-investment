from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from value_investment_agent.infrastructure.filings import official_dividend_notice_ocr_v1 as notice


def _write(path, data):
    path.write_bytes(data)
    return sha256(data).hexdigest()


def _fixture(tmp_path, monkeypatch):
    root = tmp_path
    folder = root / 'source'
    folder.mkdir(parents=True)
    pdf_hash = _write(folder / 'original.pdf', b'%PDF-fixture')
    published_ms = int(datetime(2026, 4, 17,
        tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000)
    index_hash = _write(folder / 'index.json', json.dumps({'announcements': [{
        'secCode': '600519', 'announcementId': '1225114720',
        'adjunctUrl': 'finalpage/2026-04-17/1225114720.PDF',
        'announcementTime': published_ms,
    }]}).encode())
    first = '证券代码：600519 贵州茅台酒股份有限公司'
    second = ('2025年年度利润分配拟向全体股东每股派发现金红利27.993元'
              '截至2026年3月31日，公司总股本为1,252,270,215股，'
              '回购专用账户内的股份数为794,176股，'
              '总股本扣除回购专用账户内的股份数为1,251,476,039股，'
              '以此计算合计拟派发现金红利35,032,568,759.73元'
              '本次分配方案尚需提交公司股东会审议')
    for number, text in ((1, first), (2, second)):
        image = folder / f'page-{number}.png'
        image_hash = _write(image, f'image {number}'.encode())
        (folder / f'page-{number}.ocr.json').write_text(json.dumps({
            'engine': 'rapidocr-3.10.0', 'original_sha256': pdf_hash,
            'image_sha256': image_hash, 'physical_page': number,
            'status': 'OCR_REQUIRES_VISUAL_VERIFICATION',
            'rows': [{'text': text, 'confidence': 0.99}],
        }), encoding='utf-8')
    fetched = datetime(2026, 11, 11, tzinfo=timezone.utc)
    receipt = folder / 'receipt.json'
    receipt.write_text(json.dumps({
        'schema_version': 'research-source-receipt-v1', 'action': 'no_order',
        'symbol': '600519', 'source_host': 'static.cninfo.com.cn',
        'source_url': 'https://static.cninfo.com.cn/finalpage/2026-04-17/1225114720.PDF',
        'index_announcement_id': '1225114720', 'published_date': '2026-04-17',
        'index_announcement_time_ms': published_ms,
        'fetched_at': fetched.isoformat(), 'source_path': 'source/original.pdf',
        'source_sha256': pdf_hash, 'source_bytes': len(b'%PDF-fixture'), 'index_captures': [
            {'path': 'source/index.json', 'sha256': index_hash}],
    }), encoding='utf-8')
    monkeypatch.setattr(notice, 'validate_pdf_original', lambda path: None)
    monkeypatch.setattr(notice, 'extract_pages', lambda path, limit: [first, second])
    return root, receipt, fetched


def test_source_bound_proposal_not_future_policy(tmp_path, monkeypatch):
    root, receipt, fetched = _fixture(tmp_path, monkeypatch)
    result = notice.replay_proposed_dividend(
        root=root, receipt_path=receipt, symbol='600519',
        issuer_name='贵州茅台酒股份有限公司', as_of=fetched + timedelta(seconds=1))
    assert result['proposed_total_cny'] == '35032568759.73'
    assert result['status'] == 'OFFICIAL_PROPOSAL_NOT_PAYMENT_OR_POLICY'
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    with pytest.raises(ValueError, match='NOT_AVAILABLE_AS_OF'):
        notice.replay_proposed_dividend(root=root, receipt_path=receipt, symbol='600519',
            issuer_name='贵州茅台酒股份有限公司', as_of=fetched - timedelta(seconds=1))
    (receipt.parent / 'page-2.png').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='SOURCE_BINDING_INVALID'):
        notice.replay_proposed_dividend(root=root, receipt_path=receipt, symbol='600519',
            issuer_name='贵州茅台酒股份有限公司', as_of=fetched + timedelta(seconds=1))


def test_ocr_cannot_replace_original_or_official_index(tmp_path, monkeypatch):
    root, receipt, fetched = _fixture(tmp_path, monkeypatch)
    argument = dict(root=root, receipt_path=receipt, symbol='600519',
                    issuer_name='贵州茅台酒股份有限公司',
                    as_of=fetched + timedelta(seconds=1))
    (receipt.parent / 'original.pdf').write_bytes(b'%PDF-forged')
    with pytest.raises(ValueError, match='ORIGINAL_HASH_CHANGED'):
        notice.replay_proposed_dividend(**argument)
    root, receipt, fetched = _fixture(tmp_path / 'other', monkeypatch)
    argument = dict(root=root, receipt_path=receipt, symbol='600519',
                    issuer_name='贵州茅台酒股份有限公司',
                    as_of=fetched + timedelta(seconds=1))
    (receipt.parent / 'index.json').write_text('{"announcements":[]}', encoding='utf-8')
    with pytest.raises(ValueError, match='INDEX_HASH_CHANGED'):
        notice.replay_proposed_dividend(**argument)

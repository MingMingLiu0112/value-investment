"""Archive a bounded issuer-embedded announcement query and its monthly return."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, ProxyHandler, build_opener


INDEX_URL = 'https://asia.tools.euroland.com/tools/Pressreleases/Main/GetNews/'
ISSUER_URL = 'https://www.midea.com.cn/en/Investors/information_disclosure'
QUERY = {'strDateFrom': '01/10/2025', 'strDateTo': '15/10/2025',
         'typeFilter': '', 'orderBy': '0', 'pageIndex': '0', 'pageJummp': '26',
         'hasTypeFilter': 'false', 'searchPhrase': '', 'companyCode': 'cn-000333',
         'onlyInsiderInfo': 'false', 'lang': 'en-GB', 'v': 'h-share',
         'alwaysIncludeInsiders': 'false', 'strYears': ''}


def main():
    root = Path('runtime/midea-monthly-shares') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root.mkdir(parents=True, exist_ok=False)
    opener = build_opener(ProxyHandler({}))
    request = Request(INDEX_URL, data=urlencode(QUERY).encode(),
                      headers={'Content-Type': 'application/x-www-form-urlencoded',
                               'User-Agent': 'Mozilla/5.0'})
    manifest = {'issuer_page': ISSUER_URL, 'query': QUERY, 'files': [],
                'financial_facts_verified': False, 'backtest_ready': False}

    def retain(url, filename, request=None):
        with opener.open(request or url, timeout=30) as response:
            raw = response.read(8 * 1024**2 + 1)
            if not raw or len(raw) > 8 * 1024**2:
                raise ValueError('Empty or oversized response')
            if filename.endswith('.pdf') and not raw.startswith(b'%PDF-'):
                raise ValueError('Not a PDF')
            (root / filename).write_bytes(raw)
            manifest['files'].append({'requested_url': url, 'final_url': response.url,
                'filename': filename, 'sha256': hashlib.sha256(raw).hexdigest(),
                'fetched_at': datetime.now(timezone.utc).isoformat()})
            return raw

    raw = retain(INDEX_URL, 'index.json', request)
    payload = json.loads(raw)
    news = payload['News']
    if len(news) != payload['total'] or len({r['ID'] for r in news}) != len(news):
        raise ValueError('Incomplete single-page index')
    rows = [r for r in news if r['title'] ==
            'Monthly Return of Equity Issuer on Movements in Securities for the month ended 30 September 2025']
    if len(rows) != 1 or rows[0]['ID'] != 7812944:
        raise ValueError('Monthly return identity changed; inspect before acceptance')
    attachments = [a for a in payload['Attachments'] if a['prID'] == rows[0]['ID']]
    if (len(attachments) != 1 or attachments[0]['atID'] != 3926930
            or attachments[0]['filename'] != 'HKEX-EPS_20251003_11869418_0.PDF'):
        raise ValueError('Attachment identity changed')
    url = 'https://ea-cdn.eurolandir.com/press-releases-attachments/3926930/HKEX-EPS_20251003_11869418_0.PDF'
    retain(url, 'midea-202509-monthly.pdf')
    manifest['announcement'] = rows[0]
    manifest['source_boundary'] = 'Issuer-embedded IR vendor copy; direct exchange original not yet matched'
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'directory': str(root), **manifest}, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Archive the fixed official notices inspected during historical fee research."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener
from bs4 import BeautifulSoup


SOURCES = {
    'stamp-2008': 'https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/200809/t20080919_76432.htm',
    'stamp-2023': 'https://www.mof.gov.cn/jrttts/202308/t20230828_3904235.htm',
    'transfer-2012': 'https://www.chinaclear.cn/old_files/1343899420865.pdf',
    'transfer-2015': 'https://www.chinaclear.cn/zdjs/gszb/201507/59ccd4176d2645f8b60b2d30fc3631bf.shtml',
    'transfer-2022': 'https://www.chinaclear.cn/zdjs/gszb/202204/837e3c5031104aa099d6597ba381342a.shtml',
}

EXPECTED = {
    'stamp-2008': ('单边征税', '千分之一'),
    'stamp-2023': ('2023年8月28日起', '减半征收'),
    'transfer-2015': ('0.0255', '0.02', '2015'),
    'transfer-2022': ('0.01', '双向', '2022'),
}


def validate_html(source_id, raw):
    text = ''.join(BeautifulSoup(raw, 'html.parser').get_text().split())
    if not all(token in text for token in EXPECTED[source_id]):
        raise ValueError('Notice content missing; maintenance or unexpected page')


def main():
    stamp = datetime.now(timezone.utc)
    target = Path('runtime/trading-rule-evidence') / stamp.strftime('%Y%m%dT%H%M%S%fZ')
    target.mkdir(parents=True, exist_ok=False)
    opener = build_opener(ProxyHandler({}))
    results = []
    for source_id, url in SOURCES.items():
        try:
            request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
            with opener.open(request, timeout=30) as response:
                raw = response.read(5 * 1024**2 + 1)
                if not raw or len(raw) > 5 * 1024**2:
                    raise ValueError('Empty or oversized response')
                suffix = '.pdf' if url.endswith('.pdf') else '.html'
                if suffix == '.pdf' and not raw.startswith(b'%PDF-'):
                    raise ValueError('Expected PDF')
                path = target / (source_id + suffix)
                path.write_bytes(raw)
                if response.url != url:
                    raise ValueError('Unexpected redirect; inspect archived response before acceptance')
                if suffix == '.html':
                    validate_html(source_id, raw)
                results.append({'source_id': source_id, 'requested_url': url,
                                'final_url': response.url, 'path': str(path),
                                'sha256': hashlib.sha256(raw).hexdigest(),
                                'fetched_at': datetime.now(timezone.utc).isoformat(),
                                'status': 'archived_content_requires_review'})
        except Exception as error:
            results.append({'source_id': source_id, 'requested_url': url,
                            'status': 'failed', 'error': str(error)})
        (target / 'manifest.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'directory': str(target), 'results': results}, ensure_ascii=False))
    if any(r['status'] == 'failed' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

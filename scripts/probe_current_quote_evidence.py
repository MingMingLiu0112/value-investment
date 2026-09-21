"""Archive three bounded quote responses to inspect provider date provenance."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = ROOT / 'runtime' / 'quote-session-probes' / stamp
    target.mkdir(parents=True)
    observations = []
    with requests.Session() as session:
        session.trust_env = False
        for name, url, params, headers in [
            ('tencent_rank', 'https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList',
             {'_appver': '11.17.0', 'board_code': 'aStock', 'sort_type': 'price',
              'direct': 'down', 'offset': '0', 'count': '1'}, {}),
            ('tencent_quotes', 'https://qt.gtimg.cn/q=sh600519,sz000333,sh601088', {}, {}),
            ('sina_quotes', 'https://hq.sinajs.cn/list=sh600519,sz000333,sh601088', {},
             {'Referer': 'https://finance.sina.com.cn/'}),
        ]:
            row = {'name': name, 'requested_url': url, 'params': params,
                   'started_at': datetime.now(timezone.utc).isoformat()}
            try:
                response = session.get(url, params=params, headers=headers, timeout=(10, 15))
                raw = response.content
                filename = name + '.bin'
                (target / filename).write_bytes(raw)
                row.update(url=response.url, http_status=response.status_code,
                           bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                           raw_path=filename, fetched_at=datetime.now(timezone.utc).isoformat())
                response.raise_for_status()
                if name == 'tencent_rank':
                    row['decoded'] = response.json()
                else:
                    row['decoded'] = raw.decode('gb18030')
            except (requests.RequestException, ValueError, UnicodeError) as error:
                row['error'] = str(error)
            observations.append(row)
    result = {'scope': 'three fixed research cases, read-only source probe',
              'signal_approval': False, 'observations': observations}
    (target / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'path': str(target / 'manifest.json'), **result}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""Bounded direct public income acquisition; financial admission is elsewhere."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode

import requests

ENDPOINT = 'https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022'
MAX_BYTES = 2_000_000


def collect_sina_income_original(*, root: Path, symbol: str, output_dir: Path,
                                 allow_network: bool = False) -> dict | None:
    if not isinstance(symbol, str) or not re.fullmatch(r'(?:6\d{5}|[03]\d{5})', symbol, flags=re.ASCII):
        raise ValueError('Income collection requires supported six-digit security identity')
    if type(allow_network) is not bool:
        raise ValueError('Income network permission must be explicit boolean')
    if not allow_network:
        return None
    root = root.resolve()
    output = output_dir.resolve()
    if not output.is_relative_to((root / 'runtime').resolve()) or not output.is_relative_to(root):
        raise ValueError('Income originals must remain inside runtime')
    if output.exists():
        raise FileExistsError('Income acquisition requires a fresh immutable directory')
    exchange = 'sh' if symbol.startswith('6') else 'sz'
    url = ENDPOINT + '?' + urlencode(dict(paperCode=exchange + symbol, source='lrb', type='0', page='1', num='16'))
    with requests.Session() as session:
        session.trust_env = False
        with session.get(url, timeout=(10, 20), stream=True, allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code != 200 or response.url != url:
                raise ValueError('Income redirects or unexpected response URL are forbidden')
            media = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
            if media not in {'application/json', 'text/json', 'text/plain'}:
                raise ValueError('Income response must contain JSON')
            length = response.headers.get('Content-Length')
            if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > MAX_BYTES):
                raise ValueError('Income declared byte budget exceeded or invalid')
            raw = bytearray()
            for chunk in response.iter_content(64 * 1024):
                if len(raw) + len(chunk) > MAX_BYTES:
                    raise ValueError('Income streamed byte budget exceeded')
                raw.extend(chunk)
    acquired = datetime.now(timezone.utc).isoformat()
    output.mkdir(parents=True)
    original = output / 'sina-income.json'
    with original.open('xb') as stream:
        stream.write(raw)
    descriptor = dict(path=original.relative_to(root).as_posix(),
        sha256=hashlib.sha256(raw).hexdigest(), acquired_at=acquired, source_url=url)
    receipt = dict(url=url, path=descriptor['path'], sha256=descriptor['sha256'],
                   acquired_at=acquired, bytes=len(raw), action='no_order')
    receipt_path = output / 'acquisition.json'
    with receipt_path.open('xb') as stream:
        stream.write(json.dumps(receipt, sort_keys=True, allow_nan=False).encode('utf-8'))
    descriptor['receipt'] = dict(path=receipt_path.relative_to(root).as_posix(),
        sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())
    # Retain acquired bytes/receipt even when the public service returns an error.
    payload = json.loads(raw.decode('utf-8'))
    reports = payload['result']['data']['report_list']
    if (not isinstance(reports, dict) or not 1 <= len(reports) <= 32
            or any(not isinstance(key, str) or not re.fullmatch(r'[0-9]{8}', key)
                   or not isinstance(report, dict) or not isinstance(report.get('data'), list)
                   or len(report['data']) > 512
                   or any(not isinstance(row, dict) for row in report['data'])
                   for key, report in reports.items())):
        raise ValueError('Income JSON report structure outside bounded contract')
    return descriptor

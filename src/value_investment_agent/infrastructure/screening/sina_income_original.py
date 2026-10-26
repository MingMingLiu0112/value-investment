"""Bounded Sina financial originals; acquisition never admits financial facts."""
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode

import requests

ENDPOINT = 'https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022'
MAX_BYTES = 2_000_000


class SinaStatement(str, Enum):
    INCOME = 'income'
    BALANCE = 'balance'
    CASHFLOW = 'cashflow'


# AkShare stock_financial_report_sina uses the same official endpoint mapping.
STATEMENT_SOURCES = {
    SinaStatement.INCOME: 'lrb',
    SinaStatement.BALANCE: 'fzb',
    SinaStatement.CASHFLOW: 'llb',
}


def _read_original(url: str, label: str, *, max_attempts: int) -> bytearray:
    """Two attempts only for transport/5xx failures; never retry access denials."""
    for attempt in range(max_attempts):
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.get(url, timeout=(10, 20), stream=True, allow_redirects=False) as response:
                    response.raise_for_status()
                    if response.status_code != 200 or response.url != url:
                        raise ValueError(f'{label} redirects or unexpected response URL are forbidden')
                    media = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
                    if media not in {'application/json', 'text/json', 'text/plain'}:
                        raise ValueError(f'{label} response must contain JSON')
                    length = response.headers.get('Content-Length')
                    if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > MAX_BYTES):
                        raise ValueError(f'{label} declared byte budget exceeded or invalid')
                    raw = bytearray()
                    for chunk in response.iter_content(64 * 1024):
                        if len(raw) + len(chunk) > MAX_BYTES:
                            raise ValueError(f'{label} streamed byte budget exceeded')
                        raw.extend(chunk)
            return raw
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as error:
            status = error.response.status_code if error.response is not None else None
            retryable = isinstance(error, (requests.Timeout, requests.ConnectionError)) or (
                status is not None and 500 <= status <= 599)
            server_backoff = error.response is not None and error.response.headers.get('Retry-After')
            if attempt + 1 >= max_attempts or not retryable or server_backoff:
                raise
            time.sleep(1)
    raise AssertionError('unreachable Sina retry budget')


def collect_sina_income_original(*, root: Path, symbol: str, output_dir: Path,
                                 allow_network: bool = False) -> dict | None:
    """Compatibility entry: identical income URL, filename and receipt schema."""
    return collect_sina_statement_original(root=root, symbol=symbol, output_dir=output_dir,
        statement=SinaStatement.INCOME, allow_network=allow_network)


def collect_sina_statement_original(*, root: Path, symbol: str, output_dir: Path,
                                    statement: SinaStatement | str,
                                    allow_network: bool = False) -> dict | None:
    """Acquire one explicit statement without parsing amounts or changing units.

    Provider currency/unit/period/scope declarations stay in the exact raw body.
    Missing declarations remain missing, not inferred as CNY or yuan. A returned
    descriptor is provider evidence, not verified facts or historical availability.
    """
    try:
        statement = SinaStatement(statement)
    except (TypeError, ValueError) as error:
        raise ValueError('Unknown Sina statement; expected income, balance or cashflow') from error
    label = statement.value.capitalize()
    if not isinstance(symbol, str) or not re.fullmatch(r'(?:6\d{5}|[03]\d{5})', symbol, flags=re.ASCII):
        raise ValueError(f'{label} collection requires supported six-digit security identity')
    if type(allow_network) is not bool:
        raise ValueError(f'{label} network permission must be explicit boolean')
    if not allow_network:
        return None
    root = root.resolve()
    output = output_dir.resolve()
    if not output.is_relative_to((root / 'runtime').resolve()) or not output.is_relative_to(root):
        raise ValueError(f'{label} originals must remain inside runtime')
    if output.exists():
        raise FileExistsError(f'{label} acquisition requires a fresh immutable directory')
    exchange = 'sh' if symbol.startswith('6') else 'sz'
    source = STATEMENT_SOURCES[statement]
    url = ENDPOINT + '?' + urlencode(dict(paperCode=exchange + symbol, source=source, type='0', page='1', num='16'))
    # Legacy income retries are already governed by the outer batch policy.
    raw = _read_original(url, label, max_attempts=1 if statement == SinaStatement.INCOME else 2)
    acquired = datetime.now(timezone.utc).isoformat()
    output.mkdir(parents=True)
    original = output / f'sina-{statement.value}.json'
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
        raise ValueError(f'{label} JSON report structure outside bounded contract')
    if statement != SinaStatement.INCOME and any(
            row.get('item_source') not in (None, source)
            for report in reports.values() for row in report['data']):
        raise ValueError(f'{label} JSON item source differs from requested statement')
    return descriptor

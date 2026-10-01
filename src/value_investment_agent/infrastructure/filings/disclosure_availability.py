"""Conservative date-level availability from a retained CNINFO index."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse


def indexed_disclosure_availability(index: dict, *, symbol: str, source_id: str,
                                    source_url: str) -> dict:
    if index.get('url') != 'https://www.cninfo.com.cn/new/hisAnnouncement/query':
        raise ValueError('unsupported official disclosure index')
    if not source_id.startswith('cninfo:'):
        raise ValueError('unsupported disclosure source id')
    rows = [row for row in index['announcements']
            if str(row.get('announcementId')) == source_id.split(':', 1)[1]]
    if len(rows) != 1:
        raise ValueError('disclosure index requires one matching announcement')
    row = rows[0]
    url = urlparse(source_url)
    if (row.get('secCode') != symbol or url.scheme != 'https'
            or url.hostname != 'static.cninfo.com.cn'
            or url.path.lstrip('/') != row.get('adjunctUrl')):
        raise ValueError('disclosure issuer or URL mismatch')
    epoch = row['announcementTime']
    if type(epoch) is not int or epoch <= 0:
        raise ValueError('invalid indexed disclosure date')
    local = datetime.fromtimestamp(epoch / 1000, tz=timezone(timedelta(hours=8)))
    day = local.date()
    conservative = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=local.tzinfo)
    return dict(disclosure_date=day.isoformat(), timestamp_precision='DATE_ONLY',
                available_from=conservative.isoformat(),
                basis='retained_cninfo_index_next_day_conservative_reconstruction',
                intraday_publication_proven=False, independent_historical_capture_proven=False)

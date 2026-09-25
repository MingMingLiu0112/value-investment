"""Inspect count/page cardinality without weakening the production completeness gate."""
import json
import signal
import requests
from akshare.utils import demjson
from market import AllAMarketAdapter


def timeout(signum, frame):
    raise TimeoutError('Sina pagination diagnosis exceeded 180 seconds')


signal.signal(signal.SIGALRM, timeout)
signal.alarm(180)
original_get = requests.get
pages = []


def observed_get(url, **kwargs):
    response = original_get(url, **kwargs)
    params = kwargs.get('params')
    if params:
        payload = demjson.decode(response.text)
        pages.append({'page': params.get('page'), 'requested': params.get('num'),
                      'received': len(payload) if isinstance(payload, list) else None})
    else:
        print(json.dumps({'count_url': url, 'count_response': response.text}), flush=True)
    return response


requests.get = observed_get
try:
    rows = AllAMarketAdapter._sina_rows()
    print(json.dumps({'status': 'complete', 'rows': len(rows), 'pages': pages}), flush=True)
except Exception as error:
    print(json.dumps({'error': str(error), 'pages': pages}), flush=True)
    raise

"""Unrounded statutory A-share fee components, not a complete broker invoice."""
from datetime import date
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path


VERSION = 'historical-statutory-fees-v1'
SOURCES = {
    'stamp-2008': 'https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/200809/t20080919_76432.htm',
    'stamp-2023': 'https://www.mof.gov.cn/jrttts/202308/t20230828_3904235.htm',
    'transfer-2012': 'https://www.chinaclear.cn/old_files/1343899420865.pdf',
    'transfer-2015': 'https://www.chinaclear.cn/zdjs/gszb/201507/59ccd4176d2645f8b60b2d30fc3631bf.shtml',
    'transfer-2022': 'https://www.chinaclear.cn/zdjs/gszb/202204/837e3c5031104aa099d6597ba381342a.shtml',
}

CURRENT_SSE_REVIEWED_ON = date(2026, 9, 16)
CURRENT_SSE_VERSION = 'sse-reviewed-session-fees-20260916-v1'
CURRENT_SSE_ARCHIVE = 'runtime/trading-rule-evidence/current-fees-20260916T140422086178Z'
CURRENT_SSE_EVIDENCE = {
    'sse-investor-guide': ('https://one.sse.com.cn/onething/gptz/',
                           'f5d95746ec6f8dc7d5c9f057b230ba56eae67dce05dbae06fe62a0bdad98f0db'),
    'stamp-2023': (SOURCES['stamp-2023'],
                   '5ee44881ff4e13099204c268b0ff30a167e5c0a7775903836df579091f86448a'),
    'transfer-2022': (SOURCES['transfer-2022'],
                      'df193394f3e06b6adad9e01ceea796be470e59b41b718eaf129b6644b0977703'),
}


def verify_current_sse_policy(root: Path) -> dict:
    sources = []
    for key, (url, expected) in CURRENT_SSE_EVIDENCE.items():
        relative = f'{CURRENT_SSE_ARCHIVE}/{key}.html'
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Current fee source changed: {key}')
        sources.append({'source_id': key, 'url': url, 'path': relative, 'sha256': expected})
    return {'version': CURRENT_SSE_VERSION, 'reviewed_on': CURRENT_SSE_REVIEWED_ON.isoformat(),
            'valid_session': CURRENT_SSE_REVIEWED_ON.isoformat(), 'exchange': 'SSE',
            'sources': sources, 'commission_includes_exchange_charges': True,
            'commission_scenario': {'rate': '0.0003', 'minimum_cny': '5',
                                    'rounding': 'total_fee_to_cent_half_even'},
            'excluded': ['dividend_tax', 'slippage', 'actual_broker_invoice'],
            'broker_invoice_verified': False,
            'limitation': 'Reviewed-session research policy only; refresh before later sessions. '
                          'Commission, minimum and cent rounding are scenarios, not a broker invoice.'}


def current_sse_components(traded_on, side, turnover):
    """Do not extend the immutable historical span or silently cover future dates."""
    if type(traded_on) is not date or traded_on != CURRENT_SSE_REVIEWED_ON:
        raise ValueError('Current SSE fees require the explicitly reviewed session')
    result = _statutory_components(traded_on, 'SSE', side, turnover)
    result.update(version=CURRENT_SSE_VERSION, reviewed_on=CURRENT_SSE_REVIEWED_ON.isoformat())
    result['source_urls']['sse-investor-guide'] = CURRENT_SSE_EVIDENCE['sse-investor-guide'][0]
    return result


def _positive_decimal(value):
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError('A positive finite Decimal is required')
    return value


def statutory_components(traded_on, exchange, side, turnover, *, traded_face_value=None):
    """Only ordinary SSE/SZSE A-share auction trades in the frozen research span.

    traded_on is the actual China-market fill date, not the signal date.
    Amounts are intentionally unrounded until invoice rounding is established.
    """
    if type(traded_on) is not date or not date(2015, 1, 1) <= traded_on <= date(2025, 12, 31):
        raise ValueError('Outside the 2015-2025 historical research scope')
    return _statutory_components(traded_on, exchange, side, turnover, traded_face_value=traded_face_value)


def _statutory_components(traded_on, exchange, side, turnover, *, traded_face_value=None):
    if exchange not in {'SSE', 'SZSE'} or side not in {'buy', 'sell'}:
        raise ValueError('Only SSE/SZSE ordinary A-share buy/sell auction trades are covered')
    turnover = _positive_decimal(turnover)
    stamp_source = 'stamp-2023' if traded_on >= date(2023, 8, 28) else 'stamp-2008'
    sell_rate = Decimal('0.0005') if stamp_source == 'stamp-2023' else Decimal('0.001')
    stamp_rate = sell_rate if side == 'sell' else Decimal('0')
    basis = turnover
    basis_name = 'turnover_cny'
    if traded_on >= date(2022, 4, 29):
        transfer_rate, transfer_source = Decimal('0.00001'), 'transfer-2022'
    elif traded_on >= date(2015, 8, 1):
        transfer_rate, transfer_source = Decimal('0.00002'), 'transfer-2015'
    else:
        transfer_source = 'transfer-2012'
        transfer_rate = Decimal('0.0000255')
        if exchange == 'SSE':
            basis = _positive_decimal(traded_face_value)
            basis_name = 'traded_face_value_cny'
            transfer_rate = Decimal('0.0003')
    with localcontext() as context:
        context.prec = 50
        stamp = turnover * stamp_rate
        transfer = basis * transfer_rate
        subtotal = stamp + transfer
    source_ids = list(dict.fromkeys(['stamp-2008', stamp_source, transfer_source]))
    return {
        'version': VERSION, 'traded_on': traded_on.isoformat(), 'exchange': exchange,
        'side': side, 'turnover_cny': turnover,
        'stamp_rate': stamp_rate, 'stamp_duty_unrounded_cny': stamp,
        'transfer_rate': transfer_rate, 'transfer_basis': basis_name,
        'transfer_basis_cny': basis, 'csdc_transfer_unrounded_cny': transfer,
        'statutory_subtotal_unrounded_cny': subtotal,
        'source_urls': {key: SOURCES[key] for key in source_ids},
        'full_cost_verified': False,
        'excluded': ['broker_commission_and_minimum', 'broker_retained_legacy_transfer_fee',
                     'commission_included_exchange_charges', 'invoice_rounding',
                     'slippage', 'dividend_tax'],
    }

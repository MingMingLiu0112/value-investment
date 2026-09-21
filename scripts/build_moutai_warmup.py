"""Original 2013 annual vintage and 2014 distribution, for 2015 warmup."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

from pypdf import PdfReader
import pypdfium2 as pdfium

BASE = 'runtime/historical-filing-index/20260909T061926130764Z'
SOURCES = {
    '63720184': '26524de9281264e149c23bdc618a32820678c8d07c5dc7c88cbc7e19b3df0bff',
    '64148207': '2bf42ced249aa8840e928d1971a0eff63af2736d05de8ba055d27d1be8e0ca33',
}
PRIOR = 'runtime/strategy-validation/moutai-annual-inputs-20260909T055311360531Z/annual-inputs.json'
PRIOR_HASH = '116d725d44e39d2d5ba2e5ef197db358e628b9822fb120066388acc4b6f263d2'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / 'scripts'))
    from build_moutai_annual_inputs import reference_arithmetic, select_original_vintage
    from value_investment_agent.historical_asof import publication_date_upper_bound
    out = root / 'runtime/strategy-validation' / ('moutai-warmup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    rows = {
        '63720184': [
            (7, '单位：元币种：人民币主要会计数据2013年2012年'),
            (7, '主要会计数据2013年2012年'),
            (7, '2013年末2012年末'),
            (7, '归属于上市公司股东的净利润15,136,639,784.35'),
            (7, '归属于上市公司股东的净资产42,622,216,487.81'),
            (7, '基本每股收益（元／股）14.58'),
            (2, '以2013年年末总股本103,818万股为基数'),
            (45, '归属于母公司所有者权益合计42,622,216,487.81'),
            (49, '归属于母公司所有者的净利润15,136,639,784.35'),
        ],
        '64148207': [
            (1, '每股派送红股0.10000股、每股派发现金红利4.37400元（含税）'),
            (1, '股权登记日：2014年6月24日'),
            (1, '除权（除息）日：2014年6月25日'),
            (1, '新增无限售条件流通股份上市日：2014年6月26日'),
            (1, '现金红利发放日：2014年6月25日'),
            (2, '公司暂按5%的税率代扣个人所得税，扣税后实际每股派发现金红利4.15030元'),
        ],
    }
    facts, bindings = [], {}
    try:
        for aid, expected in SOURCES.items():
            path = root / BASE / 'pdfs' / f'600519-{aid}.pdf'
            if digest(path) != expected:
                raise ValueError('Reviewed original changed')
            index_hits = []
            for ip in (root / BASE).glob('600519-*.json'):
                if digest(ip) != ip.stem.rsplit('-', 1)[-1]:
                    raise ValueError('Original index hash mismatch')
                for entry in json.loads(ip.read_text(encoding='utf-8'))['response']['announcements']:
                    if str(entry['announcementId']) == aid and entry['secCode'] == '600519':
                        index_hits.append((entry, ip))
            if len(index_hits) != 1:
                raise ValueError('Missing or ambiguous announcement identity')
            entry, ip = index_hits[0]
            published = datetime.fromtimestamp(entry['announcementTime'] / 1000, timezone(timedelta(hours=8))).date().isoformat()
            url = 'https://static.cninfo.com.cn/' + entry['adjunctUrl']
            if published not in url:
                raise ValueError('Announcement date and original URL disagree')
            bindings[aid] = {'source_id': 'cninfo:' + aid, 'source_url': url,
                'source_path': str(path.relative_to(root)), 'raw_file_hash': expected,
                'index_path': str(ip.relative_to(root)), 'index_hash': digest(ip),
                'published_date': published, 'available_at': publication_date_upper_bound(published).isoformat()}
            reader = PdfReader(path)
            with pdfium.PdfDocument(path) as doc:
                for number, literal in rows[aid]:
                    page = doc[number - 1]
                    textpage = page.get_textpage()
                    try:
                        texts = [reader.pages[number - 1].extract_text(), textpage.get_text_range()]
                        if any(re.sub(r'\s+', '', t).count(literal) != 1 for t in texts):
                            raise ValueError(f'{aid} p{number}: reviewed row not unique: {literal}')
                    finally:
                        textpage.close()
                        page.close()
                    facts.append({'source_id': 'cninfo:' + aid, 'page': number,
                                  'literal': literal, 'decoders': ['pypdf', 'pdfium']})
        arithmetic = reference_arithmetic('15136639784.35', '42622216487.81', '1038180000', '14.58')
        original = {**bindings['63720184'], 'symbol': '600519', 'report_year': 2013,
            'period_label': '2013-12-31', 'field_name': 'annual_reference_original', 'unit': 'CNY/share',
            'value': arithmetic['annual_reference_on_report_end_share_basis'],
            'timestamp_precision': 'date', 'publication_date_verified': True,
            'availability_bound_verified': True, 'availability_method': 'china_publication_date_upper_bound',
            'validation_status': 'verified', 'validation_scope': 'original_vintage_research_arithmetic_only',
            'trade_input_approved': False,
            'inputs': {'parent_profit_cny': '15136639784.35', 'parent_equity_cny': '42622216487.81',
                       'ending_issued_shares': '1038180000', 'reported_basic_eps': '14.58'},
            'arithmetic': arithmetic, 'evidence': [r for r in facts if r['source_id']=='cninfo:63720184']}
        event = {**bindings['64148207'], 'symbol': '600519', 'record_date': '2014-06-24',
            'ex_date': '2014-06-25', 'listing_date': '2014-06-26', 'cash_payment_date': '2014-06-25',
            'bonus_shares_per_share': '0.10000', 'cash_per_old_share_gross': '4.37400',
            'disclosed_initial_personal_cash_per_old_share': '4.15030',
            'tax_model_approved': False, 'evidence': [r for r in facts if r['source_id']=='cninfo:64148207']}
        old_shares = Decimal(original['inputs']['ending_issued_shares'])
        new_shares = old_shares * (1 + Decimal(event['bonus_shares_per_share']))
        if new_shares != Decimal('1141998000'):
            raise ValueError('Pre-2015 share bridge mismatch')
        bridge = {'pre_event_issued_shares': str(old_shares), 'post_event_issued_shares': str(new_shares),
                  'share_scale': '1.1', 'share_scale_effective_on': event['ex_date'],
                  'cash_distributed_gross_cny': str(old_shares * Decimal(event['cash_per_old_share_gross'])),
                  'cash_dividend_is_not_bonus_share_scale': True,
                  'daily_valuation_approved': False,
                  'remaining': ['Apply capital/distribution changes to the chosen valuation model, not just divide the old price',
                                'Verify intervening facts, capital changes and tax base; annual-only input is not quarterly TTM']}
        if digest(root / PRIOR) != PRIOR_HASH:
            raise ValueError('Prior eleven-year inputs changed')
        points = [original, *json.loads((root / PRIOR).read_text(encoding='utf-8'))]
        if select_original_vintage(points, '2015-01-05T15:00:00+08:00')[0]['source_id'] != 'cninfo:63720184':
            raise ValueError('Warmup not selected on first 2015 archived bar')
        if select_original_vintage(points, '2014-03-25T23:59:59+08:00'):
            raise ValueError('Warmup selected before conservative publication bound')
        write(out / 'annual-inputs.json', points)
        write(out / 'prehistory-distribution.json', event)
        write(out / 'share-bridge.json', bridge)
        write(out / 'result.json', {'status': 'original_warmup_and_share_event_reconciled',
              'source_bindings': bindings, 'dual_decoder_rows': len(facts),
              'strategy_backtest_complete': False, 'script_sha256': digest(Path(__file__)),
              'prior_inputs_sha256': PRIOR_HASH,
              'dependencies': {name: digest(root / name) for name in [
                  'scripts/build_moutai_annual_inputs.py', 'src/value_investment_agent/historical_asof.py']}})
        write(out / 'manifest.json', {'outputs': {p.name: digest(p) for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'output': str(out), 'annual_inputs_sha256': digest(out/'annual-inputs.json'),
                          'reports': len(points), 'share_bridge': bridge}, ensure_ascii=True))
    except Exception as exc:
        write(out/'failure.json', {'type':type(exc).__name__, 'error':str(exc)})
        raise


if __name__ == '__main__':
    main()

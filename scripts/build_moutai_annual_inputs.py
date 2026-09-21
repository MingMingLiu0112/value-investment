"""Reconcile eleven original annual vintages for the historical valuation bridge.

This produces dated research inputs, not current fair values or trade approval.
No network, production database, workbook, or server operations are performed.
"""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader
import pypdfium2 as pdfium

from value_investment_agent.historical_asof import publication_date_upper_bound, select_asof
from value_investment_agent.valuation import PROFILES


VERSION = 'moutai-original-annual-reference-v1'
# Reviewed original current-year cells. Never take a later comparative column.
# year, announcement, summary/EPS/balance pages, profit, equity, basic EPS, hash
REVIEWED = (
    (2014, '1200877315', 4, 5, 41, '15349804322.27', '53430402446.09', '13.44', '89145ef5bd12256c4c75c122b1c8d59846a912434f1abd0570f678bdb1a20f24'),
    (2015, '1202072290', 5, 5, 39, '15503090276.38', '63925978438.99', '12.34', '11a32c1e7f02a54fc2eea3c0d852af59ad37af9a2cbe91857cd93a6208a96d6c'),
    (2016, '1203301659', 5, 5, 43, '16718362734.16', '72894137783.25', '13.31', 'dd26d9e0017a938cb5e1aa0a830bab7502d0de1f85eb7c00abffb4888c8c20ad'),
    (2017, '1204526780', 4, 4, 46, '27079360255.74', '91451522828.96', '21.56', 'b66a4641e5f2313ed7964e5bef0026021ff2164459d0e0615f1b4385ba1a78e3'),
    (2018, '1205958206', 5, 5, 53, '35203625263.22', '112838564332.05', '28.02', '08728fc937836cfeed8e98aeda932da54c737efa6de4280ae001476c0e393dec'),
    (2019, '1207552562', 5, 5, 54, '41206471014.43', '136010349875.11', '32.80', '2a2b384ab09a7bc295fd2e33b999acdf4212340b0141031c991060dea2fad03d'),
    (2020, '1209495421', 5, 5, 51, '46697285429.81', '161322735087.56', '37.17', '464e4c179a18ebea566c5ddc5a4dbcfb83824227e9a10eb1ba0baa23c9d58d2c'),
    (2021, '1212755849', 5, 5, 52, '52460144378.16', '189539368797.29', '41.76', 'f65effdde58bcea99fd6bdb53f61b31d5c432e6dfb2661e5caf05156a433ea5a'),
    (2022, '1216281757', 5, 5, 56, '62716443738.27', '197506672396.00', '49.93', 'de394171306b9f2c7d79f54990de2a9e9c99feb54413150180179e24f0d83358'),
    (2023, '1219506510', 5, 5, 61, '74734071550.75', '215668571607.43', '59.49', '2125ff97a452ea79b0d784e2432f7d224b6aecc330b644b593477d69e22f4ed1'),
    (2024, '1222993920', 5, 5, 61, '86228146421.62', '233105984399.47', '68.64', '5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30'),
)


def compact(text):
    return re.sub(r'\s+', '', text)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Input path escapes project')
    return path


def reference_arithmetic(profit, equity, shares, eps):
    numbers = [Decimal(str(v)) for v in (profit, equity, shares, eps)]
    if any(not n.is_finite() or n <= 0 for n in numbers):
        raise ValueError('This positive-earnings reference needs explicit positive inputs')
    profit, equity, shares, eps = numbers
    if shares != shares.to_integral_value():
        raise ValueError('Actual integer shares required')
    with localcontext() as ctx:
        ctx.prec = 40
        reconstructed_eps = profit / shares
        if reconstructed_eps.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) != eps:
            raise ValueError('Disclosed EPS does not reconcile to ending-share basis')
        pe, pb = Decimal('18'), Decimal('4')
        bvps = equity / shares
        pe_component, pb_component = eps * pe, bvps * pb
        return {k: str(v) for k, v in {
            'profit_per_ending_issued_share': reconstructed_eps,
            'parent_equity_per_ending_issued_share': bvps,
            'pe_component': pe_component, 'pb_component': pb_component,
            'annual_reference_on_report_end_share_basis': (pe_component + pb_component) / 2,
        }.items()}


def select_original_vintage(points, decision_at):
    eligible = []
    for period in sorted({point['period_label'] for point in points}):
        selected = select_asof(points, symbol='600519', field_name='annual_reference_original',
                               period_label=period, decision_at=decision_at)
        if selected:
            eligible.append(selected)
    return eligible[-1] if eligible else []


def reconcile_report(root, row, bounds):
    year, aid, summary_page, eps_page, balance_page, profit, equity, eps, expected_hash = row
    packet_path = root / f'runtime/historical-candidates-v26-20260908/600519-{aid}.json'
    packet_raw = packet_path.read_bytes()
    packet = json.loads(packet_raw)
    source = contained(root, packet['evidence_file'])
    if packet['sha256'] != expected_hash or sha(source.read_bytes()) != expected_hash:
        raise ValueError(f'{year}: reviewed original hash mismatch')
    if packet['symbol'] != '600519' or packet['report_period_from_title'] != f'{year}-12-31':
        raise ValueError('Report identity mismatch')
    matches = [b for b in bounds['rows'] if b['symbol'] == '600519' and b['announcement_id'] == aid]
    if len(matches) != 1:
        raise ValueError('Publication bound missing or ambiguous')
    bound = matches[0]
    index_path = contained(root, bound['index_path'])
    index_raw = index_path.read_bytes()
    if sha(index_raw) != bound['index_hash']:
        raise ValueError('Publication index changed')
    entries = [entry for entry in json.loads(index_raw)['response']['announcements']
               if str(entry['announcementId']) == aid and entry['secCode'] == '600519']
    if len(entries) != 1:
        raise ValueError('Original announcement identity missing or ambiguous')
    entry = entries[0]
    url = 'https://static.cninfo.com.cn/' + entry['adjunctUrl']
    if not re.search(str(year) + r'年年度报告$', entry['announcementTitle']):
        raise ValueError('Announcement title does not match report year')
    if url != bound['source_url'] or bound['raw_file_hash'] != expected_hash:
        raise ValueError('Publication original binding mismatch')
    published = bound['published_date']
    stamped_date = datetime.fromtimestamp(entry['announcementTime'] / 1000,
                                         timezone(timedelta(hours=8))).date().isoformat()
    if published not in url or stamped_date != published:
        raise ValueError('Publication-date sources disagree')
    available = publication_date_upper_bound(published).isoformat()
    if available != bound['research_not_before']:
        raise ValueError('Publication upper bound mismatch')

    reader = PdfReader(source)
    evidence = []
    with pdfium.PdfDocument(source) as document:
        cache = {}

        def texts(number):
            if number not in cache:
                page = document[number - 1]
                textpage = page.get_textpage()
                try:
                    cache[number] = (compact(reader.pages[number - 1].extract_text()),
                                     compact(textpage.get_text_range()))
                finally:
                    textpage.close()
                    page.close()
            return cache[number]

        def require(number, literal, name):
            needle = compact(literal)
            if any(text.count(needle) != 1 for text in texts(number)):
                raise ValueError(f'{year}: {name} p{number} missing/ambiguous in a decoder')
            evidence.append({'field': name, 'page': number, 'literal': literal,
                             'decoders': ['pypdf', 'pdfium'], 'source_sha256': expected_hash})

        require(summary_page, '单位：元币种：人民币', 'summary_money_unit')
        require(summary_page, f'{year}年末', 'equity_current_year_header')
        require(summary_page, '归属于上市公司股东的净利润' + format(Decimal(profit), ',.2f'), 'parent_profit_summary')
        require(summary_page, '归属于上市公司股东的净资产' + format(Decimal(equity), ',.2f'), 'parent_equity_summary')
        require(eps_page, '基本每股收益（元／股）' + eps, 'disclosed_basic_eps')
        equity_label = '归属于母公司所有者权益' + ('（或股东权益）' if year >= 2019 else '') + '合计'
        require(balance_page, equity_label + format(Decimal(equity), ',.2f'), 'parent_equity_balance')
        # Locate the already retained income-statement row, then verify the raw PDF.
        candidates = [c for c in packet['candidates'] if c['field_name'] == 'net_income'
                      and c['page'] > summary_page and Decimal(c['value']) == Decimal(profit)]
        if len(candidates) != 1:
            raise ValueError('Unique consolidated income-statement cross-check absent')
        c = candidates[0]
        t1, t2 = texts(c['page'])
        pattern = r'归属于母公司(?:所有者|股东)的净利润(?:（净亏损以[“"][-－][”"]号填列）)?' + re.escape(format(Decimal(profit), ',.2f'))
        hits = [re.findall(pattern, text) for text in (t1, t2)]
        if len(hits[0]) != 1 or hits[0] != hits[1]:
            raise ValueError(f'{year}: consolidated profit cross-check failed')
        require(c['page'], hits[0][0], 'parent_profit_income_statement')
        shares_wan = '114,199.80' if year == 2014 else '125,619.78'
        shares = Decimal(shares_wan.replace(',', '')) * 10000
        if year <= 2021:
            share_page = 1 if year <= 2017 else 2
            phrase = f'以{year}年年末总股本{shares_wan}万股为基数'
        else:
            share_page = 74 if year == 2024 else 2
            phrase = f'截至{year}年12月31日，公司总股本为{shares_wan}万股'
        require(share_page, phrase, 'explicit_dated_issued_shares')
        if year == 2014:
            require(20, '本次利润分配方案实施完毕后，公司股份增加103,818,000股，变动后股份总数为1,141,998,000股', 'share_change_crosscheck')

    arithmetic = reference_arithmetic(profit, equity, shares, eps)
    return {'symbol': '600519', 'report_year': year, 'period_label': f'{year}-12-31',
            'source_id': 'cninfo:' + aid, 'source_url': url, 'source_path': str(source.relative_to(root)),
            'raw_file_hash': expected_hash, 'index_path': str(index_path.relative_to(root)),
            'index_hash': sha(index_raw), 'candidate_packet_hash': sha(packet_raw),
            'published_date': published, 'available_at': available, 'timestamp_precision': 'date',
            'publication_date_verified': True, 'availability_bound_verified': True,
            'availability_method': 'china_publication_date_upper_bound',
            'evidence_scope': 'Original current-year rows, same-source cross-statement and dual-decoder checks',
            'input_basis': 'Reported parent equity and profit; explicit year-end issued shares; no later comparatives',
            'inputs': {'parent_profit_cny': profit, 'parent_equity_cny': equity,
                       'ending_issued_shares': str(shares), 'reported_basic_eps': eps},
            'evidence': evidence, 'arithmetic': arithmetic,
            'trade_input_approved': False,
            'remaining_trade_dependencies': ['post-period share and distribution bridge',
                'intervening amendment/correction coverage', 'historical market and execution validation'],
            'value': arithmetic['annual_reference_on_report_end_share_basis'],
            'unit': 'CNY/share', 'field_name': 'annual_reference_original',
            'validation_status': 'verified', 'validation_scope': 'original_vintage_research_arithmetic_only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if PROFILES['600519'][:2] != (Decimal('18'), Decimal('4.00')):
        raise ValueError('Legacy reference profile changed; register a new experiment')
    started = datetime.now(timezone.utc)
    out = args.output or root / 'runtime/strategy-validation' / ('moutai-annual-inputs-' + started.strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    config = {'version': VERSION, 'registered_at': started.isoformat(), 'symbol': '600519',
              'report_years': list(range(2014, 2025)), 'target_pe': '18', 'target_pb': '4',
              'purpose': 'Original-vintage annual input bridge, not strategy economic validation',
              'formula': '(reported_basic_EPS * 18 + parent_equity / ending_issued_shares * 4) / 2',
              'price_basis': 'report_end_issued_shares_only_not_daily_tradable_basis',
              'production_strategy_changed': False, 'three_scenario_valuation_completed': False}
    (out / 'config.json').write_bytes(encoded(config))
    bounds_path = root / 'runtime/historical-publication-bounds-20260908.json'
    bounds_raw = bounds_path.read_bytes()
    reports = []
    try:
        for row in REVIEWED:
            report = reconcile_report(root, row, json.loads(bounds_raw))
            reports.append(report)
            print(json.dumps({'year': row[0], 'status': 'reconciled', 'available_at': report['available_at']}, ensure_ascii=True), flush=True)
        (out / 'annual-inputs.json').write_bytes(encoded(reports))
        # Exercise the actual as-of selector at both sides of every availability boundary.
        boundaries = []
        for r in reports:
            before = r['published_date'] + 'T23:59:59+08:00'
            old, new = select_original_vintage(reports, before), select_original_vintage(reports, r['available_at'])
            if any(p['source_id'] == r['source_id'] for p in old) or not new or new[0]['source_id'] != r['source_id']:
                raise ValueError('Original vintage selected before availability or missed at bound')
            boundaries.append({'at': r['available_at'], 'before_source': old[0]['source_id'] if old else None,
                               'at_source': new[0]['source_id']})
        (out / 'availability-replay.json').write_bytes(encoded(boundaries))
        lines = ['# Moutai Original Annual Input Bridge', '',
                 'Research-only original annual references. Not FCFF scenarios, daily trade values, or a completed backtest.', '',
                 '| Year | Available no earlier than (China) | Basic EPS | Parent equity / ending issued shares | Annual reference at period-end share basis | Original |',
                 '| --- | --- | ---: | ---: | ---: | --- |']
        for r in reports:
            a = r['arithmetic']
            lines.append(f"| {r['report_year']} | {r['available_at']} | {r['inputs']['reported_basic_eps']} | {Decimal(a['parent_equity_per_ending_issued_share']):.6f} | {Decimal(r['value']):.6f} | [PDF]({r['source_url']}) |")
        lines += ['', 'All 11 year-end counts are individually evidenced, not forward-filled. Empty treasury/preference rows were not converted to zero.',
                  'The 2023 report restates prior years; the original 2022 equity remains 197506672396.00 in its original vintage, not 197480041239.46.',
                  '2015 bonus shares and 2025 repurchases prevent using these period-end references unchanged against daily unadjusted prices.',
                  'Complete amendments, daily capital/distribution alignment, execution, tax, benchmark and trade ledger before performance admission.']
        (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        result = {'status': 'original_annual_inputs_reconciled', 'report_count': len(reports),
                  'availability_boundary_checks': len(boundaries), 'completed_backtest': False}
    except Exception as exc:
        (out / 'failure.json').write_bytes(encoded({'completed_reports': [r['report_year'] for r in reports],
                                                   'error_type': type(exc).__name__, 'error': str(exc)}))
        raise
    result.update({'run_id': out.name, 'script_sha256': sha(Path(__file__).read_bytes()),
                   'bounds_sha256': sha(bounds_raw), 'finished_at': datetime.now(timezone.utc).isoformat(),
                   'outputs': {p.name: sha(p.read_bytes()) for p in sorted(out.iterdir()) if p.is_file()},
                   'dependencies': {name: sha((root / 'src/value_investment_agent' / name).read_bytes())
                                    for name in ['historical_asof.py', 'valuation.py']}})
    (out / 'manifest.json').write_bytes(encoded(result))
    print(json.dumps({'output': str(out), **result}, ensure_ascii=True))


if __name__ == '__main__':
    main()

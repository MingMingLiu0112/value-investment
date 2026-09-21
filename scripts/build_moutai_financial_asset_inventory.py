"""Inventory consolidated financial carrying values without cash/value approval."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
from check_moutai_ttm_comparability import ROOT, sha, texts

ROWS = [
    ('cash', 53, '合计', '53518798979.08', '51690610946.50'),
    ('interbank', 26, '拆出资金2', '141084158124.01', '99096188059.75'),
    ('reverse_repo', 26, '买入返售金融资产7', '406491272.08', '8879708146.97'),
    ('current_debt_investments', 59, '一年内到期的债权投资', '1798106445.56', '26871114612.71'),
    ('loans', 26, '发放贷款和垫款11', '416287173.92', '1553536744.78'),
    ('debt_investments', 26, '债权投资12', '1106707304.24', '1113032405.66'),
    ('other_debt_investments', 26, '其他债权投资13', '2414885261.51', '3496539016.41'),
    ('other_financial_assets', 26, '其他非流动金融资产15', '3917510576.37', '4105141593.22'),
]


def main():
    source = ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(source) != '0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    pages = {p: texts(source, p) for p in {r[1] for r in ROWS}|{69}}
    for key, page, label, closing, opening in ROWS:
        phrase = label+format(D(closing), ',.2f')+format(D(opening), ',.2f')
        if any(phrase not in t for t in pages[page]):
            raise ValueError('Original row mismatch: '+key)
    for phrase in ['吸收存款25,426,316,668.1718,038,383,776.30',
                   '货币资金8,358,830,124.378,358,830,124.37其他存放中央银行法定存款准备金']:
        if any(phrase not in t for t in pages[69]):
            raise ValueError('Liability/reserve scope mismatch')
    totals = {}
    for name, index, deposits in [('closing', 3, '25426316668.17'), ('opening', 4, '18038383776.30')]:
        assets = sum(D(r[index]) for r in ROWS)
        net = assets-D(deposits)
        if F(net) != sum(F(r[index]) for r in ROWS)-F(deposits):
            raise ValueError('Independent sum failed')
        totals[name] = {'selected_financial_assets': str(assets), 'external_deposits': deposits,
                        'subtotal_after_external_deposits': str(net)}
    result = {'symbol': '600519', 'period_end': '2026-06-30', 'unit': 'CNY',
        'source_url': 'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF',
        'source_path': str(source.relative_to(ROOT)), 'source_sha256': sha(source),
        'rows': [{'id':k,'page':p,'label':l,'closing':c,'opening':o} for k,p,l,c,o in ROWS],
        'totals': totals,
        'restricted_cash_subset': '8358830124.37',
        'cash_excluding_disclosed_reserve_only': str(D(ROWS[0][3])-D('8358830124.37')),
        'approved_equity_bridge': None, 'distributable_cash': None,
        'constraints': [
            'Selected financial assets include restricted cash, credit assets and investment funds, not just freely available cash.',
            'Current debt investments and noncurrent debt investments are separate balance-sheet categories; do not add the note total again.',
            'Reserve is already in cash; no extra asset addition. It is not valueless and must not be deducted twice in financial subsidiary value.',
            'Trade receivable financing stays in operating working capital; it is not included here.',
            'Long-term equity investments are excluded pending operating/strategic classification, not assumed zero.',
            'Other finance liabilities, finance nonfinancial assets, taxes, industrial operating cash and minority claims remain outside this subtotal.',
            'A consolidated bridge may replace unavailable internal-deposit detail only after full scope reconciliation; never add internal deposits to this subtotal.',
            'If adding financial franchise premium, use 51 percent of fair equity minus matching book equity, not 51 percent of full fair equity on top of retained assets.',
            'No price, fair value, buy instruction or financial asset liquidity claim is approved.']}
    out = ROOT/'runtime/company-research'/('600519-financial-asset-inventory-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    (out/'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [source,Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')}, indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'totals':totals,'cash_excluding_reserve_only':result['cash_excluding_disclosed_reserve_only']}))


if __name__ == '__main__':
    main()

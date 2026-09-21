"""Bind royalty fee facts, contract terms and shareholder approval without inventing fee bases."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import texts
from replay_moutai_distributions import digest, write_json

ROOT=Path(__file__).resolve().parents[1]
CONTRACTS=ROOT/'runtime/company-research/600519-trademark-contracts-20260909T170248744753Z'
VOTE=ROOT/'runtime/company-research/600519-trademark-contracts-20260909T170448391980Z'
REPORT=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
REPORT_HASH='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6'


def require(path,page,*phrases):
    pair=texts(path,page)
    for phrase in phrases:
        if any(phrase not in text for text in pair):
            raise ValueError('Original phrase mismatch: '+phrase)


def main():
    sources={}
    for directory in (CONTRACTS,VOTE):
        for source in json.loads((directory/'manifest.json').read_text(encoding='utf-8'))['records']:
            if digest(ROOT/source['path'])!=source['sha256']:
                raise ValueError('Contract original changed')
            sources[source['source_id']]=source
    if digest(REPORT)!=REPORT_HASH:raise ValueError('Report changed')
    old=ROOT/sources['1216856277']['path']
    new=ROOT/sources['1225324463']['path']
    vote=ROOT/sources['1225366264']['path']
    require(old,3,'2024年1月1日至2026年12月31日','收费比例沿用往期协议中的1.5%','每半年支付一次')
    require(new,1,'本交易相关议案需提交公司股东会审议')
    require(new,3,'2027年1月1日至2029年12月31日','收费比例为1.5%','按季度支付',
            '当年公司本部使用许可商标酒类产品年销售收入',
            '与其从公司购买同等数量同类产品购买价年度总额的差额')
    require(vote,4,'《关于与关联方签订<商标许可协议>的议案》审议结果：通过',
            '164,264,02799.6256408,5700.2478208,7590.1266')
    require(REPORT,75,'单位：元币种：人民币','商标许可使用费1,265,631,280.621,276,884,815.84',
            '合计3,635,355,263.823,694,704,172.74')
    require(REPORT,94,'商标使用权1,265,631,280.621,276,884,815.84')
    require(REPORT,74,'茅台酒77,724,437,925.48','其他系列酒12,934,186,511.82')
    fee=D('1265631280.62');admin=D('3635355263.82')
    liquor=D('77724437925.48')+D('12934186511.82')
    naive=liquor*D('.015');difference=naive-fee
    if F(difference)!=F(liquor)*F('0.015')-F(fee):
        raise ValueError('Independent reconciliation failed')
    limits=[
        'Shareholder resolution approves the proposal; it is not proof of executed invoice amounts or exact future quarterly settlement dates.',
        'Contract covers licensed liquor sales and specified intra-chain margins, not total company revenue, financial interest income or automatically all liquor revenue.',
        'Reported expense divided by 1.5% is only an implied arithmetic base. VAT treatment, product coverage and settlement adjustments remain unverified; do not invent their explanations.',
        '2027 quarterly settlement changes timing, not the unchanged nominal 1.5% rate. Current period-end cashflow approximations do not model this payment schedule.',
        'These are related-party costs within reported administration, not finance-company overhead by default. Do not add the fee again to a forecast already containing full administration.',
        '2026 proposal and approval cannot be backdated into historical 2015-2025 decisions; historical versions and actual availability need separate selection.'
    ]
    out=ROOT/'runtime/company-research'/('600519-trademark-basis-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','source_bindings':sources,'report_source':{'path':str(REPORT.relative_to(ROOT)),'sha256':REPORT_HASH,'pages':[74,75,94]},
            'current_term':['2024-01-01','2026-12-31'],'approved_future_term':['2027-01-01','2029-12-31'],
            'contract_rate':'0.015','current_frequency':'semiannual','future_frequency':'quarterly',
            'future_proposal_shareholder_approved':True,'exact_future_payment_dates':None,
            'h1_2026_reported_fee':str(fee),'share_of_reported_admin':str(fee/admin),
            'h1_2026_total_liquor_revenue':str(liquor),'naive_all_liquor_fee':str(naive),
            'naive_fee_minus_reported_fee':str(difference),'implied_base_not_verified':str(fee/D('.015')),
            'verified_contract_fee_base':None,'limits':limits,'forecast_approved':False,'valuation_approved':False}
    write_json(out/'evidence.json',result)
    lines=['# 茅台商标费用预测依据','',
           f'2026上半年商标许可费{fee/D("1e8"):.4f}亿元，占管理费用{fee/admin:.2%}。费用附注与关联交易附注金额一致。',
           '', '2024-2026费率1.5%、半年支付；2027-2029同费率、季度支付的议案已由股东会通过。具体开票和季度结算日未验证。',
           '',f'将全部酒类收入直接乘1.5%得到{naive/D("1e8"):.4f}亿元，比已披露费用多{difference/D("1e8"):.4f}亿元。不能用这个简化公式替代合同口径，也不能把差额臆断为税额或未许可产品。',
           '', '## 建模影响','']+['- '+x for x in limits]
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),'outputs':{p.name:digest(p) for p in out.iterdir()}})
    print(json.dumps({'output':str(out),'fee_admin_fraction':str(fee/admin),'naive_difference_cny':str(difference),'future_proposal_approved':True},ensure_ascii=False))


if __name__=='__main__':main()

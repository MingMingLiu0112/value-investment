"""Reconcile deferred taxes through profit and OCI; isolate cash-tax inference."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
from check_moutai_ttm_comparability import ROOT,sha,texts


def main():
    pdf=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(pdf)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    required={68:['25,747,560,697.256,436,890,174.3126,409,876,604.846,602,469,151.22',
        '284,199,353.9371,049,838.47302,433,406.9975,608,351.79',
        '内部交易未实现利润22,337,795,505.475,584,448,876.3723,412,114,250.645,853,028,562.66'],
        78:['当期所得税费用15,255,249,283.3915,962,179,669.57','递延所得税费用149,839,327.12-170,860,351.99'],
        72:['11,181,136.47'],
        70:['企业所得税2,909,272,618.863,172,867,724.14'],
        60:['预缴所得税4,122,884.222,389,005.72']}
    for page,phrases in required.items():
        pair=texts(pdf,page)
        for phrase in phrases:
            if any(phrase not in t for t in pair):
                raise ValueError('Original tax row mismatch: '+str(page))
    da0,da1=D('6602469151.22'),D('6436890174.31')
    dl0,dl1=D('75608351.79'),D('71049838.47')
    net0,net1=da0-dl0,da1-dl1
    expense,oci=D('149839327.12'),D('11181136.47')
    if net0-net1!=expense+oci or F(net0)-F(net1)!=F(expense)+F(oci):
        raise ValueError('Net deferred tax profit/OCI bridge fails')
    current=D('15255249283.39')
    payable0,payable1=D('3172867724.14'),D('2909272618.86')
    prepay0,prepay1=D('2389005.72'),D('4122884.22')
    implied_cash=current+(payable0-prepay0)-(payable1-prepay1)
    independent=F(current)+F(payable0)-F(payable1)+F(prepay1)-F(prepay0)
    if F(implied_cash)!=independent:
        raise ValueError('Current tax reconciliation arithmetic mismatch')
    out=ROOT/'runtime/company-research'/('600519-tax-balance-bridge-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','period':'2026H1','unit':'CNY','source_sha256':sha(pdf),'page_checks':required,
        'net_deferred_tax_asset_opening':str(net0),'net_deferred_tax_asset_closing':str(net1),
        'net_deferred_tax_asset_decrease':str(net0-net1),'profit_deferred_tax_expense':str(expense),
        'oci_tax_effect':str(oci),'unexplained_net_deferred_tax_movement':'0.00',
        'internal_profit_deferred_asset':'5584448876.37',
        'internal_profit_share_of_deferred_assets':str(D('5584448876.37')/da1),
        'current_income_tax_expense':str(current),'opening_current_net_tax_liability':str(payable0-prepay0),
        'closing_current_net_tax_liability':str(payable1-prepay1),
        'implied_cash_tax_if_no_other_movements':str(implied_cash),'actual_cash_income_tax':None,
        'cash_tax_approved':False,'equity_tax_adjustment_approved':False,
        'model_constraints':[
            'Deferred tax asset is a timing asset, not freely distributable cash; add no full book value on top of cash-tax forecasts that already include reversals.',
            'Net DTA decrease reconciles exactly to profit deferred expense plus OCI tax effect; do not put OCI tax into operating income tax.',
            'Exact aggregate reconciliation does not identify item-level reversals, future realization dates or industrial-financial attribution.',
            'Cash-tax inference assumes no other transfers/noncash movements in current tax balances; not separately disclosed cash income-tax payment.',
            'Opening current tax liability must be settled consistently in dated cash forecasts or bridge, not both.',
            'Internal-profit tax reversal depends on external sale of inventories; do not assume immediate or perpetual extra tax savings.',
            'Future tax basis, taxable profit and reversals require a schedule; a 25 percent proxy is still only a conditional modelling assumption.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [pdf,Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'deferred_bridge_reconciled':True,'internal_profit_fraction':result['internal_profit_share_of_deferred_assets'],
        'implied_cash_tax_not_actual':str(implied_cash)}))


if __name__=='__main__':
    main()

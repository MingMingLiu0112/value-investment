"""Resolve material capital-prepayment and customer-advance presentation hazards."""
from datetime import datetime,timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import texts
from replay_moutai_distributions import digest,write_json

ROOT=Path(__file__).resolve().parents[1]
CAPITAL='runtime/strategy-validation/moutai-historical-capital-20260909T153535637673Z/evidence.json'
CAPITAL_HASH='9e1e49492b4877f47627c6a4575a77abe306d659880536bc213f3198a17923c8'
PROJECTS=[
    ('中铁二十二局集团有限公司','工程中标单位',['1965121588.37']),
    ('贵州省公路局','工程承建单位',['200000000.00','200000000.00']),
    ('重庆建工集团股份有限公司','工程中标单位',['53071818.21','158745595.81']),
    ('仁怀市土地收购储备中心','政府部门',['200000000.00']),
    ('贵州建工集团第四建筑工程有限公司','工程中标单位',['101274184.27','48620115.00']),
]


def require(pair,phrase):
    if any(phrase not in text for text in pair):raise ValueError('Original clause mismatch: '+phrase)


def main():
    if digest(ROOT/CAPITAL)!=CAPITAL_HASH:raise ValueError('Capital input changed')
    reports={r['report_year']:r for r in json.loads((ROOT/CAPITAL).read_text(encoding='utf-8'))['rows']}
    for year in (2013,2020):
        if digest(ROOT/reports[year]['source_path'])!=reports[year]['source_sha256']:raise ValueError('Original changed')
    pair=texts(ROOT/reports[2013]['source_path'],71)
    require(pair,'合计4,304,579,299.68100.003,872,870,407.89100.00')
    require(pair,'合计/2,926,833,301.66//')
    require(pair,'预付土地挂牌出让保证金')
    for name,relationship,amounts in PROJECTS:
        require(pair,name+relationship+format(D(amounts[0]),',.2f'))
        for amount in amounts:require(pair,format(D(amount),',.2f'))
    known=sum(D(v) for _,_,amounts in PROJECTS for v in amounts)
    if known!=D('2926833301.66') or F(known)!=sum(F(v) for _,_,amounts in PROJECTS for v in amounts):
        raise ValueError('Named counterparties do not sum to disclosed top-five total')
    total=D(reports[2013]['facts']['prepayments']['value_cny'])
    residual=total-known
    prepayment={'source':{k:reports[2013][k] for k in ('source_id','source_path','source_url','source_sha256','available_at')},
        'physical_page':71,'reported_prepaid_total_cny':str(total),'reviewed_counterparties':PROJECTS,
        'identified_project_and_land_related_cny':str(known),'fraction_of_prepaid_total':str(known/total),
        'unclassified_remainder_cny':str(residual),'approved_operating_prepaid_cny':None,
        'decision':'Do not put all prepayments into operating NWC. Project/land-related balances require capital-spending reconciliation; residual is unknown, not automatically operating.',
        'cashflow_classification_approved':False}
    source=ROOT/reports[2020]['source_path']
    header=texts(source,73)
    require(header,'2019年12月31日2020年1月1日调整数')
    pair=texts(source,75)
    for phrase in ['预收款项13,740,329,698.82-13,740,329,698.82',
        '合同负债12,256,986,053.8412,256,986,053.84',
        '其他流动负债1,483,343,644.981,483,343,644.98',
        '流动负债合计41,093,299,212.8441,093,299,212.84']:
        require(pair,phrase)
    policy=texts(source,76)
    require(policy,'公司将“预收款项”按新收入准则调整至“合同负债”、“其他流动负债”列报')
    require(policy,'对可比期间信息不予调整')
    old=D('13740329698.82'); contract=D('12256986053.84'); other=D('1483343644.98')
    if contract+other!=old or F(contract)+F(other)!=F(old):raise ValueError('Reclassification fails conservation')
    transition={'source':{k:reports[2020][k] for k in ('source_id','source_path','source_url','source_sha256','available_at')},
        'physical_pages':[73,74,75,76],'effective_date':'2020-01-01',
        'old_advance_receipts_cny':str(old),'new_contract_liabilities_cny':str(contract),
        'new_other_current_liabilities_cny':str(other),'combined_balance_change_cny':'0',
        'decision':'Presentation reclassification is not a cash inflow or outflow. Combine matched customer balances when comparing periods; do not add old advance receipts to replacement balances.',
        'availability_rule':'Use only when this original disclosure is available; effective date is not publication date. Earlier available evidence has not been established by this check.',
        'all_future_other_current_liabilities_are_customer_related':False}
    out=ROOT/'runtime/strategy-validation'/('moutai-capital-classification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    write_json(out/'evidence.json',{'symbol':'600519','prepayments_2013':prepayment,'revenue_standard_transition':transition,
        'industrial_nwc_approved':False,'historical_valuation_approved':False})
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),'evidence_sha256':digest(out/'evidence.json')})
    print(json.dumps({'output':str(out),'project_prepaid_cny':str(known),'prepaid_fraction':str(known/total),'reclassification_cashflow':'0'}))


if __name__=='__main__':main()

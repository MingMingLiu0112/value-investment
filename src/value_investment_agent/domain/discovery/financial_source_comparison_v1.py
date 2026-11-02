"""Compare provider observations without granting statutory-fact or debt-scope admission."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import re

VERSION='financial-source-comparison-v1'
ASSURANCE='E1_TWO_PROVIDER_COMPARISON_NOT_OFFICIAL_ADMISSION'
LABELS={
 'cash':'合并货币资金','net_margin':'合并净利率',
 'operating_cash_flow_to_net_income':'经营现金流／合并净利润',
 'debt_ratio':'资产负债率','revenue_yoy':'总营业收入同比',
 'net_income_yoy':'归母净利润同比','gross_margin':'毛利率','roe':'加权ROE',
}
ALIASES={'roe':'roe_weighted','revenue_yoy':'total_revenue_yoy','net_income_yoy':'parent_net_income_yoy'}
DEBT_LABELS={
 'short_term_borrowings':'短期借款','long_term_borrowings':'长期借款',
 'bonds_payable':'应付债券','lease_liabilities_noncurrent':'非流动租赁负债',
 'current_portion_long_term_debt':'一年内到期的非流动负债',
 'long_term_payables_noncurrent':'长期应付款','other_current_liabilities':'其他流动负债',
 'other_noncurrent_liabilities':'其他非流动负债','notes_payable':'应付票据',
 'other_payables':'其他应付款','financial_deposits_and_interbank':'吸收存款及同业存放',
 'central_bank_borrowings':'向中央银行借款','interbank_borrowings':'拆入资金','repurchase_financing':'卖出回购金融资产款',
}
DIRECT_FINANCING={'short_term_borrowings','long_term_borrowings','bonds_payable','lease_liabilities_noncurrent'}


def _number(v):
    try:
        n=Decimal(str(v))
        return n if not isinstance(v,bool) and n.is_finite() else None
    except (ValueError,InvalidOperation,TypeError):return None


def _refs(p):
    refs=(p.get('metadata') or {}).get('source_refs')
    binding=(p.get('metadata') or {}).get('source_binding')
    if isinstance(binding,dict):return [binding]
    return refs if isinstance(refs,list) and refs else [dict(path=p.get('source_path'),sha256=p.get('raw_file_hash'),source_url=p.get('source_url'),acquired_at=p.get('available_at'))]


def _valid(p,at):
    if not p or _number(p.get('value')) is None:return False
    if p.get('currency')!='CNY' or p.get('unit') not in {'CNY','percent'}:return False
    scope=(p.get('metadata') or {}).get('statement_scope')
    summary_ratio=scope=='PROVIDER_SUMMARY_NOT_STATUTORY_VERIFIED' and p.get('field_name') in {'roe_weighted','gross_margin','total_revenue_yoy','parent_net_income_yoy'}
    if scope not in {'consolidated','consolidated_provider_report','explicit_reported_ratio'} and not summary_ratio:return False
    if p.get('unit')=='CNY' and scope not in {'consolidated','consolidated_provider_report'}:return False
    if (p.get('metadata') or {}).get('evidence_quarantine'):return False
    try:
        for ref in _refs(p):
            clock=datetime.fromisoformat(ref['acquired_at'])
            if clock.utcoffset() is None or clock>at:return False
            if not ref.get('path') or not re.fullmatch('[a-f0-9]{64}',ref.get('sha256','')) or urlparse(ref.get('source_url','')).scheme!='https':return False
    except (KeyError,ValueError,TypeError):return False
    return True


def _provider(url):
    host=urlparse(url).hostname or ''
    if host=='eastmoney.com' or host.endswith('.eastmoney.com'):return 'eastmoney'
    if host=='sina.cn' or host.endswith('.sina.cn') or host.endswith('.sina.com.cn'):return 'sina'
    return None


def compare_observations(primary,secondary,*,symbol,period,evaluated_at):
    if evaluated_at.utcoffset() is None:raise ValueError('AWARE_COMPARISON_CUTOFF_REQUIRED')
    rows=[]
    def select(points,field):
        names={field,ALIASES.get(field,field)}
        return [p for p in points if p.get('symbol')==symbol and p.get('period_label')==period and p.get('field_name') in names]
    for field,label in LABELS.items():
        left=select(primary,field);right=select(secondary,field)
        unit='CNY' if field=='cash' else 'percent'
        usable=lambda ps:[p for p in ps if _valid(p,evaluated_at) and p['unit']==unit]
        l=usable(left);r=usable(right)
        lv={_number(p['value']) for p in l};rv={_number(p['value']) for p in r}
        status='ONE_SOURCE_ONLY';reason='已自动检查，另一来源尚无同期间、同口径可比值。';delta=None
        tolerance=Decimal('0.01') # CNY cents or one hundredth percentage point; never relative percent.
        if len(lv)>1 or len(rv)>1:
            status='CONFLICT';reason='同一来源组出现不同数值，不能择优或取平均。'
        elif lv and rv:
            lhosts={_provider(x['source_url']) for p in l for x in _refs(p)}
            rhosts={_provider(x['source_url']) for p in r for x in _refs(p)}
            if None in lhosts|rhosts or lhosts & rhosts:
                status='NOT_COMPARABLE';reason='两组资料来自相同供应商，不能记为双源核对。'
            else:
                delta=abs(next(iter(lv))-next(iter(rv)))
                status='MATCHED' if delta<=tolerance else 'CONFLICT'
                reason='两家供应商同口径数值在公开舍入精度内一致；仅为初筛核对，不是官方事实准入。' if status=='MATCHED' else '两家供应商数值超出舍入精度，保留差异，不自动选择或放行。'
        elif (left and not l) or (right and not r):
            status='NOT_COMPARABLE';reason='来源时间、单位、合并范围或有效值不满足可比条件。'
        rows.append(dict(field=field,label=label,status=status,primary_value=str(next(iter(lv))) if len(lv)==1 else None,
            secondary_value=str(next(iter(rv))) if len(rv)==1 else None,unit=unit,reason=reason,
            absolute_difference=str(delta) if delta is not None else None,tolerance=str(tolerance),
            primary_refs=[x for p in l for x in _refs(p)],secondary_refs=[x for p in r for x in _refs(p)]))
    return dict(version=VERSION,assurance=ASSURANCE,period=period,fields=rows,
        matched_count=sum(r['status']=='MATCHED' for r in rows),conflict_count=sum(r['status']=='CONFLICT' for r in rows),
        formal_admission=False,complete_debt_verified=False,action='no_order')


def debt_details(points,*,symbol,period,evaluated_at):
    rows=[];known=[]
    for field,label in DEBT_LABELS.items():
        selected=[p for p in points if p.get('symbol')==symbol and p.get('period_label')==period and p.get('field_name')==field]
        values={_number(p.get('value')) for p in selected if _valid(p,evaluated_at) and p.get('unit')=='CNY' and (p.get('metadata') or {}).get('statement_scope') in {'consolidated','consolidated_provider_report'}}
        values.discard(None)
        conflict=len(values)>1 or any(v<0 for v in values)
        value=next(iter(values)) if len(values)==1 and not conflict else None
        direct=field in DIRECT_FINANCING
        if value is not None and direct:known.append(value)
        rows.append(dict(field=field,label=label,value=str(value) if value is not None else None,unit='CNY',
            status='CONFLICT' if conflict else 'IDENTIFIED_FINANCING' if value is not None and direct else 'NEEDS_NOTE_CLASSIFICATION' if value is not None else 'NOT_REPORTED',
            reason='两源金额冲突，不能纳入已识别合计。' if conflict else '已取得借款、债券或非流动租赁账面金额。' if value is not None and direct else '已取得余额，须从附注拆出融资性质及当期到期部分，不能整项算作有息负债。' if value is not None else '来源未列明确金额，不按零处理。',
            source_refs=[x for p in selected for x in _refs(p)]))
    return dict(version=VERSION,components=rows,identified_total=str(sum(known)) if known else None,complete_debt_verified=False,
        reason='已识别金额不含尚待附注分类的一年内到期、应付款和其他融资；保留金融子公司资金核查，不以简单相加冒充完整有息负债。',action='no_order')


DEBT_KEYS={
 'SHORT_LOAN':'short_term_borrowings','LONG_LOAN':'long_term_borrowings','BOND_PAYABLE':'bonds_payable',
 'LEASE_LIAB':'lease_liabilities_noncurrent','NONCURRENT_LIAB_1YEAR':'current_portion_long_term_debt',
 'LONG_PAYABLE':'long_term_payables_noncurrent','OTHER_CURRENT_LIAB':'other_current_liabilities',
 'OTHER_NONCURRENT_LIAB':'other_noncurrent_liabilities','NOTE_PAYABLE':'notes_payable',
 'TOTAL_OTHER_PAYABLE':'other_payables','ACCEPT_DEPOSIT_INTERBANK':'financial_deposits_and_interbank',
 'LOAN_PBC':'central_bank_borrowings','BORROW_FUND':'interbank_borrowings','SELL_REPO_FINASSET':'repurchase_financing',
}


def debt_observations(balance,*,period):
    """Preserve every requested line, including explicit-null versus absent metadata."""
    points=[]
    for symbol,record in sorted(balance.items()):
        raw=record['raw'];ref=record['source_ref']
        for key,field in DEBT_KEYS.items():
            number=_number(raw.get(key))
            points.append(dict(symbol=symbol,field_name=field,value=str(number) if number is not None else None,
                unit='CNY',currency=raw.get('CURRENCY'),period_label=period,
                source_id=ref['sha256'],source_url=ref['source_url'],raw_file_hash=ref['sha256'],
                available_at=ref['acquired_at'],fetched_at=ref['acquired_at'],created_at=ref['acquired_at'],
                parser_version=VERSION,validation_status='unverified',metadata=dict(
                    statement_scope='consolidated_provider_report',source_refs=[ref],
                    source_line_item=key,source_cell_status='ABSENT' if key not in raw else 'NULL' if raw[key] is None else 'NUMERIC' if number is not None else 'INVALID',
                    automatic_cross_source_verification=False,complete_debt_verified=False,
                    formal_admission=False,assurance='E1_PROVIDER_OBSERVATION')))
    return points


def sina_observations(data):
    """Use explicitly scoped Sina rows; same-table ratios cancel unknown amount scale."""
    output=[]
    for symbol,company in sorted(data['symbols'].items()):
        period=company['period'];tables=company['statements']
        def row(table,field):
            rows=[r for r in (table or {}).get('rows',[]) if r.get('field')==field]
            if len(rows)!=1:return None
            return _number(rows[0].get('value'))
        def same_table_units(table,*fields):
            selected=[[r for r in table.get('rows',[]) if r.get('field')==f] for f in fields]
            if any(len(group)!=1 for group in selected):return False
            units={group[0].get('unit') for group in selected}
            return len(units)==1 and next(iter(units)) in {None,'CNY','元','万元','亿元','CNY 10K','CNY 100M'}
        def emit(field,value,unit,used,formula):
            if value is None:return
            if any(t.get('scope')!='consolidated' or t.get('currency')!='CNY' for t in used):return
            refs=[t['source_ref'] for t in used]
            at=max(datetime.fromisoformat(r['acquired_at']) for r in refs).isoformat()
            output.append(dict(symbol=symbol,field_name=field,value=str(value),unit=unit,currency='CNY',period_label=period,
                source_id=';'.join(r['sha256'] for r in refs),source_url=';'.join(r['source_url'] for r in refs),
                raw_file_hash=refs[0]['sha256'],available_at=at,fetched_at=at,created_at=at,parser_version=VERSION,
                validation_status='unverified',metadata=dict(statement_scope='consolidated',source_refs=refs,
                    derivation_formula=formula,automatic_cross_source_verification=False,complete_debt_verified=False,
                    formal_admission=False,assurance='E1_PROVIDER_OBSERVATION')))
        balance=tables.get('balance',{});income=tables.get('income',{});cashflow=tables.get('cashflow',{})
        assets=row(balance,'TOTASSET');liabilities=row(balance,'TOTLIAB')
        if assets is not None and assets>0 and liabilities is not None and same_table_units(balance,'TOTASSET','TOTLIAB'):
            emit('debt_ratio',liabilities/assets*100,'percent',[balance],'SAME_TABLE_TOTLIAB/TOTASSET*100_SCALE_CANCELLED')
        revenue=row(income,'BIZTOTINCO');net=row(income,'NETPROFIT')
        if revenue is not None and revenue>0 and net is not None and same_table_units(income,'BIZTOTINCO','NETPROFIT'):
            emit('net_margin',net/revenue*100,'percent',[income],'SAME_TABLE_NETPROFIT/BIZTOTINCO*100_SCALE_CANCELLED')
        sales=row(income,'BIZINCO');cost=row(income,'BIZCOST')
        if sales is not None and sales>0 and cost is not None and same_table_units(income,'BIZINCO','BIZCOST'):
            emit('gross_margin',(sales-cost)/sales*100,'percent',[income],'SAME_TABLE_(BIZINCO-BIZCOST)/BIZINCO*100_SCALE_CANCELLED')
        prior=(company.get('comparatives',{}).get(str(int(period[:4])-1)+'-12-31') or {}).get('income',{})
        for source,field in [('BIZTOTINCO','revenue_yoy'),('PARENETP','net_income_yoy')]:
            current=row(income,source);previous=row(prior,source)
            current_units={r.get('unit') for r in income.get('rows',[]) if r.get('field')==source}
            prior_units={r.get('unit') for r in prior.get('rows',[]) if r.get('field')==source}
            if current is not None and previous is not None and previous>0 and current_units==prior_units=={'CNY'}:
                emit(field,(current-previous)/previous*100,'percent',[income,prior],
                    'SAME_PROVIDER_SAME_FIELD_TWO_FY_('+source+'-PRIOR)/PRIOR*100_SCALE_CANCELLED')
        # Absolute amounts require an explicit unit declaration bound by the source adapter.
        def amounts(table,field):
            rows=[r for r in table.get('rows',[]) if r.get('field')==field]
            return row(table,field) if len(rows)==1 and rows[0].get('unit')=='CNY' else None
        cash=amounts(balance,'CURFDS')
        emit('cash',cash,'CNY',[balance],'EXPLICIT_CNY_GROUP_CASH')
        profit=amounts(income,'NETPROFIT');ocf=amounts(cashflow,'MANANETR')
        if profit is not None and profit>0 and ocf is not None:
            emit('operating_cash_flow_to_net_income',ocf/profit*100,'percent',[cashflow,income],'EXPLICIT_SAME_CNY_GROUP_OCF/NETPROFIT*100')
    return output

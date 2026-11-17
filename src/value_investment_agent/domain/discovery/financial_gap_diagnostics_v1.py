"""Distinguish missing source data from unverified observations; grant no quality gate."""
from decimal import Decimal, InvalidOperation

VERSION='financial-gap-diagnostics-v1'
FIELDS={
 'roe':('加权ROE','percent',('roe','roe_weighted')),
 'gross_margin':('毛利率','percent',('gross_margin',)),
 'net_margin':('合并净利率','percent',('net_margin',)),
 'operating_cash_flow_to_net_income':('经营现金流／合并净利润','percent',('operating_cash_flow_to_net_income',)),
 'cash':('合并货币资金','CNY',('cash',)),
 'interest_bearing_debt':('完整有息负债','CNY',('interest_bearing_debt',)),
 'debt_ratio':('资产负债率','percent',('debt_ratio',)),
 'revenue_yoy':('总营业收入同比','percent',('revenue_yoy','total_revenue_yoy')),
 'net_income_yoy':('归母净利润同比','percent',('net_income_yoy','parent_net_income_yoy')),
}
LABELS={'bank':'银行','insurer':'保险','broker':'证券公司','financial_group':'金融控股／多元金融'}
REQUIRED={
 'bank':['不良贷款率','拨备覆盖率','核心一级资本充足率','净息差'],
 'insurer':['核心偿付能力充足率','综合偿付能力充足率'],
 'broker':['风险覆盖率','资本杠杆率','流动性覆盖率','净稳定资金率'],
 'financial_group':['分部净资产','分部ROE','分部资本风险'],
}


def build_diagnostics(points, *, period, institution_kind=None, verified_fields=()):
    applicable=institution_kind not in LABELS
    applicability=dict(kind=institution_kind,label='普通企业初筛' if applicable else LABELS[institution_kind],
        reason='普通企业财务观察；不等于质量准入。' if applicable else
          '名称／现有行业映射初步识别为'+LABELS[institution_kind]+'；其负债和现金具有不同经济含义，不能套普通企业评分。不是公司差，也不是没有财报。',
        required_metrics=REQUIRED.get(institution_kind,[]),provisional=not applicable)
    rows=[]
    for field,(label,unit,aliases) in FIELDS.items():
        selected=[p for p in points if p.get('field_name') in aliases and p.get('period_label')==period]
        unsuitable=[p for p in selected if (p.get('metadata') or {}).get('ratio_not_meaningful') is True]
        values=[];issues=[]
        for p in selected:
            if p in unsuitable:continue
            try:
                v=Decimal(str(p['value']))
                if isinstance(p['value'],bool) or not v.is_finite() or p.get('unit')!=unit:raise ValueError()
                if field in {'cash','interest_bearing_debt'} and v<0:raise ValueError()
                values.append((v,p))
            except (InvalidOperation,ValueError,TypeError,KeyError):issues.append('来源数值或单位不符合合同')
        distinct={v for v,_ in values}
        partial=any((p.get('metadata') or {}).get('complete_debt_verified') is not True for _,p in values) if field=='interest_bearing_debt' else False
        status=('CONFLICT' if issues or len(distinct)>1 else 'PARTIAL_SCOPE' if unsuitable else 'MISSING' if not distinct else
                'PARTIAL_SCOPE' if partial else 'VERIFIED' if field in verified_fields else 'AVAILABLE_PENDING_VERIFICATION')
        value=str(next(iter(distinct))) if len(distinct)==1 and not issues else None
        if status=='MISSING':
            reason='尚未取得该期间、该口径的可用公开数值。'
            if field=='interest_bearing_debt':reason='缺借款、债券、租赁及其他融资负债的完整明细；不能用总负债或空行代替。'
        elif status=='PARTIAL_SCOPE':reason=('经营现金流与合并净利润均已取得，但合并净利润非正，不能用该比率判断现金转换质量。' if unsuitable else '已识别负债金额仅为部分口径，不能当作完整有息债务。')
        elif status=='CONFLICT':reason='同期间来源值或单位冲突，保留差异，不能任选一个。'
        elif status=='VERIFIED':reason='按既有核验合同已通过；不代表整家公司质量通过。'
        else:reason='公开原值或明确公式已取得，但尚未通过正式财务质量核验。'
        rows.append(dict(field=field,label=label,status=status,value=value,unit=unit,reason=reason,
            source_refs=[{k:p.get(k) for k in ['source_id','source_url','raw_file_hash','available_at','parser_version']} for p in selected],
            derivations=[dict(formula=(p.get('metadata') or {}).get('derivation_formula'),source_refs=(p.get('metadata') or {}).get('source_refs',[])) for p in selected if (p.get('metadata') or {}).get('source_refs')],
            statement_scope='consolidated_or_explicit_reported_ratio',period=period))
    data=dict(version=VERSION,period=period,required_count=len(rows),
        available_count=sum(r['value'] is not None for r in rows),
        verified_count=sum(r['status']=='VERIFIED' for r in rows),
        missing_count=sum(r['status']=='MISSING' for r in rows),
        partial_count=sum(r['status']=='PARTIAL_SCOPE' for r in rows),
        conflict_count=sum(r['status']=='CONFLICT' for r in rows),fields=rows,
        formal_admission=False,action='no_order')
    return data,applicability


def statement_observations(statements, *, period):
    """Amount-based, same-period E1 observations; no per-share proxy or approval."""
    output=[]
    symbols=set().union(*(set(statements.get(k,{}) or {}) for k in ['balance','income','cashflow']))
    def value(row,key):
        v=(row or {}).get('raw',{}).get(key)
        try:
            d=Decimal(str(v))
            return d if not isinstance(v,bool) and d.is_finite() else None
        except (InvalidOperation,ValueError,TypeError):return None
    def emit(symbol,field,v,unit,records,formula,not_meaningful=False):
        refs=[r['source_ref'] for r in records if r]
        if (v is None and not not_meaningful) or not refs:return
        times=[r.get('acquired_at') or r.get('fetched_at') for r in refs]
        if not all(times):raise ValueError('STATEMENT_OBSERVATION_AVAILABILITY_REQUIRED')
        point=dict(symbol=symbol,field_name=field,value=str(v) if v is not None else None,unit=unit,currency='CNY',
            period_label=period,source_id=';'.join(r['sha256'] for r in refs),
            source_url=';'.join(r['source_url'] for r in refs),raw_file_hash=refs[0]['sha256'],
            available_at=max(times),fetched_at=max(times),created_at=max(times),
            parser_version=VERSION,validation_status='unverified',metadata=dict(
                assurance='E1_PROVIDER_OBSERVATION',formal_admission=False,
                automatic_cross_source_verification=False,statement_scope='consolidated_provider_report',
                derivation_formula=formula,source_refs=refs,complete_debt_verified=False,ratio_not_meaningful=not_meaningful))
        output.append(point)
    for symbol in sorted(symbols):
        b=statements.get('balance',{}).get(symbol)
        i=statements.get('income',{}).get(symbol)
        c=statements.get('cashflow',{}).get(symbol)
        cash=value(b,'MONETARYFUNDS')
        emit(symbol,'cash',cash,'CNY',[b],'REPORTED_GROUP_MONETARYFUNDS_NOT_PARENT_DISTRIBUTABLE_CASH')
        assets=value(b,'TOTAL_ASSETS');liabilities=value(b,'TOTAL_LIABILITIES')
        if assets is not None and assets>0 and liabilities is not None:
            emit(symbol,'debt_ratio',liabilities/assets*100,'percent',[b],'TOTAL_LIABILITIES/TOTAL_ASSETS*100')
        income=value(i,'TOTAL_OPERATE_INCOME');profit=value(i,'NETPROFIT')
        # This provider's income summary reports group PBT and tax, not group net profit.
        # Never substitute PARENT_NETPROFIT as the denominator of a group cash conversion.
        if profit is None:
            pretax=value(i,'TOTAL_PROFIT');tax=value(i,'INCOME_TAX')
            if pretax is not None and tax is not None:profit=pretax-tax
        if income is not None and income>0 and profit is not None:
            emit(symbol,'net_margin',profit/income*100,'percent',[i],'(GROUP_TOTAL_PROFIT-INCOME_TAX)/TOTAL_OPERATE_INCOME*100' if value(i,'NETPROFIT') is None else 'GROUP_NETPROFIT/TOTAL_OPERATE_INCOME*100')
        operating_cash=value(c,'NETCASH_OPERATE')
        if operating_cash is not None and profit is not None and profit>0:
            emit(symbol,'operating_cash_flow_to_net_income',operating_cash/profit*100,'percent',[c,i],
                 'GROUP_NETCASH_OPERATE/(GROUP_TOTAL_PROFIT-INCOME_TAX)*100' if value(i,'NETPROFIT') is None else 'GROUP_NETCASH_OPERATE/GROUP_NETPROFIT*100')
        if operating_cash is not None and profit is not None and profit<=0:
            emit(symbol,'operating_cash_flow_to_net_income',None,'percent',[c,i],
                 'GROUP_PROFIT_NON_POSITIVE_RATIO_NOT_MEANINGFUL',not_meaningful=True)
        emit(symbol,'revenue_yoy',value(i,'TOTAL_OPERATE_INCOME_YOY'),'percent',[i],'REPORTED_TOTAL_OPERATE_INCOME_YOY')
        debt_values=[value(b,key) for key in ['SHORT_LOAN','LONG_LOAN','BOND_PAYABLE','LEASE_LIAB','NONCURRENT_LIAB_1YEAR']]
        identified=[v for v in debt_values if v is not None]
        if identified:
            emit(symbol,'interest_bearing_debt',sum(identified),'CNY',[b],
                 'IDENTIFIED_BORROWING_AND_LEASE_LINES_ONLY_NOT_COMPLETE_DEBT')
    return output

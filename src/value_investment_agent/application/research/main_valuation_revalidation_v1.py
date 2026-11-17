"""Cold-replayed dated working candidate; no current price or economic approval."""
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import re

from .explicit_cash_research_runner_v1 import run_explicit_cash_research
from .agent_review.operating_task_v2 import LiveOperatingTaskService
from ...domain.research import period_earnings_assembly_v1 as periods
from ...domain.research.parent_obligation_pressure_v2 import evaluate_parent_obligation_pressure
from ...domain.valuation.operating_profit_cash_path_v1 import compile_operating_profit_cash_path, PROFIT_BASIS
from ...domain.valuation.joint_capital_cash_path_v4 import SCOPE
from ...infrastructure.filings import first_research_fact_replay_v1 as native
from ...infrastructure.filings import quarterly_operating_facts_v1 as quarterly
from ...infrastructure.filings import parent_obligation_sources_v2 as parent_sources
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.native_capital_observation_v1 import _compact, _raw_excerpt

VERSION='main-valuation-revalidation-v1'
REGISTRY='config/current-operating-research-sources-v1.json'
SUCCESS='CONDITIONAL_RESEARCH_CANDIDATE_PENDING_ECONOMIC_REVIEW'


def _json(value):
    if is_dataclass(value):return _json(asdict(value))
    if isinstance(value,(Decimal,date,datetime)):return str(value)
    if isinstance(value,dict):return {str(k):_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_json(v) for v in value]
    return value


def implementation_fingerprint_basis():
    # NEW source-only contract: LF index and CRLF checkouts have one identity.
    # No pin is added. PDF/financial evidence hashes remain exact raw bytes;
    # local source raw hashes belong only in the execution receipt.
    return dict(default='SOURCE_CRLF_TO_LF_SHA256_V1', overrides={})


def _implementation_source_hash(module):
    raw=Path(module.__file__).read_bytes().replace(b'\r\n',b'\n')
    return hashlib.sha256(raw).hexdigest()


def implementation_fingerprints():
    from . import explicit_cash_research_runner_v1
    from ...domain.valuation import operating_profit_cash_path_v1, joint_capital_cash_path_v4
    from ...domain.research import parent_obligation_pressure_v2, liability_settlement_schedule_v1
    from ...valuation_models import residual_income_path_v4
    from ...domain.valuation import signed_parent_profit
    from ...domain.decision import value_price_policy
    from ...infrastructure.filings import native_capital_observation_v1
    from ... import research_application, research_input, m1_valuation_package_builder
    from . import v4_input_adapter, v4_valuation_router
    from ..product import source_bound_inputs
    modules=(explicit_cash_research_runner_v1,periods,native,quarterly,parent_sources,
        operating_profit_cash_path_v1,joint_capital_cash_path_v4,parent_obligation_pressure_v2,liability_settlement_schedule_v1,residual_income_path_v4,
        signed_parent_profit,value_price_policy,native_capital_observation_v1,research_application,research_input,
        m1_valuation_package_builder,v4_input_adapter,v4_valuation_router,source_bound_inputs)
    return {**{m.__name__:_implementation_source_hash(m) for m in modules},
        __name__:hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}


def _bound(root,ref,closure):
    path,raw=native._raw(root,ref)
    closure.append((path,ref['sha256']))
    return raw


def _packet(root,ref,closure):return json.loads(_bound(root,ref,closure))


def _stamp(value,now):return native._time(value,now)


def _base(symbol):
    return dict(schema_version=VERSION,symbol=symbol,action='no_order',formal_eligibility=False,
        current_comparable=False,quantity=None,main_range_adopted=False,condition_price=None,
        personal_quantity=None,formal_fact_count=0,approval_changed=False,policy_not_fully_modelled=True)


def read_main_valuation_revalidation(*,root,symbol,now):
    result=_base(symbol)
    try:
        root=Path(root).resolve()
        if not isinstance(symbol,str) or not re.fullmatch('[0-9]{6}',symbol):raise ValueError('INVALID_SYMBOL')
        if now.utcoffset() is None:raise ValueError('AWARE_REVALIDATION_CLOCK_REQUIRED')
        path=root/REGISTRY
        if not path.exists():return dict(result,status='NOT_STARTED',reason='MAIN_REVALIDATION_NOT_REGISTERED')
        registry=json.loads(path.read_bytes())
        if registry.get('schema_version')!='current-operating-research-sources-v1' or registry.get('action')!='no_order':
            raise ValueError('MAIN_REVALIDATION_REGISTRY_INVALID')
        ref=registry['cases'].get(symbol,{}).get('main_revalidation')
        if ref is None:return dict(result,status='NOT_STARTED',reason='MAIN_REVALIDATION_NOT_REGISTERED')
        closure=[]
        spec=_packet(root,ref,closure)
        if spec['schema_version']!=VERSION or spec['symbol']!=symbol or spec['action']!='no_order':
            raise ValueError('MAIN_REVALIDATION_SPEC_IDENTITY_INVALID')
        if spec.get('implementation_fingerprint_basis')!=implementation_fingerprint_basis():raise ValueError('MAIN_REVALIDATION_FINGERPRINT_BASIS_INVALID')
        if spec['implementation_sha256']!=implementation_fingerprints():raise ValueError('MAIN_REVALIDATION_IMPLEMENTATION_CHANGED')
        made=_stamp(spec['generated_at'],now)
        result.update(_consume(root,spec,ref,made,now,closure))
        if any(hashlib.sha256(p.read_bytes()).hexdigest()!=h for p,h in closure):raise ValueError('REVALIDATION_SOURCE_CHANGED_DURING_REPLAY')
        if spec.get('implementation_fingerprint_basis')!=implementation_fingerprint_basis():raise ValueError('MAIN_REVALIDATION_FINGERPRINT_BASIS_INVALID')
        if spec['implementation_sha256']!=implementation_fingerprints():raise ValueError('MAIN_REVALIDATION_IMPLEMENTATION_CHANGED')
        result=_json(result)
        json.dumps(result,allow_nan=False)
        return result
    except (ValueError,OSError,KeyError,TypeError,ArithmeticError) as error:
        return dict(_base(symbol),status='UNASSESSABLE',reason=str(error),error_type=type(error).__name__)


def _consume(root,spec,ref,made,now,closure):
    b=spec['bindings']
    packets={key:_packet(root,value,closure) for key,value in b.items() if key!='quarterly_pdf'}
    quarter_path=native._inside(root,b['quarterly_pdf']['path'])
    _bound(root,b['quarterly_pdf'],closure)
    source_closure=packets['source_closure']
    if source_closure['symbol']!=spec['symbol']:raise ValueError('SOURCE_CLOSURE_ISSUER_MISMATCH')
    _stamp(source_closure['generated_at'],made)
    for source in source_closure['sources']:
        if source.get('actual_available_at'):_stamp(source['actual_available_at'],made)
        _bound(root,source,closure)
    actual=native.replay_first_research_facts(root=root,binding=b['native_facts'],now=made)
    if actual['symbol']!=spec['symbol']:raise ValueError('NATIVE_ISSUER_MISMATCH')
    template=packets['template_package']
    if template['symbol']!=spec['symbol']:raise ValueError('TEMPLATE_ISSUER_MISMATCH')
    service=LiveOperatingTaskService(root)
    ids=[x for x in Path(b['task_state']['path']).parts if x.startswith('rt-')]
    if len(ids)!=1:raise ValueError('EXACT_DRIVER_TASK_REQUIRED')
    task_spec,state,pin=service._load(ids[0],recover=False)
    if pin!=b['task_state']:raise ValueError('DRIVER_TASK_VERSION_CHANGED')
    task=service._view(task_spec,state,pin,made)
    if task['status']!='SUCCEEDED' or task['symbol']!=spec['symbol'] or task['scope']!='LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED':
        raise ValueError('VERIFIED_SUCCEEDED_DRIVER_TASK_REQUIRED:'+repr((task.get('status'),task.get('error_code'),task.get('scope'),task.get('symbol'),spec['symbol'])))
    for role_pin in task['roles'].values():_bound(root,role_pin,closure)
    qs=[s for s in packets['quarterly_receipt']['records'] if s['path']==b['quarterly_pdf']['path'] and s['sha256']==b['quarterly_pdf']['sha256']]
    if len(qs)!=1:raise ValueError('QUARTER_SOURCE_RECEIPT_MISMATCH')
    qsource=qs[0]
    _verify_quarter_receipt(qsource,spec,actual,made,packets['quarterly_receipt'])
    qpages=extract_pages(quarter_path)
    if _compact(actual['issuer_name']) not in _compact(qpages[0]):raise ValueError('QUARTER_ISSUER_NAME_MISMATCH')
    hsource=[source for source in actual['sources'] if source['report_period']==spec['financial_basis']]
    if len(hsource)!=1:raise ValueError('ONE_H1_CURRENCY_ORIGINAL_REQUIRED')
    hpages=extract_pages(native._inside(root,hsource[0]['path']))
    currency_text=_compact(hpages[55])
    currency_match=re.search(r'4、记账本位币以人民币为记账本位币。',currency_text)
    if currency_match is None:raise ValueError('EXACT_REPORTING_CURRENCY_SENTENCE_REQUIRED')
    currency_basis=dict(currency='CNY',evidence_refs=[dict(id=hsource[0]['id'],path=hsource[0]['path'],
        sha256=hsource[0]['sha256'],physical_page=56,excerpt=_raw_excerpt(hpages[55],currency_match[0]))])
    q=quarterly.parse_quarterly_operating_facts(qpages,symbol=spec['symbol'],currency_basis=currency_basis)
    def facts(period):
        selected=[row for row in actual['facts'] if row['period_end']==period]
        result={}
        for field in (*periods.COMPONENT_FIELDS,'tax','parent_profit'):
            rows=[r for r in selected if r['field']==field]
            if len(rows)!=1:raise ValueError('EXACT_PERIOD_FACT_REQUIRED:'+period+':'+field)
            result[field]=Decimal(rows[0]['value'])
        return result
    h1=facts(spec['financial_basis'])
    fy=facts(spec['prior_fiscal_end'])
    nine={k:Decimal(v['current']) for k,v in q['fields'].items()}
    prior9={k:Decimal(v['comparative']) for k,v in q['fields'].items()}
    year=int(spec['financial_basis'][:4])
    if (q['period_end']!=f'{year}-09-30' or spec['financial_basis']!=f'{year}-06-30'
            or spec['prior_fiscal_end']!=f'{year-1}-12-31'):raise ValueError('ACTUAL_PERIOD_CHAIN_MISMATCH')
    def segment(values,start,end,kind,refs,assumptions):
        return dict(period_start=start,period_end=end,kind=kind,currency='CNY',scope='consolidated',
            group_pbt_cny=str(values['pre_tax_profit']),income_tax_cny=str(values['tax']),
            signed_nci_cny=str(values['pre_tax_profit']-values['tax']-values['parent_profit']),
            parent_profit_cny=str(values['parent_profit']),source_refs=refs,assumption_refs=assumptions,
            asof=made.isoformat())
    q3=periods.subtract_same_year_ytd(segment(nine,f'{year}-01-01',f'{year}-09-30','REPORTED_FACT',[b['quarterly_pdf']],[]),
        segment(h1,f'{year}-01-01',f'{year}-06-30','DERIVED_FACT',[b['native_facts']],[]),asof=made)
    prior4={field:fy[field]-prior9[field] for field in (*periods.COMPONENT_FIELDS,'tax','parent_profit')}
    da=_cold_da(root,packets['da_wc'],actual,made)
    snapshot=parent_sources.load_parent_obligation_snapshot(root=root,native_path=b['native_facts']['path'],cutoff=made)
    floor=parent_sources.load_frozen_cash_floor_assumption(root=root,relative_path=b['floor_assumption']['path'],cutoff=made)
    constraints=parent_sources.load_official_parent_constraint_disclosures(bundle_root=root/spec['constraint_bundle'],cutoff=made)
    from ...domain.research.liability_settlement_schedule_v1 import compile_liability_settlements
    if type(spec['hypotheses']['liability_payment_year']) is not int or spec['hypotheses']['liability_payment_year']!=1:
        raise ValueError('EXPLICIT_YEAR1_BOOK_SETTLEMENT_REQUIRED')
    obligations=[dict(obligation_id=field,opening_balance_cny=snapshot['balances'][field],payment_year=spec['hypotheses']['liability_payment_year'],
        source_refs=[b['native_facts'],snapshot['facts'][field]])
        for field in ('short_term_borrowings','current_noncurrent_liabilities','dividend_payable')]
    settlement=compile_liability_settlements(obligations=obligations,years=10)
    compiled,assemblies,pressures={},{},{}
    scenario_failures={}
    hypothesis=spec['hypotheses']
    for name in ('bear','base','bull'):
        own=hypothesis['scenarios'][name]
        if own['point_selection']!='margin_lower':raise ValueError('UNSUPPORTED_POINT_SELECTION')
        point=task['operating_driver_bridge']['paths'][name]['extrema']['margin_lower']['drivers']
        forecasts={}
        for label,base,start,end in (('q4_forecast',prior4,f'{year}-10-01',f'{year}-12-31'),
                ('h1_next_forecast',h1,f'{year+1}-01-01',f'{year+1}-06-30')):
            baseline_start=f'{year-1}-10-01' if label=='q4_forecast' else f'{year}-01-01'
            baseline_end=spec['prior_fiscal_end'] if label=='q4_forecast' else spec['financial_basis']
            components=[dict(field=k,value=str(base[k]),period_start=baseline_start,period_end=baseline_end,
                kind='DERIVED_FACT' if label=='q4_forecast' else 'REPORTED_FACT',currency='CNY',scope='consolidated',
                source_refs=[b['native_facts'],b['quarterly_pdf']],assumption_refs=[]) for k in periods.COMPONENT_FIELDS]
            drivers=dict(point,source_refs=[b['task_state']],assumption_refs=[ref])
            if label=='q4_forecast':drivers['other_pretax_cny']='0'
            projected=periods.project_operating_period(components,drivers,dict(period_start=start,period_end=end,asof=made.isoformat()))
            pbt=Decimal(projected['group_pbt_cny']).quantize(Decimal('.01'))
            if not own['tax_rationale'] or not own['nci_rationale'] or own['negative_profit_tax_benefit'] is not False:
                raise ValueError('EXPLICIT_TAX_NCI_RATIONALE_AND_NO_AUTOMATIC_TAX_BENEFIT_REQUIRED')
            rate,minority=Decimal(own['tax_rate']),Decimal(own['signed_nci_ratio'])
            if not rate.is_finite() or not minority.is_finite() or not 0<=rate<1 or not -1<=minority<=1:
                raise ValueError('TAX_NCI_POINT_OUTSIDE_SUPPORTED_BOUNDS')
            tax=(max(pbt,Decimal(0))*rate).quantize(Decimal('.01'))
            nci=(max(pbt-tax,Decimal(0))*minority).quantize(Decimal('.01'))
            forecasts[label]=dict(period_start=start,period_end=end,kind='FORECAST_ASSUMPTION',currency='CNY',scope='consolidated',
                group_pbt_cny=str(pbt),income_tax_cny=str(tax),signed_nci_cny=str(nci),source_refs=projected['source_refs'],
                assumption_refs=[ref],projection=projected)
        chosen={k:{field:value for field,value in row.items() if field!='projection'} for k,row in forecasts.items()}
        first=periods.assemble_annual_earnings(year=1,period_start=f'{year}-07-01',period_end=f'{year+1}-06-30',
            segments=[q3,chosen['q4_forecast'],chosen['h1_next_forecast']],asof=made)
        pressure=evaluate_parent_obligation_pressure(snapshot=snapshot,scenario=dict(scenario_id=name,
            reserve_other_current=own['reserve_other_current'],reserve_noncurrent_borrowings=own['reserve_noncurrent_borrowings'],
            cash_floor_cny=floor['value'],floor_includes_debt=False,future_investment_reserve_cny='0',hypothetical_additional_distribution_cny='0'))
        permanent_floor=Decimal(snapshot['balances']['cash_equivalents'])-Decimal(pressure['conditional_cash_residual_cny'])
        # Scheduled book balances remain in gross opening cash and are paid
        # once by the existing commitment mechanism, not reserved a second time.
        effective_floor=permanent_floor-Decimal(settlement['initial_outstanding_cny'])
        opening=dict(as_of=spec['financial_basis'],scope=SCOPE,currency='CNY',
            book_equity_cny=template['facts']['operating_inputs']['start_book_equity'],
            cash_cny=snapshot['balances']['cash_equivalents'],unremitted_cny='0',distribution_capacity_cny=snapshot['balances']['retained_profit'],
            operating_capital_cny=str(Decimal(template['facts']['operating_inputs']['start_book_equity'])-Decimal(snapshot['balances']['cash_equivalents'])),
            productive_capital_cny='0',cash_floor_cny=str(effective_floor),ordinary_shares=template['facts']['operating_inputs']['ordinary_shares'])
        model_years,annual=[],[]
        for i in range(1,11):
            if i==1:assembled=first
            else:
                held=dict(chosen['h1_next_forecast'],period_start=f'{year+i-1}-07-01',period_end=f'{year+i}-06-30',
                    group_pbt_cny=first['annual_row']['group_pbt_cny'],income_tax_cny=first['annual_row']['tax_assumption']['value'],
                    signed_nci_cny=first['annual_row']['signed_nci_cny'],source_refs=[b['task_state']],assumption_refs=[ref])
                assembled=periods.assemble_annual_earnings(year=i,period_start=held['period_start'],period_end=held['period_end'],segments=[held],asof=made)
            row=deepcopy(assembled['annual_row'])
            row['cash_policy']=dict(target_payout_ratio=own['target_payout_ratio'],accessible_profit_ratio=own['accessible_profit_ratio'],
                reserve_ratio=own['reserve_ratio'],net_maintenance_cash_cny=str(da['net_maintenance_ex_rou_proxy_cny']),
                operating_wc_cash_cny=str(da['wc_ex_payables_proxy_cny']) if i==1 else '0',
                commitment_cash_cny=settlement['rows'][i-1]['payment_cny'],scope=SCOPE,currency='CNY')
            annual.append(row);model_years.append(assembled)
        terminal=deepcopy(own['terminal_policy'])
        terminal.update(net_maintenance_cash_cny=str(da['net_maintenance_ex_rou_proxy_cny']),operating_wc_cash_cny='0',commitment_cash_cny='0')
        try:
            compiled[name]=compile_operating_profit_cash_path(opening_state=opening,annual_rows=annual,
                capital_policy=dict(operating_allocation='0',new_operating_return='0',new_liquidity_return='0'),
                terminal_policy=terminal,cost_of_equity=own['cost_of_equity'],profit_basis=PROFIT_BASIS)
            for index,row in enumerate(compiled[name]['rows']):
                row['cash_use_breakdown']=dict(economic_capital_cash_cny='0',
                    liability_settlement_cny=settlement['rows'][index]['payment_cny'],
                    classification='NONPRODUCTIVE_LIABILITY_SETTLEMENT',scope='COMMITMENT_COMPONENTS_ONLY',
                    commitment_total_cny=settlement['rows'][index]['payment_cny'],maturity_dates_proven=False,new_shareholder_distribution=False)
        except ValueError as error:
            scenario_failures[name]=dict(status='UNASSESSABLE',reason=str(error))
        assemblies[name]=dict(**forecasts,model_years=model_years)
        pressures[name]=dict(pressure=pressure,permanent_lock_pressure_comparison=dict(effective_floor_cny=str(permanent_floor),horizon='THROUGH_EXPLICIT_AND_TERMINAL_NO_AUTOMATIC_RELEASE'),
            effective_cash_floor_cny=str(effective_floor),settlement_schedule=settlement,reservation_horizon='UNSCHEDULED_OTHER_CURRENT_AND_CASH_FLOOR_REMAIN_RESERVED',
            declared_dividend_reserved_once=True,wc_excludes_opening_payable_settlement=True)
    if scenario_failures:
        return dict(status='PARTIAL_REVALIDATION_PENDING_ECONOMIC_REVIEW',source_spec=ref,
            as_of=made.isoformat(),financial_basis=spec['financial_basis'],latest_actual_period=q['period_end'],confidence='low',
            period_assembly=dict(q3_actual=q3,scenarios=assemblies),parent_obligations=dict(snapshot=snapshot,per_scenario=pressures),
            annual_ledgers={name:{k:v for k,v in result.items() if k!='typed_scenario'} for name,result in compiled.items()},
            scenario_failures=scenario_failures,valuation=None,price_policy=dict(status='NOT_PREPARED',rules=[],draft_prices=None),
            unknowns=spec['unknowns'],counter_evidence=[spec['countercase']])
    catalog=deepcopy(template['sources'])
    refs=[dict(id=s['id'],path=s['local_path'],sha256=s['sha256']) for s in catalog]
    extras=[ref,*b.values(),*task['roles'].values()]
    extras.extend(dict(path=s['path'],sha256=s['sha256']) for s in source_closure['sources'])
    for binding in extras:
        _bound(root,binding,closure)
        if any(s['local_path']==binding['path'] and s['sha256']==binding['sha256'] for s in catalog):continue
        ident='revalidation-'+binding['sha256']
        catalog.append(dict(id=ident,kind='research_artifact',local_path=binding['path'],location=binding['path'],sha256=binding['sha256'],
            source_available_at=made.isoformat(),retrieved_at=made.isoformat(),availability_basis='CURRENT_COLD_REVALIDATION_NOT_HISTORICAL_PIT'))
        refs.append(dict(id=ident,path=binding['path'],sha256=binding['sha256']))
    executed=run_explicit_cash_research(root=root,template_package=template,compiled_scenarios=compiled,source_catalog=catalog,evidence_refs=refs,
        assumption_metadata=dict(basis='DATED_CONDITIONAL_WORKING_CANDIDATE_NOT_ADOPTED',rationale=spec['rationale'],confidence='low',sensitivity='high'),
        version_metadata=dict(run_id='main-revalidation-'+ref['sha256'][:20],generated_at=made.isoformat(),rationale=spec['rationale'],countercase=spec['countercase']),now=now)
    valuation=json.loads(executed['outcome'].valuation.to_json()) if executed['outcome'].valuation else None
    if valuation is None:raise ValueError('SHARED_MODEL_NOT_READY')
    if service._load(ids[0],recover=False)[2]!=pin:raise ValueError('DRIVER_TASK_VERSION_CHANGED')
    price=_price_draft(spec,executed['descriptor'],valuation,ref,made)
    return dict(status=SUCCESS,source_spec=ref,as_of=made.isoformat(),financial_basis=spec['financial_basis'],latest_actual_period=q['period_end'],
        confidence='low',research_label='条件研究工作候选，待人工经济复核',
        input_descriptor_sha256=executed['input_descriptor_sha256'],implementation_sha256=spec['implementation_sha256'],
        reporting_currency_basis=currency_basis,period_assembly=dict(q3_actual=q3,scenarios=assemblies),parent_obligations=dict(snapshot=snapshot,per_scenario=pressures,
            official_constraints=constraints,current_capacity_proven=False),cash_input_basis=da,
        annual_ledgers=executed['annual_ledgers'],valuation=valuation,
        price_policy=price,
        dated_research_review_thresholds=dict(status='NOT_PREPARED',valuation_basis_date=spec['financial_basis'],
            reason='ECONOMIC_REVIEW_THRESHOLD_RULES_NOT_SELECTED',draft_id=price['draft']['draft_id'],
            rules=[],draft_prices=None,economic_approval=False,current_action_price=False),
        unknowns=spec['unknowns'],counter_evidence=[spec['countercase']],
        limitations=['2025/2026财政年度85亿元分配政策未被完整建模；不宣称履约或法律违约。',
            '母H1债务账面额与已宣股利仅年1条件支付一次；并非真实付款日或已核本金，非新分红/CapEx；其余义务保留独立压力，不是当前容量。',
            'Q4条件迁移、十年冻结利润和终端均未获经济采纳；不是历史PIT或当前价格比较。'],
        source_bindings=[ref,*b.values()])


def _cold_da(root,packet,actual,made):
    _stamp(packet['generated_at'],made)
    if packet.get('symbol')!=actual['symbol'] or packet.get('scope')!='consolidated' or packet.get('unit')!='CNY':
        raise ValueError('DA_PACKET_IDENTITY_INVALID')
    if packet['period_columns']!=['FY2025','FY2024','H12026','H12025']:
        raise ValueError('DA_EXPLICIT_PERIOD_COLUMNS_REQUIRED')
    sources={source['id']:source for source in actual['sources']}
    expected={(source['id'],source['report_period']) for source in actual['sources']
        if source['report_period'] in {'2025-12-31','2026-06-30'}}
    declared=packet.get('sources')
    if (not isinstance(declared,list) or len(declared)!=2 or len(expected)!=2
            or {(source['id'],source['report_period']) for source in declared}!=expected
            or len({source['id'] for source in declared})!=2
            or set(packet.get('original_pages',{}))!={source['id'] for source in declared}
            or len(packet.get('rows',[]))!=8 or len({r['label'] for r in packet['rows']})!=8):
        raise ValueError('DA_FY_H1_COMPLETE_UNIQUE_SOURCE_SET_REQUIRED')
    observations=[]
    for source in packet['sources']:
        current=sources.get(source['id'])
        if (current is None or current['sha256']!=source['sha256'] or current['path']!=source['path']
                or current['report_period']!=source['report_period'] or source.get('symbol')!=actual['symbol']
                or source.get('issuer_name')!=actual['issuer_name']):
            raise ValueError('DA_SOURCE_IDENTITY_MISMATCH')
        path,raw=native._raw(root,source)
        decoded=extract_pages(path)
        for clock in ('available_at','identity_available_at','published_at'):
            if source.get(clock):_stamp(source[clock],made)
        locators=packet['original_pages'][source['id']]
        if not isinstance(locators,dict) or not locators:raise ValueError('DA_SOURCE_ORIGINAL_PAGES_REQUIRED')
        for number,excerpt in locators.items():
            if _compact(decoded[int(number)-1])!=_compact(excerpt):raise ValueError('DA_ORIGINAL_PAGE_CHANGED')
        selected=''.join(_compact(decoded[int(number)-1]) for number in locators).replace(',','')
        offset=0 if source['report_period']=='2025-12-31' else 2
        for row in packet['rows']:
            label=_compact(row['label']).replace(',','').replace('负号','“-”号')
            if not isinstance(row['values'],list) or len(row['values'])!=4:
                raise ValueError('DA_FOUR_CONSUMED_COMPARATIVE_COLUMNS_REQUIRED')
            pair=row['values'][offset:offset+2]
            if len(pair)!=2 or label+''.join(pair) not in selected:
                raise ValueError('DA_WC_ORIGINAL_ROW_OR_COLUMN_MISMATCH:'+row['label'])
            locations=[int(number) for number in locators if label+''.join(pair) in _compact(decoded[int(number)-1]).replace(',','')]
            if len(locations)!=1:raise ValueError('DA_WC_UNIQUE_ORIGINAL_ROW_REQUIRED:'+row['label'])
            page=locations[0]
            original_needle=label+''.join(format(Decimal(value),',.2f') for value in pair)
            observations.append(dict(source_id=source['id'],source_sha256=source['sha256'],physical_page=page,
                label=row['label'],values=pair,excerpt=_raw_excerpt(decoded[page-1],original_needle)))
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('DA_ORIGINAL_CHANGED')
    if len(observations)!=16:raise ValueError('DA_ALL_ORIGINAL_ROWS_REQUIRED')
    result=_decode_da(packet)
    result['source_status']='ORIGINAL_PAGES_AND_COMPARATIVE_ROWS_COLD_MATCHED'
    result['observations']=observations
    return result


def _decode_da(packet):
    values={r['label']:r['values'] for r in packet['rows']}
    idx=packet['period_columns'].index('FY2025')
    value=lambda label:Decimal(values[label][idx])
    gross=value('购建固定资产、无形资产和其他长期资产支付的现金')
    da=sum(value(k) for k in ('固定资产折旧、油气资产折耗、生产性生物资产折旧','无形资产摊销','长期待摊费用摊销'))
    wc=-(value('存货的减少（增加以负号填列）')+value('经营性应收项目的减少（增加以负号填列）'))
    return dict(net_maintenance_ex_rou_proxy_cny=str(max(Decimal(0),gross-da)),wc_ex_payables_proxy_cny=str(max(Decimal(0),wc)),
        classification='EXPLICIT_HYPOTHESIS_NOT_MAINTENANCE_FACT',rou_da_not_subtracted=True,
        wc_basis='FIRST_MODEL_YEAR_ONLY_INVENTORY_RECEIVABLE_PROXY_EXCLUDES_RESERVED_PAYABLES',
        later_wc_basis='ZERO_INCREMENT_NO_RELEASE_UNDER_FROZEN_NOMINAL_EARNINGS_HYPOTHESIS')



def _price_draft(spec,descriptor,valuation,source_ref,made):
    from ...domain.decision.value_price_policy import draft_value_price_policy, preview_draft_prices
    pp=spec['price_policy']
    if (not pp['rationale'] or not pp['rule_version'] or not pp['reopen_conditions']
            or (pp['rules'] and pp['economic_conditions_sufficient'] is not True)):
        raise ValueError('EXPLICIT_PRICE_RULE_REASONS_EXPIRY_REOPEN_AND_ECONOMIC_SCOPE_REQUIRED')
    plan=dict(symbol=spec['symbol'],action='no_order',research_version=VERSION,
        valuation_input_version=descriptor.input_sha256,model_id=descriptor.requested_model,
        model_type='residual_income_or_equity_value',model_version='residual-income-equity-path-v4',
        valuation_date=valuation['valuation_date'],profile_id=descriptor.profile_id,
        source_bindings=[source_ref],**{name:valuation[name+'_value'] for name in ('bear','base','bull')})
    draft=draft_value_price_policy(plan,draft_id='main-revalidation-'+descriptor.input_sha256[:20],
        policy_id=pp['policy_id'],rule_version=pp['rule_version'],profile_id=descriptor.profile_id,
        effective_from=date.fromisoformat(pp['effective_from']),effective_through=date.fromisoformat(pp['effective_through']),
        rationale=pp['rationale'],dividend_coverage_risk=pp['dividend_coverage_risk'],rules=pp['rules'],
        thesis_reviews=pp['reopen_conditions'])
    preview=preview_draft_prices(draft)
    return dict(status='NOT_PREPARED' if not pp['rules'] else 'UNAPPROVED_DATED_RESEARCH_DRAFT',draft=draft,
        diagnostic_preview_prices=preview,rules=pp['rules'],draft_prices=None,registered=False,
        formal_eligibility=False,current_action_prices=None,economic_approval=False,
        reason='NO_CURRENT_ACTION_PRICES_OR_ECONOMICALLY_ADOPTED_MAIN_RANGE',action='no_order')


def _verify_quarter_receipt(source,spec,actual,made,packet):
    ident=spec['quarterly_source_id']
    if (source.get('status')!='ACQUIRED' or source.get('source_id')!=ident
            or re.fullmatch(r'cninfo:[0-9]+',ident) is None
            or packet.get('symbol',spec['symbol'])!=spec['symbol']
            or source.get('symbol',spec['symbol'])!=actual['symbol']
            or source.get('issuer_name',actual['issuer_name'])!=actual['issuer_name']):
        raise ValueError('QUARTER_RECEIPT_STATUS_ID_OR_ISSUER_MISMATCH')
    url=urlsplit(source['url'])
    parts=url.path.split('/')
    if (url.scheme!='https' or url.hostname!='static.cninfo.com.cn' or url.query or url.fragment
            or url.username or url.password or parts[-1]!=ident.split(':')[1]+'.PDF'
            or len(parts)!=4 or parts[1]!='finalpage'):
        raise ValueError('QUARTER_OFFICIAL_URL_ID_MISMATCH')
    publication=date.fromisoformat(parts[2])
    available=_stamp(source['available_at'],made)
    published=_stamp(source['published_at'],made)
    if published>available or published.astimezone(ZoneInfo('Asia/Shanghai')).date()!=publication:
        raise ValueError('QUARTER_PUBLICATION_AVAILABILITY_CONFLICT')
    if source.get('published_date') and date.fromisoformat(source['published_date'])!=publication:
        raise ValueError('QUARTER_DECLARED_PUBLICATION_DATE_CONFLICT')
    if source.get('source_url') and source['source_url']!=source['url']:
        raise ValueError('QUARTER_OFFICIAL_URL_ID_MISMATCH')

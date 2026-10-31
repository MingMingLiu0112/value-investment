"""Synthetic parser attacks and opt-in retained-original cash replay, no writes by service."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import parent_cash_research as service


NOW = datetime(2026, 10, 25, 9, tzinfo=timezone.utc)
SYMBOL = '600887'
OWNER = '内蒙古伊利实业集团股份有限公司'


def statement(periods):
    annual = periods[0].startswith('FY')
    current = dict(cfo_cny='10.00', cfi_cny='-2.00', cff_cny='-3.00', fx_cny='-1.00',
        reported_net_change_cny='4.00', opening_cash_and_equivalents_cny='100.00',
        closing_cash_and_equivalents_cny='104.00', gross_capex_cny='2.00',
        investment_income_cash_cny='3.00', mixed_distribution_interest_paid_cny='5.00',
        borrowings_received_cny='6.00', debt_repaid_cny='7.00')
    if not annual:
        current.update(opening_cash_and_equivalents_cny='104.00', closing_cash_and_equivalents_cny='108.00')
    previous = dict(current, opening_cash_and_equivalents_cny='80.00', closing_cash_and_equivalents_cny='84.00')
    report, interval, _ = service.PERIODS[tuple(periods)]
    columns = ['2025年度', '2024年度'] if annual else ['2026年半年度', '2025年半年度']
    spec = dict(symbol=SYMBOL, issuer='伊利', periods=periods, column_labels=columns,
        source_id='cninfo:'+('1225259562' if annual else '1225511409'),
        published_date='2026-04-30' if annual else '2026-08-27', original_acquired_at=None)
    spec['source_url'] = 'https://static.cninfo.com.cn/finalpage/'+spec['published_date']+'/'+spec['source_id'][7:]+'.PDF'
    rows = lambda keys: '\n'.join(service.LABELS[k]+' '+current[k]+' '+previous[k] for k in keys)
    table = '\n'.join([OWNER+report, '母公司现金流量表', interval, '单位：元 币种：人民币',
        '项目 附注 '+' '.join(columns), '一、经营活动产生的现金流量：', rows(['cfo_cny']),
        '二、投资活动产生的现金流量：', rows(['investment_income_cash_cny','gross_capex_cny','cfi_cny']),
        '三、筹资活动产生的现金流量：', rows(['borrowings_received_cny','debt_repaid_cny',
            'mixed_distribution_interest_paid_cny','cff_cny']),
        '四、'+rows(['fx_cny']), '五、'+rows(['reported_net_change_cny']),
        '加：'+rows(['opening_cash_and_equivalents_cny']), '六、'+rows(['closing_cash_and_equivalents_cny'])])
    return spec, ['公司代码：'+SYMBOL+'\n'+OWNER+report, table, OWNER+report+'\n合并所有者权益变动表']


@pytest.fixture
def retained(tmp_path, monkeypatch):
    specs, pages = [], {}
    for i, periods in enumerate((['FY2025','FY2024'], ['H12026','H12025'])):
        spec, extracted = statement(periods)
        path = tmp_path/f'runtime/TEST_ONLY-{i}.pdf'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'%PDF-TEST_ONLY, extracted text is mocked, not official data '+str(i).encode())
        spec.update(path=path.relative_to(tmp_path).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())
        pages[path.name] = extracted
        specs.append(spec)
    data = dict(schema_version='two-company-earnings-source-spec-v1',
        scope='RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION', action='no_order', companies={SYMBOL:specs})
    spec_path = tmp_path/service.SPEC
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(data), encoding='utf-8')
    for ref in service._EXECUTED_BINDINGS:
        target = tmp_path/ref['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((service._EXECUTING_ROOT/ref['path']).read_bytes())
    monkeypatch.setattr(service, 'extract_pages', lambda path:deepcopy(pages[path.name]))
    return tmp_path, data, pages


def save_spec(root, data):
    (root/service.SPEC).write_text(json.dumps(data), encoding='utf-8')


def test_service_reads_both_columns_and_no_forecast_or_write(retained):
    root, _, _ = retained
    before = {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with localcontext() as ctx:
        ctx.prec = 3
        result = service.load_parent_cash_research(root=root, symbol=SYMBOL, now=NOW)
    assert result['status'] == 'SOURCE_REPLAYED_HISTORICAL_PARENT_CASH'
    assert result['continuity_status'] == result['historical_cash_reconciliation_status'] == 'PASS'
    assert len(result['historical_statements']) == 2
    for statement_ in result['historical_statements']:
        for balance in statement_['balances']:
            assert Decimal(balance['cash_residual_cny']) == Decimal(balance['movement_residual_cny']) == 0
            assert balance['reconciliation']['status']=='HISTORICAL_CASH_RECONCILED_NOT_DISTRIBUTABLE'
            assert balance['reconciliation']['statement']['scope']=='issuer_parent_standalone'
        fx = statement_['rows']['fx_cny']
        assert fx['physical_page'] == 2 and len(fx['columns']) == 2
        assert fx['columns'][0]['value'] == '-1.00'
        assert fx['source_binding']['sha256']
    assert result['ordinary_dividends_paid_cny'] is result['upstream_dividends_received_cny'] is None
    assert result['parent_restricted_cash_cny'] is result['future_distributable_cash_cny'] is None
    assert result['distribution_capacity_status'] == 'UNKNOWN'
    assert result['policy_status']=='NOT_EVALUATED_SOURCE_BOUND_POLICY_AND_ELIGIBLE_SHARES_REQUIRED'
    assert not any(result[k] for k in ('economic_approval','formal_eligibility','primary_valuation_usable',
                                      'strategy_admitted','price_admitted'))
    assert result['action'] == 'no_order'
    assert before == {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fault', ['symbol','owner','scope','compiler','unit','currency','period',
    'columns','duplicate','missing_fx','one_column','bad_fx','bad_movement','bad_prior','section',
    'foreign_table','foreign_report','missing_end','wrong_spec_period'])
def test_parser_rejects_bad_table_without_borrowing_numbers(fault):
    spec, pages = statement(['FY2025','FY2024'])
    if fault == 'symbol': pages[0] = pages[0].replace(SYMBOL,'600519')
    elif fault == 'owner': pages[0] = pages[0].replace(OWNER,'其他股份有限公司')
    elif fault == 'scope': pages[1] = pages[1].replace('母公司现金流量表','合并现金流量表')
    elif fault == 'compiler': pages[1] = pages[1].replace('四、','编制单位：其他股份有限公司\n四、')
    elif fault == 'unit': pages[1] = pages[1].replace('单位：元','单位：万元')
    elif fault == 'currency': pages[1] = pages[1].replace('人民币','美元')
    elif fault == 'period': pages[1] = pages[1].replace('2025年1-12月','2025年1-6月')
    elif fault == 'columns': pages[1] = pages[1].replace('项目 附注 2025年度 2024年度','项目 附注 2024年度 2025年度')
    elif fault == 'duplicate': pages[1] += '\n经营活动产生的现金流量净额 10.00 10.00'
    elif fault == 'missing_fx': pages[1] = pages[1].replace('四、汇率变动对现金及现金等价物的影响 -1.00 -1.00\n','')
    elif fault == 'one_column': pages[1] = pages[1].replace('取得投资收益收到的现金 3.00 3.00','取得投资收益收到的现金 3.00')
    elif fault == 'bad_fx': pages[1] = pages[1].replace('影响 -1.00 -1.00','影响 1.00 -1.00')
    elif fault == 'bad_movement': pages[1] = pages[1].replace('净增加额 4.00 4.00','净增加额 5.00 4.00')
    elif fault == 'bad_prior': pages[1] = pages[1].replace('余额 104.00 84.00','余额 104.00 85.00')
    elif fault == 'section': pages[1] = pages[1].replace('经营活动产生的现金流量净额 10.00 10.00\n','').replace('四、','经营活动产生的现金流量净额 10.00 10.00\n四、')
    elif fault == 'foreign_table': pages[1] = pages[1].replace('四、','子公司现金流量表\n四、')
    elif fault == 'foreign_report': pages[1] = pages[1].replace('四、','其他股份有限公司2025年年度报告\n四、')
    elif fault == 'missing_end': pages.pop()
    elif fault == 'wrong_spec_period': spec['periods']=['FY2024','FY2023']
    with pytest.raises(ValueError):
        service.extract_parent_cash_statement(pages=pages,spec=spec)


@pytest.mark.parametrize('explicit', [False, True])
def test_matching_parent_continuation_preserves_pages(explicit):
    spec, pages = statement(['FY2025','FY2024'])
    first, last = pages[1].split('四、',1)
    title = '\n母公司现金流量表（续）\n编制单位：'+OWNER if explicit else ''
    pages[1:2] = [first, OWNER+'2025年年度报告'+title+'\n四、'+last]
    result = service.extract_parent_cash_statement(pages=pages,spec=spec)
    assert result['rows']['fx_cny']['physical_page'] == 3
    assert result['rows']['cfo_cny']['physical_page'] == 2


@pytest.mark.parametrize('fault', ['hash','format','source_id','url','issuer','periods','future',
    'naive_acquired','future_acquired','source_before_period','path','scope','implementation','continuity','naive_clock'])
def test_service_fails_closed_with_no_old_amounts(retained, fault):
    root, data, pages = retained
    source = data['companies'][SYMBOL][0]
    clock = NOW
    if fault == 'hash': (root/source['path']).write_bytes(b'%PDF-changed')
    elif fault == 'format':
        (root/source['path']).write_bytes(b'not a PDF');source['sha256']=sha256(b'not a PDF').hexdigest()
    elif fault == 'source_id': source['source_id']='cninfo:1'
    elif fault == 'url': source['source_url']=source['source_url'].replace('static.cninfo.com.cn','example.com')
    elif fault == 'issuer': source['symbol']='600519'
    elif fault == 'periods': data['companies'][SYMBOL][1]['periods']=['FY2025','FY2024']
    elif fault == 'future': clock=NOW.replace(year=2025)
    elif fault == 'naive_acquired': source['original_acquired_at']='2026-10-25T08:00:00'
    elif fault == 'future_acquired': source['original_acquired_at']=(NOW+timedelta(days=1)).isoformat()
    elif fault == 'source_before_period':
        source['published_date']='2025-01-01';source['source_url']=source['source_url'].replace('2026-04-30','2025-01-01')
    elif fault == 'path': source['path']='../outside.pdf'
    elif fault == 'scope': data['scope']='formal_approved'
    elif fault == 'implementation': (root/service._EXECUTED_BINDINGS[-1]['path']).write_bytes(b'drift')
    elif fault == 'continuity': pages['TEST_ONLY-1.pdf'][1]=pages['TEST_ONLY-1.pdf'][1].replace('104.00','105.00').replace('108.00','109.00')
    elif fault == 'naive_clock': clock=NOW.replace(tzinfo=None)
    save_spec(root,data)
    result=service.load_parent_cash_research(root=root,symbol=SYMBOL,now=clock)
    assert result['status']=='SOURCE_REVALIDATION_FAILED'
    assert result['historical_statements']==[] and result['source_bindings']==[]
    assert result['formal_eligibility'] is False


@pytest.mark.parametrize('target', ['original','spec','implementation'])
def test_end_of_read_revalidates_all_source_bytes(retained,monkeypatch,target):
    root,data,_=retained
    original=service.extract_parent_cash_statement
    def changed(**kwargs):
        result=original(**kwargs)
        path=(root/data['companies'][SYMBOL][0]['path'] if target=='original'
              else root/service.SPEC if target=='spec' else root/service._EXECUTED_BINDINGS[-1]['path'])
        path.write_bytes(b'changed during read')
        return result
    monkeypatch.setattr(service,'extract_parent_cash_statement',changed)
    assert service.load_parent_cash_research(root=root,symbol=SYMBOL,now=NOW)['status']=='SOURCE_REVALIDATION_FAILED'


def test_unlisted_company_does_not_invent_research(retained):
    root,_,_=retained
    assert service.load_parent_cash_research(root=root,symbol='000001',now=NOW) is None


def test_domain_reconciliation_is_called_for_each_printed_period(retained,monkeypatch):
    root,_,_=retained
    original=service.reconcile_parent_cash_statement
    calls=[]
    def observed(*,statement):
        calls.append(deepcopy(statement))
        return original(statement=statement)
    monkeypatch.setattr(service,'reconcile_parent_cash_statement',observed)
    result=service.load_parent_cash_research(root=root,symbol=SYMBOL,now=NOW)
    assert len(calls)==4
    assert {row['period_end'] for row in calls}=={'2025-12-31','2024-12-31','2026-06-30','2025-06-30'}
    assert all(row['scope']=='issuer_parent_standalone' and row['fx_cny']=='-1.00' for row in calls)
    assert any(ref['path'].endswith('/parent_cash_policy.py') for ref in result['source_bindings'])


@pytest.mark.parametrize('field',['investment_income_cash_cny','mixed_distribution_interest_paid_cny','fx_cny'])
def test_blank_or_one_column_never_inherits_next_row(field):
    spec,pages=statement(['H12026','H12025'])
    label=service.LABELS[field]
    import re
    pages[1]=re.sub(re.escape(label)+r' -?\d+\.\d{2} -?\d+\.\d{2}',label,pages[1])
    with pytest.raises(ValueError):
        service.extract_parent_cash_statement(pages=pages,spec=spec)


def test_retained_actual_two_originals_readonly():
    location=os.environ.get('PARENT_CASH_REPLAY_ROOT')
    if not location:
        pytest.skip('Opt-in retained public originals, not synthetic research')
    root=Path(location)
    result=service.load_parent_cash_research(root=root,symbol=SYMBOL,now=NOW)
    assert result['status']=='SOURCE_REPLAYED_HISTORICAL_PARENT_CASH'
    fy,h1=result['historical_statements']
    assert fy['balances'][0]['closing_cash_and_equivalents_cny']=='13404587376.75'
    assert h1['balances'][0]['closing_cash_and_equivalents_cny']=='14939427794.14'
    assert fy['rows']['fx_cny']['physical_page']==91
    assert h1['rows']['fx_cny']['physical_page']==57
    assert h1['balances'][0]['fx_cny']=='-22976.75'
    assert fy['balances'][0]['fx_cny']=='65113.83'
    assert h1['balances'][0]['mixed_distribution_interest_paid_cny']=='6186835910.21'
    assert h1['balances'][0]['reconciliation']['statement']['period_end']=='2026-06-30'
    hashes={ref['path']:sha256((root/ref['path']).read_bytes()).hexdigest() for ref in result['source_bindings']}
    assert all(hashes[ref['path']]==ref['sha256'] for ref in result['source_bindings'])
    assert service.load_parent_cash_research(root=root,symbol=SYMBOL,now=NOW)==result
    assert hashes=={name:sha256((root/name).read_bytes()).hexdigest() for name in hashes}


@pytest.mark.parametrize('layout', ['same_line', 'next_line', 'wrapped_label'])
def test_complete_two_columns_support_real_pdf_line_wrapping(layout):
    spec, pages = statement(['FY2025', 'FY2024'])
    if layout != 'same_line':
        for label in service.LABELS.values():
            rendered = label if layout == 'next_line' else label[:8]+'\n'+label[8:]
            pages[1] = pages[1].replace(label+' ', rendered+'\n')
    result = service.extract_parent_cash_statement(pages=pages, spec=spec)
    assert result['rows']['cfo_cny']['columns'][0]['value'] == '10.00'
    assert result['rows']['gross_capex_cny']['physical_page'] == 2
    assert result['balances'][0]['cash_residual_cny'] == '0.00'


@pytest.mark.parametrize('amounts', ['', ' 3.00', '\n3.00', '\n3.00\n3.00', '\n3.00 3.00 3.00'])
def test_wrapped_row_rejects_blank_incomplete_or_extra_columns(amounts):
    spec, pages = statement(['FY2025', 'FY2024'])
    label = service.LABELS['investment_income_cash_cny']
    pages[1] = pages[1].replace(label+' 3.00 3.00', label+amounts)
    with pytest.raises(ValueError, match='TWO_PRINTED_VALUES_REQUIRED:investment_income_cash_cny'):
        service.extract_parent_cash_statement(pages=pages, spec=spec)


@pytest.mark.parametrize('source_id,rows', [
    ('1225114741', {
        'cfo_cny': (66, '32618216666.91', '36826593268.70'),
        'cfi_cny': (67, '46417636870.56', '37359465215.19'),
        'cff_cny': (67, '-70822236099.32', '-68816834968.42'),
        'gross_capex_cny': (67, '3104346428.46', '4660307532.89'),
        'investment_income_cash_cny': (67, '49653138761.40', '42023527068.33'),
    }),
    ('1225475868', {
        'cfo_cny': (35, '15224606455.02', '8195990042.68'),
        'cfi_cny': (35, '-784318271.33', '-1594040752.84'),
        'cff_cny': (35, '-37915309725.21', '-39875924477.68'),
        'gross_capex_cny': (35, '828735611.53', '1593022645.30'),
    }),
])
def test_600519_retained_layout_rows_and_blank_rejection(source_id, rows):
    location = os.environ.get('PARENT_CASH_REPLAY_ROOT')
    if not location:
        pytest.skip('Opt-in retained 600519 originals, no source acquisition')
    root = Path(location)
    spec = next(s for s in json.loads((root/service.SPEC).read_bytes())['companies']['600519']
                if s['source_id'] == 'cninfo:'+source_id)
    path = root/spec['path']
    assert sha256(path.read_bytes()).hexdigest() == spec['sha256']
    pages = service.extract_pages(path)
    for key, (page, current, prior) in rows.items():
        text = '\n'.join(line.strip() for line in pages[page-1].splitlines() if line.strip())
        match = service._printed_cash_row(text=text, key=key, label=service.LABELS[key])
        assert tuple(str(Decimal(v.replace(',', ''))) for v in match.groups()) == (current, prior)
        assert match[0].strip()
    # Real blanks stay unknown. Neither restoring identical bytes nor layout
    # support licenses filling FX, borrowing or prior investment receipts with 0.
    with pytest.raises(ValueError, match='TWO_PRINTED_VALUES_REQUIRED:fx_cny'):
        service.extract_parent_cash_statement(pages=pages, spec=spec)


def test_explicit_partial_cash_never_fills_blank_or_claims_full_reconciliation():
    spec, pages = statement(['FY2025','FY2024'])
    result = service.extract_parent_cash_statement(pages=pages, spec=spec,
        observation_fields={'cfo_cny','gross_capex_cny'})
    assert result['whole_statement_reconciled'] is False
    assert 'fx_cny' in result['unknown_fields']
    assert set(result['rows']) == {'cfo_cny','gross_capex_cny'}
    assert 'fx_cny' not in result['balances'][0]


def test_actual_partial_600519_preserves_known_rows_without_inventing_missing_columns():
    location = os.environ.get('PARENT_CASH_REPLAY_ROOT')
    if not location:
        pytest.skip('Explicit actual original source root required')
    result = service.load_parent_cash_research(root=Path(location),symbol='600519',
        now=datetime.now(timezone.utc),observations_only=True)
    assert result['status'] == 'SOURCE_REPLAYED_PARTIAL_PARENT_CASH'
    assert result['historical_cash_reconciliation_status'] == 'INCOMPLETE'
    routes = {row['period']:row for row in result['cash_routes']}
    assert Decimal(routes['FY2025']['partial_cash_before_mixed_payments_cny']) == Decimal('32618216666.91')+Decimal('49653138761.40')-Decimal('3104346428.46')
    assert routes['H12026']['partial_cash_before_mixed_payments_cny'] is None
    assert 'investment_income_cash_cny' in routes['H12026']['unknown_fields']
    assert routes['H12026']['printed_cash_change_cny'] == '-23475021541.52'
    assert all(row['future_distributable_cash_cny'] is None for row in result['cash_routes'])

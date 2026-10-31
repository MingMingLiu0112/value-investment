"""Read retained standalone cash statements, never forecast distributable cash."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
import json
import re

from ...infrastructure.filings.pdf_text import extract_pages
from ...domain.valuation.parent_cash_policy import reconcile_parent_cash_statement
from ..product.common import require_inside, sha256_file


SPEC = 'docs/current/two-company-earnings-bridge-20261024/sources.json'
LABELS = {
    'cfo_cny': '经营活动产生的现金流量净额',
    'cfi_cny': '投资活动产生的现金流量净额',
    'cff_cny': '筹资活动产生的现金流量净额',
    'fx_cny': '汇率变动对现金及现金等价物的影响',
    'reported_net_change_cny': '现金及现金等价物净增加额',
    'opening_cash_and_equivalents_cny': '期初现金及现金等价物余额',
    'closing_cash_and_equivalents_cny': '期末现金及现金等价物余额',
    'gross_capex_cny': '购建固定资产、无形资产和其他长期资产支付的现金',
    'investment_income_cash_cny': '取得投资收益收到的现金',
    'mixed_distribution_interest_paid_cny': '分配股利、利润或偿付利息支付的现金',
    'borrowings_received_cny': '取得借款收到的现金',
    'debt_repaid_cny': '偿还债务支付的现金',
}
PERIODS = {
    ('FY2025', 'FY2024'): ('2025年年度报告', '2025年1-12月', '2025年度2024年度'),
    ('H12026', 'H12025'): ('2026年半年度报告', '2026年1-6月', '2026年半年度2025年半年度'),
}
_MONEY = r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}'
_EXECUTING_ROOT = Path(__file__).resolve().parents[4]
_EXECUTED_BINDINGS = tuple(dict(path=name, sha256=sha256_file(_EXECUTING_ROOT/name)) for name in (
    'src/value_investment_agent/application/research/parent_cash_research.py',
    'src/value_investment_agent/domain/valuation/parent_cash_policy.py',
    'src/value_investment_agent/infrastructure/filings/pdf_text.py',
    'src/value_investment_agent/infrastructure/filings/pdfium_runtime.py',
))


def _compact(text):
    return re.sub(r'\s+', '', text).replace('－', '-').replace('—', '-').replace('–', '-')


def _printed_cash_row(*, text: str, key: str, label: str):
    # PDFium may put both amounts on the line after a wrapped label. Keep
    # the two printed columns together; never cross a following row label.
    pattern = (r'(?m)^[ \t]*(?:[一二三四五六]、|加[:：])?'
               + r'[ \t\n]*'.join(map(re.escape, label))
               + r'(?:[ \t]+|[ \t]*\n[ \t]*)'
               + '('+_MONEY+r')[ \t]+('+_MONEY+r')[ \t]*\r?$')
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError('PARENT_CASH_TWO_PRINTED_VALUES_REQUIRED:'+key)
    return matches[0]


def extract_parent_cash_statement(*, pages: list[str], spec: dict, observation_fields=None) -> dict:
    """Parse printed columns; the caller must separately authenticate PDF bytes."""
    periods = tuple(spec['periods'])
    if periods not in PERIODS:
        raise ValueError('PARENT_CASH_UNSUPPORTED_PERIOD')
    report, interval, columns = PERIODS[periods]
    if ''.join(spec['column_labels']) != columns:
        raise ValueError('PARENT_CASH_SPEC_COLUMN_MISMATCH')
    header = '\n'.join(pages[:8])
    codes = set(re.findall(r'(?:公司|证券|股票)\s*代码\s*[:：]?\s*([0-9]{6})(?!\d)', header))
    owners = set()
    for page in pages[:8]:
        for line in page.splitlines():
            text = _compact(line)
            if text.endswith(report):
                owner = text[:-len(report)]
                if owner.endswith('股份有限公司'):
                    owners.add(owner)
    if (codes != {spec['symbol']} or len(owners) != 1
            or spec['issuer'] not in next(iter(owners))):
        raise ValueError('PARENT_CASH_ISSUER_OR_REPORT_MISMATCH')
    owner = next(iter(owners))
    lines = [(n, line.strip()) for n, page in enumerate(pages, 1)
             for line in page.splitlines() if line.strip()]
    starts = [i for i, (_, line) in enumerate(lines) if _compact(line) == '母公司现金流量表']
    if len(starts) != 1:
        raise ValueError('PARENT_CASH_TABLE_AMBIGUOUS')
    start = starts[0]
    ends = [i for i in range(start+1, len(lines))
            if _compact(lines[i][1]) in {'合并所有者权益变动表', '母公司所有者权益变动表'}]
    if not ends:
        raise ValueError('PARENT_CASH_TABLE_END_MISSING')
    selected = lines[start:ends[0]]
    continuation = {'母公司现金流量表(续)', '母公司现金流量表（续）',
                    '母公司现金流量表(续表)', '母公司现金流量表（续表）'}
    for i, (_, line) in enumerate(selected):
        text = _compact(line)
        if i and re.search(r'现金流量表|资产负债表|利润表|所有者权益变动表', text):
            if text not in continuation:
                raise ValueError('PARENT_CASH_TABLE_OWNERSHIP_CHANGED')
        if '编制单位' in text:
            compiler = re.fullmatch(r'编制单位[:：](.+?)(?:单位[:：].*)?', text)
            if not compiler or compiler[1] != owner:
                raise ValueError('PARENT_CASH_COMPILER_CHANGED')
        if re.search(r'\d{4}年(?:半年度|年度)报告$', text) and text != owner+report:
            raise ValueError('PARENT_CASH_REPORT_OWNER_CHANGED')
        units = re.findall(r'(?<!编制)单位[:：]([^:：]+?)(?=币种[:：]|$)', text)
        currencies = re.findall(r'币种[:：](.+)$', text)
        if any(unit != '元' for unit in units) or any(c != '人民币' for c in currencies):
            raise ValueError('PARENT_CASH_UNIT_OR_CURRENCY_MISMATCH')
    text = '\n'.join(line for _, line in selected)
    joined = _compact(text)
    headers = [_compact(line) for _, line in selected if _compact(line).startswith('项目')]
    intervals = [_compact(line) for _, line in selected
                 if re.fullmatch(r'\d{4}年\d{1,2}-\d{1,2}月', _compact(line))]
    if (interval not in joined or not headers or any(h != '项目附注'+columns for h in headers)
            or not intervals or any(item != interval for item in intervals)
            or '单位:元' not in joined.replace('：', ':')
            or '币种:人民币' not in joined.replace('：', ':')
            or any(word in joined for word in ('调整前', '调整后'))):
        raise ValueError('PARENT_CASH_PERIOD_COLUMNS_OR_UNIT_MISSING')
    sections = ('一、经营活动产生的现金流量:', '二、投资活动产生的现金流量:',
                '三、筹资活动产生的现金流量:', '四、汇率变动对现金及现金等价物的影响')
    normalized = joined.replace('：', ':')
    if any(normalized.count(label) != 1 for label in sections):
        raise ValueError('PARENT_CASH_SECTIONS_MISSING_OR_AMBIGUOUS')
    positions = [normalized.index(label) for label in sections]
    if positions != sorted(positions):
        raise ValueError('PARENT_CASH_SECTION_ORDER_INVALID')
    facts = {}
    if observation_fields is not None and (not observation_fields or not set(observation_fields) <= set(LABELS)):
        raise ValueError('Explicit supported partial cash fields required')
    for key, label in LABELS.items():
        if observation_fields is not None and key not in observation_fields:
            continue
        if joined.count(label) != 1:
            raise ValueError('PARENT_CASH_ROW_MISSING_OR_AMBIGUOUS:'+key)
        position = normalized.index(label)
        if key == 'cfo_cny':
            valid_section = positions[0] < position < positions[1]
        elif key in {'cfi_cny', 'gross_capex_cny', 'investment_income_cash_cny'}:
            valid_section = positions[1] < position < positions[2]
        elif key in {'cff_cny', 'borrowings_received_cny', 'debt_repaid_cny',
                     'mixed_distribution_interest_paid_cny'}:
            valid_section = positions[2] < position < positions[3]
        else:
            valid_section = position >= positions[3]
        if not valid_section:
            raise ValueError('PARENT_CASH_ROW_SECTION_MISMATCH:'+key)
        match = _printed_cash_row(text=text, key=key, label=label)
        page = selected[text[:match.start()].count('\n')][0]
        facts[key] = dict(label=label, physical_page=page, statement_scope='listed_parent_only',
            unit='CNY', currency='CNY', evidence_excerpt=match[0].strip(),
            columns=[dict(period=period, value=str(Decimal(value.replace(',', ''))))
                     for period, value in zip(periods, match.groups())])
    if observation_fields is not None:
        return dict(symbol=spec['symbol'], issuer=owner, periods=list(periods),
            statement_scope='listed_parent_only', rows=facts,
            balances=[dict(period=period, **{key: row['columns'][index]['value'] for key,row in facts.items()})
                for index, period in enumerate(periods)],
            whole_statement_reconciled=False, unknown_fields=sorted(set(LABELS)-set(facts)))
    with localcontext() as ctx:
        ctx.prec = 48
        balances = []
        for index, period in enumerate(periods):
            values = {key: Decimal(row['columns'][index]['value']) for key, row in facts.items()}
            year = int(period[-4:])
            reconciliation = reconcile_parent_cash_statement(statement=dict(
                symbol=spec['symbol'], period_start=f'{year}-01-01',
                period_end=f'{year}-12-31' if period.startswith('FY') else f'{year}-06-30',
                scope='issuer_parent_standalone', unit='CNY', currency='CNY',
                opening_cash_cny=str(values['opening_cash_and_equivalents_cny']),
                closing_cash_cny=str(values['closing_cash_and_equivalents_cny']),
                **{key:str(values[key]) for key in ('cfo_cny','cfi_cny','cff_cny','fx_cny','reported_net_change_cny')}))
            if any(values[key] < 0 for key in LABELS if key not in {
                    'cfo_cny', 'cfi_cny', 'cff_cny', 'fx_cny', 'reported_net_change_cny'}):
                raise ValueError('PARENT_CASH_UNSUPPORTED_GROSS_OR_BALANCE_SIGN')
            balances.append(dict(period=period, **{k: str(v) for k, v in values.items()},
                cash_residual_cny=reconciliation['closing_cash_residual_cny'],
                movement_residual_cny=reconciliation['net_change_residual_cny'],
                reconciliation=reconciliation))
    return dict(symbol=spec['symbol'], issuer=owner, periods=list(periods),
                statement_scope='listed_parent_only', rows=facts, balances=balances)


def load_parent_cash_research(*, root: Path, symbol: str, now: datetime, observations_only=False) -> dict | None:
    """Re-read two retained originals; no saved cash JSON, forecasts or writes."""
    if not isinstance(symbol, str) or re.fullmatch(r'[0-9]{6}', symbol) is None:
        raise ValueError('Parent cash requires a security code')
    root = root.resolve()
    envelope = dict(schema_version='parent-cash-research-v1', symbol=symbol, action='no_order',
        formal_eligibility=False, research_admitted=False, action_admitted=False,
        sustainable_distribution_proven=False, economic_approval=False, primary_valuation_usable=False,
        price_admitted=False, strategy_admitted=False, distribution_capacity_status='UNKNOWN',
        future_distributable_cash_cny=None, parent_restricted_cash_cny=None,
        policy_status='NOT_EVALUATED_SOURCE_BOUND_POLICY_AND_ELIGIBLE_SHARES_REQUIRED',
        upstream_dividends_received_cny=None, ordinary_dividends_paid_cny=None,
        historical_statements=[], source_bindings=[])
    try:
        if now.utcoffset() is None:
            raise ValueError('PARENT_CASH_AWARE_CLOCK_REQUIRED')
        path = require_inside(root, root/SPEC, 'parent cash source specification')
        spec_ref = dict(path=SPEC, sha256=sha256_file(path))
        source_spec = json.loads(path.read_bytes())
        if (source_spec['schema_version'] != 'two-company-earnings-source-spec-v1'
                or source_spec['scope'] != 'RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION'
                or source_spec['action'] != 'no_order'):
            raise ValueError('PARENT_CASH_SOURCE_SPEC_MISMATCH')
        originals = source_spec['companies'].get(symbol)
        if originals is None:
            return None
        if (len(originals) != 2 or {tuple(s['periods']) for s in originals} != set(PERIODS)
                or len({s['source_id'] for s in originals}) != 2):
            raise ValueError('PARENT_CASH_TWO_DISTINCT_PERIOD_ORIGINALS_REQUIRED')
        refs = [spec_ref, *[dict(ref) for ref in _EXECUTED_BINDINGS]]
        statements = []
        for source in originals:
            ident = re.fullmatch(r'cninfo:([0-9]+)', source['source_id'])
            url = re.fullmatch(r'https://static\.cninfo\.com\.cn/finalpage/(\d{4}-\d{2}-\d{2})/([0-9]+)\.PDF', source['source_url'])
            if (source['symbol'] != symbol or not ident or not url or ident[1] != url[2]
                    or url[1] != source['published_date']):
                raise ValueError('PARENT_CASH_OFFICIAL_SOURCE_IDENTITY_MISMATCH')
            published = date.fromisoformat(source['published_date'])
            closing = date(2025, 12, 31) if source['periods'][0] == 'FY2025' else date(2026, 6, 30)
            boundary = datetime.combine(published+timedelta(days=1), time(), timezone(timedelta(hours=8)))
            acquired = source.get('original_acquired_at')
            if published < closing or boundary > now:
                raise ValueError('PARENT_CASH_SOURCE_NOT_AVAILABLE')
            if acquired is not None:
                acquired_at = datetime.fromisoformat(acquired)
                if acquired_at.utcoffset() is None or acquired_at > now or acquired_at.astimezone(
                        timezone(timedelta(hours=8))).date() < published:
                    raise ValueError('PARENT_CASH_ACQUISITION_TIME_INVALID')
            relative = Path(source['path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('PARENT_CASH_ROOT_RELATIVE_ORIGINAL_REQUIRED')
            original = require_inside(root, root/relative, 'parent cash official original')
            if sha256_file(original) != source['sha256'] or not original.read_bytes().startswith(b'%PDF-'):
                raise ValueError('PARENT_CASH_ORIGINAL_HASH_OR_FORMAT_MISMATCH')
            ref = dict(path=relative.as_posix(), sha256=source['sha256'])
            fields = None
            if observations_only:
                fields = {'cfo_cny','cfi_cny','cff_cny','reported_net_change_cny',
                    'opening_cash_and_equivalents_cny','closing_cash_and_equivalents_cny',
                    'gross_capex_cny','mixed_distribution_interest_paid_cny'}
                if source['periods'][0].startswith('FY'):
                    fields.add('investment_income_cash_cny')
            statement = extract_parent_cash_statement(pages=extract_pages(original), spec=source,
                observation_fields=fields)
            binding = dict(id=source['source_id'], **ref, source_url=source['source_url'],
                published_date=source['published_date'], original_acquired_at=acquired,
                date_only_available_at_conservative=boundary.isoformat(), revalidated_at=now.isoformat())
            for fact in statement['rows'].values():
                fact.update(source_id=source['source_id'], source_binding=dict(binding))
            statement['source_binding'] = binding
            statements.append(statement)
            refs.append(ref)
        by_period = {s['periods'][0]: s for s in statements}
        annual, interim = by_period['FY2025'], by_period['H12026']
        if (annual['issuer'] != interim['issuer'] or
                Decimal(annual['balances'][0]['closing_cash_and_equivalents_cny']) !=
                Decimal(interim['balances'][0]['opening_cash_and_equivalents_cny'])):
            raise ValueError('PARENT_CASH_PERIOD_CONTINUITY_FAILED')
        for ref in refs:
            if sha256_file(require_inside(root, root/ref['path'], 'parent cash final source check')) != ref['sha256']:
                raise ValueError('PARENT_CASH_SOURCE_CHANGED_DURING_READ')
        cash_routes = []
        if observations_only:
            with localcontext() as context:
                context.prec = 48
                for statement in (annual, interim):
                    for row in statement['balances']:
                        income = row.get('investment_income_cash_cny')
                        proxy = (Decimal(row['cfo_cny'])+Decimal(income)-Decimal(row['gross_capex_cny'])
                            if income is not None else None)
                        cash_routes.append(dict(period=row['period'], scope='listed_parent_only', currency='CNY',
                            identity_class='DERIVED_FROM_PRINTED_HISTORICAL_CASH_NOT_NORMALIZED',
                            printed_cfo_cny=row['cfo_cny'], printed_gross_capex_cny=row['gross_capex_cny'],
                            printed_investment_income_cash_cny=income,
                            partial_cash_before_mixed_payments_cny=str(proxy) if proxy is not None else None,
                            formula='CFO + investment-income cash - gross long-term-asset cash',
                            printed_mixed_distribution_interest_paid_cny=row['mixed_distribution_interest_paid_cny'],
                            printed_cash_change_cny=row['reported_net_change_cny'],
                            unknown_fields=statement['unknown_fields'],
                            future_distributable_cash_cny=None, ordinary_dividends_identified=False,
                            limitation='Partial historical funding route, not FCF, subsidiary-dividend attribution, legal capacity or a future payout ceiling.'))
        return dict(envelope, status=('SOURCE_REPLAYED_PARTIAL_PARENT_CASH' if observations_only
                else 'SOURCE_REPLAYED_HISTORICAL_PARENT_CASH'),
            cash_routes=cash_routes,
            evaluated_at=now.isoformat(), historical_statements=[annual, interim], source_bindings=refs,
            availability_scope='RETAINED_ORIGINAL_RESEARCH_NOT_CONTEMPORANEOUS_PIT_PROOF',
            continuity_status='PASS', historical_cash_reconciliation_status='INCOMPLETE' if observations_only else 'PASS',
            limitations=['H1 is not annualized; historical net cash is not recurring cash capacity.',
                'Mixed distribution/profit/interest payments are not identified ordinary dividends.',
                'Investment income cash is not identified subsidiary dividend remittance.',
                'Cash equivalents are not certified legally distributable parent cash.',
                'No future remittance, financing, maintenance capex or payout policy is assumed.'])
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, IndexError):
        return dict(envelope, status='SOURCE_REVALIDATION_FAILED',
                    reason='Parent cash originals, statement scope or reconciliation failed; amounts withheld.')

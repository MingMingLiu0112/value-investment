"""Source-bound economic diagnostics for pending equity research, without approval."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path
import re

from ...valuation_models.residual_income import QualityCompounderFacts, scenario_value
from ...valuation_models.residual_income_path_v2 import scenario_calculation
from ...research_input import _residual_scenario_from_payload
from ...valuation_models.residual_income_path_v3 import (
    scenario_calculation as scenario_calculation_v3,
)
from ...valuation_models.residual_income_path_v4 import (
    scenario_calculation as scenario_calculation_v4,
)
from .v3_input_adapter import (
    RETENTION_CONTRACT as V3_RETENTION_CONTRACT,
    scenario_from_payload as scenario_from_payload_v3,
)
from .v4_input_adapter import (
    RETENTION_CONTRACT as V4_RETENTION_CONTRACT,
    scenario_from_payload as scenario_from_payload_v4,
)
from ..product.common import normalize_symbol
from .value_research_analysis import _available, _bound, load_current_value_research_analysis
from .economic_review_bundle import _build_economic_review_bundle
from .operating_earnings_bridge import research_from_retained_sources
from ...infrastructure.filings.pdf_text import extract_pages


_OPERATING_EXECUTION_PATHS = (
    'src/value_investment_agent/application/research/value_economic_assessment.py',
    'src/value_investment_agent/application/research/operating_earnings_bridge.py',
    'src/value_investment_agent/infrastructure/filings/pdf_text.py',
    'src/value_investment_agent/infrastructure/filings/pdfium_runtime.py',
)
_EXECUTED_OPERATING_BINDINGS = tuple(dict(path=name, sha256=sha256(
    (Path(__file__).resolve().parents[4] / name).read_bytes()).hexdigest())
    for name in _OPERATING_EXECUTION_PATHS)

_CASH_EXECUTION_BINDINGS = tuple(ref for ref in _EXECUTED_OPERATING_BINDINGS
    if ref['path'] != 'src/value_investment_agent/application/research/operating_earnings_bridge.py') + (
        dict(path='src/value_investment_agent/application/research/value_research_analysis.py',
             sha256=sha256((Path(__file__).resolve().parents[4] /
                'src/value_investment_agent/application/research/value_research_analysis.py').read_bytes()).hexdigest()),)
_CASH_SCOPE = 'HISTORICAL_FINANCIAL_FLOW_DIAGNOSTIC_NOT_NORMALIZED_OR_DISTRIBUTABLE'


def _cash_flow_rows(pages, *, symbol, issuer, current_year):
    """Read two printed columns inside one identified consolidated cash table."""
    compact = lambda text: re.sub(r'\s+', '', text)
    header = '\n'.join(pages[:8])
    codes = set(re.findall(r'(?:公司|证券|股票)\s*代码\s*[:：]?\s*([0-9]{6})(?!\d)', header))
    if codes != {symbol} or issuer not in compact(header):
        raise ValueError('CASH_FLOW_ISSUER_MISMATCH')
    if f'{current_year}年半年度报告' not in compact(header):
        raise ValueError('CASH_FLOW_REPORT_PERIOD_MISMATCH')
    lines = [(page, line.strip()) for page, text in enumerate(pages, 1)
             for line in text.splitlines() if line.strip()]
    starts = [i for i, (_, line) in enumerate(lines) if compact(line) == '合并现金流量表']
    if len(starts) != 1:
        raise ValueError('CASH_FLOW_CONSOLIDATED_TABLE_AMBIGUOUS')
    start = starts[0]
    ends = [i for i in range(start + 1, len(lines)) if compact(lines[i][1]) == '母公司现金流量表']
    if not ends:
        raise ValueError('CASH_FLOW_TABLE_END_MISSING')
    selected = lines[start:ends[0]]
    owners = {compact(issuer)}
    for line in header.splitlines():
        report_owner = re.fullmatch(r'(.+?)' + str(current_year) + r'年半年度报告', compact(line))
        if report_owner and compact(issuer) in report_owner[1]:
            owners.add(report_owner[1])
    ownership = [dict(physical_page=lines[start][0], evidence_excerpt=lines[start][1],
                      kind='CONSOLIDATED_TABLE_START')]
    continuation_titles = {'合并现金流量表（续）', '合并现金流量表(续)',
                           '合并现金流量表（续表）', '合并现金流量表(续表)'}
    for index, (page_number, line) in enumerate(selected):
        text = compact(line)
        if '现金流量表' in text and index != 0:
            if text not in continuation_titles:
                raise ValueError('CASH_FLOW_STATEMENT_OWNERSHIP_CHANGED')
            ownership.append(dict(physical_page=page_number, evidence_excerpt=line,
                                  kind='CONSOLIDATED_CONTINUATION'))
        if '编制单位' in text:
            compiler = re.fullmatch(r'编制单位[:：](.+?)(?:单位[:：].*)?', text)
            if not compiler or compiler[1] not in owners:
                raise ValueError('CASH_FLOW_COMPILING_ENTITY_MISMATCH')
            ownership.append(dict(physical_page=page_number, evidence_excerpt=line,
                                  kind='MATCHED_COMPILING_ENTITY'))
    table = '\n'.join(line for _, line in selected)
    joined = compact(table)
    period = joined.replace('—', '-').replace('－', '-').replace('–', '-')
    if f'{current_year}年1-6月' not in period:
        raise ValueError('CASH_FLOW_STATEMENT_PERIOD_MISMATCH')
    expected = f'项目附注{current_year}年半年度{current_year-1}年半年度'
    headers = [compact(line) for _, line in selected if compact(line).startswith('项目')]
    if not headers or any(line != expected for line in headers):
        raise ValueError('CASH_FLOW_TWO_COLUMN_ORDER_MISMATCH')
    units = re.findall(r'(?<!编制)单位[:：]\s*([^\s:：]+)', table)
    currencies = re.findall(r'币种[:：]\s*([^\s:：]+)', table)
    if not units or not currencies or set(units) != {'元'} or set(currencies) != {'人民币'}:
        raise ValueError('CASH_FLOW_UNIT_OR_CURRENCY_MISMATCH')
    boundaries = ('经营活动现金流入小计', '经营活动现金流出小计', '二、投资活动产生的现金流量')
    if any(joined.count(label) != 1 for label in boundaries):
        raise ValueError('CASH_FLOW_OPERATING_SECTION_AMBIGUOUS')
    inflow, outflow, investing = (joined.index(label) for label in boundaries)
    if not inflow < outflow < investing:
        raise ValueError('CASH_FLOW_OPERATING_SECTION_ORDER_INVALID')
    money = r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}'
    rows = []
    for label, section in (
            ('经营活动产生的现金流量净额', 'OPERATING_NET_CASH'),
            ('存放中央银行和同业款项净增加额', 'OPERATING_CASH_OUTFLOW')):
        if joined.count(label) != 1:
            raise ValueError('CASH_FLOW_ROW_MISSING_OR_AMBIGUOUS:' + label)
        position = joined.index(label)
        if not ((outflow < position < investing) if section == 'OPERATING_NET_CASH'
                else (inflow < position < outflow)):
            raise ValueError('CASH_FLOW_ROW_SECTION_MISMATCH:' + label)
        pattern = (r'(?m)^' + r'\s*'.join(re.escape(char) for char in label)
                   + r'\s+(' + money + r')\s+(' + money + r')[ \t]*(?=\n|$)')
        matches = list(re.finditer(pattern, table))
        if len(matches) != 1:
            if section == 'OPERATING_CASH_OUTFLOW':
                blank = re.search(r'(?m)^' + r'\s*'.join(re.escape(char) for char in label)
                                  + r'[ \t]*\n(?=[^\d\s-])', table)
                if blank:
                    return None
            raise ValueError('CASH_FLOW_ROW_REQUIRES_TWO_PRINTED_VALUES:' + label)
        match = matches[0]
        page = selected[table[:match.start()].count('\n')][0]
        rows.append(dict(label=label, section=section, physical_page=page,
            evidence_excerpt=match[0], unit='CNY', currency='CNY', statement_scope='consolidated',
            statement_ownership_evidence=[dict(item) for item in ownership],
            columns=[dict(period=f'H1{year}', value=str(Decimal(value.replace(',', ''))))
                     for year, value in zip((current_year, current_year-1), match.groups())]))
    return rows


def _current_cash_conversion_diagnostic(root, analysis, now):
    """Optional source-matched cash counterevidence, never a valuation fallback."""
    unavailable = dict(status='UNAVAILABLE', scope=_CASH_SCOPE, symbol=analysis['symbol'],
        action='no_order', rows=[], normalized_parent_profit_cny=None, primary_valuation_usable=False,
        g3_changed=False, approval_changed=False, price_admitted=False, strategy_admitted=False,
        input_descriptor_sha256=analysis.get('input_descriptor_sha256'),
        candidate_binding=analysis.get('review_binding', {}).get('candidate_binding'),
        formal_eligibility=False, action_admitted=False, source_bindings=[], execution_bindings=[],
        source_spec_binding=None, calculation=None, counter_evidence=None, reason=None,
        explanation='未完成当前绑定原件的适用性与来源核验，不提供现金反证金额。',
        source_retrieved_at=None, source_available_at=None, knowledge_as_of=None,
        historical_pit_admitted=False,
        availability_scope='BOUND_PDF_TIMESTAMPS_NOT_CONTEMPORANEOUS_PIT_OR_HISTORICAL_DIAGNOSTIC')
    try:
        name = 'docs/current/two-company-earnings-bridge-20261024/sources.json'
        raw = (root/name).read_bytes()
        spec_ref = dict(path=name, sha256=sha256(raw).hexdigest())
        spec = json.loads(raw)
        if (spec['schema_version'] != 'two-company-earnings-source-spec-v1'
                or spec['scope'] != 'RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION'
                or spec['action'] != 'no_order' or not isinstance(spec['companies'], dict)):
            raise ValueError('CASH_FLOW_SOURCE_SPEC_UNSUPPORTED')
        declared_sources = spec['companies'].get(analysis['symbol'])
        if declared_sources is None:
            return None
        candidates = [row for row in declared_sources if len(row['periods']) == 2
                      and all(re.fullmatch(r'H1[0-9]{4}', period) for period in row['periods'])]
        if len(candidates) != 1:
            raise ValueError('CASH_FLOW_H1_SOURCE_MISSING_OR_AMBIGUOUS')
        declared = candidates[0]
        current_year = int(declared['periods'][0][2:])
        if declared['periods'][1] != f'H1{current_year-1}':
            raise ValueError('CASH_FLOW_H1_PERIOD_ORDER_INVALID')
        sources = [row for row in analysis['source_catalog'] if row['id'] == declared['source_id']]
        if len(sources) != 1:
            raise ValueError('CURRENT_CASH_FLOW_SOURCE_MISSING_OR_AMBIGUOUS')
        source = sources[0]
        if (declared['symbol'] != analysis['symbol'] or source['sha256'] != declared['sha256']
                or source['kind'] != 'official_issuer_filing'
                or source['location'] != declared['source_url']
                or source['issuer_identity']['security_code'] != analysis['symbol']
                or declared['issuer'] not in source['issuer_identity']['issuer_name']):
            return dict(unavailable, status='SOURCES_DIFFER_FROM_CURRENT_RESEARCH',
                        reason='CURRENT_CASH_FLOW_SOURCE_IDENTITY_MISMATCH')
        ref = dict(path=source['local_path'], sha256=source['sha256'])
        if ref not in analysis['source_bindings']:
            raise ValueError('CURRENT_CASH_FLOW_SOURCE_NOT_IN_CONSUMED_CLOSURE')
        for key in ('source_available_at', 'retrieved_at', 'published_at'):
            if source.get(key):
                _available(source[key], now)
        if source.get('published_at'):
            published = datetime.fromisoformat(source['published_at']).astimezone(timezone(timedelta(hours=8)))
            if published.date().isoformat() != declared['published_date']:
                raise ValueError('CASH_FLOW_DISCLOSURE_DATE_MISMATCH')
        context = [analysis['review_binding'][key] for key in (
            'candidate_binding', 'package_binding', 'workbench_binding', 'review_packet_binding')]
        for binding in [spec_ref, ref, *context, *_CASH_EXECUTION_BINDINGS]:
            _bound(root, binding)
        rows = _cash_flow_rows(extract_pages(root/ref['path']), symbol=analysis['symbol'],
            issuer=source['issuer_identity']['issuer_name'], current_year=current_year)
        if rows is None:
            for binding in [spec_ref, ref, *context, *_CASH_EXECUTION_BINDINGS]:
                _bound(root, binding)
            return dict(unavailable, status='NOT_APPLICABLE',
                reason='TARGET_FINANCIAL_FLOW_ROW_HAS_NO_PRINTED_AMOUNTS_NOT_ASSUMED_ZERO',
                explanation='该合并表的目标金融资金项目未列示金额；不按零推定，也不套用该项目的方向中和计算。',
                source_spec_binding=spec_ref, source_bindings=[ref],
                execution_bindings=[dict(binding) for binding in _CASH_EXECUTION_BINDINGS])
        clocks = [datetime.fromisoformat(source[key]) for key in ('source_available_at', 'retrieved_at')]
        period_end = datetime.fromisoformat(f'{current_year}-06-30T23:59:59+08:00')
        if any(clock.utcoffset() is None or not period_end <= clock <= now for clock in clocks):
            raise ValueError('CASH_FLOW_ACQUISITION_CLOCK_INVALID')
        for row in rows:
            row['source_id'] = declared['source_id']
            row['source_binding'] = dict(ref)
        current, previous = (Decimal(column['value']) for column in rows[0]['columns'])
        flow_now, flow_before = (Decimal(column['value']) for column in rows[1]['columns'])
        with localcontext() as context_decimal:
            context_decimal.prec = 48
            change, contribution = current-previous, flow_before-flow_now
            neutral_now, neutral_before = current+flow_now, previous+flow_before
            fraction = str(contribution/change) if change != 0 else None
        result = dict(unavailable, status='SOURCE_REPLAYED_HISTORICAL_COUNTEREVIDENCE', rows=rows,
            input_descriptor_sha256=analysis['input_descriptor_sha256'],
            candidate_binding=dict(analysis['review_binding']['candidate_binding']),
            source_spec_binding=spec_ref, source_bindings=[ref],
            execution_bindings=[dict(binding) for binding in _CASH_EXECUTION_BINDINGS],
            source_retrieved_at=source['retrieved_at'], source_available_at=source['source_available_at'],
            knowledge_as_of=max(clocks).isoformat(), historical_pit_admitted=False,
            calculation=dict(reported_cfo_change_cny=str(change),
                identified_outflow_direction_contribution_cny=str(contribution),
                contribution_fraction_of_reported_change=fraction,
                current_after_identified_item_cny=str(neutral_now),
                prior_after_identified_item_cny=str(neutral_before),
                remaining_change_cny=str(neutral_now-neutral_before),
                formula='direction_contribution=prior_outflow-current_outflow; neutral_CFO=CFO+printed_outflow'),
            explanation='该项目列在经营现金流出项，负数会增加披露CFO；中和时加回原表有符号金额，不取绝对值。',
            counter_evidence='合并CFO同比变化含金融资金配置方向变化，不能直接归为主营盈利增长、正常化现金或可持续分红。',
            interpretation_limits=['仅中和这一已识别项目，未剔除其他金融、营运资本、税及少数股东影响。',
                '这是合并现金流历史诊断，不是母公司可分配现金；空白金额不推定为零。',
                '不修改正常化利润、原估值、主估值门禁、G3或任何交易权限。'])
        for binding in [spec_ref, ref, *context, *_CASH_EXECUTION_BINDINGS]:
            _bound(root, binding)
        return result
    except (OSError, ValueError, KeyError, TypeError, IndexError, ArithmeticError) as error:
        return dict(unavailable, reason=type(error).__name__ + ':' + str(error))


METHODOLOGY = [
    "https://pages.stern.nyu.edu/adamodar/New_Home_Page/valquestions/highgrowthperiod.htm",
    "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/littlebook/cashflows.htm",
    "https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/returnmeasures.pdf",
]


def _number(value):
    if value is None:
        return None
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Economic input must be finite")
    return result


def _ratio(numerator, denominator):
    return str(numerator / denominator) if denominator is not None and denominator > 0 else None


def _mechanism_explanation(scenarios):
    """Describe consumed scenario mechanics, not inherited proposal prose."""
    if not scenarios:
        raise ValueError('Scenario mechanisms require consumed inputs')
    costs = {_number(row['cost_of_equity']) for row in scenarios}
    spreads = [_number(row['terminal_excess_roe']) for row in scenarios]
    reasons = [
        ('三情景共用权益成本；情景价值差不是资本成本敏感性。' if len(costs) == 1
         else '三情景权益成本不同；价值差还需结合盈利、留存与终端路径解释。')]
    if all(value == 0 for value in spreads):
        reasons.append('各情景终端ROE等于权益成本，永久超额回报归零，但企业价值不等于零。')
        limitation = 'Zero terminal excess return does not prove a neutral valuation or that competitive advantage ends on schedule.'
    elif all(value > 0 for value in spreads):
        reasons.append('各情景终端仍假设超额回报持续；零增长不等于竞争优势消失或估值保守。')
        limitation = 'Positive terminal excess returns require sustained economic advantages; zero growth does not validate that assumption.'
    else:
        reasons.append('终端超额回报并非全部归零，需逐情景核对其方向与持续依据。')
        limitation = 'Terminal excess returns differ by scenario; no common zero-excess-return interpretation is supported.'
    return reasons, limitation


def _operating_review_fields(result):
    return {key: result[key] for key in (
        'schema_version', 'symbol', 'action', 'scope', 'breakdown_status',
        'h1_change', 'annual_change', 'commercial_subtotal', 'unallocated_balances_cny',
        'normalized_parent_profit_cny', 'normalized_range', 'tax_rate_assumption',
        'parent_attribution_assumption', 'normalization_open_items', 'interpretation_limits',
        'g3_changed', 'price_admitted', 'strategy_admitted', 'normalized_earnings_admitted')}


def load_retained_operating_bridge(*, root: Path, symbol: str, now: datetime) -> dict | None:
    """Independent original-statement explanation, never a candidate replay fallback."""
    symbol = normalize_symbol(symbol)
    name = 'docs/current/two-company-earnings-bridge-20261024/sources.json'
    path = root / name
    if not path.exists():
        return None
    unavailable = dict(status='SOURCE_REVALIDATION_FAILED', symbol=symbol, action='no_order',
        context_scope='INDEPENDENT_RETAINED_FILINGS_V1', normalized_parent_profit_cny=None,
        g3_changed=False, price_admitted=False, strategy_admitted=False,
        action_admitted=False, approval_changed=False, primary_valuation_usable=False)
    try:
        raw = path.read_bytes()
        binding = dict(path=name, sha256=sha256(raw).hexdigest())
        spec = json.loads(raw)
        if (spec['schema_version'] != 'two-company-earnings-source-spec-v1'
                or spec['scope'] != 'RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION'
                or spec['action'] != 'no_order'):
            raise ValueError('Unsupported historical source specification')
        items = spec['companies'].get(symbol)
        if items is None:
            return None
        if (len(items) != 2 or any(row['symbol'] != symbol for row in items)
                or len({row['source_id'] for row in items}) != 2):
            raise ValueError('Historical originals require distinct matching issuer sources')
        for ref in _EXECUTED_OPERATING_BINDINGS:
            _bound(root, ref)
        # The retained parser checks actual PDF issuer/year, consolidated scope,
        # amounts, reconciliation and source bytes; no saved result JSON is read.
        result = research_from_retained_sources(root=root,
            specs=[dict(row, fields=spec['common_fields'] + row['extra_fields']) for row in items], now=now)
        review = _operating_review_fields(result)
        if result['symbol'] != symbol or result['action'] != 'no_order':
            raise ValueError('Historical source result belongs to another issuer')
        review.update(status='SOURCE_VERIFIED_HISTORICAL_DRIVERS_NOT_NORMALIZED',
            context_scope='INDEPENDENT_RETAINED_FILINGS_V1',
            action_admitted=False, approval_changed=False, primary_valuation_usable=False,
            read_at=now.isoformat(), report_periods=[row['periods'] for row in items],
            execution_bindings=[dict(ref) for ref in _EXECUTED_OPERATING_BINDINGS],
            historical_ttm_cny=result['ttm']['lines_cny']['ex_parent_profit'],
            source_spec_binding=binding, source_bindings=result['source_bindings'],
            availability_scope='RETAINED_ORIGINAL_RESEARCH_NOT_CONTEMPORANEOUS_PIT_PROOF')
        for ref in [binding, *result['source_bindings'], *_EXECUTED_OPERATING_BINDINGS]:
            _bound(root, dict(path=ref['path'], sha256=ref['sha256']))
        return review
    except (OSError, ValueError, KeyError, TypeError, StopIteration, ArithmeticError, IndexError):
        return unavailable


def _current_operating_bridge(root, analysis, historical, now):
    """Cold-read only the originals already bound to this current research case."""
    name = 'docs/current/two-company-earnings-bridge-20261024/sources.json'
    path = root / name
    if not path.exists():
        return None
    unavailable = dict(status='SOURCE_REVALIDATION_FAILED', symbol=analysis['symbol'],
        action='no_order', normalized_parent_profit_cny=None, g3_changed=False,
        price_admitted=False, strategy_admitted=False)
    try:
        raw = path.read_bytes()
        binding = dict(path=name, sha256=sha256(raw).hexdigest())
        spec = json.loads(raw)
        if (spec['schema_version'] != 'two-company-earnings-source-spec-v1'
                or spec['scope'] != 'RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION'
                or spec['action'] != 'no_order'):
            raise ValueError('Unsupported operating research source specification')
        items = spec['companies'].get(analysis['symbol'])
        if items is None:
            return None
        catalog = {row['id']: row for row in analysis['source_catalog']}
        for item in items:
            if (item['symbol'] != analysis['symbol'] or item['source_id'] not in catalog
                    or catalog[item['source_id']]['sha256'] != item['sha256']):
                return dict(unavailable, status='SOURCES_DIFFER_FROM_CURRENT_RESEARCH')
        result = research_from_retained_sources(root=root,
            specs=[dict(row, fields=spec['common_fields'] + row['extra_fields']) for row in items], now=now)
        if historical is None or _number(result['ttm']['lines_cny']['ex_parent_profit']) != historical:
            return dict(unavailable, status='HISTORICAL_ANCHOR_MISMATCH')
        _bound(root, binding)
        # Expose the computed bridge, not the separately saved author result JSON.
        review = _operating_review_fields(result)
        review.update(status='SOURCE_VERIFIED_HISTORICAL_DRIVERS_NOT_NORMALIZED',
            input_descriptor_sha256=analysis['input_descriptor_sha256'],
            candidate_binding=analysis['review_binding']['candidate_binding'],
            historical_ttm_cny=result['ttm']['lines_cny']['ex_parent_profit'],
            source_spec_binding=binding, source_bindings=result['source_bindings'])
        return review
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return unavailable


def _review_calculations(review: dict, catalog: dict, symbol: str, now: datetime) -> list[dict]:
    """Recalculate the supported historical bridges from their disclosed rows."""
    if not review:
        return []
    if review.get("symbol") != symbol:
        raise ValueError("Financial review belongs to another company")
    facts = {fact["id"]: fact for fact in review["facts"]}
    if len(facts) != len(review["facts"]):
        raise ValueError("Duplicate financial fact ID")
    # These are existing named calculation contracts, not a general formula evaluator.
    signs = {"calendar2025_paid_dividends": (1, 1),
        "calendar2025_parent_partial_cash_proxy": (1, 1, -1),
        "fy2025_plan_dividends": (1, 1),
        "fy_parent_FY2025_cash_capex_proxy": (1, -1),
        "ttm_ex_nonrecurring_parent_profit": (1, 1, -1)}
    cash_periods = {'fy_parent_FY2025_cash_residual': 'FY2025',
                    'h1_parent_H12026_cash_residual': 'H12026'}
    cash_labels = ('经营活动产生的现金流量净额', '投资活动产生的现金流量净额',
        '筹资活动产生的现金流量净额', '汇率变动对现金及现金等价物的影响',
        '现金及现金等价物净增加额', '期初现金及现金等价物余额', '期末现金及现金等价物余额')
    signs.update({name: (1, 1, 1, 1, 0, 1, -1) for name in cash_periods})
    rows = []
    for name, coefficients in signs.items():
        calculation = review.get("calculations", {}).get(name)
        if calculation is None:
            continue
        ids, columns = calculation["input_fact_ids"], calculation["input_column_indices"]
        if len(ids) != len(coefficients) or len(columns) != len(ids):
            raise ValueError("Invalid financial calculation inputs")
        terms, evidence, amounts = [], [], []
        for position, (fact_id, index, sign) in enumerate(zip(ids, columns, coefficients)):
            fact = facts[fact_id]
            source = catalog.get(fact["source_id"])
            binding = fact["source_binding"]
            if (source is None or source["sha256"] != binding["sha256"]
                    or binding["id"] != fact["source_id"]
                    or fact.get("unit") != "CNY" or fact.get("currency") != "CNY"
                    or type(index) is not int or not 0 <= index < len(fact["columns"])):
                raise ValueError("Financial row source, unit or column mismatch")
            expected_scope = ("consolidated_parent_attributable" if name == "ttm_ex_nonrecurring_parent_profit"
                else "listed_parent_external_shareholders_gross_tax" if name in
                {"calendar2025_paid_dividends", "fy2025_plan_dividends"} else "listed_parent_only")
            if fact.get("statement_scope") != expected_scope:
                raise ValueError("Financial calculation mixes ownership scopes")
            for field in ("available_at_conservative", "current_local_verified_at"):
                if binding.get(field):
                    _available(binding[field], now)
            column = fact["columns"][index]
            if name in cash_periods:
                label = ''.join(str(fact.get('label', '')).split())
                if (column['period'] != cash_periods[name] or label != cash_labels[position]
                        or label not in ''.join(str(fact.get('evidence_excerpt', '')).split())
                        or source.get('kind') != 'official_issuer_filing'
                        or binding.get('source_url') != source.get('location')
                        or not str(binding.get('source_url', '')).startswith('https://')
                        or type(fact['physical_page']) is not int or fact['physical_page'] < 1):
                    raise ValueError('Parent cash bridge row label, period or page mismatch')
            if name == "ttm_ex_nonrecurring_parent_profit":
                # Existing official review rows carry their accounting basis in
                # the disclosed label, not in the convenient local fact ID.
                label = "".join(str(fact.get("label", "")).split())
                expected_label = ("\u5f52\u5c5e\u4e8e\u4e0a\u5e02\u516c\u53f8\u80a1\u4e1c\u7684"
                                  "\u6263\u9664\u975e\u7ecf\u5e38\u6027\u635f\u76ca\u7684\u51c0\u5229\u6da6")
                if (label != expected_label or expected_label not in
                        "".join(str(fact.get("evidence_excerpt", "")).split())):
                    raise ValueError("TTM calculation requires disclosed ex-nonrecurring parent profit basis")
                period = {"H12026": "H1_2026", "H12025": "H1_2025"}.get(
                    column["period"], column["period"])
                if period != ("FY2025", "H1_2026", "H1_2025")[position]:
                    raise ValueError("TTM calculation requires ordered distinct FY2025/H1_2026/H1_2025 periods")
            if name in {"calendar2025_parent_partial_cash_proxy", "fy_parent_FY2025_cash_capex_proxy"} and column["period"] != "FY2025":
                raise ValueError("Cash calculation mixes reporting periods")
            amount = _number(column['value'])
            if amount is None:
                raise ValueError('Financial calculation requires an observed amount')
            amounts.append(amount)
            terms.append(sign * amount)
            evidence.append(dict(fact_id=fact_id, source_id=fact["source_id"],
                sha256=binding["sha256"], source_url=binding.get("source_url"),
                physical_page=fact["physical_page"], excerpt=fact["evidence_excerpt"],
                statement_scope=fact["statement_scope"], period=column["period"],
                value=column["value"], coefficient=sign))
            if name in cash_periods:
                evidence[-1]['label'] = label
        computed = sum(terms, Decimal(0))
        if name in cash_periods:
            if (computed != 0 or amounts[4] != amounts[6] - amounts[5]
                    or len({row['source_id'] for row in evidence}) != 1
                    or calculation.get('scope') != 'listed_parent_only'):
                raise ValueError('Parent cash balance or movement does not reconcile')
        if computed != _number(calculation["value"]):
            raise ValueError("Financial calculation does not reconcile")
        rows.append(dict(id=name, **calculation, recomputed_value=str(computed),
            calculation_verified=True, evidence=evidence))
    bridges = {row['id']: row for row in rows if row['id'] in cash_periods}
    if len(bridges) == 2:
        annual = bridges['fy_parent_FY2025_cash_residual']['evidence']
        interim = bridges['h1_parent_H12026_cash_residual']['evidence']
        if _number(annual[6]['value']) != _number(interim[5]['value']):
            raise ValueError('Parent cash bridge periods are not continuous')
    return rows


def load_current_value_economic_assessment(*, root: Path, symbol: str, now: datetime) -> dict | None:
    """Re-derive only the registered current version; malformed sources raise.

    A caller cannot inject an analysis dictionary, a price, or an approval. The
    inherited loader verifies the review packet and recalculates model outputs.
    Diagnostic model cash distributions remain assumptions, never issuer cash.
    """
    root, symbol = root.resolve(), normalize_symbol(symbol)
    analysis = load_current_value_research_analysis(root=root, symbol=symbol, now=now)
    if analysis is None:
        return None
    if analysis["symbol"] != symbol or analysis["action"] != "no_order":
        raise ValueError("Economic assessment identity mismatch")
    catalog = {source["id"]: source for source in analysis["source_catalog"]}
    if len(catalog) != len(analysis["source_catalog"]):
        raise ValueError("Economic assessment requires unique source IDs")
    for source in catalog.values():
        for field in ("source_available_at", "retrieved_at", "published_at"):
            if source.get(field):
                _available(source[field], now)
    for anchor in analysis["official_fact_anchors"]:
        if anchor["source_id"] not in catalog:
            raise ValueError("Economic fact anchor has no bound source")
    inputs = analysis["consumed_operating_inputs"]
    book, shares = _number(inputs["start_book_equity"]), _number(inputs["ordinary_shares"])
    if book <= 0 or shares <= 0:
        raise ValueError("Economic assessment requires positive equity and shares")
    summary = analysis["financial_summary"]
    historical = _number(summary.get("ttm_ex_nonrecurring_parent_profit_cny"))
    normalized = _number(summary.get("normalized_parent_profit_cny"))
    reconciliation = summary.get("historical_profit_reconciliation") or {}
    profit_bridge = dict(status="NOT_AVAILABLE", formula=None, inputs=[], computed_ttm_cny=None)
    if reconciliation:
        if reconciliation.get("symbol") != symbol:
            raise ValueError("Profit reconciliation belongs to another company")
        rows = reconciliation.get("source_rows", [])
        periods = {row["period"]: row for row in rows}
        if len(periods) != len(rows):
            raise ValueError("Duplicate profit bridge period")
        if set(periods) == {"FY2025", "H1_2026", "H1_2025"}:
            for row in rows:
                source = catalog.get(row["source_id"])
                if (source is None or source["sha256"] != row["sha256"]
                        or row.get("currency") != "CNY"
                        or row.get("profit_basis") != "attributable_to_parent"
                        or row.get("statement_scope") != "consolidated"):
                    raise ValueError("Profit bridge source or accounting scope mismatch")
                _bound(root, dict(path=row["path"], sha256=row["sha256"]))
            computed = (_number(periods["FY2025"]["ex_nonrecurring_profit_cny"])
                        + _number(periods["H1_2026"]["ex_nonrecurring_profit_cny"])
                        - _number(periods["H1_2025"]["ex_nonrecurring_profit_cny"]))
            if computed != historical or computed != _number(reconciliation["ttm_ex_nonrecurring_parent_profit_cny"]):
                raise ValueError("Profit bridge does not reconcile")
            profit_bridge = dict(status="HISTORICAL_RECONCILED_NOT_NORMALIZED",
                formula="FY2025 + H1_2026 - H1_2025", inputs=rows, computed_ttm_cny=str(computed))
    scenario_rows = []
    with localcontext() as context:
        context.prec = 48
        for scenario in analysis["scenarios"]:
            given = scenario["inputs"]
            cost = _number(given["cost_of_equity"])
            roes = [_number(value) for value in given["forecast_roes"]]
            if given.get("retention_contract") == V4_RETENTION_CONTRACT:
                typed = scenario_from_payload_v4(given)
                diagnostic_facts = QualityCompounderFacts(
                    symbol=symbol, as_of=now.date(), verified=False,
                    confidence="LOW", evidence_refs=[], blockers=[],
                    operating_inputs=dict(start_book_equity=book, ordinary_shares=shares))
                result = scenario_calculation_v4(diagnostic_facts, typed)
                first_retention = typed.forecast_retentions[0]
            elif given.get("retention_contract") == V3_RETENTION_CONTRACT:
                typed = scenario_from_payload_v3(given)
                diagnostic_facts = QualityCompounderFacts(
                    symbol=symbol, as_of=now.date(), verified=False,
                    confidence="LOW", evidence_refs=[], blockers=[],
                    operating_inputs=dict(start_book_equity=book, ordinary_shares=shares))
                result = scenario_calculation_v3(diagnostic_facts, typed)
                first_retention = typed.forecast_retentions[0]
            elif given.get("retention_contract") == "annual-retention-v2":
                typed = _residual_scenario_from_payload(given)
                diagnostic_facts = QualityCompounderFacts(
                    symbol=symbol, as_of=now.date(), verified=False,
                    confidence="LOW", evidence_refs=[], blockers=[],
                    operating_inputs=dict(start_book_equity=book, ordinary_shares=shares))
                result = scenario_calculation(diagnostic_facts, typed)
                first_retention = typed.forecast_retentions[0]
            else:
                result = scenario_value(book, shares, cost, dict(
                    forecast_roe=roes, terminal_roe=given["terminal_roe"],
                    terminal_growth=given["terminal_growth"], retention=given["retention"]))
                first_retention = _number(given["retention"])
            years = result["forecast_years"]
            first, last = _number(years[0]["net_income_assumption_cny"]), _number(years[-1]["net_income_assumption_cny"])
            scenario_rows.append(dict(scenario=scenario["scenario"],
                dated_per_share_value=scenario["per_share_value"],
                diagnostic_basis="UNDATED_BOOK_BASIS_NOT_REPLACEMENT_FOR_DATED_VALUATION",
                first_year_profit_cny=str(first),
                first_year_profit_to_historical_ttm=_ratio(first, historical),
                first_year_dividend_assumption_cny=years[0]["dividend_assumption_cny"],
                first_year_payout_ratio=str(1 - first_retention),
                explicit_years=len(roes), years_above_equity_cost=sum(roe > cost for roe in roes),
                first_year_excess_roe=str(roes[0] - cost),
                final_explicit_profit_cny=str(last),
                explicit_profit_cagr=(str((last / first) ** (Decimal(1) / (len(roes) - 1)) - 1)
                    if first > 0 and last > 0 and len(roes) > 1 else None),
                terminal_excess_roe=str(_number(given["terminal_roe"]) - cost),
                cost_of_equity=str(cost), terminal_growth=given["terminal_growth"],
                terminal_spread=str(cost - _number(given["terminal_growth"])),
                terminal_growth_status=result.get("terminal_growth_status"),
                terminal_value_method=result.get("terminal_value_method"),
                terminal_value_error_kind=result.get("terminal_value_error_kind"),
                terminal_economic_uncertainty_status=result.get(
                    "terminal_economic_uncertainty_status"),
                terminal_residual_contribution_ratio=result["terminal_residual_contribution_ratio"],
                dividend_ri_reconciliation_cny=result["dividend_crosscheck_difference_cny"],
                implied_expectation_scope="REGISTERED_SCENARIO_CONDITIONS_NOT_MARKET_IMPLIED",
                cash_distribution_scope="SELF_FUNDED_MODEL_ASSUMPTION_NOT_SUSTAINABLE_ISSUER_DIVIDEND"))
    short_fade = summary.get("pending_model_choice") == "short-advantage"
    mechanism_reasons, mechanism_limitation = _mechanism_explanation(scenario_rows)
    blockers = ["NORMALIZED_EARNINGS_NOT_ESTABLISHED", "SUSTAINABLE_DISTRIBUTABLE_CASH_NOT_ESTABLISHED",
        "ADVANTAGE_DURATION_AND_FADE_NOT_ECONOMICALLY_VALIDATED",
        "EQUITY_COST_INPUTS_REQUIRE_EXACT_VERSION_REVIEW", "CURRENT_MODEL_VALIDITY_REQUIRES_EVENT_REVIEW"]
    if short_fade:
        blockers.append("SHORT_ADVANTAGE_STRESS_IS_NOT_NEUTRAL_PRIMARY_VALUATION")
    historical_calculations = _review_calculations(
        summary.get("verified_financial_review") or {}, catalog, symbol, now)
    cash_rows = [row for row in historical_calculations if row["id"] != "ttm_ex_nonrecurring_parent_profit"]
    for row in historical_calculations:
        if row["id"] == "ttm_ex_nonrecurring_parent_profit":
            if _number(row["recomputed_value"]) != historical:
                raise ValueError("Financial review and earnings anchor differ")
            profit_bridge = dict(status="HISTORICAL_RECONCILED_NOT_NORMALIZED", formula=row["formula"],
                inputs=row["evidence"], computed_ttm_cny=row["recomputed_value"])
    cash_by_id = {row["id"]: row for row in cash_rows}
    cash_diagnostics = []
    paid = cash_by_id.get("calendar2025_paid_dividends")
    proxy = cash_by_id.get("calendar2025_parent_partial_cash_proxy")
    if paid is not None and proxy is not None:
        numerator, denominator = _number(proxy["recomputed_value"]), _number(paid["recomputed_value"])
        with localcontext() as context:
            context.prec = 48
            cash_diagnostics.append(dict(id="CALENDAR2025_PARTIAL_PARENT_CASH_TO_PAID_DIVIDEND",
                numerator_cny=str(numerator), denominator_cny=str(denominator),
                ratio=_ratio(numerator, denominator), difference_cny=str(numerator - denominator),
                evidence_calculation_ids=[proxy["id"], paid["id"]],
                scope="HISTORICAL_PARTIAL_PROXY_NOT_SUSTAINABILITY_OR_DISTRIBUTABLE_CASH",
                limitation="Investment cash can include nonrecurring receipts; financing, required liquidity, legal restrictions and future investment remain unbridged."))
    tasks = [
        dict(id="NORMALIZED_EARNINGS", question="Bridge reported and ex-nonrecurring profit to recurring after-tax parent earnings; quantify maintenance and accounting adjustments without pre-tax addbacks.", evidence_fields=["financial_summary", "official_fact_anchors"]),
        dict(id="CASH_RETURN", question="Reconcile parent cash, subsidiary upstreaming, mandatory investment, debt and distribution restrictions; distinguish payment calendar from profit year.", evidence_fields=["historical_cash_observations", "source_catalog"]),
        dict(id="PRIMARY_MODEL", question="Support the advantage duration and fade with business evidence; compare a continuity case against the stress and explain clean-surplus adjustments.", evidence_fields=["scenarios", "counter_evidence"]),
        dict(id="EQUITY_COST", question="Review dated CNY nominal risk-free, equity premium and beta inputs for this equity scope, with source dates and sensitivity.", evidence_fields=["assumptions", "sensitivity"]),
        dict(id="CURRENT_EXPECTATIONS", question="Use an independently verified PriceBridge and a bounded registered inverse model; report no solution rather than extending parameter bounds.", evidence_fields=["review_binding"]),
    ]
    accounting_review = _build_economic_review_bundle(root=root, analysis=analysis, now=now)
    # The outer assessment already records the same cutoff; omit the volatile
    # nested timestamp to keep its content fingerprint stable across replays.
    accounting_review.pop("evaluated_at")
    result = dict(schema_version="value-economic-assessment-v1", symbol=symbol, action="no_order",
        accounting_bridge_review=accounting_review,
        status="ECONOMIC_DIAGNOSTICS_COMPLETE_PRIMARY_NOT_ESTABLISHED", assessed_at=now.isoformat(),
        input_descriptor_sha256=analysis["input_descriptor_sha256"], review_binding=analysis["review_binding"],
        research_as_of=analysis["research_as_of"], valuation_date=analysis["valuation_date"],
        economic_assumptions_reviewed=False, primary_valuation_usable=False,
        strategy_admitted=False, action_admitted=False, approval_changed=False,
        model_applicability=dict(model=analysis["model_applicability"]["route"],
            assessment="STRESS_ONLY" if short_fade else "CONTINUITY_ALTERNATIVE_REQUIRES_VALIDATION",
            reasons=mechanism_reasons,
            historical_proposal_limits=summary.get("pending_model_limits", []),
            clean_surplus_bridge=summary.get("financial_equity_bridge"),
            limitation=mechanism_limitation),
        earnings=dict(historical_ex_nonrecurring_ttm_cny=str(historical) if historical is not None else None,
            normalized_parent_profit_candidate_cny=str(normalized) if normalized is not None else None,
            normalization_status="NOT_ESTABLISHED", historical_bridge=profit_bridge,
            note="Period-end equity ratios and next-year model profit are not disclosed weighted ROE or normalized earnings."),
        scenarios=scenario_rows, historical_cash_observations=cash_rows,
        cash_return_diagnostics=cash_diagnostics,
        sustainable_distribution_status="NOT_ESTABLISHED",
        reverse_expectations=dict(status="REQUIRES_VERIFIED_PRICEBRIDGE_AND_REGISTERED_INVERSE",
            market_implied_result=None, registered_scenario_conditions=scenario_rows),
        sensitivity=analysis["sensitivity"], assumptions=analysis["assumptions"],
        counter_evidence=analysis["counter_evidence"], thesis_breakers=analysis["thesis_breakers"],
        official_fact_anchors=analysis["official_fact_anchors"], source_catalog=analysis["source_catalog"],
        source_bindings=analysis["source_bindings"], blockers=blockers, next_verifications=tasks,
        methodology_sources=METHODOLOGY)
    operating_bridge = _current_operating_bridge(root, analysis, historical, now)
    if operating_bridge is not None:
        result['earnings']['operating_quality_bridge'] = operating_bridge
        if operating_bridge['status'] == 'SOURCE_VERIFIED_HISTORICAL_DRIVERS_NOT_NORMALIZED':
            for binding in [operating_bridge['source_spec_binding'], *(
                    dict(path=source['path'], sha256=source['sha256'])
                    for source in operating_bridge['source_bindings'])]:
                if binding not in result['source_bindings']:
                    result['source_bindings'].append(binding)
    cash_conversion = _current_cash_conversion_diagnostic(root, analysis, now)
    if cash_conversion is not None:
        result['cash_conversion_diagnostic'] = cash_conversion
        if cash_conversion['status'] in {'SOURCE_REPLAYED_HISTORICAL_COUNTEREVIDENCE', 'NOT_APPLICABLE'}:
            for binding in [cash_conversion['source_spec_binding'], *cash_conversion['source_bindings'],
                            *cash_conversion['execution_bindings']]:
                if binding not in result['source_bindings']:
                    result['source_bindings'].append(binding)
    for binding in result["source_bindings"]:
        _bound(root, binding)
    content = {key: value for key, value in result.items() if key != "assessed_at"}
    result["assessment_sha256"] = sha256(json.dumps(content, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()
    return result

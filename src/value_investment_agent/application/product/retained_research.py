"""Append retained case evidence without replacing already delivered research."""
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

from .common import load_json_object, require_inside, sha256_bytes, sha256_file
from .product_workbench_candidate import _project_prospective_baseline
from .prospective_baseline import _verify_fact_text


_DISPLAY = {
    'mature_manufacturing': '成熟制造业',
    'cyclical_cash_return': '周期性现金回报企业',
    'Segment margin, cash conversion and reinvestment efficiency.': '分部利润率、现金转换及再投资效率。',
    'Normalized coal price/cost, power and transport contribution, capex discipline and distribution capacity.':
        '正常化煤价与成本、电力及运输贡献、资本开支纪律和可持续分配能力。',
    'Segment margin declined while volumes and revenue grew; durable economics cannot be inferred.':
        '销量和收入增长时分部利润率下降，不能据此认定盈利能力可持续。',
    'Revenue, operating profit, operating cash flow and coal price all declined in reported 2025 figures.':
        '2025 年披露的收入、营业利润、经营现金流和煤价均下降。',
    'PARTIAL: household and commercial/industrial segments are disclosed, but competitive durability remains unverified.':
        '已披露家用及商业/工业业务分部，但竞争优势的持久性尚未独立核实。',
    'PARTIAL: integrated coal, power and transport operations are disclosed; durable advantage is not independently proven.':
        '已披露煤炭、电力、运输一体化业务；优势的持久性尚未独立证明。',
    'DATA_INCOMPLETE: no independently time-bound baseline package for dividends, buybacks and debt is registered.':
        '分红、回购和债务尚缺完整的时点化资本配置证据包。',
    'PARTIAL: capex is reported but maintenance versus growth and sustainable distribution capacity remain unresolved.':
        '已披露资本开支，但维持与增长投入拆分、可持续分配能力尚未核定。',
    'DATA_INCOMPLETE.': '资料尚未齐全。',
    'DATA_INCOMPLETE: ordinary and special distributions are not normalized.':
        '普通与特别分红尚未完成正常化研究。',
    'MODEL_NOT_READY: existing segment facts do not establish verified FCFF scope, share denominator, capex split or WACC.':
        'FCFF 模型所需工业/金融业务口径、普通股股数、资本开支拆分和资本成本尚未闭合。',
    'CYCLICAL_MODEL_NOT_READY: reported cycle profit does not establish normalized earnings, unit cost or maintenance capex.':
        '周期模型所需正常化利润、单位成本和维持性资本开支尚未闭合。',
    'independent available_at for retained PDF': '原件独立可用时间依据',
    'maintenance versus growth capex': '维持性与增长性资本开支拆分',
    'ordinary-share denominator': '普通股股数口径',
    'WACC': '加权平均资本成本',
    'normalized commodity price range': '正常化商品价格区间',
    'unit-cost reconciliation': '单位成本勾稽',
    'maintenance capex': '维持性资本开支',
    'ordinary versus special dividend': '普通与特别分红分类',
}


def extend_retained_research_payload(*, root: Path, payload: dict,
                                    snapshot_path: Path, snapshot_sha256: str) -> dict:
    """Reuse the registered baseline projection, then append missing cases only.

    This reads sealed evidence, not the research scheduler. Gate approval,
    intrinsic-value calculation and current quote admission are out of scope.
    """
    source = require_inside(root, root / snapshot_path, 'retained research snapshot')
    if sha256_file(source) != snapshot_sha256:
        raise ValueError('retained research snapshot hash mismatch')
    snapshot = load_json_object(source, 'retained research snapshot')
    cutoff = date.fromisoformat(payload['as_of'])
    built = datetime.fromisoformat(snapshot['built_at'])
    if built.utcoffset() is None or built.date() > cutoff:
        raise ValueError('retained research observation exceeds product date')
    existing = {card['symbol']: card for card in payload['companies']}
    if len(existing) != len(payload['companies']):
        raise ValueError('duplicate existing research company')
    registered = {card['symbol']: card for card in snapshot['cards']}
    if not set(existing).issubset(registered):
        raise ValueError('existing research falls outside retained registered cases')
    if any(card['company_name'] != registered[symbol]['company'] for symbol, card in existing.items()):
        raise ValueError('retained company identity conflicts with delivered research')
    additions = set(registered) - set(existing)
    if not additions:
        raise ValueError('retained research adds no missing company')

    scratch = deepcopy(payload)
    scratch.update(companies=[], opportunities=[], today_items=[])
    scratch['audit'] = {'evidence': []}
    _project_prospective_baseline(scratch, root=root, snapshot_path=snapshot_path,
                                  snapshot_sha256=snapshot_sha256)
    for symbol in additions:
        for fact in registered[symbol]['known_facts']:
            available = datetime.fromisoformat(fact['available_at'])
            if available.utcoffset() is None or available.date() > cutoff:
                raise ValueError('retained fact exceeds product date')
            original = require_inside(root, root / fact['source_path'], 'retained fact original')
            content = original.read_bytes()
            if sha256_bytes(content) != fact['source_sha256']:
                raise ValueError('retained fact original changed during read')
            _verify_fact_text(content, fact, {'report_period': fact['report_period']})

    result = deepcopy(payload)
    selected = [card for card in scratch['companies'] if card['symbol'] in additions]
    section_sources = {'business_quality': 'business_quality',
                       'capital_allocation': 'capital_allocation', 'valuation': 'model_applicability',
                       'dividend': 'dividend_sustainability', 'risks_counterevidence': 'strongest_counterevidence'}
    for card in selected:
        original = registered[card['symbol']]
        count = len(original['known_facts'])
        card['latest_change'] = f'封存基线 {built.date()}：重新核对 {count} 项报告事实；不代表当前完整研究通过。'
        card['next_trigger'] = next(item['next_trigger'] for item in scratch['opportunities']
                                    if item['symbol'] == card['symbol'])
        card['original_thesis'] = '尚未形成获批准的投资论点；研究回报驱动：' + _DISPLAY.get(original['return_drivers'], original['return_drivers'])
        for section in card['sections']:
            if section['key'] in section_sources:
                text = original[section_sources[section['key']]]
                section['summary'] = _DISPLAY.get(text, text)
            elif section['key'] == 'financial_quality':
                section['summary'] = f'{count} 项报告披露事实已核对；财务质量、现金归属与完整事实门尚未通过。年报和半年报不得直接计算同比。'
        rows = {row['label']: row['value'] for row in card['decision_review']}
        rows['前瞻研究画像'] = _DISPLAY.get(original['profile'], original['profile'])
        rows['基线证据覆盖'] = f'{count} 项封存报告事实重新核对；{len(original["unadmitted_fact_ids"])} 项仍待核验。不是完整财务或严格历史时点准入。'
        rows['估值模型适用性'] = _DISPLAY.get(original['model_applicability'], original['model_applicability'])
        rows['最强反证'] = _DISPLAY.get(original['strongest_counterevidence'], original['strongest_counterevidence'])
        rows['尚缺证据'] = '；'.join(_DISPLAY.get(text, text) for text in original['unknowns'])
        rows['预期回报来源'] = _DISPLAY.get(original['return_drivers'], original['return_drivers'])
        rows['事实解释边界'] = '归母利润和合并现金流归属不同，不计算现金转换比率；半年报不年化，不把已披露现金流当作可分红现金或 FCFF。'
        card['decision_review'] = [{'label': label, 'value': value} for label, value in rows.items()]
        for step in card['decision_process']:
            if step['key'] == 'financial_facts':
                step['reason'] = f'已重核 {count} 项报告事实，但这不等于完整 FinancialFacts、财务质量及严格历史可得性门通过。'
            elif step['key'] == 'model_applicability':
                step['reason'] = rows['估值模型适用性']
            elif step['key'] == 'business_quality':
                step['reason'] = '已有封存业务解释与反证，但未形成完整独立商业质量及 Thesis 批准。'

    refs = {ref for card in selected for ref in card['evidence_refs']}
    source_urls = {f'prospective-{symbol}-fact-{index}': fact['source_url']
                   for symbol in additions for index, fact in enumerate(registered[symbol]['known_facts'], 1)}
    audit = {item['evidence_id']: item for item in result['audit']['evidence']}
    for record in scratch['audit']['evidence']:
        if record['evidence_id'] not in refs:
            continue
        if record['evidence_id'] in source_urls:
            record['source_url'] = source_urls[record['evidence_id']]
        previous = audit.get(record['evidence_id'])
        if previous is not None and previous != record:
            raise ValueError('retained research evidence identity conflict')
        audit[record['evidence_id']] = record
    result['audit']['evidence'] = list(audit.values())
    result['companies'].extend(selected)
    new_opportunities = [card for card in scratch['opportunities'] if card['symbol'] in additions]
    for card in new_opportunities:
        original = registered[card['symbol']]
        card['why_now'] = f'已登记研究对象；封存基线 {built.date()} 中 {len(original["known_facts"])} 项报告事实已重核。不是新筛选机会或买入推荐。'
        card['main_risk'] = '估值尚未就绪；' + _DISPLAY.get(original['strongest_counterevidence'], original['strongest_counterevidence'])
    result['opportunities'].extend(new_opportunities)
    result['overview']['pending_count'] = payload['overview']['pending_count'] + len(new_opportunities)
    result['today_items'].extend(dict(item, what_happened=f'封存基线 {built.date()} 的财务事实已接入共享研究卡。')
                                 for item in scratch['today_items'] if item.get('symbol') in additions)
    result['system_health']['message'] = f'已登记 {len(result["companies"])} 家公司使用同一研究展示路径；各自事实、估值与缺项分开。当前不生成买卖指令或个性化仓位。'
    if sha256_file(source) != snapshot_sha256:
        raise ValueError('retained research changed during composition')
    return result

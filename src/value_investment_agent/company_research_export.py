"""Pinned historical research display, isolated from decision inputs."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path


PACK = 'runtime/company-research/600519-20260909T032233545655Z/evidence.json'
PACK_HASH = 'b4f3af37564519de73164bc3f92bef2dfbab2e62fbd3108c368c96d3ab2c9e68'
ANNUAL_PACK = 'runtime/strategy-validation/moutai-warmup-20260909T062823719664Z/annual-inputs.json'
ANNUAL_HASH = '41f7d1fb196adc6840ea43bb58ddf57a38116334410a4ee61b589ac4bfc231fc'
DISTRIBUTION_DIR = 'runtime/strategy-validation/moutai-distributions-20260909T063018977769Z'
DISTRIBUTION_MANIFEST_HASH = '1939a45d9a7d24a875632117d531c7313df4f86e6b7e67b3f1879cdcd1d2988f'
TTM_PACK = 'runtime/company-research/600519-ttm-scope-20260909T072356118039Z/evidence.json'
TTM_HASH = '2d518b72fc2c9b8a60663c1f64121bfa45247de6262668db44ab656f27b6c57e'

FORECAST_PACKS = {
    'conditional_dcf': ('600519-conditional-operating-dcf-20260909T123857151905Z', '931d9234f3e473b50ec30f4c65fb4e08deb263f9a34fd9babc780d9f5037372b'),
    'operating': ('600519-operating-forecast-20260909T104143099320Z', 'cb52c2b0ac4b7b8474b1afd30a726845a995a14739d8f91ea872256f58b6f2bb'),
    'reinvestment': ('600519-reinvestment-basis-20260909T104614530208Z', '00fe8a450a5cd1e60d9ad1da181886df4bf88e4bd3e88fd196f198c3c1fad370'),
    'tax': ('600519-tax-forecast-basis-20260909T104847206196Z', 'e8c5e16b66cda8ec9a00c025964a3be05bf6dfe09508b2b7ee2e4e108c8d7c70'),
    'nwc': ('600519-nwc-sensitivity-20260909T114536573711Z', '1e198cdfd8ba276147ec4eb1c5a6bf77d3ba62f5323619d244c3f13d270a4c42'),
}


def load_end_to_end_case(root: Path) -> str:
    """Return the latest immutable one-stock case status, if it was generated."""
    pointer = root / 'runtime/company-research/600519-end-to-end-case-latest.json'
    if not pointer.exists():
        return '单股票完整流程案例尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'evidence.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Latest single-stock case evidence changed')
    case = json.loads(path.read_text(encoding='utf-8'))
    if (case.get('symbol') != '600519' or case.get('run_type') != 'research_simulation'
            or case.get('trade_approved') is not False or case.get('decision', {}).get('state') != 'research_only'):
        raise ValueError('Single-stock case approval scope changed')
    return (
        f"单股票流程案例已生成：{reference['path']}。数据快照、648组条件估值、5832组敏感性、"
        '2015-2025历史回放和官方指数对照已由同一案例包关联；当前状态为研究模拟，禁止交易。'
    )


def load_paper_decision_status(root: Path) -> str:
    """Surface the latest immutable daily paper-decision trace in Excel."""
    pointer = root / 'runtime/strategy-validation/moutai-paper-decisions-latest.json'
    if not pointer.exists():
        return '逐日模拟决策记录尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    summary_path = (root / reference['path'] / 'summary.json').resolve()
    if (not summary_path.is_relative_to(root.resolve())
            or hashlib.sha256(summary_path.read_bytes()).hexdigest() != reference['summary_sha256']):
        raise ValueError('Latest paper-decision summary changed')
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    if (summary.get('symbol') != '600519' or summary.get('rule_version') != 'moutai-paper-state-v1'
            or summary.get('trade_approved') is not False or summary.get('orders') != 0
            or summary.get('strategy_backtest_complete') is not False):
        raise ValueError('Paper-decision approval scope changed')
    legacy = summary.get('legacy_reference') or {}
    if legacy.get('status') and not str(legacy['status']).startswith('PE18/PB4 equal blend'):
        raise ValueError('Unexpected legacy reference scope')
    return (
        f"逐日模拟决策已重放{summary['rows']}个交易日（{summary['first_date']}至{summary['last_date']}）："
        f"{summary['states'].get('blocked', 0)}日阻断、{summary['orders']}笔订单。"
        '原因是历史合理价值、模拟账户及执行准入尚未完成；该记录证明门禁链路，不能证明策略收益。'
        '旧PE18/PB4等权参考价已逐日保留为反证，不是DCF、合理价或交易阈值。'
    )


def load_historical_admission_status(root: Path) -> str:
    pointer = root / 'runtime/strategy-validation/moutai-historical-admission-latest.json'
    if not pointer.exists():
        return '历史策略准入缺口审计尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'evidence.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Historical admission evidence changed')
    audit = json.loads(path.read_text(encoding='utf-8'))
    values = audit.get('historical_value') or {}
    admission = audit.get('admission') or {}
    if (audit.get('symbol') != '600519' or audit.get('sessions') != 2674
            or values.get('approved_sessions') != 0 or admission.get('historical_trade_backtest_complete') is not False
            or admission.get('trade_approved') is not False):
        raise ValueError('Historical admission scope changed')
    capital = audit.get('capital_and_distribution') or {}
    return (
        f"历史策略准入审计：2674日中已批准的点时历史价值为{values['approved_sessions']}日。"
        f"另有{capital.get('sessions_after_disclosed_distribution')}日需补分红权益确认桥接、"
        f"2025回购计划后{capital.get('sessions_after_2025_repurchase_program_start')}日中，"
        f"{capital.get('sessions_with_disclosed_repurchase_snapshot')}日有披露进度快照、"
        f"{capital.get('sessions_without_disclosed_repurchase_snapshot')}日无快照；库存股与每股价值分母仍未匹配。"
        '因此尚未形成真实策略收益回测，不能以持有对照替代。'
    )


def load_historical_conditional_input_status(root: Path) -> str:
    """Surface the bounded historical FCFF input package without promoting it to value."""
    pointer = root / 'runtime/strategy-validation/moutai-historical-conditional-inputs-latest.json'
    if not pointer.exists():
        return '历史条件估值输入包尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'evidence.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Historical conditional-input evidence changed')
    package = json.loads(path.read_text(encoding='utf-8'))
    cases = package.get('input_cases') or []
    if (package.get('symbol') != '600519' or package.get('version') != 'moutai-historical-conditional-inputs-v1'
            or package.get('case_count') != 12 or len(cases) != 12 or package.get('formal_fair_value') is not None
            or package.get('trade_approved') is not False or package.get('strategy_backtest_complete') is not False):
        raise ValueError('Historical conditional-input approval scope changed')
    if any(case.get('trade_approved') is not False or case.get('formal_fair_value') is not None
           or case.get('conditional_value') is not None
           or not str((case.get('source') or {}).get('source_url', '')).startswith('https://static.cninfo.com.cn/')
           or not (case.get('source') or {}).get('annual_report_document_hash') for case in cases):
        raise ValueError('Historical conditional inputs were promoted to values')
    return (
        '历史条件估值输入包：已按当时可用日期冻结12个年报版本，原公告URL、归档路径及Hash均已逐份核验；逐个保留经营小计、资本投入、'
        '营运资本、现金税、共享成本和股本分母的有限情景。它只定义研究输入，不生成条件价值、'
        '正式合理价或交易价值；共有成本、现金税及库存股/分红分母缺口仍阻断交易。'
    )


def load_historical_input_timeline_status(root: Path) -> str:
    pointer = root / 'runtime/strategy-validation/moutai-historical-input-timeline-latest.json'
    if not pointer.exists():
        return '历史逐日条件输入时间线尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'summary.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Historical input timeline changed')
    summary = json.loads(path.read_text(encoding='utf-8'))
    if (summary.get('symbol') != '600519' or summary.get('sessions') != 2674
            or summary.get('input_cases') != 12 or summary.get('point_in_time_violations') != 0
            or summary.get('formal_fair_value') is not None or summary.get('trade_approved') is not False):
        raise ValueError('Historical input timeline scope changed')
    return ('逐日历史输入时间线：2674个交易日均仅绑定当时已披露的12个年度输入版本，点时性违规为0；'
            '这证明输入可用性，不代表已有历史合理价、策略收益或交易批准。')


def load_historical_conditional_replay_status(root: Path) -> str:
    """Display the isolated historical DCF experiment without promoting it."""
    pointer = root / 'runtime/strategy-validation/moutai-historical-conditional-replay-latest.json'
    if not pointer.exists():
        return '历史条件估值重放尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'summary.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Historical conditional replay evidence changed')
    summary = json.loads(path.read_text(encoding='utf-8'))
    if (summary.get('symbol') != '600519' or summary.get('rule_version') not in {
            'moutai-historical-conditional-dcf-v1', 'moutai-historical-conditional-dcf-v2-shared-cost-only'}
        or summary.get('sessions') != 2674 or summary.get('sessions_with_experimental_range') != 2603
        or summary.get('formal_fair_value') is not None or summary.get('valuation_approved') is not False
        or summary.get('trade_approved') is not False or summary.get('strategy_backtest_complete') is not False):
        raise ValueError('Historical conditional replay approval scope changed')
    return ('历史条件估值重放：2674个交易日均只使用当时已披露年报；2603日得到固定有限情景的实验DCF范围，'
            '71日因首个报告期缺上年营运资本而阻断。该范围不是正式合理价，不得进入买卖、回测收益或账户准入。')


def load_blocked_paper_ledger_status(root: Path) -> str:
    pointer = root / 'runtime/strategy-validation/moutai-blocked-paper-ledger-latest.json'
    if not pointer.exists():
        return '逐日阻断式纸面账本尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'summary.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Blocked paper-ledger evidence changed')
    summary = json.loads(path.read_text(encoding='utf-8'))
    if (summary.get('symbol') != '600519' or summary.get('sessions') != 2674
            or summary.get('orders') != 0 or summary.get('executions') != 0
            or summary.get('performance_available') is not False or summary.get('trade_approved') is not False):
        raise ValueError('Blocked paper-ledger scope changed')
    return ('逐日阻断式纸面账本：2674日均保存决策证据及下一可成交日；账户资金、净值、订单和成交均为空或为0，'
            '没有策略绩效。它是后续真实模拟账户的接口，不构成回测或交易准入。')


def load_simulation_closure_status(root: Path) -> str:
    """Show the auditable virtual-account acceptance run without promoting it."""
    pointer = root / 'runtime/strategy-validation/moutai-simulation-closure-latest.json'
    if not pointer.exists():
        return '模拟执行闭环验收尚未运行。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'summary.json').resolve()
    if (not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']):
        raise ValueError('Simulation closure evidence changed')
    summary = json.loads(path.read_text(encoding='utf-8'))
    closure_dir = path.parent
    contract_manifest = closure_dir / 'real-contract' / 'manifest.json'
    contract_input = closure_dir / 'real-contract' / 'input.json'
    if not contract_manifest.is_file() or not contract_input.is_file():
        raise ValueError('Simulation closure real execution contract is missing')
    contract_outputs = json.loads(contract_manifest.read_text(encoding='utf-8')).get('outputs') or {}
    if hashlib.sha256(contract_input.read_bytes()).hexdigest() != contract_outputs.get('input.json'):
        raise ValueError('Simulation closure real execution input changed')
    contract = json.loads(contract_input.read_text(encoding='utf-8'))
    sessions = contract.get('sessions') or []
    real = summary.get('real_history') or {}
    synthetic = summary.get('synthetic_execution_validation') or {}
    current = summary.get('current_observation')
    if (summary.get('symbol') != '600519' or summary.get('run_type') != 'simulation_closure_acceptance'
            or real.get('sessions') != 2674 or real.get('cash_events') != 15
            or real.get('filled_orders') != 0 or real.get('second_run_new_journal_rows') != 0
            or real.get('fee_model') != 'historical_sse'
            or synthetic.get('second_run_new_journal_rows') != 0
            or synthetic.get('fee_model') != 'flat'
            or synthetic.get('generated_decision_states') != ['proposed_entry', 'proposed_reduce']
            or synthetic.get('generated_quantities') != [300, 100]
            or synthetic.get('sizing_policy_scope') != 'research_only_p2_position_sizing_experiment'
            or summary.get('execution_mechanics_verified') is not True
            or summary.get('simulation_eligible') is not False
            or summary.get('valuation_approved') is not False
            or summary.get('trade_approved') is not False or summary.get('live_eligible') is not False):
        raise ValueError('Simulation closure approval scope changed')
    calendar_audit = contract.get('sse_calendar_audit') or {}
    suspension_audit = contract.get('sse_suspension_audit') or {}
    if (contract.get('symbol') != '600519'
            or contract.get('contract_version') != 'moutai-real-execution-input-v5'
            or len(sessions) != real['sessions']
            or not sessions
            or sessions[0].get('execution_status') != 'first_archived_bar_no_prior_close'
            or any(session.get('execution_status') != 'daily_bar_execution_not_admitted' for session in sessions[1:])
            or any(session.get('next_open_fill_eligible') is not False for session in sessions)
            or calendar_audit.get('calendar_approved') is not True
            or calendar_audit.get('execution_approved') is not False
            or calendar_audit.get('sse_open_dates') != real['sessions']
            or suspension_audit.get('queried_windows') != 4
            or suspension_audit.get('official_returned_record_count') != 0
            or suspension_audit.get('status') != 'no_official_listed_stop_resume_records_returned'
            or suspension_audit.get('execution_approved') is not False):
        raise ValueError('Simulation closure execution-state scope changed')
    current_text = ''
    if current is not None:
        account = current.get('paper_account_snapshot') or {}
        replay = current.get('idempotent_replay') or {}
        if (current.get('quote_session_verified') is not True
                or current.get('action') != 'no_order'
                or account.get('cash_cny') != '1000000.00'
                or account.get('shares') != 0 or account.get('nav_cny') != '1000000.00'
                or account.get('journal_rows') != 0
                or replay.get('new_orders') != 0 or replay.get('new_fills') != 0
                or replay.get('new_journal_rows') != 0):
            raise ValueError('Simulation closure current-observation scope changed')
        current_text = (
            '本次当前双源会话已验证，观察/无订单；独立研究账户保持100万元、0股、0笔新增账本，'
            '未伪造次日开盘成交价；相同观察重跑仍为0笔订单、0笔成交、0笔账本变动；'
        )
    return (
        '模拟执行闭环验收：真实历史输入覆盖2674个交易日和15条现金分派；因估值尚未准入，真实路径0笔订单，'
        f"首次记账{real.get('first_run_new_journal_rows')}行，重复运行新增{real.get('second_run_new_journal_rows')}行。"
        f"合成机制路径由状态机与仓位实验生成建仓300股、减仓100股，首次成交{synthetic.get('first_run_filled_orders')}笔，重复运行新增{synthetic.get('second_run_new_journal_rows')}行；"
        '上交所交易日历和四段官方停复牌查询已核验，日线涨跌幅已筛查；该历史回执使用旧全拒绝执行契约，不能证明真实成交。保守日线模拟契约及必要成本、流动性约束尚待接通；'
        '执行机制已验证，但估值准入、真实决策链、历史策略证据和模拟准入均未完成；'
        + current_text
        +
        '仅验证T+1、费用、现金、持仓与幂等性，不是历史策略收益、合理价或实盘建议。'
    )


def load_experimental_signal_coverage_status(root: Path) -> str:
    pointer = root / 'runtime/strategy-validation/moutai-experimental-signal-coverage-latest.json'
    if not pointer.exists():
        return '条件估值安全边际覆盖预检尚未运行。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'evidence.json').resolve()
    if (not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']):
        raise ValueError('Experimental signal-coverage evidence changed')
    result = json.loads(path.read_text(encoding='utf-8'))
    coverage = result.get('range_endpoint_safety_margin_coverage') or {}
    lower = coverage.get('lower') or {}
    midpoint = coverage.get('midpoint') or {}
    upper = coverage.get('upper') or {}
    if (result.get('symbol') != '600519' or result.get('sessions') != 2674
            or result.get('sessions_with_experimental_range') != 2603
            or any(lower.get(key, {}).get('sessions') != 0 for key in ('0.20', '0.30', '0.40'))
            or midpoint.get('0.20', {}).get('sessions') != 12
            or any(midpoint.get(key, {}).get('sessions') != 0 for key in ('0.30', '0.40'))
            or [upper.get(key, {}).get('sessions') for key in ('0.20', '0.30', '0.40')] != [491, 150, 54]
            or result.get('trade_approved') is not False):
        raise ValueError('Experimental signal-coverage scope changed')
    return ('条件估值反证预检（区间覆盖审计）：2603日有实验范围；下端在20%/30%/40%均为0个信号，中点仅20%有12日，'
            '上端分别有491/150/54日。端点差异重大，未选上端制造买点；这不是策略收益、正式合理价或实盘建议。')


def load_historical_range_experiment_status(root: Path) -> str:
    """Show every endpoint/margin replay without turning it into a strategy claim."""
    pointer = root / 'runtime/strategy-validation/moutai-historical-range-experiment-latest.json'
    if not pointer.exists():
        return '历史区间逐笔研究实验尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'result.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Historical range experiment result changed')
    result = json.loads(path.read_text(encoding='utf-8'))
    rows = result.get('results') or []
    by_name = {row.get('scenario'): row for row in rows}
    expected_fills = {
        'lower-20pct': 0, 'lower-30pct': 0, 'lower-40pct': 0,
        'midpoint-20pct': 2, 'midpoint-30pct': 0, 'midpoint-40pct': 0,
        'upper-20pct': 4, 'upper-30pct': 4, 'upper-40pct': 2,
    }
    expected_periods = ['development', 'validation', 'sealed_test']
    period_map = {row.get('scenario'): row.get('periods') or [] for row in rows}
    if (result.get('symbol') != '600519' or result.get('run_type') != 'historical_research_range_sensitivity'
            or result.get('window') != ['2015-01-05', '2025-12-31'] or result.get('sessions') != 2674
            or len(rows) != 9 or {name: by_name.get(name, {}).get('fills') for name in expected_fills} != expected_fills
            or by_name['upper-20pct'].get('rejected_orders') != 4
            or any([item.get('period') for item in periods] != expected_periods for periods in period_map.values())
            or any(any(item.get('fills') != 0 for item in periods[1:]) for periods in period_map.values())
            or any(result.get(key) is not False for key in ('valuation_approved', 'strategy_backtest_complete',
                                                             'simulation_eligible', 'trade_approved', 'live_eligible'))
            or result.get('formal_fair_value') is not None):
        raise ValueError('Historical range experiment approval scope changed')
    return ('历史区间逐笔研究实验：下端三档均0笔成交；中点20%为2笔；上端20%/30%/40%为4/4/2笔，'
            '其中上端20%另有4笔拒单保留。全部成交均在2015-2019开发期，2020-2022验证期和2023-2025封存测试期均为0笔；'
            '因此没有样本外交易证据。全部为8%单股上限下的研究账本，未对齐税后基准且日线成交可行性未证实；'
            '不是通过回测、正式合理价、模拟准入或实盘建议。')


def load_current_execution_contract_status(root: Path) -> str:
    """Display dated paper-execution mechanics without promoting an order."""
    pointer = root / 'runtime/strategy-validation/moutai-current-execution-contract-latest.json'
    if not pointer.exists():
        return '日线纸面执行契约尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'evidence.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Current execution-contract evidence changed')
    contract = json.loads(path.read_text(encoding='utf-8'))
    if (contract.get('symbol') != '600519' or contract.get('contract_version') != 'current-next-session-paper-execution-v1'
            or contract.get('execution_ready') is not True or contract.get('blockers') != []
            or contract.get('trade_approved') is not False or contract.get('live_eligible') is not False
            or Decimal(contract['price_limit_down']) <= 0 or Decimal(contract['price_limit_up']) <= 0
            or Decimal(contract['liquidity_budget_cny']) <= 0 or Decimal(contract['slippage_bps']) < 0
            or set(contract.get('evidence') or {}) != {'quote', 'suspension', 'fee_policy', 'liquidity'}):
        raise ValueError('Current execution-contract scope changed')
    return (f"日线纸面执行契约：{contract['observed_session']}会话对应{contract['valid_session']}下一会话；"
            f"涨跌停区间{contract['price_limit_down']}/{contract['price_limit_up']}元，"
            f"研究滑点{contract['slippage_bps']}bp，前已知流动性预算{contract['liquidity_budget_cny']}元。"
            '行情、停复牌、费用和流动性证据均已Hash绑定；仅执行机械条件已登记，不构成估值、订单或实盘准入。')


def load_cash_anchor_paper_contract_status(root: Path) -> str:
    """Show the separate research-simulation replay without promoting its value."""
    pointer = root / 'runtime/strategy-validation/moutai-cash-anchor-paper-contract-latest.json'
    if not pointer.exists():
        return '现金分派锚定研究模拟契约尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'summary.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['summary_sha256']:
        raise ValueError('Cash-anchor paper-contract summary changed')
    summary = json.loads(path.read_text(encoding='utf-8'))
    if (summary.get('symbol') != '600519' or summary.get('rule_version') != 'moutai-cash-anchor-paper-contract-v1'
            or summary.get('sessions') != 2674 or summary.get('blocked_before_cash_observation') != 364
            or summary.get('research_model_decision_sessions') != 2310 or summary.get('proposed_orders') != 0
            or summary.get('research_simulation_eligible') is not True or summary.get('formal_fair_value') is not None
            or summary.get('valuation_approved') is not False or summary.get('trade_approved') is not False):
        raise ValueError('Cash-anchor paper-contract scope changed')
    return ('现金分派锚定研究模拟：364日因尚无已实施年度现金观察而阻断，2310日按点时保守端点完成模型评估；'
            '既定30%安全边际下0笔订单。真实虚拟账本两次运行已覆盖2674个交易日且重复运行不新增账本行；'
            '这是自然零交易研究回放，不是正式合理价、策略收益或实盘建议。')


def load_pe_mid_paper_contract_status(root: Path) -> str:
    """Display the isolated median-PE experiment without promoting it to advice."""
    v2_pointer = root / 'runtime/strategy-validation/moutai-pe-mid-paper-contract-v2-latest.json'
    if v2_pointer.exists():
        reference = json.loads(v2_pointer.read_text(encoding='utf-8'))
        path = (root / reference['path'] / 'summary.json').resolve()
        if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['summary_sha256']:
            raise ValueError('Median-PE v2 paper-contract summary changed')
        summary = json.loads(path.read_text(encoding='utf-8'))
        context = summary.get('share_event_context', {})
        if (summary.get('symbol') != '600519'
                or summary.get('rule_version') != 'moutai-pe-mid-paper-contract-v2-2025-extension'
                or summary.get('window_end') != '2025-12-31' or summary.get('sessions') != 2674
                or summary.get('cash_events') != 15 or summary.get('blocked_sessions') != 252
                or summary.get('research_decision_sessions') != 2422 or summary.get('proposed_entries') != 1
                or summary.get('proposed_exits') != 0 or summary.get('2025_sessions') != 243
                or context.get('contemporaneous_expected_cancellation_available_at') != '2025-08-31T00:00:00+08:00'
                or context.get('ex_post_confirmation_prohibited_for_2025_decisions') is not True
                or summary.get('formal_fair_value') is not None or summary.get('valuation_approved') is not False
                or summary.get('trade_approved') is not False):
            raise ValueError('Median-PE v2 paper-contract scope changed')
        return ('中位历史PE研究实验v2：保留v1，另将相同规则延至2015-2025；252日样本不足阻断、2422日研究评估，'
                '固定30%安全边际仅1次研究入场、0次退出。2025年243个交易日仅使用当时已披露EPS；'
                '8月30日公告在8月31日后仅作为预计注销的公司行动上下文，年报事后确认不得倒灌。'
                '相对PE不是内在价值，此实验不构成策略收益、正式合理价或实盘建议。')
    pointer = root / 'runtime/strategy-validation/moutai-pe-mid-paper-contract-latest.json'
    if not pointer.exists():
        return '中位历史PE研究实验尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'summary.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['summary_sha256']:
        raise ValueError('Median-PE paper-contract summary changed')
    summary = json.loads(path.read_text(encoding='utf-8'))
    if (summary.get('symbol') != '600519' or summary.get('rule_version') != 'moutai-pe-mid-paper-contract-v1'
            or summary.get('window_end') != '2024-12-31' or summary.get('sessions') != 2431
            or summary.get('cash_events') != 13 or summary.get('blocked_sessions') != 252
            or summary.get('research_decision_sessions') != 2179 or summary.get('proposed_entries') != 1
            or summary.get('proposed_exits') != 0 or summary.get('formal_fair_value') is not None
            or summary.get('valuation_approved') is not False or summary.get('trade_approved') is not False):
        raise ValueError('Median-PE paper-contract scope changed')
    return ('中位历史PE研究实验：仅用2015-2024已覆盖送股/分红窗口，252日样本不足阻断、2179日研究评估；'
            '固定30%安全边际仅1次研究入场、0次退出。2025回购/注销范围未覆盖而排除；'
            '相对PE不是内在价值，此实验不构成策略收益、正式合理价或实盘建议。')


def load_midea_admission_status(root: Path) -> str:
    pointer = root / 'runtime/company-research/midea-admission-audit-latest.json'
    if not pointer.exists():
        return '美的研究准入审计尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'evidence.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Midea admission-audit evidence changed')
    audit = json.loads(path.read_text(encoding='utf-8'))
    if (audit.get('symbol') != '000333' or audit.get('research_state') != 'watch'
            or audit.get('action') != 'no_order'
            or audit.get('blocking_gate_ids') != ['financial_scope', 'per_share_scope', 'formal_valuation']
            or audit.get('facts', {}).get('research_ttm_parent_attributable_net_income_cny') != 44721506000
            or audit.get('facts', {}).get('execution_sessions') != 2621
            or audit.get('formal_fair_value') is not None or audit.get('trade_approved') is not False):
        raise ValueError('Midea admission-audit scope changed')
    return ('美的准入审计：研究跟踪/禁止下单。TTM归母利润447.22亿元为研究级勾稽事实；'
            '2621个归档交易日及5段整日停牌约束可用于后续执行研究，另有1日部分停牌阻断。'
            '加权普通股、A/H与库存股分母、正式估值尚未通过；不计算EPS、合理价、安全边际、仓位或买卖点。')


def load_current_valuation_admission_status(root: Path) -> str:
    pointer = root / 'runtime/company-research/600519-current-valuation-admission-latest.json'
    if not pointer.exists():
        return '当前正式合理价准入审计尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'evidence.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Current valuation-admission evidence changed')
    audit = json.loads(path.read_text(encoding='utf-8'))
    separated = audit.get('admission_version') == 'current-valuation-admission-v3'
    expected = ['parent_equity_scope', 'model_arithmetic', 'cost_of_equity_selection', 'forward_assumptions',
                'current_share_capital_actions']
    expected_blocking = []
    if not separated:
        expected.extend(['historical_execution', 'market_session', 'paper_execution'])
        expected_blocking.append('historical_execution')
    allowed_blocking = [] if audit.get('p1_current_model_admitted') is True else ['current_share_capital_actions']
    expected_conclusion = ('admitted_for_bounded_current_paper_research'
                           if not allowed_blocking else 'not_admitted_for_specified_simulation')
    if (audit.get('symbol') != '600519' or audit.get('formal_fair_value') is not None
            or audit.get('valuation_approved') is not False or audit.get('trade_approved') is not False
            or [gate.get('id') for gate in audit.get('gates', [])] != expected
            or audit.get('blocking_gate_ids') != allowed_blocking):
        raise ValueError('Current valuation-admission scope changed')
    assessment = audit.get('model_scope_assessment') or {}
    if (assessment.get('conclusion') != expected_conclusion
            or assessment.get('primary_model', {}).get('name') != 'consolidated_parent_equity_residual_income_or_dividend_capacity'
            or assessment.get('cross_check', {}).get('name') != 'cash_distribution_anchored_equity_range'):
        raise ValueError('Current valuation model-scope assessment changed')
    p1_reference = audit.get('p1_model_contract_evidence') or {}
    p1_path = (root / p1_reference.get('path', '')).resolve()
    if (not p1_path.is_relative_to(root.resolve()) or not p1_path.is_file()
            or hashlib.sha256(p1_path.read_bytes()).hexdigest() != p1_reference.get('sha256')):
        raise ValueError('P1 model-contract evidence changed')
    p1_contract = json.loads(p1_path.read_text(encoding='utf-8'))
    expected_contract = 'moutai-p1-model-contract-v4' if p1_contract.get('contract_version') == 'moutai-p1-model-contract-v4' else ('moutai-p1-model-contract-v3' if separated else 'moutai-p1-model-contract-v2')
    if (p1_contract.get('contract_version') != expected_contract
            or p1_contract.get('specified_simulation_eligible') is not False
            or p1_contract.get('formal_fair_value') is not None
            or p1_contract.get('trade_approved') is not False):
        raise ValueError('P1 model-contract admission changed')
    context = {gate['id']: gate['passed'] for gate in (audit.get('context_checks', []) if separated else audit['gates'])}
    market_text = ('归档双源收盘价及上交所会话已验证，需按该会话日期阅读；' if context.get('market_session') is True
                   else '归档双源收盘价或上交所会话尚未验证；')
    execution_text = ('虚拟账户执行机制已验证；' if context.get('paper_execution') is True
                      else '虚拟账户执行机制尚未验证；')
    model_text = ''
    if separated:
        model_ref = p1_contract['inputs']['current_model'] if expected_contract == 'moutai-p1-model-contract-v4' else p1_contract['inputs']['conditional_model']
        model_path = (root / model_ref['path']).resolve()
        if (not model_path.is_relative_to(root.resolve())
                or hashlib.sha256(model_path.read_bytes()).hexdigest() != model_ref['sha256']):
            raise ValueError('Primary conditional model evidence changed')
        model = json.loads(model_path.read_text(encoding='utf-8'))
        value_key = 'conditional_value_per_current_disclosed_share_cny' if expected_contract == 'moutai-p1-model-contract-v4' else 'conditional_value_per_2025_issued_share_cny'
        values = ' / '.join(f"{Decimal(row[value_key]):.2f}" for row in model['results'])
        model_text = ('研究日剩余收益条件值：悲观/基准/乐观为' + values
                      + '元，仅限研究日条件比较，尚非当前合理价或买卖阈值。')
        if model.get('facts', {}).get('report_published_date'):
            model_text += ('年报披露日' + model['facts']['report_published_date']
                           + '，日期级可用时间' + model['facts']['report_available_at']
                           + '；股数取自原文股份表，非股本金额换算。')
    if separated and not allowed_blocking:
        remaining = 'P1当前模型已完成限定纸面研究准入；P2仍须绑定日线状态、流动性、限价与账户执行条款，历史执行单独验收；'
    elif separated:
        remaining = 'P1当前模型已撤回：资本动作证据在原估值时点之后取得，不能倒填为当时已知；当前合理价、纸面交易输入和任何订单均被阻断，待下一交易日重建完整时点一致的证据链；'
    else:
        remaining = '资本成本单点选择、前瞻ROE/留存、当前股本/资本动作和历史执行仍未通过；'
    return ('正式合理价准入审计：' + market_text + execution_text
            + 'P1模型契约已冻结：候选主模型为合并归母权益残余收益/分红能力模型；账面权益、归母利润和股本范围一致，条件值仅用于已登记研究日期。'
            + model_text + remaining + '旧经营FCFF DCF及权益桥接保留为反证研究；'
            '当前合理价为空，不得生成买卖指令。')


def load_current_conditional_observation(root: Path) -> str:
    pointer = root / 'runtime/company-research/600519-current-conditional-observation-latest.json'
    if not pointer.exists():
        return '当前条件研究观察尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'evidence.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Current conditional observation evidence changed')
    observation = json.loads(path.read_text(encoding='utf-8'))
    scenarios = observation.get('scenarios') or []
    common_scope = (
        observation.get('symbol') == '600519'
        and observation.get('research_state') == 'watch'
        and observation.get('action') == 'no_order'
        and observation.get('valuation_approved') is False
        and observation.get('simulation_eligible') is False
        and observation.get('trade_approved') is False
        and observation.get('live_eligible') is False
        and isinstance(observation.get('quote_session_verified'), bool)
    )
    if not common_scope:
        raise ValueError('Current conditional observation scope changed')
    reason_codes = set(observation.get('reason_codes') or [])
    if not scenarios:
        if (observation.get('observation_version') != 'moutai-primary-conditional-observation-v2'
                or observation.get('quote_session_verified') is not True
                or 'current_model_not_same_date_as_quote_session' not in reason_codes):
            raise ValueError('Current conditional observation zero-scenario scope changed')
        return ('当前条件研究观察：报价交易会话已验证，但模型日期与报价会话不一致；'
                '未计算安全边际、不生成订单。正式合理价、模拟、交易及实盘准入仍未通过。')
    if len(scenarios) != 3:
        raise ValueError('Current conditional observation scenario scope changed')
    values = ' / '.join(f"{Decimal(row['conditional_value_per_share_cny']):.2f}" for row in scenarios)
    session_text = ('该报价的上交所交易会话已验证；' if observation['quote_session_verified']
                    else '该报价的上交所交易会话尚未验收；')
    qualifying = sum(row.get('meets_30pct_entry_experiment') is True for row in scenarios)
    return ('当前条件研究观察：悲观/基准/乐观条件每股值为' + values + '元；'
            + f'{qualifying}/3个情景达到单项30%价差条件。'
            + session_text + '报表日估值与所列报价仅作条件比较，当前权益桥接及模型尚未批准；'
            '状态为观察且不生成订单，单项价差不等于可买入。')


def load_finance_cost_scope_sensitivity_status(root: Path) -> str:
    pointer = root / 'runtime/company-research/600519-finance-cost-sensitivity-latest.json'
    if not pointer.exists():
        return '财务公司成本尺度敏感性尚未生成。'
    reference = json.loads(pointer.read_text(encoding='utf-8'))
    path = (root / reference['path'] / 'evidence.json').resolve()
    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Finance-cost sensitivity evidence changed')
    result = json.loads(path.read_text(encoding='utf-8'))
    representatives = result.get('representative_scenarios') or []
    if (result.get('symbol') != '600519' or len(result.get('results') or []) != 1296
            or result.get('robust_no_entry_under_this_sensitivity') is not True
            or any(result.get(key) is not False for key in ('scope_approved', 'valuation_approved',
                                                            'simulation_eligible', 'trade_approved', 'live_eligible'))
            or [group.get('scenario') for group in representatives] != ['bear', 'base', 'bull']
            or any(len(group.get('rows') or []) != 2 for group in representatives)):
        raise ValueError('Finance-cost sensitivity scope changed')
    values = ' / '.join(f"{Decimal(group['rows'][1]['adjusted_conditional_value_per_share_cny']):.2f}"
                        for group in representatives)
    scale = Decimal(result['finance_reference_scale']['annualized_reference_scale_cny']) / Decimal('1e8')
    return ('财务公司成本尺度敏感性：以收入减税前利润年化%.2f亿元作反事实尺度后，'
            '悲观/基准/乐观条件每股值为%s元，仍均低于观察价；'
            '该差额不是费用分摊或上界，不能解除估值和交易门禁。' % (scale, values))


def verify_forecast_research(root: Path) -> dict:
    packs = {}
    for name, (directory, expected) in FORECAST_PACKS.items():
        raw = (root / 'runtime/company-research' / directory / 'evidence.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Forecast research changed: ' + name)
        packs[name] = json.loads(raw)
        if packs[name]['symbol'] != '600519':
            raise ValueError('Forecast company mismatch')
    for reference in packs['operating']['source_bindings']:
        source = (root / reference['path']).resolve()
        if not source.is_relative_to(root.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest() != reference['sha256']:
            raise ValueError('Forecast original changed')
    if (packs['operating']['equity_value_approved'] is not False
            or packs['reinvestment']['industrial_reinvestment_approved'] is not False
            or packs['tax']['cash_tax_approved'] is not False
            or packs['nwc']['complete_industrial_nwc'] is not False):
        raise ValueError('Forecast approval scope changed; review display')
    dcf = packs['conditional_dcf']
    if (dcf['valuation_approved'] is not False or dcf['strategy_approved'] is not False
            or dcf['fair_value_per_share'] is not None or dcf['equity_bridge'] is not None
            or len(dcf['results']) != 54):
        raise ValueError('Conditional DCF scope changed; review display')
    return packs


def verify_latest_research(root: Path) -> dict:
    raw = (root / TTM_PACK).read_bytes()
    if hashlib.sha256(raw).hexdigest() != TTM_HASH:
        raise ValueError('Latest TTM research package changed')
    data = json.loads(raw)
    if (data['symbol'] != '600519' or data['period_end'] != '2026-06-30'
            or data['reported_flow_research_supported'] is not True
            or any(data[key] is not False for key in ('normalized_earnings_approved',
                   'fcff_approved', 'current_eps_approved', 'trade_value_approved'))):
        raise ValueError('Unexpected latest research scope')
    checked = set()
    for metric in data['ttm'].values():
        if metric['comparative_matches_original'] is not True:
            raise ValueError('Latest comparative not reconciled')
        for row in metric['input_rows']:
            source = (root / row['path']).resolve()
            key = (source, row['sha256'])
            if key in checked:
                continue
            if not source.is_relative_to(root.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('Latest research original changed')
            checked.add(key)
    return data


def verify_distribution_research(root: Path) -> dict:
    directory = root / DISTRIBUTION_DIR
    raw = (directory / 'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DISTRIBUTION_MANIFEST_HASH:
        raise ValueError('Distribution replay manifest changed')
    for name, expected in json.loads(raw)['outputs'].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Distribution replay output changed')
    for reference in json.loads((directory / 'input-references.json').read_text(encoding='utf-8')):
        path = (root / reference['path']).resolve()
        if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
            raise ValueError('Distribution replay input changed')
    result = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
    if result['strategy_backtest_complete'] is not False or result['economic_evidence'] != 'not_evaluated':
        raise ValueError('Unexpected distribution replay approval scope')
    return result


def verify_annual_research(root: Path) -> None:
    raw = (root / ANNUAL_PACK).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ANNUAL_HASH:
        raise ValueError('Historical annual input package changed')
    rows = json.loads(raw)
    if [r['report_year'] for r in rows] != list(range(2013, 2025)):
        raise ValueError('Historical annual input coverage changed')
    for row in rows:
        source = (root / row['source_path']).resolve()
        if not source.is_relative_to(root.resolve()):
            raise ValueError('Historical annual source escapes project')
        if hashlib.sha256(source.read_bytes()).hexdigest() != row['raw_file_hash']:
            raise ValueError('Historical annual original changed')
        if row['symbol'] != '600519' or row['trade_input_approved'] is not False:
            raise ValueError('Unexpected historical research scope')


def load_company_research(root: Path) -> dict:
    backtest_dir = root / 'runtime/strategy-validation/moutai-account-comparison-20260909T145827486266Z'
    manifest_raw = (backtest_dir / 'manifest.json').read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != '36d1a7053283de31d151e39bc60755ec98bdc63a71ba98811b4eac885ea49d5a':
        raise ValueError('Account comparison manifest changed')
    for name, expected in json.loads(manifest_raw)['outputs'].items():
        path = (backtest_dir / name).resolve()
        if not path.is_relative_to(backtest_dir.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Account comparison output changed')
    account = json.loads((backtest_dir / 'result.json').read_text(encoding='utf-8'))
    metrics = json.loads((backtest_dir / 'path-metrics.json').read_text(encoding='utf-8'))['hold']
    if account['strategy_approved'] is not False or account['certified_excess_return'] is not None:
        raise ValueError('Account comparison approval changed; review display')
    if len(account['summary']) != 6 or any(r['legacy_orders'] != 0 for r in account['summary']):
        raise ValueError('Legacy zero-order display is stale')
    backtest_text = (
        '历史研究回放2015-2025：旧规则六组均零交易。买入持有对照首笔投入96%，分红留现金；'
        f"100万元期末{Decimal(account['independent_ending_hold_equity_cny']) / Decimal('10000'):.2f}万元，"
        f"最大回撤{Decimal(metrics['full']['max_drawdown']):.2%}，"
        f"2023-2025账面变动{Decimal(metrics['2023-2025']['marked_return']):.2%}。"
        '这是持有对照，不是价值策略收益；最终税费、成交约束及宽基全收益未验收。'
    )
    benchmark_raw = (root / 'runtime/strategy-validation/moutai-official-benchmark-comparison-20260909T162649301451Z/evidence.json').read_bytes()
    if hashlib.sha256(benchmark_raw).hexdigest() != 'b93c0d0bce6dc40519b6cc965688a5e92c8cce9683e636e5db057e707661b3f8':
        raise ValueError('Official benchmark comparison changed')
    benchmark = json.loads(benchmark_raw)
    if benchmark['net_alpha_approved'] is not False or benchmark['strategy_approved'] is not False or benchmark['rows'] != 2674:
        raise ValueError('Benchmark comparison scope changed')
    recent = benchmark['metrics']['2023-2025']
    backtest_text += (
        f"官方全收益研究对照2023-2025：沪深300 {Decimal(recent['H00300']['return']):+.2%}，"
        f"主要消费 {Decimal(recent['H00932']['return']):+.2%}。"
        '指数为税费前分红再投资，持有账户分红留现金，不能直接解释为净超额收益；两条额外日期原样隔离，方法和独立数据核验未完成。'
        '基准原始接口：https://www.csindex.com.cn/csindex-home/perf/index-perf。'
    )
    integrated_raw = (root / 'runtime/company-research/600519-integrated-conditional-equity-20260909T142721122559Z/evidence.json').read_bytes()
    if hashlib.sha256(integrated_raw).hexdigest() != '67e908b43a33700442267796e71a75e91b93430cd749de9fe1392e3d01eff6bc':
        raise ValueError('Integrated equity research changed')
    integrated = json.loads(integrated_raw)
    if (integrated['valuation_approved'] is not False or integrated['strategy_approved'] is not False
            or integrated['industrial_financial_scope_approved'] is not False or len(integrated['results']) != 648):
        raise ValueError('Integrated research approval scope changed')
    sensitivity_raw = (root / 'runtime/company-research/600519-equity-sensitivity-20260909T164014633417Z/evidence.json').read_bytes()
    if hashlib.sha256(sensitivity_raw).hexdigest() != '85b068ffadeb747bb1b7b7441ecb9bdc15437e393aeddf84aa09ae5ab6220323':
        raise ValueError('Integrated equity sensitivity changed')
    sensitivity = json.loads(sensitivity_raw)
    if sensitivity['grid_rows'] != 648 or sensitivity['valuation_approved'] is not False:
        raise ValueError('Integrated sensitivity scope changed')
    separated_raw = (root / 'runtime/company-research/600519-separated-rates-20260909T165254638416Z/evidence.json').read_bytes()
    if hashlib.sha256(separated_raw).hexdigest() != 'd53ab67705671c685acbae261ed7f427d6e5c0285d07874b8c6850085cac1106':
        raise ValueError('Separate-rate research changed')
    separated = json.loads(separated_raw)
    if (separated['equal_rate_cases_reproduced'] != 648 or len(separated['results']) != 5832
            or separated['valuation_approved'] is not False or separated['strategy_approved'] is not False):
        raise ValueError('Separate-rate approval scope changed')
    sensitivity_text = (
        '经营/金融/少数权益回报率已分别实验5832组，原648组同率结果复现。其他条件不变，'
        f"经营折现率平均每股影响{Decimal(separated['rate_comparisons']['operating_rate']['mean_span']):.2f}元，"
        f"金融权益{Decimal(separated['rate_comparisons']['finance_equity_rate']['mean_span']):.2f}元，"
        f"少数权益{Decimal(separated['rate_comparisons']['minority_equity_rate']['mean_span']):.2f}元。"
        '6%/8%/10%仍是实验，不是批准资本成本；幅度不是预期涨幅或置信区间。共享费用仍未拆清，不能视作不重要。'
    )
    trademark_raw = (root / 'runtime/company-research/600519-trademark-basis-20260909T170630619991Z/evidence.json').read_bytes()
    if hashlib.sha256(trademark_raw).hexdigest() != '05aecb23891642668e87201c6acae011fe6093b714346e0273f5f1b7649ae1fb':
        raise ValueError('Trademark cost evidence changed')
    trademark = json.loads(trademark_raw)
    if trademark['future_proposal_shareholder_approved'] is not True or trademark['forecast_approved'] is not False:
        raise ValueError('Trademark approval scope changed')
    trademark_text = (
        f"2026H1商标费占管理费{Decimal(trademark['share_of_reported_admin']):.2%}；1.5%只适用于合同计费基数。"
        f"全部酒类收入直接乘费率会多算{Decimal(trademark['naive_fee_minus_reported_fee'])/Decimal('10000'):.2f}万元。"
        '2027-2029季度支付议案已获股东会通过，但开票基数及具体付款日待核；不得在现有管理费之外再加一遍。'
    )
    scenarios = integrated['representative_scenarios']
    if [r['scenario'] for r in scenarios] != ['bear', 'base', 'bull']:
        raise ValueError('Integrated scenario identity changed')
    trial_values = ' / '.join(f"{Decimal(r['conditional_value_per_disclosed_share']):.2f}" for r in scenarios)
    event_raw = (root / 'runtime/company-research/600519-current-share-price-review-20260909T134816842261Z/evidence.json').read_bytes()
    if hashlib.sha256(event_raw).hexdigest() != '7dcfcd3ac0428d7f8eca9eb3781c5360dcfc46e0f601b3e47a9e83e9666dea0a':
        raise ValueError('Current company events changed')
    event = json.loads(event_raw)
    if event['symbol'] != '600519' or event['valuation_approved'] is not False:
        raise ValueError('Current event approval scope changed')
    peer_path = root / 'runtime/company-research/000858-revision-replay-20260909T131721971494Z/evidence.json'
    peer_raw = peer_path.read_bytes()
    if hashlib.sha256(peer_raw).hexdigest() != 'c9536b4609a27c21d0d02650069b551fd07413608c0da2a5457f7e44ac568524':
        raise ValueError('Peer correction research changed')
    peer = json.loads(peer_raw)
    if peer['symbol'] != '000858' or peer['checks_passed'] != 14 or peer['historical_backtest_complete'] is not False:
        raise ValueError('Peer correction research scope changed')
    forecast = verify_forecast_research(root)
    latest = verify_latest_research(root)
    verify_annual_research(root)
    distributions = verify_distribution_research(root)
    raw = (root / PACK).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PACK_HASH:
        raise ValueError('Company research package changed; review before publication')
    data = json.loads(raw)
    source = (root / data['source_path']).resolve()
    if not source.is_relative_to(root.resolve()):
        raise ValueError('Research source escapes project')
    if hashlib.sha256(source.read_bytes()).hexdigest() != data['source_sha256']:
        raise ValueError('Company research original changed')
    if data['symbol'] != '600519' or data['report_year'] != 2024:
        raise ValueError('Unexpected company research identity')
    if not all(data['arithmetic_checks'].values()) or data['current_valuation_approved']:
        raise ValueError('Unexpected research validation scope')
    # Excel cells cap text at 32,767 characters. Put the current no-order
    # conclusion and the newest replay at the front so historic evidence cannot
    # hide a material gate behind a truncated cell tail.
    case_status = (load_current_valuation_admission_status(root) + load_current_conditional_observation(root)
                   + load_current_execution_contract_status(root) + load_experimental_signal_coverage_status(root) + load_historical_range_experiment_status(root)
                   + load_cash_anchor_paper_contract_status(root)
                   + load_pe_mid_paper_contract_status(root) + load_finance_cost_scope_sensitivity_status(root)
                   + load_end_to_end_case(root) + load_paper_decision_status(root)
                   + load_historical_admission_status(root) + load_historical_conditional_input_status(root)
                   + load_historical_input_timeline_status(root) + load_historical_conditional_replay_status(root)
                   + load_blocked_paper_ledger_status(root) + load_simulation_closure_status(root))
    return {'600519': [
        f"截至2026-06-30报告口径TTM：收入{Decimal(latest['ttm']['revenue']['value']) / Decimal('1e8'):.2f}亿元、"
        f"归母利润{Decimal(latest['ttm']['parent_profit']['value']) / Decimal('1e8'):.2f}亿元；"
        f'条件每股试算（悲观/基准/乐观）：{trial_values}元。不是正式合理价或买卖价格。'
        '经营、现金、税资本、金融和少数权益已整合；648组复算通过。代表组8%回报、2025资本开支、60天现金缓冲。'
        '7月调价已作为量价综合压力假设评审，不额外叠加涨价收益。',
        '系列酒收入下降而成本上升，基准恢复假设可能失效；合并CFO包含财务公司资金。'
        f"TTM资本开支{Decimal(forecast['reinvestment']['ttm']['cash_capex']) / Decimal('1e8'):.2f}亿元，低支出不能永久外推。"
        '营运资本已同时排除应付及预缴所得税，避免与现金税重复；仍含季节性薪酬及未分类往来款。'
        + trademark_text +
        '同行反证：五粮液2026H1收入同比+20.87%使用更正后的低基数；销售费用率14.89%升至22.25%，经营现金流-21.54亿元，不据此上调茅台增长。'
        '更正原文：https://static.cninfo.com.cn/finalpage/2026-04-30/1225273122.PDF；当前中报：https://static.cninfo.com.cn/finalpage/2026-08-29/1225531252.PDF。',
        case_status + '研究试算：工业DCF共有管理费/税费归属未拆清，单列金融利息和财务费用原已排除，不能再次加回；六月余额和披露股数沿用至九月。税资本及分派能力假设未验收。'
        '详见D盘最新整合估值报告，不能按试算值计算有效买入线。'
        + sensitivity_text + backtest_text + '尚无批准的合理价或买卖指令。研究更新2026-09-10，不代表行情刷新。',
        'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF',
    ], '000333': [
        '家电制造研究跟踪：已归档2014-2024年度总股本事实，以及2025年A/H月度与注销完成观察；'
        '这些是股本范围研究证据，不是可直接相除的EPS分母。',
        '主要风险：A/H与库存股时点、加权普通股和独立原件范围尚未闭合；'
        '历史日线含部分停牌会话，不能以日线替代盘中可成交性。',
        load_midea_admission_status(root),
        'https://static.cninfo.com.cn/finalpage/2025-12-23/1224890769.PDF',
    ]}

"""User-readable report text without changing observation semantics."""
from decimal import Decimal
from html import escape


def render_hotspot_markdown(report):
    lines = ['# 热点研究观察', '', '仅供研究，未获交易准入，不产生订单。',
             f"市场原文采集时间：{report['market_snapshot_acquired_at']}（不是交易日期）。",
             '行业快照交易日期未知；以下报价只证明各证券所列日期，不代表全市场日期。',
             '', '## 带日期报价', '', '| 证券代码 | 报价日期 | 价格（元） | 核验状态 |',
             '| --- | --- | ---: | --- |']
    for quote in report['dated_quote_observations']:
        valid = quote['status'] == 'DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION'
        lines.append(f"| {quote['symbol']} | {quote.get('quote_date') or '未知'} | {quote.get('price') if valid else '未知'} | {'双源日期与价格一致，未获价格准入' if valid else '未知，未获价格准入'} |")
    if not report['dated_quote_observations']:
        lines.append('| — | 未知 | 未知 | 无已核验带日期报价 |')
    behavior = report['price_behavior']
    daily = behavior['periods']['daily']
    lines += ['', '## 历史日线关键价位', '', f"证券：{behavior['symbol']}。"]
    if daily['status'] == 'OBSERVED_NOT_ADMITTED':
        change = Decimal(daily['five_bar_price_change']) * 100
        lines += [f"历史范围：{daily['first_date']}至{daily['last_date']}，共{daily['bars']}根日线。",
                  f"历史末日收盘：{daily['close']}元；此前五根日线支撑：{daily['prior_five_bar_support']}元；阻力：{daily['prior_five_bar_resistance']}元。",
                  f"五根日线价格变化：{change:.2f}%；历史末日突破阻力：{'是' if daily['breakout'] else '否'}；跌破支撑：{'是' if daily['below_support'] else '否'}。",
                  '上述价位仅适用于历史窗口；后续报价不能据此证明当前突破。价格未复权，公司行动与成交量口径未核验。',
                  '失效观察：后续完整收盘跌破历史支撑时需重新研究；这不是卖出指令。']
    else:
        lines.append('历史日线不足，关键价位未知。')
    lines += ['60分钟与15分钟：未知，无对应原件；不合成周期。', '', '## 行业快照', '',
              '交易日期未知，不是今日热点。百分比为覆盖证券等权变化，非行业指数收益。', '',
              '| 行业 | 等权变化 | 持续性／催化剂 |', '| --- | ---: | --- |']
    for sector in report['themes'][:10]:
        change = Decimal(sector['equal_weight_change_percent'])
        lines.append(f"| {sector['theme']} | {change:.2f}% | 未知 |")
    lines += ['', '价值、风险、事件、PIT、样本外与Shadow等门禁仍未证明；观察状态不构成买卖建议。']
    return '\n'.join(lines) + '\n'


_LIFECYCLE_REASONS = {
    'PRICE_BASIS_UNKNOWN': '公司行动覆盖未核验，原始保护价与当前价不能假定可直接比较',
    'PRICE_BASIS_INCOMPARABLE': '价格窗口跨越已收录实施分配事件，不复权价格不能直接比较',
    'CURRENT_DATA_UNAVAILABLE': '当前行情证据不可用，无法判断当前结构',
    'ENTRY_STRUCTURE_OBSERVED': '当前开仓结构条件已被观察到，仅供研究观察',
    'ENTRY_STRUCTURE_NOT_QUALIFIED': '当前开仓结构尚不满足观察条件',
    'ENTRY_TRIGGER_NOT_OBSERVED': '当前单周期开仓触发条件尚未出现',
    'ENTRY_BEHAVIOR_QUALITY_NOT_USABLE': '价格行为质量不足或尚待核验',
    'ENTRY_MULTIPERIOD_STRUCTURE_NOT_QUALIFIED': '多周期整体结构尚未达到合格观察标准',
    'OWNED_ENTRY_REQUIRED_FOR_HELD_REVIEW': '缺少已核验的持仓及原始入场依据，不能进行个人加仓复核',
    'ENTRY_EVIDENCE_UNAVAILABLE': '原始参考 case 在指定入场时点不可用',
    'ENTRY_CURRENT_RULE_MISMATCH': '原始参考与当前参考的本次重算规则不一致',
    'ORIGINAL_PROTECTION_BREACHED': '曾收盘跌破原始参考保护价；后来恢复不能抹去这次破位',
    'CURRENT_PROTECTION_BREACHED': '当前保护条件已触发破位结构复核',
    'ENTRY_TO_CURRENT_DATA_INCOMPLETE': '从参考入场时点到当前的数据不完整，不能据此确认持有或加仓结构',
    'CURRENT_REDUCTION_CONDITION_OBSERVED': '当前减仓结构条件已被观察到，仅供复核',
    'CURRENT_ADD_CONDITION_OBSERVED': '当前加仓结构条件已被观察到，仅供复核',
    'NO_STRUCTURAL_CHANGE_OBSERVED': '本次未观察到需要改变结构观察状态的条件',
    'ADD_CONDITION_NOT_OBSERVED': '未观察到加仓结构条件',
    'ADD_STRUCTURE_QUALITY_NOT_USABLE': '加仓结构质量不可用于当前判断',
}
_LIFECYCLE_REVIEWS = {
    'UNKNOWN': '当前结构结论未知', 'WATCH': '继续观察',
    'ENTRY_OBSERVATION': '开仓结构观察',
    'EXIT_STRUCTURE_REVIEW': '退出结构复核',
    'REDUCE_STRUCTURE_REVIEW': '减仓结构复核',
    'ADD_STRUCTURE_REVIEW': '加仓结构复核',
    'HOLD_STRUCTURE_OBSERVATION': '维持结构观察',
}
_LIFECYCLE_EXTERNAL = {
    'OWNED_ENTRY_THESIS': '核验真实持仓归属及原始入场论据',
    'CORPORATE_ACTION_COMPARABILITY': '核验公司行动与价格口径可比性',
    'INDEPENDENT_STRATEGY_ADMISSION': '完成独立策略准入复核',
    'EVENT_RISK': '复核事件风险',
    'PORTFOLIO_CAPACITY': '复核组合容量与约束',
    'SELLABLE_QUANTITY_T_PLUS_ONE_AND_EXECUTION': '复核可卖数量、T+1 与执行条件',
}
_LIFECYCLE_CHECKS = {
    'PRICE_COMPARABILITY': '公司行动与价格口径可比性',
    'CURRENT_DATA': '当前行情证据', 'ENTRY_REFERENCE': '原始参考证据',
    'ENTRY_RULE_COMPATIBILITY': '本次重算规则兼容性',
    'ORIGINAL_PROTECTION': '原始参考保护价', 'CONTINUITY_COVERAGE': '连续行情覆盖',
    'CURRENT_EXIT': '当前退出结构条件', 'CURRENT_REDUCE': '当前减仓结构条件',
    'CURRENT_ADD': '当前加仓结构条件', 'CURRENT_OPEN': '当前开仓结构条件',
    'STRUCTURE_QUALITY': '价格行为质量', 'OPPORTUNITY_QUALITY': '多周期机会分级',
}
_LIFECYCLE_OUTCOMES = {
    'CONFIRMED': '同口径覆盖已确认，仅限此证据范围', 'INCOMPARABLE': '不宜直接比较',
    'CURRENT': '当前可用', 'STALE': '已过期', 'INVALID': '无效', 'UNKNOWN': '未知',
    'VERIFIED_REFERENCE_ONLY': '仅参考证据已核验，不代表真实入场或持仓',
    'UNVERIFIED': '未核验', 'NOT_SUPPLIED': '未提供',
    'MATCH': '一致', 'MISMATCH': '不一致', 'NOT_EVALUATED': '未评估',
    'BREACHED': '已观察到破位', 'NO_OBSERVED_BREACH': '未观察到破位',
    'COMPLETE': '覆盖完整', 'INCOMPLETE': '覆盖不完整',
    'OBSERVED': '已观察到条件', 'NOT_OBSERVED': '未观察到条件',
    'RESEARCH_ONLY': '仅供研究', 'UNFAVORABLE_DAILY_TREND': '日线趋势不利',
    'INSUFFICIENT_UPPER_SPACE': '上方空间不足',
    'ACTIVE_ONLY': '仅活跃观察', 'CONFLICT_OR_REJECTED': '存在结构冲突或已拒绝',
    'STRUCTURE_QUALIFIED_OBSERVATION': '结构合格观察',
}
_LIFECYCLE_PRICE_SCOPES = {
    'LATEST_COMPLETED_SESSION_DUAL_SOURCE_CLOSE': '最近已完成交易时段的双源收盘观察',
    'LAST_COMPLETED_CLOSE_DISPLAY_ONLY': '最近已完成收盘，仅供展示',
    'HISTORICAL_CLOSE_NOT_CURRENT_QUOTE': '历史收盘，非当前报价',
}
_LIFECYCLE_VALUE_LABELS = {
    'window_start': '价格形成窗口起日', 'window_end': '价格形成窗口止日',
    'crossing_events': '跨越的已收录事件', 'ex_date': '除息除权日',
    'complete_corporate_action_coverage': '全部公司行动覆盖已证明',
    'historical_availability_proven': '独立历史可得性已证明',
    'pdf_semantics_reverified': '本次重审原文语义',
    'adjusted_protection_price': '已核验调整后保护价',
    'price': '价格', 'as_of': '观察日期', 'available_at': '原件可得时点',
    'reference_price_scope': '价格范围', 'current_pit': '当前 PIT 标志',
    'source_integrity': '原件完整性状态',
    'current': '当前参考', 'entry': '原始参考',
    'original_protection_price': '原始参考保护价',
    'current_rolling_protection_price': '当前滚动保护价',
    'first_breach_at': '首次收盘破位时点', 'breach_count': '收盘破位次数',
    'first_breach_close': '首次破位收盘价',
    'inspected_bar_count': '已检查 K 线数量', 'missing_completed_bars': '缺失的已完成 K 线',
    'coverage': '数据覆盖', 'current_data_status': '当前行情状态',
    'entry_at': '参考入场时点', 'observed': '是否观察到条件',
    'observation_quality': '观察质量', 'structure_tier': '结构等级',
    'model_or_rule_version': '本次重算规则版本',
    'rule_version': '规则版本', 'structure_reasons': '分级原因', 'daily_trend': '日线趋势',
    'risk_reward_ratio': '结构距离比', 'risk_reward_scope': '距离比口径',
    'risk_reward_blocker': '距离比缺失原因',
    'intent': '结构动作', 'rule': '条件规则', 'status': '状态',
    'requires_existing_holding': '是否要求已有持仓', 'formal_eligibility': '正式准入',
    'personal_permission': '个人权限', 'action': '订单行为', 'blockers': '阻断原因',
}


def _lifecycle_value(value):
    if value is None or value == '':
        return '未知'
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, dict):
        return '；'.join(f"{_lifecycle_value(_LIFECYCLE_VALUE_LABELS.get(key, key))}：{_lifecycle_value(item)}"
                        for key, item in value.items()) or '未知'
    if isinstance(value, (list, tuple)):
        return '、'.join(_lifecycle_value(item) for item in value) or '无列明项'
    text = escape(str(value), quote=False).replace('\r', ' ').replace('\n', ' ')
    for character in ('\\', '`', '*', '[', ']', '|', '#'):
        text = text.replace(character, '\\' + character)
    return text


def _lifecycle_code(code, labels):
    if code is None or code == '':
        return '未知'
    return f"{labels.get(code, '未识别的代码')}（{_lifecycle_value(code)}）"


def _lifecycle_binding(binding):
    binding = binding or {}
    return f"原件：{_lifecycle_value(binding.get('path'))}；SHA-256：{_lifecycle_value(binding.get('sha256'))}"


def render_hotspot_action_coverage_markdown(coverage):
    """Explain the two coverage axes without promoting an empty query to proof."""
    if (coverage.get('schema_version') != 'hotspot-official-action-coverage-v1'
            or coverage.get('action') != 'no_order'):
        raise ValueError('Official no_order coverage contract required')
    labels = {'COMPLETE': '所需价格窗口内的官方公告查询已完整核验',
        'PARTIAL': '已核验公告范围不足以覆盖整个价格形成窗口',
        'MISSING': '没有提供完整官方扫描归档',
        'INVALID_OR_UNAVAILABLE': '公告归档无法核验或在评估时点尚不可得'}
    gaps = {
        'OFFICIAL_PUBLICATION_WINDOW_MISSING': '缺少官方完整公告扫描原件',
        'OFFICIAL_PUBLICATION_WINDOW_INVALID_OR_UNAVAILABLE': '公告原件或日期核验失败',
        'PUBLICATION_SCAN_DOES_NOT_COVER_PRICE_FORMATION_WINDOW': '公告查询范围未覆盖全部价格形成期',
        'OPENING_PENDING_ACTION_STATE_MISSING': '缺少窗口开始前已公告、尚待生效的公司行动状态',
        'EFFECTIVE_TERMS_AND_AMENDMENT_CHAIN_UNREVIEWED': '实施条款及后续修订、取消链尚未逐项核验',
        'SAME_BASIS_PRICE_MAPPING_NOT_VERIFIED': '原保护价和当前价的同口径映射未验证',
        'ANNOUNCEMENT_SEMANTICS_UNREVIEWED': '公告正文尚未完成公司行动语义审查',
    }
    lines = ['## 官方公告覆盖与价格口径', '',
        _lifecycle_code(coverage.get('official_publication_coverage'), labels) + '。',
        f"所需价格形成期：{_lifecycle_value(coverage.get('required_from'))} 至 {_lifecycle_value(coverage.get('required_to'))}。",
        f"实际公告查询窗口：{_lifecycle_value(coverage.get('publication_window'))}；归档取得时点：{_lifecycle_value(coverage.get('source_available_at'))}。",
        f"归档公告数：{_lifecycle_value(coverage.get('announcement_count'))}。",
        '公告查询完整不等于公司行动完整。零公告不证明没有此前已公布、当前才生效的分红、送转、配股、拆并股或修订取消。',
        '公司行动覆盖与价格可比性仍待核验；不折算原保护价，不自动确认持有、加仓、减仓或退出。',
        '以下公告仅为待审原件；归档时间不能回填为历史决策时点，也不构成 OOS 或真实 Shadow。', '']
    lines.extend('- ' + gaps.get(gap, _lifecycle_value(gap)) for gap in coverage.get('gaps', []))
    for item in coverage.get('pending_announcements', []):
        lines.append(f"- 待审公告：{_lifecycle_value(item.get('title'))}；发布日期：{_lifecycle_value(item.get('published_at'))}；来源：{_lifecycle_value(item.get('source_url'))}。")
    lines.extend('- ' + _lifecycle_binding(ref) for ref in coverage.get('evidence_bindings', []))
    lines.append('策略仍未证明有效；action=no_order。')
    return '\n'.join(lines) + '\n'


def render_cash_event_mapping_markdown(review):
    """Display event arithmetic separately from approved lifecycle protection."""
    if review.get('schema_version') != 'hotspot-cash-event-mapping-v1' or review.get('action') != 'no_order':
        raise ValueError('Cash event no_order mapping required')
    proof = review.get('event_proof') or {}
    terms, mapping = proof.get('terms') or {}, review.get('mapping') or {}
    lines = ['# 单次现金分红口径复核', '',
        '价格输入仅为解释性参考，不是已核验行情、真实入场或个人保护价；不产生交易指令。',
        f"本次原件核验时点：{_lifecycle_value(review.get('evaluated_at'))}；不证明历史决策时点已经取得这些资料。",
        f"证券：{_lifecycle_value(review.get('symbol'))}；状态：{_lifecycle_value(review.get('status'))}。",
        f"实施公告编号：{_lifecycle_value(terms.get('announcement_number'))}；公告日期：{_lifecycle_value(terms.get('published_date'))}。",
        f"登记日：{_lifecycle_value(terms.get('record_date'))}；除息生效日：{_lifecycle_value(terms.get('ex_date'))}；公告付款日：{_lifecycle_value(terms.get('cash_payment_date'))}。",
        '公告付款日不是账户实际收到现金的证明。',
        f"每股税前现金：{_lifecycle_value(terms.get('cash_per_share'))}；原文页码：{_lifecycle_value(terms.get('term_pages'))}。", '',
        f"保留的原保护参考价：{_lifecycle_value(review.get('original_protection_price'))}；保留的当期参考价：{_lifecycle_value(review.get('original_current_price'))}。",
        f"仅考虑本事件后的保护参考坐标：{_lifecycle_value(mapping.get('event_only_protection_on_current_basis'))}。",
        f"当期参考价还原至原坐标：{_lifecycle_value(mapping.get('event_only_current_on_original_basis'))}。",
        f"原始价差：{_lifecycle_value(mapping.get('raw_distance_to_original_protection'))}；单事件换算后价差：{_lifecycle_value(mapping.get('event_only_distance_to_protection'))}。",
        f"算式：{_lifecycle_value(mapping.get('formula'))}。", '',
        '这是未作交易所最小报价单位取整的单事件坐标换算，不是市场价格预测、止损成交价、税后收益或总回报。',
        '更正、取消或非现金条款未解决时不换算；没有发现修订资料也不能证明不存在修订。',
        '期初待生效行动与全部窗口覆盖未证明，不得将该数值写回已批准保护位，也不得据此推翻原破位记录。',
        f"修订链状态：{_lifecycle_value(proof.get('revision_status'))}；窗口可比性：{_lifecycle_value(review.get('window_comparability'))}。",
        f"未完成项：{_lifecycle_value(review.get('blockers'))}。"]
    lines.extend('- ' + _lifecycle_binding(ref) for ref in proof.get('evidence_bindings', []))
    original = proof.get('body_evidence_binding') or {}
    lines += [f"正文来源：{_lifecycle_value(original.get('url'))}。", 'action=no_order；策略 NOT_PROVEN。']
    window = review.get('event_window_review')
    if window:
        lines += ['', '## 官方后续公告窗口', '',
            f"窗口核验：{_lifecycle_value(window.get('status'))}；自动纳入核验的其他原件数：{_lifecycle_value(window.get('related_document_count'))}。",
            f"修订状态：{_lifecycle_value(window.get('revision_status'))}；具体缺口：{_lifecycle_value(window.get('gaps'))}。",
            '没有完整期初公司行动状态和修订语义证据，整体比较未放行；不能从零后续公告推断没有变化。']
        lines.extend('- ' + _lifecycle_binding(ref) for ref in window.get('evidence_bindings', []))
    return '\n'.join(lines) + '\n'


def render_hotspot_lifecycle_markdown(review):
    """Present the supplied lifecycle explanation; never recompute its decisions."""
    explanation = review.get('decision_explanation')
    if (not isinstance(explanation, dict)
            or explanation.get('schema_version') != 'hotspot-lifecycle-explanation-v1'
            or explanation.get('action') != 'no_order' or review.get('action') != 'no_order'
            or explanation.get('selected_review') != review.get('observed_review')):
        raise ValueError('Consistent no_order lifecycle explanation required')
    price = explanation.get('current_price_observation') or {}
    comparison = review.get('original_entry_comparison') or {}
    versions = explanation.get('recomputed_rule_versions') or {}
    lines = ['# 热点结构连续性复核', '',
        '仅供研究与结构复核，不授予个人加仓或交易权限，不产生订单。',
        '参考 case 不等于已拥有的 Entry、已核验的入场论据或真实成交记录；持仓归属未经本报告核验。',
        'HOLD 仅指维持结构观察，不代表原始投资论据（thesis）已验证。', '',
        f"证券：{_lifecycle_value(review.get('symbol'))}；评估时点：{_lifecycle_value(review.get('evaluated_at'))}。",
        f"策略验证：{_lifecycle_value(review.get('strategy_validation'))}；订单行为：no_order。", '',
        '## 本次结构结论', '',
        f"观察结果：{_lifecycle_code(explanation.get('selected_review'), _LIFECYCLE_REVIEWS)}。",
        f"判定依据：{_lifecycle_code(explanation.get('basis_code'), _LIFECYCLE_REASONS)}。", '',
        '## 当前价格与保护价', '',
        f"当前价格观察（元）：{_lifecycle_value(price.get('price'))}；观察日期：{_lifecycle_value(price.get('as_of'))}；原件可得时点：{_lifecycle_value(price.get('available_at'))}。",
        f"价格范围：{_lifecycle_code(price.get('reference_price_scope'), _LIFECYCLE_PRICE_SCOPES)}；当前 PIT 标志：{_lifecycle_value(price.get('current_pit'))}。",
        '上述价格不是盘中实时价；仅供展示的收盘价不等于当前 PIT 证据，原件完整性核验也不代表策略或交易准入。',
        f"原始参考保护价（元）：{_lifecycle_value(comparison.get('original_protection_price'))}；当前滚动保护价（元）：{_lifecycle_value(comparison.get('current_rolling_protection_price'))}。",
        f"首次收盘破位时点：{_lifecycle_value(comparison.get('first_breach_at'))}；收盘破位次数：{_lifecycle_value(comparison.get('breach_count'))}。",
        f"首次破位收盘价（元）：{_lifecycle_value(comparison.get('first_breach_close'))}。",
        f"数据覆盖：{_lifecycle_value(comparison.get('coverage'))}；已检查 K 线数量：{_lifecycle_value(comparison.get('inspected_bar_count'))}。", '',
        '## 本次重算规则与证据', '',
        f"当前参考重算规则：{_lifecycle_value(versions.get('current'))}。",
        f"原始参考重算规则：{_lifecycle_value(versions.get('entry'))}。",
        '这里的规则版本仅说明本次重算，不证明原入场当时真实采用了这些规则。',
        f"来源范围：{_lifecycle_value(explanation.get('source_scope'))}。",
        '以下输入引用不表示已核验；各项实际使用的证据以判定路径中的绑定为准。',
        f"当前参考 case 输入引用：{_lifecycle_binding(review.get('current_case_binding'))}。",
        f"原始参考 case 输入引用：{_lifecycle_binding(review.get('entry_case_binding'))}。", '',
        '## 判定路径', '']
    for index, step in enumerate(explanation.get('decision_path') or [], start=1):
        values = {key: value for key, value in (step.get('values') or {}).items()
                  if key not in {'official_disclosure_coverage', 'cash_action_window_reviews'}}
        lines += [f"{index}. 检查：{_lifecycle_code(step.get('check'), _LIFECYCLE_CHECKS)}；结果：{_lifecycle_code(step.get('outcome'), _LIFECYCLE_OUTCOMES)}。",
                  f"   数值与状态：{_lifecycle_value(values)}。"]
        bindings = step.get('evidence_bindings') or []
        lines.extend(f"   {_lifecycle_binding(binding)}。" for binding in bindings)
        if not bindings:
            lines.append('   证据绑定：未知。')
    if not explanation.get('decision_path'):
        lines.append('判定路径：未知。')
    coverage = (review.get('price_comparability') or {}).get('official_disclosure_coverage')
    if coverage:
        lines += ['', render_hotspot_action_coverage_markdown(coverage)]
    for window in (review.get('price_comparability') or {}).get('cash_action_window_reviews', []):
        lines += ['', '## 现金事件与后续公告窗口', '',
            f"事件窗口核验：{_lifecycle_value(window.get('status'))}；实施原文在官方索引中：{_lifecycle_value(window.get('implementation_in_index'))}。",
            f"自动核对的其他原件数：{_lifecycle_value(window.get('related_document_count'))}；修订状态：{_lifecycle_value(window.get('revision_status'))}。",
            '全量公告查询与单事件对应仍不能代替期初公司行动状态和全部修订语义核验，整体价格比较未放行。',
            f"具体缺口：{_lifecycle_value(window.get('gaps'))}。"]
    lines += ['', '## 为何不能据此加仓', '',
              '上述结构结果不能单独作为加仓依据；仍须完成外部复核。']
    raw_observation = review.get('unadjusted_structural_observation')
    if raw_observation:
        lines += [f"未作复权的原始结构记录：{_lifecycle_code(raw_observation.get('observed_review'), _LIFECYCLE_REVIEWS)}。",
                  '原始破位与保护价仍保留；这不是已核验可比性的持有、加仓或退出结论。']
    reasons = explanation.get('why_not_add') or []
    lines.extend('- ' + _lifecycle_code(code, _LIFECYCLE_REASONS) for code in reasons)
    if not reasons:
        lines.append('- 结构层面的未加仓原因未列明；不代表已获加仓权限。')
    lines += ['', '## 必须复核事项', '']
    external = explanation.get('required_external_reviews') or []
    lines.extend('- ' + _lifecycle_code(code, _LIFECYCLE_EXTERNAL) for code in external)
    if not external:
        lines.append('- 外部复核事项：未知，不能视为已完成。')
    return '\n'.join(lines) + '\n'

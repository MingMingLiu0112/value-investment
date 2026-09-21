"""Prepare pinned local debt-note research for display, never financial approval."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from .current_maturities import TITLE
from .financing_bridge import bridge_financing_rows


def load_debt_research(project_root, payload, payload_hash):
    root = Path(project_root).resolve()
    config_path = root / 'debt-research.json'
    if not config_path.exists():
        return {'companies': {}, 'evidence': {}}
    config = json.loads(config_path.read_text(encoding='utf-8'))
    audit_path = (root / config['audit_path']).resolve()
    if not audit_path.is_relative_to(root / 'runtime'):
        raise ValueError('Research audit must stay inside project runtime')
    raw = audit_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != config['audit_sha256']:
        raise ValueError('Pinned debt research audit changed')
    audit = json.loads(raw)
    sources = sum((payload.get(key, []) for key in
                   ('points', 'annual_points', 'disclosures', 'filing_candidates')), [])
    companies, evidence = {}, {}
    points = payload.get('points', []) + payload.get('annual_points', [])
    for report in audit['reports']:
        code = report['symbol']
        if code in companies:
            raise ValueError('Duplicate company in debt research audit')
        companies[code] = '研究证据停用：原件或导出来源未匹配'
        original_path = (root / report.get('financing', {}).get('path', '')).resolve()
        if not original_path.is_relative_to(root / 'runtime') or not original_path.is_file():
            continue
        if hashlib.sha256(original_path.read_bytes()).hexdigest() != report['sha256']:
            continue
        matches = [p for p in sources if p.get('symbol') == code
                   and p.get('sha256') == report['sha256'] and p.get('source_url') == report['source_url']
                   and (p.get('report_period') or p.get('period_label')) == report['report_period']]
        if not matches:
            continue
        notes = report.get('notes', [])
        if len(notes) != 1:
            companies[code] = '附注格式尚未覆盖或不唯一；完整有息负债未验证'
            continue
        note = notes[0]
        closing = note['total']['amounts']['closing']
        aggregate = bridge_financing_rows(
            {'rows': [{'label': TITLE, 'amounts': {'closing': closing}}], 'total': {'unit': 'CNY'}},
            points, code, report['report_period'], report['sha256'], report['source_url'])
        comparison = aggregate['rows'][0]
        fact = comparison.get('balance_fact') or {}
        metadata = fact.get('metadata') or {}
        recheck = {'method': 'current_export_debt_note_amount_bridge_v1',
                   'payload_sha256': payload_hash, 'payload_generated_at': payload.get('generated_at'),
                   'symbol': code, 'period': report['report_period'],
                   'audit_sha256': config['audit_sha256'], 'original_sha256': report['sha256'],
                   'status': comparison['status'], 'difference_cny': comparison.get('difference_cny'),
                   'data_point_id': fact.get('data_point_id'), 'source_id': fact.get('source_id'),
                   'secondary_data_point_id': metadata.get('secondary_data_point_id'),
                   'secondary_source_id': metadata.get('secondary_source_id')}
        recheck['recheck_id'] = hashlib.sha256(json.dumps(recheck, sort_keys=True).encode()).hexdigest()
        if closing is None:
            state = '本期合计为空，未填零'
        elif aggregate.get('matched_rows') == 1:
            state = '附注合计与当前导出金额一致（非完整负债验证）'
        else:
            state = {'amount_conflict': '附注合计与当前导出金额冲突',
                     'ambiguous_balance_facts': '当前导出候选不唯一，未沿用旧核对',
                     'balance_evidence_not_accepted': '当前导出证据尚未通过校验',
                     'missing_balance_fact': '当前导出缺少对应本期指标',
                     'unknown_or_incompatible_amount': '当前导出金额或单位不兼容',
                     'financing_closing_unknown_or_invalid': '附注本期合计未知或无效'}.get(
                         comparison['status'], '附注已提取；合计尚未与当前导出匹配')
        companies[code] = report['report_period'] + '\n' + state + '\n完整有息负债未验证'
        source = next((p for p in matches if p.get('source_id')), matches[0])
        pages = note.get('physical_pages', [note['physical_page']])
        records = []
        for row in note['rows'] + [note['total']]:
            normalized = row['amounts']['closing']
            multiplier = Decimal(note.get('normalization_multiplier', '1'))
            if multiplier not in (Decimal(1), Decimal(1000)):
                raise ValueError('Unsupported research normalization')
            raw_value = str(Decimal(normalized) / multiplier) if normalized is not None else None
            records.append({'label': '负债附注研究：' + row['label'],
                'field_name': 'research_current_maturity_total' if row is note['total'] else 'research_current_maturity_component',
                'period': report['report_period'], 'value': raw_value,
                'unit': 'CNY thousand' if multiplier == 1000 else 'CNY',
                'status': '研究提取，非已验证指标',
                'source_id': str(source.get('source_id', '')), 'source_url': report['source_url'],
                'sha256': report['sha256'], 'pages': ','.join(map(str, pages)),
                'parser': note['parser'], 'fetched_at': source.get('fetched_at'),
                'excerpt': json.dumps({'raw_cells': row['raw_cells'], 'context': note['context'],
                    'normalized_cny': normalized, 'multiplier': str(multiplier),
                    'audit_sha256': config['audit_sha256'], 'audit_finished_at': audit.get('finished_at'),
                    'current_export_recheck': recheck,
                    'scope': '研究展示，不进入评分估值或交易信号'}, ensure_ascii=False)})
        evidence[code] = records
    return {'companies': companies, 'evidence': evidence}

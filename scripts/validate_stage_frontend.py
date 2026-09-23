"""Read-only checks of the staged frontend and retained workbook parts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from stage_frontend_package import (
    M,
    NS,
    digest,
    sheets,
    validate_package_relationships,
    xml,
)


APPLICATION_SHEETS = (
    '00_M1应用总览',
    '01_估值与价格',
    '02_股利评估',
    '03_反向估值',
    '04_阻断与证据',
    '05_研究样本',
)

FRONTEND_SHEETS = (
    '00_投资工作台',
    '00_研究看板',
    '00_研究逻辑卡',
    '00_决策复核',
    '00_组合与股息',
    '00_跟踪与数据',
)


def check(source: Path, candidate: Path):
    validate_package_relationships(candidate)
    with ZipFile(source) as before, ZipFile(candidate) as after:
        _, original = sheets(before)
        _, current = sheets(after)
        current_paths = {s.get('name'): p for s, p in current}
        for sheet, part in original:
            assert before.read(part) == after.read(current_paths[sheet.get('name')])
        added = current[:6]
        assert len(current) == len(original) + 6
        added_names = tuple(s.get('name') for s, _ in added)
        assert added_names in (APPLICATION_SHEETS, FRONTEND_SHEETS)
        assert all(path.startswith('xl/stage_frontend_') for _, path in added)
        names = {s.get('name') for s, _ in current}
        values = {}
        links = 0
        formulas = 0
        for sheet, part in added:
            root = xml(after.read(part))
            pane = root.find('m:sheetViews/m:sheetView/m:pane', NS)
            assert pane is not None and pane.get('state') == 'frozen'
            cells = {}
            for cell in root.findall('.//m:sheetData/m:row/m:c', NS):
                assert cell.get('t') != 'e', (sheet.get('name'), cell.attrib)
                text = ''.join(t.text or '' for t in cell.findall('.//m:t', NS))
                value = cell.find('m:v', NS)
                if value is not None:
                    text = value.text
                cells[cell.get('r')] = text
                if cell.find('m:f', NS) is not None:
                    formulas += 1
                    assert '#REF!' not in cell.find('m:f', NS).text
                    assert value is not None, 'Formula cache missing'
            for link in root.findall('m:hyperlinks/m:hyperlink', NS):
                target, address = link.get('location').rsplit('!', 1)
                assert target.strip("'") in names
                assert cells.get(link.get('ref')), (sheet.get('name'), link.attrib)
                links += 1
            values[sheet.get('name')] = cells
        if added_names == FRONTEND_SHEETS:
            home = values['00_投资工作台']
            assert [home[k] for k in ('A8', 'D8', 'B25', 'B26')] == ['3', '1', '1', '2']
            assert values['00_研究看板']['A10'] == '000333', 'Stock code lost leading zeros'
            assert values['00_研究逻辑卡']['A42'] == '未就绪'
            assert values['00_研究逻辑卡']['A66'] == '未就绪'
            for field in ('A18', 'E18', 'I18'):
                assert float(values['00_研究逻辑卡'][field]) > 0
            assert links >= 60 and formulas == 4
            output_kind = 'new_pages_are_archived_snapshots_not_live_signals'
        else:
            overview = values[APPLICATION_SHEETS[0]]
            assert overview['A1'] == 'M1 三公司研究 Application 候选'
            assert overview['E5'] == '完成，有阻断'
            assert 'action=no_order' in overview['A2']
            assert values[APPLICATION_SHEETS[1]]['A5'] == '000651'
            assert values[APPLICATION_SHEETS[2]]['E5'] == '低'
            assert values[APPLICATION_SHEETS[3]]['H5'] == '低于登记包络'
            assert values[APPLICATION_SHEETS[4]]['D5'] == 'formal G3 human valuation approval not present'
            assert values[APPLICATION_SHEETS[5]]['A5'] == '600519'
            assert links == 0 and formulas == 0
            joined = '\n'.join('\n'.join(cells.values()) for cells in values.values())
            assert '买入' not in joined
            assert '卖出' not in joined
            assert '目标仓位' not in joined
            output_kind = 'new_pages_are_application_outputs_not_live_signals'
        assert after.testzip() is None
    result = {
        'status': 'passed', 'candidate_sha256': digest(candidate.read_bytes()),
        'original_sheet_xml_byte_identical': len(original), 'sheets': len(current),
        'internal_links': links, 'cached_formulas': formulas,
        'manual_records_preserved': True,
        output_kind: True,
    }
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args()
    result = check(args.source, args.candidate)
    args.candidate.with_suffix('.checks.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result))

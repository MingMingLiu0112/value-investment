import json
from zipfile import ZipFile

import pytest

from scripts.current.verify_dual_product_values import verify_dual_product_values
from value_investment_agent.application.product.common import sha256_file


def workbook_fixture(root, *, tamper=False, duplicate=False):
    (root/'config').mkdir()
    candidate = root/'candidate.json'
    candidate.write_text(json.dumps({'candidate_valuation': {
        'bear_value': '9.80', 'base_value': '10.08', 'bull_value': '10.30'}}), encoding='utf-8')
    (root/'config/user-research-workflow-v1.json').write_text(json.dumps({
        'review_candidates': {'600887': {'path': 'candidate.json', 'sha256': sha256_file(candidate)}}}), encoding='utf-8')
    rows = []
    for index, (label, value) in enumerate([('悲观', '9.8'), ('基准', '10.08'), ('乐观', '10.3')], 1):
        if tamper and index == 2:
            value = '100.8'
        rows.append(f'<row r="{index}"><c r="A{index}" t="inlineStr"><is><t>600887</t></is></c>'
            f'<c r="B{index}" t="inlineStr"><is><t>当前候选 {label}（元/股）</t></is></c>'
            f'<c r="C{index}"><v>{value}</v></c></row>')
    if duplicate:
        rows.append(rows[0])
    path = root/'preview.xlsx'
    with ZipFile(path, 'w') as archive:
        archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="03_公司" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(rows)+'</sheetData></worksheet>')
    return path, candidate


def test_values_match_pinned_candidate(tmp_path):
    workbook, _ = workbook_fixture(tmp_path)
    assert len(verify_dual_product_values(root=tmp_path, workbook=workbook)['checks']) == 3


@pytest.mark.parametrize('fault', ['value', 'duplicate', 'source'])
def test_changed_value_or_source_refuses_publication(tmp_path, fault):
    workbook, candidate = workbook_fixture(tmp_path, tamper=fault == 'value', duplicate=fault == 'duplicate')
    if fault == 'source':
        candidate.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError):
        verify_dual_product_values(root=tmp_path, workbook=workbook)

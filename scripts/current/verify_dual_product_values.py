"""Independently reconcile exported candidate values with pinned research inputs."""
from decimal import Decimal
from pathlib import PurePosixPath
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from value_investment_agent.application.product.common import load_json_object, sha256_file

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def verify_dual_product_values(*, root, workbook):
    workflow = load_json_object(root/'config/user-research-workflow-v1.json', 'workflow')
    with ZipFile(workbook) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(item.itertext()) for item in
                ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        sheets = ET.fromstring(archive.read('xl/workbook.xml')).findall('s:sheets/s:sheet', NS)
        relation = {item.attrib['Id']: item.attrib['Target'] for item in
            ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        sheet = next(item for item in sheets if item.attrib['name'] == '03_公司')
        target = relation[sheet.attrib['{'+REL+'}id']]
        path = target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl')/target)
        rows = []
        for row in ET.fromstring(archive.read(path)).findall('s:sheetData/s:row', NS):
            values = {}
            for cell in row.findall('s:c', NS):
                value = cell.find('s:v', NS)
                text = value.text if value is not None else ''
                if cell.attrib.get('t') == 's':
                    text = strings[int(text)]
                elif cell.attrib.get('t') == 'inlineStr':
                    text = ''.join(cell.find('s:is', NS).itertext())
                column = ''.join(c for c in cell.attrib['r'] if c.isalpha())
                values[column] = text
            rows.append(values)
    checks = []
    for symbol, binding in workflow['review_candidates'].items():
        source = root/binding['path']
        if sha256_file(source) != binding['sha256']:
            raise ValueError('candidate value source hash mismatch')
        candidate = load_json_object(source, 'research candidate')
        for key, label in [('bear', '悲观'), ('base', '基准'), ('bull', '乐观')]:
            matches = [row for row in rows if row.get('A') == symbol
                and row.get('B') == f'当前候选 {label}（元/股）']
            if len(matches) != 1:
                raise ValueError('exported current candidate is missing or duplicated')
            expected = Decimal(candidate['candidate_valuation'][key+'_value'])
            actual = Decimal(matches[0]['C'])
            if abs(expected-actual) > Decimal('0.00000001'):
                raise ValueError('exported current candidate value differs from research')
            checks.append(dict(symbol=symbol, scenario=key, expected=str(expected), actual=str(actual)))
    return dict(action='no_order', status='PASS', workbook_sha256=sha256_file(workbook), checks=checks)

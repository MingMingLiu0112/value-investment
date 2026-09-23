from __future__ import annotations

import importlib.util
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
SPEC = importlib.util.spec_from_file_location(
    'stage_frontend_package', SCRIPTS / 'stage_frontend_package.py'
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

M = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'


def _workbook_xml(names):
    sheets = ''.join(
        f'<sheet name="{name}" sheetId="{index + 1}" r:id="stageFrontend{index + 1}"/>'
        for index, name in enumerate(names)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{M}" xmlns:r="{R}"><sheets>{sheets}</sheets></workbook>'
    )


def _rels_xml(prefix, name):
    worksheet = '' if not name else (
        f'<Relationship Id="stageFrontend1" '
        f'Type="{R}/worksheet" Target="{prefix}sheet1.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{P}">{worksheet}</Relationships>'
    )


def _styles_xml():
    sections = ('numFmts', 'fonts', 'fills', 'borders', 'cellStyleXfs', 'cellXfs', 'dxfs')
    body = ''.join(f'<{tag} count="0"/>' for tag in sections)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<styleSheet xmlns="{M}">{body}</styleSheet>'
    )


def _content_types_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Types xmlns="{CT}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '</Types>'
    )


def _sheet_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{M}"><sheetData><row r="1"><c r="A1" t="inlineStr">'
        '<is><t>value</t></is></c></row></sheetData></worksheet>'
    )


def _root_rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{P}">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def _write_minimal_workbook(path: Path, sheet_name: str, part_prefix: str) -> None:
    with ZipFile(path, 'w', ZIP_DEFLATED) as package:
        package.writestr('[Content_Types].xml', _content_types_xml())
        package.writestr('_rels/.rels', _root_rels_xml())
        package.writestr('xl/workbook.xml', _workbook_xml([sheet_name]))
        package.writestr('xl/_rels/workbook.xml.rels', _rels_xml(part_prefix, sheet_name))
        package.writestr('xl/styles.xml', _styles_xml())
        package.writestr(f'xl/{part_prefix}sheet1.xml', _sheet_xml())


def test_graft_assigns_unique_relationship_ids_and_retains_original_target(tmp_path):
    source = tmp_path / 'source.xlsx'
    addon = tmp_path / 'addon.xlsx'
    output = tmp_path / 'candidate.xlsx'
    _write_minimal_workbook(source, 'original', 'stage_frontend/worksheets/')
    _write_minimal_workbook(addon, 'm1', 'worksheets/')
    expected = MODULE.digest(source.read_bytes())

    MODULE.graft(source, addon, output, expected)

    with ZipFile(output) as package:
        rels = ET.fromstring(package.read('xl/_rels/workbook.xml.rels'))
        ids = [relation.get('Id') for relation in rels]
        assert ids == ['stageFrontend1', 'm1Application1']
        assert len(ids) == len(set(ids))
        targets = {relation.get('Id'): relation.get('Target') for relation in rels}
        assert targets['stageFrontend1'] == 'stage_frontend/worksheets/sheet1.xml'
        assert targets['m1Application1'] == '/xl/stage_frontend_2/worksheets/sheet1.xml'
        workbook = ET.fromstring(package.read('xl/workbook.xml'))
        sheet_ids = [
            sheet.get(f'{{{R}}}id') for sheet in workbook.find(f'{{{M}}}sheets')
        ]
        assert sheet_ids == ['m1Application1', 'stageFrontend1']
    MODULE.validate_package_relationships(output)


def test_validate_package_relationships_rejects_duplicate_ids(tmp_path):
    path = tmp_path / 'broken.xlsx'
    with ZipFile(path, 'w', ZIP_DEFLATED) as package:
        package.writestr('xl/workbook.xml', '<workbook/>')
        package.writestr(
            '_rels/.rels',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{P}">'
            '<Relationship Id="same" Target="xl/workbook.xml"/>'
            '<Relationship Id="same" Target="xl/workbook.xml"/>'
            '</Relationships>',
        )

    try:
        MODULE.validate_package_relationships(path)
    except AssertionError as error:
        assert 'duplicate relationship id' in str(error)
    else:
        raise AssertionError('duplicate relationship ids were accepted')


def test_next_relationship_id_skips_existing_values():
    rels = ET.Element(f'{{{P}}}Relationships')
    ET.SubElement(rels, f'{{{P}}}Relationship', {'Id': 'm1Application1'})
    ET.SubElement(rels, f'{{{P}}}Relationship', {'Id': 'm1Application2'})

    assert MODULE.next_relationship_id(rels, 'm1Application') == 'm1Application3'

"""Append artifact-authored frontend sheets without rewriting retained evidence sheets."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import posixpath
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

M = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
C = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS = {'m': M, 'r': R, 'p': P}
ET.register_namespace('', M)
ET.register_namespace('r', R)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def xml(data):
    return ET.fromstring(data)


def serialized(root):
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def resolve(base, target):
    return target.lstrip('/') if target.startswith('/') else posixpath.normpath(
        posixpath.join(posixpath.dirname(base), target))


def sheets(z):
    workbook = xml(z.read('xl/workbook.xml'))
    rels = xml(z.read('xl/_rels/workbook.xml.rels'))
    targets = {r.get('Id'): resolve('xl/workbook.xml', r.get('Target')) for r in rels}
    return workbook, [(s, targets[s.get(f'{{{R}}}id')])
                      for s in workbook.find(f'{{{M}}}sheets')]


def next_relationship_id(rels, prefix, start=1):
    """Return the first `prefixN` relationship id not already used."""
    existing = {relation.get('Id') for relation in rels}
    index = start
    while f'{prefix}{index}' in existing:
        index += 1
    return f'{prefix}{index}'


def validate_package_relationships(path):
    """Fail closed when any relationship part has duplicate or dangling ids."""
    with ZipFile(path) as package:
        parts = set(package.namelist())
        for name in sorted(part for part in parts if part.endswith('.rels')):
            owner = name.replace('/_rels/', '/').removesuffix('.rels')
            if name == '_rels/.rels':
                owner = ''
            ids = set()
            for relation in xml(package.read(name)):
                rel_id = relation.get('Id')
                if not rel_id:
                    raise AssertionError(f'relationship without Id in {name}')
                if rel_id in ids:
                    raise AssertionError(f'duplicate relationship id {rel_id!r} in {name}')
                ids.add(rel_id)
                if relation.get('TargetMode') != 'External':
                    target = resolve(owner, relation.get('Target'))
                    if target not in parts:
                        raise AssertionError(
                            f'dangling target {target!r} from {name}: {relation.attrib}'
                        )


def preview(source, output):
    # Only the inspection copy is truncated. The publication path copies original bytes.
    with ZipFile(source) as z:
        workbook, entries = sheets(z)
        replacements = {}
        for sheet, path in entries:
            root = xml(z.read(path))
            data = root.find(f'{{{M}}}sheetData')
            for row in list(data):
                if int(row.get('r')) > 35:
                    data.remove(row)
            for tag in ('drawing', 'legacyDrawing', 'conditionalFormatting', 'dataValidations', 'autoFilter'):
                for item in root.findall(f'{{{M}}}{tag}'):
                    root.remove(item)
            merges = root.find(f'{{{M}}}mergeCells')
            if merges is not None:
                import re
                for item in list(merges):
                    if max(map(int, re.findall(r'\d+', item.get('ref')))) > 35:
                        merges.remove(item)
                merges.set('count', str(len(merges)))
            replacements[path] = serialized(root)
        with ZipFile(output, 'w', ZIP_DEFLATED) as dest:
            for item in z.infolist():
                dest.writestr(deepcopy(item), replacements.get(item.filename, z.read(item.filename)))
    return {'source_sha256': digest(source.read_bytes()), 'preview': str(output)}


def merge_styles(original, addition):
    offsets = {}
    nums = original.find(f'{{{M}}}numFmts')
    if nums is None:
        nums = ET.Element(f'{{{M}}}numFmts', {'count': '0'})
        original.insert(0, nums)
    next_number = max([163] + [int(n.get('numFmtId')) for n in nums]) + 1
    number_map = {}
    for item in addition.findall(f'{{{M}}}numFmts/{{{M}}}numFmt'):
        old = int(item.get('numFmtId'))
        number_map[old] = next_number
        child = deepcopy(item)
        child.set('numFmtId', str(next_number))
        nums.append(child)
        next_number += 1
    nums.set('count', str(len(nums)))
    for tag in ('fonts', 'fills', 'borders', 'cellStyleXfs', 'cellXfs', 'dxfs'):
        target = original.find(f'{{{M}}}{tag}')
        incoming = addition.find(f'{{{M}}}{tag}')
        if target is None:
            target = ET.SubElement(original, f'{{{M}}}{tag}', {'count': '0'})
        offsets[tag] = len(target)
        for item in incoming if incoming is not None else []:
            child = deepcopy(item)
            for xf in child.iter(f'{{{M}}}xf'):
                for attr, key in (('fontId', 'fonts'), ('fillId', 'fills'), ('borderId', 'borders'), ('xfId', 'cellStyleXfs')):
                    if attr in xf.attrib:
                        xf.set(attr, str(int(xf.get(attr)) + offsets[key]))
                if int(xf.get('numFmtId', '0')) in number_map:
                    xf.set('numFmtId', str(number_map[int(xf.get('numFmtId'))]))
            target.append(child)
        target.set('count', str(len(target)))
    # Keep SpreadsheetML style sections in schema order.
    order = ['numFmts', 'fonts', 'fills', 'borders', 'cellStyleXfs', 'cellXfs', 'cellStyles', 'dxfs', 'tableStyles', 'colors', 'extLst']
    original[:] = sorted(original, key=lambda el: order.index(el.tag.split('}')[-1]))
    return offsets


def graft(source, addon, output, expected):
    if digest(source.read_bytes()) != expected:
        raise ValueError('Source changed since inspection; do not publish')
    if output.exists():
        raise ValueError('Candidate already exists')
    with ZipFile(source) as src, ZipFile(addon) as new:
        workbook, existing = sheets(src)
        _, added = sheets(new)
        old_names = {s.get('name') for s, _ in existing}
        if old_names & {s.get('name') for s, _ in added}:
            raise ValueError('Frontend sheets already exist; refuse duplicate replacement')
        styles = xml(src.read('xl/styles.xml'))
        offsets = merge_styles(styles, xml(new.read('xl/styles.xml')))
        shared = []
        if 'xl/sharedStrings.xml' in new.namelist():
            shared = [deepcopy(si) for si in xml(new.read('xl/sharedStrings.xml'))]
        excluded = {'xl/workbook.xml', 'xl/_rels/workbook.xml.rels', 'xl/styles.xml', 'xl/sharedStrings.xml'}
        mapped_candidates = {
            name: 'xl/stage_frontend/' + name[3:]
            for name in new.namelist()
            if name.startswith('xl/')
            and name not in excluded
            and not name.startswith('xl/theme/')
        }
        prefix = 'xl/stage_frontend/'
        suffix = 2
        while any(target in src.namelist() for target in mapped_candidates.values()):
            prefix = f'xl/stage_frontend_{suffix}/'
            mapped_candidates = {
                name: prefix + name[3:]
                for name, _ in mapped_candidates.items()
            }
            suffix += 1
        mapping = mapped_candidates
        content_types = xml(src.read('[Content_Types].xml'))
        new_types = xml(new.read('[Content_Types].xml'))
        known_ext = {x.get('Extension') for x in content_types}
        for item in new_types:
            if item.tag == f'{{{C}}}Override' and item.get('PartName', '').lstrip('/') in mapping:
                child = deepcopy(item)
                child.set('PartName', '/' + mapping[item.get('PartName').lstrip('/')])
                content_types.append(child)
            elif item.tag == f'{{{C}}}Default' and item.get('Extension') not in known_ext:
                content_types.append(deepcopy(item))
                known_ext.add(item.get('Extension'))
        rels = xml(src.read('xl/_rels/workbook.xml.rels'))
        # Threaded comments also require their workbook-level person relationship.
        for relation in xml(new.read('xl/_rels/workbook.xml.rels')):
            target = resolve('xl/workbook.xml', relation.get('Target'))
            if target in mapping and relation.get('Type') != R + '/worksheet':
                child = deepcopy(relation)
                child.set('Id', next_relationship_id(rels, 'm1Dependency'))
                child.set('Target', '/' + mapping[target])
                rels.append(child)
        max_id = max(int(s.get('sheetId')) for s, _ in existing)
        sheet_list = workbook.find(f'{{{M}}}sheets')
        for i, (s, path) in enumerate(added):
            rel_id = next_relationship_id(rels, 'm1Application')
            child = deepcopy(s)
            child.set('sheetId', str(max_id + i + 1))
            child.set(f'{{{R}}}id', rel_id)
            sheet_list.insert(i, child)
            ET.SubElement(rels, f'{{{P}}}Relationship', {'Id': rel_id, 'Type': R + '/worksheet', 'Target': '/' + mapping[path]})
        for name in workbook.findall(f'{{{M}}}definedNames/{{{M}}}definedName'):
            if 'localSheetId' in name.attrib:
                name.set('localSheetId', str(int(name.get('localSheetId')) + len(added)))
        for view in workbook.findall(f'{{{M}}}bookViews/{{{M}}}workbookView'):
            view.set('activeTab', '0')
            view.set('firstSheet', '0')
        replacements = {'xl/workbook.xml': serialized(workbook),
                        'xl/_rels/workbook.xml.rels': serialized(rels),
                        'xl/styles.xml': serialized(styles),
                        '[Content_Types].xml': serialized(content_types)}
        copied = {}
        links_path = addon.parent / 'frontend-links.json'
        frontend_links = json.loads(links_path.read_text(encoding='utf-8')) if links_path.exists() else []
        sheet_names = {path: sheet.get('name') for sheet, path in added}
        for path, target in mapping.items():
            data = new.read(path)
            if path.endswith('.rels'):
                root = xml(data)
                owner = path.replace('/_rels/', '/').removesuffix('.rels')
                for rel in root:
                    if rel.get('TargetMode') == 'External':
                        continue
                    ref = resolve(owner, rel.get('Target'))
                    if ref not in mapping:
                        raise ValueError('Unmapped frontend dependency: ' + ref)
                    rel.set('Target', '/' + mapping[ref])
                data = serialized(root)
            elif path.startswith('xl/worksheets/') and path.endswith('.xml'):
                root = xml(data)
                # Preserve the requested frozen navigation when the exporter omits panes.
                view = root.find('m:sheetViews/m:sheetView', NS)
                if view is not None:
                    for pane in view.findall('m:pane', NS):
                        view.remove(pane)
                    rows = 8 if sheet_names.get(path) == '00_研究看板' else 4
                    ET.SubElement(view, f'{{{M}}}pane', {
                        'ySplit': str(rows), 'topLeftCell': f'A{rows + 1}',
                        'activePane': 'bottomLeft', 'state': 'frozen',
                    })
                    view.set('zoomScale', '90')
                for cell in root.iter(f'{{{M}}}c'):
                    if 's' in cell.attrib:
                        cell.set('s', str(int(cell.get('s')) + offsets['cellXfs']))
                    if cell.get('t') == 's':
                        value = cell.find(f'{{{M}}}v')
                        entry = deepcopy(shared[int(value.text)])
                        entry.tag = f'{{{M}}}is'
                        cell.remove(value)
                        cell.set('t', 'inlineStr')
                        cell.append(entry)
                for element in root.iter():
                    if 'dxfId' in element.attrib:
                        element.set('dxfId', str(int(element.get('dxfId')) + offsets['dxfs']))
                    if element.tag == f'{{{M}}}col' and 'style' in element.attrib:
                        element.set('style', str(int(element.get('style')) + offsets['cellXfs']))
                links = [link for link in frontend_links if link['sheet'] == sheet_names.get(path)]
                if links:
                    hyperlinks = root.find(f'{{{M}}}hyperlinks')
                    if hyperlinks is None:
                        hyperlinks = ET.Element(f'{{{M}}}hyperlinks')
                        preceding = {'sheetPr', 'dimension', 'sheetViews', 'sheetFormatPr', 'cols', 'sheetData', 'sheetCalcPr', 'sheetProtection', 'protectedRanges', 'scenarios', 'autoFilter', 'sortState', 'dataConsolidate', 'customSheetViews', 'mergeCells', 'phoneticPr', 'conditionalFormatting', 'dataValidations'}
                        index = max([0] + [i + 1 for i, el in enumerate(root) if el.tag.split('}')[-1] in preceding])
                        root.insert(index, hyperlinks)
                    for link in links:
                        ET.SubElement(hyperlinks, f'{{{M}}}hyperlink', {key: link[key] for key in ('ref', 'location', 'display')})
                data = serialized(root)
            copied[target] = data
        with ZipFile(output, 'w', ZIP_DEFLATED, allowZip64=True) as out:
            for item in src.infolist():
                # writestr updates ZipInfo offsets; never mutate the source index.
                out.writestr(deepcopy(item), replacements.get(item.filename, src.read(item.filename)))
            for name, data in copied.items():
                out.writestr(name, data)
        with ZipFile(output) as result:
            unchanged = [p for p in src.namelist() if p not in replacements]
            assert all(result.read(p) == src.read(p) for p in unchanged)
            assert result.testzip() is None
            validate_package_relationships(output)
            _, verified = sheets(result)
            verified_ids = {sheet.get(f'{{{R}}}id') for sheet, _ in verified}
            assert len(verified_ids) == len(verified)
            first_six = [(sheet.get('name'), path) for sheet, path in verified[:len(added)]]
            assert [sheet.get('name') for sheet, _ in added] == [name for name, _ in first_six]
            assert all(path.startswith(prefix) for _, path in first_six)
            assert all(path in mapping.values() for _, path in first_six)
            retained = [(sheet.get('name'), path) for sheet, path in verified[len(added):]]
            assert [sheet.get('name') for sheet, _ in existing] == [name for name, _ in retained]
    receipt = {'source_sha256': expected, 'candidate_sha256': digest(output.read_bytes()),
               'original_parts_unchanged': len(unchanged), 'original_sheets_preserved': len(existing),
               'new_sheets': [s.get('name') for s, _ in added], 'candidate': str(output),
               'retained_parts_modified': sorted(replacements), 'status': 'candidate_verified_not_published'}
    output.with_suffix('.receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['preview', 'graft'])
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--addon', type=Path)
    parser.add_argument('--expected-sha256')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = preview(args.source, args.output) if args.mode == 'preview' else graft(
        args.source, args.addon, args.output, args.expected_sha256)
    print(json.dumps(result, ensure_ascii=False))

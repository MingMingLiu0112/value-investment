"""Archive the author's public workbook and expose formulas, not strategy approval."""
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from openpyxl import load_workbook


def main():
    url = 'https://pages.stern.nyu.edu/~adamodar/pc/fcffsimpleginzu.xlsx'
    raw = build_opener(ProxyHandler({})).open(url, timeout=60).read()
    workbook = load_workbook(io.BytesIO(raw), data_only=False)
    stamp = datetime.now(timezone.utc)
    target = Path('runtime/valuation-research') / stamp.strftime('%Y%m%dT%H%M%S%fZ')
    target.mkdir(parents=True, exist_ok=False)
    (target / 'fcffsimpleginzu.xlsx').write_bytes(raw)
    cells = []
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                if cell.value is not None:
                    cells.append({'sheet': sheet.title, 'cell': cell.coordinate,
                                  'type': cell.data_type, 'value': str(cell.value)})
    result = {'url': url, 'fetched_at': stamp.isoformat(),
              'sha256': hashlib.sha256(raw).hexdigest(),
              'scope': 'Original formula inventory; no recalculation or investment approval',
              'cells': cells}
    (target / 'formula-inventory.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'directory': str(target), 'sha256': result['sha256'],
                      'cells': len(cells)}))


if __name__ == '__main__':
    main()

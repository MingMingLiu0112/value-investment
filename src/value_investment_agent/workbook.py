from __future__ import annotations

import json
import subprocess
from pathlib import Path


def sync_workbook(payload: dict, template: Path, output_directory: Path) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    payload_path = output_directory / 'excel-payload.json'
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding='utf-8')
    output_path = output_directory / f'{template.stem}_已同步.xlsx'
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'sync_workbook.mjs'
    subprocess.run(['node', str(script), str(template), str(payload_path), str(output_path)], check=True)
    return output_path

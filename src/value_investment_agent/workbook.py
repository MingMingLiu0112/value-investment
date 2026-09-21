from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def sync_workbook(payload: dict, template: Path, output_directory: Path) -> Path:
    """Update the canonical workbook in place after making a recoverable technical copy."""
    if not template.is_file():
        raise FileNotFoundError(f'Canonical workbook was not found: {template}')
    output_directory.mkdir(parents=True, exist_ok=True)
    payload_path = output_directory / 'excel-payload.json'
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding='utf-8')
    backup_directory = output_directory / 'workbook-backups'
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / f'{template.stem}-{datetime.now():%Y%m%d-%H%M%S}.xlsx'
    shutil.copy2(template, backup_path)
    output_path = output_directory / f'{template.stem}_已同步.xlsx'
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'sync_workbook.py'
    output_path = output_directory / f'.{template.stem}.syncing.xlsx'
    subprocess.run([sys.executable, str(script), str(template), str(payload_path), str(output_path)], check=True)
    try:
        output_path.replace(template)
    except PermissionError as error:
        output_path.unlink(missing_ok=True)
        raise RuntimeError('Excel is open or locked. Close WPS, then retry the sync.') from error
    return template

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path('.env')) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    database_url: str
    restore_database_url: str | None
    backup_directory: Path
    workbook_path: Path
    output_directory: Path
    data_max_age_hours: int
    price_conflict_tolerance: float
    container_runtime: str
    postgres_container_name: str
    restore_container_name: str


def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        database_url=os.environ.get('DATABASE_URL', 'postgresql://value_agent:change-me@localhost:5432/value_agent'),
        restore_database_url=os.environ.get('RESTORE_DATABASE_URL') or None,
        backup_directory=Path(os.environ.get('BACKUP_DIRECTORY', 'backups')),
        workbook_path=Path(os.environ.get('WORKBOOK_PATH', 'A股价值投资_Agent前端智能跟踪模板.xlsx')),
        output_directory=Path(os.environ.get('OUTPUT_DIRECTORY', 'runtime')),
        data_max_age_hours=int(os.environ.get('DATA_MAX_AGE_HOURS', '30')),
        price_conflict_tolerance=float(os.environ.get('PRICE_CONFLICT_TOLERANCE', '0.03')),
        container_runtime=os.environ.get('CONTAINER_RUNTIME', 'podman'),
        postgres_container_name=os.environ.get('POSTGRES_CONTAINER_NAME', 'value-investment-postgres'),
        restore_container_name=os.environ.get('RESTORE_CONTAINER_NAME', 'value-investment-restore-postgres'),
    )

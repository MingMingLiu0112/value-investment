import importlib.util
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_preclose_capital_refresh", ROOT / "scripts" / "prepare_moutai_preclose_capital_refresh.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SHANGHAI = timezone(timedelta(hours=8))


def test_preclose_receipt_rejects_after_close_and_wrong_day():
    with pytest.raises(ValueError, match="too late"):
        MODULE.require_preclose(datetime(2026, 9, 21, 15, 0, tzinfo=SHANGHAI), date(2026, 9, 21))
    with pytest.raises(ValueError, match="equal"):
        MODULE.require_preclose(datetime(2026, 9, 21, 14, 45, tzinfo=SHANGHAI), date(2026, 9, 22))


def test_preclose_receipt_accepts_weekday_before_close():
    MODULE.require_preclose(datetime(2026, 9, 21, 14, 45, tzinfo=SHANGHAI), date(2026, 9, 21))

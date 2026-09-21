import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('trading_rule_archive',
    Path(__file__).resolve().parents[1] / 'scripts' / 'archive_trading_rules.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_maintenance_page_cannot_be_rule_evidence():
    with pytest.raises(ValueError):
        module.validate_html('transfer-2022', '<html>中国结算系统维护中</html>'.encode('utf-8'))


def test_required_notice_values_survive_html_and_whitespace():
    raw = '<meta charset="utf-8"><p>2022 年 <b>0.01</b> ‰ 双 向</p>'.encode('utf-8')
    module.validate_html('transfer-2022', raw)


def test_previous_rate_cannot_pass_as_new_notice():
    raw = '<meta charset="utf-8"><p>2022 年 0.02 ‰ 双向</p>'.encode('utf-8')
    with pytest.raises(ValueError):
        module.validate_html('transfer-2022', raw)

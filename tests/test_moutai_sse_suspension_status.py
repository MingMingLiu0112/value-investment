import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_sse_suspension", ROOT / "scripts" / "audit_moutai_sse_suspension_status.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_windows_cover_full_replay_with_official_interface_limit():
    assert MODULE.WINDOWS == (("20150101", "20171231"), ("20180101", "20201231"), ("20210101", "20231231"), ("20240101", "20251231"))
    params = MODULE.request_params("20150101", "20171231")
    assert params["productCode"] == "600519"
    assert params["sqlId"] == "GW_PL_JYTS_TFPXX"


def test_jsonp_requires_expected_envelope_and_complete_total():
    payload = MODULE.parse_jsonp(b'callback({"sqlId":"GW_PL_JYTS_TFPXX","result":[],"pageHelp":{"total":0}})')
    assert MODULE.validate_response(payload) == []
    with pytest.raises(ValueError):
        MODULE.parse_jsonp(b'{}')
    with pytest.raises(ValueError):
        MODULE.validate_response({"sqlId": "wrong", "result": [], "pageHelp": {"total": 0}})
    with pytest.raises(ValueError):
        MODULE.validate_response({"sqlId": "GW_PL_JYTS_TFPXX", "result": [], "pageHelp": {"total": 1}})

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_pe_mid_contract_v2", ROOT / "scripts" / "build_moutai_pe_mid_paper_contract_v2.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_v2_extends_the_same_research_rule_without_promoting_approval():
    contract, trace, _, _ = MODULE.build_research_contract()
    assert contract["contract_version"] == "moutai-pe-mid-paper-contract-v2-2025-extension"
    assert len(contract["sessions"]) == 2674
    assert trace[-1]["date"] == "2025-12-31"
    assert contract["research_rule"]["entry_margin"] == "30% unchanged from v1"
    assert contract["share_event_context"]["ex_post_confirmation_prohibited_for_2025_decisions"] is True
    assert contract["valuation_approved"] is False
    assert contract["trade_approved"] is False

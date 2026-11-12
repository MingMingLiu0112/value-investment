"""Frozen economic-policy source bytes must be checkout-stable."""

from hashlib import sha256
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("symbol", ("600519", "600887"))
def test_v4_policy_rationale_binding_matches_checkout_bytes(symbol):
    policy_path = ROOT / "config" / "research-proposals" / f"{symbol}-joint-capital-cash-path-v4.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    for binding in policy["rationale_bindings"]:
        rationale = ROOT / binding["path"]
        assert rationale.is_file()
        assert sha256(rationale.read_bytes()).hexdigest() == binding["sha256"]

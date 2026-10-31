from value_investment_agent.application.product.public_snapshot import _resolve_runtime


def test_retained_public_json_and_runtime_are_accepted(tmp_path):
    assert _resolve_runtime(tmp_path, "artifacts/current/p5/packet.json") == tmp_path / "artifacts/current/p5/packet.json"
    assert _resolve_runtime(tmp_path, "runtime/packet.json") == tmp_path / "runtime/packet.json"


def test_private_escape_and_other_artifacts_are_rejected(tmp_path):
    for path in ("../packet.json", "artifacts/archive/packet.json", "artifacts/current/private/packet.json",
                 "artifacts/current/journal.json", "artifacts/current/account.xlsx", "config/packet.json"):
        assert _resolve_runtime(tmp_path, path) is None

import hashlib
import json

import pytest

from value_investment_agent.application.hotspot.replay_read_model import FOLDER, load_replay_summary


def write_bound(root, name, value):
    path = root / FOLDER / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value).encode("utf-8")
    path.write_bytes(raw)
    return {"path": FOLDER + "/" + name, "sha256": hashlib.sha256(raw).hexdigest()}


def reports(root, *, different_parent=False):
    parent = {"path": "synthetic-spec.json", "sha256": "synthetic-spec-hash"}
    report = dict(schema_version="hotspot-five-case-replay-report-v1", action="no_order", spec_binding=parent,
                  computed_at="2026-10-14T21:00:00+08:00", data_available_at="2026-10-14T18:00:00+08:00",
                  partitions={}, limitations=["retrospective-not-OOS"], results=[
                      dict(symbol="300364", case_binding={"case_sha256": "synthetic-case"},
                           rule_version="hotspot-prior-five-completed-bars-v1", segments={}, last_observation={"signal_state": "WATCH"})])
    report_binding = write_bound(root, "replay-results-v1.json", report)
    manifest = write_bound(root, "replay-manifest-v1.json", {
        "schema_version": "hotspot-event-replay-manifest-v1", "action": "no_order", "outputs": [report_binding]})
    structure = dict(schema_version="hotspot-descriptive-structure-prefix-report-v1", action="no_order",
                     parent_spec_binding={} if different_parent else parent, results=[
                         dict(symbol="300364", rule_version="hotspot-confirmed-structure-v1", segments={},
                              last_observation={"structure": {"daily_trend": "DOWNTREND"}})])
    structure_binding = write_bound(root, "replay-structure-results-v1.json", structure)
    structure_manifest = write_bound(root, "replay-structure-manifest-v1.json", {
        "schema_version": "hotspot-structure-prefix-manifest-v1", "action": "no_order", "output_binding": structure_binding})
    return manifest["sha256"], structure_manifest["sha256"]


def test_web_read_model_exposes_frozen_descriptions_not_current_permission(tmp_path):
    v1, structure = reports(tmp_path)
    output = load_replay_summary(root=tmp_path, manifest_sha256=v1, structure_manifest_sha256=structure)
    assert output["reference_scope"] == "FROZEN_REPLAY_NOT_CURRENT_JUDGMENT"
    assert output["items"][0]["archived_structure_observation"]["structure"]["daily_trend"] == "DOWNTREND"
    assert output["formal_eligibility"] is False
    assert output["portfolio_eligibility"] is None
    assert output["prospective_oos_admitted"] is False
    assert output["elapsed_real_shadow_sessions"] == 0
    assert output["action"] == "no_order"


def test_v1_only_is_readable_without_inventing_new_structure(tmp_path):
    v1, _ = reports(tmp_path)
    output = load_replay_summary(root=tmp_path, manifest_sha256=v1)
    assert output["items"][0]["structure_rule_version"] is None


def test_tampered_report_or_unpinned_manifest_is_rejected(tmp_path):
    v1, _ = reports(tmp_path)
    with pytest.raises(ValueError, match="hash"):
        load_replay_summary(root=tmp_path, manifest_sha256="wrong")
    (tmp_path / FOLDER / "replay-results-v1.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="hash"):
        load_replay_summary(root=tmp_path, manifest_sha256=v1)


def test_structure_cannot_mix_another_frozen_input_chain(tmp_path):
    v1, structure = reports(tmp_path, different_parent=True)
    with pytest.raises(ValueError, match="different frozen replay"):
        load_replay_summary(root=tmp_path, manifest_sha256=v1, structure_manifest_sha256=structure)

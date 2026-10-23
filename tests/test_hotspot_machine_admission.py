"""Attack replay linkage, not just signed summary flags."""
from copy import deepcopy

import pytest

from test_hotspot_independent_validation import NOW, dependencies
from value_investment_agent.application.hotspot import independent_validation as subject


def verify(root, documents):
    return subject.verify_strategy_admission_sources(root=root, documents=documents,
        symbol="600519", rule_version="structure-v1", cutoff=NOW)


def test_true_flags_are_not_a_machine_report(tmp_path):
    with pytest.raises(ValueError, match="machine-replayable"):
        verify(tmp_path, [dict(strict_pit_admitted=True, strict_oos_admitted=True,
                              strategy_validation="PASSED")])


def test_relabeling_actual_replay_cannot_change_admission(tmp_path, monkeypatch):
    dependencies(monkeypatch)
    actual = subject.validate_current_hotspot_strategy(root=tmp_path, now=NOW)
    forged = deepcopy(actual)
    forged.update(strategy_validation="PASSED", strict_pit_admitted=True,
                  strict_oos_admitted=True, actual_sample_accepted=True)
    with pytest.raises(ValueError, match="independently recomputed"):
        verify(tmp_path, [forged])
    with pytest.raises(ValueError, match="current security and rule"):
        verify(tmp_path, [actual])


def test_matching_identity_does_not_override_failed_evidence(tmp_path, monkeypatch):
    dependencies(monkeypatch)
    actual = subject.validate_current_hotspot_strategy(root=tmp_path, now=NOW)
    actual["current_scope"].update(data_status="CURRENT", signal_rule_version="structure-v1")
    actual["sample_comparison"]["applies_to_current_strategy"] = True
    # Isolate the admission decision from the expensive source replay. No
    # synthetic report is persisted or presented as actual validation.
    monkeypatch.setattr(subject, "validate_current_hotspot_strategy", lambda **kw: actual)
    with pytest.raises(ValueError, match="evidence remains unproven"):
        verify(tmp_path, [actual])


def test_ambiguous_and_future_audits_rejected(tmp_path, monkeypatch):
    dependencies(monkeypatch)
    actual = subject.validate_current_hotspot_strategy(root=tmp_path, now=NOW)
    with pytest.raises(ValueError, match="one machine"):
        verify(tmp_path, [actual, actual])
    actual["evaluated_at"] = "2099-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="unavailable at review"):
        verify(tmp_path, [actual])

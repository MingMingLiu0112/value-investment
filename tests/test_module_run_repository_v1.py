"""TEST_ONLY existing repository/schema integration, not production DB acceptance."""
from datetime import date, datetime, timezone
from pathlib import Path
import json

import pytest
from value_investment_agent.domain.research.module_run_v1 import (
    ModuleRun, make_manifest, canonical_sha256, module_run_schema,
)
from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
from value_investment_agent.infrastructure.module_run_artifact_codec_v1 import artifact_payload, decode_artifact
from value_investment_agent.research_artifacts import ResearchArtifactIdentity


def _run():
    item = dict(role="result", schema_id="TEST_ONLY-v1", payload={"status": "source_checked"},
                sha256=canonical_sha256({"status": "source_checked"}))
    return ModuleRun.from_payload(dict(
        schema_version="module-run-v1", action="no_order", run_id="test-validation-1",
        module_id="A", symbol=None, run_type="VALIDATE", status="SUCCESS",
        created_at="2026-11-01T01:00:00+00:00",
        started_at="2026-11-01T01:00:00+00:00", finished_at="2026-11-01T01:00:01+00:00",
        parent_run_ids=[], stage_events=[], warnings=[], errors=[],
        input_manifest=make_manifest("test-input", [item]),
        output_manifest=make_manifest("test-output", [item]), source_refs=[], artifact_refs=[],
        metrics={"assurance": "TEST_ONLY", "source_ref_validation": "CALLER_RESPONSIBILITY"},
        model_version="NOT_APPLICABLE", rule_version="TEST_ONLY", code_commit="a"*40))


def test_same_existing_repository_accepts_and_decodes_module_run_without_new_store():
    run = _run()
    repository = InMemoryResearchArtifactRepository()
    identity = ResearchArtifactIdentity(
        scope_type="review", scope_key=run.run_id, artifact_type="module_run",
        schema_version="module-run-v1", as_of=date(2026, 11, 1),
        available_at=datetime(2026, 11, 1, 1, 0, 1, tzinfo=timezone.utc))
    stored = repository.save_object(run, identity=identity, run_id=run.run_id)
    assert repository.save_object(run, identity=identity, run_id=run.run_id).artifact_id == stored.artifact_id
    loaded = repository.load_by_id(stored.artifact_id)
    assert repository.verify(loaded)["verified"] is True
    payload = loaded.envelope.payload_object()
    assert decode_artifact("module_run", payload) == run
    assert artifact_payload(run) == ("module_run", run.as_dict())
    assert len(repository.list_versions("review", run.run_id, "module_run")) == 1


def test_catalog_has_exact_eleven_modules_and_schema_refs_are_resolvable():
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root/"config/value-mainline-modules-v1.json").read_text(encoding="utf-8"))
    schema = json.loads((root/"schemas/value-mainline-v1.json").read_text(encoding="utf-8"))
    assert [m["module_id"] for m in catalog["modules"]] == [
        "A", "B", "C", "D1", "D2", "E1", "E2", "F1", "F2", "G1", "G2"]
    assert schema["$defs"]["ModuleRun"] == {k:v for k,v in module_run_schema().items() if k != "$schema"}
    for m in catalog["modules"]:
        for name in ("input_schema", "output_schema"):
            ref = m[name]["$ref"]
            assert ref.split("#/")[1].split("/")[1] in schema["$defs"]
        assert set(m["criteria"]) == set(catalog["criteria_definitions"])
        assert set(m["method_status"]) == {
            "input_schema", "output_schema", "validate", "run", "get_run", "replay", "explain", "health_check"}
        assert m["action"] == "no_order"
        assert (root/m["source_report"]).is_file()



def test_retained_driver_source_checkout_preserves_committed_bytes():
    # Historical task hashes bind raw implementation bytes, not normalized text.
    import subprocess
    root = Path(__file__).resolve().parents[1]
    name = "src/value_investment_agent/application/research/agent_review/operating_driver_draft_v2.py"
    blob = subprocess.check_output(["git", "-C", str(root), "show", "HEAD:" + name])
    assert (root/name).read_bytes() == blob
    attribute = subprocess.check_output(
        ["git", "-C", str(root), "check-attr", "text", "--", name], text=True)
    assert attribute.strip().endswith(": text: unset")



def test_additive_module_dispatch_preserves_frozen_financial_codec():
    import hashlib
    from value_investment_agent import research_artifact_codecs as legacy
    root = Path(__file__).resolve().parents[1]
    raw = (root/"src/value_investment_agent/research_artifact_codecs.py").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "05722dc2263f6e29cf58dc7caf62cff00a16d25fb1525561e772ac9a77d32e28"
    assert "module_run" not in legacy.CODECS
    assert artifact_payload(_run())[0] == "module_run"

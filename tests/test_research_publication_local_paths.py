"""Remote citation URLs cannot hide conflicting local publication originals."""
import hashlib
import json

import pytest

from value_investment_agent.application.product.research_publication_input import prepare_research_publication_input


@pytest.mark.parametrize("mutation", [None, "missing", "hash-drift", "second-local-drift"])
def test_all_declared_local_paths_verified_beside_remote_url(tmp_path, mutation):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    original = runtime / "original.pdf"
    original.write_bytes(b"publication-original")
    source = {"location": "https://example.test/original.pdf", "local_path": "runtime/original.pdf",
              "sha256": hashlib.sha256(original.read_bytes()).hexdigest()}
    if mutation == "missing":
        source["local_path"] = "runtime/missing.pdf"
    elif mutation == "hash-drift":
        source["sha256"] = "0" * 64
    elif mutation == "second-local-drift":
        other = runtime / "other.pdf"
        other.write_bytes(b"unrelated-original")
        source["path"] = "runtime/other.pdf"
    read_model = runtime / "model.json"
    read_model.write_text(json.dumps({
        "schema_version": "historical-company-read-model-preview-v1", "action": "no_order",
        "canonical_written": False, "historical_preview": True,
        "snapshot": {"action": "no_order"}, "source_catalog": [source],
    }), encoding="utf-8")
    output = runtime / "publication.json"
    kwargs = dict(root=tmp_path, read_model_path=read_model,
                  expected_sha256=hashlib.sha256(read_model.read_bytes()).hexdigest(), output_path=output)
    if mutation is not None:
        with pytest.raises((ValueError, FileNotFoundError)):
            prepare_research_publication_input(**kwargs)
        assert not output.exists()
    else:
        result = prepare_research_publication_input(**kwargs)
        assert source["local_path"] in {binding["path"] for binding in result["source_bindings"]}
        assert result["publication_approved"] is False


@pytest.mark.parametrize("mutation", [None, "sibling-drift", "ordinary-evidence-sibling"])
def test_sibling_supersedes_is_verified_without_relaxing_evidence_paths(tmp_path, mutation):
    runtime = tmp_path / "runtime"
    package_dir = runtime / "packages"
    package_dir.mkdir(parents=True)
    prior = package_dir / "previous.json"
    prior.write_text('{"version": "prior"}', encoding="utf-8")
    prior_hash = hashlib.sha256(prior.read_bytes()).hexdigest()
    current = package_dir / "current.json"
    role = "evidence" if mutation == "ordinary-evidence-sibling" else "supersedes"
    current.write_text(json.dumps({role: {"path": prior.name, "sha256": prior_hash}}), encoding="utf-8")
    model = runtime / "model.json"
    model.write_text(json.dumps({
        "schema_version": "historical-company-read-model-preview-v1", "action": "no_order",
        "canonical_written": False, "historical_preview": True, "snapshot": {"action": "no_order"},
        "source_catalog": [{"path": "runtime/packages/current.json",
                            "sha256": hashlib.sha256(current.read_bytes()).hexdigest()}],
    }), encoding="utf-8")
    if mutation == "sibling-drift":
        prior.write_text('{"version": "changed"}', encoding="utf-8")
    args = dict(root=tmp_path, read_model_path=model,
                expected_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
                output_path=runtime / "handoff.json")
    if mutation is not None:
        with pytest.raises((ValueError, FileNotFoundError)):
            prepare_research_publication_input(**args)
        assert not args["output_path"].exists()
    else:
        result = prepare_research_publication_input(**args)
        assert {"path": "runtime/packages/previous.json", "sha256": prior_hash} in result["source_bindings"]
        assert result["publication_approved"] is False

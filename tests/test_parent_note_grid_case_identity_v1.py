"""The versioned Fen case and valuation boundary reopen the official source closure."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from shutil import copyfile

import pytest

from value_investment_agent.application.research import parent_note_grid_case_v1 as adapter


DIRECTORY = "runtime/600809-public-report-sources-20261127"
TEMPLATE = f"{DIRECTORY}/v3-case-template-fenjiu-historical-v1.json"
TEMPLATE_SHA = "65d2b822b655169a521c957b709b3974d6fabd590730d5fbb0ddeaa75889e16f"


def pin(root, path, payload):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    target.write_bytes(blob)
    return {"path": path, "sha256": sha256(blob).hexdigest()}


@pytest.fixture
def evidence(tmp_path):
    root = os.environ.get("FENJIU_SOURCE_ROOT")
    if not root:
        pytest.skip("Set FENJIU_SOURCE_ROOT to the retained public source root")
    root = Path(root)
    template = adapter.legacy._read(root, {"path": TEMPLATE, "sha256": TEMPLATE_SHA})
    spec = json.loads((root / DIRECTORY / "parent-note-grid-source-manifest-v1.json").read_bytes())
    for item in spec["owner_sources"]:
        receipt = item["receipt_binding"]
        record = adapter.legacy._read(root, receipt)
        for binding in (receipt, record["source"], *record["index_bindings"]):
            path = Path(binding["path"])
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            copyfile(root / path, tmp_path / path)
    return tmp_path, spec, template


def package_for_test(root, spec, template, descriptors):
    return dict(symbol=spec["symbol"], sources=descriptors, source_contract=dict(
        schema_version="parent-note-grid-task-receipt-v1", source_adapter_version=adapter.VERSION,
        spec_binding=pin(root, "runtime/test-spec.json", spec),
        case_package_binding=pin(root, "runtime/test-case.json", template)))


def test_fen_case_and_valuation_replay_official_sources(evidence, monkeypatch):
    root, spec, template = evidence
    sources = adapter.verified_descriptors(root, spec, template)
    assert [source["id"] for source in sources] == ["cninfo:1225156714", "cninfo:1225535289"]
    assert all(source["issuer_identity"]["organization_id"] == "gssh0600809" for source in sources)
    package = package_for_test(root, spec, template, sources)

    class ReachedValuationAdapter(Exception):
        pass

    def reached(*args, **kwargs):
        raise ReachedValuationAdapter

    monkeypatch.setattr(adapter.legacy.adapter, "build_direct_owner_cash_descriptor", reached)
    with pytest.raises(ReachedValuationAdapter):
        adapter.run_registered_research(root, package, datetime.now(timezone.utc))

    altered = deepcopy(package)
    altered["sources"][0]["issuer_identity"]["organization_id"] = "gssh0600887"
    with pytest.raises(ValueError, match="NOTE_GRID_VALUATION_SOURCE_CLOSURE_MISMATCH"):
        adapter.run_registered_research(root, altered, datetime.now(timezone.utc))


def test_fen_rejects_wrong_organization_and_substituted_pdf(evidence):
    root, spec, template = evidence
    wrong_org = deepcopy(template)
    wrong_org["sources"][0]["issuer_identity"]["organization_id"] = "gssh0600887"
    with pytest.raises(ValueError, match="NOTE_GRID_CASE_ORIGINAL_IDENTITY_MISMATCH"):
        adapter.verified_descriptors(root, spec, wrong_org)

    sources = adapter.verified_descriptors(root, spec, template)
    package = package_for_test(root, spec, template, sources)
    copyfile(root / sources[1]["local_path"], root / sources[0]["local_path"])
    with pytest.raises(ValueError, match="Retained official evidence binding invalid"):
        adapter.run_registered_research(root, package, datetime.now(timezone.utc))

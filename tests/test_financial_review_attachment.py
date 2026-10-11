"""Integrity and admission boundaries for retained financial supplements."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.application.product.financial_review_attachment import (
    FACTS_SCHEMA, MANIFEST_SCHEMA, SOURCE_SCOPE, STATUS,
    load_financial_review_attachment,
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    script = root / "review.py"
    script.write_text("raise RuntimeError('must never execute')\n", encoding="utf-8")
    source = root / "original.pdf"
    source.write_bytes(b"%PDF-1.4\nsynthetic original\n")
    report = root / "report.md"
    report.write_text("Retained research supplement\n", encoding="utf-8")
    generated = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    binding = {
        "id": "cninfo:12345", "path": str(source), "sha256": _sha(source),
        "source_url": "https://static.cninfo.com.cn/finalpage/2025-05-01/12345.PDF",
        "published_date": "2025-05-01", "available_at_conservative": "2025-05-02T00:00:00+08:00",
        "availability_basis": "date_only_next_day_bound_not_intraday_timestamp",
        "current_local_verified_at": generated, "original_retrieved_at": None,
    }
    fact = {
        "id": "revenue", "source_id": binding["id"], "source_binding": deepcopy(binding),
        "columns": [{"period": "FY2024", "value": "10.01"}],
    }
    payload = {
        "schema_version": FACTS_SCHEMA, "symbol": "600887", "generated_at": generated,
        "financial_period_end": "2024-12-31", "scope": SOURCE_SCOPE,
        "source_bindings": [binding], "facts": [fact],
        "calculations": {"retained": {
            "formula": "existing reviewed definition", "input_fact_ids": ["revenue"],
            "input_column_indices": [0], "value": "10.01", "unit": "CNY", "scope": "consolidated",
        }},
        "limitations": ["Not normalized profit or valuation admission."],
        "model_approved": False, "strict_pit_admitted": False, "price_admitted": False,
        "recommendation": "NO_ACTION", "position_guidance": None, "action": "no_order",
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA, "script": {"path": str(script), "sha256": _sha(script)},
        "source_bindings": [binding], "outputs": {}, "action": "no_order",
    }
    return root, payload, manifest


def _pin(package):
    root, payload, manifest = package
    _write(root / "facts.json", payload)
    manifest["outputs"] = {name: _sha(root / name) for name in ("facts.json", "report.md")}
    _write(root / "manifest.json", manifest)
    return dict(root=root, symbol="600887", manifest_path=root / "manifest.json",
                manifest_sha256=_sha(root / "manifest.json"))


def test_synthetic_projection_is_read_only_and_not_admitted(package):
    args = _pin(package)
    root, payload, _ = package
    before = {path: path.read_bytes() for path in root.iterdir()}
    result = load_financial_review_attachment(**args)
    assert result["status"] == STATUS
    assert result["scope"] == "NOT_ADMITTED"
    assert result["verification_scope"] == "LOCAL_SOURCE_BYTES_ONLY_NOT_FINANCIAL_APPROVAL"
    assert result["action"] == "no_order"
    for key in ("facts", "calculations", "limitations", "financial_period_end", "generated_at", "source_bindings"):
        assert result[key] == payload[key]
    assert result["generated_at_role"] == "ARTIFACT_GENERATION_NOT_RESEARCH_CUTOFF"
    assert all(result[key] is False for key in ("model_approved", "strict_pit_admitted", "price_admitted"))
    assert not {"research_as_of", "cutoff_at", "approved_at", "decision_at"} & result.keys()
    assert {path: path.read_bytes() for path in root.iterdir()} == before


@pytest.mark.parametrize("filename", ["original.pdf", "report.md", "review.py", "facts.json", "manifest.json"])
def test_every_bound_file_is_rehashed(package, filename):
    args = _pin(package)
    with (package[0] / filename).open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_financial_review_attachment(**args)


@pytest.mark.parametrize("filename", ["original.pdf", "report.md", "review.py", "facts.json", "manifest.json"])
def test_missing_file_fails_closed(package, filename):
    args = _pin(package)
    (package[0] / filename).unlink()
    with pytest.raises(ValueError, match="missing"):
        load_financial_review_attachment(**args)


def test_wrong_symbol(package):
    args = _pin(package)
    args["symbol"] = "600519"
    with pytest.raises(ValueError, match="symbol mismatch"):
        load_financial_review_attachment(**args)


@pytest.mark.parametrize("schema_target", [1, 2])
def test_unknown_schema(package, schema_target):
    package[schema_target]["schema_version"] = "unknown-v2"
    with pytest.raises(ValueError, match="schema"):
        load_financial_review_attachment(**_pin(package))


@pytest.mark.parametrize("target,key,value", [
    (1, "action", "order"), (2, "action", "order"),
    (1, "model_approved", True), (1, "strict_pit_admitted", True), (1, "price_admitted", True),
    (1, "recommendation", "BUY"), (1, "position_guidance", {"weight": "0.1"}),
])
def test_admission_and_order_flags_are_rejected(package, target, key, value):
    package[target][key] = value
    with pytest.raises(ValueError, match="no_order"):
        load_financial_review_attachment(**_pin(package))


@pytest.mark.parametrize("timestamp", ["2999-01-01T00:00:00+00:00", "2025-01-01T00:00:00", None])
def test_invalid_or_future_generated_at(package, timestamp):
    package[1]["generated_at"] = timestamp
    with pytest.raises(ValueError, match="generated_at"):
        load_financial_review_attachment(**_pin(package))


def test_future_source_verification(package):
    package[2]["source_bindings"][0]["current_local_verified_at"] = "2999-01-01T00:00:00+00:00"
    package[1]["source_bindings"] = deepcopy(package[2]["source_bindings"])
    with pytest.raises(ValueError, match="future timestamp"):
        load_financial_review_attachment(**_pin(package))


@pytest.mark.parametrize("role", ["manifest", "script", "source"])
@pytest.mark.parametrize("absolute", [False, True])
def test_bound_paths_cannot_escape_root(package, role, absolute):
    root, payload, manifest = package
    outside = root.parent / ("outside.pdf" if role == "source" else "outside.py")
    outside.write_bytes(b"outside")
    path = str(outside) if absolute else "../" + outside.name
    if role == "script":
        manifest["script"] = {"path": path, "sha256": _sha(outside)}
    elif role == "source":
        manifest["source_bindings"][0].update(path=path, sha256=_sha(outside))
        payload["source_bindings"] = deepcopy(manifest["source_bindings"])
    args = _pin(package)
    if role == "manifest":
        _write(outside, manifest)
        args.update(manifest_path=Path(path), manifest_sha256=_sha(outside))
    with pytest.raises(ValueError, match="project root"):
        load_financial_review_attachment(**args)


def test_source_catalog_and_embedded_fact_binding_must_match(package):
    package[1]["facts"][0]["source_binding"]["sha256"] = "a" * 64
    with pytest.raises(ValueError, match="unbound source"):
        load_financial_review_attachment(**_pin(package))


def test_all_sources_verified_even_if_no_fact_uses_them(package):
    extra = deepcopy(package[2]["source_bindings"][0])
    extra.update(id="cninfo:67890", path="missing.pdf",
                 source_url="https://static.cninfo.com.cn/finalpage/2025-05-01/67890.PDF")
    package[2]["source_bindings"].append(extra)
    package[1]["source_bindings"] = deepcopy(package[2]["source_bindings"])
    with pytest.raises(ValueError, match="missing"):
        load_financial_review_attachment(**_pin(package))


def test_unofficial_source_url(package):
    package[2]["source_bindings"][0]["source_url"] = "https://static.cninfo.com.cn.evil.example/12345.PDF"
    package[1]["source_bindings"] = deepcopy(package[2]["source_bindings"])
    with pytest.raises(ValueError, match="official PDF"):
        load_financial_review_attachment(**_pin(package))


def test_undefined_calculation_reference(package):
    package[1]["calculations"]["retained"]["input_column_indices"] = [1]
    with pytest.raises(ValueError, match="undefined fact/column"):
        load_financial_review_attachment(**_pin(package))


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity", "not-a-number", "1,000"])
def test_calculation_value_must_be_finite_decimal(package, value):
    package[1]["calculations"]["retained"]["value"] = value
    with pytest.raises(ValueError, match="finite Decimal"):
        load_financial_review_attachment(**_pin(package))


def test_inspected_historical_review_is_also_rehashed(package):
    old = package[0] / "old.json"
    _write(old, {"research_as_of": "2020-01-01"})
    package[1]["old_review_inspected"] = {
        "path": str(old), "sha256": _sha(old), "consumed_as_fact_object": False,
    }
    args = _pin(package)
    assert "research_as_of" not in load_financial_review_attachment(**args)
    _write(old, {"research_as_of": "2021-01-01"})
    with pytest.raises(ValueError, match="historical review hash mismatch"):
        load_financial_review_attachment(**args)


def test_exact_manifest_hash_is_required(package):
    args = _pin(package)
    args["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        load_financial_review_attachment(**args)


def test_rehash_at_return_detects_mid_load_changes(package, monkeypatch):
    from value_investment_agent.application.product import financial_review_attachment as module

    args = _pin(package)
    original_hash = module.sha256_file
    calls = 0

    def changing_hash(path):
        nonlocal calls
        result = original_hash(path)
        if path.name == "original.pdf":
            calls += 1
            if calls == 1:
                path.write_bytes(b"changed after first hash")
        return result

    monkeypatch.setattr(module, "sha256_file", changing_hash)
    with pytest.raises(ValueError, match="final verification hash mismatch"):
        load_financial_review_attachment(**args)

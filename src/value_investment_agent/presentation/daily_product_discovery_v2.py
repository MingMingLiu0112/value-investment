"""Versioned discovery overlay for the existing daily product contract."""
from __future__ import annotations

from pathlib import Path

from value_investment_agent.application.product.common import (
    load_json_object, require_inside, sha256_file, write_new_json,
)
from value_investment_agent.application.product.research_publication_input import (
    load_research_publication_input, prepare_research_publication_input,
)
from value_investment_agent.application.research.value_research_queue import build_value_research_queue
from value_investment_agent.application.product.daily_product_update import semantic_digest
from .daily_product_composition import compose_daily_product


def _bound(root: Path, binding: dict, label: str) -> tuple[Path, dict]:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError(f"{label} requires path and SHA-256")
    path = require_inside(root / "runtime", root / binding["path"], label)
    if sha256_file(path) != binding["sha256"]:
        raise ValueError(f"{label} hash mismatch")
    return path, load_json_object(path, label)


def verify_discovery_bindings(root: Path, bindings: dict) -> None:
    if ("value_discovery_report" in bindings) != ("value_research_queue" in bindings):
        raise ValueError("M2 discovery and research queue must be supplied together")
    if "value_discovery_report" not in bindings:
        if "m2_pending_research" in bindings:
            raise ValueError("pending M2 research requires a bound queue")
        return
    _, report = _bound(root, bindings["value_discovery_report"], "M2 report")
    _, queue = _bound(root, bindings["value_research_queue"], "M2 queue")
    if (report.get("action") != "no_order" or report.get("status") != "RESEARCH_LEADS_ONLY"
            or queue.get("action") != "no_order" or queue.get("admission") != "RESEARCH_QUEUE_ONLY"
            or queue.get("inputs", {}).get("report_sha256") != bindings["value_discovery_report"]["sha256"]):
        raise ValueError("M2 discovery/queue scope mismatch")
    inputs = queue["inputs"]
    rebuilt = build_value_research_queue(
        root=root, report_path=root / inputs["report_path"],
        report_sha256=inputs["report_sha256"],
        receipt_path=root / inputs["receipt_path"],
        receipt_sha256=inputs["receipt_sha256"], budget=queue["budget"],
        previous_path=root / inputs["previous_queue_path"] if inputs.get("previous_queue_path") else None,
        previous_sha256=inputs.get("previous_queue_sha256"),
    )
    if queue != rebuilt:
        raise ValueError("M2 queue is not a replay of bound original inputs")
    if "m2_pending_research" in bindings:
        _, pending = _bound(root, bindings["m2_pending_research"], "pending M2 research")
        selected = {item["symbol"] for item in queue["entries"]
                    if item["queue_status"] == "SELECTED_FOR_DATA_CHECK"}
        if (pending.get("schema_version") != "m2-pending-research-intake-v1"
                or pending.get("action") != "no_order"
                or pending.get("decision_admitted") is not False
                or pending.get("quote_admitted") is not False
                or pending.get("symbol") not in selected
                or pending.get("m2_queue_binding") != bindings["value_research_queue"]):
            raise ValueError("pending M2 research is not bound to selected non-admitted lead")


def compose_daily_product_v2(*, root: Path, folder: Path, published: dict,
                             batch: dict, extensions: dict):
    verify_discovery_bindings(root, extensions)
    product, changes = compose_daily_product(root=root, folder=folder,
        published=published, batch=batch, extensions=extensions)
    if "value_discovery_report" not in extensions:
        return product, changes
    prior_binding = published["pointer"].get("daily_product_state_binding")
    prior = _bound(root, prior_binding, "prior daily state")[1] if prior_binding else None
    current = _bound(root, product["state_binding"], "current daily state")[1]
    old_extensions = (prior or {}).get("content", {}).get("extensions", {})
    new_extensions = current["content"]["extensions"]
    discovery_roles = ("value_discovery_report", "value_research_queue", "m2_pending_research")
    discovery_changed = any(semantic_digest(old_extensions.get(role)) != semantic_digest(new_extensions.get(role))
                            for role in discovery_roles)
    risk_changed = semantic_digest(old_extensions.get("dual_sleeve_report")) != semantic_digest(
        new_extensions.get("dual_sleeve_report"))
    if discovery_changed:
        categories = set(changes["categories"])
        categories.add("VALUE_DISCOVERY_CHANGE")
        if not risk_changed:
            categories.discard("PORTFOLIO_RISK_CHANGE")
        changes["categories"] = sorted(categories)
    read_binding = product["handoff"]["read_model_binding"]
    _, envelope = _bound(root, read_binding, "daily product read model")
    for source in (
        root / "scripts/current/render_dual_strategy_artifact_pages_v2.mjs",
        root / "src/value_investment_agent/presentation/daily_product_discovery_v2.py",
    ):
        envelope.setdefault("additional_evidence_bindings", []).append({
            "path": source.relative_to(root).as_posix(), "sha256": sha256_file(source),
        })
    envelope["product_renderer_version"] = "dual-strategy-discovery-v2"
    read_path = folder / "product-read-model-v2.json"
    write_new_json(read_path, envelope)
    handoff_path = folder / "product-publication-input-v2.json"
    handoff = prepare_research_publication_input(root=root, read_model_path=read_path,
        expected_sha256=sha256_file(read_path), output_path=handoff_path)
    product.update(handoff=handoff, handoff_path=handoff_path,
                   renderer_version="dual-strategy-discovery-v2",
                   extension_bindings={role: extensions[role] for role in discovery_roles
                                       if role in extensions})
    return product, changes


def prepare_historical_discovery_preview(*, root: Path, output_dir: Path,
                                         bindings: dict) -> dict:
    """Overlay research-only discovery on the last verified product, never publish it."""
    root = root.resolve()
    output_dir = require_inside(root / "runtime", output_dir, "M2 historical preview")
    if output_dir.exists():
        raise FileExistsError("historical preview output must be new")
    verify_discovery_bindings(root, bindings)
    if "value_discovery_report" not in bindings:
        raise ValueError("historical discovery preview requires M2 report and queue")
    pointer = load_json_object(root / "config/current-trial-workbook.json", "canonical pointer")
    publication = pointer["current_publication"]
    receipt_path = require_inside(root / "runtime", root / publication["receipt"], "publication receipt")
    if sha256_file(receipt_path) != publication["receipt_sha256"]:
        raise ValueError("published receipt hash mismatch")
    receipt = load_json_object(receipt_path, "publication receipt")
    sources_path = require_inside(root / "runtime", root / receipt["source_bindings_path"], "source ledger")
    if sha256_file(sources_path) != receipt["source_bindings_sha256"]:
        raise ValueError("published source ledger hash mismatch")
    sources = load_json_object(sources_path, "source ledger")
    parent = sources["publication_input_binding"]
    handoff = load_research_publication_input(root=root, path=root / parent["path"],
                                               expected_sha256=parent["sha256"])
    _, envelope = _bound(root, handoff["read_model_binding"], "published read model")
    if envelope.get("product_extensions", {}).keys() & bindings.keys():
        raise ValueError("historical preview role already exists in published product")
    envelope["product_extensions"] = dict(envelope.get("product_extensions", {}), **bindings)
    for source in (
        root / "scripts/current/render_dual_strategy_artifact_pages_v2.mjs",
        root / "src/value_investment_agent/presentation/daily_product_discovery_v2.py",
    ):
        envelope.setdefault("additional_evidence_bindings", []).append({
            "path": source.relative_to(root).as_posix(), "sha256": sha256_file(source),
        })
    envelope["product_renderer_version"] = "dual-strategy-discovery-v2"
    output_dir.mkdir(parents=True)
    read_path = output_dir / "product-read-model-v2.json"
    write_new_json(read_path, envelope)
    handoff_path = output_dir / "product-publication-input-v2.json"
    result = prepare_research_publication_input(root=root, read_model_path=read_path,
        expected_sha256=sha256_file(read_path), output_path=handoff_path)
    return {"action": "no_order", "historical_preview": True, "canonical_written": False,
            "publication_input_path": handoff_path.relative_to(root).as_posix(),
            "publication_input_sha256": sha256_file(handoff_path),
            "source_count": len(result["source_bindings"])}

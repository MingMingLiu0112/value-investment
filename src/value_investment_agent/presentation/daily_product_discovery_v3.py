"""FM-3 overlay without modifying the source-bound v2 publication contract."""
from __future__ import annotations

from pathlib import Path

from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.application.product.daily_product_update import semantic_digest
from value_investment_agent.application.product.research_publication_input import prepare_research_publication_input
from .daily_product_discovery_v2 import _bound, compose_daily_product_v2


def compose_daily_product_v3(*, root: Path, folder: Path, published: dict,
                             batch: dict, extensions: dict):
    for role, schema in (
        ("m2_quality_diagnostic", "m2-quality-diagnostic-v1"),
        ("market_regime_observation", "market-regime-observation-v1"),
        ("hotspot_watch_queue", "hotspot-watch-queue-v1"),
    ):
        if role not in extensions:
            raise ValueError(f"FM-3 {role} binding missing")
        _, value = _bound(root, extensions[role], role)
        if value.get("schema_version") != schema or value.get("action") != "no_order":
            raise ValueError(f"FM-3 {role} contract mismatch")
    _, market = _bound(root, extensions["market_regime_observation"], "market regime")
    if market.get("position_guidance") is not None or market.get("regime") != "UNKNOWN":
        raise ValueError("unadmitted market regime cannot set positions or an inferred category")
    _, queue = _bound(root, extensions["hotspot_watch_queue"], "hotspot watch queue")
    if any(item.get("action") != "no_order" for item in queue.get("items", [])):
        raise ValueError("hotspot queue cannot contain orders")
    product, changes = compose_daily_product_v2(root=root, folder=folder,
        published=published, batch=batch, extensions=extensions)
    _, envelope = _bound(root, product["handoff"]["read_model_binding"], "FM-2 read model")
    pending = envelope.get("product_extensions", {}).get("m2_pending_research")
    if pending and pending not in (extensions.get("m2_pending_research"),):
        _, old_pending = _bound(root, pending, "previous M2 pending research")
        if old_pending.get("m2_queue_binding") != extensions["value_research_queue"]:
            envelope["product_extensions"].pop("m2_pending_research")
            _, state = _bound(root, product["state_binding"], "FM-2 product state")
            state["content"]["extensions"].pop("m2_pending_research", None)
            state["semantic_sha256"] = semantic_digest(state["content"])
            state_path = folder / "product-update-state-v3.json"
            write_new_json(state_path, state)
            product["state_binding"] = {"path": state_path.relative_to(root).as_posix(),
                                        "sha256": sha256_file(state_path)}
            changes["current_semantic_sha256"] = state["semantic_sha256"]
            changes["material_change"] = changes["previous_semantic_sha256"] != state["semantic_sha256"]
    for source in (
        root / "scripts/current/render_dual_strategy_artifact_pages_v3.mjs",
        root / "src/value_investment_agent/presentation/daily_product_discovery_v3.py",
    ):
        envelope.setdefault("additional_evidence_bindings", []).append({
            "path": source.relative_to(root).as_posix(), "sha256": sha256_file(source)})
    envelope["product_renderer_version"] = "dual-strategy-discovery-v3"
    read_path = folder / "product-read-model-v3.json"
    write_new_json(read_path, envelope)
    handoff_path = folder / "product-publication-input-v3.json"
    handoff = prepare_research_publication_input(root=root, read_model_path=read_path,
        expected_sha256=sha256_file(read_path), output_path=handoff_path)
    product.update(handoff=handoff, handoff_path=handoff_path,
                   renderer_version="dual-strategy-discovery-v3")
    return product, changes

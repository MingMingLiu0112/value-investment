import json

from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.application.product.daily_product_update import semantic_digest
from value_investment_agent.presentation import daily_product_discovery_v3 as module


def test_old_pending_case_is_not_inherited_by_new_queue(tmp_path, monkeypatch):
    root = tmp_path
    runtime = root / "runtime"
    runtime.mkdir()
    folder = runtime / "current"
    folder.mkdir()

    def bound(name, value):
        path = runtime / (name + ".json")
        write_new_json(path, value)
        return {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}

    old_queue = {"path": "runtime/old-queue.json", "sha256": "a" * 64}
    queue = bound("queue", {"action": "no_order"})
    pending = bound("pending", {"action": "no_order", "m2_queue_binding": old_queue})
    extensions = {
        "value_research_queue": queue,
        "m2_quality_diagnostic": bound("quality", {
            "schema_version": "m2-quality-diagnostic-v1", "action": "no_order"}),
        "market_regime_observation": bound("market", {
            "schema_version": "market-regime-observation-v1", "action": "no_order",
            "regime": "UNKNOWN", "position_guidance": None}),
        "hotspot_watch_queue": bound("hotspot", {
            "schema_version": "hotspot-watch-queue-v1", "action": "no_order", "items": []}),
    }
    state_content = {"extensions": {"m2_pending_research": {"stale": True}}}
    state = bound("state", {"action": "no_order", "content": state_content,
                            "semantic_sha256": semantic_digest(state_content)})
    read = bound("read", {"product_extensions": {"m2_pending_research": pending}})
    for name in ("render_dual_strategy_artifact_pages_v3.mjs",):
        path = root / "scripts/current" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// test renderer", encoding="utf-8")
    source = root / "src/value_investment_agent/presentation/daily_product_discovery_v3.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# test source", encoding="utf-8")
    product = {"state_binding": state, "handoff": {"read_model_binding": read}}
    changes = {"previous_semantic_sha256": "b" * 64, "categories": ["VALUE_DISCOVERY_CHANGE"]}
    monkeypatch.setattr(module, "compose_daily_product_v2", lambda **_: (product, changes))
    monkeypatch.setattr(module, "prepare_research_publication_input", lambda **_: {
        "read_model_binding": read})

    result, updated = module.compose_daily_product_v3(root=root, folder=folder,
        published={}, batch={}, extensions=extensions)
    next_state = json.loads((root / result["state_binding"]["path"]).read_text())
    next_read = json.loads((folder / "product-read-model-v3.json").read_text())
    assert "m2_pending_research" not in next_state["content"]["extensions"]
    assert "m2_pending_research" not in next_read["product_extensions"]
    assert updated["material_change"] is True

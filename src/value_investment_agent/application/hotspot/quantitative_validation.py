"""Source-bound quantitative protocol loading, computation and non-admission."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json

from .event_replay import _bound_bytes
from ...domain.hotspot.quantitative_validation import simulate_fold, stamp


@dataclass(frozen=True)
class ProtocolBinding:
    path: str
    sha256: str

    def __post_init__(self):
        if (not isinstance(self.path, str) or not self.path or Path(self.path).is_absolute()
                or not isinstance(self.sha256, str) or len(self.sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.sha256)):
            raise ValueError("Invalid quantitative protocol binding")


def compute_quantitative_validation(*, root: Path, binding: ProtocolBinding,
                                    protocol: dict, now: datetime) -> dict:
    root = root.resolve()
    # Repeat binding verification at the computation boundary, including callers
    # using this service directly instead of the public validation entrypoint.
    bound = json.loads(_bound_bytes(root, dict(path=binding.path, sha256=binding.sha256)))
    if bound != protocol:
        raise ValueError("Quantitative protocol differs from bound bytes")
    if (protocol.get("schema_version") != "hotspot-execution-protocol-v1"
            or protocol.get("action") != "no_order"
            or protocol.get("namespace") not in ("TEST_ONLY", "ACTUAL")
            or protocol.get("parameters_changed") is not False):
        raise ValueError("Unsupported quantitative protocol specification")
    if now.utcoffset() is None or stamp(protocol["registered_at"]) > now:
        raise ValueError("Protocol registration must precede computation")
    inputs = json.loads(_bound_bytes(root, protocol["input_binding"]))
    costs = json.loads(_bound_bytes(root, protocol["cost_binding"]))
    namespace = protocol["namespace"]
    if inputs.get("namespace") != namespace or costs.get("namespace") != namespace:
        raise ValueError("Execution evidence namespace mismatch")
    if stamp(costs["known_at"]) > stamp(protocol["registered_at"]):
        raise ValueError("Cost basis must be frozen before protocol registration")
    if stamp(costs["effective_start"]) >= stamp(costs["effective_end"]):
        raise ValueError("Dated cost validity interval required")
    if not protocol.get("rule_bindings"):
        raise ValueError("Frozen source-bound rules required")
    for rule in protocol["rule_bindings"]:
        _bound_bytes(root, rule)
    folds = protocol["folds"]
    if not folds or len({f["id"] for f in folds}) != len(folds):
        raise ValueError("Distinct OOS folds required")
    previous = None
    for fold in folds:
        train_start, train_end, start, end = (stamp(fold[k]) for k in
            ("train_start", "train_end", "test_start", "test_end"))
        if (not train_start <= train_end < start <= end <= now
                or stamp(protocol["registered_at"]) > start
                or (previous is not None and start <= previous)):
            raise ValueError("Predeclared disjoint OOS fold cutoff required")
        previous = end
    if any(o["fold"] not in {f["id"] for f in folds} for o in inputs["orders"]):
        raise ValueError("Unknown execution fold")
    configured = {**protocol, "costs": costs}
    results = [simulate_fold(configured, inputs, f) for f in folds]
    sensitivity = [dict(multiplier=str(m), folds=[simulate_fold(configured, inputs, f,
        cost_multiplier=m) for f in folds]) for m in (Decimal(0), Decimal(2))]
    count = sum(f["trade_count"] for f in results)
    minimum = protocol["minimum_oos_trades"]
    if type(minimum) is not int or minimum < 1:
        raise ValueError("Predeclared positive sample requirement required")
    insufficient = count < minimum
    # Detect source/rule edits while the numeric replay was running.
    for source in [dict(path=binding.path, sha256=binding.sha256),
                   protocol["input_binding"], protocol["cost_binding"], *protocol["rule_bindings"]]:
        _bound_bytes(root, source)
    return dict(schema_version="hotspot-execution-metrics-v1", namespace=namespace,
        protocol_binding=dict(path=binding.path, sha256=binding.sha256),
        source_bindings=[protocol["input_binding"], protocol["cost_binding"], *protocol["rule_bindings"]],
        evaluated_at=now.isoformat(), status="PARTIAL", metrics_scope="FROZEN_ORDER_EXECUTION_SIMULATION",
        folds=results, cost_sensitivity=sensitivity, trade_count=count,
        partitions=folds, training_performed=False,
        oos_scope="FROZEN_ORDERS_WITHIN_PREDECLARED_WINDOWS_NOT_CERTIFIED_STRATEGY_OOS",
        return_units="FRACTION", monetary_units="CNY",
        sample_status="INSUFFICIENT" if insufficient else "COUNT_ONLY_NOT_RESEARCH_ADMISSION",
        sample_admission_status="REJECTED_INSUFFICIENT_SAMPLE" if insufficient else "NOT_PROVEN",
        minimum_oos_trades=minimum,
        actual_sample_accepted=False, strategy_validation="NOT_PROVEN",
        strict_pit_admitted=False, strict_oos_admitted=False,
        limitations=["Simulated fills are not broker executions",
            "Frozen supplied signals are not proof of historical selection or universe PIT",
            "Each fold resets cash and inventory; open positions are right censored",
            "Full exits only; no partial fills, corporate actions or execution queue model",
            "Trade count alone cannot establish significance or independent strategy approval"],
        formal_eligibility=False, performance_claim_allowed=False, action="no_order")

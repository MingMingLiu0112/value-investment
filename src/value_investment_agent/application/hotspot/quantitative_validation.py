"""Source-bound quantitative protocol loading, computation and non-admission."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json

from .event_replay import _bound_bytes
from ...domain.hotspot.quantitative_validation import simulate_fold, stamp


def build_economic_validation_draft(*, now: datetime) -> dict:
    """Executable proposed design, not a registration, signature or approved policy."""
    if now.utcoffset() is None:
        raise ValueError('Aware draft creation clock required')
    return dict(schema_version='hotspot-economic-validation-draft-v1', status='DRAFT',
        created_at=now.isoformat(), registered_at=None, approval_status='NOT_APPROVED',
        design_source='docs/current/swing-strategy-specification-20261023.md#5',
        block_count=3, block_sessions=42, benchmarks=['CASH', 'SAME_POOL_EQUAL_WEIGHT'],
        block_acceptance='ALL_THREE_BLOCKS_MUST_MEET_EXPLICIT_POLICY',
        cost_multipliers=['0', '1', '2'],
        economic_policy=dict(minimum_excess_cash='0', minimum_excess_pool='0',
            maximum_drawdown='0.20', minimum_trades=30,
            uncertainty_method='STATIONARY_BOOTSTRAP_MEAN_PAIRED_DAILY_EXCESS_LOWER',
            uncertainty_parameters=dict(block_length=10, resamples=2000, confidence='0.95',
                seed=20261025, minimum_effective_blocks=12),
            uncertainty_application='FULL_126_SESSION_WINDOW',
            minimum_excess_lower_bound='0', cost_evaluation='BASE_NET_WITH_2X_CASH_FLOOR'),
        policy_status='CANDIDATE_FOR_RESEARCH_REVIEW_NOT_AUTHORIZED_PERSONAL_RISK',
        policy_rationale=dict(excess='Positive net excess to both declared benchmarks; no fitted margin',
            drawdown='20 percent subjective pilot risk cap, not an industry standard or user IPS',
            sample='30 closed trades per 42-session block is a demanding pilot guard, not statistical power proof',
            blocks='10-day expected block spans twice the existing five-session exit experiment',
            uncertainty='One-sided 95 percent paired stationary-bootstrap bound; assumptions unproven',
            effective_blocks='12 expected blocks is a pilot guard, not independence proof',
            stress='2x-cost return must not fall below the declared cash benchmark'),
        required_evidence=['CONTEMPORANEOUS_POOL_AND_CLASSIFICATION', 'ARCHIVED_SOURCE_PIT',
            'UNTOUCHED_PREDECLARED_WINDOWS', 'RULE_AND_COST_BINDINGS',
            'DATED_TRADABILITY_AND_CORPORATE_ACTIONS', 'PAIRED_PORTFOLIO_BENCHMARKS',
            'PREDECLARED_ECONOMIC_AND_UNCERTAINTY_POLICY'],
        parameters_changed=False, formal_eligibility=False, action='no_order')


def compute_paired_stationary_uncertainty(rows: list, parameters: dict) -> dict:
    """Optional mature-library time-series calculation, never an OOS attestation."""
    import math
    from hashlib import sha256
    from importlib.metadata import version
    import numpy as np
    from arch.bootstrap import StationaryBootstrap
    from ...domain.execution.exchange_calendar import is_exchange_session, next_exchange_session

    if version('arch') != '8.0.0':
        raise ValueError('Reviewed arch 8.0.0 research runtime required')
    block, reps, seed = (parameters[k] for k in ('block_length', 'resamples', 'seed'))
    minimum = parameters['minimum_effective_blocks']
    confidence = float(parameters['confidence'])
    if (type(block) is not int or not 2 <= block <= len(rows)
            or type(reps) is not int or not 200 <= reps <= 10000 or type(seed) is not int
            or type(minimum) is not int or minimum < 2 or not 0 < confidence < 1):
        raise ValueError('Explicit bounded time-series bootstrap parameters required')
    dates = [row['date'] for row in rows]
    if dates != sorted(set(dates)):
        raise ValueError('Unique ordered paired dates required')
    previous = None
    for text in dates:
        day = datetime.fromisoformat(text).date()
        if (day.isoformat() != text or not is_exchange_session('SSE', day)
                or (previous and day != next_exchange_session('SSE', previous))):
            raise ValueError('Complete consecutive paired exchange sessions required')
        previous = day
    if any(type(row[key]) is bool for row in rows for key in ('daily_excess_cash', 'daily_excess_pool')):
        raise ValueError('Boolean is not a paired return')
    data = np.array([[float(row['daily_excess_cash']), float(row['daily_excess_pool'])]
                     for row in rows], dtype=float)
    if not np.isfinite(data).all():
        raise ValueError('Finite paired excess returns required')
    bootstrap = StationaryBootstrap(block, data, seed=seed)
    interval = bootstrap.conf_int(lambda sample: sample.mean(axis=0), reps=reps,
        method='percentile', size=confidence, tail='lower')
    lower = [float(value) for value in interval[0]]
    if not all(math.isfinite(value) for value in lower):
        raise ValueError('Nonfinite bootstrap bound')
    return dict(method='STATIONARY_BOOTSTRAP_MEAN_PAIRED_DAILY_EXCESS_LOWER',
        engine='arch==8.0.0', parameters=dict(parameters), observed_days=len(rows),
        implementation_binding=dict(path='src/value_investment_agent/application/hotspot/quantitative_validation.py',
            sha256=sha256(Path(__file__).read_bytes()).hexdigest()),
        expected_block_count=str(len(rows) / block),
        sample_status='INSUFFICIENT' if len(rows) < block * minimum else 'DIAGNOSTIC_ONLY',
        cash_excess_lower_bound=str(lower[0]), pool_excess_lower_bound=str(lower[1]),
        upper_bound=None, units='MEAN_DAILY_RETURN_FRACTION',
        coverage_scope='MARGINAL_ONE_SIDED_BOUNDS_NOT_SIMULTANEOUS_CONFIDENCE_REGION',
        interval_scope='CONDITIONAL_ON_STATIONARITY_AND_DEPENDENCE_ASSUMPTIONS_NOT_VERIFIED_OOS',
        formal_eligibility=False, strict_oos_admitted=False, action='no_order')


def diagnose_retained_economic_draft(*, root: Path, binding: 'ProtocolBinding',
                                     now: datetime) -> dict:
    """Run verified existing real/fixture replay without fabricating portfolio blocks."""
    from .independent_validation import _execution_evidence
    from ...domain.hotspot.quantitative_validation import evaluate_economic_validation_draft
    if now.utcoffset() is None:
        raise ValueError('Aware diagnostic cutoff required')
    ref = dict(path=binding.path, sha256=binding.sha256)
    protocol = json.loads(_bound_bytes(root, ref))
    if stamp(protocol['created_at']) > now:
        raise ValueError('Draft unavailable at evaluation cutoff')
    replay = _execution_evidence(root, now)
    # Existing fixed-five independent accounts cannot become a pooled benchmark
    # by averaging returns; absent paired results remain absent.
    evaluation = evaluate_economic_validation_draft(protocol, [])
    evaluation['checks'].extend([
        dict(check='PREDECLARED_UNTOUCHED_OOS',
            status='INSUFFICIENT_DATA' if replay['protocol']['registered_before_validation'] else 'FAIL',
            reason='Declared registration is not independent proof; retrospective registration fails'),
        dict(check='HISTORICAL_SOURCE_PIT',
            status='FAIL' if replay['decision_availability']['source_acquired_after_decision'] else 'INSUFFICIENT_DATA',
            reason='Use actual source acquisition versus generated historical decision clocks'),
        dict(check='PAIRED_PORTFOLIO_BENCHMARKS', status='INSUFFICIENT_DATA',
            reason='No comparable net cash/same-pool portfolio benchmark was supplied or fabricated'),
    ])
    evaluation.update(protocol_binding=ref, evaluated_at=now.isoformat(),
        retained_replay_content_sha256=replay['replay_content_sha256'],
        retained_summary=replay['summary'],
        diagnostic_partitions=replay['costed_partitions'],
        existing_protocol=replay['protocol'], decision_availability=replay['decision_availability'],
        strict_rejection_counts=replay['strict_rejection_counts'],
        evidence_gaps=['PAIRED_NET_CASH_AND_SAME_POOL_BENCHMARKS_MISSING',
            'THREE_42_SESSION_BLOCK_RESULTS_MISSING', 'ECONOMIC_POLICY_NOT_PREDECLARED',
            'DATED_TRADABILITY_AND_COMPANY_ACTIONS_NOT_PROVEN', 'UNTOUCHED_OOS_NOT_PROVEN',
            'NATURAL_TIME_SHADOW_NOT_ASSESSED'],
        source_bindings=replay['source_bindings'])
    _bound_bytes(root, ref)
    for source in replay['source_bindings']:
        _bound_bytes(root, source)
    return evaluation


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

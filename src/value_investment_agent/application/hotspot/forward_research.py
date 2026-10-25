"""Append-only public forward observations; no strategy admission or paper fills."""
from datetime import datetime, timezone, time
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from .daily_selection import verify_daily_selection
from .price_action_case import project_current_price_action_plan
from .independent_price_conditions import INDEPENDENT_OPEN_RULE
from .independent_admission import _contains_test_namespace
from ...domain.hotspot.shadow_observation import make_shadow_baseline, compare_archived_baseline
from ...domain.hotspot.strategy_execution_replay import DEFAULT_INITIAL_CASH_CNY, EXPERIMENT_VERSION
from ...domain.execution.exchange_calendar import is_exchange_session
from ...infrastructure.hotspot.current_price_case import (
    collect_current_price_case, load_current_price_case,
)
from ...quote_session_collection import collect_session_bundle
from ...quote_sessions import CHINA


CODE_ROOT = Path(__file__).resolve().parents[4]
RULE_FILES = tuple("src/value_investment_agent/" + name for name in (
    "application/hotspot/forward_research.py",
    "application/hotspot/daily_selection.py",
    "application/hotspot/price_action_case.py",
    "application/hotspot/independent_price_conditions.py",
    "application/hotspot/independent_admission.py",
    "application/hotspot/strategy_execution_replay.py",
    "application/hotspot/quantitative_validation.py",
    "domain/hotspot/daily_selection.py",
    "domain/hotspot/current_price.py",
    "domain/hotspot/price_action_plan.py",
    "domain/hotspot/confirmed_price_structure.py",
    "domain/hotspot/opportunity_quality.py",
    "domain/hotspot/shadow_observation.py",
    "domain/hotspot/strategy_execution_replay.py",
    "domain/hotspot/quantitative_validation.py",
    "domain/execution/exchange_calendar.py",
    "infrastructure/hotspot/current_price_case.py",
    "infrastructure/hotspot/sina_price_case.py",
    "infrastructure/hotspot/daily_market.py",
    "m2_market_data.py", "quote_session_collection.py", "quote_sessions.py",
))


def _stamp(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Aware timestamp required")
    return value.astimezone(CHINA)


def _clock(test_only, now):
    if type(test_only) is not bool or (not test_only and now is not None):
        raise ValueError("Clock injection is TEST_ONLY")
    return _stamp(now if now is not None else datetime.now(timezone.utc))


def _binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())


def _read(root, binding):
    if Path(binding['path']).is_absolute() or '..' in Path(binding['path']).parts:
        raise ValueError('Canonical relative source path required')
    path = (root / binding["path"]).resolve()
    if (not path.is_relative_to(root) or not path.is_relative_to((root / "runtime").resolve())
            or path.stat().st_size > 16_000_000):
        raise ValueError("Source must be inside runtime")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("Source hash changed")
    return json.loads(raw)


def _write(root, path, value):
    if not path.resolve().is_relative_to(root / 'runtime'):
        raise ValueError('Forward writes must remain inside workspace runtime')
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, sort_keys=True, allow_nan=False)
    return _binding(root, path)


def _rules():
    return [dict(path=name, sha256=sha256((CODE_ROOT / name).read_bytes()).hexdigest())
            for name in RULE_FILES]


def _costs():
    from inspect import signature
    from .strategy_execution_replay import build_strategy_execution_replay, OFFICIAL_SOURCES
    parameters = signature(build_strategy_execution_replay).parameters
    rates = {row['topic']: row['rate'] for row in OFFICIAL_SOURCES if 'rate' in row}
    return dict(commission_rate=str(parameters['commission_rate'].default),
        minimum_commission_cny=str(parameters['minimum_commission_cny'].default),
        slippage_bps=str(parameters['slippage_bps'].default),
        sell_tax_rate=rates['SELL_STAMP_TAX_HALVED_FROM_20230828'],
        transfer_fee_rate=rates['TRANSFER_FEE_DOUBLE_SIDED_FROM_20220429'],
        scope='ASSUMED_RESEARCH_COSTS_NOT_VERIFIED_PERSONAL_OR_CURRENT_POLICY')


def _execution_policy():
    from inspect import signature
    from ...domain.hotspot.strategy_execution_replay import replay_shared_strategy_execution
    return dict(experiment_version=EXPERIMENT_VERSION + '-shared-feedback-v1',
        quantity=signature(replay_shared_strategy_execution).parameters['quantity'].default,
        mode='STRICT_OBSERVATION_ONLY', missing_dated_state='NO_FILL',
        invalid_board_quantity='NO_FILL_NO_AUTOMATIC_SIZE_UPGRADE')


def _reject_test_source(value, test_only):
    if not test_only and (_contains_test_namespace(value) or value.get('test_only') is True
            or value.get('fixture_scope') in {'TEST_ONLY', 'SIMULATED', 'SYNTHETIC'}
            or value.get('namespace') == 'SYNTHETIC'):
        raise ValueError('Test or simulated source cannot enter ACTUAL forward research')


def _selection(root, binding, cutoff, test_only=False):
    report = _read(root, binding)
    _reject_test_source(report, test_only)
    verify_daily_selection(root, report)
    for source in report['source_bindings']:
        if Path(source['path']).suffix.lower() == '.json':
            _reject_test_source(_read(root, source), test_only)
    if not isinstance(report.get("candidate_pool"), list):
        raise ValueError("Explicit verified candidate pool required")
    for stamp in [report["available_at"],
                  *(item["available_at"] for item in report["source_bindings"])]:
        if _stamp(stamp) > cutoff:
            raise ValueError("Candidate evidence unavailable at freeze")
    symbols = sorted(row["symbol"] for row in report["candidate_pool"])
    if not symbols or len(symbols) != len(set(symbols)) or len(symbols) > 10:
        raise ValueError("One to ten unique frozen candidates required")
    return report, symbols


def freeze_forward_research(*, root: Path, candidate_binding: dict,
                            test_only=False, now=None) -> dict:
    """Freeze a verified public pool and real module hashes, without collecting."""
    root = Path(root).resolve()
    cutoff = _clock(test_only, now)
    report, symbols = _selection(root, candidate_binding, cutoff, test_only)
    rules = _rules()
    from .quantitative_validation import build_economic_validation_draft
    manifest = dict(schema_version="hotspot-forward-research-v1", status="DRAFT",
        approved=False, namespace="TEST_ONLY" if test_only else "ACTUAL", action="no_order",
        frozen_at=cutoff.isoformat(), candidate_binding=dict(candidate_binding),
        candidate_source_bindings=report["source_bindings"], symbols=symbols, rule_bindings=rules,
        initial_cash_cny=str(DEFAULT_INITIAL_CASH_CNY), capital_scope="COMMON_CASH_ACCOUNT",
        simultaneous_order_convention="TIMESTAMP_THEN_SYMBOL_ASCENDING_NOT_REAL_ORDER_PRIORITY",
        costs=_costs(),
        execution_policy=_execution_policy(),
        economic_candidate=build_economic_validation_draft(now=cutoff),
        benchmark_policy=dict(cash='ZERO_INTEREST_ZERO_FEES',
            pool='FROZEN_COHORT_TARGET_EQUAL_CASH_BUY_HOLD', cost_multipliers=['0', '1', '2'],
            terminal='MARK_UNREALIZED_NO_FORCED_LIQUIDATION'),
        calendar_coverage='2026_ONLY_FAIL_CLOSED',
        pool_scope='FIXED_FROZEN_RESEARCH_COHORT_NOT_FUTURE_ALL_MARKET_SELECTION',
        source_authentication='HASH_AND_PROVIDER_CONTRACT_NOT_INDEPENDENT_SOURCE_ATTESTATION',
        stock_state_policy="UNKNOWN_UNLESS_DATED_EVIDENCE_VERIFIED",
        corporate_action_policy="UNADJUSTED_PRICE_STRUCTURE_REQUIRES_CORPORATE_ACTION_REVIEW",
        execution_status="UNASSESSABLE", hypothetical_fills=None,
        elapsed_real_shadow_sessions=0, strict_pit_admitted=False, strict_oos_admitted=False,
        strategy_validation="NOT_PROVEN", formal_eligibility=False)
    directory = root / "runtime" / "hotspot-forward" / uuid4().hex
    if not directory.resolve().is_relative_to(root / 'runtime'):
        raise ValueError('Forward manifest directory escapes runtime')
    directory.mkdir(parents=True, exist_ok=False)
    return _write(root, directory / "manifest.json", manifest)


def _verify_freeze(root, binding, test_only, cutoff):
    manifest = _read(root, binding)
    path = (root / binding["path"]).resolve()
    if (not path.is_relative_to(root / "runtime/hotspot-forward") or path.name != "manifest.json"
            or manifest.get("schema_version") != "hotspot-forward-research-v1"
            or manifest.get("namespace") != ("TEST_ONLY" if test_only else "ACTUAL")
            or manifest.get("status") != "DRAFT" or manifest.get("approved") is not False
            or manifest.get("action") != "no_order" or manifest["rule_bindings"] != _rules()
            or manifest['costs'] != _costs() or manifest['execution_policy'] != _execution_policy()
            or manifest['initial_cash_cny'] != str(DEFAULT_INITIAL_CASH_CNY)
            or manifest.get('formal_eligibility') is not False
            or manifest.get('hypothetical_fills') is not None
            or manifest.get('elapsed_real_shadow_sessions') != 0):
        raise ValueError("Frozen rules or namespace changed")
    frozen = _stamp(manifest["frozen_at"])
    from .quantitative_validation import build_economic_validation_draft
    if manifest['economic_candidate'] != build_economic_validation_draft(now=frozen):
        raise ValueError('Frozen economic candidate changed')
    if frozen > cutoff:
        raise ValueError("Freeze is in the future")
    report, symbols = _selection(root, manifest["candidate_binding"], frozen, test_only)
    if (symbols != manifest["symbols"]
            or report["source_bindings"] != manifest["candidate_source_bindings"]):
        raise ValueError("Frozen candidate sources changed")
    return manifest, path.parent


def _verified_observations(session_root, cases, symbols, started, finished, previous_observations=None,
                           test_only=False):
    if started.date() != finished.date() or finished < started:
        raise ValueError("Collection must finish in the same real session date")
    if sorted(cases) != symbols:
        raise ValueError("Complete frozen pool required; no dropped securities")
    observations = []
    for symbol in symbols:
        binding = cases[symbol]
        _reject_test_source(_read(session_root, binding), test_only)
        case = load_current_price_case(root=session_root, symbol=symbol,
            case_path=Path(binding["path"]), expected_sha256=binding["sha256"], now=finished)
        if (case["market_trade_date"] != started.date().isoformat()
                or case.get("observation_scope") == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"):
            raise ValueError("Old trade date or display-only evidence cannot count as a new session")
        quote = case["current_reference_close"]
        bundle = _read(session_root, dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"]))
        _reject_test_source(bundle, test_only)
        times = [bundle["started_at"], bundle["finished_at"],
                 *(item["fetched_at"] for item in bundle["documents"].values()),
                 *(item["fetched_at"] for item in case["source_bindings"].values())]
        if any(not started <= _stamp(value) <= finished for value in times):
            raise ValueError("Sources must be freshly collected inside this observation")
        plan = project_current_price_action_plan(case)
        baseline = make_shadow_baseline({**case, "data_available_at": plan["data_available_at"]},
                                       plan, observed_at=finished)
        previous = (previous_observations or {}).get(symbol)
        conditions = deepcopy(plan['conditional_action_rules'])
        conditions['OPEN']['rule'] = INDEPENDENT_OPEN_RULE
        observations.append(dict(symbol=symbol, case_binding=binding, baseline=baseline,
            prior_condition_comparison=compare_archived_baseline(previous['baseline'], baseline) if previous else None,
            conditions=conditions, execution_status="UNASSESSABLE",
            hypothetical_fills=None, profit=None, action="no_order"))
    return observations


def observe_forward_research(*, root: Path, manifest_binding: dict, test_only=False,
                             now=None, bundle_collector=None, case_collector=None) -> dict:
    """Collect one fresh completed date into an isolated root; never update current.

    Failed attempts retain their own UUID; only a verified receipt claims a date.
    """
    root = Path(root).resolve()
    started = _clock(test_only, now)
    if not test_only and (bundle_collector is not None or case_collector is not None):
        raise ValueError("Collector injection is TEST_ONLY")
    manifest, directory = _verify_freeze(root, manifest_binding, test_only, started)
    if started.date() <= _stamp(manifest["frozen_at"]).date():
        raise ValueError("Forward session must follow the frozen date")
    if not is_exchange_session('SSE', started.date()) or started.time() < time(15):
        raise ValueError('A completed actual exchange session is required before collection')
    day = started.date().isoformat()
    sessions = directory / "sessions"
    previous_observations, previous_binding = {}, None
    # Reverify completed prior observations; never trust their stored count/flags.
    for previous in sorted(sessions.glob("*/receipt.json")):
        prior_day = previous.parent.name
        if prior_day >= day:
            raise ValueError("Duplicate or non-increasing session")
        receipt = json.loads(previous.read_bytes())
        prior = _read(root, receipt)
        prior_root = (root / prior['session_root']).resolve()
        if (not prior_root.is_relative_to(root / 'runtime/hotspot-forward-data')
                or prior_root.name != prior['session_id']):
            raise ValueError('Prior observation data root changed')
        if (prior["manifest_binding"] != manifest_binding or prior["trade_date"] != prior_day
                or prior.get('prior_observation_binding') != previous_binding
                or _stamp(prior["started_at"]).date().isoformat() != prior_day):
            raise ValueError("Prior observation identity changed")
        rebuilt = _verified_observations(prior_root, prior["cases"], manifest["symbols"],
            _stamp(prior["started_at"]), _stamp(prior["finished_at"]), previous_observations, test_only)
        if rebuilt != prior["observations"]:
            raise ValueError("Prior observation source replay changed")
        previous_observations = {row['symbol']: row for row in rebuilt}
        previous_binding = receipt
    claimed = sessions / day
    claimed.mkdir(parents=True, exist_ok=True)
    # Keep native provider paths below Windows MAX_PATH without system changes.
    session_id = uuid4().hex[:16]
    session_root = root / 'runtime/hotspot-forward-data' / session_id
    if not session_root.resolve().is_relative_to(root / 'runtime'):
        raise ValueError('Forward data directory escapes runtime')
    (session_root / "runtime").mkdir(parents=True, exist_ok=False)
    cases, failures = {}, []
    try:
        bundle = (bundle_collector or collect_session_bundle)(manifest['symbols'])
        bundle_path = session_root / 'runtime/quotes.json'
        bundle_binding = _write(session_root, bundle_path, bundle)
        for symbol in manifest['symbols']:
            try:
                kwargs = dict(root=session_root, symbol=symbol, as_of=started.date(),
                    quote_bundle_path=bundle_path, quote_bundle_sha256=bundle_binding['sha256'])
                if test_only:
                    kwargs['now'] = started
                case = (case_collector or collect_current_price_case)(**kwargs)
                cases[symbol] = dict(path=case['case_path'], sha256=case['case_sha256'])
            except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
                failures.append(dict(symbol=symbol, reason=str(error)))
        finished = _clock(test_only, now)
        observations = _verified_observations(session_root, cases, manifest['symbols'], started, finished,
                                               previous_observations, test_only)
        _verify_freeze(root, manifest_binding, test_only, finished)
        if observations != _verified_observations(session_root, cases, manifest['symbols'], started, finished,
                                                   previous_observations, test_only):
            raise ValueError('Observation sources changed before publication')
    except Exception as error:
        _write(root, session_root / 'failure.json', dict(manifest_binding=manifest_binding,
            started_at=started.isoformat(), cases=cases, failures=failures,
            reason=str(error), elapsed_real_shadow_sessions=0, action='no_order'))
        raise
    result = dict(schema_version="hotspot-forward-observation-v1", status="DRAFT", approved=False,
        namespace=manifest["namespace"], manifest_binding=manifest_binding, session_id=session_id,
        session_root=session_root.relative_to(root).as_posix(),
        prior_observation_binding=previous_binding,
        trade_date=day, started_at=started.isoformat(), finished_at=finished.isoformat(),
        cases=cases, observations=observations, execution_status="UNASSESSABLE",
        hypothetical_fills=None, profit=None, elapsed_real_shadow_sessions=0,
        strategy_validation="NOT_PROVEN", strict_pit_admitted=False, strict_oos_admitted=False,
        formal_eligibility=False, action="no_order")
    binding = _write(root, session_root / "observation.json", result)
    _write(root, claimed / "receipt.json", binding)
    return binding

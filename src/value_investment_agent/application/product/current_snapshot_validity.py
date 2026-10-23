"""Explicit, read-only, zero-new-filing model reuse; never whole-day coverage.

No registry discovery, signing, publication or default freshness policy. The policy
authorizer is a trusted application dependency (like value_price_policy's existing
confirmation authorizer), not a callback or approval flag accepted from HTTP/JSON.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime
import json
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from ...event_scan import event_scan_from_payload
from ...model_validity import ModelValidity, model_validity_identity_blockers
from ...research_run_contract import valuation_result_sha256
from ...valuation_models.base import ValuationResult
from .common import normalize_symbol, sha256_file
from .incremental_validity import (
    BINDING_SCHEMA_V2, PARTIAL_WINDOW, POINTER_PATH, incremental_scan_start,
    load_incremental_scan_binding, read_bound_json, registered_package,
    verify_incremental_observation_sources,
)

SCOPE = 'CURRENT_AS_OF_SNAPSHOT_V1'
POLICY_SCHEMA = 'current-asof-snapshot-policy-v1'
CHINA = ZoneInfo('Asia/Shanghai')


@dataclass(frozen=True)
class ApprovedBaseline:
    """Internal native replay output, not a serialized authorization input."""
    valuation: ValuationResult
    validity: ModelValidity
    reviewed_at: datetime
    approval_id: str
    rule_version: str
    research_version: str
    approval_transport: dict
    announcements: tuple


@dataclass(frozen=True)
class CurrentSnapshotValidity:
    status: str
    symbol: str
    evaluated_at: datetime
    knowledge_as_of: datetime | None
    model_validity: ModelValidity | None
    valuation: ValuationResult | None
    bindings: dict
    blockers: tuple[str, ...]

    @property
    def usable_for_research_comparison(self) -> bool:
        return (self.status == 'VALID_AS_OF_SNAPSHOT' and not self.blockers
                and self.model_validity is not None and self.model_validity.status == 'VALID')

    def as_policy(self) -> dict:
        return dict(schema_version='current-snapshot-validity-result-v1', scope=SCOPE,
            status=self.status, symbol=self.symbol, evaluated_at=self.evaluated_at.isoformat(),
            knowledge_as_of=self.knowledge_as_of.isoformat() if self.knowledge_as_of else None,
            full_calendar_window_elapsed=False, strict_contemporaneous_pit=False,
            source_assurance='REPLAYED_OFFICIAL_QUERY_NOT_REALTIME_INDEX_COMPLETENESS',
            usable_for_research_comparison=self.usable_for_research_comparison,
            model_validity=json.loads(self.model_validity.to_json()) if self.model_validity else None,
            valuation=json.loads(self.valuation.to_json()) if self.valuation else None,
            bindings=deepcopy(self.bindings), blockers=list(self.blockers),
            formal_eligibility=False, g3_approval_granted=False,
            strategy_approval_granted=False, research_cutoff_changed=False, action='no_order')


def _stamp(value, label):
    if not isinstance(value, str):
        raise ValueError(label + ' requires an explicit timestamp')
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError(label + ' requires a timezone')
    return stamp


def _announcement_map(announcements):
    rows = {}
    for item in announcements:
        if item.announcement_id in rows:
            raise ValueError('Duplicate announcement identity')
        # Paths may differ after a legitimate re-query; original URL/bytes may not.
        refs = tuple(sorted((ref['sha256'], ref.get('source_url', item.source_url))
                            for ref in item.evidence_refs))
        if not refs:
            raise ValueError('Announcement requires bound original bytes')
        rows[item.announcement_id] = (item.title, item.published_at, item.source_url, refs)
    return rows


def _replay_approved_baseline(root, package, reviews_ref, now):
    """Reuse the existing signed G3/history verifier, never mint approval here."""
    from .source_bound_inputs import verify_package_local_sources
    from .research_reviews import attach_research_reviews, verify_human_approval_transport_provenance
    from ...m1_valuation_package_builder import build_descriptor
    from ...research_input import build_research_run_spec
    from ...research_application import ResearchApplicationService
    from ...human_research_approval import resolve_human_research_approval

    if not verify_package_local_sources(root, package):
        raise ValueError('BASELINE_BOUND_ORIGINALS_REQUIRED')
    descriptor = build_descriptor(package, root=root)
    spec = build_research_run_spec(descriptor)
    event_ref = package['model_validity_input'].get('event_scan_ref')
    path, _ = read_bound_json(root, reviews_ref, 'baseline signed reviews')
    spec = attach_research_reviews(root=root, spec=spec, descriptor=descriptor,
        path=path, expected_sha256=reviews_ref['sha256'],
        event_sha256=event_ref['sha256'] if event_ref else None, require_model_binding=True)
    approval = spec.human_research_approval
    if approval is None or not approval.authenticated_transport_binding:
        raise ValueError('BASELINE_AUTHENTICATED_G3_REQUIRED')
    approval = verify_human_approval_transport_provenance(root, approval)
    transport = approval.authenticated_transport_binding
    _, trust = read_bound_json(root, transport['trust_root_binding'], 'baseline G3 trust')
    if not _stamp(trust['valid_from'], 'trust start') <= now <= _stamp(trust['valid_until'], 'trust end'):
        raise ValueError('BASELINE_APPROVAL_AUTHORITY_EXPIRED')
    outcome = ResearchApplicationService().run_company_research(spec)
    valuation, validity = outcome.valuation, outcome.model_validity
    decision = resolve_human_research_approval(approval, valuation,
        model_id=outcome.route.selected_model,
        research_case_payload=spec.research_case_payload, facts_payload=spec.facts_payload,
        assumptions_payload=spec.assumptions_payload, require_authenticated_provenance=True)
    if (not decision.approved or not decision.price_assessment_eligible or decision.blockers
            or not outcome.gate.ready_for_price_assessment):
        raise ValueError('BASELINE_RESEARCH_NOT_APPROVED: ' + '; '.join(decision.blockers))
    if validity is None or valuation is None or valuation.blockers or valuation.status == 'not_ready':
        raise ValueError('BASELINE_MODEL_NOT_USABLE')
    if valuation.confidence == '\u4f4e':
        raise ValueError('BASELINE_LOW_CONFIDENCE')
    if not spec.rule_version or not spec.research_case.research_version:
        raise ValueError('BASELINE_RULE_OR_RESEARCH_IDENTITY_MISSING')
    announcements = ()
    if event_ref:
        _, scan = read_bound_json(root, event_ref, 'baseline event scan')
        parsed = event_scan_from_payload(scan)
        verify_incremental_observation_sources(root, {'source_bindings': list(parsed.evidence_refs)})
        announcements = parsed.announcements
    return ApprovedBaseline(valuation, validity, approval.reviewed_at, approval.approval_id,
        spec.rule_version, spec.research_case.research_version, deepcopy(transport), tuple(announcements))


def evaluate_current_snapshot_validity(*, root: Path, symbol: str,
        incremental_binding_ref: dict, baseline_reviews_binding: dict,
        policy_binding: dict | None, now: datetime,
        authorize_policy: Callable | None = None) -> CurrentSnapshotValidity:
    """Return a scoped typed input for Root's explicit quote_bridge integration.

    No legacy resolver dispatch changes. Only this result's valid envelope plus
    its unchanged valuation may be used for snapshot research comparison; the
    envelope must accompany the typed ModelValidity through all consumers.
    """
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    incremental_binding_ref = deepcopy(incremental_binding_ref)
    baseline_reviews_binding = deepcopy(baseline_reviews_binding)
    policy_binding = deepcopy(policy_binding)
    bindings = {}
    baseline = None
    knowledge = None
    try:
        if now.utcoffset() is None:
            raise ValueError('Snapshot evaluation requires an aware clock')
        pointer_hash = sha256_file(root / POINTER_PATH)
        package_ref, package = registered_package(root, symbol)
        baseline = _replay_approved_baseline(root, package, baseline_reviews_binding, now)
        bindings.update(package=deepcopy(package_ref), reviews=deepcopy(baseline_reviews_binding),
            approval_transport=deepcopy(baseline.approval_transport), approval_id=baseline.approval_id,
            rule_version=baseline.rule_version, research_version=baseline.research_version)
        if baseline.validity.status == 'STALE':
            raise ValueError('BASELINE_KNOWN_STALE')
        if policy_binding is None or authorize_policy is None:
            raise ValueError('EXPLICIT_CONFIRMED_SNAPSHOT_POLICY_REQUIRED')
        _, policy = read_bound_json(root, policy_binding, 'snapshot policy')
        _, binding = read_bound_json(root, incremental_binding_ref, 'snapshot increment')
        cutoff = now.astimezone(CHINA).date()
        if (binding.get('schema_version') != BINDING_SCHEMA_V2
                or binding.get('coverage_mode') != PARTIAL_WINDOW):
            raise ValueError('Snapshot requires explicit V2 partial acquisition')
        load_incremental_scan_binding(root=root, binding_ref=incremental_binding_ref, symbol=symbol,
            package_path=root / package_ref['path'], package_sha256=package_ref['sha256'],
            review_cutoff=cutoff, today=now)
        _, observation = read_bound_json(root, binding['observation_ref'], 'snapshot observation')
        _, scan_payload = read_bound_json(root, binding['scan_ref'], 'snapshot scan')
        scan = event_scan_from_payload(scan_payload)
        knowledge = _stamp(observation['acquired_at'], 'knowledge_as_of')
        if knowledge > now or knowledge.astimezone(CHINA).date() != cutoff:
            raise ValueError('Snapshot expired across China date or is in the future')
        bindings.update(increment=deepcopy(incremental_binding_ref), observation=deepcopy(binding['observation_ref']),
            scan=deepcopy(binding['scan_ref']), policy=deepcopy(policy_binding),
            valuation_sha256=valuation_result_sha256(baseline.valuation))
        if baseline.validity.status != 'VALID' or baseline.validity.blockers:
            raise ValueError('BASELINE_VALIDITY_NOT_ESTABLISHED')
        if baseline.valuation.confidence == '\u4f4e' or baseline.valuation.blockers:
            raise ValueError('BASELINE_LOW_OR_BLOCKED')
        if baseline.reviewed_at > knowledge:
            raise ValueError('Snapshot precedes baseline approval availability')
        expected = dict(schema_version=POLICY_SCHEMA, scope=SCOPE, action='no_order', symbol=symbol,
            rule='ZERO_NEW_OR_CHANGED_FILINGS', baseline_package=package_ref,
            baseline_reviews=baseline_reviews_binding, approval_id=baseline.approval_id,
            approval_transport=baseline.approval_transport, model_id=baseline.validity.model_id,
            model_version=baseline.valuation.model_version, rule_version=baseline.rule_version,
            research_version=baseline.research_version,
            valuation_sha256=valuation_result_sha256(baseline.valuation))
        if any(policy.get(key) != value for key, value in expected.items()):
            raise ValueError('SNAPSHOT_POLICY_IDENTITY_MISMATCH')
        age = policy.get('max_snapshot_age_seconds')
        if type(age) is not int or age <= 0:
            raise ValueError('Snapshot freshness requires an explicit positive policy duration')
        start, end = (_stamp(policy[key], key) for key in ('valid_from', 'valid_until'))
        confirmed = _stamp(policy.get('confirmed_at'), 'confirmed_at')
        if (not start <= confirmed <= knowledge <= now <= end
                or (now - knowledge).total_seconds() > age):
            raise ValueError('SNAPSHOT_POLICY_OR_FRESHNESS_EXPIRED')
        if authorize_policy(root=root, policy_binding=deepcopy(policy_binding),
                policy=deepcopy(policy), now=now) is not True:
            raise ValueError('SNAPSHOT_POLICY_NOT_AUTHORIZED')
        known = _announcement_map(baseline.announcements)
        observed = _announcement_map(scan.announcements)
        if observed != known:
            raise ValueError('NEW_CHANGED_OR_MISSING_FILINGS_REQUIRE_REVIEW')
        # No blanket blocker deletion: a successor rule only consumes this exact
        # native collector's neutral, acquisition-level pending state.
        if (scan.parser_version != 'cninfo-announcement-window-v1'
                or tuple(scan.blockers) != ('This acquired query window does not replace earlier event/model/G3 reviews.',)):
            raise ValueError('Unsupported snapshot acquisition blockers')
        validity = replace(baseline.validity, last_material_event_check=cutoff,
            evidence_refs=[*baseline.validity.evidence_refs,
                dict(id='current-asof-snapshot-' + incremental_binding_ref['sha256'], **incremental_binding_ref),
                dict(id='current-asof-policy-' + policy_binding['sha256'], **policy_binding)])
        if model_validity_identity_blockers(validity, baseline.valuation):
            raise ValueError('BASELINE_MODEL_IDENTITY_MISMATCH')
        # Replay all native originals and the live approval head after computation.
        load_incremental_scan_binding(root=root, binding_ref=incremental_binding_ref, symbol=symbol,
            package_path=root / package_ref['path'], package_sha256=package_ref['sha256'],
            review_cutoff=cutoff, today=now)
        verify_incremental_observation_sources(root, observation)
        if authorize_policy(root=root, policy_binding=deepcopy(policy_binding),
                policy=deepcopy(policy), now=now) is not True:
            raise ValueError('Snapshot policy revoked during evaluation')
        if (_replay_approved_baseline(root, package, baseline_reviews_binding, now) != baseline
                or sha256_file(root / POINTER_PATH) != pointer_hash):
            raise ValueError('Baseline approval or registration changed during snapshot evaluation')
        for ref in (package_ref, baseline_reviews_binding, policy_binding, incremental_binding_ref):
            read_bound_json(root, ref, 'snapshot final input')
        verify_incremental_observation_sources(root, observation)
        return CurrentSnapshotValidity('VALID_AS_OF_SNAPSHOT', symbol, now, knowledge, validity,
            baseline.valuation, bindings, ())
    except (ValueError, KeyError, TypeError, OSError, AttributeError, OverflowError) as error:
        stale = baseline is not None and baseline.validity.status == 'STALE'
        return CurrentSnapshotValidity('STALE' if stale else 'UNKNOWN', symbol, now, knowledge,
            baseline.validity if stale else None, baseline.valuation if baseline else None,
            bindings, (str(error),))

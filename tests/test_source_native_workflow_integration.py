"""TEST_ONLY native candidates use the real shared workflow without verifier stubs."""
from datetime import datetime, timezone
import json

import pytest

from test_source_native_candidate_v2 import synthetic_native, prepare
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.pending_research_candidate import verify_pending_research_candidate
from value_investment_agent.application.product.pending_candidate_supplement import load_current_pending_candidate_supplement
from value_investment_agent.application.product.research_reviews import prepare_pending_review_intake
from value_investment_agent.application.product.research_review_wizard import (
    preview_pending_review_response, build_external_review_handoff,
)
from value_investment_agent.application.research.value_research_analysis import load_current_value_research_analysis


def register_native(case):
    root, _, _ = case
    candidate = prepare(case)
    path = root / 'runtime/native-v2/candidate.json'
    binding = dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
    registry = root / 'config/user-research-workflow-v1.json'
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps(dict(schema_version='user-research-workflow-v1',
        action='no_order', supplemental_review_candidates={candidate['symbol']: binding})), encoding='utf-8')
    return root, candidate, path, binding


def test_native_intake_and_unsigned_preview_do_not_replace_frozen_verifier(synthetic_native):
    root, candidate, path, binding = register_native(synthetic_native)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        verify_pending_research_candidate(root=root, path=path, expected_sha256=binding['sha256'])
    intake = prepare_pending_review_intake(root=root, candidate_path=path, candidate_sha256=binding['sha256'])
    preview = preview_pending_review_response(root=root, candidate_path=path, candidate_sha256=binding['sha256'])
    assert len(intake['groups']) == len(preview['review_questions']) == 5
    assert intake['model_context'] == candidate['model_context']
    assert intake['whole_model_decision'] is None
    assert intake['research_admitted'] is False
    assert preview['status'] == 'READ_ONLY_PREVIEW_NOT_APPROVED'
    assert preview['draft']['whole_model_approval'] is None
    assert preview['draft']['reviewer_id'] is None
    assert before == path.read_bytes()


def test_native_supplement_and_public_analysis_preserve_exact_cash_materials(synthetic_native):
    root, candidate, _, binding = register_native(synthetic_native)
    supplement = load_current_pending_candidate_supplement(root=root, symbol=candidate['symbol'])
    assert supplement['candidate_binding'] == binding
    assert supplement['candidate'] == candidate
    assert supplement['registered_current_case_changed'] is False
    analysis = load_current_value_research_analysis(root=root, symbol=candidate['symbol'], now=datetime.now(timezone.utc))
    native = analysis['source_native_cash_review']
    assert native['candidate_binding'] == binding
    assert native['model_context'] == candidate['model_context']
    assert native['primary_registered'] is native['approval_changed'] is False
    assert native['valuation_timing'] is None
    assert native['valuation_timing_status'] == 'MISSING_EXPLICIT_MODEL_TIMING'
    assert analysis['joint_capital_review'] is None
    for scenario in ('bear', 'base', 'bull'):
        assert native['scenarios'][scenario]['per_share_value'] == analysis['valuation'][scenario + '_value']
        assert native['scenarios'][scenario]['cash_ledger']


def test_native_handoff_keeps_five_groups_and_unsigned_economic_materials(synthetic_native):
    root, candidate, _, binding = register_native(synthetic_native)
    handoff = build_external_review_handoff(root=root, symbol=candidate['symbol'], now=datetime.now(timezone.utc))
    assert handoff['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    assert handoff['candidate_binding'] == binding
    assert len(handoff['review_questions']) == 5
    assert handoff['unsigned_response']['whole_model_approval'] is None
    assert handoff['verification']['approval_changed'] is False
    materials = handoff['economic_review_materials']
    assert materials['source_native_cash_review']['candidate_binding'] == binding
    assert materials['primary_valuation_usable'] is False
    assert handoff['materiality_handoff']['g3_approval_granted'] is False

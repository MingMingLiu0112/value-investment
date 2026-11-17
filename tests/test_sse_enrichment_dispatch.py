"""TEST_ONLY dispatch; uses legacy mechanism fixtures, not market evidence."""
from copy import deepcopy
import pytest
from test_value_enrichment_batch import flow,run
from value_investment_agent.application.research import sse_research_priority_v1 as priority
from value_investment_agent.application.research.value_research_queue import _canonical_hash


def convert(flow,monkeypatch,selected=True):
    args,q,calls=flow;q=deepcopy(q);q['schema_version']=priority.SCHEMA_VERSION
    q['inputs']['sse_manifest']={'path':'runtime/TEST_ONLY_manifest.json','sha256':'a'*64}
    for row in q['evidence_enrichment_work_queue']:row['tracking_selected']=selected
    q.pop('content_sha256');q['content_sha256']=_canonical_hash(q)
    monkeypatch.setattr(priority,'build_sse_research_priority',lambda **kwargs:deepcopy(q))
    return args,q,calls


def test_sse_queue_reuses_actual_enrichment_checkpointing(flow,monkeypatch):
    converted=convert(flow,monkeypatch)
    result=run(converted,'sse-test-only',allow_network=True)
    assert result['attempted_count']==1 and result['queue_content_sha256']==converted[1]['content_sha256']
    assert result['formal_eligibility'] is False and result['action']=='no_order'


def test_budget_deferred_untracked_names_not_executed(flow,monkeypatch):
    converted=convert(flow,monkeypatch,selected=False)
    result=run(converted,'sse-untracked',allow_network=True)
    assert result['attempted_count']==0 and converted[2]==[]


def test_sse_rebuild_mismatch_stops_before_acquisition(flow,monkeypatch):
    converted=convert(flow,monkeypatch)
    monkeypatch.setattr(priority,'build_sse_research_priority',lambda **kwargs:{'TEST_ONLY':'changed'})
    with pytest.raises(ValueError,match='replayed bound inputs'):run(converted,'sse-bad',allow_network=True)
    assert converted[2]==[]

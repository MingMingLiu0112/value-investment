"""TEST_ONLY pipeline contracts; mock acquisition is not real-company acceptance."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json
import pytest
from value_investment_agent.application.research import sse_research_pipeline_v1 as app
from value_investment_agent.application.research import sse_research_priority_v1 as priority
from value_investment_agent.application.discovery import sse_main_screening as screen
from value_investment_agent.infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress
from value_investment_agent.application.research.value_research_queue import _canonical_hash

NOW=datetime(2026,11,2,tzinfo=timezone.utc)

@pytest.fixture
def setup(tmp_path,monkeypatch):
    root=tmp_path;source=root/'runtime/source.json';source.parent.mkdir();source.write_text('{"TEST_ONLY":true}')
    ref=app._binding(root,source);(root/'.tmp').mkdir();(root/screen.POINTER).write_text(json.dumps(dict(manifest=ref)))
    monkeypatch.setattr(screen,'replay_research_inputs',lambda **kw:dict(financial_payload=dict(points=[]),points=[]))
    monkeypatch.setattr(ValueEnrichmentProgress,'completed_sources',lambda self,**kw:[])
    def build(**kw):
        previous=app._bound(root,dict(path=kw['previous_path'].relative_to(root).as_posix(),sha256=kw['previous_sha256'])) if kw['previous_path'] else None
        row=dict(symbol='600001',company_name='TEST_ONLY',industry='TEST_ONLY',channels=['value'],screening_reasons=['TEST_ONLY observed lead'],first_seen_at=previous['deep_research_priority'][0]['first_seen_at'] if previous else kw['now'].isoformat(),tracking_status='RESEARCH_PENDING',tracking_selected=True,timing=dict(financial_period='2025-12-31'),evidence_completeness=dict(accepted_fields=['roe'],required_fields=['roe']),gaps=['BUSINESS_UNKNOWN'])
        q=dict(schema_version=priority.SCHEMA_VERSION,action='no_order',admission='RESEARCH_QUEUE_ONLY',evaluation_at=kw['now'].isoformat(),source_available_at=NOW.isoformat(),budget=kw['budget'],enrichment_budget=kw['budget'],tracking_count=1,candidate_count=1,deep_research_priority=[row],evidence_enrichment_work_queue=[],inputs=dict(sse_manifest=kw['manifest_binding'],financial_export_path=kw['financial_export_path'].relative_to(root).as_posix(),financial_export_sha256=kw['financial_export_sha256'],previous_queue_path=kw['previous_path'].relative_to(root).as_posix() if kw['previous_path'] else None,previous_queue_sha256=kw['previous_sha256']))
        q['content_sha256']=_canonical_hash(q);return q
    monkeypatch.setattr(priority,'build_sse_research_priority',build)
    monkeypatch.setattr(screen,'read_screen',lambda **kw:dict(status='PARTIAL',source_refs=[ref],source_status='RETAINED_DATED_RESEARCH'))
    app._CACHE._entry=None
    return root,ref


def prepare(setup,name='queue'):
    root,ref=setup
    return app.prepare_sse_research_run(root=root,manifest_binding=ref,output_path=root/'runtime'/name/'queue.json',budget=30)


def test_current_public_read_is_readonly_and_tracks_real_output_shape(setup):
    root,ref=setup;result=prepare(setup)
    before={p.relative_to(root):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    view=app.read_sse_research_pool(root=root,now=datetime.now(timezone.utc))
    assert view['status']=='AVAILABLE' and view['tracking_count']==1
    assert view['items'][0]['next_action']=='进入经营与反证研究'
    assert view['action']=='no_order' and view['queue_binding']==result['queue']
    assert before=={p.relative_to(root):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


def test_same_day_followup_keeps_prior_queue_and_first_seen(setup):
    root,_=setup;first=prepare(setup,'one');old=(root/first['queue']['path']).read_bytes()
    second=prepare(setup,'two');q=app._bound(root,second['queue']);prior=json.loads(old)
    assert q['deep_research_priority'][0]['first_seen_at']==prior['deep_research_priority'][0]['first_seen_at']
    assert (root/first['queue']['path']).read_bytes()==old
    assert app.read_sse_research_pool(root=root,now=datetime.now(timezone.utc))['history_available']


def test_broken_source_keeps_pointer_and_history_not_false_zero(setup):
    root,_=setup;prepare(setup);before=(root/app.POINTER).read_bytes()
    (root/'runtime/source.json').write_text('{"TEST_ONLY":"changed"}')
    view=app.read_sse_research_pool(root=root,now=datetime.now(timezone.utc))
    assert view['status']=='UNAVAILABLE' and view['tracking_count'] is None and view['history_available']
    assert (root/app.POINTER).read_bytes()==before


def test_queue_tamper_rejected_even_if_manifest_rehashed(setup):
    root,_=setup;result=prepare(setup);p=root/result['queue']['path'];q=json.loads(p.read_bytes());q['deep_research_priority'][0]['company_name']='FAKE';p.write_text(json.dumps(q))
    pointer=json.loads((root/app.POINTER).read_bytes());mp=root/pointer['manifest']['path'];m=json.loads(mp.read_bytes());m['queue']=app._binding(root,p);mp.write_text(json.dumps(m));pointer['manifest']=app._binding(root,mp);(root/app.POINTER).write_text(json.dumps(pointer))
    assert app.read_sse_research_pool(root=root,now=datetime.now(timezone.utc))['status']=='UNAVAILABLE'


def test_prepare_failure_does_not_replace_prior_pointer(setup,monkeypatch):
    root,_=setup;prepare(setup,'one');old=(root/app.POINTER).read_bytes()
    def reject(**kw):raise ValueError('TEST_ONLY_SOURCE_UNAVAILABLE')
    monkeypatch.setattr(screen,'replay_research_inputs',reject)
    with pytest.raises(ValueError,match='SOURCE_UNAVAILABLE'):prepare(setup,'two')
    assert (root/app.POINTER).read_bytes()==old


def test_unknown_source_is_not_zero(tmp_path):
    view=app.read_sse_research_pool(root=tmp_path,now=NOW)
    assert view['status']=='UNAVAILABLE' and view['total_candidates'] is None and view['tracking_count'] is None


@pytest.mark.parametrize("has_previous", [False, True])
def test_concurrent_publish_rechecks_pointer_under_real_lock_and_preserves_parent(setup, monkeypatch, has_previous):
    """TEST_ONLY: collide before publication; real OS lock and replace must serialize."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    root, _ = setup
    seed = prepare(setup, "seed") if has_previous else None
    pointer_path = root / app.POINTER
    previous_raw = pointer_path.read_bytes() if has_previous else None
    preserved = {p: p.read_bytes() for p in root.rglob("*")
                 if p.is_file() and p != pointer_path
                 and p.name != "sse-research-publication.lock"}
    original_build = priority.build_sse_research_priority
    barrier = Barrier(2)
    previous_hashes = []

    def collide(**kwargs):
        result = original_build(**kwargs)
        previous_hashes.append(kwargs["previous_sha256"])
        # Both preparations have captured exactly the same predecessor before either commits.
        barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(priority, "build_sse_research_priority", collide)
    successes, rejections = [], []
    with ThreadPoolExecutor(max_workers=2) as workers:
        pending = [workers.submit(prepare, setup, name) for name in ("racer-a", "racer-b")]
        for future in pending:
            try:
                successes.append(future.result(timeout=15))
            except ValueError as error:
                rejections.append(str(error))

    assert previous_hashes == [seed["queue"]["sha256"] if seed else None] * 2
    assert len(successes) == 1
    assert rejections == ["RESEARCH_POINTER_CHANGED_DURING_PREPARATION"]
    current_pointer = json.loads(pointer_path.read_bytes())
    assert current_pointer["manifest"] == successes[0]["manifest"]
    current = app._bound(root, current_pointer["manifest"])
    assert current["queue"] == successes[0]["queue"]
    assert current["parent_manifest"] == (seed["manifest"] if seed else None)
    queue = app._bound(root, current["queue"])
    if seed:
        parent = app._bound(root, current["parent_manifest"])
        assert parent["queue"] == seed["queue"]
        assert queue["inputs"]["previous_queue_sha256"] == seed["queue"]["sha256"]
        history_pointer = root / current_pointer["manifest"]["path"]
        assert (history_pointer.parent / "previous-pointer.json").read_bytes() == previous_raw
        assert queue["deep_research_priority"][0]["first_seen_at"] == app._bound(
            root, seed["queue"])["deep_research_priority"][0]["first_seen_at"]
    else:
        assert queue["inputs"]["previous_queue_sha256"] is None
    assert all(path.read_bytes() == raw for path, raw in preserved.items())

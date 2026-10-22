"""Real Windows CLI acceptance in an isolated project with retained public bytes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = Path('C:/Users/we/AppData/Local/Programs/PowerShell/7/pwsh.exe')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_daily_entry_busy_preserves_active_receipt(tmp_path):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    project = tmp_path / 'busy-project'
    current = project / 'scripts/current'
    current.mkdir(parents=True)
    scratch = project / '.tmp'
    scratch.mkdir()
    shutil.copy2(ROOT / 'scripts/current/run_daily_workbench.ps1', current)
    receipt = scratch / 'daily-workbench-latest-run.json'
    receipt.write_bytes(b'{"status":"ACTIVE_SENTINEL"}')
    lock = (scratch / 'daily-workbench.lock').as_posix().replace("'", "''")
    holder = subprocess.Popen([str(PWSH), '-NoProfile', '-Command',
        f"$h=[IO.File]::Open('{lock}',[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);"
        "[Console]::WriteLine('LOCKED');[Console]::ReadLine()|Out-Null;$h.Dispose()"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding='utf-8')
    try:
        assert holder.stdout.readline().strip() == 'LOCKED'
        completed = subprocess.run([str(PWSH), '-NoProfile', '-File',
            str(current / 'run_daily_workbench.ps1'), '-NoServer'], cwd=project,
            capture_output=True, text=True, encoding='utf-8', timeout=20)
        assert completed.returncode == 2
        assert 'BUSY' in completed.stdout
        assert receipt.read_bytes() == b'{"status":"ACTIVE_SENTINEL"}'
    finally:
        holder.communicate('\n', timeout=10)


def test_read_only_cannot_start_value_priority_work(tmp_path):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    current = tmp_path / 'scripts/current'
    current.mkdir(parents=True)
    shutil.copy2(ROOT / 'scripts/current/run_daily_workbench.ps1', current)
    completed = subprocess.run([str(PWSH), '-NoProfile', '-File',
        str(current / 'run_daily_workbench.ps1'), '-Mode', 'READ_ONLY',
        '-BuildValueResearchPriority', '-NoServer'], cwd=tmp_path,
        capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert completed.returncode != 0
    assert 'requires explicit SAFE_REFRESH' in completed.stderr
    assert not (tmp_path / '.tmp/daily-workbench-latest-run.json').exists()


def test_safe_refresh_failure_keeps_previous_snapshot_bytes(tmp_path):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    project = tmp_path / 'isolated-project'
    project.mkdir()
    for directory in ('src', 'scripts'):
        shutil.copytree(ROOT / directory, project / directory,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'node_modules'))
    (project / 'config').mkdir()
    # No workbook/private data is copied or consulted. Missing active inputs
    # and the unavailable network must never republish the retained snapshot.
    for name in ('current-daily-public-snapshot.json', 'current-quote-bridge.json'):
        shutil.copy2(ROOT / 'config' / name, project / 'config' / name)
    pointer = project / 'config/current-daily-public-snapshot.json'
    old = json.loads(pointer.read_bytes())
    if not (ROOT / old['packet_path']).is_file():
        pytest.skip('Retained public snapshot original is absent from this source-only checkout')
    artifact = project / old['packet_path']
    artifact.parent.mkdir(parents=True)
    shutil.copy2(ROOT / old['packet_path'], artifact)
    shutil.copy2(ROOT / 'tests/fixtures/p6_network_unavailable/sitecustomize.py',
                 project / 'src/sitecustomize.py')
    original_pointer_sha = digest(ROOT / 'config/current-daily-public-snapshot.json')
    before, artifact_before = digest(pointer), digest(artifact)
    command = [str(PWSH), '-NoProfile', '-File',
               str(project / 'scripts/current/run_daily_workbench.ps1'),
               '-Mode', 'SAFE_REFRESH', '-NoServer']
    completed = subprocess.run(command, cwd=project, capture_output=True, text=True,
                               encoding='utf-8', timeout=180)
    receipt = json.loads((project / '.tmp/daily-workbench-latest-run.json').read_text(encoding='utf-8-sig'))
    output = completed.stdout + completed.stderr
    failures = [failure for path in (project / 'runtime/quote-sessions').glob('*/bundle.json')
                for failure in json.loads(path.read_bytes()).get('request_failures', [])]
    result = dict(schema_version='p6-refresh-failure-e2e-v1', action='no_order',
        execution='ACTUAL_WINDOWS_PWSH_SAME_SAFE_REFRESH_NOSERVER',
        injection=['missing_public_input_registry', 'network_connect_denied_in_isolated_python'],
        exit_code=completed.returncode, status=receipt['status'], published=receipt['published'],
        retained_publication_id=receipt['retained_publication_id'],
        finished_at=receipt['finished_at'], pointer_sha_before=before, pointer_sha_after=digest(pointer),
        packet_sha_before=artifact_before, packet_sha_after=digest(artifact),
        original_pointer_unchanged=digest(ROOT / 'config/current-daily-public-snapshot.json') == original_pointer_sha,
        network_failure_observed=bool(failures) and all(
            'P6_ISOLATED_NETWORK_UNAVAILABLE' in failure.get('error', '') for failure in failures),
        network_failed_request_count=len(failures),
        no_server_observed='-NoServer' in output,
        excel_or_private_copied=False,
        script_sha256=digest(project / 'scripts/current/run_daily_workbench.ps1'))
    destination = os.environ.get('P6_FAILURE_RECEIPT')
    if destination:
        target = Path(destination).resolve()
        assert target.is_relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert completed.returncode != 0, output
    assert receipt['status'] != 'SUCCESS' and receipt['published'] is False
    assert result['pointer_sha_before'] == result['pointer_sha_after']
    assert result['packet_sha_before'] == result['packet_sha_after']
    assert result['original_pointer_unchanged']
    assert result['network_failure_observed'] and result['no_server_observed'], output


@pytest.mark.parametrize('scenario,expected_exit,expected_status,published', [
    ('complete', 0, 'SUCCESS', True),
    ('partial', 3, 'PARTIAL', True),
    ('incremental_unavailable', 3, 'PARTIAL', True),
    ('m2_unavailable', 3, 'PARTIAL', True),
    ('m2_historical', 3, 'PARTIAL', True),
    ('m2_manifest_missing', 3, 'PARTIAL', True),
    ('m2_crash', 3, 'PARTIAL', True),
    ('quote_malformed', 3, 'PARTIAL', True),
    ('pre_unreadable', 3, 'PARTIAL', True),
    ('pre_and_post_unreadable', 2, 'BLOCKED', False),
    ('research_unavailable', 3, 'PARTIAL', True),
    ('unavailable', 2, 'BLOCKED', False),
    ('core_conflict', 2, 'BLOCKED', False),
    ('core_unavailable', 2, 'BLOCKED', False),
    ('core_recovered', 0, 'SUCCESS', True),
    ('post_integrity_loss', 2, 'BLOCKED', False),
    ('post_unreadable', 2, 'BLOCKED', False),
])
def test_windows_entry_distinguishes_partial_from_core_failure(tmp_path, scenario,
                                                             expected_exit, expected_status, published):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    project = tmp_path / scenario
    current = project / 'scripts/current'
    current.mkdir(parents=True)
    (project / 'src/value_investment_agent').mkdir(parents=True)
    (project / 'src/value_investment_agent/__init__.py').write_text('', encoding='utf-8')
    (project / 'config').mkdir()
    pointer = project / 'config/current-daily-public-snapshot.json'
    pointer.write_text(json.dumps({'publication_id': 'retained'}), encoding='utf-8')
    (project / 'config/current-quote-bridge.json').write_text(
        json.dumps({'quotes': {'600887': {}}}), encoding='utf-8')
    shutil.copy2(ROOT / 'scripts/current/run_daily_workbench.ps1', current)
    packet = dict(action='no_order', publication_id='verified', source_bindings_verified=True)
    (project / 'scripts/run_m2_opportunity_discovery.py').write_text(
        'import json,sys\nfrom pathlib import Path\n'
        f'scenario={scenario!r}\n'
        'if scenario == "m2_crash":\n'
        '    raise RuntimeError("TEST_ONLY private diagnostic not for public receipt")\n'
        'out=Path(sys.argv[sys.argv.index("--output-dir")+1])\n'
        'if scenario != "m2_manifest_missing":\n'
        '    out.mkdir(parents=True)\n'
        '    (out/"manifest.json").write_text(json.dumps({"action":"no_order","test_only":True}))\n'
        'print(json.dumps({"action":"no_order", "rule_version":"m2-evidence-screen-v3",'
        '"input_mode":"HISTORICAL_REPLAY" if scenario == "m2_historical" else "LIVE_COLLECTION",'
        '"current_publication_eligible":False,"financial_input":{"input_adapter_version":"financial-export-v2"}}))\n'
        'raise SystemExit(2 if scenario == "m2_unavailable" else 0)\n', encoding='utf-8')
    # Stub only child adapters in the isolated project; execute the real PS entry.
    build_exit = 4 if scenario == 'core_conflict' else 2 if scenario == 'core_unavailable' else 0
    (current / 'build_daily_public_packet.py').write_text(
        'import json,sys\nfrom pathlib import Path\n'
        f'packet=json.loads({json.dumps(packet)!r})\n'
        'counter=Path(".tmp/build-calls")\n'
        'count=int(counter.read_text())+1 if counter.exists() else 1\n'
        'counter.write_text(str(count))\n'
        f'scenario={scenario!r}\n'
        'if (scenario == "pre_unreadable" and count == 1) or scenario == "pre_and_post_unreadable":\n'
        '    print("TEST_ONLY invalid initial packet output")\n'
        '    raise SystemExit(0)\n'
        'if scenario == "post_integrity_loss" and count > 1:\n'
        '    packet["source_bindings_verified"]=False\n'
        'if scenario == "post_unreadable" and count > 1:\n'
        '    print("invalid packet output")\n'
        '    raise SystemExit(0)\n'
        'if "--no-publish" not in sys.argv:\n'
        '    packet["snapshot"]={"publication_id":"verified","status":"VERIFIED"}\n'
        '    Path("config/current-daily-public-snapshot.json").write_text(json.dumps(packet))\n'
        f'print(json.dumps(packet))\nraise SystemExit(2 if scenario == "core_recovered" and count == 1 else {build_exit})\n', encoding='utf-8')
    readiness = dict(prices_ready=scenario in {'complete', 'core_recovered', 'incremental_unavailable', 'm2_unavailable', 'm2_historical', 'm2_manifest_missing', 'pre_unreadable', 'pre_and_post_unreadable', 'quote_malformed'}, quotes_ready=scenario not in {'m2_crash', 'quote_malformed'},
        continuity_ready=True,
        publication_ready=scenario != 'unavailable', core_integrity_ok=True,
        market_trade_dates=['2026-10-14'], price_securities=[], quote_securities=[])
    refresh = dict(status='WRITTEN', items=[], failures=[] if scenario in {'complete', 'incremental_unavailable', 'm2_unavailable', 'm2_historical', 'm2_manifest_missing', 'pre_unreadable', 'pre_and_post_unreadable', 'm2_crash'} else [
        dict(symbol='300001', reason='missing 15m')])
    (current / 'refresh_current_price_conditions.py').write_text(
        'import json,sys\n'
        f'value=json.loads({json.dumps(readiness)!r}) if "--check-reuse" in sys.argv else json.loads({json.dumps(refresh)!r})\n'
        'print(json.dumps(value))\n', encoding='utf-8')
    (project / 'scripts/collect_quote_sessions.py').write_text(
        'import json,sys\n'
        f'if {scenario == "quote_malformed"!r}:\n'
        '    print(json.dumps({"status":"COLLECTED"}))\n'
        '    raise SystemExit(0)\n'
        'print(json.dumps({"path":"runtime/TEST_ONLY-quotes","bundle_sha256":"a"*64,'
        '"status":"COLLECTED","observations":[{"symbol":"600887",'
        '"result":{"status":"matched_close","passed":True,"expected_session":"2026-10-14"},'
        '"b1_acquisition":{"eligible":True}}]}))\n', encoding='utf-8')
    (current / 'pin_current_quote_bridge.py').write_text(
        'import json\nprint(json.dumps({"status":"PINNED","action":"no_order"}))\n',
        encoding='utf-8')
    (current / 'collect_registered_validity_scan.py').write_text(
        'import json,sys\n'
        f'failed={scenario == "incremental_unavailable"!r}\n'
        'print(json.dumps({"binding_ref":{"path":"runtime/TEST_ONLY-scan.json","sha256":"a"*64}}))\n'
        'raise SystemExit(2 if failed else 0)\n', encoding='utf-8')
    (current / 'review_registered_research_validity.py').write_text(
        'import json\nprint(json.dumps({"reviews":[{"symbol":"600887",'
        '"model_validity_status":"UNKNOWN","status":"REQUIRES_MATERIALITY_REVIEW"}]}))\n',
        encoding='utf-8')
    before = pointer.read_bytes()
    research_args = []
    if scenario == 'research_unavailable':
        (current / 'run_agent_research_pilot.py').write_text(
            'raise RuntimeError("TEST_ONLY unavailable research")\n', encoding='utf-8')
        research_args = ['-ResearchMockPlan', 'runtime/TEST_ONLY-plan.json',
                         '-ResearchMockPlanSha256', 'a' * 64]
    completed = subprocess.run([str(PWSH), '-NoProfile', '-File',
        str(current / 'run_daily_workbench.ps1'), '-Mode', 'SAFE_REFRESH', '-NoServer', *research_args],
        cwd=project, capture_output=True, text=True, encoding='utf-8', timeout=60)
    receipt = json.loads((project / '.tmp/daily-workbench-latest-run.json').read_text(encoding='utf-8-sig'))
    assert completed.returncode == expected_exit, completed.stdout + completed.stderr
    assert receipt['status'] == expected_status and receipt['published'] is published
    assert receipt['finished_at']
    assert receipt['marketwide_screen']['current_publication_eligible'] is False
    assert receipt['marketwide_screen']['status'] == (
        'BLOCKED' if scenario in {'m2_unavailable', 'm2_historical', 'm2_manifest_missing', 'm2_crash'} else 'RESEARCH_ONLY')
    if receipt['marketwide_screen']['status'] == 'RESEARCH_ONLY':
        assert receipt['marketwide_screen']['manifest_sha256'] == digest(
            project / receipt['marketwide_screen']['manifest_path'])
    elif scenario == 'm2_manifest_missing':
        assert 'manifest_sha256' not in receipt['marketwide_screen']
    assert int((project / '.tmp/build-calls').read_text()) == (3 if published else 2)
    assert receipt['node_receipt_scope'] == 'COMMAND_EXECUTION_ONLY_NOT_DATA_ADMISSION'
    nodes = receipt['nodes']
    assert [row['sequence'] for row in nodes] == list(range(1, len(nodes) + 1))
    assert all(row['started_at'] <= row['finished_at'] for row in nodes)
    assert all(row['execution_status'] != 'RUNNING' for row in nodes)
    if scenario.startswith('pre_'):
        assert nodes[0]['execution_status'] == 'FAILED'
        assert nodes[0]['output_status'] == 'INVALID_JSON'
        assert any(row['command'] == 'scripts/run_m2_opportunity_discovery.py' for row in nodes)
    if scenario == 'm2_crash':
        failed = next(row for row in nodes if row['command'] == 'scripts/run_m2_opportunity_discovery.py')
        assert failed['exit_code'] != 0 and failed['execution_status'] == 'FAILED'
        for command in ('scripts/collect_quote_sessions.py', 'scripts/current/pin_current_quote_bridge.py'):
            assert any(row['command'] == command and row['execution_status'] == 'SUCCEEDED' for row in nodes)
        assert 'private diagnostic' not in json.dumps(receipt)
        diagnostic = receipt['marketwide_screen']['diagnostic']
        log = project / diagnostic['path']
        assert log.is_relative_to(project / 'runtime/daily-marketwide')
        assert digest(log) == diagnostic['sha256']
        assert diagnostic['scope'] == 'LOCAL_DIAGNOSTIC_ONLY_NOT_DATA_EVIDENCE'
        assert 'Traceback' in log.read_text(encoding='utf-8-sig')
        assert 'TEST_ONLY private diagnostic not for public receipt' in log.read_text(encoding='utf-8-sig')
    if scenario == 'quote_malformed':
        assert not any(row['command'] == 'scripts/current/pin_current_quote_bridge.py' for row in nodes)
        assert any(row['command'] == 'scripts/current/review_registered_research_validity.py' for row in nodes)
    if not published:
        assert pointer.read_bytes() == before
        assert receipt['retained_publication_id'] == 'retained'
    else:
        assert json.loads(pointer.read_bytes())['publication_id'] == 'verified'


def _research_discovery_project(tmp_path, *, discovery_status='READY'):
    project = tmp_path / ('research-discovery-' + discovery_status.lower())
    current = project / 'scripts/current'
    current.mkdir(parents=True)
    (project / 'src/value_investment_agent').mkdir(parents=True)
    (project / 'src/value_investment_agent/__init__.py').write_text('', encoding='utf-8')
    (project / 'config').mkdir()
    (project / 'config/current-quote-bridge.json').write_text(
        json.dumps({'quotes': {}}), encoding='utf-8')
    (project / '.tmp').mkdir()
    shutil.copy2(ROOT / 'scripts/current/run_daily_workbench.ps1', current)

    discovery = {
        'schema_version': 'agent-daily-discovery-v1', 'action': 'no_order', 'mode': 'MOCK',
        'status': discovery_status, 'approval_count': 0, 'registered_or_published': False,
        'batch_plan': ({'path': 'runtime/agent-research-discovery/batch.json',
                        'sha256': 'b' * 64} if discovery_status == 'READY' else None),
        'items': ([{'symbol': '600519', 'workflow': 'event', 'status': 'EXPORTED'}]
                  if discovery_status == 'READY' else
                  [{'workflow': 'retrospective', 'status': 'WAITING_CONFIRMED_TEST_ONLY_INPUT'}]),
    }
    (current / 'run_agent_research_pilot.py').write_text(
        'import json,sys\n'
        'from pathlib import Path\n'
        'args=sys.argv[1:]\n'
        "with Path('.tmp/research-calls.jsonl').open('a',encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(args)+'\\n')\n"
        "if '--discover-contexts' in args:\n"
        f"    result={discovery!r}\n"
        '    print(json.dumps(result))\n'
        f"    raise SystemExit({2 if discovery_status == 'BLOCKED' else 0})\n"
        "if '--batch-plan' in args:\n"
        "    result={'schema_version':'daily-agent-mock-batch-result-v1','action':'no_order',"
        "'mode':'MOCK','status':'SUCCESS','items':[],'approval_count':0,"
        "'registered_or_published':False,'decision_changed':False}\n"
        '    print(json.dumps(result))\n'
        '    raise SystemExit(0)\n'
        'raise SystemExit(9)\n', encoding='utf-8')
    (current / 'build_daily_public_packet.py').write_text(
        'import json\n'
        "print(json.dumps({'publication_id':'none','source_bindings_verified':False}))\n"
        'raise SystemExit(2)\n', encoding='utf-8')
    return project


def test_read_only_records_failed_prebuild_without_reaching_collectors(tmp_path):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    project = _research_discovery_project(tmp_path)
    pointer = project / 'config/current-daily-public-snapshot.json'
    pointer.write_bytes(b'{"publication_id":"retained"}')
    (project / 'config/current-quote-bridge.json').write_bytes(b'broken quote registry')
    (project / 'scripts/current/build_daily_public_packet.py').write_text(
        'import json\nfrom pathlib import Path\n'
        'receipt=json.loads(Path(".tmp/daily-workbench-latest-run.json").read_text(encoding="utf-8-sig"))\n'
        'assert receipt["nodes"][-1]["execution_status"] == "RUNNING"\n'
        'assert receipt["nodes"][-1]["finished_at"] is None\n'
        'assert receipt["published"] is False\n'
        'Path(".tmp/progress-observed").write_text("RUNNING")\n'
        'print("TEST_ONLY malformed build result")\n', encoding='utf-8')
    completed = subprocess.run([str(PWSH), '-NoProfile', '-File',
        str(project / 'scripts/current/run_daily_workbench.ps1'),
        '-Mode', 'READ_ONLY', '-NoServer'], cwd=project,
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    receipt = json.loads((project / '.tmp/daily-workbench-latest-run.json')
                        .read_text(encoding='utf-8-sig'))
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert receipt['status'] == 'BLOCKED' and receipt['published'] is False
    assert pointer.read_bytes() == b'{"publication_id":"retained"}'
    assert (project / '.tmp/progress-observed').read_text() == 'RUNNING'
    assert len(receipt['nodes']) == 1
    assert receipt['nodes'][0]['command'] == 'scripts/current/build_daily_public_packet.py'
    assert receipt['nodes'][0]['output_status'] == 'INVALID_JSON'
    assert not (project / 'runtime').exists()


def _research_calls(project):
    return [json.loads(line) for line in
            (project / '.tmp/research-calls.jsonl').read_text(encoding='utf-8').splitlines()]


def _research_receipt(project):
    return json.loads((project / '.tmp/daily-workbench-research-latest.json')
                      .read_text(encoding='utf-8-sig'))


def test_daily_entry_auto_discovers_mock_plan_and_registers_only_discovered_batch(tmp_path):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    project = _research_discovery_project(tmp_path)
    completed = subprocess.run([
        str(PWSH), '-NoProfile', '-File', str(project / 'scripts/current/run_daily_workbench.ps1'),
        '-Mode', 'READ_ONLY', '-NoServer', '-AutoDiscoverResearchContexts', '-RegisterResearchDrafts'],
        cwd=project, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert completed.returncode == 2, completed.stdout + completed.stderr
    calls = _research_calls(project)
    assert len(calls) == 2
    assert '--discover-contexts' in calls[0] and '--mode' in calls[0]
    assert calls[0][calls[0].index('--mode') + 1] == 'mock'
    assert '--authorize-paid-api' not in calls[0] + calls[1]
    assert calls[1][calls[1].index('--batch-plan') + 1] == \
        'runtime/agent-research-discovery/batch.json'
    assert calls[1][calls[1].index('--batch-plan-sha256') + 1] == 'b' * 64
    assert '--register-drafts' in calls[1]
    receipt = _research_receipt(project)
    assert receipt['status'] == 'SUCCESS'
    assert receipt['source'] == 'AUTO_DISCOVERY'
    assert receipt['discovery']['status'] == 'READY'
    assert receipt['action'] == 'no_order'


def test_daily_entry_discovery_without_contexts_fails_closed_before_registration(tmp_path):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    project = _research_discovery_project(tmp_path, discovery_status='BLOCKED')
    completed = subprocess.run([
        str(PWSH), '-NoProfile', '-File', str(project / 'scripts/current/run_daily_workbench.ps1'),
        '-Mode', 'READ_ONLY', '-NoServer', '-AutoDiscoverResearchContexts', '-RegisterResearchDrafts'],
        cwd=project, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert completed.returncode == 2, completed.stdout + completed.stderr
    calls = _research_calls(project)
    assert len(calls) == 1 and '--discover-contexts' in calls[0]
    assert all('--register-drafts' not in call for call in calls)
    receipt = _research_receipt(project)
    assert receipt['status'] == 'BLOCKED'
    assert receipt['source'] == 'AUTO_DISCOVERY'
    assert receipt['discovery']['batch_plan'] is None
    assert receipt['result'] is None
    assert '未发现可用上下文' in completed.stdout


def test_daily_entry_pinned_mock_plan_overrides_auto_discovery(tmp_path):
    if not PWSH.is_file():
        pytest.skip('Windows PowerShell 7 required')
    project = _research_discovery_project(tmp_path)
    completed = subprocess.run([
        str(PWSH), '-NoProfile', '-File', str(project / 'scripts/current/run_daily_workbench.ps1'),
        '-Mode', 'READ_ONLY', '-NoServer', '-AutoDiscoverResearchContexts',
        '-ResearchMockPlan', 'runtime/pinned.json',
        '-ResearchMockPlanSha256', 'c' * 64, '-RegisterResearchDrafts'],
        cwd=project, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert completed.returncode == 2, completed.stdout + completed.stderr
    calls = _research_calls(project)
    assert len(calls) == 1 and '--discover-contexts' not in calls[0]
    assert calls[0][calls[0].index('--batch-plan') + 1] == 'runtime/pinned.json'
    assert calls[0][calls[0].index('--batch-plan-sha256') + 1] == 'c' * 64
    receipt = _research_receipt(project)
    assert receipt['source'] == 'PINNED_MOCK_PLAN'

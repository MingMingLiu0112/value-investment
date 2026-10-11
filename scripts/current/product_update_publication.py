"""Adapt the existing protected publisher and native verifiers to manual updates."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

from value_investment_agent.application.product.common import load_json_object, sha256_file, write_new_json, require_inside
from value_investment_agent.infrastructure.evidence.workbook_publication import verify_workbook_publication, verify_native_workbook_receipt


PWSH = Path('C:/Users/we/AppData/Local/Programs/PowerShell/7/pwsh.exe')
NODE = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'


class ProductPublicationError(ValueError):
    def __init__(self, message, *, canonical_written):
        super().__init__(message)
        self.canonical_written = canonical_written


def _command(root, folder, name, args, timeout=300):
    env = dict(os.environ, PYTHONPATH=str(root/'src'), TEMP=str(root/'.tmp'),
               TMP=str(root/'.tmp'), PYTHONIOENCODING='utf-8')
    result = subprocess.run([str(a) for a in args], cwd=root, env=env,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    write_new_json(folder/(name+'-command.json'), dict(action='no_order', exit_code=result.returncode,
                    stdout=result.stdout, stderr=result.stderr, arguments=[str(a) for a in args]))
    if result.returncode:
        raise ValueError(name+'未通过：'+(result.stderr or result.stdout)[-1500:])
    return result


def _native(root, folder, workbook, name):
    output = folder/name
    receipt = output/'receipt.json'
    _command(root, folder, name, [PWSH, '-NoProfile', '-File',
        root/'scripts/current/verify_m7_product_ux_trial_wps.ps1', '-WorkbookPath', workbook,
        '-ReceiptPath', receipt, '-OutputDirectory', output, '-ExpectedSha256', sha256_file(workbook)])
    payload = load_json_object(receipt, 'native receipt')
    verify_native_workbook_receipt(root, payload, sha256_file(workbook))
    return receipt


def _register(root, folder, before_pointer, publication, native_path, product):
    pointer_path = root/'config/current-trial-workbook.json'
    if load_json_object(pointer_path, 'current pointer') != before_pointer:
        raise ValueError('工作簿指针发生并发变化，拒绝覆盖')
    successor = deepcopy(before_pointer)
    successor.update(previous_canonical_workbook_sha256=publication['before_sha256'],
                     canonical_workbook_sha256=publication['after_sha256'],
                     daily_product_state_binding=product['state_binding'])
    old = before_pointer['current_publication']
    successor['current_publication'] = dict(old,
        receipt=publication['receipt'], receipt_sha256=sha256_file(root/publication['receipt']),
        wps_receipt=native_path.relative_to(root).as_posix(), wps_receipt_sha256=sha256_file(native_path),
        registered_at=datetime.now(timezone.utc).date().isoformat(),
        status='PUBLISHED_WPS_READONLY_VERIFIED', research_as_of=product['handoff']['snapshot']['as_of'])
    floor = verify_workbook_publication(root, successor)
    successor['current_publication']['quote_observation_as_of'] = str(floor)
    verify_workbook_publication(root, successor)
    staging = root/'.tmp'/('workbook-pointer-'+uuid4().hex+'.json')
    write_new_json(staging, successor)
    if load_json_object(pointer_path, 'current pointer') != before_pointer:
        raise ValueError('工作簿指针发生并发变化，保留登记暂存供排查')
    os.replace(staging, pointer_path)
    verify_workbook_publication(root, load_json_object(pointer_path, 'updated pointer'))
    return successor


def recover_interrupted_product_publications(*, root, workbook):
    """Restore only an exact unregistered candidate, never a user/successor edit."""
    from scripts.current.publish_product_workbench_to_canonical import (
        _project_staging_directory, _replace_canonical_staging)
    results = []
    for intent_path in sorted((root/'runtime').rglob('publication-intent.json')):
        folder = intent_path.parent
        if (folder/'publication-complete.json').exists() or (folder/'publication-rollback.json').exists():
            continue
        intent = load_json_object(intent_path, 'publication recovery intent')
        prior = load_json_object(folder/'previous-workbook-pointer.json', 'prior pointer')
        if intent['before_sha256'] != prior['canonical_workbook_sha256']:
            raise ValueError('恢复意图与原指针 Hash 不一致，拒绝恢复')
        pointer = load_json_object(root/'config/current-trial-workbook.json', 'pointer')
        actual = sha256_file(workbook)
        if actual == intent['before_sha256'] and pointer == prior:
            continue
        if pointer != prior:
            if actual == pointer['canonical_workbook_sha256']:
                verify_workbook_publication(root, pointer)
                results.append(dict(status='SUCCESSOR_ALREADY_REGISTERED', folder=str(folder)))
                continue
            raise ValueError('发布中断且指针或用户文件发生变化；拒绝自动恢复')
        if actual != intent['candidate_sha256']:
            raise ValueError('发布中断后原表已被修改；拒绝覆盖')
        backup = require_inside(folder, root/intent['recovery_backup']['path'], 'recovery backup')
        if (intent['recovery_backup']['sha256'] != intent['before_sha256']
                or sha256_file(backup) != intent['before_sha256']):
            raise ValueError('发布恢复备份 Hash 不匹配')
        staging_root = _project_staging_directory(root, workbook, authorized_external=True)
        staging = staging_root/('interrupted-rollback-'+uuid4().hex+'.xlsx')
        shutil.copy2(backup, staging)
        _replace_canonical_staging(workbook, staging, expected_source_sha256=actual,
            staging_sha256=intent['before_sha256'], scratch_dir=staging_root)
        receipt = dict(action='no_order', status='ROLLED_BACK_INTERRUPTED_UNREGISTERED_PUBLICATION',
            workbook_sha256=sha256_file(workbook))
        write_new_json(folder/'publication-rollback.json', receipt)
        results.append(receipt)
    return results


def publish_product_update(*, root: Path, folder: Path, product: dict,
                           workbook: Path, expected_before: str) -> dict:
    # These helpers are the existing publisher contract; no parallel replacement
    # implementation or spreadsheet engine is introduced here.
    sys.path.insert(0, str(root))
    from scripts.current.publish_product_workbench_to_canonical import (
        build_protected_research_preview, _verify_authored_product_inputs,
        _verify_reviewed_research_source_bindings, _reviewed_research_publication,
        _project_staging_directory, _replace_canonical_staging)
    from value_investment_agent.presentation.excel.product_workbench import _user_text
    before_pointer = load_json_object(root/'config/current-trial-workbook.json', 'pointer')
    if before_pointer['canonical_workbook_sha256'] != expected_before or sha256_file(workbook) != expected_before:
        raise ValueError('原表或当前指针 Hash 冲突，拒绝覆盖')
    handoff = product['handoff']
    handoff_path = product['handoff_path']
    strings = set()
    pending = [handoff['snapshot']]
    while pending:
        value = pending.pop()
        if isinstance(value, str): strings.add(value)
        elif isinstance(value, dict): pending.extend(value.values())
        elif isinstance(value, list): pending.extend(value)
    policy = root/'src/value_investment_agent/presentation/excel/product_workbench.py'
    display_path = folder/'display-input.json'
    write_new_json(display_path, dict(action='no_order', canonical_written=False,
        input_sha256=sha256_file(handoff_path),
        policy_binding=dict(path=policy.relative_to(root).as_posix(), sha256=sha256_file(policy)),
        strings={value: _user_text(value) for value in strings}))
    marker = Path('C:/Users/we/.codex/plugins/cache/openai-primary-runtime/spreadsheets/26.1007.11041/skills/spreadsheets/container_tools/mark_artifact_operation_started.mjs')
    if not NODE.is_file() or not marker.is_file():
        raise ValueError('托管表格运行环境不可用；研究已保留，未发布')
    _command(root, folder, 'artifact-start', [NODE, marker, '--operation-kind', 'edit',
                                           '--expected-output-count', '1', '--output-format', 'xlsx'])
    authored = folder/'trade-assistant-preview.xlsx'
    _command(root, folder, 'artifact', [NODE, root/'scripts/current/render_dual_strategy_artifact_pages.mjs',
        '--publication-input', handoff_path, '--sha256', sha256_file(handoff_path),
        '--display-input', display_path, '--output', authored, '--render-review',
        '--manual-input-source', workbook, '--manual-input-source-sha256', expected_before])
    candidate = folder/'canonical-integration-historical-preview.xlsx'
    protected = build_protected_research_preview(root, workbook, candidate, product['model'],
                         authored_pages=authored, authored_pages_sha256=sha256_file(authored))
    authored_sources = _verify_authored_product_inputs(root, authored, sha256_file(authored),
                                                      sha256_file(handoff_path), len(handoff['source_bindings']))
    sources_path = candidate.with_name(candidate.stem+'.source-bindings.json')
    write_new_json(sources_path, dict(schema_version='existing-workbench-preview-bindings-v1',
        integrated_canonical=True, historical_preview=True, canonical_written=False, action='no_order',
        publication_input_binding=dict(path=handoff_path.relative_to(root).as_posix(), sha256=sha256_file(handoff_path)),
        authored_pages_binding=dict(path=authored.relative_to(root).as_posix(), sha256=sha256_file(authored)),
        source_bindings=[*handoff['source_bindings'], *authored_sources],
        workbook_sha256=protected['workbook_sha256'], output_manifest_sha256=protected['manifest_sha256']))
    _verify_reviewed_research_source_bindings(root, candidate, folder/'canonical-preservation.json', sources_path)
    from scripts.current.verify_dual_product_values import verify_dual_product_values
    write_new_json(folder/'numeric-source-verification.json',
        verify_dual_product_values(root=root, workbook=candidate))
    _command(root, folder, 'readability', [sys.executable, '-X', 'utf8',
        root/'scripts/current/audit_m7_product_ux_readability.py', '--workbook', candidate,
        '--receipt', folder/'readability.json'])
    _native(root, folder, candidate, 'native-review')
    _command(root, folder, 'native-navigation', [PWSH, '-NoProfile', '-File',
        root/'scripts/current/verify_product_navigation.ps1', '-WorkbookPath', candidate,
        '-ExpectedSha256', sha256_file(candidate), '-ReceiptPath', folder/'native-navigation.json'])
    # Native named-page/PDF evidence and explicit geometry checks are verified
    # automatically. Final user acceptance remains independent.
    readable = load_json_object(folder/'readability.json', 'readability')
    if readable['status'] != 'passed':
        raise ValueError('表格存在裁切，未发布')
    write_new_json(folder/'visual-review.json', dict(status='PASS', publication_allowed=True,
        action='no_order', workbook_sha256=sha256_file(candidate),
        review_method='Native named-page PDF exports plus deterministic geometry/readability checks',
        final_user_acceptance='NOT_PASSED', publication_allowed_scope='AUTOMATED_LAYOUT_ONLY'))
    write_new_json(folder/'previous-workbook-pointer.json', before_pointer)
    recovery_backup = folder/'pre-publication-recovery.xlsx'
    shutil.copy2(workbook, recovery_backup)
    if sha256_file(recovery_backup) != expected_before:
        raise ValueError('预发布恢复备份 Hash 冲突')
    write_new_json(folder/'publication-intent.json', dict(action='no_order',
        before_sha256=expected_before, candidate_sha256=sha256_file(candidate),
        recovery_backup=dict(path=recovery_backup.relative_to(root).as_posix(), sha256=expected_before)))
    publication = None
    try:
        publication = _reviewed_research_publication(root, workbook, folder,
                      sha256_file(folder/'canonical-preservation.json'), publish=True)
        write_new_json(folder/'publication-pending-registration.json', publication)
        native = _native(root, folder, workbook, 'published-native-review')
        successor = _register(root, folder, before_pointer, publication, native, product)
        result = dict(status='PUBLISHED_WPS_READONLY_VERIFIED', action='no_order',
            workbook_sha256=sha256_file(workbook), pointer_sha256=sha256_file(root/'config/current-trial-workbook.json'),
            publication_receipt=publication['receipt'], user_acceptance='NOT_PASSED')
        write_new_json(folder/'publication-complete.json', result)
        return result
    except Exception as error:
        current_pointer = load_json_object(root/'config/current-trial-workbook.json', 'pointer')
        if current_pointer != before_pointer and sha256_file(workbook) == current_pointer['canonical_workbook_sha256']:
            verify_workbook_publication(root, current_pointer)
            return dict(status='PUBLISHED_WPS_READONLY_VERIFIED', action='no_order',
                workbook_sha256=sha256_file(workbook),
                pointer_sha256=sha256_file(root/'config/current-trial-workbook.json'),
                warning='版本已合法登记；尾部回执写入失败：'+str(error), user_acceptance='NOT_PASSED')
        # Never restore over a concurrent user edit or a successor registration.
        if (sha256_file(workbook) == sha256_file(candidate)
                and load_json_object(root/'config/current-trial-workbook.json', 'pointer') == before_pointer):
            staging_root = _project_staging_directory(root, workbook, authorized_external=True)
            rollback = staging_root/('rollback-'+uuid4().hex+'.xlsx')
            shutil.copy2(recovery_backup, rollback)
            _replace_canonical_staging(workbook, rollback,
                expected_source_sha256=sha256_file(candidate), staging_sha256=expected_before,
                scratch_dir=staging_root)
            write_new_json(folder/'publication-rollback.json', dict(action='no_order',
                status='ROLLED_BACK_AFTER_VERIFICATION_FAILURE', workbook_sha256=sha256_file(workbook)))
        raise ProductPublicationError(str(error), canonical_written=sha256_file(workbook) != expected_before) from error

"""One update use case, with injected existing research and publication adapters."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Callable

from .common import load_json_object, require_inside, sha256_file, write_new_json


def semantic_content(value):
    """Exclude transport identity, retaining evidence dates and economic inputs."""
    ignored = {'generated_at', 'finished_at', 'started_at', 'run_id', 'fetched_at',
               'collected_at', 'implementation_bindings', 'receipt_binding',
               'outputs'}
    if isinstance(value, dict):
        return {key: semantic_content(item) for key, item in value.items() if key not in ignored}
    if isinstance(value, list):
        return [semantic_content(item) for item in value]
    return value


def semantic_digest(value):
    raw = json.dumps(semantic_content(value), ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def run_product_update(*, root: Path, output_dir: Path, published: dict,
                       research_runner: Callable, composer: Callable,
                       publisher: Callable, publish: bool = True) -> dict:
    root = root.resolve()
    output_dir = require_inside(root/'runtime', output_dir, 'product update output')
    output_dir.mkdir(parents=True, exist_ok=False)
    before = published['pointer']['canonical_workbook_sha256']
    result = dict(schema_version='daily-update-product-closure-v1', action='no_order',
                  canonical_written=False, previous_workbook_sha256=before,
                  status='UPDATE_FAILED', blockers=[], position_guidance=None)
    try:
        batch_path = research_runner(output_dir/'research')
        batch_path = require_inside(output_dir, batch_path, 'research receipt')
        batch = load_json_object(batch_path, 'research batch')
        if (batch.get('action') != 'no_order' or batch.get('failed_case_count')
                or batch.get('blocked_asset_count') or batch.get('partial_product_count')):
            raise ValueError('部分公司研究未完成；正式表格保持已发布版本')
        result['research_binding'] = dict(path=batch_path.relative_to(root).as_posix(),
                                         sha256=sha256_file(batch_path))
        product, changes = composer(output_dir, deepcopy(published), batch)
        result['changes'] = changes
        result['semantic_sha256'] = changes.get('current_semantic_sha256')
        if not changes['material_change']:
            result.update(status='NO_MATERIAL_CHANGE', message='输入和研究状态无实质变化，未覆盖工作簿。')
        elif not publish:
            result.update(status='UPDATED_NOT_PUBLISHED', message='研究更新完成；本次仅生成候选产品。')
        else:
            receipt = publisher(output_dir, product, before)
            if receipt.get('status') != 'PUBLISHED_WPS_READONLY_VERIFIED':
                raise ValueError('发布后原生验证或指针登记未完成')
            result.update(status='PUBLISHED_WPS_READONLY_VERIFIED', canonical_written=True,
                          publication=receipt, message='研究及正式 Excel 已更新并验证。')
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        result['canonical_written'] = bool(getattr(error, 'canonical_written', False))
        if result['canonical_written']:
            result['status'] = 'PUBLICATION_NEEDS_RECOVERY'
        result['blockers'].append(str(error))
        result['message'] = '更新或发布未完成，详见失败原因；未把旧数据标成新数据。'
    write_new_json(output_dir/'product-update-receipt.json', result)
    return result

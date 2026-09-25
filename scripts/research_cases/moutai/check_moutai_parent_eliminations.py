"""Verify parent internal receivables; parent statements are not an industrial segment."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(source)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    pair=texts(source,103)
    rows=[('贵州茅台酒销售有限公司','6933933340.00'),
          ('贵州茅台酱香酒营销有限公司','1876222738.14'),
          ('贵州茅台酒进出口有限责任公司','1036137600.22')]
    checks=['合并范围内关联方组合9,846,293,678.361009,846,293,678.3611,895,319,134.7510011,895,319,134.75']
    checks.extend(name+format(D(amount),',.2f')+format(D(amount),',.2f') for name,amount in rows)
    for phrase in checks:
        if any(phrase not in text for text in pair):
            raise ValueError('Parent intercompany disclosure mismatch')
    total=sum((D(amount) for _,amount in rows),D(0))
    if total!=D('9846293678.36') or sum((Fraction(amount) for _,amount in rows),Fraction(0))!=Fraction(total):
        raise ValueError('Parent receivable counterparties do not reconcile')
    out=ROOT/'runtime/company-research'/('600519-parent-eliminations-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    result={'symbol':'600519','period_end':'2026-06-30','unit':'CNY','scope':'parent legal entity',
        'source_path':str(source.relative_to(ROOT)),'source_sha256':sha(source),'physical_page':103,
        'original_checks':checks,'counterparties':[{'name':n,'receivable':v} for n,v in rows],
        'internal_parent_trade_receivables':str(total),
        'model_scope_constraints':['Parent trade receivables are fully internal to consolidation for this disclosed balance.',
            'Do not add parent receivables to consolidated operating assets or the equity bridge.',
            'Parent profit/cash flow is not industrial consolidated profit/cash flow: sales margins, minority participation and internal settlements differ.',
            'A sum-of-parts model must eliminate intercompany claims and investments before combining subsidiary values.',
            'This counterparties reconciliation does not establish every group elimination or complete industrial allocation.'],
        'industrial_segment_substitution_allowed':False}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'evidence_sha256':sha(out/'evidence.json'),'script_sha256':sha(Path(__file__))},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'reconciled_internal_receivables':str(total)}))


if __name__=='__main__':
    main()

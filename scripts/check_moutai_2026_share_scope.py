"""Distinguish planned cancellation from later confirmed issued shares."""
from datetime import datetime, timezone
from decimal import Decimal as D
import hashlib
import json

from pypdf import PdfReader
import pypdfium2 as pdfium
from build_moutai_business_evidence import ROOT, compact


SOURCES = [
    ('runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf',
     '0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6',
     {22: ['单位：股', '三、股份总数1,252,270,215100-2,188,614-2,188,6141,250,081,601100'],
      23: ['并在中国证券登记结算有限责任公司上海分公司完成注销', '1,252,270,215股减少至1,250,081,601股'],
      72: ['股票回购120,112,601.532,880,061,147.373,000,173,748.90'],
      86: ['其他原因的合并范围变动', '成立全资子公司贵州爱茅台数字科技有限公司']}),
    ('runtime/historical-filing-index/20260909T034313031785Z/pdfs/600519-1225333825.pdf',
     'c3d2cf8322ad4b8d8b69c914a0afd265bf0f85cdaa1f023d00109caa0a9721c1',
     {2: ['2026年5月27日，公司回购股份实施完成', '2,999,933,749.57元（不含交易费用）'],
      3: ['预计公司将于2026年5月28日', '本次拟注销后']}),
]


def main():
    proof = []
    for relative, digest, pages in SOURCES:
        path = ROOT / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Original hash mismatch')
        reader = PdfReader(path)
        with pdfium.PdfDocument(path) as doc:
            for number, snippets in pages.items():
                text1 = compact(reader.pages[number - 1].extract_text())
                page = doc[number - 1]
                textpage = page.get_textpage()
                try:
                    text2 = compact(textpage.get_text_range())
                finally:
                    textpage.close()
                    page.close()
                for snippet in snippets:
                    if compact(snippet) not in text1 or compact(snippet) not in text2:
                        raise ValueError(f'Reviewed snippet mismatch p{number}: {snippet}')
                proof.append({'path': relative, 'sha256': digest, 'physical_page': number, 'snippets': snippets})
    before, cancelled, after = 1252270215, 2188614, 1250081601
    if before - cancelled != after:
        raise ValueError('Issued-share roll-forward mismatch')
    treasury_residual = D('120112601.53') + D('2880061147.37') - D('3000173748.90')
    if treasury_residual != 0:
        raise ValueError('Treasury carrying amount does not reconcile')
    result = {
        'symbol': '600519', 'generated_at': datetime.now(timezone.utc).isoformat(),
        'evidence': proof, 'issued_shares_at_2026_06_30': after,
        'issued_share_roll_forward': {'opening': before, 'cancellation': cancelled, 'closing': after},
        'treasury_carrying_amount_reconciled_CNY': str(treasury_residual),
        'treasury_basis': 'Derived from opening plus additions less reductions; not blank-cell default',
        'repurchase_completed_on': '2026-05-27',
        'cancellation_expected_on': '2026-05-28',
        'cancellation_exact_effective_date_verified': False,
        'cancellation_confirmed_by_period_end': '2026-06-30',
        'confirmation_report_publication_date': '2026-08-15',
        'publication_precision': 'date_only_no_intraday_proof',
        'current_2026_09_09_share_basis_verified': False,
        'accounting_eps_weighted_shares_verified': False,
        'consolidation_scope_unchanged': False,
        'new_subsidiary': '贵州爱茅台数字科技有限公司',
        'full_ttm_comparability_approved': False,
        'valuation_approved': False,
    }
    target = ROOT / 'runtime/company-research' / ('600519-shares-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    target.mkdir(parents=True, exist_ok=False)
    (target / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(target / 'evidence.json'), 'issued_shares': after,
                      'treasury_CNY_residual': str(treasury_residual), 'exact_cancellation_date_verified': False}))


if __name__ == '__main__':
    main()

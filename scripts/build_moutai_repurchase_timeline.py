"""Point-in-time cumulative repurchase disclosures, separated by program."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts
from value_investment_agent.historical_asof import publication_date_upper_bound


def select(rows,program,decision):
    stamp=datetime.fromisoformat(decision)
    if stamp.utcoffset() is None:
        raise ValueError('Timezone required')
    eligible=[r for r in rows if r['program']==program and datetime.fromisoformat(r['available_at'])<=stamp]
    return max(eligible,key=lambda r:r['available_at']) if eligible else None


def main():
    prior=ROOT/'runtime/strategy-validation/moutai-repurchase-snapshots-20260909T094904283693Z/evidence.json'
    if sha(prior)!='28c7d841e57cae731ae6453dfe199b5f980af7a97d0f23fb0fefa653a2d05885':
        raise ValueError('Snapshot input changed')
    rows=[{**r,'program':'2024-09-21','repurchase_complete':False} for r in json.loads(prior.read_text(encoding='utf-8'))['snapshots']]
    first=ROOT/'runtime/company-research/600519-first-repurchases-20260909T095115681968Z'
    specs={'1222206659':('2024-09-21','2025-01-02',200900,'299919221.00'),
           '1224917210':('2025-11-06','2025-12-31',87059,'120102993.09')}
    for entry in json.loads((first/'manifest.json').read_text(encoding='utf-8')):
        announcement=entry['announcement'];aid=announcement['announcementId']
        program,cutoff,shares,cash=specs[aid];pdf=first/(aid+'.pdf')
        if sha(pdf)!=entry['sha256'] or sha(ROOT/entry['index_path'])!=entry['index_sha256']:
            raise ValueError('Original or index changed')
        phrase=datetime.fromisoformat(cutoff).strftime('%Y年%m月%d日').replace('年0','年').replace('月0','月')
        for decoded in texts(pdf,2):
            if phrase not in decoded or f'{shares:,}' not in decoded or f'{float(cash):,.2f}' not in decoded:
                raise ValueError('First repurchase body mismatch')
        published=datetime.fromtimestamp(announcement['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
        rows.append({'source_id':'cninfo:'+aid,'program':program,'statistical_cutoff':cutoff,
            'published_date':published,'available_at':publication_date_upper_bound(published).isoformat(),
            'cumulative_shares':shares,'cumulative_cash_excluding_fees':cash,'source_sha256':entry['sha256'],
            'source_path':str(pdf.relative_to(ROOT)),'source_url':entry['url'],'repurchase_complete':False})
    completed=ROOT/'runtime/company-research/600519-cancellation-2025-20260909T094442562176Z/original.pdf'
    if sha(completed)!='9ad8dda3c43bbc19bf9926394ddf4a030543455910f7ef1b1bb736bd4385215b':
        raise ValueError('Completion original changed')
    for text in texts(completed,2):
        if any(p not in text for p in ('2025年8月29日','3,927,585股','5,999,985,966.95元','公司回购股份实施完成')):
            raise ValueError('Completion evidence mismatch')
    for text in texts(completed,3):
        if '预计公司将于2025年9月1日' not in text:
            raise ValueError('Cancellation qualification changed')
    rows.append({'source_id':'cninfo:1224625694','program':'2024-09-21','statistical_cutoff':'2025-08-29',
        'published_date':'2025-08-30','available_at':publication_date_upper_bound('2025-08-30').isoformat(),
        'cumulative_shares':3927585,'cumulative_cash_excluding_fees':'5999985966.95',
        'source_path':str(completed.relative_to(ROOT)),'source_sha256':sha(completed),
        'repurchase_complete':True,'cancellation_confirmed':False})
    rows.sort(key=lambda r:r['available_at'])
    checks=[('2025-11-06','2025-12-31T15:00:00+08:00',None),
            ('2025-11-06','2026-01-05T15:00:00+08:00',None),
            ('2025-11-06','2026-01-06T00:00:00+08:00','cninfo:1224917210'),
            ('2024-09-21','2025-08-29T15:00:00+08:00','cninfo:1224387017'),
            ('2024-09-21','2025-09-01T15:00:00+08:00','cninfo:1224625694')]
    for program,day,expected in checks:
        chosen=select(rows,program,day)
        if (chosen['source_id'] if chosen else None)!=expected:
            raise ValueError('Point-in-time boundary failed')
    out=ROOT/'runtime/strategy-validation'/('moutai-repurchase-timeline-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    (out/'evidence.json').write_text(json.dumps({'snapshots':rows,'boundary_checks':checks,
        'limitations':['Snapshots describe last disclosed cumulative repurchases, not actual current daily treasury stock.',
            'Programs remain separate; first-program completion does not imply second-program completion.',
            'Repurchase cash excludes fees; cancellation and accounting recognition remain separate.',
            'No complete share count, valuation or strategy approval.']},ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json'),'prior_snapshot_sha256':sha(prior)},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'snapshots':len(rows),'boundary_checks_passed':len(checks)}))


if __name__=='__main__':
    main()

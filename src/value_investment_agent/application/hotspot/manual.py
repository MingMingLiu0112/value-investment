"""Network-first manual observation with explicit retained-data fallback."""
from datetime import datetime,timezone
import json
from pathlib import Path
from value_investment_agent.application.product.common import require_inside,sha256_file,write_new_json
from value_investment_agent.m2_market_data import fetch_tencent_board_rank,fetch_sina_industry_quotes
from value_investment_agent.quote_session_collection import collect_session_bundle
from value_investment_agent.infrastructure.hotspot.sources import read_bound
from .scan import scan_market_hotspots


def run_manual_scan(*,root:Path,output:Path,offline_bundle:Path|None=None,offline_sha256:str|None=None,cutoff:datetime|None=None) -> dict:
    output=require_inside(root/'runtime',output,'hotspot output')
    if offline_bundle is not None:
        bundle=require_inside(root,offline_bundle,'offline hotspot bundle')
        if not offline_sha256 or sha256_file(bundle)!=offline_sha256:
            raise ValueError('Offline bundle hash required and must match')
        result=scan_market_hotspots(root=root,config_path=bundle,output=output,cutoff=cutoff or datetime.now(timezone.utc))
        mode={'mode':'OFFLINE_VERIFIED_REPLAY','fallback':False,'network_attempted':False}
    else:
        if offline_sha256 is not None:
            raise ValueError('Offline hash requires bundle')
        if cutoff is not None:
            raise ValueError('Network scan cannot inject observation time')
        output.mkdir(parents=True,exist_ok=False)
        config=json.loads((root/'config/hotspot-manual-scan-v1.json').read_text(encoding='utf-8'))
        attempts=[]
        for role,collector in [('market',fetch_tencent_board_rank),('industry',fetch_sina_industry_quotes)]:
            try:
                raw,payload=collector()
                path=output/(role+'-raw.json')
                path.write_bytes(raw)
                config[role]=dict(path=path.relative_to(root).as_posix(),sha256=sha256_file(path),
                    available_at=payload['fetched_at'],source_url=payload['source_url'])
                attempts.append(dict(role=role,status='COLLECTED_SECONDARY_SOURCE'))
            except Exception as error:
                attempts.append(dict(role=role,status='RETAINED_OLD_CACHE_FALLBACK',
                    error_type=type(error).__name__,reason=str(error)[:400],
                    cache_available_at=config[role]['available_at']))
        bundle=output/'offline-bundle.json'
        try:
            industry=json.loads((root/config['industry']['path']).read_text(encoding='utf-8'))
            rows=sorted(industry['rows'],key=lambda r:float(r.get('amount') or 0),reverse=True)
            history_raw,_=read_bound(root,config['history'],datetime.now(timezone.utc))
            history_symbol=json.loads(history_raw)['symbol']
            symbols=list(dict.fromkeys([str(r['code']).zfill(6) for r in rows[:config['limit']]]+[history_symbol]))
            dated=collect_session_bundle(symbols)
            dated_path=output/'dated-quotes.json'
            write_new_json(dated_path,dated)
            config['dated_quotes']=dict(path=dated_path.relative_to(root).as_posix(),sha256=sha256_file(dated_path),
                available_at=dated['finished_at'],source_url='https://qt.gtimg.cn/q=')
        except Exception as error:
            attempts.append(dict(role='dated_quotes',status='UNKNOWN',reason=str(error)[:400]))
        write_new_json(bundle,config)
        mode={'mode':'NETWORK_FIRST','network_attempted':True,'fallback':any(a['status']=='RETAINED_OLD_CACHE_FALLBACK' for a in attempts),'attempts':attempts}
        result=scan_market_hotspots(root=root,config_path=bundle,output=output,cutoff=datetime.now(timezone.utc),prepared_output=True,collection=mode)
    # Keep acquisition mode separate from the stable observation semantics.
    write_new_json(output/'collection-receipt.json',dict(mode,action='no_order',report_sha256=sha256_file(output/'report.json')))
    return dict(report_path=(output/'report.json').relative_to(root).as_posix(),sha256=sha256_file(output/'report.json'),action='no_order')

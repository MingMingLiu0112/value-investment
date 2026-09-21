"""Collect and compare official lists to a retained market export, without DB access."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'src'))
from value_investment_agent.official_universe import collect_security_lists, reconcile_security_lists

root = Path('runtime/exchange-lists')
universe = collect_security_lists(root / 'raw')
payload = json.loads(Path('runtime/server-export-payload.json').read_text(encoding='utf-8-sig'))
result = reconcile_security_lists(universe,payload['market_audit'])
(root / 'official-universe.json').write_text(json.dumps(universe,ensure_ascii=False,indent=2),encoding='utf-8')
(root / 'reconciliation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k != 'sources'},ensure_ascii=False),flush=True)

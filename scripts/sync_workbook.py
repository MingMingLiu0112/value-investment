"""Low-memory replacement for the spreadsheet WASM exporter."""
import json
import hashlib
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from value_investment_agent.excel_report import build_report
from value_investment_agent.debt_research_export import load_debt_research
from value_investment_agent.company_research_export import load_company_research

if __name__ == '__main__':
    template, payload, output = map(Path, sys.argv[1:])
    receipt = output.with_suffix(output.suffix + '.failure.json')
    try:
        print(json.dumps({'stage': 'read_payload'}, ensure_ascii=False), flush=True)
        raw = payload.read_bytes()
        data = json.loads(raw.decode('utf-8-sig'))
        root = Path(__file__).resolve().parents[1]
        print(json.dumps({'stage': 'load_research'}, ensure_ascii=False), flush=True)
        research = load_debt_research(root, data, hashlib.sha256(raw).hexdigest())
        company_research = load_company_research(root)
        print(json.dumps({'stage': 'build_workbook'}, ensure_ascii=False), flush=True)
        result = build_report(template, data, output, debt_research=research, company_research=company_research)
        receipt.unlink(missing_ok=True)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as error:
        receipt.write_text(json.dumps({'error_type': type(error).__name__, 'error': str(error),
                                       'traceback': traceback.format_exc()}, ensure_ascii=False, indent=2), encoding='utf-8')
        raise

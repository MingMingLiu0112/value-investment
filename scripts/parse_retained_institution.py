"""Run the current institution parser on one retained PDF without DB writes."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'src'))
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.institution_metrics import parse_tables

path,model,period = sys.argv[1:]
facts = parse_tables(extract_pages(Path(path)),model,period)
print(json.dumps(facts,ensure_ascii=False,indent=2))

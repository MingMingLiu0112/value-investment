"""Run the staged repair module without installing it into live server source."""
import runpy
import sys
from pathlib import Path

import provenance_repair

sys.modules['value_investment_agent.provenance_repair'] = provenance_repair
runpy.run_path(str(Path(__file__).with_name('repair_filing_provenance.py')), run_name='__main__')

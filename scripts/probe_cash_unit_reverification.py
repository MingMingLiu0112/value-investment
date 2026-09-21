"""Stage only the comparison module; preserve production dependencies."""
from pathlib import Path
import runpy
import value_investment_agent

stage = Path(__file__).resolve().parent
value_investment_agent.__path__.insert(0, str(stage))
runpy.run_path(str(stage / 'reverify_shadowed_facts.py'), run_name='__main__')

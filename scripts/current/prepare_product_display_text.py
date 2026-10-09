"""Reuse the existing display policy; do not change source research strings."""
import json
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from value_investment_agent.application.product.research_publication_input import load_research_publication_input
from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.presentation.excel.product_workbench import _user_text

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--publication-input", type=Path, required=True)
parser.add_argument("--sha256", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
source = ROOT / args.publication_input
output = (ROOT / args.output).resolve()
if not output.is_relative_to(ROOT / "runtime"):
    raise ValueError("display snapshot must remain under runtime")
verified = load_research_publication_input(root=ROOT, path=source, expected_sha256=args.sha256)
strings = set()

def visit(value):
    if isinstance(value, str):
        strings.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            visit(item)
    elif isinstance(value, list):
        for item in value:
            visit(item)

visit(verified["snapshot"])
policy = ROOT / "src/value_investment_agent/presentation/excel/product_workbench.py"
write_new_json(output, {
    "input_sha256": sha256_file(source),
    "policy_binding": {"path": policy.relative_to(ROOT).as_posix(), "sha256": sha256_file(policy)},
    "strings": {text: _user_text(text) for text in sorted(strings)},
    "action": "no_order", "canonical_written": False,
})
print(json.dumps({"output": str(output.relative_to(ROOT)), "sha256": sha256_file(output),
                  "canonical_written": False, "action": "no_order"}))

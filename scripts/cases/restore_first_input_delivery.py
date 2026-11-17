"""Restore a reviewed public first-input archive into a new isolated directory."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.application.research.first_input_delivery_v1 import restore_first_input_delivery

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    destination = args.destination.resolve()
    if not destination.is_relative_to((ROOT / ".tmp").resolve()):
        parser.error("destination must be a new isolated directory under project .tmp")
    print(json.dumps(restore_first_input_delivery(archive_root=args.archive,
        manifest_sha256=args.sha256, destination=destination)))

"""Write one read-only daily research summary from the registered inputs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.product.common import write_new_json  # noqa: E402
from value_investment_agent.application.product.daily_research_status import (  # noqa: E402
    build_daily_research_status,
)


def _content_digest(content: dict) -> str:
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to((ROOT / "runtime").resolve()):
        parser.error("output must remain under runtime/")
    content = build_daily_research_status(ROOT, today=datetime.now(timezone.utc))
    digest = _content_digest(content)
    payload = {"schema_version": "daily-research-summary-v1", "action": "no_order",
               "content": content, "content_sha256": digest}
    if output.exists():
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as error:
            parser.error(f"existing output is unreadable: {type(error).__name__}")
        if existing.get("content") == content and existing.get("content_sha256") == digest:
            print(json.dumps({"status": "UNCHANGED", "output": str(output),
                              "content_sha256": digest, "action": "no_order"},
                             ensure_ascii=False, indent=2))
            return 0
        print(json.dumps({"status": "REFUSED_INPUT_CHANGED", "output": str(output),
                          "existing_content_sha256": existing.get("content_sha256"),
                          "recomputed_content_sha256": digest, "action": "no_order",
                          "note": "write a new output path; history is never overwritten"},
                         ensure_ascii=False, indent=2))
        return 3
    write_new_json(output, payload)
    print(json.dumps({"status": "WRITTEN", "output": str(output),
                      "content_sha256": digest,
                      "needs_re_research_count": content["needs_re_research_count"],
                      "registered_count": content["registered_count"],
                      "action": "no_order"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

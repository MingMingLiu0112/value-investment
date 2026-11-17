"""Cold, offline A/B replay from an explicitly hash-bound public SSE manifest.

The historical manifest remains untouched. This command creates a new versioned
observation under the isolated root and never reads or updates a current pointer.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from value_investment_agent.application.discovery import sse_main_screening as screen


VERSION = "sse-ab-offline-source-bound-v1"


def bound_bytes(source_root: Path, binding: dict) -> bytes:
    if not isinstance(binding, dict) or not {"path", "sha256"} <= binding.keys():
        raise ValueError("EXACT_SOURCE_BINDING_REQUIRED")
    relative = Path(binding["path"])
    if relative.is_absolute() or ".." in relative.parts or not relative.as_posix().startswith("runtime/sse-main-screening/"):
        raise ValueError("PUBLIC_SSE_RUNTIME_PATH_REQUIRED")
    path = (source_root / relative).resolve()
    if not path.is_relative_to((source_root / "runtime/sse-main-screening").resolve()):
        raise ValueError("SOURCE_OUTSIDE_SSE_RUNTIME")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError(f"SOURCE_HASH_MISMATCH:{relative.as_posix()}")
    return raw


def stage_tree(source_root: Path, target_root: Path, value, staged: dict[str, str]) -> None:
    if isinstance(value, dict):
        if {"path", "sha256"} <= value.keys():
            raw = bound_bytes(source_root, value)
            relative = Path(value["path"])
            key = relative.as_posix()
            if key in staged and staged[key] != value["sha256"]:
                raise ValueError(f"CONFLICTING_SOURCE_BINDING:{key}")
            destination = target_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.read_bytes() != raw:
                raise ValueError(f"STAGED_SOURCE_CONFLICT:{key}")
            if not destination.exists():
                destination.write_bytes(raw)
            staged[key] = value["sha256"]
            if relative.suffix == ".json":
                try:
                    nested = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    nested = None
                if nested is not None:
                    stage_tree(source_root, target_root, nested, staged)
        for child in value.values():
            stage_tree(source_root, target_root, child, staged)
    elif isinstance(value, list):
        for child in value:
            stage_tree(source_root, target_root, child, staged)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_root, target_root = args.source_root.resolve(), args.target_root.resolve()
    if args.output.exists():
        raise ValueError("NEW_OUTPUT_PATH_REQUIRED")
    binding = {"path": args.manifest_path, "sha256": args.manifest_sha256}
    manifest = json.loads(bound_bytes(source_root, binding))
    if manifest.get("schema_version") != "sse-main-screening-v1" or manifest.get("action") != "no_order":
        raise ValueError("HISTORICAL_PUBLIC_SSE_MANIFEST_REQUIRED")
    staged: dict[str, str] = {}
    stage_tree(source_root, target_root, manifest["inputs"], staged)
    cutoff = datetime.fromisoformat(manifest["generated_at"])
    result, receipt = screen.compile_inputs(root=target_root, inputs=manifest["inputs"],
                                            now=cutoff, run_id=manifest["run_id"])
    output = {
        "schema_version": VERSION, "action": "no_order",
        "historical_manifest": binding, "historical_implementation": manifest["implementation"],
        "replay_implementation": screen.implementation(), "evaluation_at": cutoff.isoformat(),
        "historical_manifest_replayed_identically": False,
        "staged_public_sources": staged, "counts": result["counts"],
        "result": result, "receipt": receipt,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"schema_version": VERSION, "counts": result["counts"],
                      "implementation_changed": manifest["implementation"] != output["replay_implementation"],
                      "staged_public_sources": len(staged), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Acquire, archive or restore a bounded official report set; never approve research."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.application.research.public_evidence import (
    run_public_evidence, publish_public_evidence,
    archive_public_evidence, restore_public_evidence,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("collect", "archive", "restore"), default="collect")
    parser.add_argument("--requests", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-public-downloads", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--previous-bundle")
    parser.add_argument("--previous-sha256")
    parser.add_argument("--publish-status", action="store_true")
    parser.add_argument("--bundle", help="Exact runtime bundle path for archive")
    parser.add_argument("--bundle-sha256")
    parser.add_argument("--manifest", help="Archive manifest path relative to project root")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--destination", type=Path, help="New isolated project .tmp root for restore")
    args = parser.parse_args()
    if args.mode == "collect":
        if not args.requests or not args.output:
            parser.error("collect requires --requests and --output")
        if any((args.bundle, args.bundle_sha256, args.manifest, args.manifest_sha256, args.destination)):
            parser.error("archive/restore arguments cannot be used in collect mode")
        if bool(args.previous_bundle) != bool(args.previous_sha256):
            parser.error("previous bundle requires both path and hash")
        previous = dict(path=args.previous_bundle, sha256=args.previous_sha256) if args.previous_bundle else None
        ref = run_public_evidence(root=ROOT, requests=json.loads(args.requests.read_text(encoding="utf-8-sig")),
            output_dir=args.output, allow_network=args.allow_public_downloads,
            refresh=args.refresh, previous_binding=previous)
        if args.publish_status:
            publish_public_evidence(ROOT, ref)
        result = dict(bundle=ref, action="no_order")
    else:
        if any((args.requests, args.allow_public_downloads, args.refresh, args.previous_bundle,
                args.previous_sha256, args.publish_status)):
            parser.error("archive/restore cannot collect, refresh or publish current")
        if args.mode == "archive":
            if not args.bundle or not args.bundle_sha256 or not args.output:
                parser.error("archive requires --bundle, --bundle-sha256 and --output")
            if any((args.manifest, args.manifest_sha256, args.destination)):
                parser.error("restore arguments cannot be used in archive mode")
            result = archive_public_evidence(root=ROOT,
                bundle_binding=dict(path=args.bundle, sha256=args.bundle_sha256), output_dir=args.output)
        else:
            if not args.manifest or not args.manifest_sha256 or not args.destination:
                parser.error("restore requires --manifest, --manifest-sha256 and --destination")
            if any((args.bundle, args.bundle_sha256, args.output)):
                parser.error("archive arguments cannot be used in restore mode")
            result = restore_public_evidence(root=ROOT,
                manifest_binding=dict(path=args.manifest, sha256=args.manifest_sha256),
                destination=args.destination)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

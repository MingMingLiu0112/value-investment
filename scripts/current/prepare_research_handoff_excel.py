"""Prepare a protected canonical preview from reverified research, never publish."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.product.common import require_inside, sha256_file, write_new_json
from value_investment_agent.application.product.research_publication_input import load_research_publication_input
from value_investment_agent.presentation.read_models.existing_research_report import public_workbench_payload_from_snapshot
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
from scripts.current.publish_product_workbench_to_canonical import (
    build_protected_research_preview, _workbook_path, _verify_authored_product_inputs,
)


def prepare(*, root: Path, canonical: Path, handoff: Path, digest: str, folder: Path,
            authored_pages: Path | None = None, authored_pages_sha256: str | None = None) -> dict:
    folder = require_inside(root / "runtime", folder, "historical preview folder")
    if folder.exists():
        raise FileExistsError("preview folder must be new")
    verified = load_research_publication_input(root=root, path=handoff, expected_sha256=digest)
    model = product_workbench_from_payload(public_workbench_payload_from_snapshot(verified["snapshot"]))
    authored_bindings = []
    if authored_pages is not None:
        authored_pages = require_inside(root / "runtime", authored_pages, "authored product pages")
        authored_bindings = _verify_authored_product_inputs(
            root, authored_pages, authored_pages_sha256, digest, len(verified["source_bindings"]))
    candidate = folder / "canonical-integration-historical-preview.xlsx"
    render_options = {} if authored_pages is None else dict(
        authored_pages=authored_pages, authored_pages_sha256=authored_pages_sha256)
    if authored_pages is None and authored_pages_sha256 is not None:
        raise ValueError("authored-page hash requires an authored workbook")
    receipt = build_protected_research_preview(root, canonical, candidate, model, **render_options)
    # Reverify after rendering so a changing source cannot enter publication.
    load_research_publication_input(root=root, path=handoff, expected_sha256=digest)
    binding = dict(path=handoff.resolve().relative_to(root.resolve()).as_posix(), sha256=digest)
    sidecar = dict(schema_version="existing-workbench-preview-bindings-v1",
                   integrated_canonical=True, historical_preview=True,
                   canonical_written=False, action="no_order",
                   publication_input_binding=binding,
                   source_bindings=verified["source_bindings"],
                   workbook_sha256=sha256_file(candidate),
                   output_manifest_sha256=receipt["manifest_sha256"])
    if authored_pages is not None:
        for binding in authored_bindings:
            if sha256_file(root / binding["path"]) != binding["sha256"]:
                raise ValueError("authored input changed after preparation")
        sidecar["source_bindings"] = [*verified["source_bindings"], *authored_bindings]
        sidecar["authored_pages_binding"] = authored_bindings[0]
    write_new_json(candidate.with_name(candidate.stem + ".source-bindings.json"), sidecar)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output-folder", type=Path, required=True)
    parser.add_argument("--historical-preview", action="store_true", required=True)
    parser.add_argument("--authored-pages", type=Path)
    parser.add_argument("--authored-pages-sha256")
    args = parser.parse_args()
    receipt = prepare(root=ROOT, canonical=_workbook_path(), handoff=ROOT / args.publication_input,
                      digest=args.sha256, folder=ROOT / args.output_folder,
                      authored_pages=None if args.authored_pages is None else ROOT / args.authored_pages,
                      authored_pages_sha256=args.authored_pages_sha256)
    import json
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()

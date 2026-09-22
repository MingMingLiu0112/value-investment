#!/usr/bin/env python3
"""Import frozen three-company runtime artifacts into a research repository.

Use --dsn only with a disposable/local/test PostgreSQL instance. Without it,
the command performs the same migration in an offline in-memory repository and
prints the parity report.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
    PostgresResearchArtifactRepository,
)
from value_investment_agent.research_runtime_import import (
    VALUATION_POINTERS,
    import_runtime_artifacts,
    resolve_pinned,
    semantic_parity_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root containing the runtime directory",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="disposable/local/test PostgreSQL DSN; production is forbidden",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="stable import run identity",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    run_id = args.run_id or (
        "c3-runtime-import-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )

    postgres = args.dsn is not None
    if postgres:
        repository = PostgresResearchArtifactRepository(args.dsn)
        try:
            repository.migrate()
            result = import_runtime_artifacts(
                repository, root, run_id=run_id
            )
        finally:
            repository.close()
    else:
        repository = InMemoryResearchArtifactRepository()
        result = import_runtime_artifacts(repository, root, run_id=run_id)

    valuations = {
        symbol: resolve_pinned(root, pointer)[0]
        for symbol, pointer in VALUATION_POINTERS.items()
    }
    rows = semantic_parity_report(result, root=root, valuations=valuations)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "backend": "postgresql" if postgres else "in-memory",
                "symbols": list(result.symbols),
                "artifact_count": len(result.stored),
                "all_hashes_matched": result.all_hashes_matched,
                "missing_artifacts": [list(item) for item in result.missing],
                "parity_rows": list(rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

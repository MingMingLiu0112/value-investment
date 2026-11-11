"""Optional local replay inputs; missing originals are not CI evidence."""
import json
from pathlib import Path

import pytest


def require_retained_originals(root, *paths):
    root = Path(root).resolve()
    pending = [Path(path) for path in paths]
    seen = set()

    def references(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"path", "case_path", "bundle_path"} and isinstance(child, str):
                    pending.append(root / child)
                else:
                    references(child)
        elif isinstance(value, list):
            for child in value:
                references(child)

    while pending:
        path = pending.pop().resolve()
        if not path.is_relative_to(root):
            raise ValueError("Retained test source escapes repository")
        if path in seen:
            continue
        seen.add(path)
        if not path.exists():
            pytest.skip("Local retained original absent: " + path.relative_to(root).as_posix())
        if path.is_dir():
            pending.extend(path.rglob("*"))
        elif path.suffix == ".json":
            references(json.loads(path.read_bytes()))

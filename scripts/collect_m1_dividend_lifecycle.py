"""Compatibility entry point for the M1 dividend evidence collector."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cases.collect_m1_dividend_lifecycle import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

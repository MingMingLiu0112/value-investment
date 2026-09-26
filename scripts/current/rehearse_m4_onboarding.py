"""Run the synthetic-only M4 onboarding rehearsal and write its receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.portfolio import (  # noqa: E402
    run_m4_synthetic_onboarding_rehearsal,
)
from value_investment_agent.presentation.read_models.product_workbench import (  # noqa: E402
    product_workbench_from_payload,
)


def _product_read_model_summary(payload: dict) -> dict:
    model = product_workbench_from_payload(payload)
    return {
        "schema_version": model.schema_version,
        "system_health": {
            "code": model.system_health.status.code,
            "label": model.system_health.status.user_label,
        },
        "stages": [
            {
                "key": stage.stage_key,
                "code": stage.status.code,
                "label": stage.status.user_label,
                "detail": stage.detail,
            }
            for stage in model.stage_summaries
        ],
        "portfolio": {
            "real_data_available": model.portfolio.real_data_available,
            "status_code": model.portfolio.status.code,
            "status_label": model.portfolio.status.user_label,
            "summary_count": len(model.portfolio.summary),
            "position_count": len(model.portfolio.positions),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "runtime")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    result = run_m4_synthetic_onboarding_rehearsal(
        args.runtime_root,
        args.run_id,
        product_read_model_mapper=_product_read_model_summary,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

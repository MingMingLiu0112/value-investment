#!/usr/bin/env python3
"""Build one clearly labelled, no-order product-workbench learning preview.

The preview only demonstrates how the Company page explains a research review.
It never contains personal portfolio data, executable instructions, or a claim
that any displayed company is a live recommendation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from scripts.build_m7_daily_workbench import build_packet  # noqa: E402
from value_investment_agent.application.product.product_workbench_candidate import (  # noqa: E402
    build_product_workbench_candidate_payload,
)
from value_investment_agent.presentation.excel.product_workbench import (  # noqa: E402
    write_product_workbench_candidate,
)
from value_investment_agent.presentation.read_models.product_workbench import (  # noqa: E402
    product_workbench_from_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--synthetic-packet", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument(
        "--simulated-user-trial",
        action="store_true",
        help="Required acknowledgement that this is a runtime-only learning preview.",
    )
    return parser.parse_args()


def _review_rows(symbol: str) -> list[dict[str, str]]:
    common = [
        {
            "label": "模拟情景说明",
            "value": "本页为产品体验情景，不是实时研究结论，也不是交易建议。",
        },
        {
            "label": "买入复核前提",
            "value": "证据、估值有效期、当前价格与反证必须同时通过人工复核。",
        },
        {
            "label": "加仓纪律",
            "value": "只有价值判断未被削弱、价格吸引力改善且组合风险允许时，才进入人工加仓复核。",
        },
        {
            "label": "退出或降级条件",
            "value": "核心投资逻辑被证伪、内在价值永久受损或风险显著上升时，重新研究而非机械操作。",
        },
    ]
    if symbol == "600519":
        common.insert(1, {"label": "模拟关注重点", "value": "验证现金回报质量、品牌定价能力与资本配置是否仍支持原始逻辑。"})
    elif symbol == "000333":
        common.insert(1, {"label": "模拟关注重点", "value": "验证经营现金转换、再投资回报与股息覆盖是否同步改善。"})
    else:
        common.insert(1, {"label": "模拟关注重点", "value": "周期盈利必须先做正常化判断，不能用当期低估值或高股息率替代研究。"})
    return common


def main() -> int:
    args = parse_args()
    if not args.simulated_user_trial:
        raise ValueError("refusing preview without --simulated-user-trial")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "runtime"):
        raise ValueError("simulated user trial must remain under runtime/")

    evidence_root = ROOT
    if bool(args.synthetic_packet) != bool(args.evidence_root):
        raise ValueError("--synthetic-packet and --evidence-root must be supplied together")
    if args.synthetic_packet is not None:
        packet_path = args.synthetic_packet.resolve()
        evidence_root = args.evidence_root.resolve()
        if not all(path.is_relative_to(ROOT / "runtime") for path in (packet_path, evidence_root)):
            raise ValueError("synthetic input and evidence root must remain under runtime/")
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        if not isinstance(packet, dict) or packet.get("simulation_only") is not True:
            raise ValueError("synthetic packet must explicitly declare simulation_only=true")
        if packet.get("action") != "no_order":
            raise ValueError("synthetic packet action must remain no_order")
    else:
        packet = build_packet(datetime.now(timezone.utc))
    payload = build_product_workbench_candidate_payload(packet, root=evidence_root)
    payload["system_health"]["message"] = "模拟产品体验：所有结论均待真实证据与人工复核。"
    for company in payload["companies"]:
        company["decision_review"] = _review_rows(company["symbol"])
    model = product_workbench_from_payload(payload)
    receipt = write_product_workbench_candidate(model, output=output, root=ROOT)
    print(receipt["workbook_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

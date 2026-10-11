"""Isolated registered-company runs and append-only comparison, never a scheduler."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .common import load_json_object, require_inside, sha256_file, write_new_json
from .daily_assets import inspect_daily_case_assets


def previous_case_from_run(*, root: Path, case: dict, previous_run: Path | None,
                           symbol: str) -> dict:
    if previous_run is None:
        return case
    folder = require_inside(root / "runtime", previous_run, "previous daily run")
    if not (folder / "receipt.json").is_file():
        batch_path = folder / "batch-receipt.json"
        if batch_path.is_file():
            batch = load_json_object(batch_path, "previous batch receipt")
            if batch.get("action") != "no_order" or batch.get("canonical_workbook_written") is not False:
                raise ValueError("previous batch receipt scope mismatch")
            matching = [row for row in batch.get("cases", []) if row.get("symbol") == symbol]
            if not matching or (len(matching) == 1 and not matching[0].get("receipt")):
                return case
        folder = require_inside(root / "runtime", folder / symbol, "previous company run")
    prior = load_json_object(folder / "receipt.json", "previous daily receipt")
    if (prior.get("symbol") != symbol or prior.get("action") != "no_order"
            or prior.get("canonical_workbook_written") is not False):
        raise ValueError("previous daily receipt identity/scope mismatch")
    bound = prior.get("outputs", {}).get("workbench")
    if bound is None:
        return case
    path = require_inside(folder, root / bound["path"], "previous daily workbench")
    if sha256_file(path) != bound["sha256"]:
        raise ValueError("previous daily workbench hash mismatch")
    return {**case, "previous_workbench": path.relative_to(root).as_posix(),
            "previous_workbench_sha256": bound["sha256"],
            "previous_daily_receipt": (folder / 'receipt.json').relative_to(root).as_posix(),
            "previous_daily_receipt_sha256": sha256_file(folder / 'receipt.json')}


def run_daily_batch(*, root: Path, cases: dict, symbols: list[str], output_dir: Path,
                    run_case: Callable, quote_provider: Callable | None = None,
                    quote_bundle: Path | None = None, agent_mode: str = "offline",
                    previous_run: Path | None = None, report_only: bool = False) -> dict:
    output_dir = require_inside(root / "runtime", output_dir, "daily batch output")
    if output_dir.exists():
        raise FileExistsError("daily batch directory already exists")
    if not symbols or len(set(symbols)) != len(symbols) or any(symbol not in cases for symbol in symbols):
        raise ValueError("daily batch requires distinct registered symbols")
    output_dir.mkdir(parents=True)
    rows = []
    for symbol in symbols:
        try:
            case = previous_case_from_run(root=root, case=cases[symbol],
                                         previous_run=previous_run, symbol=symbol)
            bundle, quote_error = quote_bundle, None
            if quote_provider is not None and not any(row["required_for_research"] for row in
                    inspect_daily_case_assets(root=root, case=case, agent_mode=agent_mode)["blockers"]):
                bundle, quote_error = quote_provider(symbol)
            result = run_case(root=root, symbol=symbol, case=case,
                output_dir=output_dir / symbol, quote_bundle=bundle,
                agent_mode=agent_mode, quote_error=quote_error, report_only=report_only)
            rows.append({"symbol": symbol, "status": result["status"],
                "research_as_of": result.get("research_as_of"),
                "quote_date": result["quote_check"].get("quote_date"),
                "quote_status": result["quote_check"]["status"],
                "recommendation_type": result["recommendation_type"],
                "preview_error": result.get("preview_error"),
                "receipt": {"path": (output_dir / symbol / "receipt.json").relative_to(root).as_posix(),
                            "sha256": sha256_file(output_dir / symbol / "receipt.json")},
                "outputs": result["outputs"], "error": None})
        except (ValueError, OSError, KeyError, TypeError) as error:
            rows.append({"symbol": symbol, "status": "RUN_FAILED", "recommendation_type": "NO_ACTION",
                         "error": f"{type(error).__name__}: {error}", "outputs": {}})
    report = output_dir / "batch-report.md"
    lines = ["# 已注册公司每日研究辅助", "", "本次手动执行；候选建议不是订单。私人仓位未接入。", "",
             "| 公司代码 | 技术运行 | 研究截止 | 行情日期 | 行情状态 | 证券级状态 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(key) or "未形成") for key in
            ("symbol", "status", "research_as_of", "quote_date", "quote_status", "recommendation_type")) + " |")
        if row["error"]:
            lines.extend(["", f"{row['symbol']} 未完成：{row['error']}"])
        elif "report" in row["outputs"]:
            lines.extend(["", f"[{row['symbol']} 的依据、风险与下一触发]({row['symbol']}/report.md)"])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = {"schema_version": "daily-trade-assistant-batch-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
              "action": "no_order", "canonical_workbook_written": False,
              "cases": rows, "failed_case_count": sum(row["status"] == "RUN_FAILED" for row in rows),
              "blocked_asset_count": sum(row["status"] == "BLOCKED_RESEARCH_ASSETS" for row in rows),
              "partial_product_count": sum(bool(row.get("preview_error")) for row in rows),
              "report": {"path": report.relative_to(root).as_posix(), "sha256": sha256_file(report)}}
    write_new_json(output_dir / "batch-receipt.json", result)
    return result

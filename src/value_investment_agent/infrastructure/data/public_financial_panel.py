"""Bulk public disclosure adapter: build a PIT financial panel.

Companion to `pit_extract.py`. That module reads the curated, verified store on
the remote box; this one reads the public bulk endpoints, which have far greater
breadth (every listed company, every statutory period) but no verification and no
`interest_bearing_debt`. Width comes from here, depth from there.

Availability is not decided here — it is delegated to
`domain.pit.availability`, so the rule has exactly one definition and cannot drift
between callers. The same applies to the universe boundary, delegated to
`domain.pit.universe`.

Research-only. Nothing in this module scores, values, sizes or emits an order.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

import pandas as pd

from value_investment_agent.domain.pit import availability, universe

SCHEMA_VERSION = "public-financial-panel-v1"
ACTION_NO_ORDER = "no_order"

# Public bulk endpoints carry no interest-bearing-debt field. The existing
# financial_quality score requires it and explicitly refuses proxy formulas, so
# this absence is recorded on every receipt instead of being papered over.
MISSING_FIELDS: tuple[str, ...] = ("interest_bearing_debt",)

# Chinese column label -> internal name.
_COLUMN_MAP = {
    "股票代码": "symbol",
    "股票简称": "name",
    "净资产收益率": "roe",
    "销售毛利率": "gross_margin",
    "营业总收入-同比增长": "revenue_yoy",
    "净利润-同比增长": "net_income_yoy",
    "每股经营现金流量": "operating_cash_flow_per_share",
    "每股收益": "eps",
    "资产-货币资金": "cash",
    "资产负债率": "debt_ratio",
    "资产-总资产": "total_assets",
    "净利润": "net_income",
    "营业总收入": "revenue",
}

_KEEP: tuple[str, ...] = (
    "symbol", "name", "roe", "gross_margin", "revenue_yoy", "net_income_yoy",
    "operating_cash_flow_per_share", "eps", "cash", "debt_ratio",
    "total_assets", "net_income", "revenue",
)


@dataclass
class PanelBuildResult:
    schema_version: str = SCHEMA_VERSION
    action: str = ACTION_NO_ORDER
    rows: int = 0
    symbols: int = 0
    periods: list[str] = field(default_factory=list)
    dropped_non_a_share: int = 0
    failed_periods: list[str] = field(default_factory=list)
    frame: pd.DataFrame | None = None
    caveats: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "rows": self.rows,
            "symbols": self.symbols,
            "report_periods": self.periods,
            "dropped_non_a_share": self.dropped_non_a_share,
            "failed_periods": self.failed_periods,
            "missing_fields": list(MISSING_FIELDS),
            "availability_rule": (
                "statutory disclosure deadline (conservative: may delay, never advance)"),
            "caveats": list(self.caveats),
        }


def _rename(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns=_COLUMN_MAP)


def _fetch_period(period: str) -> pd.DataFrame | None:
    """One statutory period from the three bulk statement endpoints."""
    import akshare as ak

    yjbb = ak.stock_yjbb_em(date=period)
    zcfz = ak.stock_zcfz_em(date=period)
    lrb = ak.stock_lrb_em(date=period)
    if yjbb is None or zcfz is None or yjbb.empty or zcfz.empty:
        return None

    yjbb, zcfz = _rename(yjbb), _rename(zcfz)
    lrb = _rename(lrb) if lrb is not None else pd.DataFrame(columns=["symbol"])

    for frame in (yjbb, zcfz, lrb):
        missing = [c for c in _KEEP if c not in frame.columns and c in _COLUMN_MAP.values()]
        if missing:
            raise RuntimeError(f"{period}: upstream schema drift, missing {missing}")

    yjbb = yjbb[[c for c in _KEEP if c in yjbb.columns]].copy()
    zcfz = zcfz[[c for c in _KEEP if c in zcfz.columns]].copy()
    lrb = lrb[[c for c in _KEEP if c in lrb.columns]].copy()

    merged = yjbb.merge(zcfz, on="symbol", how="left").merge(lrb, on="symbol", how="left")
    year, month, day = availability.split_period(period)
    merged["report_period"] = f"{year:04d}-{month:02d}-{day:02d}"
    merged["available_at"] = availability.available_at(period).isoformat()
    return merged


def build(start_year: int, end_year: int, annual_only: bool = False,
          as_of: date | None = None,
          progress: Callable[[str], None] | None = None) -> PanelBuildResult:
    """Fetch every publicly-available statutory period into one tidy panel.

    Fails closed on a total fetch failure: a partial sample that looks complete is
    more dangerous than no sample, because it will be backtested.
    """
    periods = availability.report_periods(start_year, end_year, as_of=as_of,
                                          annual_only=annual_only)
    emit = progress or (lambda _msg: None)
    emit(f"报告期 {len(periods)} 个: {periods[0]} .. {periods[-1]}" if periods else "无可用报告期")

    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    kept_by_period: list[int] = []
    for index, period in enumerate(periods, start=1):
        started = time.time()
        try:
            frame = _fetch_period(period)
        except Exception as error:  # network, or upstream schema drift
            failed.append(period)
            emit(f"  [{index}/{len(periods)}] {period} 失败: {type(error).__name__}: {error}")
            continue
        if frame is None:
            failed.append(period)
            emit(f"  [{index}/{len(periods)}] {period} 空响应")
            continue
        before = len(frame)
        frame = frame[frame["symbol"].astype(str).str[:3].isin(universe.A_SHARE_PREFIXES)].copy()
        emit(f"  [{index}/{len(periods)}] {period} -> {len(frame)} 行 "
             f"(剔除 {before - len(frame)}) ({time.time() - started:.1f}s)")
        kept_by_period.append(len(frame))
        frames.append(frame)

    if not frames:
        raise RuntimeError(
            f"no report period fetched ({len(failed)} failed); aborting (fail-closed)")

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.drop_duplicates(subset=["symbol", "report_period"], keep="last")
    panel = panel.sort_values(["symbol", "report_period"]).reset_index(drop=True)

    return PanelBuildResult(
        rows=int(len(panel)),
        symbols=int(panel["symbol"].nunique()),
        periods=sorted(panel["report_period"].unique().tolist()),
        dropped_non_a_share=0,
        failed_periods=failed,
        frame=panel,
        caveats=(
            "Availability uses the statutory deadline, not the real announcement "
            "date; this delays signals and cannot create look-ahead.",
            f"{', '.join(MISSING_FIELDS)} is unavailable from bulk endpoints; the "
            "cash-flow pillar must be computed without it or sourced from the store.",
            "Currency is CNY as reported; no restatement history is retained, so a "
            "restated figure overwrites the original rather than being versioned.",
            "Interim ROE is as-reported and is not annualised.",
        ),
    )


def write_csv(result: PanelBuildResult, out_path) -> None:
    """CSV rather than parquet: no binary engine is available, and adding one is a
    supply-chain cost a research probe does not justify."""
    from pathlib import Path

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if result.frame is None:
        raise ValueError("nothing to write: build produced no frame")
    result.frame.to_csv(out_path, index=False, encoding="utf-8")

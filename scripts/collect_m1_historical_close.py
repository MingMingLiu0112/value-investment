"""Archive the latest completed M1 session from two daily-bar providers."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m1_historical_quote import (  # noqa: E402
    SCHEMA_VERSION,
    TOLERANCE,
    latest_completed_szse_session,
    sohu_daily_bar,
    szse_calendar_day,
    tencent_daily_bar,
)


SZSE_CALENDAR_URL = (
    "https://www.szse.cn/api/report/exchange/onepersistenthour/monthList"
)
TENCENT_DAILY_URL = (
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
)
SOHU_DAILY_URL = "https://q.stock.sohu.com/hisHq"


def _fetch(session: requests.Session, url: str, *, params=None, headers=None) -> bytes:
    response = session.get(
        url,
        params=params,
        headers=headers,
        timeout=(10, 30),
    )
    response.raise_for_status()
    return response.content, response.url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="000651")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not re.fullmatch(r"[0-9]{6}", args.symbol):
        parser.error("symbol must contain six digits")
    if not args.symbol.startswith(("0", "3")):
        parser.error("this collector currently supports SZSE symbols only")

    root = args.root.resolve()
    with requests.Session() as session:
        session.trust_env = False
        calendar_raw, calendar_url = _fetch(
            session,
            SZSE_CALENDAR_URL,
            params={"month": datetime.now(timezone.utc).strftime("%Y-%m")},
            headers={"Referer": "https://www.szse.cn/"},
        )
        target_date, calendar_now = latest_completed_szse_session(calendar_raw)
        tencent_key = "sz" + args.symbol
        tencent_raw, tencent_url = _fetch(
            session,
            TENCENT_DAILY_URL,
            params={
                "param": (
                    f"{tencent_key},day,"
                    f"{(target_date - timedelta(days=45)).strftime('%Y-%m-%d')},"
                    f"{(target_date + timedelta(days=1)).strftime('%Y-%m-%d')},"
                    "640,"
                )
            },
        )
        sohu_raw, sohu_url = _fetch(
            session,
            SOHU_DAILY_URL,
            params={
                "code": f"cn_{args.symbol}",
                "start": (target_date - timedelta(days=45)).strftime("%Y%m%d"),
                "end": (target_date + timedelta(days=1)).strftime("%Y%m%d"),
            },
        )

    tencent = tencent_daily_bar(tencent_raw, args.symbol, target_date)
    sohu = sohu_daily_bar(sohu_raw, args.symbol, target_date)
    calendar = szse_calendar_day(calendar_raw, target_date)
    tencent_close = Decimal(tencent["close"])
    sohu_close = Decimal(sohu["close"])
    if abs(tencent_close - sohu_close) > TOLERANCE:
        raise ValueError(
            f"Provider close conflict: Tencent={tencent_close}, "
            f"Sohu={sohu_close}"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = root / "runtime" / "m1-historical-quote-crosscheck" / stamp
    target.mkdir(parents=True, exist_ok=False)
    files = {
        "tencent": "tencent-daily.json",
        "sohu": "sohu-daily.json",
        "szse_calendar": "szse-calendar.json",
    }
    raw_values = {
        "tencent": tencent_raw,
        "sohu": sohu_raw,
        "szse_calendar": calendar_raw,
    }
    final_urls = {
        "tencent": tencent_url,
        "sohu": sohu_url,
        "szse_calendar": calendar_url,
    }
    documents = {}
    fetched_at = datetime.now(timezone.utc).isoformat()
    for provider, filename in files.items():
        path = target / filename
        path.write_bytes(raw_values[provider])
        documents[provider] = {
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(raw_values[provider]).hexdigest(),
            "source_url": final_urls[provider],
            "fetched_at": fetched_at,
        }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": fetched_at,
        "action": "no_order",
        "symbol": args.symbol,
        "quote_date": target_date.isoformat(),
        "verified_close": tencent["close"],
        "tencent_close": tencent["close"],
        "sohu_close": sohu["close"],
        "tolerance": str(TOLERANCE),
        "calendar_now_date": calendar["calendar_now_date"],
        "selection_rule": (
            "latest official SZSE trading day strictly before calendar nowdate"
        ),
        "provider_documents": documents,
        "backtest_ready": False,
    }
    manifest_path = target / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result = {
        **manifest,
        "manifest_path": str(manifest_path.relative_to(root)),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "latest_completed_session": target_date.isoformat(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

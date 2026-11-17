"""Replay reviewed distribution and financing constraints for D2 citation."""

from datetime import datetime, date
from decimal import Decimal
import re
from hashlib import sha256
import json
from pathlib import Path

from ...product.common import require_inside
from ....infrastructure.filings.native_capital_observation_v1 import _compact
from ....infrastructure.filings.pdf_text import extract_pages


def _bound_path(root, relative, digest):
    path = require_inside(root / "runtime", root / relative, "cash constraint source")
    if sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("CASH_CONSTRAINT_HASH_CHANGED")
    return path


def replay_parent_cash_constraint_evidence(*, root, binding, symbol, now):
    root = Path(root).resolve()
    document = _bound_path(root, binding["path"], binding["sha256"])
    facts = json.loads(document.read_bytes())
    if (facts["symbol"] != symbol or facts["action"] != "no_order"
            or facts["classification"] != "HISTORICAL_CONSTRAINT_EVIDENCE"
            or facts["actual_settlement_verified"] is not False
            or facts["forecast_commitment_cny"] is not None or now.utcoffset() is None):
        raise ValueError("CASH_CONSTRAINT_SCOPE_INVALID")

    rows = []
    reserve = facts["legal_reserve"]
    if reserve["future_appropriation"] is not None:
        raise ValueError("CASH_CONSTRAINT_FUTURE_VALUE_NOT_ALLOWED")
    fy_path = _bound_path(root, reserve["fy_pdf"], reserve["fy_pdf_sha256"])
    fy_page = _compact(extract_pages(fy_path)[reserve["fy_page"] - 1])
    reported = f"{Decimal(reserve['reported_cny']):,.2f}"
    if f"法定盈余公积{reported}" not in fy_page:
        raise ValueError("CASH_CONSTRAINT_RESERVE_ROW_CHANGED")
    for key, scope in (("charter", "ISSUER_ARTICLES_RULE_TEXT"),
                       ("financing_source", "ISSUER_FINANCING_DISCLOSURE")):
        source = facts[key]
        available = datetime.fromisoformat(source["available_at"])
        if available.utcoffset() is None or available > now:
            raise ValueError("CASH_CONSTRAINT_SOURCE_NOT_AVAILABLE")
        pages = extract_pages(_bound_path(root, source["path"], source["sha256"]))
        source_id = "cninfo:" + source["url"].rsplit("/", 1)[-1].removesuffix(".PDF")
        if key == "charter":
            page = reserve["rule_page"]
            if "累计额为公司注册资本的百分之五十以上的,可以不再提取" not in _compact(pages[page - 1]):
                raise ValueError("CASH_CONSTRAINT_CHARTER_ROW_CHANGED")
            entries = [("statutory_reserve_rule", page,
                f"母公司分配约束：法定盈余公积实报 {reserve['reported_cny']} 元，章程阈值 "
                f"{reserve['threshold_cny']} 元。前者来自已核验年报第 {reserve['fy_page']} 页。"
                "本资料用于研究未来计提的条件，不证明将来实际提取金额。", "2025-12-31")]
        else:
            entries = []
            for item in facts["issuer_financing"]:
                page = item["physical_page"]
                text = _compact(pages[page - 1])
                maturity = date.fromisoformat(item["maturity"])
                amount = Decimal(item["principal_cny"]) / Decimal("100000000")
                locator = (
                    rf"代码{re.escape(item['code'])}期限\d+天起息日2026年10月12日"
                    rf"兑付日{maturity.year}年{maturity.month}月{maturity.day}日"
                    rf"计划发行总额\d+亿元实际发行总额{amount:f}亿元"
                )
                if len(re.findall(locator, text)) != 1:
                    raise ValueError("CASH_CONSTRAINT_FINANCING_ROW_CHANGED")
                entries.append((item["code"], page,
                    f"母公司发行融资券 {item['code']}，本金 {item['principal_cny']} 元，"
                    f"公告到期日 {item['maturity']}。实际兑付与续借未核验。", "2026-10-12"))
        for identifier, page, text, period in entries:
            rows.append(dict(id=f"{source_id}:{identifier}", source_id=source_id,
                available_at=available.isoformat(), pdf_sha256=source["sha256"],
                physical_page=page, scope=scope, unit="TEXT", period=period,
                text=text, text_sha256=sha256(text.encode("utf-8")).hexdigest(),
                kind="REPORTED_HISTORICAL_FACT_NOT_FORECAST"))
    return rows

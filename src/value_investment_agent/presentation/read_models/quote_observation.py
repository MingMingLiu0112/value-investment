"""Surface a verified retained close without changing valuation or decision gates."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ...quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE
from .product_workbench import EvidenceRecord, StatusView, TodayItem


CHINA_TIME = timezone(timedelta(hours=8))


def project_quote_observation(model, quote, *, path: str, sha256: str,
                              captured_at: datetime, generated_at: datetime):
    if (captured_at.utcoffset() is None or generated_at.utcoffset() is None
            or captured_at > generated_at or model.generated_at > generated_at):
        raise ValueError("quote observation timestamps are not ordered")
    display_date = generated_at.astimezone(CHINA_TIME).date()
    capture_date = captured_at.astimezone(CHINA_TIME).date()
    if (quote.status != QUOTE_STATUS_VERIFIED_CLOSE
            or quote.quote_date > capture_date or model.as_of > display_date):
        raise ValueError("quote observation requires a verified close within the display cutoff")
    cards = [card for card in model.companies if card.symbol == quote.symbol]
    if len(cards) != 1:
        raise ValueError("quote observation requires one existing company")
    card = cards[0]
    label = "已核验收盘行情（未桥接估值）"
    if label in dict(card.decision_review):
        raise ValueError("quote observation already exists")
    identity = f"{quote.symbol}-quote-observation-{sha256[:12]}"
    if any(record.evidence_id == identity for record in model.audit_evidence):
        raise ValueError("quote observation evidence already exists")
    record = EvidenceRecord(identity, "封存双源收盘行情", "quote_session",
                            path, sha256, capture_date)
    sources = [ref for ref in quote.evidence_refs if ref.get("kind") == "quote_provider_document"]
    if {ref.get("provider") for ref in sources} != {"tencent", "sina"}:
        raise ValueError("quote observation requires two provider documents")
    source_text = "；".join(f"{ref['provider']} {ref['source_url']} SHA-256 {ref['sha256']}"
                           for ref in sources)
    detail = (f"{quote.quote_date.isoformat()} 双源核验收盘价 {quote.current_price} 元；"
              f"本次采集 {captured_at.astimezone(CHINA_TIME).isoformat()}；"
              f"原始来源：{source_text}。这只是报价观察；模型有效性、公告覆盖与"
              "价格相对内在价值的判断未获准入。")
    updated = replace(card,
        decision_review=(*card.decision_review, (label, detail)),
        evidence_refs=tuple(dict.fromkeys((*card.evidence_refs, identity))))
    today = TodayItem(StatusView("MARKET_DATA", "行情"), card.company_name,
        f"{quote.quote_date.isoformat()} 双源核验收盘价 {quote.current_price} 元；"
        f"{capture_date.isoformat()} 取得归档。",
        f"原研究展示截止 {model.as_of.isoformat()}；报价不改变内在价值，"
        "也不代表研究或价格桥接已完成。",
        "仅行情已核验；买卖状态仍待研究、事件、模型和价格桥接复核。",
        "核验公告覆盖与模型有效性后，再由独立价格桥接评估；不得据此下单。",
        (identity,), card.symbol)
    return replace(model,
        generated_at=generated_at, as_of=display_date,
        companies=tuple(updated if item.symbol == card.symbol else item for item in model.companies),
        today_items=(*model.today_items, today),
        audit_evidence=(*model.audit_evidence, record))

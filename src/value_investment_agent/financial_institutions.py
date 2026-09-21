"""Conservative classification and gates for financial-institution research.

This module deliberately identifies only obvious issuer-name patterns.  The
classification is provisional until a reviewer confirms the issuer's official
industry and the specialised evidence set required for its model.
"""

from __future__ import annotations


FINANCIAL_KEYWORDS = {
    "bank": ("银行",),
    "insurer": ("保险", "中国人寿", "中国太保", "中国平安", "中国人保"),
    "broker": ("证券",),
}


def provisional_financial_type(name: str | None, sector: str | None) -> str | None:
    """Return a conservative provisional type, never an authoritative sector."""
    searchable = f"{name or ''} {sector or ''}"
    for institution_type, keywords in FINANCIAL_KEYWORDS.items():
        if any(keyword in searchable for keyword in keywords):
            return institution_type
    if sector and any(label in sector for label in ('非银金融', '多元金融')):
        return 'financial_group'
    return None


def financial_gate_message(institution_type: str) -> tuple[str, str]:
    labels = {"bank": "银行", "insurer": "保险", "broker": "证券公司", "financial_group": "金融控股/多元金融"}
    label = labels[institution_type]
    return (
        f"{label}专用模型待核验",
        f"名称/板块初步识别为{label}；须以同一报告期官方披露复核专用指标和行业分类，禁止套用通用企业现金流、负债率或 EV/EBITDA 规则。",
    )

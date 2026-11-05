"""Reverify already archived official notices behind retrospective fee rates."""
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser
import json
from pathlib import Path, PureWindowsPath
import re
import unicodedata

from ..evidence.historical_price_correspondence import require_inside, sha256_file
from ...historical_fees import SOURCES, CURRENT_SSE_EVIDENCE, statutory_components, VERSION


ARCHIVE = "runtime/trading-rule-evidence/20260908T115226080339Z"
# Inherit the originals already reviewed by historical_fees and its frozen doc.
DIGESTS = {
    "stamp-2008": "4edaa053cbc7c2727e183a27f2e974aabb3534e4485522e3675f40ca7a6d8263",
    "stamp-2023": CURRENT_SSE_EVIDENCE["stamp-2023"][1],
    "transfer-2022": CURRENT_SSE_EVIDENCE["transfer-2022"][1],
}
CLAUSES = {
    "stamp-2008": ("2008年9月19日起", "出让方按千分之一的税率", "对受让方不再征税"),
    "stamp-2023": ("公告2023年第39号", "自2023年8月28日起", "证券交易印花税实施减半征收"),
    "transfer-2022": ("2022年4月29日起", "股票交易过户费", "按照成交金额0.01‰双向收取"),
}


class _NoticeText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _clauses(source_id, raw):
    parser = _NoticeText()
    parser.feed(raw.decode("utf-8"))
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", "".join(parser.parts)))
    if any(token not in text for token in CLAUSES[source_id]):
        raise ValueError("Official notice clauses missing: " + source_id)


def inspect_statutory_fee_evidence(*, root: Path, now: datetime) -> dict:
    """This proves notice correspondence, never complete fee-policy continuity.

    Reuse the historical component arithmetic within its existing 2015-2025
    scope. Do not extend that module's reviewed-session or historical contract.
    Local acquisition metadata is not independent historical PIT attestation.
    """
    if now.utcoffset() is None:
        raise ValueError("Aware fee-evidence cutoff required")
    result = dict(schema_version="hotspot-statutory-fee-originals-v1", source_status="MISSING",
        action="no_order", source_bindings=[], source_available_at=None, published_components=None,
        arithmetic_probes=[], complete_policy_continuity=False, historical_availability_proven=False,
        broker_invoice_verified=False, full_cost_verified=False,
        scope="RETAINED_OFFICIAL_NOTICE_COMPONENTS_NOT_FULL_EXECUTABLE_COST",
        arithmetic_version=VERSION)
    root = root.resolve()
    try:
        manifest_path = require_inside(root, root / ARCHIVE / "manifest.json", "fee archive manifest")
        if not manifest_path.is_file():
            return result
        if not 0 < manifest_path.stat().st_size <= 128 * 1024:
            raise ValueError("Fee manifest exceeds bounds")
        manifest_hash = sha256_file(manifest_path)
        rows = json.loads(manifest_path.read_bytes())
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Fee manifest requires source records")
        selected, stamps, bindings = {}, [], [dict(path=f"{ARCHIVE}/manifest.json", sha256=manifest_hash)]
        for source_id, expected in DIGESTS.items():
            matches = [row for row in rows if row.get("source_id") == source_id]
            if len(matches) != 1:
                raise ValueError("Unique official fee source required: " + source_id)
            row = matches[0]
            relative = PureWindowsPath(row["path"])
            available = datetime.fromisoformat(row["fetched_at"])
            if (relative.drive or relative.is_absolute() or relative.as_posix() != f"{ARCHIVE}/{source_id}.html"
                    or row["requested_url"] != SOURCES[source_id] or row["final_url"] != SOURCES[source_id]
                    or row["sha256"] != expected or available.utcoffset() is None or available > now):
                raise ValueError("Official fee source identity/acquisition mismatch")
            path = require_inside(root, root.joinpath(*relative.parts), "fee source original")
            if not 0 < path.stat().st_size <= 1024 * 1024 or sha256_file(path) != expected:
                raise ValueError("Official fee original hash/size mismatch")
            _clauses(source_id, path.read_bytes())
            selected[source_id] = dict(source_id=source_id, path=relative.as_posix(), sha256=expected,
                url=SOURCES[source_id], available_at=available.isoformat())
            stamps.append(available)
            bindings.append(selected[source_id])
        # Existing date-aware component engine; these are arithmetic probes,
        # not real trades, personal invoices, or the 2026 strategy's OOS fills.
        probes = []
        for day, side in ((date(2023, 8, 25), "sell"), (date(2023, 8, 28), "sell"),
                          (date(2023, 8, 28), "buy")):
            components = statutory_components(day, "SSE", side, Decimal("100000"))
            probes.append({key: str(value) if isinstance(value, Decimal) else value
                           for key, value in components.items()})
        if any(sha256_file(require_inside(root, root / ref["path"], "fee source")) != ref["sha256"]
               for ref in bindings):
            raise ValueError("Fee original changed during read")
        result.update(source_status="VERIFIED_RETAINED_OFFICIAL_NOTICES", source_bindings=bindings,
            source_available_at=max(stamps).isoformat(), arithmetic_probes=probes,
            published_components=dict(sell_stamp_rate=probes[1]["stamp_rate"],
                buy_stamp_rate=probes[2]["stamp_rate"], transfer_rate=probes[1]["transfer_rate"],
                stamp_effective_from="2023-08-28", transfer_effective_from="2022-04-29",
                transfer_sides=["buy", "sell"], markets=["SSE", "SZSE"],
                security_scope="ORDINARY_A_SHARE_AUCTION_ONLY"))
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        result.update(source_status="INVALID_OR_UNAVAILABLE", diagnostic=str(error))
    return result

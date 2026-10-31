"""Replay exchange-list originals behind an existing public publication binding."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import parse_qs, urlsplit
from io import BytesIO
from html.parser import HTMLParser

from ...official_universe import VERSION, parse_szse, parse_sse
from ...domain.portfolio.security_attributes import moment, official_observation, auction_buy_rule


QUANTITY_SOURCES = {
    "SSE_QUANTITY": "https://english.sse.com.cn/start/trading/mechanism/",
    "SZSE_QUANTITY_2026": "https://www.szse.cn/English/rules/siteRule/P020260708406221548360.pdf",
}
QUANTITY_DIRECTORY = "runtime/trading-rule-evidence/security-quantity-v1"
# Inspected originals captured 2026-10-16 Asia/Shanghai. Changed bytes require review.
QUANTITY_DIGESTS = {
    "SSE_QUANTITY": "debd61a1b48157e8f3ddfaa1fcd851c108dd399f513fee16397e2e15d14e7843",
    "SZSE_QUANTITY_2026": "9361881e506748a78fde5bffd2a8aa04ad6939b32c6af0101693708efa8e47c8",
}


class _RuleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def validate_quantity_original(source_id, raw):
    """Admit only the inspected quantity clauses; no price-limit or liquidity claims."""
    if source_id == "SZSE_QUANTITY_2026":
        from pypdf import PdfReader
        if not raw.startswith(b"%PDF-"):
            raise ValueError("Quantity rule original is not PDF")
        pages = PdfReader(BytesIO(raw)).pages
        text = "".join(page.extract_text() for page in pages)
        tokens = ("2026 Revision", "3.3.8", "multiplesof100shares(units)",
            "maximumordersizeis1,000,000shares(units)",
            "300,000sharesforalimitorder", "takeeffectonJuly6,2026")
    elif source_id == "SSE_QUANTITY":
        parser = _RuleText()
        parser.feed(raw.decode("utf-8"))
        text = " ".join(parser.parts)
        tokens = ("For the Main Board", "each order shall be in multiples of 100 shares",
            "shall not exceed 1 million shares", "For STAR Market",
            "no less than 200 shares and no more than 100,000 shares")
    else:
        raise ValueError("Unsupported quantity rule source")
    compact = "".join(text.split())
    if any("".join(token.split()) not in compact for token in tokens):
        raise ValueError("Official quantity clauses changed or are unavailable")


def capture_quantity_originals(root):
    """Explicit bounded acquisition, never invoked by a private read or preview."""
    import requests
    import shutil
    from datetime import datetime, timezone
    root = Path(root).resolve()
    directory = root / QUANTITY_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    receipts = []
    with requests.Session() as session:
        session.trust_env = False
        for source_id, url in QUANTITY_SOURCES.items():
            # One request per original, with no redirects or retry loops.
            with session.get(url, timeout=(10, 25), stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                if response.url != url or response.status_code != 200:
                    raise ValueError("Unexpected quantity source response")
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > 5 * 1024**2:
                        raise ValueError("Quantity rule exceeds archive budget")
            raw = bytes(raw)
            validate_quantity_original(source_id, raw)
            digest = hashlib.sha256(raw).hexdigest()
            if digest != QUANTITY_DIGESTS[source_id]:
                raise ValueError("Changed official quantity original requires review")
            path = directory / (digest + ".bin")
            if shutil.disk_usage(directory).free - len(raw) < 2 * 1024**3:
                raise OSError("Preserve 2 GiB disk reserve")
            if not path.exists():
                path.write_bytes(raw)
            elif path.read_bytes() != raw:
                raise ValueError("Retained quantity original changed")
            receipt = {"id": source_id, "source_url": url, "path": path.relative_to(root).as_posix(),
                "sha256": digest, "known_at": datetime.now(timezone.utc).isoformat(),
                "published_at": None, "source_role": "OFFICIAL_QUANTITY_RULE"}
            target = directory / (source_id + ".json")
            temporary = target.with_suffix(".part")
            temporary.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
            temporary.replace(target)
            receipts.append(receipt)
    return receipts


def verified_quantity_rule(root, attribute, *, now):
    rule = auction_buy_rule(attribute)
    if rule is None:
        return None
    root = Path(root).resolve()
    try:
        receipt = json.loads((root / QUANTITY_DIRECTORY / (rule["source_id"] + ".json")).read_text(encoding="utf-8"))
        if (receipt["id"] != rule["source_id"]
                or receipt["source_url"] != QUANTITY_SOURCES[rule["source_id"]]
                or receipt["sha256"] != QUANTITY_DIGESTS[rule["source_id"]]):
            raise ValueError("Quantity source identity changed")
        path, raw = _original(root, {"local_path": receipt["path"], "sha256": receipt["sha256"]})
        validate_quantity_original(rule["source_id"], raw)
        acquired = moment(receipt["known_at"])
        known = max(moment(attribute["known_at"]), acquired)
        expiry = min(moment(attribute["valid_until"]), moment(receipt["known_at"]) + timedelta(days=7))
        if not known <= now <= expiry:
            return None
        if rule["source_id"] == "SZSE_QUANTITY_2026" and now.date().isoformat() < "2026-07-06":
            return None
        return {**rule, "symbol": attribute["symbol"], "exchange": attribute["exchange"],
            "board": attribute["board"], "security_type": attribute["security_type"],
            "known_at": known.isoformat(), "valid_until": expiry.isoformat(),
            "evidence_refs": [*attribute["evidence_refs"], receipt],
            "source_language": "OFFICIAL_ENGLISH_REFERENCE_CHINESE_TEXT_CONTROLS",
            "historical_pit": False, "action": "no_order"}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _original(root, source):
    name = source["local_path"].replace("\\", "/")
    path = Path(name)
    if PureWindowsPath(name).is_absolute() or path.is_absolute():
        # Rebase retained legacy absolute references only by their explicit
        # runtime suffix; the bound digest still authenticates restored bytes.
        parts = name.split("/")
        if "runtime" not in parts:
            raise ValueError("Official original has no repository runtime identity")
        path = Path(*parts[parts.index("runtime"):])
    if ".." in path.parts:
        raise ValueError("Official original traverses outside runtime")
    path = (root / path).resolve()
    if not path.is_relative_to((root / "runtime").resolve()):
        raise ValueError("Official original outside runtime")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("Official original changed")
    return path, raw


def _source_kind(source):
    endpoints = {"SZSE_A": ("www.szse.cn", "/api/report/ShowReport"),
        "SSE_1": ("query.sse.com.cn", "/sseQuery/commonQuery.do"),
        "SSE_8": ("query.sse.com.cn", "/sseQuery/commonQuery.do")}
    label = source["label"]
    if label not in endpoints:
        raise ValueError("Unsupported exchange source")
    for key in ("url", "request_url"):
        url = urlsplit(source[key])
        if url.scheme != "https" or (url.hostname, url.path) != endpoints[label] or url.username or url.password:
            raise ValueError("Source is not the official security-list endpoint")
        query = parse_qs(url.query)
        if label == "SZSE_A":
            if any(query.get(k) != [v] for k, v in {"SHOWTYPE": "xlsx", "CATALOGID": "1110", "TABKEY": "tab1"}.items()):
                raise ValueError("Wrong SZSE list scope")
        elif query.get("STOCK_TYPE") != [label[-1]] or query.get("sqlId") != ["COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L"]:
            raise ValueError("Wrong SSE list scope")
    return label


def replay_official_attributes(root, universe, universe_binding, symbols, *, now):
    root = Path(root).resolve()
    if universe.get("parser_version") != VERSION or universe.get("complete") is not True:
        raise ValueError("Unverified official universe contract")
    completed = moment(universe["fetched_at"])
    if completed > now:
        raise ValueError("Official universe is not known yet")
    retained = {r["symbol"]: r for r in universe["records"]}
    if len(retained) != len(universe["records"]):
        raise ValueError("Duplicate retained identity")
    result, seen = [], set()
    for source in universe["sources"]:
        if source["label"] not in ("SZSE_A", "SSE_1", "SSE_8"):
            continue
        label = _source_kind(source)
        fetched = moment(source["fetched_at"])
        if fetched > completed:
            raise ValueError("Universe available before its originals")
        path, raw = _original(root, source)
        records = parse_szse(raw) if label == "SZSE_A" else parse_sse(raw, "\u4e3b\u677f" if label == "SSE_1" else "\u79d1\u521b\u677f")
        codes = ({r["A_STOCK_CODE"]: r.get("CSRC_CODE") for r in json.loads(raw)["result"]} if label != "SZSE_A" else {})
        for row in records:
            if row["symbol"] in seen:
                raise ValueError("Duplicate official source identity")
            seen.add(row["symbol"])
            if row["symbol"] not in symbols:
                continue
            if row != retained.get(row["symbol"]):
                raise ValueError("Normalized official identity differs from original")
            known = max(completed, fetched)
            expiry = fetched + timedelta(days=7)
            if now > expiry:
                continue
            code = codes.get(row["symbol"])
            if label == "SZSE_A":
                match = re.match(r"^([A-S])(?:\s|$)", row.get("official_industry") or "")
                code = match[1] if match else None
            if code is not None and not re.fullmatch(r"[A-S]", code):
                code = None
            refs = [{"id": source["sha256"], "path": path.relative_to(root).as_posix(),
                "sha256": source["sha256"], "source_url": source["url"], "known_at": fetched.isoformat(),
                "source_role": label, "published_at": None},
                {"id": universe_binding["sha256"], **universe_binding, "source_role": "PUBLISHED_OFFICIAL_UNIVERSE"}]
            observation = official_observation(row, industry_code=code, known_at=known, valid_until=expiry, evidence_refs=refs)
            observation["trading_rules"] = verified_quantity_rule(root, observation, now=now)
            result.append(observation)
    return result

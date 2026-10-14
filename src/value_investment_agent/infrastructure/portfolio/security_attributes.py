"""Replay exchange-list originals behind an existing public publication binding."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import parse_qs, urlsplit

from ...official_universe import VERSION, parse_szse, parse_sse
from ...domain.portfolio.security_attributes import moment, official_observation


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
            result.append(official_observation(row, industry_code=code, known_at=known, valid_until=expiry, evidence_refs=refs))
    return result

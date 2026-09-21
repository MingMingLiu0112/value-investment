#!/usr/bin/env python3
"""Archive the SSE closure-notice index before adding an SSE session rule.

The existing quote-session gate deliberately supports only the SZSE machine
calendar.  This probe is read-only: it retains the official SSE index page,
records its hash, and lists only links whose visible text mentions 2026.  A
later parser must pin one returned notice and prove its calendar semantics;
an index hit alone never opens a trading-session gate.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
INDEX_URL = "https://www.sse.com.cn/disclosure/dealinstruc/closed/"


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._parts: list[str] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            title = " ".join("".join(self._parts).split())
            if title:
                self.links.append({"href": self._href, "title": title})
            self._href = None
            self._parts = []


def main() -> int:
    fetched_at = datetime.now(timezone.utc)
    output = ROOT / "runtime" / "exchange-calendar-probes" / f"sse-index-{fetched_at:%Y%m%dT%H%M%SZ}"
    output.mkdir(parents=True, exist_ok=False)
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(
            INDEX_URL,
            headers={"Referer": "https://www.sse.com.cn/", "User-Agent": "value-investment-agent/1.0"},
            timeout=(10, 20),
        )
        response.raise_for_status()
        raw = response.content
    raw_path = output / "sse-closure-index.html"
    raw_path.write_bytes(raw)
    parser = LinkCollector()
    parser.feed(raw.decode("utf-8", errors="replace"))
    candidates = [item for item in parser.links if "2026" in item["title"] or "2026" in item["href"]]
    evidence = {
        "scope": "SSE official closure-notice index discovery only; not a trading calendar or session approval.",
        "source_url": response.url,
        "fetched_at": fetched_at.isoformat(),
        "http_status": response.status_code,
        "raw_file": raw_path.name,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "candidate_links": candidates,
        "candidate_count": len(candidates),
        "session_approved": False,
    }
    evidence_path = output / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "candidate_count": len(candidates)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

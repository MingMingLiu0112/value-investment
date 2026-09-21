#!/usr/bin/env python3
"""Archive the official SSE 2026 closure notice for later semantic review.

This command intentionally does not infer a calendar.  It retains the notice
HTML and extracts its visible text, so a session rule can be tested against
the exact official wording rather than a hand-copied holiday list.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
NOTICE_URL = "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml"


class TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def main() -> int:
    fetched_at = datetime.now(timezone.utc)
    output = ROOT / "runtime" / "exchange-calendar-probes" / f"sse-2026-closure-notice-{fetched_at:%Y%m%dT%H%M%SZ}"
    output.mkdir(parents=True, exist_ok=False)
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(
            NOTICE_URL,
            headers={"Referer": "https://www.sse.com.cn/disclosure/dealinstruc/closed/", "User-Agent": "value-investment-agent/1.0"},
            timeout=(10, 20),
        )
        response.raise_for_status()
        raw = response.content
    raw_path = output / "sse-2026-closure-notice.html"
    raw_path.write_bytes(raw)
    parser = TextCollector()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = "\n".join(parser.parts)
    text_path = output / "visible-text.txt"
    text_path.write_text(text + "\n", encoding="utf-8")
    evidence = {
        "scope": "Official SSE 2026 closure notice archive; calendar semantics not inferred by this command.",
        "source_url": response.url,
        "fetched_at": fetched_at.isoformat(),
        "http_status": response.status_code,
        "raw_file": raw_path.name,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "visible_text_file": text_path.name,
        "visible_text_sha256": hashlib.sha256(text_path.read_bytes()).hexdigest(),
        "session_approved": False,
    }
    evidence_path = output / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "raw_sha256": evidence["raw_sha256"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Archive primary current-fee references; never infer admission from download success."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "sse-investor-guide": ("https://one.sse.com.cn/onething/gptz/",
                           ("0.5", "0.01", "包含在券商交易佣金中")),
    "stamp-2023": ("https://www.mof.gov.cn/jrttts/202308/t20230828_3904235.htm",
                   ("2023年8月28日", "减半征收")),
    "transfer-2022": ("https://www.chinaclear.cn/zdjs/gszb/202204/837e3c5031104aa099d6597ba381342a.shtml",
                      ("2022年4月29日", "0.01")),
}


def main():
    now = datetime.now(timezone.utc)
    output = ROOT / "runtime/trading-rule-evidence" / ("current-fees-" + now.strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for key, (url, required) in SOURCES.items():
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        raw = response.content
        html = output / (key + ".html")
        html.write_bytes(raw)
        text = "".join(BeautifulSoup(raw, "html.parser").get_text("", strip=True).split())
        if any(token not in text for token in required):
            raise ValueError(f"Expected source content missing in {key}; raw response retained")
        records.append({"source_id": key, "url": url, "response_url": response.url,
                        "path": str(html.relative_to(ROOT)),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "required_text_checks": list(required)})
    manifest = {"sources": records, "created_at": now.isoformat(),
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "scope": "Primary-source capture, not broker fee verification or trading admission"}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "sources": records}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

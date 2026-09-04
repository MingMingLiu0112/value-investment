from pathlib import Path

from value_investment_agent import disclosures


def announcement(title: str, url: str) -> dict:
    return {
        "announcementTitle": title,
        "adjunctUrl": url,
        "announcementTime": 1776355200000,
    }


def test_collects_only_full_latest_official_reports(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        disclosures,
        "_request_json",
        lambda _: {"announcements": [
            announcement("Demo 2025年年度报告摘要", "summary.pdf"),
            announcement("Demo 2025年年度报告", "annual.pdf"),
            announcement("Demo 2026年半年度报告", "interim.pdf"),
            announcement("Demo 2025年年度报告（英文版）", "annual-en.pdf"),
        ]},
    )

    downloaded: list[str] = []

    def download(url: str, target: Path) -> str:
        downloaded.append(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"official PDF")
        return "a" * 64

    monkeypatch.setattr(disclosures, "_download", download)
    records = disclosures.collect_latest_reports(["600519"], tmp_path)

    assert {record["report_kind"] for record in records} == {"annual", "interim"}
    assert {record["report_period"] for record in records} == {"2025-12-31", "2026-06-30"}
    assert all(url.startswith("https://static.cninfo.com.cn/") for url in downloaded)
    assert all(record["source_name"] == disclosures.SOURCE_NAME for record in records)

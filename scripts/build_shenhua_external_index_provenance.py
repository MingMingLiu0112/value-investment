"""Build a source-addressed Shenhua external index-operator provenance package."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re

from bs4 import BeautifulSoup
from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/company-research/shenhua-external-index-provenance-20260922"
POINTER = ROOT / "runtime/company-research/shenhua-external-index-provenance-latest.json"
PRIOR_BRIDGE_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json"

REVIEW_DATE = date(2026, 9, 22)

RAW_SOURCES = {
    "ncei_launch_announcement": {
        "filename": "announcement.html",
        "url": "https://www.ncexc.cn/c/2021-12-31/487233.shtml",
        "sha256": "27a91d2f032381c84f3169a59fab7c378ca6f776fdc53a81ecfba2a9d2b14a75",
        "content_type": "text/html",
        "get_status": 200,
        "head_status": 200,
        "role": "NCEI operator launch announcement",
    },
    "ncei_live_page": {
        "filename": "ncei-live.html",
        "url": "https://www.ncexc.cn/mobile/",
        "sha256": "966dcd5d600e41e87e564fb569c44e66b1c2df14166daba3df2497f8022b657b",
        "content_type": "text/html",
        "get_status": 200,
        "head_status": 200,
        "role": "NCEI operator live publication page",
    },
    "ncei_history_access_shell": {
        "filename": "ncei-history-access.html",
        "url": "https://www.ncexc.com/MTServer/index/initQuery?skipType=1",
        "sha256": "9f029ae23530896a19e79d308a7860d7517b33c6380c8ffee1117252eb8e8717",
        "content_type": "text/html; charset=UTF-8",
        "get_status": 200,
        "head_status": 405,
        "role": "NCEI historical-data public shell with membership gate",
    },
    "bspi_launch_notice": {
        "filename": "bspi-launch-notice.html",
        "url": "https://www.beijingprice.cn/c/2010-09-29/500979.shtml",
        "sha256": "e50487cc41da3a409563a3f692c89d527665e96bfd96d2c320a6aee33815aef4",
        "content_type": "text/html",
        "get_status": 200,
        "head_status": 405,
        "role": "NDRC primary launch notice for the Bohai Rim thermal-coal index",
    },
    "cctd_qhd_methodology": {
        "filename": "cctd-qhd-methodology.pdf",
        "url": "https://www.cctd.com.cn/uploadfile/2022/1028/20221028114728860.pdf",
        "sha256": "04ecc550302e5dfb8e3665f82d53ba7a3989c591a56aaff1c734a0763d8f8d37",
        "content_type": "application/pdf",
        "get_status": 200,
        "head_status": 200,
        "role": "CCTD Qinhuangdao thermal-coal price methodology",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(text: str) -> str:
    return "".join(text.split())


def require_fragments(text: str, fragments: tuple[str, ...], label: str) -> None:
    normalized = compact(text)
    missing = [fragment for fragment in fragments if compact(fragment) not in normalized]
    if missing:
        raise ValueError(f"{label} is missing expected fragments: {missing}")


def html_text(path: Path) -> str:
    return BeautifulSoup(path.read_bytes(), "html.parser").get_text(" ", strip=True)


def source_record(source_id: str) -> dict:
    spec = RAW_SOURCES[source_id]
    path = OUT / spec["filename"]
    actual = sha256(path)
    if actual != spec["sha256"]:
        raise ValueError(f"Source hash mismatch for {source_id}")
    stat = path.stat()
    retrieved_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
    return {
        "id": source_id,
        "url": spec["url"],
        "path": str(path.relative_to(ROOT)),
        "sha256": actual,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "byte_size": stat.st_size,
        "content_type": spec["content_type"],
        "http_get_status": spec["get_status"],
        "http_head_status": spec["head_status"],
        "source_role": spec["role"],
    }


def source_ref(source: dict, *, description: str) -> dict:
    return {
        "id": source["id"],
        "path": source["path"],
        "sha256": source["sha256"],
        "description": description,
    }


def pdf_text(reader: PdfReader) -> str:
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def pdf_pages(reader: PdfReader, fragment: str) -> list[int]:
    wanted = compact(fragment)
    return [index + 1 for index, page in enumerate(reader.pages) if wanted in compact(page.extract_text() or "")]


def cn_date_to_iso(value: str) -> str:
    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
    if not match:
        raise ValueError(f"Unsupported Chinese date: {value}")
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def announcement_facts(source: dict) -> dict:
    text = html_text(ROOT / source["path"])
    require_fragments(text, (
        "关于发布NCEI价格指数的公告",
        "2021-12-31",
        "全国煤炭交易中心有限公司",
        "自2021年12月31日起公开发布",
        "国煤下水动力煤价格指数（NCEI）",
        "本中心独立于NCEI价格指数所反映的下水动力煤市场的直接利益相关方",
        "010-52698888",
        "ncei@ncexc.com.cn",
    ), "NCEI launch announcement")
    return {
        "operator": "全国煤炭交易中心有限公司",
        "title": "关于发布NCEI价格指数的公告",
        "document_date": "2021-12-31",
        "first_public_release_date": "2021-12-31",
        "index_name": "国煤下水动力煤价格指数（NCEI）",
        "methodology_document": "国煤下水动力煤价格指数编制方案",
        "independence_declaration": (
            "指数编制行为遵守法律法规，遵循独立、公开、透明原则；"
            "本中心独立于NCEI价格指数所反映的下水动力煤市场的直接利益相关方。"
        ),
        "contacts": {
            "telephone": ["010-52698888", "010-52175491"],
            "email": "ncei@ncexc.com.cn",
        },
        "provenance_class": "primary_index_operator_launch_notice",
        "model_input": None,
    }


def ncei_live_facts(source: dict) -> dict:
    soup = BeautifulSoup((ROOT / source["path"]).read_bytes(), "html.parser")
    slide = soup.select_one("div.priceSwiper div.swiper-slide")
    if slide is None or "NCEI" not in slide.get_text(" ", strip=True):
        raise ValueError("NCEI live page does not contain the expected first index slide")
    labels = [item.get_text(" ", strip=True) for item in slide.select("span.txt3")]
    values = [int(item.get_text(strip=True)) for item in slide.select("span.info2")]
    changes = [item.get_text(strip=True) for item in slide.select("span.txt4")]
    dates = [cn_date_to_iso(value) for value in re.findall(r"发布日期(\d{4}年\d{1,2}月\d{1,2}日)", str(slide))]
    if labels != ["下水煤指数", "中长期合同价格"]:
        raise ValueError(f"Unexpected NCEI live labels: {labels}")
    if values != [758, 704] or changes[:2] != ["+3", "+3"] or dates != ["2026-09-18", "2026-08-31"]:
        raise ValueError("NCEI live observations do not match the retained page")
    return {
        "capture_page": source["url"],
        "observations": [
            {
                "instrument": "ncei_5500k_waterborne_index",
                "display_name": "下水煤指数",
                "value": 758,
                "unit": "index_points",
                "publication_date": "2026-09-18",
                "month_on_month_change": "+3",
                "timestamp_precision": "date_only_from_operator_page",
                "model_input": None,
            },
            {
                "instrument": "ncei_5500k_medium_long_term_contract_price",
                "display_name": "中长期合同价格",
                "value": 704,
                "unit": "cny_per_tonne",
                "publication_date": "2026-08-31",
                "month_on_month_change": "+3",
                "timestamp_precision": "date_only_from_operator_page",
                "model_input": None,
            },
        ],
        "provenance_class": "operator_live_publication_page",
    }


def history_access_facts(source: dict) -> dict:
    text = html_text(ROOT / source["path"])
    raw = (ROOT / source["path"]).read_text(encoding="utf-8")
    require_fragments(text, (
        "成为缴费会员，查看历史指数数据",
        "BSPI",
        "CCTD",
        "CECI",
    ), "NCEI history access shell")
    require_fragments(raw, (
        "成为缴费会员，可享有导出功能",
        "/DzjyServer/api/queryQuotationIndexPage.json",
        "/DzjyServer/api/exportQuotationIndexExcel",
        '"0": "缴费查看更多历史数据"',
        '"2": "仅可查看缴费期间的数据"',
    ), "NCEI history access client contract")
    return {
        "public_shell_status": "rendered_public_shell_without_historical_rows",
        "historical_rows_retrieved": False,
        "membership_message": "成为缴费会员，查看历史指数数据",
        "export_requires_membership": True,
        "visible_index_tabs": ["NCEI", "BSPI", "CCTD", "CECI"],
        "client_reported_permission_states": {
            "0": "never_paid_view_more_historical_data_requires_payment",
            "1": "fully_paid_all_history_visible",
            "2": "paid_period_only_history_visible",
        },
        "api_endpoints_observed": [
            "/DzjyServer/api/queryQuotationIndexPage.json",
            "/DzjyServer/api/exportQuotationIndexExcel",
        ],
        "direct_head_method_status": source["http_head_status"],
        "provenance_class": "access_restriction_evidence_not_historical_data_source",
        "model_input": None,
    }


def bspi_facts(source: dict) -> dict:
    text = html_text(ROOT / source["path"])
    require_fragments(text, (
        "办价格[2010]2399号",
        "国家发展改革委办公厅关于开展环渤海动力煤价格指数试运行工作的通知",
        "2010年09月29日",
        "秦皇岛港、天津港、曹妃甸港、京唐港、国投京唐港、黄骅港",
        "以7天为一个报告期，每周发布一次",
        "上周三到本周二",
        "每周三下午15时发布",
        "秦皇岛海运煤炭交易市场网站和中国价格协会网站",
        "2010年10月中旬起试运行",
        "4500大卡、5000大卡、5500大卡与5800大卡",
        "各港口5500大卡综合平均价格",
        "第一批共选出149家企业作为数据采集单位",
    ), "BSPI launch notice")
    return {
        "document_issuer": "国家发展改革委办公厅",
        "document_number": "办价格[2010]2399号",
        "publication_date": "2010-09-29",
        "operator_entities": [
            {"name": "秦皇岛海运煤炭交易市场", "role": "试运行组织、数据分析与发布渠道"},
            {"name": "中国价格协会", "role": "试运行组织与发布渠道"},
        ],
        "port_universe": ["秦皇岛港", "天津港", "曹妃甸港", "京唐港", "国投京唐港", "黄骅港"],
        "reporting_period": "7天",
        "collection_window": "上周三到本周二",
        "release_schedule": "每周三下午15时",
        "release_websites": ["秦皇岛海运煤炭交易市场网站", "中国价格协会网站"],
        "trial_start": "2010-10",
        "initial_grades": [4500, 5000, 5500, 5800],
        "initial_5500_composite_average": True,
        "initial_data_collection_companies": 149,
        "definition_note": (
            "This is the regulator's trial-run notice for the Bohai Rim thermal-coal index. "
            "It must not be concatenated with NCEI as one homogeneous benchmark."
        ),
        "provenance_class": "primary_regulator_launch_notice",
        "model_input": None,
    }


def cctd_facts(source: dict) -> dict:
    reader = PdfReader(str(ROOT / source["path"]))
    text = pdf_text(reader)
    require_fragments(text, (
        "CCTD秦皇岛动力煤价格编制方案",
        "2022年10月",
        "以秦皇岛港为标准交货地",
        "秦皇岛港及周边港口（曹妃甸港、京唐港、黄骅港、天津港）",
        "离岸平仓价格（含税）",
        "5500、5000和4500kcal/kg",
        "综合交易价",
        "现货交易价",
        "年度长协价",
        "周度",
        "日度",
        "月度",
        "周五17点",
        "工作日15点",
        "CCTD环渤海动力煤现货参考价",
        "中国煤炭市场网（www.cctd.com.cn）",
        "权重分配为80%、20%",
        "严格审慎使用主观判断",
    ), "CCTD Qinhuangdao methodology")
    grade_pages = {
        grade: pdf_pages(reader, f"动力煤 {grade}")
        for grade in (4500, 5000, 5500)
    }
    return {
        "document_title": "CCTD秦皇岛动力煤价格编制方案",
        "cover_publication_period": "2022-10",
        "fifth_edition_revision_date": "2022-10-28",
        "delivery_location": "秦皇岛港及周边港口（曹妃甸港、京唐港、黄骅港、天津港）",
        "price_basis": "离岸平仓价格（含税）",
        "price_unit": "人民币元/吨",
        "representative_grades_kcal_per_kg": [5500, 5000, 4500],
        "representative_grade_pdf_pages": grade_pages,
        "publication_schedule": {
            "composite_price": "weekly, Friday 17:00",
            "spot_price_daily": "each workday 15:00",
            "spot_price_weekly": "weekly, Friday 17:00",
            "annual_long_term_price": "monthly, at month end for the next month",
        },
        "daily_spot_publication_name": "CCTD环渤海动力煤现货参考价",
        "composite_weights_fifth_edition": {
            "annual_long_term_price": "80%",
            "spot_price": "20%",
        },
        "subjective_judgment_allowed": True,
        "sample_coverage_note": "环渤海六港样本单位交易量达到总交易量的70%以上",
        "provenance_class": "primary_index_methodology",
        "model_input": None,
    }


def prior_ref(ref_id: str, pointer: Path, *, description: str) -> dict:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    target = ROOT / pin["path"] / "evidence.json"
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Prior evidence pointer escapes project root")
    actual = sha256(target)
    if actual != pin["sha256"].lower():
        raise ValueError(f"Prior evidence hash mismatch: {pointer}")
    return {
        "id": ref_id,
        "path": str(target.relative_to(ROOT)),
        "sha256": actual,
        "description": description,
    }


def build() -> dict:
    sources = {source_id: source_record(source_id) for source_id in RAW_SOURCES}
    announcement = announcement_facts(sources["ncei_launch_announcement"])
    live = ncei_live_facts(sources["ncei_live_page"])
    history_access = history_access_facts(sources["ncei_history_access_shell"])
    bspi = bspi_facts(sources["bspi_launch_notice"])
    cctd = cctd_facts(sources["cctd_qhd_methodology"])
    return {
        "symbol": "601088",
        "review_date": REVIEW_DATE.isoformat(),
        "reference_period_start": "2010-09-29",
        "reference_period_end": "2026-09-18",
        "source_type": "primary_index_operator_regulator_and_methodology_publications",
        "engineering_status": "external_index_provenance_package_complete",
        "status": "primary_provenance_archived_historical_operator_archives_membership_restricted",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
            "Pin the operator, regulator and methodology provenance for the external coal-price "
            "benchmarks referenced in Shenhua annual reports. Live values and methodology facts are "
            "research observations only; no value in this package is a normalized cyclical input."
        ),
        "ncei_launch_announcement": announcement,
        "ncei_live_page": live,
        "ncei_history_access": history_access,
        "bspi_launch_notice": bspi,
        "cctd_qhd_methodology": cctd,
        "definition_breaks": [
            {
                "id": "bohai_rim_5500_to_ncei_5500_long_term",
                "fact": (
                    "Shenhua annual-report market commentary references Bohai Rim 5,500 kcal through "
                    "2022 and NCEI 5,500 kcal long-term from 2023. The operator archives must be "
                    "retained separately; the change is a benchmark-definition break, not a continuation."
                ),
            },
            {
                "id": "ncei_and_qhd_spot_are_different_markets",
                "fact": "NCEI long-term and Qinhuangdao spot prices are different instruments and cannot be averaged.",
            },
        ],
        "specific_findings": [
            {
                "id": "ncei_operator_identity_independence_and_launch_date_pinned",
                "fact": "The operator is 全国煤炭交易中心有限公司; NCEI was first publicly released on 2021-12-31.",
            },
            {
                "id": "ncei_live_page_pins_two_dated_observations",
                "fact": "The retained mobile page shows the waterborne index at 758 on 2026-09-18 and the medium/long-term contract price at 704 CNY/t on 2026-08-31, both up 3 month on month.",
            },
            {
                "id": "operator_historical_archive_is_membership_gated",
                "fact": "NCEI, BSPI, CCTD and CECI historical tables are hidden by a paid-membership message; export also requires a logged-in current-year paid permission.",
            },
            {
                "id": "bspi_primary_notice_pins_weekly_trial_schedule",
                "fact": "NDRC's 2010 notice defines a 7-day period, Wednesday 15:00 publication and a trial beginning in October 2010.",
            },
            {
                "id": "cctd_methodology_pins_three_grades_and_prices",
                "fact": "CCTD QHD uses 5500/5000/4500 kcal/kg, FOB tax-inclusive prices, and separate composite, spot and annual long-term prices with weekly/daily/monthly publication.",
            },
            {
                "id": "cctd_allows_disclosed_subjective_judgment",
                "fact": "The CCTD methodology explicitly allows subjective judgment in defined circumstances, so index continuity and sample quality must be checked before using a historical archive.",
            },
        ],
        "registered_cyclical_facts_operating_inputs": [],
        "point_in_time_policy": [
            "A source page is known only on or after its retrieval date; operator publication dates are retained separately.",
            "Live operator values are point observations, not a substitute for the missing daily or weekly historical archive.",
            "A paid-membership gate means the historical rows were not source-addressably retained and are unavailable to this package.",
            "Issuer annual-report market commentary remains secondary provenance for an index.",
            "BSPI trial-period rules and the 2021 NCEI launch are separate instruments and separate point-in-time records.",
        ],
        "forbidden_calculations": [
            "Use current NCEI values 758 or 704 directly as normalized bear/base/bull price inputs.",
            "Concatenate BSPI and NCEI into one historical benchmark series without operator archive reconciliation.",
            "Treat membership-hidden historical rows as available or interpolate them from live snapshots.",
            "Derive Shenhua fair value from index levels before route, tax and contract-mix reconciliation.",
            "Use issuer annual-report annual averages as an index-operator daily archive.",
        ],
        "blockers": [
            "index_operator_historical_archives_are_membership_restricted_and_not_reconciled",
            "live_operator_values_are_research_observations_not_cyclical_model_inputs",
            "bohai_rim_5500_and_ncei_5500_are_different_benchmark_instruments",
            "issuer_annual_report_market_commentary_is_secondary_provenance",
            "cctd_bspi_and_ncei_are_not_one_interchangeable_coal_price_series",
        ],
        "evidence_refs": [
            source_ref(sources["ncei_launch_announcement"], description="NCEI operator launch announcement"),
            source_ref(sources["ncei_live_page"], description="NCEI operator live page with dated observations"),
            source_ref(sources["ncei_history_access_shell"], description="NCEI historical-data shell and membership restriction evidence"),
            source_ref(sources["bspi_launch_notice"], description="NDRC Bohai Rim thermal-coal index trial notice"),
            source_ref(sources["cctd_qhd_methodology"], description="CCTD Qinhuangdao thermal-coal price methodology"),
            prior_ref("shenhua_price_cost_transport_bridge", PRIOR_BRIDGE_POINTER, description="Previously compiled external-price and 2025 cost/transport bridge"),
        ],
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    script_digest = sha256(Path(__file__).resolve())
    source_hashes = {source_id: source_record(source_id)["sha256"] for source_id in RAW_SOURCES}
    manifest = {
        "script_sha256": script_digest,
        "evidence_sha256": digest,
        "source_sha256s": source_hashes,
        "prior_evidence_sha256s": {
            "shenhua_price_cost_transport_bridge": json.loads(PRIOR_BRIDGE_POINTER.read_text(encoding="utf-8"))["sha256"],
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    POINTER.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": digest,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(target),
        "sha256": digest,
        "status": payload["status"],
        "registered_inputs": payload["registered_cyclical_facts_operating_inputs"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

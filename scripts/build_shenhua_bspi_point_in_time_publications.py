"""Build a fail-closed Shenhua BSPI point-in-time publication package."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/company-research/shenhua-bspi-point-in-time-publications-20260922"
POINTER = ROOT / "runtime/company-research/shenhua-bspi-point-in-time-publications-latest.json"
BSPI_PATH = ROOT / "runtime/company-research/shenhua-public-index-history-20260922/BSPI.json"

RECONCILIATION_POINTER = ROOT / "runtime/company-research/shenhua-bspi-annual-report-reconciliation-latest.json"
EXTERNAL_INDEX_POINTER = ROOT / "runtime/company-research/shenhua-external-index-provenance-latest.json"
PRICE_COST_BRIDGE_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json"
PUBLIC_INDEX_POINTER = ROOT / "runtime/company-research/shenhua-public-index-history-latest.json"

REVIEW_DATE = date(2026, 9, 22)
BSPI_HASH = "069cde6b91be135bfa229a302533cfbfc670b36609515a2f4cae18cb3748083f"
CEI_ARTICLE_PATH_FRAGMENT = "4b4ff617-75ee4708-0176-b7581631-0a06_2020.html"

PUBLISHER_PROVENANCE = {
    "bspi_operator": {
        "operator_name": "秦皇岛海运煤炭交易市场有限公司",
        "historical_platform_domains": [
            {
                "domain": "www.osc.org.cn",
                "role": "historical operator/launch-period domain",
                "probe_status": "DNS_NOT_RESOLVED",
            },
            {
                "domain": "www.cqcoal.com",
                "role": "current Qinhuangdao Coal Network operator domain",
                "probe_status": "HTTP_EMPTY_REPLY",
            },
            {
                "domain": "news.cqcoal.com:8001",
                "role": "operator article API host",
                "probe_status": "HTTP_EMPTY_REPLY",
            },
        ],
        "addressable_operator_article_host": "news.cqcoal.com:8001",
        "availability_note": (
            "On 2026-09-22 the historical osc.org.cn domain did not resolve and the current "
            "cqcoal.com/news.cqcoal.com hosts returned empty replies. The 2017/2021/2022 operator "
            "article bytes retained in this package therefore remain the only source-addressable "
            "operator pages; 2018/2019/2020 operator originals are ORIGINAL_NOT_EVIDENCED."
        ),
    },
    "ncei_operator": {
        "operator_name": "全国煤炭交易中心有限公司",
        "primary_domain": "www.ncexc.cn",
        "history_access": "membership_gated",
        "site_search_status": "no_original_2023_2025_monthly_publication_pages_returned",
        "note": (
            "A 2026-09-22 operator-domain search returned no source-addressable original 2023-2025 "
            "monthly NCEI publication or revision page. Third-party search snippets are not archived "
            "as evidence and are not used to synthesize a NCEI series."
        ),
    },
}

ORIGINAL_AVAILABILITY = {
    "status": "ORIGINAL_NOT_EVIDENCED_FOR_MISSING_YEARS",
    "probe_date": REVIEW_DATE.isoformat(),
    "bspi_missing_years": [2018, 2019, 2020],
    "ncei_missing_years": [2023, 2024, 2025],
    "findings": [
        {
            "id": "bspi_2018_operator_original_not_evidenced",
            "year": 2018,
            "status": "ORIGINAL_NOT_EVIDENCED",
            "detail": "CoalChina and China5e attributed republications plus Great Wall Network and Hebei Economic Daily operator-group news reports are archived for 569. No operator original was retrieved.",
        },
        {
            "id": "bspi_2019_operator_original_not_evidenced",
            "year": 2019,
            "status": "ORIGINAL_NOT_EVIDENCED",
            "detail": "China5e and CWESTC attributed republications plus a CCTD-hosted third-party market commentary are archived for 551. No operator original was retrieved.",
        },
        {
            "id": "bspi_2020_operator_original_not_evidenced",
            "year": 2020,
            "status": "ORIGINAL_NOT_EVIDENCED",
            "detail": "China5e, E-Hang, CWESTC and In-en explicit republications corroborate 585; a CEI title/date listing also addresses the 585 headline, but its full article is login-gated. No operator original was retrieved.",
        },
        {
            "id": "ncei_2023_2025_original_publication_records_not_evidenced",
            "years": [2023, 2024, 2025],
            "status": "ORIGINAL_NOT_EVIDENCED",
            "detail": "No original monthly publication or revision page was retrieved from ncexc.cn; membership-gated history and search snippets are not a completed point-in-time series.",
        },
    ],
}

RAW_SOURCES = {
    "cctd_bspi_overview_20140918": {
        "filename": "cctd-bspi-overview-20140918.html",
        "url": "https://www.cctd.com.cn/show-425-150230-1.html",
        "sha256": "ba9ce29d684a4f15151ce09d4e83dda1ef6652427c64257bc4b22206a2759516",
        "encoding": "gbk",
        "get_status": 200,
        "source_role": "CCTD operator BSPI overview and methodology page",
    },
    "cctd_bspi_2014_page_525": {
        "filename": "cctd-bspi-2014-year-end-525.html",
        "url": "https://www.cctd.com.cn/show-259-16672-1.html",
        "sha256": "1502bb2c1203df7c8e8af3571797303a6dcc2ed5901d43f2d06e35dc5e2139e4",
        "encoding": "gbk",
        "get_status": 200,
        "source_role": "CCTD-hosted republication of the Qinhuangdao Coal Network BSPI 525 page",
    },
    "cctd_bspi_2015_page_372": {
        "filename": "cctd-bspi-2015-year-end-372.html",
        "url": "https://www.cctd.com.cn/show-34-8496-1.html",
        "sha256": "cc8103b9b45b80fe2d16ba0965f5bd03d9bdac9b61a3576f77cf3635ee3d9de8",
        "encoding": "gbk",
        "get_status": 200,
        "source_role": "CCTD-hosted republication of the Qinhuangdao Coal Network BSPI 372 page",
    },
    "cctd_bspi_2016_page_593": {
        "filename": "cctd-bspi-2016-year-end-593.html",
        "url": "https://www.cctd.com.cn/show-259-156792-1.html",
        "sha256": "d8054506f28ff8767cadd5d9c69ae514d75749582bb5eb053c386e95d4790978",
        "encoding": "gbk",
        "get_status": 200,
        "source_role": "CCTD-hosted republication of the Qinhuangdao Coal Network BSPI 593 page",
    },
    "china5e_attributed_bspi_2017_page_577": {
        "filename": "china5e-attributed-bspi-2017-year-end-577.html",
        "url": "https://www.china5e.com/news/news-1015770-1.html",
        "sha256": "36a9feac23891d397e69a4940cd9f0ffa21eec64a3dbe1afc320acd5b243913f",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network",
    },
    "china5e_attributed_bspi_2020_page_585": {
        "filename": "china5e-attributed-bspi-2020-year-end-585.html",
        "url": "https://www.china5e.com/news/news-1107332-1.html",
        "sha256": "96525e2a6e404169df049f64ae0ad03ad99d33e02520bf4add001b666239d913",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network",
    },
    "ehang_attributed_bspi_2020_page_585": {
        "filename": "ehang-attributed-bspi-2020-year-end-585.html",
        "url": "http://www.e-hang.net/wap/detail/post-43328.html",
        "sha256": "25b916b7ca45b550f087f18f267f5340815204eb311852d6a943789b265359a1",
        "encoding": "utf-8",
        "get_status": 200,
        "alternate_urls": [
            "http://www.ehangwang.cn/wap/detail/post-43328.html",
        ],
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network",
    },
    "china5e_attributed_bspi_2021_page_737": {
        "filename": "china5e-attributed-bspi-2021-year-end-737.html",
        "url": "https://www.china5e.com/news/news-1127902-1.html",
        "sha256": "ad8e0c782e719943149e7d616ed82caed6d5949c235b33db2418776c9117ff69",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network",
    },
    "china5e_attributed_bspi_2022_page_734": {
        "filename": "china5e-attributed-bspi-2022-year-end-734.html",
        "url": "https://www.china5e.com/news/news-1145873-1.html",
        "sha256": "bb78430ceb17813ab440500e0f3fb129cbbe469c029310ab5788272be827789f",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network",
    },
    "china5e_attributed_bspi_2018_page_569": {
        "filename": "china5e-attributed-bspi-2018-year-end-569.html",
        "url": "https://www.china5e.com/news/news-1048170-1.html",
        "sha256": "d5c12665d62b9575bc6ae48d230f9f5bd3a821cade9c53abfa5d549c11acc63c",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network for BSPI 569",
    },
    "hebccw_attributed_bspi_2018_page_569": {
        "filename": "hebccw-attributed-bspi-2018-year-end-569.html",
        "url": "http://heb.hebccw.cn/system/2018/12/27/019351324.shtml",
        "sha256": "fa21b62238fb88c8bd6422b17024201015d790cb97deac58b315bddb128b346c",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Great Wall Network news report attributed to the Qinhuangdao Maritime Coal Exchange release for BSPI 569",
    },
    "cctd_market_commentary_2019_bspi_551": {
        "filename": "cctd-hosted-bspi-2019-year-end-551.html",
        "url": "https://www.cctd.com.cn/index.php?a=show&catid=609&id=197612",
        "sha256": "3cc8a919b4413f149b92ca04b887fbde7c7d75cb71d1f66116029c2d66aef54c",
        "encoding": "gbk",
        "get_status": 200,
        "source_role": "CCTD-hosted third-party market commentary that quotes the 2019 BSPI 551 release",
    },
    "cei_bspi_2020_page_585": {
        "filename": "cei-attributed-bspi-2020-year-end-585.html",
        "url": "http://ibe.cei.cn//defaultsite/s/column/4028c7ca-39905444-0139-90673495-02b5_2020.html?articleListType=1&coluOpenType=1",
        "sha256": "0819931180fc7b9f78c05c63ec9c50dd55343d656f94e7d4d17364d35c8aaf42",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": (
            "CEI-hosted secondary BSPI 2020 listing page whose accessible bytes expose only the "
            "exact title, 2020-12-31 listing date and addressable article path. The linked article "
            "is login-gated and the listing has no explicit Qinhuangdao Coal Network attribution."
        ),
        "listing_scope": "title_date_article_path_only",
        "full_article_access": "LOGIN_GATED",
    },
    "coalchina_attributed_bspi_2018_page_569": {
        "filename": "coalchina-attributed-bspi-2018-year-end-569.html",
        "url": "https://www.coalchina.org.cn/index.php?m=content&c=index&a=show&catid=30&id=74553",
        "sha256": "4e1d5091fc0c99e3401d514ffde8babc64df6f88f85c7fa9d267082884671cbc",
        "encoding": "gbk",
        "get_status": 200,
        "source_role": "China National Coal Association republication explicitly attributed to Qinhuangdao Coal Network for BSPI 569",
    },
    "hebeidaily_operator_group_news_2018_bspi_569": {
        "filename": "hebeidaily-operator-group-news-bspi-2018-year-end-569.html",
        "url": "http://epaper.hbjjrb.com/jjrb/201812/31/con32968.html",
        "sha256": "69e912fa385ccf58352416c868870b31eefcce769fe0451e85be5d61e15efb6a",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Hebei Economic Daily print news report of the Hebei Port Group Qinhuangdao Maritime Coal Exchange release for BSPI 569",
    },
    "china5e_attributed_bspi_2019_page_551": {
        "filename": "china5e-attributed-bspi-2019-year-end-551.html",
        "url": "https://www.china5e.com/news/news-1079406-1.html",
        "sha256": "2abaa272dd32fea29f1add0a2b1cf25596fc8926a68063ee34db557793e28fe2",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network for BSPI 551",
    },
    "cwestc_attributed_bspi_2019_page_551": {
        "filename": "cwestc-attributed-bspi-2019-year-end-551.html",
        "url": "http://www.cwestc.com/newshtml/2019-12-26/594223.shtml",
        "sha256": "462c621357697426fba97c5178a9aa8ae584e426a6432d1b27a949874f2b59a8",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network for BSPI 551",
    },
    "cwestc_attributed_bspi_2020_page_585": {
        "filename": "cwestc-attributed-bspi-2020-year-end-585.html",
        "url": "http://www.cwestc.com/newshtml/2020-12-31/652286.shtml",
        "sha256": "edeba8d83f5ae96da54885e28b7dcd0ec3e3328753bc68ce55b51c6866e20f9a",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network for BSPI 585",
    },
    "in_en_attributed_bspi_2020_page_585": {
        "filename": "in-en-attributed-bspi-2020-year-end-585.html",
        "url": "https://coal.in-en.com/html/coal-2589787.shtml",
        "sha256": "093b77bad173b01fda73a47a04d82f280dfad91579bff1af05963ead4536e71f",
        "encoding": "utf-8",
        "get_status": 200,
        "source_role": "Secondary republication explicitly attributed to Qinhuangdao Coal Network for BSPI 585",
    },
    "cqcoal_operator_api_2017_bspi_577": {
        "filename": "cqcoal-api-article-80997-234.json",
        "url": "http://news.cqcoal.com:8001/api/news/80997/234",
        "sha256": "c76dc2478254672aa57ddacaec87390eb73d89cb57c48a74c0f5d002c5b54c12",
        "content_type": "application/json",
        "get_status": 200,
        "source_role": "Qinhuangdao Coal Network operator article API response for the 2017 BSPI 577 publication",
    },
    "cqcoal_operator_page_2017_bspi_577": {
        "filename": "cqcoal-page-article-80997-234.html",
        "url": "http://news.cqcoal.com/blank/nc.jsp?mid=80997&tid=234",
        "sha256": "74ac3f496b40d35161755f64edceeeb8ac01b6910b5ff74e839bcdad7afa90da",
        "content_type": "text/html; charset=UTF-8",
        "get_status": 200,
        "source_role": "Qinhuangdao Coal Network addressable article page for the 2017 BSPI 577 publication",
    },
    "cqcoal_operator_api_2021_bspi_737": {
        "filename": "cqcoal-api-article-110846-234.json",
        "url": "http://news.cqcoal.com:8001/api/news/110846/234",
        "sha256": "a5c98109ecd46fe72ce838a03dc7fb50e1422f37c416ce849152a26c3b581d9f",
        "content_type": "application/json",
        "get_status": 200,
        "source_role": "Qinhuangdao Coal Network operator article API response for the 2021 BSPI 737 publication",
    },
    "cqcoal_operator_page_2021_bspi_737": {
        "filename": "cqcoal-page-article-110846-234.html",
        "url": "http://news.cqcoal.com/blank/nc.jsp?mid=110846&tid=234",
        "sha256": "5c4730ab67ad008080540d5f52e49a15e3fd7e29eb9362a2e4faa56ab8377693",
        "content_type": "text/html; charset=UTF-8",
        "get_status": 200,
        "source_role": "Qinhuangdao Coal Network addressable article page for the 2021 BSPI 737 publication",
    },
    "cqcoal_operator_api_2022_bspi_734": {
        "filename": "cqcoal-api-article-114105-234.json",
        "url": "http://news.cqcoal.com:8001/api/news/114105/234",
        "sha256": "da0cc66ff2b7c2f78125d9cd5cfce3319451242887dc8411e0a3b505b245d1c0",
        "content_type": "application/json",
        "get_status": 200,
        "source_role": "Qinhuangdao Coal Network operator article API response for the 2022 BSPI 734 publication",
    },
    "cqcoal_operator_page_2022_bspi_734": {
        "filename": "cqcoal-page-article-114105-234.html",
        "url": "http://news.cqcoal.com/blank/nc.jsp?mid=114105&tid=234",
        "sha256": "6e500c3c042945018091645e3cde0d53505cf9e5215807ce8a56403768562fe3",
        "content_type": "text/html; charset=UTF-8",
        "get_status": 200,
        "source_role": "Qinhuangdao Coal Network addressable article page for the 2022 BSPI 734 publication",
    },
    "cqcoal_operator_search_gap_2020_final_bspi_585": {
        "filename": "cqcoal-search-gap-2020-final-bspi-585.json",
        "url": "http://www.cqcoal.com/mars-web/newslist/searchByKeyWord",
        "sha256": "21c416122c7dd6facf7af710312ad91a9ad99b916f92e107496f6da624936c0f",
        "content_type": "application/json",
        "get_status": 200,
        "source_role": "Qinhuangdao Coal Network search-index gap snapshot for the missing 2020 final BSPI 585 article",
    },
}

PUBLICATION_SPECS = (
    {
        "id": "bspi_2014_cctd_page_525",
        "source_id": "cctd_bspi_2014_page_525",
        "year": 2014,
        "cited_value": 525,
        "reporting_period_start": "2014-12-17",
        "reporting_period_end": "2014-12-23",
        "page_publication_timestamp": "2014-12-24T15:48:00+08:00",
        "cited_release_date": "2014-12-24",
        "source_role": "cctd_hosted_republication",
        "cctd_hosted_republication_found": True,
        "operator_primary_page_found": False,
        "secondary_attributed_republication_found": False,
        "operator_article_id": None,
        "operator_publish_time": None,
        "operator_api_update_time": None,
        "operator_source_label": None,
        "calendar_year_final_publication": False,
        "endpoint_last_date": "2014-12-31",
        "endpoint_last_value": 523,
        "annual_report_period_end_value": 525,
        "date_alignment_status": "mismatch_flagged",
        "mismatch_notes": (
            "The page reports 525 for 2014-12-17 to 2014-12-23, but the retained endpoint "
            "has 523 on 2014-12-31, so this page is not a calendar-year-final publication."
        ),
    },
    {
        "id": "bspi_2015_cctd_page_372",
        "source_id": "cctd_bspi_2015_page_372",
        "year": 2015,
        "cited_value": 372,
        "reporting_period_start": "2015-12-23",
        "reporting_period_end": "2015-12-29",
        "page_publication_timestamp": "2016-01-04T13:55:32+08:00",
        "cited_release_date": "2015-12-30",
        "source_role": "cctd_hosted_republication",
        "cctd_hosted_republication_found": True,
        "operator_primary_page_found": False,
        "secondary_attributed_republication_found": False,
        "operator_article_id": None,
        "operator_publish_time": None,
        "operator_api_update_time": None,
        "operator_source_label": None,
        "calendar_year_final_publication": True,
        "endpoint_last_date": "2015-12-30",
        "endpoint_last_value": 372,
        "annual_report_period_end_value": 372,
        "date_alignment_status": "reconciled",
        "mismatch_notes": [],
    },
    {
        "id": "bspi_2016_cctd_page_593",
        "source_id": "cctd_bspi_2016_page_593",
        "year": 2016,
        "cited_value": 593,
        "reporting_period_start": "2016-12-21",
        "reporting_period_end": "2016-12-27",
        "page_publication_timestamp": "2016-12-28T15:01:05+08:00",
        "cited_release_date": None,
        "source_role": "cctd_hosted_republication",
        "cctd_hosted_republication_found": True,
        "operator_primary_page_found": False,
        "secondary_attributed_republication_found": False,
        "operator_article_id": None,
        "operator_publish_time": None,
        "operator_api_update_time": None,
        "operator_source_label": None,
        "calendar_year_final_publication": True,
        "endpoint_last_date": "2016-12-28",
        "endpoint_last_value": 593,
        "annual_report_period_end_value": 593,
        "date_alignment_status": "reconciled",
        "mismatch_notes": [],
    },
    {
        "id": "bspi_2017_cqcoal_operator_577",
        "source_id": "cqcoal_operator_api_2017_bspi_577",
        "secondary_source_id": "china5e_attributed_bspi_2017_page_577",
        "year": 2017,
        "cited_value": 577,
        "reporting_period_start": "2017-12-20",
        "reporting_period_end": "2017-12-26",
        "page_publication_timestamp": "2017-12-27T15:08:00+08:00",
        "cited_release_date": "2017-12-27",
        "source_role": "cqcoal_operator_direct_page",
        "cctd_hosted_republication_found": False,
        "operator_primary_page_found": True,
        "secondary_attributed_republication_found": True,
        "operator_article_id": 80997,
        "operator_publish_time": "2017-12-27 15:08",
        "operator_api_update_time": "2022-10-31 13:52:19",
        "operator_source_label": "秦皇岛煤炭网",
        "calendar_year_final_publication": True,
        "endpoint_last_date": "2017-12-27",
        "endpoint_last_value": 577,
        "annual_report_period_end_value": 578,
        "date_alignment_status": "annual_report_value_mismatch",
        "mismatch_notes": (
            "Final 2017 publication is 577; the issuer annual-report period-end value is 578, "
            "which the endpoint shows on 2017-11-08. The observations are not reconciled."
        ),
    },
    {
        "id": "bspi_2020_china5e_attributed_585",
        "source_id": "china5e_attributed_bspi_2020_page_585",
        "additional_secondary_source_ids": (
            "ehang_attributed_bspi_2020_page_585",
        ),
        "year": 2020,
        "cited_value": 585,
        "reporting_period_start": "2020-12-23",
        "reporting_period_end": "2020-12-29",
        "page_publication_timestamp": "2020-12-31T10:43:44+08:00",
        "cited_release_date": None,
        "source_role": "secondary_attributed_republication",
        "cctd_hosted_republication_found": False,
        "operator_primary_page_found": False,
        "secondary_attributed_republication_found": True,
        "operator_article_id": None,
        "operator_publish_time": None,
        "operator_api_update_time": None,
        "operator_source_label": None,
        "calendar_year_final_publication": True,
        "endpoint_last_date": "2020-12-30",
        "endpoint_last_value": 585,
        "annual_report_period_end_value": 585,
        "date_alignment_status": "reconciled",
        "mismatch_notes": [],
        "provenance_notes": (
            "The Qinhuangdao Coal Network search index and the complete public 234-column listing "
            "do not contain the exact 2020-12-23 to 2020-12-29 BSPI 585 article. China5e and E-Hang "
            "are two independently addressable republications that explicitly attribute the full text "
            "to Qinhuangdao Coal Network, but neither is promoted to an operator original."
        ),
    },
    {
        "id": "bspi_2021_cqcoal_operator_737",
        "source_id": "cqcoal_operator_api_2021_bspi_737",
        "secondary_source_id": "china5e_attributed_bspi_2021_page_737",
        "year": 2021,
        "cited_value": 737,
        "reporting_period_start": "2021-12-22",
        "reporting_period_end": "2021-12-28",
        "page_publication_timestamp": "2021-12-29T15:00:00+08:00",
        "cited_release_date": "2021-12-29",
        "source_role": "cqcoal_operator_direct_page",
        "cctd_hosted_republication_found": False,
        "operator_primary_page_found": True,
        "secondary_attributed_republication_found": True,
        "operator_article_id": 110846,
        "operator_publish_time": "2021-12-29 15:00",
        "operator_api_update_time": "2022-10-31 13:52:19",
        "operator_source_label": "秦皇岛煤炭网",
        "calendar_year_final_publication": True,
        "endpoint_last_date": "2021-12-29",
        "endpoint_last_value": 737,
        "annual_report_period_end_value": 737,
        "date_alignment_status": "reconciled",
        "mismatch_notes": [],
    },
    {
        "id": "bspi_2022_cqcoal_operator_734",
        "source_id": "cqcoal_operator_api_2022_bspi_734",
        "secondary_source_id": "china5e_attributed_bspi_2022_page_734",
        "year": 2022,
        "cited_value": 734,
        "reporting_period_start": "2022-12-21",
        "reporting_period_end": "2022-12-27",
        "page_publication_timestamp": "2022-12-28T15:07:00+08:00",
        "cited_release_date": "2022-12-28",
        "source_role": "cqcoal_operator_direct_page",
        "cctd_hosted_republication_found": False,
        "operator_primary_page_found": True,
        "secondary_attributed_republication_found": True,
        "operator_article_id": 114105,
        "operator_publish_time": "2022-12-28 15:07",
        "operator_api_update_time": "2023-01-05 16:40:37",
        "operator_source_label": "秦皇岛煤炭网",
        "calendar_year_final_publication": True,
        "endpoint_last_date": "2022-12-28",
        "endpoint_last_value": 734,
        "annual_report_period_end_value": 734,
        "date_alignment_status": "reconciled",
        "mismatch_notes": [],
    },
)


CORROBORATING_PUBLICATION_SPECS = (
    {
        "id": "bspi_2018_china5e_attributed_569",
        "source_id": "china5e_attributed_bspi_2018_page_569",
        "year": 2018,
        "cited_value": 569,
        "reporting_period_start": "2018-12-19",
        "reporting_period_end": "2018-12-25",
        "page_publication_timestamp": "2018-12-27T11:04:11+08:00",
        "source_date": "2018-12-27",
        "provenance_class": "secondary_attributed_republication",
        "explicit_operator_attribution": True,
        "notes": "China5e repeats the full 569 text and labels its source as Qinhuangdao Coal Network.",
    },
    {
        "id": "bspi_2018_hebccw_operator_group_news_569",
        "source_id": "hebccw_attributed_bspi_2018_page_569",
        "year": 2018,
        "cited_value": 569,
        "reporting_period_start": "2018-12-19",
        "reporting_period_end": "2018-12-25",
        "page_publication_timestamp": "2018-12-27T20:06:21+08:00",
        "source_date": "2018-12-27",
        "provenance_class": "operator_group_news_report",
        "explicit_operator_attribution": True,
        "notes": "Great Wall Network reports that Hebei Port Group Qinhuangdao Maritime Coal Exchange published 569; it is a news report, not an operator article page.",
    },
    {
        "id": "bspi_2019_cctd_market_commentary_551",
        "source_id": "cctd_market_commentary_2019_bspi_551",
        "year": 2019,
        "cited_value": 551,
        "reporting_period_start": "2019-12-18",
        "reporting_period_end": "2019-12-24",
        "page_publication_timestamp": "2019-12-26T10:01:51+08:00",
        "source_date": "2019-12-26",
        "provenance_class": "third_party_market_commentary",
        "explicit_operator_attribution": False,
        "notes": "The CCTD page is authored by Ruitian Futures and merely quotes the 551 release; it is not an attributed BSPI republication.",
    },
    {
        "id": "bspi_2020_cei_secondary_listing_585",
        "source_id": "cei_bspi_2020_page_585",
        "year": 2020,
        "cited_value": 585,
        "reporting_period_start": None,
        "reporting_period_end": None,
        "page_publication_timestamp": None,
        "source_date": "2020-12-31",
        "provenance_class": "secondary_index_republication",
        "explicit_operator_attribution": False,
        "article_path_fragment": CEI_ARTICLE_PATH_FRAGMENT,
        "access_scope": "title_date_article_path_only",
        "full_article_access": "LOGIN_GATED",
        "notes": (
            "The CEI 2020 industry-channel listing exposes only the exact title, listing date and "
            "article path. The linked article is login-gated, so the retained page provides title/date "
            "addressability but no full-text attributed republication and no explicit operator attribution."
        ),
    },
    {
        "id": "bspi_2018_coalchina_attributed_569",
        "source_id": "coalchina_attributed_bspi_2018_page_569",
        "year": 2018,
        "cited_value": 569,
        "reporting_period_start": "2018-12-19",
        "reporting_period_end": "2018-12-25",
        "page_publication_timestamp": "2018-12-26T00:00:00+08:00",
        "source_date": "2018-12-26",
        "provenance_class": "industry_association_attributed_republication",
        "explicit_operator_attribution": True,
        "notes": "The China National Coal Association republishes the full 569 text and labels its source as Qinhuangdao Coal Network; the association page remains a third-party republication.",
    },
    {
        "id": "bspi_2018_hebeidaily_operator_group_news_569",
        "source_id": "hebeidaily_operator_group_news_2018_bspi_569",
        "year": 2018,
        "cited_value": 569,
        "reporting_period_start": "2018-12-19",
        "reporting_period_end": "2018-12-25",
        "page_publication_timestamp": "2018-12-31T00:00:00+08:00",
        "source_date": "2018-12-31",
        "provenance_class": "print_news_operator_group_report",
        "explicit_operator_attribution": True,
        "notes": "Hebei Economic Daily reports that Hebei Port Group Qinhuangdao Maritime Coal Exchange published 569; it is an independent print news report, not an operator article page.",
    },
    {
        "id": "bspi_2019_china5e_attributed_551",
        "source_id": "china5e_attributed_bspi_2019_page_551",
        "year": 2019,
        "cited_value": 551,
        "reporting_period_start": "2019-12-18",
        "reporting_period_end": "2019-12-24",
        "page_publication_timestamp": "2019-12-26T11:16:11+08:00",
        "source_date": "2019-12-26",
        "provenance_class": "secondary_attributed_republication",
        "explicit_operator_attribution": True,
        "notes": "China5e repeats the full 551 text and labels its source as Qinhuangdao Coal Network.",
    },
    {
        "id": "bspi_2019_cwestc_attributed_551",
        "source_id": "cwestc_attributed_bspi_2019_page_551",
        "year": 2019,
        "cited_value": 551,
        "reporting_period_start": "2019-12-18",
        "reporting_period_end": "2019-12-24",
        "page_publication_timestamp": "2019-12-26T09:44:26+08:00",
        "source_date": "2019-12-26",
        "provenance_class": "secondary_attributed_republication",
        "explicit_operator_attribution": True,
        "notes": "CWESTC repeats the full 551 text and labels its source as Qinhuangdao Coal Network.",
    },
    {
        "id": "bspi_2020_cwestc_attributed_585",
        "source_id": "cwestc_attributed_bspi_2020_page_585",
        "year": 2020,
        "cited_value": 585,
        "reporting_period_start": "2020-12-23",
        "reporting_period_end": "2020-12-29",
        "page_publication_timestamp": "2020-12-31T11:41:14+08:00",
        "source_date": "2020-12-31",
        "provenance_class": "secondary_attributed_republication",
        "explicit_operator_attribution": True,
        "notes": "CWESTC repeats the full 585 text and labels its source as Qinhuangdao Coal Network.",
    },
    {
        "id": "bspi_2020_in_en_attributed_585",
        "source_id": "in_en_attributed_bspi_2020_page_585",
        "year": 2020,
        "cited_value": 585,
        "reporting_period_start": "2020-12-23",
        "reporting_period_end": "2020-12-29",
        "page_publication_timestamp": "2020-12-30T18:40:00+08:00",
        "source_date": "2020-12-30",
        "provenance_class": "secondary_attributed_republication",
        "explicit_operator_attribution": True,
        "notes": "In-en repeats the full 585 text and labels its source as Qinhuangdao Coal Network.",
    },
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pointer_payload(pointer: Path) -> tuple[dict, Path, str]:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    target = ROOT / pin["path"] / "evidence.json"
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError(f"Pointer escapes project root: {pointer}")
    actual = sha256(target)
    if actual != pin["sha256"].lower():
        raise ValueError(f"Evidence hash mismatch: {pointer}")
    return json.loads(target.read_text(encoding="utf-8")), target, actual


def prior_ref(pointer: Path, ref_id: str, *, description: str) -> dict:
    _, target, actual = pointer_payload(pointer)
    return {
        "id": ref_id,
        "path": str(target.relative_to(ROOT)),
        "sha256": actual,
        "description": description,
    }


def source_record(source_id: str) -> dict:
    spec = RAW_SOURCES[source_id]
    path = OUT / spec["filename"]
    actual = sha256(path)
    if actual != spec["sha256"].lower():
        raise ValueError(f"Source hash mismatch for {source_id}")
    stat = path.stat()
    record = {
        "id": source_id,
        "url": spec["url"],
        "alternate_urls": list(spec.get("alternate_urls", ())),
        "path": str(path.relative_to(ROOT)),
        "sha256": actual,
        "retrieved_at_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "byte_size": stat.st_size,
        "content_type": spec.get("content_type", "text/html"),
        "encoding": spec.get("encoding"),
        "http_get_status": spec["get_status"],
        "http_head_status": None,
        "source_role": spec["source_role"],
    }
    for key in ("listing_scope", "full_article_access"):
        if key in spec:
            record[key] = spec[key]
    return record


def source_ref(source: dict, *, description: str) -> dict:
    return {
        "id": source["id"],
        "path": source["path"],
        "sha256": source["sha256"],
        "description": description,
    }


def endpoint_last_rows() -> dict[int, dict]:
    actual = sha256(BSPI_PATH)
    if actual != BSPI_HASH:
        raise ValueError(f"BSPI endpoint hash mismatch: {actual}")
    rows = json.loads(BSPI_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("BSPI endpoint did not return a non-empty array")
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["name"][:4]), []).append(row)
    return {
        year: {"date": rows[-1]["name"], "value": int(rows[-1]["age"])}
        for year, rows in grouped.items()
    }


def reconciliation_rows() -> dict[int, dict]:
    payload, _, _ = pointer_payload(RECONCILIATION_POINTER)
    return {row["year"]: row for row in payload["comparisons"]}


def stripped_text(value: str) -> str:
    return "".join(re.sub(r"<[^>]+>", "", value).split())


def require_fragments(value: str, fragments: tuple[str, ...], label: str) -> None:
    normalized = stripped_text(value)
    missing = [fragment for fragment in fragments if fragment not in normalized]
    if missing:
        raise ValueError(f"{label} is missing expected fragments: {missing}")


OPERATOR_API_EXPECTATIONS = {
    "cqcoal_operator_api_2017_bspi_577": {
        "article_id": 80997,
        "title": "环渤海动力煤价报收577元/吨",
        "publish_time": "2017-12-27 15:08",
        "update_time": "2022-10-31 13:52:19",
        "news_source": "秦皇岛煤炭网",
        "content_fragments": (
            "2017年12月20日至12月26日",
            "报收于577元/吨",
            "环比持平",
        ),
    },
    "cqcoal_operator_api_2021_bspi_737": {
        "article_id": 110846,
        "title": "【BSPI】环渤海动力煤价格指数报收于737元/吨",
        "publish_time": "2021-12-29 15:00",
        "update_time": "2022-10-31 13:52:19",
        "news_source": "秦皇岛煤炭网",
        "content_fragments": (
            "2021年12月22日至2021年12月28日",
            "报收于737元/吨",
            "环比下行3元/吨",
        ),
    },
    "cqcoal_operator_api_2022_bspi_734": {
        "article_id": 114105,
        "title": "【BSPI】环渤海动力煤价格指数734元/吨",
        "publish_time": "2022-12-28 15:07",
        "update_time": "2023-01-05 16:40:37",
        "news_source": "秦皇岛煤炭网",
        "content_fragments": (
            "2022年12月21日至2022年12月27日",
            "报收于734元/吨",
            "环比持平",
        ),
    },
}


def validate_operator_sources() -> None:
    for source_id, expected in OPERATOR_API_EXPECTATIONS.items():
        record = source_record(source_id)
        path = ROOT / record["path"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        data = payload["data"]
        if int(data["id"]) != expected["article_id"]:
            raise ValueError(f"Operator article id changed for {source_id}")
        for field in ("title", "publishTime", "updateTime", "newsSource"):
            actual = data.get(field)
            wanted = expected[field.replace("Time", "_time").replace("Source", "_source")]
            if actual != wanted:
                raise ValueError(f"Operator {field} changed for {source_id}: {actual!r} != {wanted!r}")
        require_fragments(
            data.get("content") or "",
            expected["content_fragments"],
            source_id,
        )

        page_source_id = source_id.replace("_api_", "_page_")
        page = ROOT / source_record(page_source_id)["path"]
        page_text = page.read_text(encoding="utf-8")
        require_fragments(
            page_text,
            (f"varmId={expected['article_id']}", "vartId=234", "秦皇岛煤炭网版权声明"),
            page_source_id,
        )


def validate_search_gap_snapshot() -> None:
    record = source_record("cqcoal_operator_search_gap_2020_final_bspi_585")
    payload = json.loads((ROOT / record["path"]).read_text(encoding="utf-8"))
    exact, generic = payload["queries"]
    if exact["result_total"] != 0:
        raise ValueError("2020 final-period operator search is no longer empty")
    matched_titles = [item["title"] for item in generic["matches"]]
    if any("2020年12月23日至2020年12月29日" in title for title in matched_titles):
        raise ValueError("A target 2020 article unexpectedly appeared in the search snapshot")
    if payload["interpretation"].count("not the 2020-12-30 publication") != 1:
        raise ValueError("Search-gap interpretation text changed")


ATTRIBUTED_2020_PUBLICATION_EXPECTATIONS = {
    "china5e_attributed_bspi_2020_page_585": {
        "page_date": "2020-12-31",
        "fragments": (
            "2020年12月23日至2020年12月29日",
            "环渤海动力煤价格指数报收于585元/吨",
            "环比上行3元/吨",
            "1257.40点",
            "秦皇岛煤炭网",
        ),
    },
    "ehang_attributed_bspi_2020_page_585": {
        "page_date": "2020-12-30",
        "fragments": (
            "2020年12月23日至2020年12月29日",
            "环渤海动力煤价格指数报收于585元/吨",
            "环比上行3元/吨",
            "1257.40点",
            "（齐红）",
            "来源：秦皇岛煤炭网",
        ),
    },
}


def validate_2020_attributed_sources() -> None:
    for source_id, expected in ATTRIBUTED_2020_PUBLICATION_EXPECTATIONS.items():
        record = source_record(source_id)
        path = ROOT / record["path"]
        text = path.read_text(encoding="utf-8")
        require_fragments(text, expected["fragments"], source_id)
        if expected["page_date"] not in stripped_text(text):
            raise ValueError(f"{source_id} page date is missing: {expected['page_date']}")


def validate_corroborating_sources() -> None:
    expectations = {
        "china5e_attributed_bspi_2018_page_569": {
            "page_date": "2018-12-27",
            "fragments": (
                "2018年12月19日至2018年12月25日",
                "环渤海动力煤价格指数报收于569元/吨",
                "环比下降1元/吨",
                "秦皇岛煤炭网",
            ),
        },
        "hebccw_attributed_bspi_2018_page_569": {
            "page_date": "2018-12-27",
            "fragments": (
                "2018年12月19日至2018年12月25日",
                "环渤海动力煤价格指数报收于569元/吨",
                "环比下降1元/吨",
                "河北港口集团秦皇岛海运煤炭交易市场发布",
            ),
        },
        "cctd_market_commentary_2019_bspi_551": {
            "page_date": "2019-12-26",
            "fragments": (
                "2019年12月18日至2019年12月24日",
                "环渤海动力煤价格指数报收于551元/吨",
                "环比上涨1元/吨",
                "来源：瑞达期货",
            ),
        },
        "cei_bspi_2020_page_585": {
            "page_date": "2020-12-31",
            "fragments": (
                "环渤海动力煤价格指数585元/吨",
                "2020-12-31",
            ),
            "raw_fragments": (CEI_ARTICLE_PATH_FRAGMENT,),
        },
        "coalchina_attributed_bspi_2018_page_569": {
            "page_date": "2018-12-26",
            "fragments": (
                "2018年12月19日至2018年12月25日",
                "环渤海动力煤价格指数报收于569元/吨",
                "环比下降1元/吨",
                "秦皇岛煤炭网",
            ),
        },
        "hebeidaily_operator_group_news_2018_bspi_569": {
            "page_date": "2018-12-31",
            "fragments": (
                "2018年12月19日至2018年12月25日",
                "环渤海动力煤价格指数报收于569元/吨",
                "环比下降1元/吨",
                "河北港口集团秦皇岛海运煤炭交易市场发布",
            ),
        },
        "china5e_attributed_bspi_2019_page_551": {
            "page_date": "2019-12-26",
            "fragments": (
                "2019年12月18日至2019年12月24日",
                "环渤海动力煤价格指数报收于551元/吨",
                "环比上涨1元/吨",
                "秦皇岛煤炭网",
            ),
        },
        "cwestc_attributed_bspi_2019_page_551": {
            "page_date": "2019/12/26",
            "fragments": (
                "2019年12月18日至2019年12月24日",
                "环渤海动力煤价格指数报收于551元/吨",
                "环比上涨1元/吨",
                "来源：秦皇岛煤炭网",
            ),
        },
        "cwestc_attributed_bspi_2020_page_585": {
            "page_date": "2020/12/31",
            "fragments": (
                "2020年12月23日至2020年12月29日",
                "环渤海动力煤价格指数报收于585元/吨",
                "环比上行3元/吨",
                "1257.40点",
                "来源：秦皇岛煤炭网",
            ),
        },
        "in_en_attributed_bspi_2020_page_585": {
            "page_date": "2020-12-30",
            "fragments": (
                "2020年12月23日至2020年12月29日",
                "环渤海动力煤价格指数报收于585元/吨",
                "环比上行3元/吨",
                "1257.40点",
                "来源：秦皇岛煤炭网",
            ),
        },
    }
    for source_id, expected in expectations.items():
        record = source_record(source_id)
        text = (ROOT / record["path"]).read_text(encoding=record["encoding"] or "utf-8")
        require_fragments(text, expected["fragments"], source_id)
        for raw_fragment in expected.get("raw_fragments", ()):
            if raw_fragment not in text:
                raise ValueError(f"{source_id} is missing raw fragment: {raw_fragment}")
        if expected["page_date"] not in stripped_text(text):
            raise ValueError(f"{source_id} page date is missing: {expected['page_date']}")


def validate_specs_against_prior_evidence() -> None:
    validate_operator_sources()
    validate_search_gap_snapshot()
    validate_2020_attributed_sources()
    validate_corroborating_sources()
    endpoints = endpoint_last_rows()
    reports = reconciliation_rows()
    for spec in PUBLICATION_SPECS:
        year = spec["year"]
        expected_endpoint = {
            "date": spec["endpoint_last_date"],
            "value": spec["endpoint_last_value"],
        }
        if endpoints[year] != expected_endpoint:
            raise ValueError(f"Endpoint expectation changed for {year}")
        report_value = reports[year]["issuer_reported_period_end_price_cny_per_tonne"]
        if int(report_value) != spec["annual_report_period_end_value"]:
            raise ValueError(f"Annual-report expectation changed for {year}")


def publication_records() -> list[dict]:
    return [
        {
            "id": spec["id"],
            "year": spec["year"],
            "instrument": "BSPI",
            "grade": "5500_kcal_per_kg",
            "unit": "cny_per_tonne",
            "cited_value": spec["cited_value"],
            "reporting_period_start": spec["reporting_period_start"],
            "reporting_period_end": spec["reporting_period_end"],
            "page_publication_timestamp": spec["page_publication_timestamp"],
            "cited_release_date": spec["cited_release_date"],
            "source_role": spec["source_role"],
            "source_id": spec["source_id"],
            "secondary_source_id": spec.get("secondary_source_id"),
            "additional_secondary_source_ids": list(spec.get("additional_secondary_source_ids", ())),
            "cctd_hosted_republication_found": spec["cctd_hosted_republication_found"],
            "operator_primary_page_found": spec["operator_primary_page_found"],
            "secondary_attributed_republication_found": spec["secondary_attributed_republication_found"],
            "secondary_attributed_republication_count": (
                1 + len(spec.get("additional_secondary_source_ids", ()))
                if spec["secondary_attributed_republication_found"]
                else 0
            ),
            "operator_article_id": spec["operator_article_id"],
            "operator_publish_time": spec["operator_publish_time"],
            "operator_api_update_time": spec["operator_api_update_time"],
            "operator_source_label": spec["operator_source_label"],
            "calendar_year_final_publication": spec["calendar_year_final_publication"],
            "endpoint_last_observation": {
                "date": spec["endpoint_last_date"],
                "value": spec["endpoint_last_value"],
            },
            "annual_report_period_end_value": spec["annual_report_period_end_value"],
            "date_alignment_status": spec["date_alignment_status"],
            "mismatch_notes": (
                spec["mismatch_notes"]
                if isinstance(spec["mismatch_notes"], list)
                else [spec["mismatch_notes"]]
            ),
            "provenance_notes": (
                [spec["provenance_notes"]]
                if isinstance(spec.get("provenance_notes"), str)
                else list(spec.get("provenance_notes", ()))
            ),
            "model_input": None,
        }
        for spec in PUBLICATION_SPECS
    ]


def corroborating_publication_records() -> list[dict]:
    return [
        {
            "id": spec["id"],
            "source_id": spec["source_id"],
            "year": spec["year"],
            "instrument": "BSPI",
            "grade": "5500_kcal_per_kg",
            "unit": "cny_per_tonne",
            "cited_value": spec["cited_value"],
            "reporting_period_start": spec["reporting_period_start"],
            "reporting_period_end": spec["reporting_period_end"],
            "page_publication_timestamp": spec["page_publication_timestamp"],
            "source_date": spec["source_date"],
            "provenance_class": spec["provenance_class"],
            "explicit_operator_attribution": spec["explicit_operator_attribution"],
            "article_path_fragment": spec.get("article_path_fragment"),
            "access_scope": spec.get("access_scope"),
            "full_article_access": spec.get("full_article_access"),
            "notes": spec["notes"],
            "model_input": None,
        }
        for spec in CORROBORATING_PUBLICATION_SPECS
    ]


def build() -> dict:
    validate_specs_against_prior_evidence()
    sources = {source_id: source_record(source_id) for source_id in RAW_SOURCES}
    publications = publication_records()
    corroborations = corroborating_publication_records()
    operator = [item for item in publications if item["operator_primary_page_found"]]
    cctd = [item for item in publications if item["cctd_hosted_republication_found"]]
    secondary = [item for item in publications if item["secondary_attributed_republication_found"]]
    final = [item for item in publications if item["calendar_year_final_publication"]]
    independent_2020_secondary_pages = next(
        item["secondary_attributed_republication_count"]
        for item in publications
        if item["year"] == 2020
    )
    operator_missing_years = [2018, 2019, 2020]
    non_attributed_corroboration_count = sum(
        not item["explicit_operator_attribution"] for item in corroborations
    )

    return {
        "symbol": "601088",
        "review_date": REVIEW_DATE.isoformat(),
        "engineering_status": "bspi_point_in_time_publications_package_complete",
        "status": "operator_articles_archived_source_layers_corrected_without_model_inputs",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
             "Archive addressable BSPI publication pages and correct the provenance layers: "
             "CCTD pages are republications, Qinhuangdao Coal Network article pages are operator "
             "publications, and China5e/E-Hang pages remain explicitly attributed secondary republications. "
             "CoalChina, Hebei Economic Daily, CWESTC and In-en pages are separately retained as corroboration. "
             "Cited values remain research-only provenance, never normalized cyclical model inputs."
        ),
        "scope": {
            "publication_years": [item["year"] for item in publications],
            "secondary_corroboration_only_years": [2018, 2019],
            "not_collected_years": [2023, 2024, 2025],
            "operator_primary_article_years": [item["year"] for item in operator],
            "cctd_hosted_republication_years": [item["year"] for item in cctd],
            "secondary_attributed_republication_years": [item["year"] for item in secondary],
            "operator_primary_article_missing_years": operator_missing_years,
            "retrieval_date": REVIEW_DATE.isoformat(),
            "search_date": REVIEW_DATE.isoformat(),
            "search_note": (
                "The current Qinhuangdao Coal Network search index and the complete public "
                "column-234 listing do not contain the exact 2020-12-23 to 2020-12-29 BSPI 585 "
                "article. Operator article IDs 80997, 110846 and 114105 were located for 2017, "
                "2021 and 2022. Absence is recorded; it is not proof that a 2020 operator page never existed. "
                "2018 and 2019 have secondary corroboration only; 2023 onward is out of the retained "
                "BSPI publication set because the issuer benchmark switches to NCEI."
            ),
        },
        "publisher_provenance": PUBLISHER_PROVENANCE,
        "original_availability": ORIGINAL_AVAILABILITY,
        "summary": {
            "operator_primary_publication_pages": len(operator),
            "cctd_hosted_republication_pages": len(cctd),
            "attributed_secondary_republication_pages": len(secondary),
            "independent_2020_secondary_republication_pages": independent_2020_secondary_pages,
            "secondary_corroborating_pages": len(corroborations),
            "secondary_corroboration_only_years": [2018, 2019],
            "non_attributed_corroborating_pages": non_attributed_corroboration_count,
            "calendar_year_final_publications_archived": len(final),
            "calendar_year_final_publication_years": [item["year"] for item in final],
            "date_alignment_issue_years": [
                item["year"] for item in publications if item["date_alignment_status"] != "reconciled"
            ],
            "operator_primary_article_missing_years": operator_missing_years,
            "operator_primary_article_missing_years_remain_unresolved": bool(operator_missing_years),
            "missing_years_interpolated": False,
            "registered_cyclical_model_inputs": 0,
        },
        "publications": publications,
        "corroborating_publications": corroborations,
        "specific_findings": [
            {
                "id": "cctd_pages_reclassified_as_hosted_republications",
                "fact": "The retained 2014, 2015 and 2016 CCTD pages are CCTD-hosted republications, not Qinhuangdao Coal Network operator original pages.",
            },
            {
                "id": "exact_operator_articles_archived_2017_2021_2022",
                "fact": "Qinhuangdao Coal Network API and page snapshots were retained for exact BSPI 577, 737 and 734 articles published on 2017-12-27, 2021-12-29 and 2022-12-28.",
            },
            {
                "id": "2014_page_525_is_not_calendar_year_final_publication",
                "fact": "The retained 2014 CCTD page reports 525 for 2014-12-17 to 2014-12-23, but the endpoint has 523 on 2014-12-31, so the page is not a calendar-year-final observation.",
            },
            {
                "id": "2017_final_publication_577_differs_from_annual_report_578",
                "fact": "The final 2017 BSPI publication is 577; the issuer annual-report period-end value is 578, which appears in the endpoint on 2017-11-08. They are not reconciled into one endpoint.",
            },
            {
                "id": "operator_primary_article_missing_for_2020_final_period",
                "fact": "The current operator search index has no exact 2020-12-23 to 2020-12-29 BSPI 585 article, even though the 2020-12-23 582 and 2021-01-06 593 articles are addressable. China5e and E-Hang provide two independently addressable attributed republications; the CEI listing exposes the exact 585 title and 2020-12-31 date but its linked article is login-gated. None supplies an operator original.",
            },
            {
                "id": "cei_2020_page_title_date_only_login_gated",
                "fact": "The CEI listing page exposes only the exact title, 2020-12-31 listing date and article path. The linked article is login-gated, so this page is not full-text corroboration and provides no explicit operator attribution.",
            },
            {
                "id": "2018_operator_original_not_evidenced",
                "fact": "The 2018 final-period 569 is retained only through a China5e explicit republication and a Great Wall Network report attributed to the Qinhuangdao Maritime Coal Exchange. No operator article page or API response was retrieved.",
            },
            {
                "id": "2019_operator_original_not_evidenced",
                "fact": "The 2019 final-period 551 is retained only through a CCTD-hosted Ruitian Futures market commentary. The page is not an attributed BSPI republication and no operator article was retrieved.",
            },
            {
                "id": "ncei_2023_2025_original_publication_records_not_evidenced",
                "fact": "An operator-domain search on 2026-09-22 returned no source-addressable original NCEI monthly publication or revision page for 2023-2025. Third-party search snippets and membership-gated rows are not recorded as a completed point-in-time series.",
            },
            {
                "id": "operator_cms_update_times_are_retained",
                "fact": "The three exact operator articles carry later CMS updateTime values (2022 or 2023), so current bytes corroborate addressable pages but do not prove revision-free historical publication.",
            },
            {
                "id": "no_publication_value_is_registered_as_model_input",
                "fact": "Every publication has model_input=null and the package has no registered cyclical operating inputs.",
            },
            {
                "id": "additional_corroboration_pages_do_not_replace_operator_originals",
                "fact": "Six additional 2018-2020 third-party pages strengthen independent textual corroboration, but every one remains secondary provenance and the missing operator originals stay unresolved.",
            },
        ],
        "definition_breaks": [
            "A CCTD-hosted page is not the same provenance class as a Qinhuangdao Coal Network operator article page.",
            "A page publication timestamp is not necessarily the BSPI release date.",
            "A China5e attributed page is secondary provenance even when it repeats the exact period and value.",
            "Multiple independent secondary republications corroborate a text but still cannot become an operator original.",
            "A news report attributed to the operator group is not the same object as an operator article page.",
            "An industry association republication is a third-party republication even when it carries an operator source label.",
            "A third-party market-commentary quotation is weaker than an explicit source attribution and is not a republication.",
            "A secondary index listing without operator attribution is corroboration, not independent attributed provenance.",
            "A title/date listing page with a login-gated article link does not provide full-text corroboration.",
            "The final 2017 value 577 and the issuer annual-report value 578 are separate observations.",
            "BSPI remains separate from NCEI/CCTD instruments; this package does not concatenate series.",
        ],
        "registered_cyclical_facts_operating_inputs": [],
        "point_in_time_policy": [
            "Source pages are known only on or after their retrieval date; displayed publication timestamps are retained separately.",
            "Hash-bound 2026 downloads corroborate addressable pages, but the operator CMS updateTime fields and current bytes do not prove the pages were never revised after first publication.",
            "Qinhuangdao Coal Network API publishTime values are operator metadata, not cryptographic timestamps.",
            "Secondary republications corroborate values only when attribution is explicit; they are not operator originals.",
            "Multiple independent attributed republications strengthen corroboration but do not change provenance class.",
            "Industry association, print-news and energy-portal republications strengthen the text record but do not close an operator-original absence.",
            "2018 and 2019 final BSPI values 569 and 551 are retained only as secondary corroborations; their operator originals remain ORIGINAL_NOT_EVIDENCED.",
            "The CEI 2020 title/date listing addresses the 585 headline, but its login-gated article is not full-text provenance.",
            "2023 onward NCEI publication/revision records are not source-addressably archived; that absence is recorded and never transformed into a synthetic series.",
            "The missing 2020 final-period operator article and missing years remain explicitly unresolved and are never interpolated.",
            "A close or exact endpoint match is provenance corroboration, not model eligibility.",
        ],
        "forbidden_calculations": [
            "Register any BSPI publication value as a normalized bear/base/bull cyclical model input.",
            "Fill the missing 2020 operator article by interpolation or by promoting any secondary republication to primary evidence.",
            "Use the 2018 or 2019 secondary values 569 or 551 as verified final point-in-time inputs.",
            "Promote CoalChina, Hebei Economic Daily, China5e 2019, CWESTC or In-en republications to operator originals.",
            "Treat the CCTD 2019 Ruitian Futures quotation as an attributed BSPI republication.",
            "Treat the CEI 2020 title/date listing or its login-gated article as full-text attributed corroboration.",
            "Promote 2023-2025 NCEI values from search snippets or membership-hidden rows into model inputs.",
            "Reconcile 2017 final publication 577 and issuer annual-report value 578 into one endpoint.",
            "Treat the 2014 page value 525 as the calendar-year-final publication.",
            "Treat a China5e page timestamp as the BSPI release date.",
            "Treat an operator CMS updateTime as the original first-publication timestamp.",
        ],
        "blockers": [
            "operator_primary_article_missing_for_2020_final_period",
            "operator_primary_articles_missing_for_2018_and_2019",
            "ncei_2023_2025_original_publication_records_not_evidenced",
            "2014_cctd_page_is_not_calendar_year_final_publication",
            "2017_final_publication_and_annual_report_value_not_reconciled",
            "current_page_bytes_do_not_prove_revision_free_historical_publication",
            "no_normalized_cyclical_operating_inputs_registered",
        ],
        "evidence_refs": [
            source_ref(sources["cctd_bspi_overview_20140918"], description="CCTD operator BSPI overview and methodology"),
            source_ref(sources["cctd_bspi_2014_page_525"], description="CCTD-hosted republication for BSPI 525 on 2014-12-17 to 2014-12-23"),
            source_ref(sources["cctd_bspi_2015_page_372"], description="CCTD-hosted republication for BSPI 372 on 2015-12-23 to 2015-12-29"),
            source_ref(sources["cctd_bspi_2016_page_593"], description="CCTD-hosted republication for BSPI 593 on 2016-12-21 to 2016-12-27"),
            source_ref(sources["cqcoal_operator_api_2017_bspi_577"], description="Qinhuangdao Coal Network operator API article 80997 for BSPI 577"),
            source_ref(sources["cqcoal_operator_page_2017_bspi_577"], description="Qinhuangdao Coal Network addressable page for operator article 80997"),
            source_ref(sources["cqcoal_operator_api_2021_bspi_737"], description="Qinhuangdao Coal Network operator API article 110846 for BSPI 737"),
            source_ref(sources["cqcoal_operator_page_2021_bspi_737"], description="Qinhuangdao Coal Network addressable page for operator article 110846"),
            source_ref(sources["cqcoal_operator_api_2022_bspi_734"], description="Qinhuangdao Coal Network operator API article 114105 for BSPI 734"),
            source_ref(sources["cqcoal_operator_page_2022_bspi_734"], description="Qinhuangdao Coal Network addressable page for operator article 114105"),
            source_ref(sources["china5e_attributed_bspi_2017_page_577"], description="Attributed Qinhuangdao Coal Network republication of BSPI 577"),
            source_ref(sources["china5e_attributed_bspi_2020_page_585"], description="Attributed Qinhuangdao Coal Network republication of BSPI 585"),
            source_ref(sources["ehang_attributed_bspi_2020_page_585"], description="Attributed Qinhuangdao Coal Network republication of BSPI 585"),
            source_ref(sources["china5e_attributed_bspi_2021_page_737"], description="Attributed Qinhuangdao Coal Network republication of BSPI 737"),
            source_ref(sources["china5e_attributed_bspi_2022_page_734"], description="Attributed Qinhuangdao Coal Network republication of BSPI 734"),
            source_ref(sources["china5e_attributed_bspi_2018_page_569"], description="Attributed Qinhuangdao Coal Network republication of BSPI 569"),
            source_ref(sources["hebccw_attributed_bspi_2018_page_569"], description="Great Wall Network operator-group news report for BSPI 569"),
            source_ref(sources["cctd_market_commentary_2019_bspi_551"], description="CCTD-hosted third-party commentary quoting BSPI 551"),
            source_ref(sources["cei_bspi_2020_page_585"], description="CEI title/date listing for BSPI 585; linked article is login-gated and has no explicit operator attribution"),
            source_ref(sources["coalchina_attributed_bspi_2018_page_569"], description="China National Coal Association attributed republication of BSPI 569"),
            source_ref(sources["hebeidaily_operator_group_news_2018_bspi_569"], description="Hebei Economic Daily operator-group news report for BSPI 569"),
            source_ref(sources["china5e_attributed_bspi_2019_page_551"], description="Attributed Qinhuangdao Coal Network republication of BSPI 551"),
            source_ref(sources["cwestc_attributed_bspi_2019_page_551"], description="Attributed Qinhuangdao Coal Network republication of BSPI 551"),
            source_ref(sources["cwestc_attributed_bspi_2020_page_585"], description="Attributed Qinhuangdao Coal Network republication of BSPI 585"),
            source_ref(sources["in_en_attributed_bspi_2020_page_585"], description="Attributed Qinhuangdao Coal Network republication of BSPI 585"),
            source_ref(sources["cqcoal_operator_search_gap_2020_final_bspi_585"], description="Operator search-index gap snapshot for the missing 2020 final BSPI 585 article"),
            {
                "id": "cctd_bspi_historical_endpoint",
                "path": str(BSPI_PATH.relative_to(ROOT)),
                "sha256": BSPI_HASH,
                "description": "Raw BSPI JSON endpoint used only to check date/value alignment",
            },
            prior_ref(RECONCILIATION_POINTER, "shenhua_bspi_annual_report_reconciliation", description="Prior BSPI endpoint and issuer annual-report reconciliation"),
            prior_ref(EXTERNAL_INDEX_POINTER, "shenhua_external_index_provenance", description="Prior operator provenance and membership restrictions"),
            prior_ref(PRICE_COST_BRIDGE_POINTER, "shenhua_price_cost_transport_bridge", description="Prior issuer-reported annual price commentary"),
            prior_ref(PUBLIC_INDEX_POINTER, "shenhua_public_index_history", description="Prior CCTD public historical index archive"),
        ],
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    source_hashes = {source_id: source_record(source_id)["sha256"] for source_id in RAW_SOURCES}
    source_hashes["cctd_bspi_historical_endpoint"] = BSPI_HASH
    prior_hashes = {
        "shenhua_bspi_annual_report_reconciliation": json.loads(RECONCILIATION_POINTER.read_text(encoding="utf-8"))["sha256"],
        "shenhua_external_index_provenance": json.loads(EXTERNAL_INDEX_POINTER.read_text(encoding="utf-8"))["sha256"],
        "shenhua_price_cost_transport_bridge": json.loads(PRICE_COST_BRIDGE_POINTER.read_text(encoding="utf-8"))["sha256"],
        "shenhua_public_index_history": json.loads(PUBLIC_INDEX_POINTER.read_text(encoding="utf-8"))["sha256"],
    }
    manifest = {
        "script_sha256": sha256(Path(__file__).resolve()),
        "evidence_sha256": digest,
        "source_sha256s": source_hashes,
        "prior_evidence_sha256s": prior_hashes,
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
        "summary": payload["summary"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

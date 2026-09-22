"""Build a source-addressed Shenhua public coal-index history package."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/company-research/shenhua-public-index-history-20260922"
POINTER = ROOT / "runtime/company-research/shenhua-public-index-history-latest.json"
PRIOR_INDEX_POINTER = ROOT / "runtime/company-research/shenhua-external-index-provenance-latest.json"
PAGE = ROOT / "runtime/company-research/cctd-index-center-20260918.html"
PAGE_URL = "https://www.cctd.com.cn/index.php?m=content&c=index&a=lists&catid=520"

REVIEW_DATE = date(2026, 9, 22)

RAW_SOURCES = {
    "bspi": {
        "filename": "BSPI.json",
        "url": "https://www.cctd.com.cn/Echarts/data/BSPI.php",
        "sha256": "069cde6b91be135bfa229a302533cfbfc670b36609515a2f4cae18cb3748083f",
        "content_type": "text/html; charset=UTF-8",
        "payload_format": "json_array",
        "request_method": "POST_with_empty_form_body",
        "endpoint_code": "BSPI",
        "chart_title": "环渤海动力煤价格指数（BSPI）走势图",
        "series_name": "环渤海动力煤价格指数（BSPI）",
        "displayed_unit": "元/吨",
        "page_current_table_date": "2026-09-16",
        "page_acronym_discrepancy": None,
        "role": "Public CCTD chart endpoint for the Bohai Rim thermal-coal price index",
    },
    "ctpi": {
        "filename": "CTPI.json",
        "url": "https://www.cctd.com.cn/Echarts/data/CTPI.php",
        "sha256": "fcf2ba36ebfe904fffedafd06dd34c537de21ea5d513f63744bb12f990a48530",
        "content_type": "text/html; charset=UTF-8",
        "payload_format": "json_array",
        "request_method": "POST_with_empty_form_body",
        "endpoint_code": "CTPI",
        "chart_title": "太原煤炭价格（动力煤5500综合价）走势图",
        "series_name": "太原煤炭价格指数（TCPI）",
        "displayed_unit": "点",
        "page_current_table_date": "2026-09-18",
        "page_acronym_discrepancy": "endpoint_uses_ctpi_but_page_table_uses_tcpi",
        "role": "Public CCTD chart endpoint for Taiyuan thermal-coal 5500 composite price",
    },
    "scpi": {
        "filename": "SCPI.json",
        "url": "https://www.cctd.com.cn/Echarts/data/SCPI.php",
        "sha256": "db89c5109d09cb2bbea85e8a31d542d62c6061d5a5efca04d051fa08fe555830",
        "content_type": "text/html; charset=UTF-8",
        "payload_format": "json_array",
        "request_method": "POST_with_empty_form_body",
        "endpoint_code": "SCPI",
        "chart_title": "陕西煤炭价格（陕西煤炭综合价）走势图",
        "series_name": "陕西煤炭价格指数（SCPI）",
        "displayed_unit": "点",
        "page_current_table_date": "2026-09-18",
        "page_acronym_discrepancy": None,
        "role": "Public CCTD chart endpoint for Shaanxi thermal-coal composite price",
    },
    "ospi": {
        "filename": "OSPI.json",
        "url": "https://www.cctd.com.cn/Echarts/data/OSPI.php",
        "sha256": "96881acb1e0f77e758a2dae74279f6a184bc687bc0f4ef20d2ff38ed49870aa8",
        "content_type": "text/html; charset=UTF-8",
        "payload_format": "json_array",
        "request_method": "POST_with_empty_form_body",
        "endpoint_code": "OSPI",
        "chart_title": "鄂尔多斯混煤价格指数（OSPI）",
        "series_name": "鄂尔多斯混煤价格指数（OSPI）",
        "displayed_unit": "未标注",
        "page_current_table_date": "2026-09-18",
        "page_acronym_discrepancy": None,
        "role": "Public CCTD chart endpoint for Ordos blended-coal price index",
    },
    "ybspi": {
        "filename": "YBSPI.json",
        "url": "https://www.cctd.com.cn/Echarts/data/YBSPI.php",
        "sha256": "687459a992067bc1dd2b3b10c1740e8ddf6d5225352c4a23a8c6b8ead20e3db2",
        "content_type": "text/html; charset=UTF-8",
        "payload_format": "json_array",
        "request_method": "POST_with_empty_form_body",
        "endpoint_code": "YBSPI",
        "chart_title": "长江口动力煤价格指数(YBSPI)走势图",
        "series_name": "长江口动力煤价格指数(YBSPI)",
        "displayed_unit": "元/吨",
        "page_current_table_date": "2025-11-28",
        "page_acronym_discrepancy": None,
        "role": "Public CCTD chart endpoint for Yangtze River mouth thermal-coal price index",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retrieved_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def require_hash(path: Path, expected: str, label: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"{label} hash mismatch: expected {expected}, got {actual}")


def series_rows(source_id: str) -> list[dict]:
    path = OUT / RAW_SOURCES[source_id]["filename"]
    require_hash(path, RAW_SOURCES[source_id]["sha256"], source_id)
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{source_id} endpoint did not return a non-empty array")

    previous = None
    validated = []
    for index, row in enumerate(rows):
        if set(row) != {"name", "age"}:
            raise ValueError(f"{source_id} row {index} has unexpected keys: {sorted(row)}")
        raw_date = row["name"]
        raw_value = row["age"]
        try:
            observation_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError as error:
            raise ValueError(f"{source_id} row {index} has an invalid date: {raw_date}") from error
        if previous is not None and observation_date <= previous:
            raise ValueError(f"{source_id} dates are not strictly increasing at row {index}")
        value = Decimal(str(raw_value))
        if not value.is_finite():
            raise ValueError(f"{source_id} row {index} has a non-finite value: {raw_value}")
        validated.append({
            "observation_date": raw_date,
            "value": raw_value,
            "value_decimal": str(value),
            "model_input": None,
        })
        previous = observation_date
    return validated


def source_record(source_id: str) -> dict:
    spec = RAW_SOURCES[source_id]
    path = OUT / spec["filename"]
    require_hash(path, spec["sha256"], source_id)
    return {
        "id": f"cctd_{source_id}_historical_endpoint",
        "endpoint_code": spec["endpoint_code"],
        "url": spec["url"],
        "path": str(path.relative_to(ROOT)),
        "sha256": spec["sha256"],
        "retrieved_at_utc": retrieved_at(path),
        "byte_size": path.stat().st_size,
        "http_response_content_type": spec["content_type"],
        "payload_format": spec["payload_format"],
        "request_method": spec["request_method"],
        "source_role": spec["role"],
    }


def page_record() -> dict:
    actual = sha256(PAGE)
    expected = "e73ba4f2d6e4380730fd7632d61c66988cc18caea5b36cea320c43591944f5bf"
    if actual != expected:
        raise ValueError(f"CCTD index-center page hash mismatch: {actual}")
    return {
        "id": "cctd_index_center_page",
        "url": PAGE_URL,
        "path": str(PAGE.relative_to(ROOT)),
        "sha256": actual,
        "retrieved_at_utc": retrieved_at(PAGE),
        "byte_size": PAGE.stat().st_size,
        "content_type": "text/html",
        "source_role": "Public CCTD index-center page that labels the five chart endpoints",
    }


def prior_ref(pointer: Path, ref_id: str, *, description: str) -> dict:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    target = ROOT / pin["path"] / "evidence.json"
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError(f"Prior evidence pointer escapes project root: {pointer}")
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
    page = page_record()
    sources = {source_id: source_record(source_id) for source_id in RAW_SOURCES}
    series = {}
    for source_id, spec in RAW_SOURCES.items():
        rows = series_rows(source_id)
        values = [Decimal(row["value_decimal"]) for row in rows]
        series[source_id] = {
            "source_id": sources[source_id]["id"],
            "endpoint_code": spec["endpoint_code"],
            "chart_title": spec["chart_title"],
            "series_name": spec["series_name"],
            "displayed_unit": spec["displayed_unit"],
            "page_current_table_date": spec["page_current_table_date"],
            "page_acronym_discrepancy": spec["page_acronym_discrepancy"],
            "observation_count": len(rows),
            "first_observation_date": rows[0]["observation_date"],
            "first_observation_value": rows[0]["value"],
            "last_observation_date": rows[-1]["observation_date"],
            "last_observation_value": rows[-1]["value"],
            "minimum_observation_value": str(min(values)),
            "maximum_observation_value": str(max(values)),
            "observations": rows,
            "provenance_class": "public_industry_association_chart_endpoint",
            "model_input": None,
        }

    return {
        "symbol": "601088",
        "review_date": REVIEW_DATE.isoformat(),
        "engineering_status": "public_index_history_package_complete",
        "status": "public_cctd_historical_chart_series_archived_not_reconciled",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
            "Retain the five public historical chart series exposed by the CCTD index-center page. "
            "Each row is a research observation. None of these values is a normalized cyclical input."
        ),
        "publisher": "CCTD 中国煤炭市场网 (www.cctd.com.cn)",
        "publisher_class": "industry_association_public_website",
        "public_page": page,
        "series": series,
        "specific_findings": [
            {
                "id": "five_public_chart_endpoints_are_source_addressable",
                "fact": "The five chart endpoints referenced by the public CCTD index-center page returned complete JSON arrays without a membership login.",
            },
            {
                "id": "bspi_public_archive_spans_2010_to_2026",
                "fact": "BSPI has 802 unique observation dates from 2010-06-29 through 2026-09-16, with retained values from 371 to 854.",
            },
            {
                "id": "regional_series_have_limited_or_stale_coverage",
                "fact": "CTPI starts in 2024, SCPI starts in 2016, OSPI starts in 2014, and the retained YBSPI series ends on 2025-11-28.",
            },
            {
                "id": "ncei_cctd_ceci_historical_tables_remain_membership_gated",
                "fact": "These public chart endpoints do not replace the NCEI/CCTD/CECI paid historical tables documented by the prior provenance package.",
            },
            {
                "id": "bspi_hosting_requires_operator_reconciliation",
                "fact": "The BSPI series is hosted on CCTD's site, while the NDRC trial notice names Qinhuangdao Maritime Coal Exchange and China Price Association as organizers and publication channels; operator publication records must be reconciled before use.",
            },
            {
                "id": "endpoint_and_page_labels_are_not_self_describing",
                "fact": "The CTPI endpoint is labeled TCPI on the page, displayed units differ across series, OSPI has no displayed unit, and historical publication schedules contain gaps.",
            },
        ],
        "definition_breaks": [
            "BSPI and NCEI are separate instruments and cannot be concatenated into one price series.",
            "CTPI endpoint code and TCPI page label are inconsistent and require an operator methodology record.",
            "The five series have different start dates, end dates, units and publication cadences.",
            "A current archive downloaded in 2026 does not prove that each historical row was publicly known on its observation date or that it was never revised.",
        ],
        "registered_cyclical_facts_operating_inputs": [],
        "point_in_time_policy": [
            "Raw endpoint payloads are retained byte-for-byte with URL, SHA-256 and retrieval time.",
            "Each observation date comes from the endpoint; it is a source observation date, not proof of first-public availability.",
            "Missing dates are recorded as gaps and are never interpolated.",
            "Public access at retrieval time is observed access, not a legal grant of redistribution or unchanged availability.",
            "Historical values may have been revised by the publisher and must be reconciled with operator publication records before point-in-time use.",
        ],
        "forbidden_calculations": [
            "Use any endpoint value directly as a Shenhua normalized bear/base/bull price input.",
            "Concatenate BSPI, NCEI, CTPI, SCPI, OSPI or YBSPI into one homogeneous coal-price series.",
            "Impute missing dates or interpolate gaps to create a continuous series.",
            "Derive Shenhua fair value from index levels before route, tax, contract-mix and internal-transfer reconciliation.",
            "Treat annual descriptive statistics of this downloaded archive as approved cycle inputs.",
        ],
        "blockers": [
            "public_cctd_chart_archives_not_reconciled_with_operator_publication_records",
            "ncei_cctd_ceci_historical_tables_remain_membership_gated",
            "series_units_codes_and_publication_schedules_require_operator_metadata",
            "shenhua_internal_coal_electricity_transfer_and_route_cost_remain_unreconciled",
            "no_normalized_cyclical_operating_inputs_registered",
        ],
        "evidence_refs": [
            {
                "id": page["id"],
                "path": page["path"],
                "sha256": page["sha256"],
                "description": "CCTD public index-center page with series titles, labels and current tables",
            },
            *[
                {
                    "id": source["id"],
                    "path": source["path"],
                    "sha256": source["sha256"],
                    "description": f"CCTD public {source['endpoint_code']} historical chart payload",
                }
                for source in sources.values()
            ],
            prior_ref(
                PRIOR_INDEX_POINTER,
                "shenhua_external_index_provenance",
                description="Prior NCEI/BSPI/CCTD operator and methodology provenance package",
            ),
        ],
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    prior_pin = json.loads(PRIOR_INDEX_POINTER.read_text(encoding="utf-8"))
    manifest = {
        "script_sha256": sha256(Path(__file__).resolve()),
        "evidence_sha256": digest,
        "source_sha256s": {
            **{source_id: spec["sha256"] for source_id, spec in RAW_SOURCES.items()},
            "cctd_index_center_page": sha256(PAGE),
        },
        "prior_evidence_sha256s": {
            "shenhua_external_index_provenance": prior_pin["sha256"].lower(),
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
        "series": {
            source_id: {
                "rows": series["observation_count"],
                "first": series["first_observation_date"],
                "last": series["last_observation_date"],
            }
            for source_id, series in payload["series"].items()
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

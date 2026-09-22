"""Reconcile the public BSPI chart archive with Shenhua annual-report averages."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/company-research/shenhua-bspi-annual-report-reconciliation-20260922"
POINTER = ROOT / "runtime/company-research/shenhua-bspi-annual-report-reconciliation-latest.json"
BSPI_PATH = ROOT / "runtime/company-research/shenhua-public-index-history-20260922/BSPI.json"
PUBLIC_INDEX_POINTER = ROOT / "runtime/company-research/shenhua-public-index-history-latest.json"
BRIDGE_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json"

REVIEW_DATE = date(2026, 9, 22)
BSPI_HASH = "069cde6b91be135bfa229a302533cfbfc670b36609515a2f4cae18cb3748083f"


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


def decimal(value: Decimal, digits: int = 2) -> str:
    with localcontext() as context:
        context.prec = 40
        return format(value.quantize(Decimal("1").scaleb(-digits), rounding=ROUND_HALF_UP), "f")


def load_bspi_rows() -> list[dict]:
    actual = sha256(BSPI_PATH)
    if actual != BSPI_HASH:
        raise ValueError(f"BSPI endpoint hash mismatch: {actual}")
    rows = json.loads(BSPI_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("BSPI endpoint did not return a non-empty array")
    return rows


def annual_rows(rows: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        year = int(row["name"][:4])
        grouped.setdefault(year, []).append(row)
    return grouped


def mean(rows: list[dict]) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return sum((Decimal(row["age"]) for row in rows), Decimal(0)) / len(rows)


def build() -> dict:
    _, public_index_target, _ = pointer_payload(PUBLIC_INDEX_POINTER)
    _, bridge_target, _ = pointer_payload(BRIDGE_POINTER)
    public_index = json.loads(public_index_target.read_text(encoding="utf-8"))
    bridge = json.loads(bridge_target.read_text(encoding="utf-8"))
    if public_index["series"]["bspi"]["observation_count"] != 802:
        raise ValueError("Pinned public BSPI history coverage changed")

    report_rows = {
        item["year"]: item
        for item in bridge["external_price_envelope"]
    }
    by_year = annual_rows(load_bspi_rows())
    comparisons = []

    for year in range(2014, 2026):
        rows = by_year[year]
        endpoint_mean = mean(rows)
        endpoint_last = rows[-1]["age"]
        report = report_rows[year]
        reported_average = report.get("annual_average_price_cny_per_tonne")
        reported_end = report.get("period_end_price_cny_per_tonne")
        is_bohai_rim = report.get("benchmark") == "bohai_rim_5500_kcal"

        if reported_average is None:
            report_status = (
                "no_comparable_annual_average"
                if report.get("benchmark") is None
                else "issuer_reported_range_only"
            )
            difference = None
        elif is_bohai_rim:
            report_status = "annual_average_reconciled"
            difference = endpoint_mean - Decimal(str(reported_average))
        else:
            report_status = "issuer_benchmark_switched_to_ncei"
            difference = None

        end_difference = (
            Decimal(endpoint_last) - Decimal(str(reported_end))
            if is_bohai_rim and reported_end is not None
            else None
        )
        comparisons.append({
            "year": year,
            "endpoint_row_count": len(rows),
            "endpoint_simple_mean_cny_per_tonne": decimal(endpoint_mean),
            "issuer_reported_annual_average_cny_per_tonne": reported_average,
            "mean_difference_cny_per_tonne": decimal(difference) if difference is not None else None,
            "issuer_reported_period_end_price_cny_per_tonne": reported_end,
            "endpoint_last_observation_cny_per_tonne": endpoint_last,
            "period_end_difference_cny_per_tonne": (
                decimal(end_difference) if end_difference is not None else None
            ),
            "report_status": report_status,
            "model_input": None,
        })

    reconciled = [
        row for row in comparisons
        if row["mean_difference_cny_per_tonne"] is not None
    ]
    exact_ends = [
        row["year"] for row in comparisons
        if row["period_end_difference_cny_per_tonne"] == "0.00"
    ]
    off_by_date = [
        row["year"] for row in comparisons
        if row["period_end_difference_cny_per_tonne"] not in (None, "0.00")
    ]
    max_abs_difference = max(
        abs(Decimal(row["mean_difference_cny_per_tonne"])) for row in reconciled
    )

    return {
        "symbol": "601088",
        "review_date": REVIEW_DATE.isoformat(),
        "engineering_status": "bspi_annual_report_reconciliation_package_complete",
        "status": (
            "seven_bspi_annual_means_match_issuer_annual_report_averages_within_half_unit_research_only"
        ),
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
            "Compare the current public BSPI chart archive with Shenhua's point-in-time annual-report "
            "benchmark commentary. A match corroborates series identity; it does not create a model input."
        ),
        "comparison_method": {
            "archive": "BSPI JSON endpoint retrieved from www.cctd.com.cn on 2026-09-22",
            "annual_mean": "unweighted arithmetic mean of all endpoint rows whose observation date falls in the calendar year",
            "period_end": "last endpoint observation date and value in the calendar year compared with the issuer-reported year-end price",
            "comparison_scope": "2014 through 2025",
            "rounding": "two decimal places, half-up",
        },
        "comparisons": comparisons,
        "summary": {
            "comparable_reported_average_years": len(reconciled),
            "maximum_absolute_mean_difference_cny_per_tonne": decimal(max_abs_difference),
            "all_mean_differences_within_half_unit": max_abs_difference < Decimal("0.5"),
            "exact_year_end_matches": len(exact_ends),
            "exact_year_end_match_years": exact_ends,
            "year_end_off_by_date_alignment_years": off_by_date,
            "years_without_comparable_report_average": [
                row["year"] for row in comparisons if row["mean_difference_cny_per_tonne"] is None
            ],
        },
        "specific_findings": [
            {
                "id": "seven_reported_annual_averages_match_endpoint_means",
                "fact": "For 2014, 2015, 2016, 2017, 2020, 2021 and 2022, the unweighted annual means of the retained BSPI endpoint differ from Shenhua's disclosed annual averages by at most 0.49 CNY/tonne.",
            },
            {
                "id": "five_year_end_values_match_exactly",
                "fact": "2015, 2016, 2020, 2021 and 2022 endpoint year-end values exactly match the issuer-reported year-end prices; 2014 and 2017 differ by two and one CNY/tonne respectively.",
            },
            {
                "id": "endpoint_fills_two_missing_report_years_as_research_only",
                "fact": "The retained endpoint supplies annual means for 2018 and 2019, for which Shenhua's annual-report bridge has no comparable annual average; these remain research observations.",
            },
            {
                "id": "post_2022_issuer_benchmark_switches_to_ncei",
                "fact": "From 2023 the issuer annual-report bridge uses NCEI long-term prices, so BSPI annual means are not a like-for-like comparison after 2022.",
            },
            {
                "id": "current_archive_does_not_prove_historical_availability",
                "fact": "A 2026 download can be revised by the publisher; matching issuer annual averages corroborates instrument identity but does not prove each historical row was first publicly available on its observation date.",
            },
        ],
        "definition_breaks": [
            "BSPI and NCEI are separate instruments and cannot be concatenated.",
            "An endpoint's last observation in a calendar year is not necessarily the same publication date used by the issuer.",
            "A current public chart archive is not an operator point-in-time daily archive.",
        ],
        "registered_cyclical_facts_operating_inputs": [],
        "point_in_time_policy": [
            "The BSPI endpoint was retrieved on 2026-09-22 and is bound by SHA-256.",
            "Issuer annual-report facts retain their original filing dates and are read through the pinned bridge package.",
            "The arithmetic comparison is performed only on already retained source bytes.",
            "No missing date is interpolated and no future observation is used for a historical comparison.",
            "A close numerical match is corroboration, not a proof of revision-free point-in-time availability.",
        ],
        "forbidden_calculations": [
            "Register BSPI annual means as normalized bear/base/bull price inputs.",
            "Use 2018 or 2019 endpoint means without an operator point-in-time archive and methodology reconciliation.",
            "Concatenate BSPI endpoint values with NCEI long-term values after 2022.",
            "Treat a year-end endpoint value as the exact issuer publication-date value without aligning publication rules.",
        ],
        "blockers": [
            "bspi_endpoint_revision_and_historical_availability_not_proven",
            "bspi_endpoint_host_metadata_and_publication_schedule_not_reconciled",
            "2014_and_2017_year_end_publication_date_alignment_not_resolved",
            "post_2022_issuer_benchmark_switches_to_ncei",
            "no_normalized_cyclical_operating_inputs_registered",
        ],
        "evidence_refs": [
            {
                "id": "cctd_bspi_historical_endpoint",
                "path": str(BSPI_PATH.relative_to(ROOT)),
                "sha256": BSPI_HASH,
                "description": "Raw BSPI JSON endpoint retained on 2026-09-22",
            },
            prior_ref(
                PUBLIC_INDEX_POINTER,
                "shenhua_public_index_history",
                description="Five public CCTD historical chart series, archived and hash-bound",
            ),
            prior_ref(
                BRIDGE_POINTER,
                "shenhua_price_cost_transport_bridge",
                description="Shenhua 2014-2025 external-price and 2025 cost/transport bridge",
            ),
        ],
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    public_pin = json.loads(PUBLIC_INDEX_POINTER.read_text(encoding="utf-8"))
    bridge_pin = json.loads(BRIDGE_POINTER.read_text(encoding="utf-8"))
    manifest = {
        "script_sha256": sha256(Path(__file__).resolve()),
        "evidence_sha256": digest,
        "source_sha256s": {"cctd_bspi_historical_endpoint": BSPI_HASH},
        "prior_evidence_sha256s": {
            "shenhua_public_index_history": public_pin["sha256"].lower(),
            "shenhua_price_cost_transport_bridge": bridge_pin["sha256"].lower(),
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
        "summary": payload["summary"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

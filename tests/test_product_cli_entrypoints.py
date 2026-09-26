from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from value_investment_agent.application.product import review_event_for_symbol
from value_investment_agent.event_materiality import DECISION_NOT_MATERIAL
from value_investment_agent.m5_disclosure_queue import (
    DISCLOSURE_QUEUE_SCHEMA,
    PARSER_VERSION,
    PROVIDER_CNINFO,
    DisclosureReviewQueue,
    build_cninfo_event_scan,
)
from value_investment_agent.m5_disclosure_review import (
    DISCLOSURE_REVIEW_INTAKE_SCHEMA,
    DisclosureReviewDecisionInput,
    DisclosureReviewIntake,
    disclosure_queue_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "config" / "current-cli-entrypoints-v1.json"
V2 = ROOT / "config" / "current-cli-entrypoints-v2.json"
GENERIC_PRODUCT_PATHS = {
    "scripts/current/build_research_case.py",
    "scripts/current/run_company_research.py",
    "scripts/current/build_company_valuation.py",
    "scripts/current/build_current_workbench.py",
    "scripts/current/review_event.py",
}
ISSUER_SPECIFIC_PATHS = {
    "scripts/prepare_moutai_current_execution_contract.py",
    "scripts/publish_moutai_case_workbook.py",
    "scripts/run_moutai_simulation_closure.py",
    "scripts/build_m7_actual_event_candidate.py",
    "scripts/build_m7_daily_workbench_post_checkpoint_a.py",
    "scripts/build_moutai_historical_validation_admission.py",
    "scripts/run_moutai_historical_validation.ps1",
    "scripts/build_moutai_valuation_result.py",
    # Run-specific disclosure tooling: the queue builder defaults to three
    # hardcoded securities and a fixed run date, and the review applier
    # defaults to run-specific paths, so neither is a generic product entry.
    "scripts/build_m5_disclosure_queue.py",
    "scripts/apply_m5_disclosure_review.py",
}


def _registries() -> tuple[dict[str, object], dict[str, object]]:
    return (
        json.loads(V1.read_text(encoding="utf-8")),
        json.loads(V2.read_text(encoding="utf-8")),
    )


def test_v2_cli_split_preserves_every_v1_path_and_bounds_product_surface():
    v1, v2 = _registries()
    v1_paths = {entry["path"] for entry in v1["entrypoints"]}
    product = v2["SUPPORTED_PRODUCT_CLI"]
    engineering = v2["SUPPORTED_ENGINEERING_CLI"]
    all_paths = product + engineering

    assert v1["action"] == v2["action"] == "no_order"
    assert 10 <= len(product) <= 25
    assert len(all_paths) == len(set(all_paths))
    assert set(v1_paths) <= set(all_paths)
    assert GENERIC_PRODUCT_PATHS <= set(product)
    assert ISSUER_SPECIFIC_PATHS.isdisjoint(product)
    assert ISSUER_SPECIFIC_PATHS <= set(engineering)
    assert v2["counts"] == {
        "product": len(product),
        "engineering": len(engineering),
        "total": len(all_paths),
    }
    assert v2["v1_compatibility"]["registry"] == str(V1.relative_to(ROOT)).replace(
        "\\", "/"
    )
    assert v2["v1_compatibility"]["entrypoint_count"] == len(v1_paths)
    assert v2["v1_compatibility"]["sha256"] == hashlib.sha256(V1.read_bytes()).hexdigest()
    for relative in all_paths:
        assert (ROOT / relative).is_file(), relative


def test_generic_product_cli_is_thin_symbol_parameterized_and_has_no_branch():
    symbol_literal = re.compile(r"(?<![0-9])[0-9]{6}(?![0-9])")
    for relative in sorted(GENERIC_PRODUCT_PATHS):
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        assert "--symbol" in text
        assert "value_investment_agent.application.product" in text
        assert not symbol_literal.search(text)
        assert not re.search(r"if\s+symbol\s*==", text)
        assert sum(1 for _ in path.open("r", encoding="utf-8")) <= 90
        completed = subprocess.run(
            [sys.executable, str(path), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, (relative, completed.stderr)
        assert "--symbol" in completed.stdout


def test_product_application_layer_has_no_issuer_specific_branch():
    product_root = ROOT / "src" / "value_investment_agent" / "application" / "product"
    for path in product_root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "600519" not in text
        assert not re.search(r"if\s+symbol\s*==", text)


def test_event_review_product_command_uses_one_symbol_without_applying_events(tmp_path: Path):
    root = tmp_path
    archive = root / "archive"
    scan_from = date(2026, 8, 27)
    scan_to = date(2026, 9, 24)
    retrieved_at = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
    announcement_id = "1225542001"
    pdf_bytes = b"%PDF-fixture"
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    def downloader(source_url: str, target: Path) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf_bytes)
        return pdf_sha256

    scan = build_cninfo_event_scan(
        {
            "url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
            "total_announcements": 1,
            "announcements": [
                {
                    "secCode": "600887",
                    "announcementId": announcement_id,
                    "announcementTitle": "关于回购公司股份的公告",
                    "announcementTime": int(
                        datetime(2026, 9, 2, 1, 0, tzinfo=timezone.utc).timestamp()
                        * 1000
                    ),
                    "adjunctUrl": f"finalpage/2026-09-02/{announcement_id}.PDF",
                }
            ],
        },
        symbol="600887",
        scan_from=scan_from,
        scan_to=scan_to,
        retrieved_at=retrieved_at,
        evidence_dir=archive / "600887",
        root=root,
        pdf_downloader=downloader,
    )
    queue = DisclosureReviewQueue(
        queue_id="fixture-cninfo-review",
        schema_version=DISCLOSURE_QUEUE_SCHEMA,
        provider=PROVIDER_CNINFO,
        parser_version=PARSER_VERSION,
        scan_from=scan_from,
        scan_to=scan_to,
        retrieved_at=retrieved_at,
        scans=(scan,),
        action="no_order",
    )
    intake = DisclosureReviewIntake(
        schema_version=DISCLOSURE_REVIEW_INTAKE_SCHEMA,
        queue_id=queue.queue_id,
        queue_sha256=disclosure_queue_sha256(queue),
        reviewed_at=datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc),
        decisions=(
            DisclosureReviewDecisionInput(
                announcement_id=announcement_id,
                symbol="600887",
                human_decision=DECISION_NOT_MATERIAL,
                review_notes=("synthetic focused test",),
            ),
        ),
        action="no_order",
    )
    queue_path = root / "queue.json"
    intake_path = root / "intake.json"
    queue_path.write_text(queue.to_json(), encoding="utf-8")
    intake_path.write_text(intake.to_json(), encoding="utf-8")

    result = review_event_for_symbol(
        root=root,
        symbol="600887",
        queue_path=queue_path,
        intake_path=intake_path,
        runtime_root=root / "review-output",
        archive_root=root,
        review_provenance="USER_CONFIRMED_DELEGATED_REVIEW",
    )

    assert result["result"]["action"] == "no_order"
    assert result["result"]["symbol"] == "600887"
    assert result["result"]["events_not_applied"] is True
    assert result["result"]["provenance_authenticated"] is False
    assert result["result"]["requires_signed_approval_receipt_for_actual"] is True
    assert result["receipt"]["action"] == "no_order"


def test_event_review_requires_an_explicit_provenance_claim(tmp_path: Path):
    with pytest.raises(ValueError, match="explicit review provenance"):
        review_event_for_symbol(
            root=tmp_path,
            symbol="600887",
            queue_path=tmp_path / "queue.json",
            intake_path=tmp_path / "intake.json",
            runtime_root=tmp_path / "review-output",
        )

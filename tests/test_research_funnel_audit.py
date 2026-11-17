from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable

import pytest

from value_investment_agent.application.product.value_discovery_surface import (
    publish_value_discovery_report,
)
from value_investment_agent.application.research.research_funnel_audit import (
    audit_research_funnel,
    build_human_review_packet,
    write_research_funnel_audit,
)
from value_investment_agent.application.research.value_research_queue import (
    build_value_research_queue,
)
from value_investment_agent.financial_quality import GENERAL_FIELDS
from value_investment_agent.m2_opportunity_discovery import (
    CHANNELS,
    CandidateReason,
    ChannelEvaluation,
    ChannelResult,
    DataHealth,
    DiscoveryRunReceipt,
    EvidenceReference,
    LegacyComparison,
    UniverseRecord,
    UniverseSnapshot,
    candidate_signature,
    coverage_signature,
)


SYMBOLS = ("000001", "000002", "000003")
NAMES = {"000001": "Alpha", "000002": "Beta", "000003": "Gamma"}
INDUSTRIES = {"000001": "C Manufacturing", "000002": "J Finance", "000003": "K Property"}
POLICY = "m2-multi-channel-cheap-screen-v2"


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _point(
    *,
    symbol: str,
    field: str,
    index: int,
    source_name: str,
    status: str = "verified",
    accepted: bool = True,
    period: str = "2025-12-31",
    derivation: str | None = None,
) -> dict:
    metadata = {"automatic_cross_source_verification": accepted}
    if field == "interest_bearing_debt":
        metadata["complete_debt_verified"] = accepted
    if derivation:
        metadata["derivation_formula"] = derivation
        metadata["input_facts"] = {"revenue": {"value": "100"}}
    return {
        "data_point_id": f"{symbol}-{field}-{index}",
        "symbol": symbol,
        "field_name": field,
        "period_label": period,
        "created_at": f"2026-09-{index + 1:02d}T00:00:00+00:00",
        "validation_status": status,
        "metadata": metadata,
        "source_id": f"source-{index}",
        "source_name": source_name,
        "value": "10",
        "unit": "percent",
    }


def _evaluation(
    channel: str,
    symbol: str,
    status: str,
    reason: str,
    refs: tuple[EvidenceReference, ...] = (),
) -> ChannelEvaluation:
    return ChannelEvaluation(
        symbol=symbol,
        name=NAMES[symbol],
        channel=channel,
        status=status,
        reason=reason,
        profile_status="SUPPORTED",
        evidence_date="2026-10-12",
        policy_version=POLICY,
        evidence_refs=refs,
    )


def _candidate(
    channel: str,
    symbol: str,
    refs: tuple[EvidenceReference, ...],
) -> CandidateReason:
    return CandidateReason(
        symbol=symbol,
        name=NAMES[symbol],
        channel=channel,
        reasons=(f"{channel} synthetic trigger",),
        metrics={"score": "1"},
        evidence_refs=refs,
        evidence_date="2026-10-12",
        data_status="PARTIAL",
        profile_status="SUPPORTED",
        priority_tier="C",
        candidate_class="LEAD",
    )


def _fixture(
    tmp_path: Path,
    *,
    points_mutator: Callable[[list[dict]], None] | None = None,
) -> dict[str, Path]:
    root = tmp_path
    runtime = root / "runtime"
    product = runtime / "m2-product"
    product.mkdir(parents=True)

    official_path = product / "official-universe.json"
    tencent_path = product / "tencent-market.json"
    sina_path = product / "sina-industry-quotes.json"
    dividend_path = product / "eastmoney-dividends.json"
    financial_path = product / "retained-financial-points.json"
    workbook_path = product / "m2-opportunity-discovery.xlsx"

    _write_json(
        official_path,
        {
            "schema_version": "m2-opportunity-discovery-v2",
            "as_of": "2026-10-12",
            "complete": True,
            "scope": "synthetic A-share fixture",
            "records": [
                {
                    "symbol": symbol,
                    "name": NAMES[symbol],
                    "board": "Main",
                    "exchange": "SZSE",
                    "listed_on": "2000-01-01",
                    "official_industry": INDUSTRIES[symbol],
                    "security_type": "A share",
                }
                for symbol in SYMBOLS
            ],
        },
    )
    _write_json(
        tencent_path,
        {
            "rows": [
                {"code": f"sz{symbol}", "name": NAMES[symbol], "zxj": "10"}
                for symbol in SYMBOLS
            ],
            "total": len(SYMBOLS),
        },
    )
    _write_json(
        sina_path,
        {
            "rows": [
                {"code": symbol, "name": NAMES[symbol], "class": INDUSTRIES[symbol]}
                for symbol in SYMBOLS
            ]
        },
    )
    _write_json(
        dividend_path,
        {
            "rows": [
                [symbol, NAMES[symbol], "NaN", "NaN", "NaN", 0.5, 0.01]
                for symbol in SYMBOLS
            ]
        },
    )
    workbook_path.write_bytes(b"PK\x03\x04synthetic workbook")

    points = []
    for index, field in enumerate(GENERAL_FIELDS):
        points.append(
            _point(
                symbol="000001",
                field=field,
                index=index,
                source_name="CNINFO statutory disclosure",
            )
        )
    points.extend(
        [
            _point(
                symbol="000002",
                field="roe",
                index=20,
                source_name="AkShare / Sina financial abstract",
                status="pending",
                accepted=False,
            ),
            _point(
                symbol="000002",
                field="roic",
                index=21,
                source_name="AkShare / Sina financial abstract",
                status="pending",
                accepted=False,
            ),
            _point(
                symbol="000002",
                field="cet1_ratio",
                index=22,
                source_name="CNINFO official institution report",
                status="pending",
                accepted=False,
            ),
            _point(
                symbol="000002",
                field="net_margin",
                index=23,
                source_name="Value Investment Agent verified financial derivations",
                derivation="net_income / revenue",
            ),
            _point(
                symbol="000001",
                field="current_price",
                index=24,
                source_name="Tencent all-A market snapshot + Sina valuation cross-check",
            ),
        ]
    )
    if points_mutator is not None:
        points_mutator(points)
    _write_json(financial_path, {"points": points})

    fetched_at = datetime(2026, 10, 12, 1, 0, tzinfo=timezone.utc)
    references = (
        EvidenceReference(
            "official",
            official_path.relative_to(root).as_posix(),
            _hash(official_path),
            "Official universe",
            "synthetic://official",
            fetched_at,
        ),
        EvidenceReference(
            "tencent",
            tencent_path.relative_to(root).as_posix(),
            _hash(tencent_path),
            "Tencent market",
            "synthetic://tencent",
            fetched_at,
        ),
        EvidenceReference(
            "sina",
            sina_path.relative_to(root).as_posix(),
            _hash(sina_path),
            "Sina industry",
            "synthetic://sina",
            fetched_at,
        ),
        EvidenceReference(
            "dividend",
            dividend_path.relative_to(root).as_posix(),
            _hash(dividend_path),
            "Dividend snapshot",
            "synthetic://dividend",
            fetched_at,
        ),
        EvidenceReference(
            "financial",
            financial_path.relative_to(root).as_posix(),
            _hash(financial_path),
            "Retained financial points",
            "synthetic://financial",
            fetched_at,
        ),
    )
    refs = {reference.id: reference for reference in references}
    market_refs = (refs["sina"], refs["tencent"])

    channel_results = {}
    for channel in CHANNELS:
        if channel == "quality":
            evaluations = (
                _evaluation(channel, "000001", "REJECTED", "quality evidence pending"),
                _evaluation(channel, "000002", "REJECTED", "quality evidence pending"),
                _evaluation(channel, "000003", "DATA_GAP", "quality snapshot missing"),
            )
            candidates = ()
        elif channel == "value":
            evaluations = (
                _evaluation(channel, "000001", "PASS", "value trigger", market_refs),
                _evaluation(channel, "000002", "PASS", "value trigger", market_refs),
                _evaluation(channel, "000003", "REJECTED", "market cap below floor"),
            )
            candidates = (
                _candidate(channel, "000001", market_refs),
                _candidate(channel, "000002", market_refs),
            )
        elif channel == "cyclical":
            evaluations = (
                _evaluation(channel, "000001", "PASS", "cyclical trigger", market_refs),
                _evaluation(channel, "000002", "NOT_EVALUATED", "industry excluded"),
                _evaluation(channel, "000003", "NOT_EVALUATED", "industry excluded"),
            )
            candidates = (_candidate(channel, "000001", market_refs),)
        else:
            evaluations = (
                _evaluation(channel, "000001", "PASS", "dividend trigger", market_refs),
                _evaluation(channel, "000002", "REJECTED", "yield below floor"),
                _evaluation(channel, "000003", "NOT_EVALUATED", "no dividend evidence"),
            )
            candidates = (_candidate(channel, "000001", market_refs),)
        channel_results[channel] = ChannelResult(
            channel=channel,
            title=f"Synthetic {channel}",
            candidates=candidates,
            excluded=(),
            missing=(),
            rule_version=POLICY,
            evaluations=evaluations,
        )

    universe = UniverseSnapshot(
        schema_version="m2-opportunity-discovery-v2",
        as_of=date(2026, 10, 12),
        complete=True,
        scope="synthetic A-share fixture",
        records=tuple(
            UniverseRecord(
                symbol=symbol,
                name=NAMES[symbol],
                board="Main",
                exchange="SZSE",
                listed_on="2000-01-01",
                official_industry=INDUSTRIES[symbol],
                security_type="A share",
            )
            for symbol in SYMBOLS
        ),
        evidence_refs=(refs["official"],),
    )
    health = DataHealth(
        universe_count=3,
        quote_count=3,
        matched_quote_count=3,
        missing_quote_count=0,
        extra_quote_count=0,
        price_conflict_count=0,
        industry_mapping_count=3,
        financial_evidence_count=2,
        dividend_evidence_count=3,
        unsupported_financial_count=0,
        status="PARTIAL",
        blockers=("provider trade date is unverified",),
    )
    receipt = DiscoveryRunReceipt(
        schema_version="m2-opportunity-discovery-v2",
        run_id="m2-synthetic",
        rule_version=POLICY,
        generated_at=datetime(2026, 10, 12, 2, 0, tzinfo=timezone.utc),
        as_of=date(2026, 10, 12),
        action="no_order",
        universe=universe,
        data_health=health,
        channel_results=channel_results,
        legacy_comparison=LegacyComparison(0, (), 2, 0, "synthetic only"),
        evidence_refs=references,
        coverage_signature=coverage_signature(channel_results),
        candidate_signature=candidate_signature(channel_results),
        quote_date="2026-10-12",
    )
    receipt_path = product / "receipt.json"
    _write_json(receipt_path, receipt.as_policy())

    report_path = product / "value-discovery-report.json"
    publish_value_discovery_report(
        root=root,
        receipt_path=receipt_path,
        receipt_sha256=_hash(receipt_path),
        output_path=report_path,
    )
    queue_path = runtime / "value-research-queue.json"
    build_value_research_queue(
        root=root,
        report_path=report_path,
        report_sha256=_hash(report_path),
        receipt_path=receipt_path,
        receipt_sha256=_hash(receipt_path),
        budget=1,
    )
    queue = json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.exists() else None
    if queue is None:
        built = build_value_research_queue(
            root=root,
            report_path=report_path,
            report_sha256=_hash(report_path),
            receipt_path=receipt_path,
            receipt_sha256=_hash(receipt_path),
            budget=1,
        )
        _write_json(queue_path, built)

    manifest_path = product / "manifest.json"
    files = {}
    for key, path in (
        ("official", official_path),
        ("tencent", tencent_path),
        ("sina", sina_path),
        ("dividend", dividend_path),
        ("financial", financial_path),
        ("receipt", receipt_path),
        ("lead_report", report_path),
        ("workbook", workbook_path),
    ):
        files[key] = {"path": path.relative_to(root).as_posix(), "sha256": _hash(path)}
    _write_json(
        manifest_path,
        {
            "schema_version": "m2-run-manifest-v1",
            "files": files,
            "summary": {
                "action": "no_order",
                "run_id": receipt.run_id,
                "as_of": receipt.as_of.isoformat(),
                "quote_date": receipt.quote_date,
                "quote_date_verification": "UNVERIFIED_PROVIDER_TRADE_DATE",
                "coverage_signature": receipt.coverage_signature,
                "candidate_signature": receipt.candidate_signature,
                "channel_counts": {
                    channel: len(channel_results[channel].candidates)
                    for channel in CHANNELS
                },
                "coverage_counts": {
                    channel: channel_results[channel].as_policy()["coverage"]
                    for channel in CHANNELS
                },
                "data_health": health.as_policy(),
                "lead_report_path": report_path.relative_to(root).as_posix(),
                "receipt_path": receipt_path.relative_to(root).as_posix(),
            },
        },
    )
    return {
        "root": root,
        "receipt": receipt_path,
        "manifest": manifest_path,
        "queue": queue_path,
        "financial": financial_path,
    }


def _audit(fixture: dict[str, Path]) -> dict:
    return audit_research_funnel(
        root=fixture["root"],
        receipt_path=fixture["receipt"],
        manifest_path=fixture["manifest"],
        queue_path=fixture["queue"],
    )


def _rewrite_queue(fixture: dict[str, Path], mutator: Callable[[dict], None]) -> None:
    queue = json.loads(fixture["queue"].read_text(encoding="utf-8"))
    mutator(queue)
    queue["content_sha256"] = _canonical_hash(
        {key: value for key, value in queue.items() if key != "content_sha256"}
    )
    _write_json(fixture["queue"], queue)


def _forge_quote_verification(fixture: dict[str, Path], status: str) -> None:
    manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
    report_path = fixture["root"] / manifest["files"]["lead_report"]["path"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["quote_date_verification"] = status
    for lead in report["leads"]:
        lead["quote_date_verification"] = status
    _write_json(report_path, report)

    def update_queue(queue: dict) -> None:
        queue["inputs"]["report_sha256"] = _hash(report_path)

    _rewrite_queue(fixture, update_queue)
    manifest["files"]["lead_report"]["sha256"] = _hash(report_path)
    manifest["summary"]["quote_date_verification"] = status
    _write_json(fixture["manifest"], manifest)


def test_hash_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    fixture["financial"].write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        _audit(fixture)


def test_count_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
    manifest["summary"]["coverage_counts"]["quality"]["rejected_count"] += 1
    _write_json(fixture["manifest"], manifest)
    with pytest.raises(ValueError, match="coverage count mismatch"):
        _audit(fixture)


def test_quality_rejections_without_evidence_are_insufficient(tmp_path):
    result = _audit(_fixture(tmp_path))
    quality = result["channels"]["quality"]
    assert quality["status_counts"]["REJECTED"] == 2
    assert quality["effective_status_counts"]["REJECTED"] == 0
    assert quality["effective_status_counts"]["INSUFFICIENT_EVIDENCE"] == 2
    assert result["quality_rejected_zero_evidence_count"] == 2
    assert result["interpretation"]["quality_rejected_without_evidence"]["effective_status"] == (
        "INSUFFICIENT_EVIDENCE"
    )
    assert "raw status REJECTED" in result["interpretation"]["product_level"]


def test_no_trade_and_unverified_quote_dates_are_preserved(tmp_path):
    result = _audit(_fixture(tmp_path))
    packet = build_human_review_packet(result)
    assert result["action"] == "no_order"
    assert result["trade_intent"] == "NO_TRADE"
    assert result["quote"]["quote_date_verification"] == "UNVERIFIED_PROVIDER_TRADE_DATE"
    assert result["quote"]["trade_date_verified"] is False
    assert result["quote"]["verified_quote_count"] == 0
    assert result["quote"]["unverified_quote_count"] == 3
    assert result["capital_return_roic"]["status"] == "UNAVAILABLE"
    assert packet["action"] == "no_order"
    assert packet["signature"] is None
    assert packet["approval"] is None


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("missing", "missing an availability timestamp"),
        ("timezone_less", "must include a timezone"),
        ("future", "later than receipt.generated_at"),
    ),
)
def test_financial_point_untrusted_timestamps_fail_closed(tmp_path, case, message):
    def mutate(points: list[dict]) -> None:
        point = points[0]
        if case == "missing":
            point.pop("available_at", None)
            point.pop("fetched_at", None)
            point.pop("created_at", None)
        elif case == "timezone_less":
            point["available_at"] = "2026-10-12T00:00:00"
        else:
            point["available_at"] = "2026-10-12T02:00:01+00:00"

    fixture = _fixture(tmp_path, points_mutator=mutate)
    with pytest.raises(ValueError, match=message):
        _audit(fixture)


def test_report_cannot_forge_verified_quote_dates(tmp_path):
    fixture = _fixture(tmp_path)
    _forge_quote_verification(fixture, "VERIFIED_PROVIDER_TRADE_DATE")
    with pytest.raises(ValueError, match="unsupported quote-date verification status"):
        _audit(fixture)


@pytest.mark.parametrize(
    ("research_state", "gaps", "message"),
    (
        ("APPROVED", ["QUOTE_DATE_UNVERIFIED"], "research_state is invalid"),
        ("DISCOVERED", ["QUOTE_DATE_UNVERIFIED"], "DISCOVERED entry must have empty gaps"),
        ("DATA_CHECK", [], "DATA_CHECK entry must have non-empty gaps"),
    ),
)
def test_queue_state_and_gaps_must_match_production_contract(
    tmp_path, research_state, gaps, message
):
    fixture = _fixture(tmp_path)

    def mutate(queue: dict) -> None:
        queue["entries"][0]["research_state"] = research_state
        queue["entries"][0]["gaps"] = gaps

    _rewrite_queue(fixture, mutate)
    with pytest.raises(ValueError, match=message):
        _audit(fixture)


def test_packet_is_deterministic_and_outputs_never_overwrite(tmp_path):
    fixture = _fixture(tmp_path)
    result = _audit(fixture)
    first_packet = build_human_review_packet(result)
    second_packet = build_human_review_packet(result)
    assert first_packet == second_packet
    assert first_packet["selection"]["sample_size"] == 1
    assert first_packet["sample"][0]["symbol"] == "000001"

    output_dir = fixture["root"] / "runtime" / "audit-output"
    manifest = write_research_funnel_audit(
        result,
        first_packet,
        root=fixture["root"],
        output_dir=output_dir,
    )
    assert manifest["action"] == "no_order"
    assert {path.name for path in output_dir.iterdir()} == {
        "result.json",
        "report.md",
        "human-review-packet.json",
        "manifest.json",
    }
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_research_funnel_audit(
            result,
            first_packet,
            root=fixture["root"],
            output_dir=output_dir,
        )
    assert before == {path.name: path.read_bytes() for path in output_dir.iterdir()}


def test_source_files_exactly_mirror_source_hashes_after_round_trip(tmp_path):
    fixture = _fixture(tmp_path)
    result = _audit(fixture)
    packet = build_human_review_packet(result)
    output_dir = fixture["root"] / "runtime" / "bound-audit"
    write_research_funnel_audit(
        result,
        packet,
        root=fixture["root"],
        output_dir=output_dir,
    )

    written_result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    written_manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert written_result["action"] == "no_order"
    assert written_manifest["trade_intent"] == "NO_TRADE"
    assert set(written_result["source_files"]) == set(written_result["source_hashes"])
    assert written_manifest["source_hashes"] == written_result["source_hashes"]
    assert {"manifest", "queue", "workbook"} <= set(written_result["source_files"])
    for role, binding in written_result["source_files"].items():
        assert binding["sha256"] == written_result["source_hashes"][role]
        source_path = fixture["root"] / binding["path"]
        assert _hash(source_path) == binding["sha256"]


def test_writer_rejects_stale_audit_digest(tmp_path):
    fixture = _fixture(tmp_path)
    result = _audit(fixture)
    stale_result = json.loads(json.dumps(result))
    stale_result["audit_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="audit result digest is stale"):
        write_research_funnel_audit(
            stale_result,
            build_human_review_packet(result),
            root=fixture["root"],
            output_dir=fixture["root"] / "runtime" / "stale-audit",
        )


def test_writer_rejects_stale_packet_digest(tmp_path):
    fixture = _fixture(tmp_path)
    result = _audit(fixture)
    stale_packet = json.loads(json.dumps(build_human_review_packet(result)))
    stale_packet["packet_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="packet digest is stale"):
        write_research_funnel_audit(
            result,
            stale_packet,
            root=fixture["root"],
            output_dir=fixture["root"] / "runtime" / "stale-packet",
        )


def test_queue_path_escape_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    outside_queue = fixture["root"] / "outside-queue.json"
    _write_json(outside_queue, {})
    with pytest.raises(ValueError, match="runtime or artifacts"):
        audit_research_funnel(
            root=fixture["root"],
            receipt_path=fixture["receipt"],
            manifest_path=fixture["manifest"],
            queue_path=outside_queue,
        )


def test_manifest_file_path_escape_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
    manifest["files"]["financial"]["path"] = "runtime/outside-financial.json"
    _write_json(fixture["manifest"], manifest)
    with pytest.raises(ValueError, match="outside the M2 product directory"):
        _audit(fixture)


def test_output_directory_must_remain_under_runtime_or_artifacts(tmp_path):
    fixture = _fixture(tmp_path)
    result = _audit(fixture)
    packet = build_human_review_packet(result)
    with pytest.raises(ValueError, match="runtime or artifacts"):
        write_research_funnel_audit(
            result,
            packet,
            root=fixture["root"],
            output_dir=fixture["root"] / "outside",
        )

"""Application service for the synthetic M4 onboarding rehearsal."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import tempfile
from typing import Any, Callable, Iterator, Mapping


ROOT = Path(__file__).resolve().parents[4]

from value_investment_agent.dividend_income_projection import (  # noqa: E402
    build_portfolio_dividend_income_projection,
    security_dividend_income_projection_from_payload,
)
from value_investment_agent.domain.portfolio.confirmation_receipt import (  # noqa: E402
    USER_CONFIRMED_RECONCILIATION,
    build_portfolio_confirmation_receipt,
    portfolio_confirmation_receipt_from_payload,
)
from value_investment_agent.portfolio_contracts import (  # noqa: E402
    NAMESPACE_ACTUAL,
    NAMESPACE_SIMULATED,
    RECONCILIATION_PENDING,
    RECONCILIATION_RECONCILED,
    PortfolioInputBundle,
    portfolio_input_bundle_from_payload,
)
from value_investment_agent.portfolio_reconciliation import (  # noqa: E402
    STATUS_MATCH_PENDING_HUMAN_CONFIRMATION,
    reconcile_portfolio_snapshots,
)
from value_investment_agent.portfolio_risk import (  # noqa: E402
    build_portfolio_risk_assessment,
    security_risk_attributes_from_payload,
)
from value_investment_agent.position_guidance import (  # noqa: E402
    build_position_guidance,
    position_candidate_from_payload,
    position_tier_policy_from_payload,
)
from value_investment_agent.investment_decision import ACTION_NO_ORDER  # noqa: E402
from value_investment_agent.private_portfolio_intake import (  # noqa: E402
    encrypt_private_portfolio_payload,
    load_private_portfolio_bundle,
)


RECEIPT_SCHEMA_VERSION = "m4-synthetic-onboarding-rehearsal-receipt-v1"
M7_MATERIAL_SCHEMA_VERSION = "m4-synthetic-m7-candidate-material-v1"
PRODUCT_WORKBENCH_SCHEMA_VERSION = "m7-product-workbench-v1"
CLASSIFICATION = "SYNTHETIC_REHEARSAL_ONLY"
SYNTHETIC_SCOPE = "SYNTHETIC_M4_REHEARSAL_ONLY"
SOURCE_BUNDLE_FIXTURE = ROOT / "tests" / "fixtures" / "m4_guidance_income_demo.json"
RISK_FIXTURE = ROOT / "tests" / "fixtures" / "m4_portfolio_risk_demo.json"
_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(payload),
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite: {path}")
    value = _json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return _sha256_bytes(value)


def _write_bytes(path: Path, value: bytes) -> str:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return _sha256_bytes(value)


@contextmanager
def _private_workspace() -> Iterator[tuple[Path, Path]]:
    """Create disposable encrypted-input paths outside the checkout."""
    with tempfile.TemporaryDirectory(prefix="m4-synthetic-data-") as data_directory:
        with tempfile.TemporaryDirectory(prefix="m4-synthetic-key-") as key_directory:
            private_root = Path(data_directory).resolve()
            key_path = Path(key_directory).resolve() / "portfolio.key"
            key_path.write_text(secrets.token_hex(32) + "\n", encoding="ascii")
            yield private_root, key_path


def _fresh_output_directory(runtime_root: Path, run_id: str | None) -> tuple[Path, str]:
    root = runtime_root.resolve()
    if run_id is None:
        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            + "-"
            + secrets.token_hex(3)
        )
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must contain only letters, digits, dot, underscore or hyphen")
    output = root / f"m4-synthetic-onboarding-{run_id}"
    if output.exists():
        raise FileExistsError(f"synthetic rehearsal output already exists: {output}")
    output.mkdir(parents=True, exist_ok=False)
    return output, run_id


def _synthetic_bundle_payload(source: Mapping[str, Any]) -> dict[str, Any]:
    policy = dict(source["policy"])
    snapshot = dict(source["snapshot"])
    policy["account_scope"] = SYNTHETIC_SCOPE
    policy["evidence_refs"] = [
        *(dict(item) for item in policy.get("evidence_refs") or ()),
        {"id": "synthetic-rehearsal-policy-marker"},
    ]
    snapshot["account_scope"] = SYNTHETIC_SCOPE
    snapshot["namespace"] = NAMESPACE_ACTUAL
    snapshot["reconciliation_status"] = RECONCILIATION_PENDING
    snapshot["reconciled_at"] = None
    snapshot["evidence_refs"] = [
        *(dict(item) for item in snapshot.get("evidence_refs") or ()),
        {"id": "synthetic-rehearsal-snapshot-marker"},
    ]
    return {
        "policy": policy,
        "snapshot": snapshot,
        "action": ACTION_NO_ORDER,
    }


def _fixture_receipt(path: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": _sha256_bytes(path.read_bytes()),
        "classification": "PUBLIC_SYNTHETIC_FIXTURE",
    }


def _artifact(
    output: Path,
    artifacts: dict[str, dict[str, str]],
    name: str,
    payload: Mapping[str, Any],
) -> str:
    digest = _write_json(output / name, payload)
    artifacts[name] = {"path": name, "sha256": digest}
    return digest


def _artifact_bytes(
    output: Path,
    artifacts: dict[str, dict[str, str]],
    name: str,
    payload: bytes,
) -> str:
    digest = _write_bytes(output / name, payload)
    artifacts[name] = {"path": name, "sha256": digest}
    return digest


def _stage(evidence: str, *, business_status: str) -> dict[str, Any]:
    return {
        "status": "EXERCISED",
        "classification": CLASSIFICATION,
        "business_status": business_status,
        "evidence": evidence,
    }


def _build_models(
    confirmed: PortfolioInputBundle,
    guidance_fixture: Mapping[str, Any],
    risk_fixture: Mapping[str, Any],
) -> tuple[Any, Any, Any, PortfolioInputBundle]:
    simulated_snapshot = replace(confirmed.snapshot, namespace=NAMESPACE_SIMULATED)
    simulated_bundle = PortfolioInputBundle(
        policy=confirmed.policy,
        snapshot=simulated_snapshot,
    )
    symbols = tuple(holding.symbol for holding in simulated_snapshot.holdings)
    try:
        attributes = {
            symbol: security_risk_attributes_from_payload(
                risk_fixture["security_attributes"][symbol]
            )
            for symbol in symbols
        }
        candidates = {
            symbol: position_candidate_from_payload(guidance_fixture["candidates"][symbol])
            for symbol in symbols
        }
        security_projections = {
            symbol: security_dividend_income_projection_from_payload(
                guidance_fixture["security_projections"][symbol]
            )
            for symbol in symbols
        }
    except KeyError as error:
        raise ValueError(
            "Synthetic public fixtures do not cover a confirmed holding; "
            f"missing public contract input: {error.args[0]}"
        ) from error

    as_of = datetime.fromisoformat(str(guidance_fixture["generated_at"])).date()
    generated_at = datetime.fromisoformat(str(guidance_fixture["generated_at"]))
    tier_policy = position_tier_policy_from_payload(guidance_fixture["tier_policy"])
    risk = build_portfolio_risk_assessment(
        bundle=simulated_bundle,
        security_attributes=attributes,
        as_of=as_of,
        generated_at=generated_at,
        assessment_id="synthetic-rehearsal-risk-v1",
        assessment_namespace=NAMESPACE_SIMULATED,
    )
    guidance = build_position_guidance(
        bundle=simulated_bundle,
        tier_policy=tier_policy,
        candidates=candidates,
        as_of=as_of,
        generated_at=generated_at,
        assessment_id="synthetic-rehearsal-guidance-v1",
        assessment_namespace=NAMESPACE_SIMULATED,
    )
    dividend = build_portfolio_dividend_income_projection(
        bundle=simulated_bundle,
        security_projections=security_projections,
        as_of=as_of,
        generated_at=generated_at,
        assessment_id="synthetic-rehearsal-dividend-v1",
        assessment_namespace=NAMESPACE_SIMULATED,
    )
    return risk, guidance, dividend, simulated_bundle


def _product_evidence(
    artifacts: Mapping[str, Mapping[str, str]],
    *,
    available_at: str,
) -> list[dict[str, Any]]:
    records = [
        (
            "synthetic-reconciliation",
            "Synthetic dual-snapshot reconciliation",
            "06_dual_snapshot_reconciliation.json",
        ),
        (
            "synthetic-confirmation",
            "Synthetic reconciliation confirmation receipt",
            "07_confirmation_receipt.json",
        ),
        ("synthetic-risk", "Synthetic PortfolioRisk assessment", "09_portfolio_risk.json"),
        (
            "synthetic-guidance",
            "Synthetic PositionGuidance assessment",
            "10_position_guidance.json",
        ),
        (
            "synthetic-dividend",
            "Synthetic DividendProjection assessment",
            "11_dividend_projection.json",
        ),
    ]
    return [
        {
            "evidence_id": evidence_id,
            "title": title,
            "artifact_type": "m4_synthetic_rehearsal_artifact",
            "path": path,
            "sha256": artifacts[path]["sha256"],
            "available_at": available_at,
            "action": ACTION_NO_ORDER,
        }
        for evidence_id, title, path in records
    ]


def _product_payload(
    artifacts: Mapping[str, Mapping[str, str]],
    *,
    as_of: str,
    generated_at: str,
    risk_status: str,
    guidance_status: str,
    dividend_status: str,
) -> dict[str, Any]:
    return {
        "schema_version": PRODUCT_WORKBENCH_SCHEMA_VERSION,
        "generated_at": generated_at,
        "as_of": as_of,
        "action": ACTION_NO_ORDER,
        "overview": {"pending_count": 1},
        "system_health": {
            "status": "EVIDENCE_INSUFFICIENT",
            "message": "Synthetic rehearsal completed; real private portfolio input is still absent.",
        },
        "stages": {
            "m2": {
                "status": "HUMAN_PASS",
                "detail": "Existing stage status is not revalidated here.",
            },
            "m3": {
                "status": "PARTIAL",
                "detail": "Existing stage status is not revalidated here.",
            },
            "m4": {
                "status": "ENGINEERING_DONE_SIMULATED",
                "detail": (
                    "Synthetic onboarding chain exercised. "
                    "M4_PERSONALIZED_ACCEPTANCE=WAITING_R2; "
                    "synthetic success is not real acceptance."
                ),
            },
            "m5": {
                "status": "WAIT",
                "detail": "No M5 acceptance is claimed by this rehearsal.",
            },
            "m6": {
                "status": "NOT_STARTED",
                "detail": "No operational monitoring is claimed here.",
            },
        },
        "audit": {"evidence": _product_evidence(artifacts, available_at=as_of)},
        "today_items": [],
        "opportunities": [],
        "companies": [],
        "portfolio": {
            "real_data_available": False,
            "status": "SIMULATED_ONLY",
            "connection_hint": (
                "Synthetic rehearsal only. Real IPS/portfolio input remains WAITING_R2; "
                f"risk={risk_status}, guidance={guidance_status}, dividend={dividend_status}."
            ),
            "summary": [],
            "positions": [],
            "action": ACTION_NO_ORDER,
        },
        "events": [],
    }


def run_m4_synthetic_onboarding_rehearsal(
    runtime_root: Path,
    run_id: str | None = None,
    *,
    product_read_model_mapper: Callable[
        [Mapping[str, Any]], Mapping[str, Any]
    ],
) -> dict[str, Any]:
    if not callable(product_read_model_mapper):
        raise ValueError("product_read_model_mapper must be callable")
    output, run_id = _fresh_output_directory(runtime_root, run_id)
    artifacts: dict[str, dict[str, str]] = {}
    marker_digest = _write_json(
        output / "SYNTHETIC_REHEARSAL_ONLY.json",
        {
            "classification": CLASSIFICATION,
            "action": ACTION_NO_ORDER,
            "run_id": run_id,
            "real_private_inputs_used": False,
            "synthetic_success_is_not_real_acceptance": True,
        },
    )
    artifacts["SYNTHETIC_REHEARSAL_ONLY.json"] = {
        "path": "SYNTHETIC_REHEARSAL_ONLY.json",
        "sha256": marker_digest,
    }

    source_bundle = _read_json(SOURCE_BUNDLE_FIXTURE)
    guidance_fixture = source_bundle
    risk_fixture = _read_json(RISK_FIXTURE)
    fixture_receipts = [
        _fixture_receipt(SOURCE_BUNDLE_FIXTURE),
        _fixture_receipt(RISK_FIXTURE),
    ]

    draft_payload = _synthetic_bundle_payload(source_bundle)
    draft_bytes = _json_bytes(draft_payload)
    with _private_workspace() as (private_root, key_path):
        draft_path = private_root / "synthetic-onboarding-draft.json"
        _write_bytes(draft_path, draft_bytes)
        _artifact(
            output,
            artifacts,
            "01_init.json",
            {
                "classification": CLASSIFICATION,
                "status": "SYNTHETIC_DRAFT_INITIALIZED",
                "action": ACTION_NO_ORDER,
                "draft_classification": CLASSIFICATION,
                "draft_sha256": _sha256_bytes(draft_bytes),
                "source_fixtures": fixture_receipts,
            },
        )

        pending_bundle = portfolio_input_bundle_from_payload(draft_payload)
        pending_blockers = pending_bundle.missing_guidance_inputs()
        if pending_blockers != ("snapshot.reconciliation",):
            raise ValueError(
                "Synthetic draft does not have the expected pre-confirmation blocker: "
                f"{pending_blockers}"
            )
        _artifact(
            output,
            artifacts,
            "02_validate.json",
            {
                "classification": CLASSIFICATION,
                "status": "CONTRACT_VALID_PENDING_RECONCILIATION",
                "action": ACTION_NO_ORDER,
                "blockers": list(pending_blockers),
                "namespace": pending_bundle.snapshot.namespace,
                "real_input": False,
            },
        )

        reported_path = private_root / "reported.viportfolio"
        confirmed_source_path = private_root / "confirmed-source.viportfolio"
        created_at = datetime(
            2026, 9, 22, 20, 10, tzinfo=timezone(timedelta(hours=8))
        )
        reported_receipt = encrypt_private_portfolio_payload(
            draft_payload,
            reported_path,
            key_path,
            private_root=private_root,
            repository_root=ROOT,
            created_at=created_at,
        )
        confirmed_source_receipt = encrypt_private_portfolio_payload(
            draft_payload,
            confirmed_source_path,
            key_path,
            private_root=private_root,
            repository_root=ROOT,
            created_at=created_at,
        )
        _artifact(
            output,
            artifacts,
            "03_encrypt_reported.json",
            {
                "classification": CLASSIFICATION,
                "synthetic_ciphertext_rehearsal_only": True,
                "receipt": reported_receipt.as_policy(),
            },
        )
        _artifact(
            output,
            artifacts,
            "04_encrypt_confirmed_source.json",
            {
                "classification": CLASSIFICATION,
                "synthetic_ciphertext_rehearsal_only": True,
                "receipt": confirmed_source_receipt.as_policy(),
            },
        )

        verified_bundle, verified_receipt = load_private_portfolio_bundle(
            reported_path,
            key_path,
            private_root=private_root,
            repository_root=ROOT,
        )
        if verified_bundle != pending_bundle:
            raise ValueError("Encrypted synthetic draft did not round-trip")
        tampered_path = private_root / "tampered.viportfolio"
        tampered = json.loads(reported_path.read_text(encoding="utf-8"))
        ciphertext = bytearray(base64.b64decode(tampered["ciphertext"]))
        ciphertext[-1] ^= 0x01
        tampered["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
        _write_bytes(tampered_path, _json_bytes(tampered))
        try:
            load_private_portfolio_bundle(
                tampered_path,
                key_path,
                private_root=private_root,
                repository_root=ROOT,
            )
        except ValueError:
            tamper_status = "REJECTED"
        else:
            raise ValueError("Tampered synthetic ciphertext was not rejected")
        _artifact(
            output,
            artifacts,
            "05_verify.json",
            {
                "classification": CLASSIFICATION,
                "status": "ROUND_TRIP_VERIFIED",
                "action": ACTION_NO_ORDER,
                "public_receipt": verified_receipt.as_policy(),
                "blockers": list(verified_bundle.missing_guidance_inputs()),
                "tamper_check": tamper_status,
            },
        )

        reconciliation_generated_at = datetime(
            2026, 9, 22, 20, 15, tzinfo=timezone(timedelta(hours=8))
        )
        report = reconcile_portfolio_snapshots(
            verified_bundle.snapshot,
            pending_bundle.snapshot,
            report_id=f"{run_id}-synthetic-dual-snapshot-reconciliation",
            generated_at=reconciliation_generated_at,
        )
        if report.status != STATUS_MATCH_PENDING_HUMAN_CONFIRMATION:
            raise ValueError(f"Synthetic snapshots did not reconcile: {report.status}")
        report_payload = {
            **report.as_private_policy(),
            "classification": CLASSIFICATION,
            "synthetic_success_is_not_real_acceptance": True,
        }
        report_bytes = _json_bytes(report_payload)
        _artifact_bytes(
            output,
            artifacts,
            "06_dual_snapshot_reconciliation.json",
            report_bytes,
        )

        confirmed_at = datetime(
            2026, 9, 22, 20, 30, tzinfo=timezone(timedelta(hours=8))
        )
        confirmation_id = f"{run_id}-SYNTHETIC_RECONCILIATION_CONFIRMATION"
        confirmation = build_portfolio_confirmation_receipt(
            reconciliation_bytes=report_bytes,
            reconciliation_payload=report_payload,
            user_confirmation=USER_CONFIRMED_RECONCILIATION,
            confirmed_at=confirmed_at,
            confirmation_id=confirmation_id,
        )
        reparsed_confirmation = portfolio_confirmation_receipt_from_payload(
            confirmation.as_private_policy()
        )
        if reparsed_confirmation.receipt_sha256 != confirmation.receipt_sha256:
            raise ValueError("Synthetic confirmation receipt did not replay")
        _artifact(
            output,
            artifacts,
            "07_confirmation_receipt.json",
            {
                "classification": CLASSIFICATION,
                "synthetic_human_confirmation_rehearsal_only": True,
                "synthetic_success_is_not_real_acceptance": True,
                "private_receipt": confirmation.as_private_policy(),
                "public_fingerprint": confirmation.as_public_fingerprint(),
                "reconciliation_file_sha256": _sha256_bytes(report_bytes),
            },
        )

        final_snapshot = replace(
            pending_bundle.snapshot,
            reconciliation_status=RECONCILIATION_RECONCILED,
            reconciled_at=confirmed_at,
            evidence_refs=(
                *pending_bundle.snapshot.evidence_refs,
                {
                    "id": confirmation_id,
                    "report_id": report.report_id,
                    "confirmation_receipt_sha256": confirmation.receipt_sha256,
                    "classification": CLASSIFICATION,
                },
            ),
        )
        final_bundle = replace(pending_bundle, snapshot=final_snapshot)
        final_path = private_root / "final-confirmed.viportfolio"
        final_receipt = encrypt_private_portfolio_payload(
            final_bundle.as_policy(),
            final_path,
            key_path,
            private_root=private_root,
            repository_root=ROOT,
            created_at=confirmed_at,
        )
        reloaded_final, _ = load_private_portfolio_bundle(
            final_path,
            key_path,
            private_root=private_root,
            repository_root=ROOT,
        )
        if not reloaded_final.snapshot.is_reconciled:
            raise ValueError("Confirmed synthetic snapshot did not remain reconciled")
        _artifact(
            output,
            artifacts,
            "08_final_confirmed_encryption.json",
            {
                "classification": CLASSIFICATION,
                "synthetic_ciphertext_rehearsal_only": True,
                "receipt": final_receipt.as_policy(),
                "confirmation_evidence_bound": True,
            },
        )

    risk, guidance, dividend, simulated_bundle = _build_models(
        reloaded_final,
        guidance_fixture,
        risk_fixture,
    )
    risk_payload = {
        "classification": CLASSIFICATION,
        "synthetic_success_is_not_real_acceptance": True,
        "assessment": risk.as_policy(),
    }
    guidance_payload = {
        "classification": CLASSIFICATION,
        "synthetic_success_is_not_real_acceptance": True,
        "assessment": guidance.as_policy(),
    }
    dividend_payload = {
        "classification": CLASSIFICATION,
        "synthetic_success_is_not_real_acceptance": True,
        "assessment": dividend.as_policy(),
    }
    for name, payload in (
        ("09_portfolio_risk.json", risk_payload),
        ("10_position_guidance.json", guidance_payload),
        ("11_dividend_projection.json", dividend_payload),
    ):
        _artifact(output, artifacts, name, payload)

    as_of = simulated_bundle.snapshot.as_of.isoformat()
    generated_at = datetime.fromisoformat(
        str(guidance_fixture["generated_at"])
    ).isoformat()
    product_payload = _product_payload(
        artifacts,
        as_of=as_of,
        generated_at=generated_at,
        risk_status=risk.status,
        guidance_status=guidance.status,
        dividend_status=dividend.status,
    )
    _artifact(
        output,
        artifacts,
        "12_product_workbench_payload.json",
        product_payload,
    )
    read_model_summary = dict(product_read_model_mapper(product_payload))
    if read_model_summary.get("schema_version") != PRODUCT_WORKBENCH_SCHEMA_VERSION:
        raise ValueError("Product read model mapper returned an unsupported schema")
    product_portfolio = read_model_summary.get("portfolio")
    if not isinstance(product_portfolio, Mapping):
        raise ValueError("Product read model mapper must return portfolio status")
    product_status = product_portfolio.get("status_code")
    if not isinstance(product_status, str) or not product_status:
        raise ValueError("Product read model mapper must return a portfolio status code")
    m7_material = {
        "schema_version": M7_MATERIAL_SCHEMA_VERSION,
        "classification": CLASSIFICATION,
        "action": ACTION_NO_ORDER,
        "synthetic_success_is_not_real_acceptance": True,
        "M4_PERSONALIZED_ACCEPTANCE": "WAITING_R2",
        "M7_USER_ACCEPTANCE": "NOT_PASSED",
        "INITIAL_ASSISTED_USE": "NOT_REACHED",
        "M6_OPERATIONAL": "NOT_STARTED",
        "product_payload": "12_product_workbench_payload.json",
        "product_payload_sha256": artifacts[
            "12_product_workbench_payload.json"
        ]["sha256"],
        "source_stage_artifact_sha256": {
            name: artifacts[name]["sha256"]
            for name in (
                "06_dual_snapshot_reconciliation.json",
                "07_confirmation_receipt.json",
                "09_portfolio_risk.json",
                "10_position_guidance.json",
                "11_dividend_projection.json",
            )
        },
        "read_model_summary": read_model_summary,
    }
    _artifact(output, artifacts, "13_m7_candidate_material.json", m7_material)

    chain_stages = {
        "init": _stage(
            "01_init.json",
            business_status="SYNTHETIC_DRAFT_INITIALIZED",
        ),
        "validate": _stage(
            "02_validate.json",
            business_status="PENDING_RECONCILIATION",
        ),
        "encrypt": _stage(
            (
                "03_encrypt_reported.json; "
                "04_encrypt_confirmed_source.json; "
                "08_final_confirmed_encryption.json"
            ),
            business_status="ENCRYPTED",
        ),
        "verify": _stage(
            "05_verify.json",
            business_status="ROUND_TRIP_VERIFIED",
        ),
        "dual_snapshot_reconciliation": _stage(
            "06_dual_snapshot_reconciliation.json",
            business_status=report.status,
        ),
        "confirmation_receipt": _stage(
            "07_confirmation_receipt.json",
            business_status="SYNTHETIC_CONFIRMATION_ONLY",
        ),
        "portfolio_risk": _stage(
            "09_portfolio_risk.json",
            business_status=risk.status,
        ),
        "position_guidance": _stage(
            "10_position_guidance.json",
            business_status=guidance.status,
        ),
        "dividend_projection": _stage(
            "11_dividend_projection.json",
            business_status=dividend.status,
        ),
        "product_read_model": _stage(
            "12_product_workbench_payload.json",
            business_status=product_status,
        ),
        "m7_candidate_material": _stage(
            "13_m7_candidate_material.json",
            business_status="NOT_USER_ACCEPTED",
        ),
    }
    if not all(item["status"] == "EXERCISED" for item in chain_stages.values()):
        raise ValueError("Not every requested chain stage was exercised")

    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "classification": CLASSIFICATION,
        "action": ACTION_NO_ORDER,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_chain": list(chain_stages),
        "chain_stages": chain_stages,
        "all_requested_stages_exercised": True,
        "M4_PERSONALIZED_ACCEPTANCE": "WAITING_R2",
        "synthetic_success_is_not_real_acceptance": True,
        "real_private_inputs_used": False,
        "production_evidence_created": False,
        "M7_USER_ACCEPTANCE": "NOT_PASSED",
        "INITIAL_ASSISTED_USE": "NOT_REACHED",
        "M6_OPERATIONAL": "NOT_STARTED",
        "source_fixtures": fixture_receipts,
        "model_statuses": {
            "portfolio_risk": risk.status,
            "position_guidance": guidance.status,
            "dividend_projection": dividend.status,
        },
        "confirmation": {
            "receipt_sha256": confirmation.receipt_sha256,
            "reconciliation_sha256": confirmation.reconciliation_sha256,
            "synthetic_confirmation_only": True,
        },
        "artifacts": artifacts,
        "blockers": [
            "M4_PERSONALIZED_ACCEPTANCE remains WAITING_R2.",
            "Real user IPS, account, holdings, cash and cost-basis input was not used.",
            "M7 user acceptance and INITIAL_ASSISTED_USE remain unreached.",
            "M6 real-session operational evidence is not claimed.",
        ],
        "limitations": [
            "Every portfolio input originates from public synthetic fixtures.",
            "The ACTUAL namespace is used only to exercise the public reconciliation contract.",
            "Risk, guidance and dividend outputs are relabeled SIMULATED.",
            "No order, trade authorization, production evidence or personalized acceptance is created.",
        ],
        "synthetic_marker_sha256": marker_digest,
    }
    receipt_path = output / "receipt.json"
    receipt_file_sha256 = _write_json(receipt_path, receipt)
    _write_json(
        output / "receipt.sha256.json",
        {
            "schema_version": "file-sha256-v1",
            "path": "receipt.json",
            "sha256": receipt_file_sha256,
        },
    )
    return {
        "status": "COMPLETED_SYNTHETIC_ONLY",
        "output_dir": str(output),
        "receipt": str(receipt_path),
        "receipt_sha256": receipt_file_sha256,
        "M4_PERSONALIZED_ACCEPTANCE": "WAITING_R2",
        "synthetic_success_is_not_real_acceptance": True,
        "action": ACTION_NO_ORDER,
    }

"""Persist a forward-only RFC 3161 integrity checkpoint for public research."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from ...infrastructure.rfc3161_tsa import (
    DIGICERT_POLICY_OID,
    DIGICERT_TSA_URL,
    OpenSslRfc3161Tsa,
    TimestampVerification,
)


TIMESTAMP_CHAIN_SCHEMA = "prospective-timestamp-chain-v1"


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _write_receipt(directory: Path, receipt: dict[str, Any]) -> None:
    content = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (directory / "receipt.json").write_text(content, encoding="utf-8", newline="\n")


def _receipt(
    *,
    verification: TimestampVerification,
    endpoint_url: str,
    payload_file: str,
    request_file: str,
    response_file: str,
) -> dict[str, Any]:
    return {
        "schema_version": TIMESTAMP_CHAIN_SCHEMA,
        "status": "TIMESTAMP_VERIFIED_NOT_PIT_ADMITTED",
        "claim": "PAYLOAD_BYTES_EXISTED_NO_LATER_THAN_SIGNED_GEN_TIME",
        "strict_pit_admissible": False,
        "historical_registration_modified": False,
        "historical_retrospective_effect": "NONE",
        "action": "no_order",
        "payload_file": payload_file,
        "payload_sha256": verification.payload_sha256,
        "request_file": request_file,
        "request_sha256": verification.request_sha256,
        "response_file": response_file,
        "response_sha256": verification.response_sha256,
        "timestamp_endpoint": endpoint_url,
        "tsa_policy_oid": verification.policy_oid,
        "tsa_nonce": verification.nonce,
        "gen_time_utc": verification.gen_time_utc,
        "accuracy": verification.accuracy,
        "ca_bundle_sha256": verification.ca_bundle_sha256,
        "openssl_version": verification.openssl_version,
        "signature_chain_verification": "PASS",
        "payload_imprint_and_nonce_verification": "PASS",
    }


def create_prospective_timestamp_chain(
    *,
    root: Path,
    payload_path: Path,
    output_dir: Path,
    ca_bundle_path: Path,
    expected_policy_oid: str = DIGICERT_POLICY_OID,
    endpoint_url: str = DIGICERT_TSA_URL,
    openssl_binary: str | Path | None = None,
    public_research_only: bool = False,
) -> dict[str, Any]:
    if public_research_only is not True:
        raise ValueError("timestamping is restricted to public-research-only payloads")
    project_root = Path(root).resolve(strict=True)
    payload = Path(payload_path).resolve(strict=True)
    destination = Path(output_dir).resolve()
    runtime_root = (project_root / "runtime" / "prospective-timestamp-chains").resolve()
    if not _inside(payload, project_root) or not payload.is_file():
        raise ValueError("timestamp payload must be a file inside the project root")
    if not _inside(destination, runtime_root) or destination == runtime_root:
        raise ValueError("timestamp-chain output must be a new directory under runtime/prospective-timestamp-chains")
    if destination.exists():
        raise FileExistsError(f"timestamp-chain output already exists: {destination}")

    payload_bytes = payload.read_bytes()
    tsa = OpenSslRfc3161Tsa(
        ca_bundle_path=ca_bundle_path,
        expected_policy_oid=expected_policy_oid,
        endpoint_url=endpoint_url,
        openssl_binary=openssl_binary,
    )
    request = tsa.create_request(payload_bytes)
    response = tsa.submit_request(request)
    verification = tsa.verify_response(payload_bytes, request, response)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".timestamp-chain-", dir=destination.parent))
    try:
        payload_file = "payload.bin"
        request_file = "request.tsq"
        response_file = "response.tsr"
        (temporary / payload_file).write_bytes(payload_bytes)
        (temporary / request_file).write_bytes(request)
        (temporary / response_file).write_bytes(response)
        receipt = _receipt(
            verification=verification,
            endpoint_url=endpoint_url,
            payload_file=payload_file,
            request_file=request_file,
            response_file=response_file,
        )
        _write_receipt(temporary, receipt)
        temporary.rename(destination)
        return receipt
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def verify_prospective_timestamp_chain(
    *,
    chain_dir: Path,
    ca_bundle_path: Path,
    expected_policy_oid: str,
    openssl_binary: str | Path | None = None,
) -> dict[str, Any]:
    directory = Path(chain_dir).resolve(strict=True)
    receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    if receipt.get("schema_version") != TIMESTAMP_CHAIN_SCHEMA:
        raise ValueError("unsupported prospective timestamp-chain schema")
    if receipt.get("strict_pit_admissible") is not False or receipt.get("action") != "no_order":
        raise ValueError("timestamp receipt has unsafe or missing admission fields")
    if receipt.get("tsa_policy_oid") != expected_policy_oid:
        raise ValueError("timestamp receipt policy does not match the expected policy")

    payload = (directory / receipt["payload_file"]).read_bytes()
    request = (directory / receipt["request_file"]).read_bytes()
    response = (directory / receipt["response_file"]).read_bytes()
    actual_hashes = {
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "request_sha256": hashlib.sha256(request).hexdigest(),
        "response_sha256": hashlib.sha256(response).hexdigest(),
    }
    for key, value in actual_hashes.items():
        if receipt.get(key) != value:
            raise ValueError(f"timestamp-chain file hash mismatch: {key}")

    tsa = OpenSslRfc3161Tsa(
        ca_bundle_path=ca_bundle_path,
        expected_policy_oid=expected_policy_oid,
        endpoint_url=receipt["timestamp_endpoint"],
        openssl_binary=openssl_binary,
    )
    verification = tsa.verify_response(payload, request, response)
    expected = _receipt(
        verification=verification,
        endpoint_url=receipt["timestamp_endpoint"],
        payload_file=receipt["payload_file"],
        request_file=receipt["request_file"],
        response_file=receipt["response_file"],
    )
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise ValueError(f"timestamp receipt field does not match verified token: {key}")
    return receipt

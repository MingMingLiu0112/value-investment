"""Persist a forward-only RFC 3161 integrity checkpoint for public research."""
from __future__ import annotations

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
    TimestampRevocationVerification,
)


TIMESTAMP_CHAIN_SCHEMA_V1 = "prospective-timestamp-chain-v1"
TIMESTAMP_CHAIN_SCHEMA_V2 = "prospective-timestamp-chain-v2"
TIMESTAMP_CHAIN_SCHEMA = TIMESTAMP_CHAIN_SCHEMA_V2


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _write_receipt(directory: Path, receipt: dict[str, Any]) -> None:
    content = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (directory / "receipt.json").write_text(content, encoding="utf-8", newline="\n")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _receipt_v1(
    *,
    verification: TimestampVerification,
    endpoint_url: str,
    payload_file: str,
    request_file: str,
    response_file: str,
) -> dict[str, Any]:
    return {
        "schema_version": TIMESTAMP_CHAIN_SCHEMA_V1,
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


def _receipt_v2(
    *,
    verification: TimestampRevocationVerification,
    ca_bundle: bytes,
    endpoint_url: str,
    payload_file: str,
    request_file: str,
    response_file: str,
    ca_bundle_file: str,
    signer_certificate_file: str,
    intermediate_certificates_file: str,
    trust_anchor_file: str,
) -> dict[str, Any]:
    timestamp = verification.timestamp
    revocation_evidence = [
        {
            "certificate_sha256": item.certificate_sha256,
            "issuer_sha256": item.issuer_sha256,
            "distribution_point": item.distribution_point,
            "crl_file": f"crls/{item.certificate_sha256}.der",
            "crl_sha256": item.crl_sha256,
            "this_update_utc": item.this_update_utc,
            "next_update_utc": item.next_update_utc,
        }
        for item in verification.evidence
    ]
    return {
        "schema_version": TIMESTAMP_CHAIN_SCHEMA_V2,
        "status": "TIMESTAMP_VERIFIED_REVOCATION_CHECKED_NOT_PIT_ADMITTED",
        "claim": "PAYLOAD_BYTES_EXISTED_NO_LATER_THAN_SIGNED_GEN_TIME",
        "strict_pit_admissible": False,
        "historical_registration_modified": False,
        "historical_retrospective_effect": "NONE",
        "action": "no_order",
        "payload_file": payload_file,
        "payload_sha256": timestamp.payload_sha256,
        "request_file": request_file,
        "request_sha256": timestamp.request_sha256,
        "response_file": response_file,
        "response_sha256": timestamp.response_sha256,
        "timestamp_endpoint": endpoint_url,
        "tsa_policy_oid": timestamp.policy_oid,
        "tsa_nonce": timestamp.nonce,
        "gen_time_utc": timestamp.gen_time_utc,
        "accuracy": timestamp.accuracy,
        "openssl_version": timestamp.openssl_version,
        "ca_bundle_file": ca_bundle_file,
        "ca_bundle_sha256": _sha256(ca_bundle),
        "signer_certificate_file": signer_certificate_file,
        "signer_certificate_pem_sha256": _sha256(verification.signer_certificate_pem),
        "intermediate_certificates_file": intermediate_certificates_file,
        "intermediate_certificates_pem_sha256": [
            _sha256(item) for item in verification.intermediate_certificates_pem
        ],
        "trust_anchor_file": trust_anchor_file,
        "trust_anchor_pem_sha256": _sha256(verification.trust_anchor_pem),
        "signature_chain_verification": "PASS_ON_PINNED_CERTIFICATE_PATH",
        "payload_imprint_and_nonce_verification": "PASS",
        "revocation_status": "PASS_AT_SIGNED_GEN_TIME",
        "revocation_policy": "DIRECT_FULL_SCOPE_CRL_ONLY",
        "revocation_evidence": revocation_evidence,
    }


def _read_bound_file(directory: Path, relative_name: Any) -> bytes:
    if not isinstance(relative_name, str) or not relative_name:
        raise ValueError("timestamp receipt contains an invalid file path")
    path = (directory / relative_name).resolve(strict=True)
    if not _inside(path, directory) or not path.is_file():
        raise ValueError("timestamp receipt file path escapes the chain directory")
    return path.read_bytes()


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

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".timestamp-chain-", dir=destination.parent))
    try:
        payload_file = "payload.bin"
        request_file = "request.tsq"
        response_file = "response.tsr"
        ca_bundle_file = "ca-bundle.pem"
        signer_certificate_file = "signer.pem"
        intermediate_certificates_file = "intermediates.pem"
        trust_anchor_file = "trust-anchor.pem"
        payload_bytes = payload.read_bytes()
        ca_bundle_bytes = Path(ca_bundle_path).expanduser().resolve(strict=True).read_bytes()
        (temporary / payload_file).write_bytes(payload_bytes)
        (temporary / ca_bundle_file).write_bytes(ca_bundle_bytes)

        tsa = OpenSslRfc3161Tsa(
            ca_bundle_path=temporary / ca_bundle_file,
            expected_policy_oid=expected_policy_oid,
            endpoint_url=endpoint_url,
            openssl_binary=openssl_binary,
        )
        request = tsa.create_request(payload_bytes)
        response = tsa.submit_request(request)
        verification = tsa.verify_response_with_revocation(payload_bytes, request, response)

        (temporary / request_file).write_bytes(request)
        (temporary / response_file).write_bytes(response)
        (temporary / signer_certificate_file).write_bytes(verification.signer_certificate_pem)
        (temporary / intermediate_certificates_file).write_bytes(
            b"".join(verification.intermediate_certificates_pem)
        )
        (temporary / trust_anchor_file).write_bytes(verification.trust_anchor_pem)
        crl_directory = temporary / "crls"
        crl_directory.mkdir(parents=True, exist_ok=True)
        for item in verification.evidence:
            crl_path = crl_directory / f"{item.certificate_sha256}.der"
            crl_path.parent.mkdir(parents=True, exist_ok=True)
            crl_path.write_bytes(item.crl_der)

        receipt = _receipt_v2(
            verification=verification,
            ca_bundle=ca_bundle_bytes,
            endpoint_url=endpoint_url,
            payload_file=payload_file,
            request_file=request_file,
            response_file=response_file,
            ca_bundle_file=ca_bundle_file,
            signer_certificate_file=signer_certificate_file,
            intermediate_certificates_file=intermediate_certificates_file,
            trust_anchor_file=trust_anchor_file,
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
    expected_policy_oid: str,
    ca_bundle_path: Path | None = None,
    openssl_binary: str | Path | None = None,
) -> dict[str, Any]:
    directory = Path(chain_dir).resolve(strict=True)
    receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    schema = receipt.get("schema_version")
    if schema not in {TIMESTAMP_CHAIN_SCHEMA_V1, TIMESTAMP_CHAIN_SCHEMA_V2}:
        raise ValueError("unsupported prospective timestamp-chain schema")
    if receipt.get("strict_pit_admissible") is not False or receipt.get("action") != "no_order":
        raise ValueError("timestamp receipt has unsafe or missing admission fields")
    if receipt.get("tsa_policy_oid") != expected_policy_oid:
        raise ValueError("timestamp receipt policy does not match the expected policy")

    payload = _read_bound_file(directory, receipt.get("payload_file"))
    request = _read_bound_file(directory, receipt.get("request_file"))
    response = _read_bound_file(directory, receipt.get("response_file"))
    actual_hashes = {
        "payload_sha256": _sha256(payload),
        "request_sha256": _sha256(request),
        "response_sha256": _sha256(response),
    }
    for key, value in actual_hashes.items():
        if receipt.get(key) != value:
            raise ValueError(f"timestamp-chain file hash mismatch: {key}")

    if schema == TIMESTAMP_CHAIN_SCHEMA_V1:
        if ca_bundle_path is None:
            raise ValueError("legacy v1 timestamp verification requires the original CA bundle")
        tsa = OpenSslRfc3161Tsa(
            ca_bundle_path=ca_bundle_path,
            expected_policy_oid=expected_policy_oid,
            endpoint_url=receipt["timestamp_endpoint"],
            openssl_binary=openssl_binary,
        )
        verification = tsa.verify_response(payload, request, response)
        expected = _receipt_v1(
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

    ca_bundle = _read_bound_file(directory, receipt.get("ca_bundle_file"))
    if _sha256(ca_bundle) != receipt.get("ca_bundle_sha256"):
        raise ValueError("timestamp-chain CA bundle hash mismatch")
    if ca_bundle_path is not None:
        supplied_ca_bundle = Path(ca_bundle_path).expanduser().resolve(strict=True).read_bytes()
        if _sha256(supplied_ca_bundle) != receipt.get("ca_bundle_sha256"):
            raise ValueError("supplied CA bundle differs from the bundle retained with the chain")

    evidence_records = receipt.get("revocation_evidence")
    if not isinstance(evidence_records, list) or not evidence_records:
        raise ValueError("v2 timestamp chain is missing revocation evidence")
    retained_crls: dict[str, bytes] = {}
    for record in evidence_records:
        if not isinstance(record, dict):
            raise ValueError("v2 timestamp chain has malformed revocation evidence")
        certificate_sha256 = record.get("certificate_sha256")
        if not isinstance(certificate_sha256, str) or certificate_sha256 in retained_crls:
            raise ValueError("v2 timestamp chain has duplicate or malformed CRL bindings")
        crl_der = _read_bound_file(directory, record.get("crl_file"))
        if _sha256(crl_der) != record.get("crl_sha256"):
            raise ValueError("timestamp-chain CRL hash mismatch")
        retained_crls[certificate_sha256] = crl_der

    tsa = OpenSslRfc3161Tsa(
        ca_bundle_path=directory / receipt["ca_bundle_file"],
        expected_policy_oid=expected_policy_oid,
        endpoint_url=receipt["timestamp_endpoint"],
        openssl_binary=openssl_binary,
    )
    verification = tsa.verify_response_with_revocation(
        payload,
        request,
        response,
        crl_evidence_by_certificate_sha256=retained_crls,
    )
    for key, relative_name in (
        ("signer_certificate_pem_sha256", receipt.get("signer_certificate_file")),
        ("trust_anchor_pem_sha256", receipt.get("trust_anchor_file")),
    ):
        if _sha256(_read_bound_file(directory, relative_name)) != receipt.get(key):
            raise ValueError(f"timestamp-chain certificate hash mismatch: {key}")
    intermediate_bytes = _read_bound_file(directory, receipt.get("intermediate_certificates_file"))
    if _sha256(intermediate_bytes) != _sha256(b"".join(verification.intermediate_certificates_pem)):
        raise ValueError("timestamp-chain intermediate certificate bytes do not match the verified path")

    expected = _receipt_v2(
        verification=verification,
        ca_bundle=ca_bundle,
        endpoint_url=receipt["timestamp_endpoint"],
        payload_file=receipt["payload_file"],
        request_file=receipt["request_file"],
        response_file=receipt["response_file"],
        ca_bundle_file=receipt["ca_bundle_file"],
        signer_certificate_file=receipt["signer_certificate_file"],
        intermediate_certificates_file=receipt["intermediate_certificates_file"],
        trust_anchor_file=receipt["trust_anchor_file"],
    )
    if receipt != expected:
        differing_keys = sorted(key for key in set(receipt) | set(expected) if receipt.get(key) != expected.get(key))
        raise ValueError(f"timestamp receipt fields do not match verification: {', '.join(differing_keys)}")
    return receipt

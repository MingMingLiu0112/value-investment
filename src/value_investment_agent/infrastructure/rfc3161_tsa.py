"""RFC 3161 requests and verification through the OpenSSL command line."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Sequence
from urllib.parse import urlparse

import requests


DIGICERT_TSA_URL = "http://timestamp.digicert.com"
DIGICERT_POLICY_OID = "2.16.840.1.114412.7.1"
MAX_TIMESTAMP_RESPONSE_BYTES = 2 * 1024 * 1024


class TimestampVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class TimestampVerification:
    payload_sha256: str
    request_sha256: str
    response_sha256: str
    ca_bundle_sha256: str
    nonce: str
    gen_time_utc: str
    policy_oid: str
    accuracy: str | None
    openssl_version: str


def resolve_openssl(binary: str | Path | None = None) -> Path:
    candidate = str(binary) if binary is not None else os.environ.get("OPENSSL_BIN")
    if candidate:
        located = shutil.which(candidate)
        path = Path(located or candidate)
        if path.is_file():
            return path.resolve()
        raise FileNotFoundError(f"OpenSSL executable not found: {candidate}")

    located = shutil.which("openssl")
    if located:
        return Path(located).resolve()

    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_root = Path(git).resolve().parent.parent
            for path in (git_root / "usr/bin/openssl.exe", git_root / "mingw64/bin/openssl.exe"):
                if path.is_file():
                    return path.resolve()
    raise FileNotFoundError("OpenSSL 3.x is required; set OPENSSL_BIN to its executable")


def _run_openssl(binary: Path, args: Sequence[str], *, timeout: int = 30) -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().replace("\r", " ")
        raise TimestampVerificationError(
            f"OpenSSL {' '.join(args[:2])} failed ({result.returncode}): {detail[:500]}"
        )
    return result.stdout.strip()


def _field(text: str, label: str) -> str:
    match = re.search(rf"(?m)^{re.escape(label)}:\s*(.*?)\s*$", text)
    if not match:
        raise TimestampVerificationError(f"RFC 3161 response is missing {label}")
    return match.group(1)


def _nonce_value(text: str) -> str:
    raw = _field(text, "Nonce")
    if raw.lower().startswith("0x"):
        try:
            return str(int(raw[2:], 16))
        except ValueError as exc:
            raise TimestampVerificationError("RFC 3161 nonce is malformed") from exc
    if raw.isdecimal():
        return str(int(raw))
    raise TimestampVerificationError("RFC 3161 nonce is malformed")


def _query_imprint(query_text: str) -> tuple[str, str]:
    algorithm = _field(query_text, "Hash Algorithm").lower()
    if algorithm != "sha256":
        raise TimestampVerificationError("timestamp request did not use SHA-256")
    try:
        message_data = query_text.split("Message data:", 1)[1].split("Policy OID:", 1)[0]
    except IndexError as exc:
        raise TimestampVerificationError("timestamp request is missing its message imprint") from exc
    octets: list[str] = []
    for line in message_data.splitlines():
        if " - " not in line:
            continue
        dump = line.split(" - ", 1)[1].split("  ", 1)[0]
        octets.extend(re.findall(r"[0-9a-fA-F]{2}", dump))
    if len(octets) != hashlib.sha256().digest_size:
        raise TimestampVerificationError("timestamp request has a malformed SHA-256 imprint")
    return algorithm, "".join(octets).lower()


def _parse_gen_time(value: str) -> datetime:
    match = re.fullmatch(
        r"([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})\s+GMT",
        value,
    )
    if not match:
        raise TimestampVerificationError("OpenSSL returned an unsupported genTime format")
    month = {name: index for index, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        start=1,
    )}.get(match.group(1))
    if month is None:
        raise TimestampVerificationError("OpenSSL returned an invalid genTime month")
    try:
        return datetime.strptime(
            f"{match.group(4)}-{month:02d}-{int(match.group(2)):02d}T{match.group(3)}",
            "%Y-%m-%dT%H:%M:%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise TimestampVerificationError("OpenSSL returned an invalid genTime") from exc


def _validate_endpoint(endpoint_url: str) -> None:
    parsed = urlparse(endpoint_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("TSA endpoint must be an absolute HTTP or HTTPS URL")


class OpenSslRfc3161Tsa:
    def __init__(
        self,
        *,
        ca_bundle_path: Path,
        expected_policy_oid: str,
        endpoint_url: str = DIGICERT_TSA_URL,
        openssl_binary: str | Path | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        _validate_endpoint(endpoint_url)
        if not re.fullmatch(r"\d+(?:\.\d+)+", expected_policy_oid):
            raise ValueError("expected_policy_oid must be a numeric OID")
        ca_bundle = Path(ca_bundle_path).expanduser().resolve()
        if not ca_bundle.is_file() or ca_bundle.stat().st_size == 0:
            raise FileNotFoundError(f"CA bundle is missing or empty: {ca_bundle}")
        if timeout_seconds < 1 or timeout_seconds > 120:
            raise ValueError("timeout_seconds must be between 1 and 120")
        self.ca_bundle_path = ca_bundle
        self.expected_policy_oid = expected_policy_oid
        self.endpoint_url = endpoint_url
        self.openssl_binary = resolve_openssl(openssl_binary)
        self.timeout_seconds = timeout_seconds

    def create_request(self, payload: bytes) -> bytes:
        if not payload:
            raise ValueError("timestamp payload must not be empty")
        with tempfile.TemporaryDirectory(prefix="via-rfc3161-") as directory:
            root = Path(directory)
            data_path = root / "payload.bin"
            request_path = root / "request.tsq"
            data_path.write_bytes(payload)
            _run_openssl(
                self.openssl_binary,
                ["ts", "-query", "-data", str(data_path), "-sha256", "-cert", "-out", str(request_path)],
                timeout=self.timeout_seconds,
            )
            request = request_path.read_bytes()
            if not request:
                raise TimestampVerificationError("OpenSSL produced an empty timestamp request")
            return request

    def submit_request(self, request: bytes) -> bytes:
        if not request:
            raise ValueError("timestamp request must not be empty")
        response = requests.post(
            self.endpoint_url,
            data=request,
            headers={
                "Content-Type": "application/timestamp-query",
                "Accept": "application/timestamp-reply",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/timestamp-reply":
            raise TimestampVerificationError(f"unexpected TSA content type: {content_type or 'missing'}")
        if not response.content or len(response.content) > MAX_TIMESTAMP_RESPONSE_BYTES:
            raise TimestampVerificationError("TSA response is empty or exceeds the size limit")
        return response.content

    def verify_response(self, payload: bytes, request: bytes, response: bytes) -> TimestampVerification:
        if not payload or not request or not response:
            raise ValueError("payload, request, and response must all be non-empty")
        if len(response) > MAX_TIMESTAMP_RESPONSE_BYTES:
            raise TimestampVerificationError("TSA response exceeds the size limit")
        with tempfile.TemporaryDirectory(prefix="via-rfc3161-verify-") as directory:
            root = Path(directory)
            data_path = root / "payload.bin"
            request_path = root / "request.tsq"
            response_path = root / "response.tsr"
            data_path.write_bytes(payload)
            request_path.write_bytes(request)
            response_path.write_bytes(response)

            query_text = _run_openssl(
                self.openssl_binary,
                ["ts", "-query", "-in", str(request_path), "-text"],
                timeout=self.timeout_seconds,
            )
            reply_text = _run_openssl(
                self.openssl_binary,
                ["ts", "-reply", "-in", str(response_path), "-text"],
                timeout=self.timeout_seconds,
            )
            status = _field(reply_text, "Status").rstrip(".").lower()
            if status != "granted":
                raise TimestampVerificationError(f"TSA did not grant the request: {status}")
            _, query_imprint = _query_imprint(query_text)
            if query_imprint != hashlib.sha256(payload).hexdigest():
                raise TimestampVerificationError("timestamp request imprint does not match the payload")
            query_nonce = _nonce_value(query_text)
            response_nonce = _nonce_value(reply_text)
            if query_nonce != response_nonce:
                raise TimestampVerificationError("TSA response nonce does not match the request")
            policy_oid = _field(reply_text, "Policy OID")
            if policy_oid != self.expected_policy_oid:
                raise TimestampVerificationError("TSA response policy OID does not match the configured policy")
            if _field(reply_text, "Hash Algorithm").lower() != "sha256":
                raise TimestampVerificationError("TSA response did not use SHA-256")
            if not re.search(r"(?im)^Certificate required:\s*yes\s*$", query_text):
                raise TimestampVerificationError("timestamp request did not require the signer certificate")
            gen_time = _parse_gen_time(_field(reply_text, "Time stamp"))
            accuracy_match = re.search(r"(?m)^Accuracy:\s*(.*?)\s*$", reply_text)
            verify_args = [
                "ts", "-verify", "-queryfile", str(request_path),
                "-in", str(response_path),
                "-CAfile", str(self.ca_bundle_path), "-attime", str(int(gen_time.timestamp())),
            ]
            _run_openssl(self.openssl_binary, verify_args, timeout=self.timeout_seconds)
            version = _run_openssl(self.openssl_binary, ["version"], timeout=self.timeout_seconds)

        return TimestampVerification(
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            request_sha256=hashlib.sha256(request).hexdigest(),
            response_sha256=hashlib.sha256(response).hexdigest(),
            ca_bundle_sha256=hashlib.sha256(self.ca_bundle_path.read_bytes()).hexdigest(),
            nonce=response_nonce,
            gen_time_utc=gen_time.isoformat().replace("+00:00", "Z"),
            policy_oid=policy_oid,
            accuracy=accuracy_match.group(1) if accuracy_match else None,
            openssl_version=version,
        )

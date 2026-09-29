"""RFC 3161 requests and verification through the OpenSSL command line."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import tempfile
from typing import Sequence
from urllib.parse import quote, urlparse

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtendedKeyUsageOID


DIGICERT_TSA_URL = "http://timestamp.digicert.com"
DIGICERT_POLICY_OID = "2.16.840.1.114412.7.1"
MAX_TIMESTAMP_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CRL_BYTES = 8 * 1024 * 1024
MAX_CERTIFICATE_CHAIN_LENGTH = 12


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


@dataclass(frozen=True)
class TimestampRevocationEvidence:
    certificate_sha256: str
    issuer_sha256: str
    distribution_point: str
    crl_der: bytes
    crl_sha256: str
    this_update_utc: str
    next_update_utc: str


@dataclass(frozen=True)
class TimestampRevocationVerification:
    timestamp: TimestampVerification
    signer_certificate_pem: bytes
    intermediate_certificates_pem: tuple[bytes, ...]
    trust_anchor_pem: bytes
    evidence: tuple[TimestampRevocationEvidence, ...]


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


def _certificate_sha256(certificate: x509.Certificate) -> str:
    return certificate.fingerprint(hashes.SHA256()).hex()


def _openssl_store_uri(path: Path) -> str:
    value = Path(path).resolve().as_posix()
    if os.name == "nt":
        drive, remainder = value[0].lower(), value[2:]
        return f"file:/{drive}{quote(remainder, safe='/:')}"
    return f"file:{quote(value, safe='/:')}"


def _certificate_pem(certificate: x509.Certificate) -> bytes:
    return certificate.public_bytes(Encoding.PEM)


def _load_pem_certificates(content: bytes) -> list[x509.Certificate]:
    blocks = re.findall(
        rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        content,
        flags=re.DOTALL,
    )
    if not blocks:
        raise TimestampVerificationError("PEM certificate bundle is empty or malformed")
    return [x509.load_pem_x509_certificate(block) for block in blocks]


def _is_ca(certificate: x509.Certificate) -> bool:
    try:
        return certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        return False


def _build_trusted_certificate_path(
    signer: x509.Certificate,
    embedded_certificates: Sequence[x509.Certificate],
    ca_bundle: bytes,
) -> tuple[x509.Certificate, ...]:
    trusted_certificates = _load_pem_certificates(ca_bundle)
    trusted = {_certificate_sha256(certificate) for certificate in trusted_certificates}
    candidates = {
        _certificate_sha256(certificate): certificate
        for certificate in (*embedded_certificates, *trusted_certificates)
    }

    def walk(
        current: x509.Certificate,
        path: tuple[x509.Certificate, ...],
    ) -> list[tuple[x509.Certificate, ...]]:
        fingerprint = _certificate_sha256(current)
        if fingerprint in trusted:
            if not _is_ca(current):
                return []
            return [path]
        if len(path) >= MAX_CERTIFICATE_CHAIN_LENGTH:
            return []

        paths: list[tuple[x509.Certificate, ...]] = []
        for issuer in sorted(candidates.values(), key=_certificate_sha256):
            issuer_fingerprint = _certificate_sha256(issuer)
            if issuer_fingerprint in {_certificate_sha256(item) for item in path}:
                continue
            if current.issuer != issuer.subject or not _is_ca(issuer):
                continue
            try:
                current.verify_directly_issued_by(issuer)
            except (InvalidSignature, ValueError):
                continue
            paths.extend(walk(issuer, (*path, issuer)))
        return paths

    paths = walk(signer, (signer,))
    if not paths:
        raise TimestampVerificationError("timestamp signer has no path to a configured CA trust anchor")
    unique_paths = {
        tuple(_certificate_sha256(certificate) for certificate in path): path
        for path in paths
    }
    if len(unique_paths) != 1:
        raise TimestampVerificationError("timestamp signer has an ambiguous path to configured trust anchors")
    return next(iter(unique_paths.values()))


def _crl_distribution_point(certificate: x509.Certificate) -> str:
    try:
        points = certificate.extensions.get_extension_for_class(x509.CRLDistributionPoints).value
    except x509.ExtensionNotFound as exc:
        raise TimestampVerificationError("certificate has no CRL distribution point") from exc
    if len(points) != 1:
        raise TimestampVerificationError("only one full-scope CRL distribution point is supported")
    point = points[0]
    if point.reasons is not None or point.crl_issuer is not None or point.full_name is None:
        raise TimestampVerificationError("partial or indirect CRL distribution points are unsupported")
    if len(point.full_name) != 1 or not isinstance(point.full_name[0], x509.UniformResourceIdentifier):
        raise TimestampVerificationError("CRL distribution point must contain exactly one URI")
    freshest_oid = x509.ObjectIdentifier("2.5.29.46")
    if any(extension.oid == freshest_oid for extension in certificate.extensions):
        raise TimestampVerificationError("delta CRL distribution is unsupported")
    uri = point.full_name[0].value
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise TimestampVerificationError("CRL distribution point is not an absolute HTTP(S) URL")
    return uri


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, address: str, port: int, timeout: int) -> None:
        super().__init__(address, port=port, timeout=timeout, context=ssl.create_default_context())
        self._server_hostname = hostname

    def connect(self) -> None:
        raw_socket = socket.create_connection((self.host, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self._server_hostname)


def _request_public_bytes(
    method: str,
    uri: str,
    *,
    headers: dict[str, str],
    body: bytes | None = None,
    max_bytes: int,
    error_label: str,
    address_resolver=None,
    connection_factory=None,
    timeout_seconds: int = 15,
) -> tuple[bytes, str | None]:
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise TimestampVerificationError(f"unsafe {error_label} URL")
    if parsed.fragment:
        raise TimestampVerificationError(f"{error_label} URL must not contain a fragment")
    hostname = parsed.hostname
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise TimestampVerificationError(f"{error_label} URL must use a DNS hostname")

    default_port = 443 if parsed.scheme == "https" else 80
    try:
        port = parsed.port or default_port
    except ValueError as exc:
        raise TimestampVerificationError(f"{error_label} URL has an invalid port") from exc
    if not 1 <= port <= 65535:
        raise TimestampVerificationError(f"{error_label} URL has an invalid port")

    resolver = address_resolver or socket.getaddrinfo
    try:
        answers = resolver(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise TimestampVerificationError(f"{error_label} DNS lookup failed") from exc
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses:
        raise TimestampVerificationError(f"{error_label} resolved to no addresses")
    try:
        parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
    except ValueError as exc:
        raise TimestampVerificationError(f"{error_label} resolved to an invalid address") from exc
    if any(not address.is_global for address in parsed_addresses):
        raise TimestampVerificationError(f"{error_label} resolved to a non-public address")

    pinned_address = addresses[0]
    if connection_factory is None:
        if parsed.scheme == "https":
            connection = _PinnedHTTPSConnection(hostname, pinned_address, port, timeout_seconds)
        else:
            connection = http.client.HTTPConnection(pinned_address, port=port, timeout=timeout_seconds)
    else:
        connection = connection_factory(parsed.scheme, hostname, pinned_address, port, timeout_seconds)

    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    host_header = hostname if port == default_port else f"{hostname}:{port}"
    request_headers = {**headers, "Host": host_header, "Connection": "close"}
    try:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        if response.status != 200:
            raise TimestampVerificationError(
                f"{error_label} endpoint returned HTTP {response.status}; redirects are rejected"
            )
        content_length = response.getheader("Content-Length")
        if content_length is not None and int(content_length) > max_bytes:
            raise TimestampVerificationError(f"{error_label} response exceeds the size limit")
        content = response.read(max_bytes + 1)
        if not content or len(content) > max_bytes:
            raise TimestampVerificationError(f"{error_label} response is empty or exceeds the size limit")
        return content, response.getheader("Content-Type")
    except (OSError, http.client.HTTPException, ssl.SSLError, ValueError) as exc:
        if isinstance(exc, TimestampVerificationError):
            raise
        raise TimestampVerificationError(f"{error_label} request failed") from exc
    finally:
        connection.close()


def _fetch_crl_bytes(
    uri: str,
    *,
    address_resolver=None,
    connection_factory=None,
    timeout_seconds: int = 15,
) -> bytes:
    parsed = urlparse(uri)
    try:
        port = parsed.port
    except ValueError as exc:
        raise TimestampVerificationError("CRL distribution point has an invalid port") from exc
    if port not in (None, 80 if parsed.scheme == "http" else 443):
        raise TimestampVerificationError("non-default CRL distribution point ports are unsupported")
    content, _ = _request_public_bytes(
        "GET",
        uri,
        headers={"Accept": "application/pkix-crl, application/octet-stream"},
        max_bytes=MAX_CRL_BYTES,
        error_label="CRL",
        address_resolver=address_resolver,
        connection_factory=connection_factory,
        timeout_seconds=timeout_seconds,
    )
    return content


def _validate_crl(
    certificate: x509.Certificate,
    issuer: x509.Certificate,
    crl_der: bytes,
    gen_time: datetime,
    distribution_point: str,
) -> TimestampRevocationEvidence:
    if not crl_der or len(crl_der) > MAX_CRL_BYTES:
        raise TimestampVerificationError("CRL evidence is empty or exceeds the size limit")
    try:
        crl = x509.load_der_x509_crl(crl_der)
    except ValueError as exc:
        raise TimestampVerificationError("CRL evidence is not a DER X.509 CRL") from exc
    if crl.issuer != issuer.subject:
        raise TimestampVerificationError("CRL issuer does not match the selected certificate issuer")

    try:
        delta_oid = x509.ExtensionOID.DELTA_CRL_INDICATOR
        crl.extensions.get_extension_for_oid(delta_oid)
    except x509.ExtensionNotFound:
        pass
    else:
        raise TimestampVerificationError("delta CRLs are unsupported")

    supported_crl_extensions = {
        x509.ExtensionOID.AUTHORITY_KEY_IDENTIFIER,
        x509.ExtensionOID.CRL_NUMBER,
        x509.ExtensionOID.ISSUING_DISTRIBUTION_POINT,
    }
    if any(
        extension.critical and extension.oid not in supported_crl_extensions
        for extension in crl.extensions
    ):
        raise TimestampVerificationError("CRL contains an unsupported critical extension")

    try:
        issuing_point = crl.extensions.get_extension_for_class(x509.IssuingDistributionPoint).value
    except x509.ExtensionNotFound:
        issuing_point = None
    if issuing_point is not None and (
        issuing_point.indirect_crl
        or issuing_point.only_contains_user_certs
        or issuing_point.only_contains_ca_certs
        or issuing_point.only_contains_attribute_certs
        or issuing_point.only_some_reasons is not None
        or issuing_point.full_name is not None
        or issuing_point.relative_name is not None
    ):
        raise TimestampVerificationError("restricted or indirect CRL scope is unsupported")

    try:
        key_usage = issuer.extensions.get_extension_for_class(x509.KeyUsage).value
    except x509.ExtensionNotFound:
        key_usage = None
    if key_usage is not None and not key_usage.crl_sign:
        raise TimestampVerificationError("CRL issuer certificate lacks cRLSign usage")
    try:
        signature_valid = crl.is_signature_valid(issuer.public_key())
    except (InvalidSignature, ValueError) as exc:
        raise TimestampVerificationError("CRL signature does not verify with the selected issuer") from exc
    if not signature_valid:
        raise TimestampVerificationError("CRL signature does not verify with the selected issuer")

    this_update = crl.last_update_utc
    next_update = crl.next_update_utc
    if next_update is None:
        raise TimestampVerificationError("CRL has no nextUpdate and cannot prove bounded freshness")
    if not this_update <= gen_time <= next_update:
        raise TimestampVerificationError("CRL validity interval does not cover the TSA genTime")

    serials: set[int] = set()
    for revoked in crl:
        if revoked.serial_number in serials:
            raise TimestampVerificationError("CRL contains a duplicate revoked serial number")
        serials.add(revoked.serial_number)
        if revoked.serial_number != certificate.serial_number:
            continue
        supported_critical_entry_extensions = {
            x509.ObjectIdentifier("2.5.29.24"),
        }
        if any(
            extension.critical and extension.oid not in supported_critical_entry_extensions
            for extension in revoked.extensions
        ):
            raise TimestampVerificationError(
                "matching CRL entry contains an unsupported critical extension"
            )
        effective_dates = [revoked.revocation_date_utc]
        try:
            invalidity_date = revoked.extensions.get_extension_for_oid(
                x509.ObjectIdentifier("2.5.29.24")
            ).value.invalidity_date
        except x509.ExtensionNotFound:
            invalidity_date = None
        if invalidity_date is not None:
            if invalidity_date.tzinfo is None:
                invalidity_date = invalidity_date.replace(tzinfo=timezone.utc)
            effective_dates.append(invalidity_date)
        if min(effective_dates) <= gen_time:
            raise TimestampVerificationError("timestamp signer certificate was revoked at genTime")

    try:
        authority_key_id = crl.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
    except x509.ExtensionNotFound:
        authority_key_id = None
    if authority_key_id is not None and (
        authority_key_id.authority_cert_issuer is not None
        or authority_key_id.authority_cert_serial_number is not None
    ):
        raise TimestampVerificationError("CRL authority key identifier uses unsupported issuer fields")
    if authority_key_id is not None and authority_key_id.key_identifier is not None:
        try:
            subject_key_id = issuer.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
        except x509.ExtensionNotFound:
            subject_key_id = None
        if subject_key_id is not None and subject_key_id != authority_key_id.key_identifier:
            raise TimestampVerificationError("CRL authority key identifier does not match the selected issuer")

    return TimestampRevocationEvidence(
        certificate_sha256=_certificate_sha256(certificate),
        issuer_sha256=_certificate_sha256(issuer),
        distribution_point=distribution_point,
        crl_der=crl_der,
        crl_sha256=hashlib.sha256(crl_der).hexdigest(),
        this_update_utc=this_update.isoformat().replace("+00:00", "Z"),
        next_update_utc=next_update.isoformat().replace("+00:00", "Z"),
    )


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
        response, content_type = _request_public_bytes(
            "POST",
            self.endpoint_url,
            body=request,
            headers={
                "Content-Type": "application/timestamp-query",
                "Accept": "application/timestamp-reply",
            },
            max_bytes=MAX_TIMESTAMP_RESPONSE_BYTES,
            error_label="TSA",
            timeout_seconds=self.timeout_seconds,
        )
        content_type = (content_type or "").split(";", 1)[0].strip().lower()
        if content_type != "application/timestamp-reply":
            raise TimestampVerificationError(f"unexpected TSA content type: {content_type or 'missing'}")
        return response

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

    def verify_response_with_revocation(
        self,
        payload: bytes,
        request: bytes,
        response: bytes,
        *,
        crl_evidence_by_certificate_sha256: dict[str, bytes] | None = None,
    ) -> TimestampRevocationVerification:
        timestamp = self.verify_response(payload, request, response)
        ca_bundle = self.ca_bundle_path.read_bytes()
        retained_crls = crl_evidence_by_certificate_sha256 or {}

        with tempfile.TemporaryDirectory(prefix="via-rfc3161-revocation-") as directory:
            root = Path(directory)
            response_path = root / "response.tsr"
            token_path = root / "token.der"
            token_certificates_path = root / "token-certificates.pem"
            signer_path = root / "signer.pem"
            tst_info_path = root / "tst-info.der"
            response_path.write_bytes(response)

            _run_openssl(
                self.openssl_binary,
                ["ts", "-reply", "-in", str(response_path), "-token_out", "-out", str(token_path)],
                timeout=self.timeout_seconds,
            )
            _run_openssl(
                self.openssl_binary,
                [
                    "cms", "-verify", "-inform", "DER", "-in", str(token_path),
                    "-signer", str(signer_path), "-noverify", "-binary", "-out", str(tst_info_path),
                ],
                timeout=self.timeout_seconds,
            )
            _run_openssl(
                self.openssl_binary,
                [
                    "pkcs7", "-inform", "DER", "-in", str(token_path),
                    "-print_certs", "-out", str(token_certificates_path),
                ],
                timeout=self.timeout_seconds,
            )
            signer_pem = signer_path.read_bytes()
            signer = x509.load_pem_x509_certificate(signer_pem)
            eku = signer.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
            if not eku.critical or list(eku.value) != [ExtendedKeyUsageOID.TIME_STAMPING]:
                raise TimestampVerificationError("TSA signer must have only the critical timeStamping EKU")

            embedded_certificates = _load_pem_certificates(token_certificates_path.read_bytes())
            signer_fingerprint = _certificate_sha256(signer)
            if signer_fingerprint not in {
                _certificate_sha256(certificate) for certificate in embedded_certificates
            }:
                raise TimestampVerificationError("CMS signer certificate is not embedded in the timestamp token")

            path = _build_trusted_certificate_path(signer, embedded_certificates, ca_bundle)
            if len(path) < 2 or _certificate_sha256(path[0]) != signer_fingerprint:
                raise TimestampVerificationError("timestamp certificate path is incomplete")

            gen_time = datetime.fromisoformat(timestamp.gen_time_utc.replace("Z", "+00:00"))
            evidence: list[TimestampRevocationEvidence] = []
            for certificate, issuer in zip(path[:-1], path[1:]):
                distribution_point = _crl_distribution_point(certificate)
                certificate_fingerprint = _certificate_sha256(certificate)
                crl_der = retained_crls.get(certificate_fingerprint)
                if crl_der is None:
                    crl_der = _fetch_crl_bytes(distribution_point)
                evidence.append(
                    _validate_crl(certificate, issuer, crl_der, gen_time, distribution_point)
                )

            anchor = path[-1]
            anchor_pem = _certificate_pem(anchor)
            intermediate_pems = tuple(_certificate_pem(certificate) for certificate in path[1:-1])
            intermediates_path = root / "intermediates.pem"
            intermediates_path.write_bytes(b"".join(intermediate_pems))
            empty_ca_path = root / "empty-ca-path"
            empty_ca_path.mkdir()
            crl_bundle_path = root / "crls.pem"
            crl_bundle_path.write_bytes(
                b"".join(
                    x509.load_der_x509_crl(item.crl_der).public_bytes(Encoding.PEM)
                    for item in evidence
                )
            )
            ca_path = root / "ca-bundle.pem"
            ca_path.write_bytes(ca_bundle)
            ca_store_uri = _openssl_store_uri(ca_path)
            signer_copy_path = root / "signer.pem"
            signer_copy_path.write_bytes(_certificate_pem(signer))

            constrained_ts_args = [
                "ts", "-verify", "-queryfile", str(root / "request.tsq"),
            ]
            (root / "request.tsq").write_bytes(request)
            constrained_ts_args.extend(["-in", str(response_path)])
            constrained_ts_args.extend(
                [
                    "-CAfile", str(ca_path), "-CApath", str(empty_ca_path),
                    "-CAstore", ca_store_uri,
                    "-partial_chain", "-attime", str(int(gen_time.timestamp())),
                ]
            )
            if intermediate_pems:
                constrained_ts_args.extend(["-untrusted", str(intermediates_path)])
            _run_openssl(self.openssl_binary, constrained_ts_args, timeout=self.timeout_seconds)

            verify_args = [
                "verify", "-attime", str(int(gen_time.timestamp())),
                "-purpose", "timestampsign", "-CAfile", str(ca_path),
                "-no-CApath", "-CAstore", ca_store_uri, "-partial_chain",
                "-CRLfile", str(crl_bundle_path), "-crl_check",
            ]
            if intermediate_pems:
                verify_args.extend(["-untrusted", str(intermediates_path)])
            verify_args.append(str(signer_copy_path))
            _run_openssl(self.openssl_binary, verify_args, timeout=self.timeout_seconds)

        return TimestampRevocationVerification(
            timestamp=timestamp,
            signer_certificate_pem=_certificate_pem(signer),
            intermediate_certificates_pem=intermediate_pems,
            trust_anchor_pem=anchor_pem,
            evidence=tuple(evidence),
        )

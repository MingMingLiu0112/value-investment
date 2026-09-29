from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import socket
import json
from pathlib import Path
import subprocess
import sys

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from value_investment_agent.application.product import prospective_timestamp as app
from value_investment_agent.infrastructure import rfc3161_tsa as infra
from value_investment_agent.infrastructure.rfc3161_tsa import (
    TimestampRevocationEvidence,
    TimestampRevocationVerification,
)


POLICY = "2.16.840.1.114412.7.1"
_PAYLOAD_IMPRINT = hashlib.sha256(b"payload").hexdigest()
QUERY_TEXT = (
    "Version: 1\nHash Algorithm: sha256\nMessage data:\n"
    + "    0000 - "
    + " ".join(_PAYLOAD_IMPRINT[index : index + 2] for index in range(0, 64, 2))
    + "\nPolicy OID: unspecified\nNonce: 0x1234\nCertificate required: yes\n"
)
REPLY_TEXT = (
    "Status: Granted.\nVersion: 1\nPolicy OID: "
    + POLICY
    + "\nHash Algorithm: sha256\nTime stamp: Sep 28 10:25:16 2026 GMT\nNonce: 0x1234\n"
)
TEST_GEN_TIME = datetime(2026, 9, 28, 10, 25, 16, tzinfo=timezone.utc)


class _Response:
    content = b"der-reply"
    headers = {"Content-Type": "application/timestamp-reply"}

    @staticmethod
    def raise_for_status() -> None:
        return None


def _fake_verification(payload: bytes, request: bytes, response: bytes) -> infra.TimestampVerification:
    return infra.TimestampVerification(
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        request_sha256=hashlib.sha256(request).hexdigest(),
        response_sha256=hashlib.sha256(response).hexdigest(),
        ca_bundle_sha256="a" * 64,
        nonce="4660",
        gen_time_utc="2026-09-28T10:25:16Z",
        policy_oid=POLICY,
        accuracy=None,
        openssl_version="OpenSSL 3.2.4 test",
    )


def _fake_revocation_verification(payload: bytes, request: bytes, response: bytes):
    return TimestampRevocationVerification(
        timestamp=_fake_verification(payload, request, response),
        signer_certificate_pem=b"-----BEGIN CERTIFICATE-----\nsigner\n-----END CERTIFICATE-----\n",
        intermediate_certificates_pem=(b"-----BEGIN CERTIFICATE-----\nintermediate\n-----END CERTIFICATE-----\n",),
        trust_anchor_pem=b"-----BEGIN CERTIFICATE-----\nroot\n-----END CERTIFICATE-----\n",
        evidence=(
            TimestampRevocationEvidence(
                certificate_sha256="c" * 64,
                issuer_sha256="d" * 64,
                distribution_point="http://crl.example.invalid/signer.crl",
                crl_der=b"crl-der",
                crl_sha256=hashlib.sha256(b"crl-der").hexdigest(),
                this_update_utc="2026-09-28T00:00:00Z",
                next_update_utc="2026-10-05T00:00:00Z",
            ),
        ),
    )


def _make_certificate(subject_name, key, issuer, issuer_key, *, is_ca, distribution_uri=None, serial=1):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(issuer or name)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(datetime(2026, 1, 1))
        .not_valid_after(datetime(2030, 1, 1))
        .add_extension(x509.BasicConstraints(ca=is_ca, path_length=2 if is_ca else None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=not is_ca,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=is_ca,
                crl_sign=is_ca,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
    )
    if not is_ca:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]),
            critical=True,
        )
    if distribution_uri is not None:
        builder = builder.add_extension(
            x509.CRLDistributionPoints(
                [
                    x509.DistributionPoint(
                        full_name=[x509.UniformResourceIdentifier(distribution_uri)],
                        relative_name=None,
                        reasons=None,
                        crl_issuer=None,
                    )
                ]
            ),
            critical=False,
        )
    return builder.sign(issuer_key or key, hashes.SHA256())


def _test_certificate_chain(*, partial_reasons=None):
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root = _make_certificate("Test Root", root_key, None, None, is_ca=True, serial=1)
    intermediate_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    intermediate = _make_certificate(
        "Test Intermediate",
        intermediate_key,
        root.subject,
        root_key,
        is_ca=True,
        distribution_uri="http://crl.example.invalid/root.crl",
        serial=2,
    )
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer = _make_certificate(
        "Test TSA",
        signer_key,
        intermediate.subject,
        intermediate_key,
        is_ca=False,
        distribution_uri="http://crl.example.invalid/intermediate.crl",
        serial=3,
    )
    if partial_reasons is not None:
        signer = (
            x509.CertificateBuilder()
            .subject_name(signer.subject)
            .issuer_name(signer.issuer)
            .public_key(signer.public_key())
            .serial_number(signer.serial_number)
            .not_valid_before(datetime(2026, 1, 1))
            .not_valid_after(datetime(2030, 1, 1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
            .add_extension(
                x509.CRLDistributionPoints(
                    [
                        x509.DistributionPoint(
                            full_name=[x509.UniformResourceIdentifier("http://crl.example.invalid/intermediate.crl")],
                            relative_name=None,
                            reasons=partial_reasons,
                            crl_issuer=None,
                        )
                    ]
                ),
                critical=False,
            )
            .sign(intermediate_key, hashes.SHA256())
        )
    return root, root_key, intermediate, intermediate_key, signer, signer_key


def _make_crl(issuer, issuer_key, *, revoked_serial=None, revocation_date=None, last_update=None, next_update=None,
              invalidity_date=None, revoked_extension=None, issuer_name=None, signing_key=None, extra_extension=None,
              omit_next_update=False):
    builder = x509.CertificateRevocationListBuilder().issuer_name(issuer_name or issuer.subject)
    last_update = last_update or (TEST_GEN_TIME - timedelta(days=1))
    next_update = next_update or (TEST_GEN_TIME + timedelta(days=7))
    builder = builder.last_update(last_update.replace(tzinfo=None))
    if not omit_next_update:
        builder = builder.next_update(next_update.replace(tzinfo=None))
    builder = builder.add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
        critical=False,
    )
    if revoked_serial is not None:
        revoked = (
            x509.RevokedCertificateBuilder()
            .serial_number(revoked_serial)
            .revocation_date((revocation_date or (TEST_GEN_TIME - timedelta(days=1))).replace(tzinfo=None))
        )
        if invalidity_date is not None:
            revoked = revoked.add_extension(
                x509.InvalidityDate(invalidity_date.replace(tzinfo=None)),
                critical=False,
            )
        if revoked_extension is not None:
            revoked = revoked.add_extension(revoked_extension, critical=True)
        builder = builder.add_revoked_certificate(revoked.build())
    if extra_extension is not None:
        builder = builder.add_extension(extra_extension, critical=True)
    return builder.sign(signing_key or issuer_key, hashes.SHA256()).public_bytes(Encoding.DER)


def test_openssl_query_uses_sha256_and_requests_signer_certificate(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        Path(command[command.index("-out") + 1]).write_bytes(b"query-der")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(infra.subprocess, "run", run)
    (tmp_path / "ca.pem").write_text("test ca", encoding="ascii")
    tsa = infra.OpenSslRfc3161Tsa(
        ca_bundle_path=tmp_path / "ca.pem",
        expected_policy_oid=POLICY,
        openssl_binary=sys.executable,
    )

    assert tsa.create_request(b"public bytes") == b"query-der"
    assert "-sha256" in calls[0]
    assert "-cert" in calls[0]


def test_verifier_binds_payload_query_nonce_policy_and_ca(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1:4] == ["ts", "-query", "-in"]:
            stdout = QUERY_TEXT
        elif command[1:4] == ["ts", "-reply", "-in"]:
            stdout = REPLY_TEXT
        elif command[1:3] == ["ts", "-verify"]:
            stdout = "Verification: OK\n"
        else:
            stdout = "OpenSSL 3.2.4 test"
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(infra.subprocess, "run", run)
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("test ca", encoding="ascii")
    tsa = infra.OpenSslRfc3161Tsa(
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
        openssl_binary=sys.executable,
    )

    result = tsa.verify_response(b"payload", b"query-der", b"reply-der")

    verify_command = next(command for command in calls if command[1:3] == ["ts", "-verify"])
    assert "-queryfile" in verify_command
    assert "-CAfile" in verify_command
    assert "-attime" in verify_command
    assert result.payload_sha256 == hashlib.sha256(b"payload").hexdigest()
    assert result.nonce == "4660"
    assert result.policy_oid == POLICY
    assert result.gen_time_utc == "2026-09-28T10:25:16Z"


@pytest.mark.parametrize(
    ("reply", "policy", "error"),
    [
        (REPLY_TEXT.replace("0x1234", "0x1235"), POLICY, "nonce"),
        (REPLY_TEXT, "1.2.3", "policy OID"),
    ],
)
def test_verifier_rejects_mismatched_nonce_or_policy(tmp_path, monkeypatch, reply, policy, error):
    def run(command, **kwargs):
        stdout = QUERY_TEXT if command[1:3] == ["ts", "-query"] else reply
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(infra.subprocess, "run", run)
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("test ca", encoding="ascii")
    tsa = infra.OpenSslRfc3161Tsa(
        ca_bundle_path=ca_bundle,
        expected_policy_oid=policy,
        openssl_binary=sys.executable,
    )
    with pytest.raises(infra.TimestampVerificationError, match=error):
        tsa.verify_response(b"payload", b"query", b"reply")


def test_verifier_fails_closed_when_openssl_signature_or_chain_check_fails(tmp_path, monkeypatch):
    def run(command, **kwargs):
        if command[1:3] == ["ts", "-verify"]:
            return subprocess.CompletedProcess(command, 1, "", "certificate verify error")
        stdout = QUERY_TEXT if command[1:3] == ["ts", "-query"] else REPLY_TEXT
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(infra.subprocess, "run", run)
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("test ca", encoding="ascii")
    tsa = infra.OpenSslRfc3161Tsa(
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
        openssl_binary=sys.executable,
    )
    with pytest.raises(infra.TimestampVerificationError, match="certificate verify error"):
        tsa.verify_response(b"payload", b"query", b"reply")


def test_verifier_rejects_request_imprint_that_does_not_match_payload(tmp_path, monkeypatch):
    def run(command, **kwargs):
        stdout = QUERY_TEXT if command[1:3] == ["ts", "-query"] else REPLY_TEXT
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(infra.subprocess, "run", run)
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("test ca", encoding="ascii")
    tsa = infra.OpenSslRfc3161Tsa(
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
        openssl_binary=sys.executable,
    )
    with pytest.raises(infra.TimestampVerificationError, match="imprint does not match"):
        tsa.verify_response(b"different payload", b"query", b"reply")


def test_timestamp_chain_is_atomic_forward_only_and_reverifiable(tmp_path, monkeypatch):
    root = tmp_path / "project"
    payload = root / "runtime" / "baseline.json"
    payload.parent.mkdir(parents=True)
    payload.write_text('{"scope":"public"}', encoding="utf-8")
    ca_bundle = root / "ca.pem"
    ca_bundle.write_text("test ca", encoding="ascii")
    destination = root / "runtime" / "prospective-timestamp-chains" / "case-a"

    class FakeTsa:
        def __init__(self, **kwargs):
            self.ca_bundle_path = kwargs["ca_bundle_path"]
            self.endpoint_url = kwargs["endpoint_url"]

        def create_request(self, value):
            return b"request:" + hashlib.sha256(value).digest()

        def submit_request(self, request):
            return b"signed response"

        def verify_response_with_revocation(self, value, request, response, **kwargs):
            return _fake_revocation_verification(value, request, response)

    monkeypatch.setattr(app, "OpenSslRfc3161Tsa", FakeTsa)
    result = app.create_prospective_timestamp_chain(
        root=root,
        payload_path=payload,
        output_dir=destination,
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
        public_research_only=True,
    )

    assert result["strict_pit_admissible"] is False
    assert result["historical_retrospective_effect"] == "NONE"
    assert (destination / "response.tsr").read_bytes() == b"signed response"
    assert app.verify_prospective_timestamp_chain(
        chain_dir=destination,
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
    ) == result


def test_failed_or_non_public_timestamp_does_not_publish_receipt(tmp_path, monkeypatch):
    root = tmp_path / "project"
    payload = root / "runtime" / "baseline.json"
    payload.parent.mkdir(parents=True)
    payload.write_text("public", encoding="ascii")
    ca_bundle = root / "ca.pem"
    ca_bundle.write_text("test ca", encoding="ascii")
    destination = root / "runtime" / "prospective-timestamp-chains" / "failed"

    class FakeTsa:
        def __init__(self, **kwargs):
            pass

        def create_request(self, value):
            return b"query"

        def submit_request(self, request):
            return b"response"

        def verify_response_with_revocation(self, *args, **kwargs):
            raise infra.TimestampVerificationError("bad signature")

    monkeypatch.setattr(app, "OpenSslRfc3161Tsa", FakeTsa)
    with pytest.raises(ValueError, match="public-research-only"):
        app.create_prospective_timestamp_chain(
            root=root,
            payload_path=payload,
            output_dir=destination,
            ca_bundle_path=ca_bundle,
        )
    with pytest.raises(infra.TimestampVerificationError, match="bad signature"):
        app.create_prospective_timestamp_chain(
            root=root,
            payload_path=payload,
            output_dir=destination,
            ca_bundle_path=ca_bundle,
            expected_policy_oid=POLICY,
            public_research_only=True,
        )
    assert not destination.exists()


def test_chain_verification_detects_payload_tampering(tmp_path, monkeypatch):
    root = tmp_path / "project"
    payload = root / "runtime" / "baseline.json"
    payload.parent.mkdir(parents=True)
    payload.write_text("public", encoding="ascii")
    ca_bundle = root / "ca.pem"
    ca_bundle.write_text("test ca", encoding="ascii")
    destination = root / "runtime" / "prospective-timestamp-chains" / "case-a"

    class FakeTsa:
        def __init__(self, **kwargs):
            self.ca_bundle_path = kwargs["ca_bundle_path"]
            self.endpoint_url = kwargs["endpoint_url"]

        def create_request(self, value):
            return b"query"

        def submit_request(self, request):
            return b"response"

        def verify_response_with_revocation(self, value, request, response, **kwargs):
            return _fake_revocation_verification(value, request, response)

    monkeypatch.setattr(app, "OpenSslRfc3161Tsa", FakeTsa)
    app.create_prospective_timestamp_chain(
        root=root,
        payload_path=payload,
        output_dir=destination,
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
        public_research_only=True,
    )
    (destination / "payload.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="file hash mismatch: payload_sha256"):
        app.verify_prospective_timestamp_chain(
            chain_dir=destination,
            ca_bundle_path=ca_bundle,
            expected_policy_oid=POLICY,
        )


def test_chain_verification_detects_crl_tampering(tmp_path, monkeypatch):
    root = tmp_path / "project"
    payload = root / "runtime" / "baseline.json"
    payload.parent.mkdir(parents=True)
    payload.write_text("public", encoding="ascii")
    ca_bundle = root / "ca.pem"
    ca_bundle.write_text("test ca", encoding="ascii")
    destination = root / "runtime" / "prospective-timestamp-chains" / "case-a"

    class FakeTsa:
        def __init__(self, **kwargs):
            self.ca_bundle_path = kwargs["ca_bundle_path"]
            self.endpoint_url = kwargs["endpoint_url"]

        def create_request(self, value):
            return b"query"

        def submit_request(self, request):
            return b"response"

        def verify_response_with_revocation(self, value, request, response, **kwargs):
            return _fake_revocation_verification(value, request, response)

    monkeypatch.setattr(app, "OpenSslRfc3161Tsa", FakeTsa)
    app.create_prospective_timestamp_chain(
        root=root,
        payload_path=payload,
        output_dir=destination,
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
        public_research_only=True,
    )
    (destination / "crls" / ("c" * 64 + ".der")).write_bytes(b"tampered")

    with pytest.raises(ValueError, match="CRL hash mismatch"):
        app.verify_prospective_timestamp_chain(
            chain_dir=destination,
            expected_policy_oid=POLICY,
        )


def test_v1_receipt_remains_legacy_and_not_pit_admitted(tmp_path, monkeypatch):
    chain_dir = tmp_path / "legacy-v1"
    chain_dir.mkdir()
    payload = b"legacy payload"
    request = b"legacy request"
    response = b"legacy response"
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_bytes(b"legacy CA bundle")
    for name, content in (("payload.bin", payload), ("request.tsq", request), ("response.tsr", response)):
        (chain_dir / name).write_bytes(content)
    base = _fake_verification(payload, request, response)
    verification = infra.TimestampVerification(
        **{**base.__dict__, "ca_bundle_sha256": hashlib.sha256(ca_bundle.read_bytes()).hexdigest()}
    )
    receipt = app._receipt_v1(
        verification=verification,
        endpoint_url="http://timestamp.example.invalid",
        payload_file="payload.bin",
        request_file="request.tsq",
        response_file="response.tsr",
    )
    app._write_receipt(chain_dir, receipt)

    class LegacyTsa:
        def __init__(self, **kwargs):
            pass

        @staticmethod
        def verify_response(*args):
            return verification

    monkeypatch.setattr(app, "OpenSslRfc3161Tsa", LegacyTsa)
    result = app.verify_prospective_timestamp_chain(
        chain_dir=chain_dir,
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
    )

    assert result == receipt
    assert result["schema_version"] == app.TIMESTAMP_CHAIN_SCHEMA_V1
    assert result["strict_pit_admissible"] is False
    assert "revocation_status" not in result


def test_crl_validation_checks_signature_scope_and_gen_time():
    root, root_key, intermediate, intermediate_key, signer, _ = _test_certificate_chain()
    distribution_point = infra._crl_distribution_point(signer)
    crl_der = _make_crl(intermediate, intermediate_key)

    result = infra._validate_crl(signer, intermediate, crl_der, TEST_GEN_TIME, distribution_point)

    assert result.certificate_sha256 == signer.fingerprint(hashes.SHA256()).hex()
    assert result.issuer_sha256 == intermediate.fingerprint(hashes.SHA256()).hex()
    assert result.crl_sha256 == hashlib.sha256(crl_der).hexdigest()


def test_crl_validation_accepts_revocation_effective_after_timestamp():
    _, _, intermediate, intermediate_key, signer, _ = _test_certificate_chain()
    crl_der = _make_crl(
        intermediate,
        intermediate_key,
        revoked_serial=signer.serial_number,
        revocation_date=TEST_GEN_TIME + timedelta(hours=1),
    )

    infra._validate_crl(
        signer,
        intermediate,
        crl_der,
        TEST_GEN_TIME,
        infra._crl_distribution_point(signer),
    )


def test_crl_validation_rejects_unsupported_critical_extension_on_matching_entry():
    _, _, intermediate, intermediate_key, signer, _ = _test_certificate_chain()
    crl_der = _make_crl(
        intermediate,
        intermediate_key,
        revoked_serial=signer.serial_number,
        revocation_date=TEST_GEN_TIME + timedelta(hours=1),
        revoked_extension=x509.UnrecognizedExtension(
            x509.ObjectIdentifier("1.3.6.1.4.1.55555.1"), b"\x05\x00"
        ),
    )

    with pytest.raises(infra.TimestampVerificationError, match="unsupported critical extension"):
        infra._validate_crl(
            signer,
            intermediate,
            crl_der,
            TEST_GEN_TIME,
            infra._crl_distribution_point(signer),
        )


def test_crl_validation_rejects_invalidity_date_before_timestamp():
    _, _, intermediate, intermediate_key, signer, _ = _test_certificate_chain()
    crl_der = _make_crl(
        intermediate,
        intermediate_key,
        revoked_serial=signer.serial_number,
        revocation_date=TEST_GEN_TIME + timedelta(hours=1),
        invalidity_date=TEST_GEN_TIME - timedelta(minutes=1),
    )

    with pytest.raises(infra.TimestampVerificationError, match="revoked at genTime"):
        infra._validate_crl(
            signer,
            intermediate,
            crl_der,
            TEST_GEN_TIME,
            infra._crl_distribution_point(signer),
        )


def test_crl_validation_rejects_revoked_stale_wrong_issuer_and_bad_signature():
    _, _, intermediate, intermediate_key, signer, _ = _test_certificate_chain()
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cases = [
        (
            _make_crl(
                intermediate,
                intermediate_key,
                revoked_serial=signer.serial_number,
                revocation_date=TEST_GEN_TIME - timedelta(seconds=1),
            ),
            "revoked at genTime",
        ),
        (
            _make_crl(
                intermediate,
                intermediate_key,
                next_update=TEST_GEN_TIME - timedelta(seconds=1),
            ),
            "validity interval",
        ),
        (
            _make_crl(
                intermediate,
                intermediate_key,
                issuer_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Wrong Issuer")]),
            ),
            "issuer does not match",
        ),
        (
            _make_crl(intermediate, intermediate_key, signing_key=other_key),
            "signature does not verify",
        ),
    ]
    for crl_der, message in cases:
        with pytest.raises(infra.TimestampVerificationError, match=message):
            infra._validate_crl(
                signer,
                intermediate,
                crl_der,
                TEST_GEN_TIME,
                infra._crl_distribution_point(signer),
            )


def test_crl_validation_rejects_delta_and_partial_scope():
    _, _, intermediate, intermediate_key, signer, _ = _test_certificate_chain()
    delta = _make_crl(
        intermediate,
        intermediate_key,
        extra_extension=x509.DeltaCRLIndicator(4),
    )
    with pytest.raises(infra.TimestampVerificationError, match="delta CRLs"):
        infra._validate_crl(
            signer,
            intermediate,
            delta,
            TEST_GEN_TIME,
            infra._crl_distribution_point(signer),
        )

    partial = x509.ReasonFlags.key_compromise
    _, _, _, _, partial_signer, _ = _test_certificate_chain(partial_reasons=frozenset({partial}))
    with pytest.raises(infra.TimestampVerificationError, match="partial or indirect"):
        infra._crl_distribution_point(partial_signer)

    restricted = x509.IssuingDistributionPoint(
        full_name=None,
        relative_name=None,
        only_contains_user_certs=False,
        only_contains_ca_certs=False,
        only_some_reasons=frozenset({x509.ReasonFlags.key_compromise}),
        indirect_crl=False,
        only_contains_attribute_certs=False,
    )
    _, _, intermediate, intermediate_key, signer, _ = _test_certificate_chain()
    restricted_crl = _make_crl(
        intermediate,
        intermediate_key,
        extra_extension=restricted,
    )
    with pytest.raises(infra.TimestampVerificationError, match="restricted or indirect"):
        infra._validate_crl(
            signer,
            intermediate,
            restricted_crl,
            TEST_GEN_TIME,
            infra._crl_distribution_point(signer),
        )


def test_trusted_path_is_bound_to_a_certificate_in_the_configured_bundle():
    root, _, intermediate, _, signer, _ = _test_certificate_chain()

    path = infra._build_trusted_certificate_path(
        signer,
        [signer, intermediate],
        root.public_bytes(Encoding.PEM),
    )

    assert [item.subject for item in path] == [signer.subject, intermediate.subject, root.subject]


def test_trusted_path_rejects_cross_sign_ambiguity():
    root_one_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_one = _make_certificate("Root One", root_one_key, None, None, is_ca=True, serial=11)
    root_two_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_two = _make_certificate("Root Two", root_two_key, None, None, is_ca=True, serial=12)
    intermediate_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    intermediate_one = _make_certificate(
        "Cross-Signed Intermediate", intermediate_key, root_one.subject, root_one_key, is_ca=True, serial=13
    )
    intermediate_two = _make_certificate(
        "Cross-Signed Intermediate", intermediate_key, root_two.subject, root_two_key, is_ca=True, serial=14
    )
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer = _make_certificate(
        "Cross-Signed TSA",
        signer_key,
        intermediate_one.subject,
        intermediate_key,
        is_ca=False,
        distribution_uri="http://crl.example.invalid/cross-signed.crl",
        serial=15,
    )
    trust_bundle = root_one.public_bytes(Encoding.PEM) + root_two.public_bytes(Encoding.PEM)

    with pytest.raises(infra.TimestampVerificationError, match="ambiguous path"):
        infra._build_trusted_certificate_path(
            signer,
            [signer, intermediate_one, intermediate_two],
            trust_bundle,
        )


def test_crl_fetch_rejects_private_dns_and_redirects_without_following_them():
    def private_resolver(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port))]

    with pytest.raises(infra.TimestampVerificationError, match="non-public address"):
        infra._fetch_crl_bytes(
            "http://crl.example.invalid/list.crl",
            address_resolver=private_resolver,
            connection_factory=lambda *args: pytest.fail("must not connect to private DNS results"),
        )

    observed = {}

    class RedirectResponse:
        status = 302

        @staticmethod
        def getheader(name):
            return None

    class RedirectConnection:
        def request(self, method, path, *, body=None, headers):
            observed.update(method=method, path=path, body=body, headers=headers)

        @staticmethod
        def getresponse():
            return RedirectResponse()

        @staticmethod
        def close():
            return None

    def public_resolver(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    with pytest.raises(infra.TimestampVerificationError, match="redirects are rejected"):
        infra._fetch_crl_bytes(
            "http://crl.example.invalid/list.crl",
            address_resolver=public_resolver,
            connection_factory=lambda *args: RedirectConnection(),
        )
    assert observed["method"] == "GET"
    assert observed["headers"]["Host"] == "crl.example.invalid"


def test_tsa_submission_uses_pinned_public_transport_and_rejects_redirects(tmp_path, monkeypatch):
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("test ca", encoding="ascii")
    tsa = infra.OpenSslRfc3161Tsa(
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
        openssl_binary=sys.executable,
    )
    captured = {}

    def request_public_bytes(method, uri, **kwargs):
        captured.update(method=method, uri=uri, **kwargs)
        return b"reply", "application/timestamp-reply; charset=binary"

    monkeypatch.setattr(infra, "_request_public_bytes", request_public_bytes)
    assert tsa.submit_request(b"query") == b"reply"
    assert captured["method"] == "POST"
    assert captured["body"] == b"query"
    assert captured["headers"]["Content-Type"] == "application/timestamp-query"
    assert captured["error_label"] == "TSA"


def test_tsa_public_transport_rejects_private_dns_and_redirects(monkeypatch):
    def private_resolver(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.5", port))]

    with pytest.raises(infra.TimestampVerificationError, match="non-public address"):
        infra._request_public_bytes(
            "POST",
            "http://tsa.example.invalid/",
            body=b"query",
            headers={"Content-Type": "application/timestamp-query"},
            max_bytes=infra.MAX_TIMESTAMP_RESPONSE_BYTES,
            error_label="TSA",
            address_resolver=private_resolver,
            connection_factory=lambda *args: pytest.fail("must not connect to private DNS results"),
        )

    class RedirectResponse:
        status = 302

        @staticmethod
        def getheader(name):
            return None

    class RedirectConnection:
        def request(self, method, path, *, body=None, headers):
            captured.update(method=method, path=path, body=body, headers=headers)

        @staticmethod
        def getresponse():
            return RedirectResponse()

        @staticmethod
        def close():
            return None

    captured = {}
    direct_targets = []

    def public_resolver(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    def direct_connection(hostname, address, port, timeout):
        direct_targets.append((hostname, address, port, timeout))
        return RedirectConnection()

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9")
    monkeypatch.setattr(infra, "_PinnedHTTPSConnection", direct_connection)

    with pytest.raises(infra.TimestampVerificationError, match="redirects are rejected"):
        infra._request_public_bytes(
            "POST",
            "https://tsa.example.invalid/timestamp?profile=default",
            body=b"query",
            headers={"Content-Type": "application/timestamp-query"},
            max_bytes=infra.MAX_TIMESTAMP_RESPONSE_BYTES,
            error_label="TSA",
            address_resolver=public_resolver,
        )
    assert captured["method"] == "POST"
    assert captured["path"] == "/timestamp?profile=default"
    assert captured["headers"]["Host"] == "tsa.example.invalid"
    assert direct_targets == [("tsa.example.invalid", "8.8.8.8", 443, 15)]


def test_openssl_v2_verifies_timestamp_and_each_retained_crl_on_the_bound_path(tmp_path):
    root, root_key, intermediate, intermediate_key, signer, signer_key = _test_certificate_chain()
    ca_bundle = tmp_path / "ca-bundle.pem"
    ca_bundle.write_bytes(root.public_bytes(Encoding.PEM))
    signer_path = tmp_path / "signer.pem"
    signer_path.write_bytes(signer.public_bytes(Encoding.PEM))
    key_path = tmp_path / "signer-key.pem"
    key_path.write_bytes(
        signer_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    chain_path = tmp_path / "intermediate.pem"
    chain_path.write_bytes(intermediate.public_bytes(Encoding.PEM))
    serial_path = tmp_path / "serial.txt"
    serial_path.write_text("01\n", encoding="ascii")
    config_path = tmp_path / "tsa.cnf"
    config_path.write_text(
        "\n".join(
            [
                "[ tsa ]",
                "default_tsa = tsa_config1",
                "[ tsa_config1 ]",
                f"serial = {serial_path.as_posix()}",
                f"signer_cert = {signer_path.as_posix()}",
                f"signer_key = {key_path.as_posix()}",
                f"certs = {chain_path.as_posix()}",
                "signer_digest = sha256",
                f"default_policy = {POLICY}",
                "digests = sha256",
                "accuracy = secs:1",
                "clock_precision_digits = 0",
                "ordering = yes",
                "tsa_name = yes",
                "ess_cert_id_chain = no",
                "",
            ]
        ),
        encoding="ascii",
    )
    openssl = infra.resolve_openssl()
    tsa = infra.OpenSslRfc3161Tsa(
        ca_bundle_path=ca_bundle,
        expected_policy_oid=POLICY,
        openssl_binary=openssl,
    )
    payload = b"public research test only"
    request = tsa.create_request(payload)
    query_path = tmp_path / "query.tsq"
    query_path.write_bytes(request)
    response_path = tmp_path / "response.tsr"
    completed = subprocess.run(
        [
            str(openssl), "ts", "-reply", "-config", str(config_path),
            "-queryfile", str(query_path), "-out", str(response_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    gen_time = datetime.now(timezone.utc)
    broad_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    broad_end = datetime(2035, 1, 1, tzinfo=timezone.utc)
    signer_crl = _make_crl(
        intermediate,
        intermediate_key,
        last_update=broad_start,
        next_update=broad_end,
    )
    intermediate_crl = _make_crl(
        root,
        root_key,
        last_update=broad_start,
        next_update=broad_end,
    )
    crls = {
        infra._certificate_sha256(signer): signer_crl,
        infra._certificate_sha256(intermediate): intermediate_crl,
    }

    result = tsa.verify_response_with_revocation(payload, request, response_path.read_bytes(),
                                                  crl_evidence_by_certificate_sha256=crls)

    assert result.timestamp.policy_oid == POLICY
    assert infra._certificate_sha256(signer) == result.evidence[0].certificate_sha256
    assert infra._certificate_sha256(intermediate) == result.evidence[1].certificate_sha256
    assert len(result.evidence) == 2
    assert gen_time.year >= 2026


def test_timestamp_cli_is_registered_thin_and_exposes_create_and_verify():
    path = Path(__file__).resolve().parents[1] / "scripts/current/stamp_prospective_checkpoint.py"
    text = path.read_text(encoding="utf-8")
    assert "create_prospective_timestamp_chain" in text
    assert "verify_prospective_timestamp_chain" in text
    assert "--public-research-only" in text
    assert len(text.splitlines()) <= 90

    completed = subprocess.run(
        [sys.executable, str(path), "--help"],
        cwd=path.parents[2],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "create" in completed.stdout
    assert "verify" in completed.stdout

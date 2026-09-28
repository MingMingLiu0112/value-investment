from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from value_investment_agent.application.product import prospective_timestamp as app
from value_investment_agent.infrastructure import rfc3161_tsa as infra


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

        def verify_response(self, value, request, response):
            result = _fake_verification(value, request, response)
            return infra.TimestampVerification(
                **{**result.__dict__, "ca_bundle_sha256": hashlib.sha256(ca_bundle.read_bytes()).hexdigest()}
            )

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

        def verify_response(self, *args):
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

        def verify_response(self, value, request, response):
            result = _fake_verification(value, request, response)
            return infra.TimestampVerification(
                **{**result.__dict__, "ca_bundle_sha256": hashlib.sha256(ca_bundle.read_bytes()).hexdigest()}
            )

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

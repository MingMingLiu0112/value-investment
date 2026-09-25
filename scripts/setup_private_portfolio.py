"""Single, privacy-preserving entry point for the M4 private input package."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets

from value_investment_agent.portfolio_contracts import portfolio_input_bundle_from_payload
from value_investment_agent.portfolio_reconciliation import reconcile_portfolio_snapshots
from value_investment_agent.private_portfolio_intake import (
    encrypt_private_portfolio_payload,
    load_private_portfolio_bundle,
    require_private_data_path,
    require_private_key_path,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "m4-private-portfolio-input-template.json"


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("portfolio input must be a JSON object")
    return value


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _blockers(payload: dict) -> tuple[str, ...]:
    def collect(value: object) -> set[str]:
        if isinstance(value, dict):
            return set().union(*(collect(item) for item in value.values())) if value else set()
        if isinstance(value, list):
            return set().union(*(collect(item) for item in value)) if value else set()
        return {value} if isinstance(value, str) and value.startswith("FILL_") else set()

    placeholders = tuple(sorted(collect(payload)))
    try:
        bundle = portfolio_input_bundle_from_payload(payload)
    except (KeyError, TypeError, ValueError) as error:
        return (*placeholders, f"contract:{error}")
    return (*placeholders, *bundle.missing_guidance_inputs())


def _common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--forbidden-sync-root", action="append", default=[], type=Path)


def _private_path(args: argparse.Namespace, path: Path, *, must_exist: bool = False) -> Path:
    return require_private_data_path(
        path, private_root=args.private_root, repository_root=ROOT,
        forbidden_sync_roots=getattr(args, "forbidden_sync_root", ()),
        must_exist=must_exist,
    )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and validate a private M4 portfolio input.")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="Create a private draft from the public template.")
    initialize.add_argument("--output", required=True, type=Path)
    initialize.add_argument("--private-root", required=True, type=Path)
    initialize.add_argument("--forbidden-sync-root", action="append", default=[], type=Path)
    validate = commands.add_parser("validate", help="Validate a plaintext draft without printing values.")
    validate.add_argument("--input", required=True, type=Path)
    validate.add_argument("--private-root", required=True, type=Path)
    validate.add_argument("--forbidden-sync-root", action="append", default=[], type=Path)
    keygen = commands.add_parser("keygen", help="Create a new AES-256 key outside private and sync roots.")
    keygen.add_argument("--key-file", required=True, type=Path)
    keygen.add_argument("--private-root", required=True, type=Path)
    keygen.add_argument("--forbidden-sync-root", action="append", default=[], type=Path)
    encrypt = commands.add_parser("encrypt", help="Validate and encrypt an ACTUAL input.")
    encrypt.add_argument("--input", required=True, type=Path)
    encrypt.add_argument("--encrypted", required=True, type=Path)
    _common_paths(encrypt)
    verify = commands.add_parser("verify", help="Decrypt in memory and emit only a redacted receipt.")
    verify.add_argument("--encrypted", required=True, type=Path)
    _common_paths(verify)
    reconcile = commands.add_parser("reconcile", help="Privately compare two encrypted ACTUAL snapshots.")
    reconcile.add_argument("--reported", required=True, type=Path)
    reconcile.add_argument("--confirmed", required=True, type=Path)
    reconcile.add_argument("--private-report", required=True, type=Path)
    reconcile.add_argument("--report-id", required=True)
    _common_paths(reconcile)
    confirm = commands.add_parser("confirm-reconciliation", help="Create a new encrypted RECONCILED bundle after explicit human confirmation.")
    confirm.add_argument("--source", required=True, type=Path)
    confirm.add_argument("--private-report", required=True, type=Path)
    confirm.add_argument("--encrypted", required=True, type=Path)
    confirm.add_argument("--confirmation-id", required=True)
    confirm.add_argument("--confirmed-at", required=True)
    _common_paths(confirm)
    return parser.parse_args()


def main() -> int:
    args = _args()
    if args.command == "init":
        output = _private_path(args, args.output)
        _write_new(output, TEMPLATE.read_text(encoding="utf-8"))
        result = {"status": "DRAFT_CREATED", "action": "no_order"}
    elif args.command == "validate":
        source = _private_path(args, args.input, must_exist=True)
        blockers = _blockers(_json(source))
        result = {"status": "READY_TO_ENCRYPT" if not blockers else "NEEDS_INPUT", "blockers": list(blockers), "action": "no_order"}
    elif args.command == "keygen":
        key_file = require_private_key_path(
            args.key_file, private_root=args.private_root, repository_root=ROOT,
            forbidden_sync_roots=args.forbidden_sync_root,
        )
        _write_new(key_file, secrets.token_hex(32) + "\n")
        result = {"status": "KEY_CREATED", "action": "no_order"}
    elif args.command == "encrypt":
        source = _private_path(args, args.input, must_exist=True)
        receipt = encrypt_private_portfolio_payload(
            _json(source), args.encrypted, args.key_file,
            private_root=args.private_root, repository_root=ROOT,
            forbidden_sync_roots=args.forbidden_sync_root,
        )
        result = receipt.as_policy()
    elif args.command == "verify":
        bundle, receipt = load_private_portfolio_bundle(
            args.encrypted, args.key_file, private_root=args.private_root,
            repository_root=ROOT, forbidden_sync_roots=args.forbidden_sync_root,
        )
        result = {**receipt.as_policy(), "blockers": list(bundle.missing_guidance_inputs())}
    elif args.command == "reconcile":
        reported, _ = load_private_portfolio_bundle(
            args.reported, args.key_file, private_root=args.private_root,
            repository_root=ROOT, forbidden_sync_roots=args.forbidden_sync_root,
        )
        confirmed, _ = load_private_portfolio_bundle(
            args.confirmed, args.key_file, private_root=args.private_root,
            repository_root=ROOT, forbidden_sync_roots=args.forbidden_sync_root,
        )
        private_report = _private_path(args, args.private_report)
        report = reconcile_portfolio_snapshots(
            reported.snapshot, confirmed.snapshot, report_id=args.report_id,
            generated_at=datetime.now(timezone.utc),
        )
        report_payload = {
            "report": report.as_private_policy(),
            "bindings": {
                "reported_encrypted_sha256": hashlib.sha256(args.reported.read_bytes()).hexdigest(),
                "confirmed_encrypted_sha256": hashlib.sha256(args.confirmed.read_bytes()).hexdigest(),
            },
        }
        _write_new(private_report, json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n")
        result = {"status": report.status, "difference_count": len(report.differences), "requires_human_confirmation": True, "action": "no_order"}
    else:
        source_path = _private_path(args, args.source, must_exist=True)
        report_path = _private_path(args, args.private_report, must_exist=True)
        report_payload = _json(report_path)
        report = report_payload.get("report", {})
        bindings = report_payload.get("bindings", {})
        source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if report.get("status") != "MATCH_PENDING_HUMAN_CONFIRMATION":
            raise ValueError("only a matching reconciliation report can be confirmed")
        if source_sha not in {
            bindings.get("reported_encrypted_sha256"),
            bindings.get("confirmed_encrypted_sha256"),
        }:
            raise ValueError("reconciliation report does not bind the source ciphertext")
        confirmed_at = datetime.fromisoformat(args.confirmed_at)
        if confirmed_at.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        bundle, _ = load_private_portfolio_bundle(
            source_path, args.key_file, private_root=args.private_root,
            repository_root=ROOT, forbidden_sync_roots=args.forbidden_sync_root,
        )
        snapshot = replace(
            bundle.snapshot,
            reconciliation_status="RECONCILED",
            reconciled_at=confirmed_at,
            evidence_refs=(*bundle.snapshot.evidence_refs, {"id": args.confirmation_id, "report_id": report.get("report_id")}),
        )
        receipt = encrypt_private_portfolio_payload(
            replace(bundle, snapshot=snapshot).as_policy(), args.encrypted, args.key_file,
            private_root=args.private_root, repository_root=ROOT,
            forbidden_sync_roots=args.forbidden_sync_root,
            created_at=confirmed_at,
        )
        result = {**receipt.as_policy(), "confirmation_id": args.confirmation_id}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Back up, verify and restore the private portfolio journal (WEB-D2 P0.3).

Thin wrapper: parse arguments, resolve the guarded private journal path, call
``value_investment_agent.application.portfolio.private_backup`` and print JSON.
Exit codes: 0 healthy, 1 invalid or missing backup, 2 refused restore, 3 the
private root is unavailable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.portfolio.private_backup import (  # noqa: E402
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)
from value_investment_agent.application.portfolio.private_portfolio_service import (  # noqa: E402
    PrivateStoreUnavailable,
    resolve_private_root,
)

BACKUP_ROOT_NAME = "backups"
NORMAL_BACKUP_PREFIX = "backup-"


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="把当前私人流水备份为一个新的备份包")
    commands.add_parser("list", help="按时间从新到旧列出备份包")
    verify = commands.add_parser("verify", help="校验备份包摘要与哈希链")
    selector = verify.add_mutually_exclusive_group(required=True)
    selector.add_argument("--backup-id", help="备份包目录名")
    selector.add_argument("--latest", action="store_true", help="校验最新的普通备份包")
    restore = commands.add_parser("restore", help="用备份包覆盖当前私人流水")
    restore.add_argument("--backup-id", required=True, help="备份包目录名")
    restore.add_argument("--confirm", action="store_true", help="明确确认覆盖当前流水")
    return parser.parse_args(argv)


def _resolve_backup_dir(backup_root: Path, backup_id: str) -> Path:
    if not backup_id or Path(backup_id).name != backup_id:
        raise ValueError(f"备份标识不合法：{backup_id!r}")
    return backup_root / backup_id


def _latest_backup_dir(backup_root: Path) -> Path | None:
    for entry in list_backups(backup_root):
        if str(entry["backup_id"]).startswith(NORMAL_BACKUP_PREFIX):
            return Path(str(entry["path"]))
    return None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass
    args = _parse_args(argv)
    try:
        journal_path = resolve_private_root(repository_root=ROOT)
    except PrivateStoreUnavailable as error:
        _emit({"status": "UNAVAILABLE", "reason": str(error), "action": "no_order"})
        return 3
    backup_root = journal_path.parent / BACKUP_ROOT_NAME
    try:
        if args.command == "create":
            result = create_backup(journal_path)
            _emit(result)
            return 0 if result["source_status"] == "VALID" else 1
        if args.command == "list":
            _emit(
                {
                    "status": "LISTED",
                    "backup_root": str(backup_root),
                    "backups": list_backups(backup_root),
                    "action": "no_order",
                }
            )
            return 0
        if args.command == "verify":
            if args.latest:
                backup_dir = _latest_backup_dir(backup_root)
                if backup_dir is None:
                    _emit(
                        {
                            "status": "MISSING",
                            "reason": "备份目录中没有可校验的备份包",
                            "action": "no_order",
                        }
                    )
                    return 1
            else:
                backup_dir = _resolve_backup_dir(backup_root, args.backup_id)
            result = verify_backup(backup_dir)
            _emit(result)
            return 0 if result["status"] == "VERIFIED" else 1
        result = restore_backup(
            _resolve_backup_dir(backup_root, args.backup_id),
            journal_path,
            confirm=args.confirm,
        )
        _emit(result)
        return 0
    except PrivateStoreUnavailable as error:
        _emit({"status": "UNAVAILABLE", "reason": str(error), "action": "no_order"})
        return 3
    except FileNotFoundError as error:
        _emit({"status": "MISSING", "reason": str(error), "action": "no_order"})
        return 1
    except ValueError as error:
        if args.command == "restore":
            _emit({"status": "REFUSED", "reason": str(error), "action": "no_order"})
            return 2
        _emit({"status": "INVALID", "reason": str(error), "action": "no_order"})
        return 1
    except (OSError, RuntimeError) as error:
        _emit({"status": "FAILED", "reason": str(error), "action": "no_order"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Thin CLI wrapper — all logic lives in the library modules."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from devin_backup import __version__, restore, rotate, snapshot, verify
from devin_backup.stores import (
    DataDirError,
    default_backups_dir,
    default_config_dir,
    default_data_dir,
)


def _resolve_dirs(args) -> tuple[Path, Path]:
    data_dir = (
        Path(args.data_dir).expanduser()
        if getattr(args, "data_dir", None)
        else default_data_dir()
    )
    out = (
        Path(args.out).expanduser()
        if getattr(args, "out", None)
        else default_backups_dir(data_dir)
    )
    return data_dir, out


def _cmd_create(args) -> int:
    data_dir, out = _resolve_dirs(args)
    config_dir = args.config_dir
    if config_dir is None and args.data_dir is None:
        config_dir = default_config_dir()
    snap = snapshot.create_snapshot(data_dir, out, config_dir=config_dir)
    manifest = snapshot.load_manifest(snap)
    total = sum(f.get("size", 0) for f in manifest["files"])
    print(f"created snapshot: {snap}")
    print(f"  {len(manifest['files'])} file(s), {total} bytes")
    for rel, version in manifest["schema_versions"].items():
        print(f"  {rel}: schema v{version}")
    for entry in manifest["files"]:
        if entry["copied_via"] != "sqlite-backup" and entry["kind"] == "sqlite":
            print(f"  note: {entry['path']} fell back to file-copy")
    return 0


def _cmd_verify(args) -> int:
    report = verify.verify_snapshot(args.snapshot_dir)
    for r in report["results"]:
        mark = "ok  " if r["ok"] else "FAIL"
        line = f"  {mark} {r['path']}"
        if not r["ok"]:
            line += f"  ({r['status']})"
        print(line)
    state = "ok" if report["ok"] else "FAILED"
    print(f"{state}: {report['checked']} checked, {report['failed']} failed")
    return 0 if report["ok"] else 1


def _cmd_list(args) -> int:
    _, out = _resolve_dirs(args)
    snaps = rotate.list_snapshots(out)
    if not snaps:
        print(f"no snapshots in {out}")
        return 0
    for s in snaps:
        schemas = ", ".join(
            f"{Path(k).name} v{v}" for k, v in s["schema_versions"].items()
        ) or "-"
        print(
            f"{s['name']:<24} {s['kind']:<12} {s['files']:>3} files  "
            f"{s['size']:>10} B  {schemas}"
        )
    return 0


def _cmd_restore(args) -> int:
    plan = restore.restore_snapshot(
        args.snapshot_dir,
        args.to,
        config_dir=args.config_to or default_config_dir(),
        dry_run=args.dry_run,
        backup=not args.no_backup,
    )
    for w in plan["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    if plan["dry_run"]:
        print("dry-run - no files written (pass --apply to restore)")
        for rel in plan["would_write"]:
            print(f"  would write {rel}")
        for rel in plan["would_overwrite"]:
            print(f"  would overwrite {rel}")
        if plan["would_backup"]:
            print("  current files would first be saved to a pre-restore backup")
    else:
        if plan["pre_restore_backup"]:
            print(f"pre-restore backup: {plan['pre_restore_backup']}")
        print(f"restored {len(plan['written'])} file(s) to {plan['target']}")
    return 0


def _cmd_rotate(args) -> int:
    _, out = _resolve_dirs(args)
    if not args.yes:
        print(
            "error: rotate permanently deletes snapshots - re-run with --yes",
            file=sys.stderr,
        )
        return 2
    deleted = rotate.rotate_snapshots(out, keep=args.keep)
    if not deleted:
        print(f"nothing to delete (keep={args.keep})")
    for d in deleted:
        print(f"deleted {d.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devin-backup",
        description="Safe backup & restore for Devin Desktop stores.",
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_dirs(p, data_dir=True):
        if data_dir:
            p.add_argument(
                "--data-dir",
                help="Devin data dir (default: $DEVIN_DATA_DIR or platform default)",
            )
        p.add_argument(
            "--out",
            help="backups dir (default: $DEVIN_BACKUP_DIR or <data-dir>/backups)",
        )

    p_create = sub.add_parser("create", help="snapshot all Devin stores")
    add_dirs(p_create)
    p_create.add_argument(
        "--config-dir",
        help="separate Devin UI config root (Linux default is detected)",
    )
    p_create.set_defaults(func=_cmd_create)

    p_verify = sub.add_parser("verify", help="check a snapshot's integrity")
    p_verify.add_argument("snapshot_dir")
    p_verify.set_defaults(func=_cmd_verify)

    p_list = sub.add_parser("list", help="list snapshots")
    add_dirs(p_list)
    p_list.set_defaults(func=_cmd_list)

    p_restore = sub.add_parser("restore", help="restore a snapshot")
    p_restore.add_argument("snapshot_dir")
    p_restore.add_argument("--to", required=True, help="target Devin data root")
    p_restore.add_argument(
        "--config-to",
        help="target Devin UI config root (default: platform location)",
    )
    group = p_restore.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=True,
        help="(default) show what would happen, write nothing",
    )
    group.add_argument(
        "--apply", dest="dry_run", action="store_false",
        help="actually restore",
    )
    p_restore.add_argument(
        "--no-backup", action="store_true",
        help="skip the pre-restore backup (refuses to overwrite anything)",
    )
    p_restore.set_defaults(func=_cmd_restore)

    p_rotate = sub.add_parser("rotate", help="keep last N snapshots, delete older")
    add_dirs(p_rotate)
    p_rotate.add_argument(
        "--keep", type=int,
        default=int(os.environ.get("DEVIN_BACKUP_KEEP", "10")),
        help="snapshots to keep (default: $DEVIN_BACKUP_KEEP or 10)",
    )
    p_rotate.add_argument(
        "--yes", action="store_true",
        help="confirm deletion (required — rotate is destructive)",
    )
    p_rotate.set_defaults(func=_cmd_rotate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (
        snapshot.SnapshotError,
        restore.RestoreError,
        DataDirError,
        ValueError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

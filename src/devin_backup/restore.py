"""Restore a snapshot into a data directory.

Safety model:

- **Dry-run by default** — ``dry_run=True`` writes nothing and returns the
  plan (``would_write`` / ``would_overwrite`` / ``warnings``).
- **Pre-restore backup** — if any target file would be overwritten, the
  current files are first copied into ``<backups>/pre-restore-<timestamp>/``
  (consistent SQLite copies, same as a regular snapshot). Restore refuses to
  proceed if that backup cannot be made.
- **No-backup mode** — ``backup=False`` refuses to overwrite anything rather
  than destroying data silently.
- **Schema drift warning** — manifest ``schema_version``s are compared against
  the live databases, so "backup is v15, current is v17" is loud, not silent.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from devin_internals.schema import SchemaError, detect_schema_version

from devin_backup.snapshot import (
    MANIFEST_NAME,
    MANIFEST_VERSION,
    PRE_RESTORE_PREFIX,
    SnapshotError,
    _copy_store,
    _unique_dir,
    load_manifest,
    snapshot_timestamp,
)
from devin_backup.stores import Store


class RestoreError(RuntimeError):
    """The restore was refused or could not be completed safely."""


def _check_paths(manifest: dict, target_dir: Path) -> list[str]:
    """Manifest paths must stay inside the target dir (no ``../`` escapes)."""
    root = target_dir.resolve()
    rels = []
    for entry in manifest["files"]:
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel:
            raise RestoreError(f"manifest: invalid path entry {rel!r}")
        dest = (target_dir / rel).resolve()
        if dest == root or not dest.is_relative_to(root):
            raise RestoreError(
                f"manifest: path {rel!r} escapes the restore target — refusing"
            )
        rels.append(rel)
    return rels


def _schema_warnings(manifest: dict, target_dir: Path) -> list[str]:
    warnings = []
    for rel, backed_up in manifest.get("schema_versions", {}).items():
        live = target_dir / rel
        if not live.is_file():
            continue
        try:
            current = detect_schema_version(live)["schema_version"]
        except (SchemaError, sqlite3.Error, OSError):
            warnings.append(
                f"{rel}: cannot detect schema version of the existing file"
            )
            continue
        if current != backed_up:
            warnings.append(
                f"{rel}: backup is schema v{backed_up}, "
                f"current file is v{current} — restoring will downgrade/upgrade it"
            )
    return warnings


def _pre_restore_backup(
    snapshot_dir: Path, target_dir: Path, existing: list[str], kinds: dict[str, str]
) -> Path:
    """Copy the files about to be overwritten into ``pre-restore-<ts>/``."""
    backups_dir = snapshot_dir.parent
    pre_dir = _unique_dir(
        backups_dir, PRE_RESTORE_PREFIX + snapshot_timestamp()
    )
    try:
        entries = []
        for rel in existing:
            store = Store(
                path=target_dir / rel,
                rel_path=rel,
                kind=kinds.get(rel, "file"),
            )
            entries.append(_copy_store(store, pre_dir))
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "kind": "pre-restore",
            "tool": "devin-backup",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_data_dir": str(target_dir.resolve()),
            "restores_snapshot": snapshot_dir.name,
            "files": entries,
        }
        (pre_dir / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        shutil.rmtree(pre_dir, ignore_errors=True)
        raise RestoreError(
            f"could not create pre-restore backup in {backups_dir}: {exc} — "
            "refusing to overwrite existing files"
        ) from exc
    return pre_dir


def restore_snapshot(
    snapshot_dir: str | Path,
    target_dir: str | Path,
    *,
    dry_run: bool = True,
    backup: bool = True,
    now: datetime | None = None,
) -> dict:
    """Restore ``snapshot_dir`` into ``target_dir``.

    Args:
        dry_run: default ``True`` — plan only, write nothing.
        backup: when overwriting, first copy current files to a
            ``pre-restore-<ts>`` dir next to the snapshots. ``False`` makes
            any overwrite a hard refusal instead.
        now: timestamp override (tests).
    """
    snapshot_dir = Path(snapshot_dir).expanduser()
    target_dir = Path(target_dir).expanduser()
    try:
        manifest = load_manifest(snapshot_dir)
    except SnapshotError:
        raise
    rels = _check_paths(manifest, target_dir)
    kinds = {e["path"]: e.get("kind", "file") for e in manifest["files"]}
    existing = [rel for rel in rels if (target_dir / rel).exists()]
    warnings = _schema_warnings(manifest, target_dir)

    if dry_run:
        return {
            "dry_run": True,
            "snapshot": str(snapshot_dir),
            "target": str(target_dir),
            "would_write": rels,
            "would_overwrite": existing,
            "would_backup": existing if (existing and backup) else [],
            "warnings": warnings,
        }

    if existing:
        if not backup:
            raise RestoreError(
                f"{target_dir}: {len(existing)} file(s) would be overwritten "
                "and backup=False — refusing"
            )
        pre_dir = _pre_restore_backup(snapshot_dir, target_dir, existing, kinds)
        pre_restore: str | None = str(pre_dir)
    else:
        pre_restore = None

    for rel in rels:
        dst = target_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot_dir / rel, dst)

    return {
        "dry_run": False,
        "snapshot": str(snapshot_dir),
        "target": str(target_dir),
        "written": rels,
        "overwritten": existing,
        "pre_restore_backup": pre_restore,
        "warnings": warnings,
    }

"""Discovery of Devin's local stores under a data directory.

Known store patterns (see devin-internals-spec ``docs/SPEC.md``)::

    <data-dir>/cli/sessions.db                  session metadata + message tree
    <data-dir>/User/acp-messages/*.db           per-session ACP message logs
    <data-dir>/User/globalStorage/state.vscdb   editor/workbench state
    <data-dir>/.devin/**                        user config (skills, memory, ...)

``*.db``/``*.vscdb`` files are treated as SQLite and copied through the
SQLite backup API; everything under ``.devin/`` is a plain file copy.
SQLite sidecars (``-wal``/``-shm``/``-journal``) are never copied directly —
``Connection.backup()`` already produces a consistent standalone file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SQLITE_SUFFIXES = {".db", ".vscdb"}
SQLITE_SIDECAR_SUFFIXES = {".db-wal", ".db-shm", ".db-journal",
                           ".vscdb-wal", ".vscdb-shm", ".vscdb-journal"}
CONFIG_DIR_NAME = ".devin"


class DataDirError(RuntimeError):
    """The data directory does not exist or is not a directory."""


@dataclass(frozen=True)
class Store:
    """A file worth snapshotting."""

    path: Path
    """Absolute source path."""
    rel_path: str
    """POSIX-style path relative to the data dir (manifest key)."""
    kind: str
    """``"sqlite"`` (backup API) or ``"file"`` (plain copy)."""


def default_data_dir() -> Path:
    """Best-effort location of Devin Desktop's data dir.

    ``DEVIN_DATA_DIR`` env var wins; otherwise ``%APPDATA%/Devin`` on Windows
    or ``~/.config/devin`` elsewhere. Always pass ``--data-dir`` when in doubt.
    """
    env = os.environ.get("DEVIN_DATA_DIR")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Devin"
    return Path.home() / ".config" / "devin"


def default_backups_dir(data_dir: str | Path) -> Path:
    """``<data-dir>/backups`` — overridable via ``DEVIN_BACKUP_DIR``."""
    env = os.environ.get("DEVIN_BACKUP_DIR")
    if env:
        return Path(env).expanduser()
    return Path(data_dir) / "backups"


def is_sqlite_store(path: Path) -> bool:
    return path.suffix.lower() in SQLITE_SUFFIXES


def _is_under(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def discover_stores(
    data_dir: str | Path, *, exclude: list[str | Path] | None = None
) -> list[Store]:
    """Find all snapshot-worthy files under ``data_dir``.

    Args:
        data_dir: Devin data directory to scan.
        exclude: directories to skip (e.g. the backups dir itself when it
            lives inside the data dir).

    Raises:
        DataDirError: ``data_dir`` does not exist or is not a directory.
    """
    data_dir = Path(data_dir).expanduser()
    if not data_dir.is_dir():
        raise DataDirError(f"{data_dir}: not a directory")

    excluded = [Path(e).expanduser().resolve() for e in (exclude or [])]
    stores: list[Store] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if any(_is_under(resolved, e) for e in excluded):
            continue
        rel = path.relative_to(data_dir).as_posix()
        if path.suffix.lower() in SQLITE_SIDECAR_SUFFIXES or path.name.endswith(
            ("-wal", "-shm", "-journal")
        ):
            continue
        if is_sqlite_store(path):
            stores.append(Store(path=path, rel_path=rel, kind="sqlite"))
        elif path.relative_to(data_dir).parts[0] == CONFIG_DIR_NAME:
            stores.append(Store(path=path, rel_path=rel, kind="file"))
    return stores

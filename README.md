# devin-backup

> **Unofficial community project.** Not affiliated with, endorsed by, or
> sponsored by Cognition AI. "Devin" is a trademark of Cognition AI.

**[Português (BR)](README.pt-BR.md)** · English

Safe backup & restore for Devin Desktop stores: timestamped snapshots of
`sessions.db`, `acp-messages/`, `state.vscdb` and `.devin/` config — with
SQLite-consistent copies, integrity verification and rotation.

## The problem

Everything Devin keeps about your work lives in a handful of local SQLite
databases and config files. Two failure modes make naive `copy`/`robocopy`
backups dangerous:

1. **Live SQLite files.** Copying `sessions.db` while Devin is running can
   produce a corrupt copy — mid-write pages, unmerged WAL. It *looks* fine
   until you restore it.
2. **Silent schema drift.** `sessions.db` has already had **17 migrations**.
   Restoring an old backup over a newer install silently downgrades your
   data; nothing warns you.

## Prior art

General-purpose backup tools — `restic`, `borg`, `robocopy`, Windows File
History — copy bytes faithfully, but they know nothing about SQLite
consistency or about which files under a Devin data dir actually matter.
This project adapts the standard practice (`sqlite3`'s online backup API +
checksum manifests + retention rotation); it does not reinvent it.

## What makes it Devin-native

*It knows which stores are Devin's brain — and warns you when the brain's
format changed underneath a backup.*

1. **Side-by-side:** snapshots are made through `sqlite3.Connection.backup()`
   (consistent even while Devin runs, with file-copy fallback), and every
   manifest records `schema_version` via
   [`devin-internals-spec`](https://github.com/Icaro0310/devin-internals-spec).
2. **No-Devin:** remove Devin and there is nothing to discover — the extra
   disappears.
3. **One sentence:** on restore you get *"backup is v15, current is v17"*
   instead of a silent downgrade.

## Install

Python ≥ 3.10 and `pipx` are required. **Windows (PowerShell):** install `pipx` with `py -m pip install --user pipx`, run `py -m pipx ensurepath`, then reopen the terminal. **Linux (Debian/Ubuntu):** run `sudo apt install pipx python3-venv` and `pipx ensurepath`; reopen the terminal. Other Linux distributions should install `pipx` using their package manager.

```bash
pipx install "devin-backup @ git+https://github.com/Icaro0310/devin-backup.git"
```

(Not on PyPI yet.)

## Usage

```bash
devin-backup create  [--data-dir <session-data-root>] [--config-dir <ui-config-root>] [--out <backups-dir>]
devin-backup verify  <snapshot-dir>
devin-backup list    [--out <backups-dir>]
devin-backup restore <snapshot-dir> --to <session-data-root> [--config-to <ui-config-root>] [--apply] [--no-backup]
devin-backup rotate  [--keep N] --yes
```

- `create` snapshots `sessions.db`, ACP message databases, `state.vscdb` and
  `.devin/` files when present. A v2 manifest records which source root each
  file came from; old v1 snapshots remain readable.
- On Linux, the CLI data root and UI config root are separate. The default
  `create` detects both. If you pass `--data-dir`, also pass `--config-dir`
  to include the UI stores.
- `verify` re-checks every hash and runs `PRAGMA integrity_check` on DBs;
  exit code 1 on failure.
- `restore` is a **dry-run by default**. It restores data-root files to
  `--to` and config-root files to `--config-to` (default: detected UI config
  root). Pass `--apply` to write. Existing files are saved to a
  `pre-restore-<ts>` backup first; `--no-backup` refuses overwrites.
- `rotate` keeps the newest N snapshots (default `$DEVIN_BACKUP_KEEP` or 10)
  and is a no-op until `--yes`. `pre-restore-*` dirs are never rotated.

Defaults: the session data root is `$DEVIN_DATA_DIR` or
`%APPDATA%\\devin` on Windows and `$XDG_DATA_HOME/devin` (normally
`~/.local/share/devin`) on Linux. The UI config root is `%APPDATA%\\Devin`
on Windows and `$XDG_CONFIG_HOME/Devin` (normally `~/.config/Devin`) on Linux.
`--out` defaults to `$DEVIN_BACKUP_DIR` or `<data-root>/backups`.

```python
from devin_backup import snapshot, verify, restore

snap = snapshot.create_snapshot(data_dir, backups_dir, config_dir=config_dir)
verify.verify_snapshot(snap)                       # {"ok": True, ...}
restore.restore_snapshot(snap, data_dir, config_dir=config_dir)  # dry-run
```

## Works with Devin alone (Devin-only mode)

devin-backup copies Devin's local stores to a destination folder you pick —
an external drive, a synced folder, anywhere on disk. No cloud account, VM or
network service is required.

Snapshots contain real session data (prompts, paths, commands). Treat the
backup destination as sensitive: keep it on a private/encrypted volume and
apply the same care you give the original stores.

## Platform support

Tested on **Windows and Linux** (`windows-latest` + `ubuntu-latest` in CI).
Windows stores share the `%APPDATA%\\Devin` root. Linux stores are discovered
separately under `XDG_DATA_HOME/devin` and `XDG_CONFIG_HOME/Devin`. Use
`--data-dir` and `--config-dir` for non-default locations.
## Limitations

- **Private, volatile internals.** These stores are Devin implementation
  details; paths and schemas can change in any release. Store discovery is
  pattern-based (`*.db`, `*.vscdb`, `.devin/`) and best-effort.
- **Schema versions only exist where Devin keeps a ledger** —
  `sessions.db` gets a real `schema_version`; `acp-messages`/`state.vscdb`
  do not have one to record.
- **Not a scheduler.** M1 takes snapshots when you run it; Task Scheduler /
  cron integration is queued for M2 (see `docs/SPEC.md` §10).
- **Writes only on `--apply`.** Backup never touches Devin's databases except
  through the read-only backup API. `restore --apply` is the only write path
  and is always guarded by a pre-restore backup.
- Tested only against **synthetic fixtures** — no real session content is
  ever copied, by design.

## Development

```bash
pip install -e ".[dev]"
python -m pytest
```

Ground rules in [CONTRIBUTING.md](CONTRIBUTING.md): fixtures before code,
small commits, bilingual docs. Canonical spec: [docs/SPEC.md](docs/SPEC.md).

## License

MIT — see [LICENSE](LICENSE).

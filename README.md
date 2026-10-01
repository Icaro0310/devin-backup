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

```bash
pipx install "devin-backup @ git+https://github.com/Icaro0310/devin-backup.git"
```

(Not on PyPI yet.)

## Usage

```bash
devin-backup create  [--data-dir <path>] [--out <backups-dir>]
devin-backup verify  <snapshot-dir>
devin-backup list    [--out <backups-dir>]
devin-backup restore <snapshot-dir> --to <data-dir> [--apply] [--no-backup]
devin-backup rotate  [--keep N] --yes
```

- `create` writes `<backups>/<UTC timestamp>/` + `manifest.json`
  (files, sizes, sha256, schema versions).
- `verify` re-checks every hash and runs `PRAGMA integrity_check` on DBs;
  exit code 1 on failure.
- `restore` is a **dry-run by default** — pass `--apply` to write. Before
  overwriting anything it copies current files to a `pre-restore-<ts>`
  backup; `--no-backup` refuses to overwrite instead.
- `rotate` keeps the newest N snapshots (default `$DEVIN_BACKUP_KEEP` or 10)
  and is a no-op until `--yes`. `pre-restore-*` dirs are never rotated.

Defaults: `--data-dir` ← `$DEVIN_DATA_DIR` or `%APPDATA%\Devin` /
`~/.config/devin`; `--out` ← `$DEVIN_BACKUP_DIR` or `<data-dir>/backups`.

```python
from devin_backup import snapshot, verify, restore

snap = snapshot.create_snapshot(data_dir, backups_dir)
verify.verify_snapshot(snap)              # {"ok": True, ...}
restore.restore_snapshot(snap, data_dir)  # dry-run plan, writes nothing
```

## Platform support

Tested on **Windows and Linux** (`windows-latest` + `ubuntu-latest` in CI).
The Devin data dir is auto-detected: `%APPDATA%\Devin` on Windows,
`~/.config/devin` on other OSes; override with `--data-dir` or the
`DEVIN_DATA_DIR` env var.

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

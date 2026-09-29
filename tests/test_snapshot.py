import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from devin_internals import fixtures

from devin_backup import snapshot
from devin_backup.stores import discover_stores

EXPECTED_STORES = 5  # sessions.db + 2 acp-messages + state.vscdb + .devin/config.json


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_discover_stores_finds_all(data_dir):
    stores = discover_stores(data_dir)
    rels = sorted(s.rel_path for s in stores)
    assert "cli/sessions.db" in rels
    assert "User/globalStorage/state.vscdb" in rels
    assert ".devin/config.json" in rels
    acp = [r for r in rels if r.startswith("User/acp-messages/")]
    assert len(acp) == 2
    kinds = {s.rel_path: s.kind for s in stores}
    assert kinds["cli/sessions.db"] == "sqlite"
    assert kinds[".devin/config.json"] == "file"


def test_snapshot_copies_all_stores_with_manifest(data_dir, backups_dir):
    snap = snapshot.create_snapshot(data_dir, backups_dir)
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 1
    files = {f["path"]: f for f in manifest["files"]}
    assert len(files) == EXPECTED_STORES

    for rel, entry in files.items():
        copied = snap / rel
        assert copied.is_file(), rel
        assert entry["size"] == copied.stat().st_size
        assert entry["sha256"] == sha256(copied)

    # plain files are byte-identical to the source
    assert (snap / ".devin" / "config.json").read_bytes() == (
        data_dir / ".devin" / "config.json"
    ).read_bytes()


def test_snapshot_uses_sqlite_backup_api(data_dir, backups_dir):
    snap = snapshot.create_snapshot(data_dir, backups_dir)
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    entry = {f["path"]: f for f in manifest["files"]}["cli/sessions.db"]
    assert entry["copied_via"] == "sqlite-backup"

    # the copy is a real, consistent database with the same rows
    src = sqlite3.connect(data_dir / "cli" / "sessions.db")
    dst = sqlite3.connect(snap / "cli" / "sessions.db")
    n_src = src.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    n_dst = dst.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert n_dst == n_src and n_src > 0
    src.close()
    dst.close()


def test_snapshot_records_schema_version(data_dir, backups_dir):
    snap = snapshot.create_snapshot(data_dir, backups_dir)
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_versions"]["cli/sessions.db"] == 17
    entry = {f["path"]: f for f in manifest["files"]}["cli/sessions.db"]
    assert entry["schema_version"] == 17


def test_snapshot_records_older_schema_version(tmp_path, backups_dir):
    root = tmp_path / "data"
    fixtures.create_sessions_db(root / "cli" / "sessions.db", schema_version=15)
    snap = snapshot.create_snapshot(root, backups_dir)
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_versions"]["cli/sessions.db"] == 15


def test_snapshot_falls_back_to_file_copy(tmp_path, backups_dir):
    root = tmp_path / "data"
    (root / "cli").mkdir(parents=True)
    fake = root / "cli" / "sessions.db"
    fake.write_bytes(b"this is not a sqlite database")
    snap = snapshot.create_snapshot(root, backups_dir)
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    entry = {f["path"]: f for f in manifest["files"]}["cli/sessions.db"]
    assert entry["copied_via"] == "file-copy"
    assert entry["schema_version"] is None
    assert (snap / "cli" / "sessions.db").read_bytes() == fake.read_bytes()


def test_snapshot_excludes_backups_dir_inside_data_dir(data_dir):
    out = data_dir / "backups"
    snap1 = snapshot.create_snapshot(data_dir, out)
    snap2 = snapshot.create_snapshot(data_dir, out)
    m1 = json.loads((snap1 / "manifest.json").read_text(encoding="utf-8"))
    m2 = json.loads((snap2 / "manifest.json").read_text(encoding="utf-8"))
    assert len(m2["files"]) == len(m1["files"]) == EXPECTED_STORES


def test_snapshot_timestamped_and_unique(data_dir, backups_dir):
    now = datetime(2026, 9, 29, 20, 30, 0, tzinfo=timezone.utc)
    snap = snapshot.create_snapshot(data_dir, backups_dir, now=now)
    assert snap.name == "20260929T203000Z"
    snap2 = snapshot.create_snapshot(data_dir, backups_dir, now=now)
    assert snap2.name != snap.name
    snap3 = snapshot.create_snapshot(
        data_dir, backups_dir, now=now + timedelta(seconds=1)
    )
    assert snap3.name == "20260929T203001Z"


def test_snapshot_empty_data_dir_raises(tmp_path, backups_dir):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(snapshot.SnapshotError):
        snapshot.create_snapshot(empty, backups_dir)
    assert not list(backups_dir.iterdir()) if backups_dir.exists() else True


def test_snapshot_missing_data_dir_raises(tmp_path, backups_dir):
    with pytest.raises(snapshot.SnapshotError):
        snapshot.create_snapshot(tmp_path / "nope", backups_dir)

"""Contract test: the manifest devin-janitor's tier-3 guard consumes.

`devin-janitor cleanup --tier3` refuses to delete GUI state unless a
verified devin-backup snapshot manifest younger than 24h covers
`state.vscdb`. It re-implements the manifest format on its side
(`manifest_version in {1,2}`, `files[]` entries with `path`, `size`,
`sha256`, optional `snapshot_path`, ISO-8601 `created_at`).

These tests pin the producer side of that contract so a manifest change
that would break janitor fails here first. The consumer-side rules are
documented in `docs/snapshot-contract.md`.
"""

import json
from datetime import datetime

from devin_backup import snapshot

# Fields devin-janitor/cleanup.py::verify_snapshot requires.
REQUIRED_MANIFEST_FIELDS = {"manifest_version", "created_at", "files"}
REQUIRED_FILE_FIELDS = {"path"}  # size/sha256 enforced when present
SUPPORTED_MANIFEST_VERSIONS = {1, 2}
TIER3_REQUIRED_FRAGMENT = "state.vscdb"


def test_manifest_shape_satisfies_janitor(data_dir, backups_dir):
    snap = snapshot.create_snapshot(data_dir, backups_dir)
    manifest = json.loads((snap / "manifest.json").read_text())

    assert REQUIRED_MANIFEST_FIELDS <= set(manifest)
    assert manifest["manifest_version"] in SUPPORTED_MANIFEST_VERSIONS
    # janitor rejects manifests whose created_at it cannot parse
    datetime.fromisoformat(manifest["created_at"])
    assert isinstance(manifest["files"], list)

    for entry in manifest["files"]:
        assert REQUIRED_FILE_FIELDS <= set(entry)
        f = snap / (entry.get("snapshot_path") or entry["path"])
        assert f.is_file(), entry["path"]
        if "size" in entry:
            assert f.stat().st_size == entry["size"]
        if "sha256" in entry:
            import hashlib

            assert hashlib.sha256(f.read_bytes()).hexdigest() == entry["sha256"]


def test_manifest_covers_state_vscdb(data_dir, backups_dir):
    """Tier-3 needs a manifest whose files cover `state.vscdb`."""
    snap = snapshot.create_snapshot(data_dir, backups_dir)
    manifest = json.loads((snap / "manifest.json").read_text())
    assert any(
        TIER3_REQUIRED_FRAGMENT in str(e.get("path", ""))
        for e in manifest["files"]
    ), "manifest lost state.vscdb coverage — janitor tier-3 would refuse"

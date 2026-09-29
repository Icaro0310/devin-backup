import pytest
from devin_internals import fixtures


@pytest.fixture
def data_dir(tmp_path):
    """A synthetic Devin data dir (sessions.db, acp-messages, state.vscdb)
    plus a ``.devin/`` config file, via devin-internals-spec fixtures."""
    root = tmp_path / "data"
    fixtures.create_devin_data_dir(root, n_acp_dbs=2)
    cfg = root / ".devin" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('{"synthetic": true}\n', encoding="utf-8")
    return root


@pytest.fixture
def backups_dir(tmp_path):
    return tmp_path / "backups"

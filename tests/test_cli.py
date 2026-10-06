"""The ``retailia`` command: argument checks and the offline commands."""

import json
import sqlite3

import pytest

from retailia.cli import main


@pytest.mark.parametrize("count", ["0", "-1", "1000", "many"])
def test_init_db_rejects_customer_counts_outside_1_to_999(count, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["init-db", "--customers", count])
    assert exc.value.code == 2
    assert "--customers" in capsys.readouterr().err


def test_init_db_build_index_and_eval_run_offline(tmp_path, monkeypatch, capsys):
    db_path, index_path = tmp_path / "store.db", tmp_path / "faq_index.json"
    monkeypatch.setenv("RETAILIA_DB_PATH", str(db_path))
    monkeypatch.setenv("RETAILIA_INDEX_PATH", str(index_path))
    monkeypatch.setenv("RETAILIA_LLM_PROVIDER", "offline")
    monkeypatch.setenv("RETAILIA_EMBEDDER", "hashing")
    assert main(["init-db", "--customers", "3"]) == 0
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM customers WHERE role = 'customer'").fetchone()[0] == 3
    assert main(["build-index"]) == 0
    assert json.loads(index_path.read_text(encoding="utf-8"))["embedder"] == "hashing-512"
    summary_path = tmp_path / "summary.json"
    assert main(["eval", "--json", str(summary_path)]) == 0
    assert json.loads(summary_path.read_text(encoding="utf-8"))["db_unchanged"] is True


@pytest.mark.parametrize("make_folder", [False, True])
def test_build_index_reports_a_missing_or_empty_folder(make_folder, tmp_path, monkeypatch, capsys):
    folder = tmp_path / "faq"
    if make_folder:
        folder.mkdir()
    monkeypatch.setenv("RETAILIA_INDEX_PATH", str(tmp_path / "faq_index.json"))
    monkeypatch.setenv("RETAILIA_EMBEDDER", "hashing")
    assert main(["build-index", "--faq-dir", str(folder)]) == 1
    assert "Cannot build the FAQ index" in capsys.readouterr().err
    assert not (tmp_path / "faq_index.json").exists()


def test_configuration_error_exits_with_code_2(monkeypatch, capsys):
    monkeypatch.setenv("RETAILIA_LLM_PROVIDER", "nonsense")
    assert main(["eval"]) == 2
    assert "Configuration error" in capsys.readouterr().err

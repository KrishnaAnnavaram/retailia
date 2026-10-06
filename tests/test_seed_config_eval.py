"""Problems 1, 7 and 10: secrets from the environment, a generator that matches the schema, evaluation."""

import re
from pathlib import Path

import pytest

from retailia.agent.models import FakeChatModel, ModelTurn
from retailia.config import Settings, SettingsError
from retailia.data.db import StoreDB
from retailia.data.seed import seed_store
from retailia.evaluation import load_suite, run_suites

ROOT = Path(__file__).resolve().parents[1]


def _table_counts(db):
    with db.read_only() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def test_seed_populates_every_table_with_valid_foreign_keys(db):
    counts = _table_counts(db)
    assert all(n > 0 for n in counts.values()), counts
    with db.read_only() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        mismatched = conn.execute(
            "SELECT o.order_id FROM orders o JOIN order_items i USING (order_id) GROUP BY o.order_id "
            "HAVING o.total_cents != SUM(i.quantity * i.unit_price_cents)").fetchall()
    assert mismatched == []


def test_seed_is_deterministic_and_reseeding_does_not_duplicate(tmp_path):
    a, b = StoreDB(tmp_path / "a.db"), StoreDB(tmp_path / "b.db")
    seed_store(a, demo_password="pw-for-tests", seed=9, customers=3)
    seed_store(b, demo_password="pw-for-tests", seed=9, customers=3)
    seed_store(b, demo_password="pw-for-tests", seed=9, customers=3)
    assert _table_counts(a) == _table_counts(b)
    with a.read_only() as ca, b.read_only() as cb:
        q = "SELECT order_id, customer_id, status, total_cents FROM orders ORDER BY order_id"
        assert ca.execute(q).fetchall() == cb.execute(q).fetchall()


def test_settings_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings.from_env({"RETAILIA_DB_PATH": "rel/store.db"})
    assert s.db_path == (tmp_path / "rel" / "store.db").resolve() and s.llm_provider == "offline"
    secret = Settings.from_env({"RETAILIA_LLM_PROVIDER": "openai", "RETAILIA_LLM_API_KEY": "placeholder-value"})
    assert "placeholder-value" not in repr(secret)


@pytest.mark.parametrize("env", [{"RETAILIA_LLM_PROVIDER": "openai"}, {"RETAILIA_EMBEDDER": "openai"},
                                 {"RETAILIA_LLM_PROVIDER": "groq-direct"}, {"RETAILIA_MAX_TOOL_STEPS": "0"}])
def test_invalid_settings(env):
    with pytest.raises(SettingsError):
        Settings.from_env(env)


def test_no_credentials_in_source_tree():
    key_like = re.compile(r"(?:sk-|gsk_|AIza|hf_)[A-Za-z0-9_-]{16,}")
    for path in list((ROOT / "src").rglob("*.py")) + [ROOT / ".env.example"]:
        assert not key_like.search(path.read_text(encoding="utf-8")), path
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            assert line.endswith("="), line


def test_offline_model_passes_all_suites():
    report = run_suites()
    summary = report.summary()
    assert summary["failures"] == [] and report.passed
    for key in ("routing_accuracy", "account_answer_accuracy", "faq_citation_accuracy", "redteam_pass_rate"):
        assert summary[key] == 1.0
    assert summary["redteam_cases"] == len(load_suite("redteam")) >= 10


def test_red_team_catches_a_leaky_model():
    leaky = lambda: FakeChatModel(lambda m, t: ModelTurn(content="Customer 01 lives at 1 Example Street"))  # noqa
    report = run_suites(leaky)
    assert not report.passed and report.summary()["redteam_pass_rate"] < 1.0

from datetime import date, datetime

import pytest

from retailia.app import build
from retailia.config import Settings, packaged_faq_dir
from retailia.data.db import StoreDB
from retailia.data.seed import seed_store
from retailia.rag.embeddings import HashingEmbedder
from retailia.rag.index import build_index, save_index

PASSWORD = "test-only-passphrase"  # synthetic, used only for throwaway test databases
TODAY = date(2026, 3, 1)


@pytest.fixture(scope="session")
def store_dir(tmp_path_factory):
    folder = tmp_path_factory.mktemp("store")
    seed_store(StoreDB(folder / "store.db"), demo_password=PASSWORD, seed=5, customers=4, today=TODAY)
    save_index(build_index(packaged_faq_dir(), HashingEmbedder()), folder / "faq_index.json")
    return folder


@pytest.fixture
def settings(store_dir):
    return Settings(db_path=store_dir / "store.db", index_path=store_dir / "faq_index.json")


@pytest.fixture
def db(settings):
    return StoreDB(settings.db_path)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 3, 1, 12, 0)

    def __call__(self):
        return self.now


@pytest.fixture
def make_app(settings):
    def _make(model=None, clock=None, **overrides):
        s = Settings(**{**settings.__dict__, **overrides})
        return build(s, model=model, embedder=HashingEmbedder(), clock=clock or Clock())
    return _make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def customer(app):
    return app.auth.login("customer02", PASSWORD)


@pytest.fixture
def staff(app):
    return app.auth.login("staff01", PASSWORD)

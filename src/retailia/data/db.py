"""SQLite connections.

* :meth:`StoreDB.read_only` opens the file with ``mode=ro`` and sets
  ``PRAGMA query_only``. Everything reachable from the assistant uses it.
* :meth:`StoreDB.read_write` is used only by seeding and by the auth service
  (failed-login counters); the assistant never gets it.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator


class DatabaseMissing(FileNotFoundError):
    pass


class StoreDB:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser().resolve()

    def create_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sql = resources.files("retailia.data").joinpath("schema.sql").read_text(encoding="utf-8")
        with self.read_write() as conn:
            conn.executescript(sql)

    @staticmethod
    def _prepare(conn: sqlite3.Connection) -> sqlite3.Connection:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def read_write(self) -> Iterator[sqlite3.Connection]:
        conn = self._prepare(sqlite3.connect(self.path, timeout=10))
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read_only(self) -> Iterator[sqlite3.Connection]:
        if not self.path.exists():
            raise DatabaseMissing(f"no database at {self.path}; run `retailia init-db` first")
        conn = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=10)
        try:
            self._prepare(conn).execute("PRAGMA query_only = ON")
            yield conn
        finally:
            conn.close()

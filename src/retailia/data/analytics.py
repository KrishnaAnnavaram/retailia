"""Staff-only catalogue analytics over PII-free views, guarded in code.

A model may write SQL here, so the guard does not trust the text at all. It
relies on SQLite itself:

* the connection is read-only (``mode=ro`` + ``query_only``);
* an authorizer callback allows only ``SELECT``, reading the allow-listed views
  (plus exactly the base-table columns those views use), and a short list of
  harmless functions; anything else (PRAGMA, ATTACH, writes, recursive CTEs,
  any read of ``customers`` ...) is denied while the statement is compiled;
* a progress handler aborts long-running queries, and results are capped.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from retailia.data.db import StoreDB

# Base-table columns each view needs. SQLite reports the "source" of a read as the view *or CTE* name, so a
# query could name its own CTE "v_catalog"; restricting reads to exactly these columns means such a CTE can
# never reach anything the real views do not already expose (and never the customers table).
VIEW_BASE_COLUMNS: dict[str, frozenset[tuple[str, str]]] = {
    "v_catalog": frozenset({
        ("products", "product_id"), ("products", "sku"), ("products", "name"), ("products", "price_cents"),
        ("products", "stock"), ("products", "category_id"), ("categories", "category_id"), ("categories", "name"),
        ("feedback", "feedback_id"), ("feedback", "product_id"), ("feedback", "rating"),
    }),
    "v_product_sales": frozenset({
        ("products", "product_id"), ("products", "name"), ("products", "category_id"),
        ("categories", "category_id"), ("categories", "name"), ("order_items", "order_id"),
        ("order_items", "product_id"), ("order_items", "quantity"), ("order_items", "unit_price_cents"),
        ("orders", "order_id"), ("orders", "status"),
    }),
    "v_orders_by_month": frozenset({("orders", "placed_at"), ("orders", "status"), ("orders", "total_cents")}),
}
ALLOWED_VIEWS = frozenset(VIEW_BASE_COLUMNS)
NEVER_READABLE = frozenset({"customers"})
ALLOWED_FUNCTIONS = frozenset({
    "count", "sum", "avg", "min", "max", "round", "lower", "upper", "substr", "length", "coalesce", "ifnull",
    "abs", "total", "printf", "strftime", "date", "cast",
})
MAX_RESULT_ROWS = 50
MAX_VM_STEPS = 2_000_000


class AnalyticsDenied(PermissionError):
    pass


def _authorizer(action: int, arg1: str | None, arg2: str | None, db_name: str | None, source: str | None) -> int:
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        # arg1 = table, arg2 = column, source = innermost view/trigger/CTE name (None for direct access)
        if arg1 in NEVER_READABLE:
            return sqlite3.SQLITE_DENY
        if arg1 in ALLOWED_VIEWS:
            return sqlite3.SQLITE_OK
        allowed = VIEW_BASE_COLUMNS.get(source or "", frozenset())
        if (arg1, arg2) in allowed or (not arg2 and any(t == arg1 for t, _ in allowed)):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK if (arg2 or "").lower() in ALLOWED_FUNCTIONS else sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY


def run_analytics_query(db: StoreDB, sql: str) -> dict[str, Any]:
    statement = sql.strip().rstrip(";").strip()
    if not statement:
        raise AnalyticsDenied("empty query")
    if ";" in statement:
        raise AnalyticsDenied("only one statement is allowed")
    steps = {"n": 0}

    def progress() -> int:
        steps["n"] += 1
        return 1 if steps["n"] * 1000 > MAX_VM_STEPS else 0

    with db.read_only() as conn:
        conn.set_authorizer(_authorizer)
        conn.set_progress_handler(progress, 1000)
        try:
            cursor = conn.execute(statement)
            rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
        except sqlite3.DatabaseError as exc:
            raise AnalyticsDenied(f"query rejected: {exc}") from exc
        finally:
            conn.set_authorizer(None)
            conn.set_progress_handler(None, 0)
    columns = [d[0] for d in cursor.description or []]
    return {"columns": columns, "rows": [list(r) for r in rows[:MAX_RESULT_ROWS]],
            "truncated": len(rows) > MAX_RESULT_ROWS}

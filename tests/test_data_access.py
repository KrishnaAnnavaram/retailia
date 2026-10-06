"""Problem 2: per-customer access and read-only queries are enforced in code."""

import sqlite3

import pytest

from retailia.data.analytics import AnalyticsDenied, run_analytics_query
from retailia.data.repositories import Catalog, CustomerScope


def _owner_of_orders(db):
    with db.read_only() as conn:
        return {r[0]: r[1] for r in conn.execute("SELECT order_id, customer_id FROM orders")}


def test_scope_only_sees_own_orders(db):
    owners = _owner_of_orders(db)
    scope = CustomerScope(db, 2)
    mine = {o["order_id"] for o in scope.orders(limit=10)}
    assert mine == {oid for oid, cid in owners.items() if cid == 2}
    foreign = next(oid for oid, cid in owners.items() if cid != 2)
    assert scope.order(foreign) is None  # indistinguishable from a non-existent order
    assert scope.order(999999) is None


def test_profile_masks_email(db):
    profile = CustomerScope(db, 2).profile()
    assert profile["email"] == "c***@example.com"
    assert "shipping_address" not in profile


def test_read_only_connection_rejects_writes(db):
    with db.read_only() as conn, pytest.raises(sqlite3.OperationalError):
        conn.execute("UPDATE orders SET status = 'cancelled'")


def test_catalog_search_is_parameterised(db):
    catalog = Catalog(db)
    assert catalog.search("'; DROP TABLE products; --") == []
    assert catalog.search("100%") == []  # LIKE wildcards are escaped
    bottles = catalog.search("water bottle", max_price_cents=3000)
    assert bottles and all("Water Bottle" in p["name"] for p in bottles)
    assert len(catalog.categories()) == 6


@pytest.mark.parametrize("sql", [
    "SELECT email FROM customers",
    "SELECT password_hash FROM customers",
    "SELECT * FROM orders",                                  # base table, row level, has customer_id
    "SELECT comment FROM feedback",
    "WITH v_catalog AS (SELECT email FROM customers) SELECT * FROM v_catalog",   # CTE name spoofing a view
    "WITH v_orders_by_month AS (SELECT customer_id FROM orders) SELECT * FROM v_orders_by_month",
    "SELECT (SELECT email FROM customers LIMIT 1) FROM v_catalog",
    "PRAGMA table_info(customers)",
    "DELETE FROM orders",
    "SELECT * FROM v_catalog; DELETE FROM orders",
    "ATTACH DATABASE 'other.db' AS other",
    "SELECT load_extension('evil')",
    "",
])
def test_analytics_guard_denies(db, sql):
    with pytest.raises(AnalyticsDenied):
        run_analytics_query(db, sql)


def test_analytics_allows_views(db):
    result = run_analytics_query(db, "SELECT category, SUM(units_sold) AS units FROM v_product_sales "
                                     "GROUP BY category ORDER BY units DESC")
    assert result["columns"] == ["category", "units"] and len(result["rows"]) == 6
    assert run_analytics_query(db, "SELECT COUNT(*) FROM v_catalog")["rows"][0][0] == 108
    assert run_analytics_query(db, "select month, orders from v_orders_by_month")["rows"]


def test_analytics_aborts_runaway_queries(db, monkeypatch):
    import retailia.data.analytics as analytics

    monkeypatch.setattr(analytics, "MAX_VM_STEPS", 5_000)
    with pytest.raises(AnalyticsDenied):
        run_analytics_query(db, "SELECT COUNT(*) FROM v_catalog a, v_catalog b, v_catalog c")

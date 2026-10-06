"""Read-only, parameterised data access.

:class:`CustomerScope` is constructed with the signed-in customer's id and adds
``customer_id = ?`` to every query it runs. There is no method that takes a
customer id as an argument, so a tool (or a model driving it) cannot ask for
someone else's data. Asking for an order that belongs to another customer
looks exactly like asking for one that does not exist.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from retailia.data.db import StoreDB

MAX_ROWS = 25


def money(cents: int | None) -> str:
    return f"${(cents or 0) / 100:,.2f}"


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def _like_pattern(text: str) -> str:
    escaped = re.sub(r"([%_\\])", r"\\\1", text.strip().lower())
    return f"%{escaped}%"


class CustomerScope:
    def __init__(self, db: StoreDB, customer_id: int) -> None:
        if not isinstance(customer_id, int) or isinstance(customer_id, bool):
            raise TypeError("customer_id must be an int")  # the prototype passed a (3,) tuple around
        self.db = db
        self.customer_id = customer_id

    def profile(self) -> dict[str, Any] | None:
        with self.db.read_only() as conn:
            row = conn.execute("SELECT username, display_name, email, city FROM customers WHERE customer_id = ?",
                               (self.customer_id,)).fetchone()
        if row is None:
            return None
        return {"username": row["username"], "name": row["display_name"], "email": mask_email(row["email"]),
                "city": row["city"]}

    def orders(self, *, limit: int = 5, status: str | None = None) -> list[dict[str, Any]]:
        sql = ("SELECT o.order_id, o.status, o.placed_at, o.total_cents, o.tracking_code, "
               "(SELECT SUM(quantity) FROM order_items i WHERE i.order_id = o.order_id) AS units "
               "FROM orders o WHERE o.customer_id = ?")
        params: list[Any] = [self.customer_id]
        if status:
            sql += " AND o.status = ?"
            params.append(status)
        sql += " ORDER BY o.placed_at DESC, o.order_id DESC LIMIT ?"
        params.append(max(1, min(limit, MAX_ROWS)))
        with self.db.read_only() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._order_summary(r) for r in rows]

    @staticmethod
    def _order_summary(row: sqlite3.Row) -> dict[str, Any]:
        return {"order_id": row["order_id"], "status": row["status"], "placed_on": row["placed_at"][:10],
                "total": money(row["total_cents"]), "units": row["units"], "tracking_code": row["tracking_code"]}

    def order(self, order_id: int) -> dict[str, Any] | None:
        with self.db.read_only() as conn:
            row = conn.execute(
                "SELECT o.order_id, o.status, o.placed_at, o.total_cents, o.tracking_code, "
                "(SELECT SUM(quantity) FROM order_items i WHERE i.order_id = o.order_id) AS units "
                "FROM orders o WHERE o.order_id = ? AND o.customer_id = ?",
                (order_id, self.customer_id),
            ).fetchone()
            if row is None:
                return None
            items = conn.execute(
                "SELECT p.name, i.quantity, i.unit_price_cents FROM order_items i "
                "JOIN products p ON p.product_id = i.product_id WHERE i.order_id = ? ORDER BY p.name",
                (order_id,),
            ).fetchall()
        summary = self._order_summary(row)
        summary["items"] = [{"product": r["name"], "quantity": r["quantity"], "unit_price": money(r["unit_price_cents"])}
                            for r in items]
        return summary

    def cart(self) -> dict[str, Any]:
        with self.db.read_only() as conn:
            rows = conn.execute(
                "SELECT p.product_id, p.name, p.price_cents, p.stock, ci.quantity FROM carts c "
                "JOIN cart_items ci ON ci.cart_id = c.cart_id JOIN products p ON p.product_id = ci.product_id "
                "WHERE c.customer_id = ? ORDER BY p.name",
                (self.customer_id,),
            ).fetchall()
        items = [{"product_id": r["product_id"], "product": r["name"], "quantity": r["quantity"],
                  "unit_price": money(r["price_cents"]), "in_stock": r["stock"] >= r["quantity"]} for r in rows]
        subtotal = sum(r["price_cents"] * r["quantity"] for r in rows)
        return {"items": items, "units": sum(r["quantity"] for r in rows), "subtotal": money(subtotal)}

    def my_reviews(self) -> list[dict[str, Any]]:
        with self.db.read_only() as conn:
            rows = conn.execute(
                "SELECT p.name, f.rating, f.comment FROM feedback f JOIN products p ON p.product_id = f.product_id "
                "WHERE f.customer_id = ? ORDER BY f.created_at DESC LIMIT ?",
                (self.customer_id, MAX_ROWS),
            ).fetchall()
        return [{"product": r["name"], "rating": r["rating"], "comment": r["comment"]} for r in rows]


class Catalog:
    """Public product data. Reads only products, categories and aggregated ratings."""

    def __init__(self, db: StoreDB) -> None:
        self.db = db

    def categories(self) -> list[str]:
        with self.db.read_only() as conn:
            return [r["name"] for r in conn.execute("SELECT name FROM categories ORDER BY name")]

    def search(self, query: str | None = None, *, category: str | None = None, max_price_cents: int | None = None,
               in_stock_only: bool = False, limit: int = 8) -> list[dict[str, Any]]:
        sql = ["SELECT product_id, sku, name, category, price_cents, stock, avg_rating, rating_count "
               "FROM v_catalog WHERE 1 = 1"]
        params: list[Any] = []
        for word in (query or "").split()[:6]:
            sql.append("AND (lower(name) LIKE ? ESCAPE '\\' OR lower(category) LIKE ? ESCAPE '\\')")
            params += [_like_pattern(word.rstrip("s") if len(word) > 3 else word)] * 2
        if category:
            sql.append("AND lower(category) = lower(?)")
            params.append(category.strip())
        if max_price_cents is not None:
            sql.append("AND price_cents <= ?")
            params.append(max_price_cents)
        if in_stock_only:
            sql.append("AND stock > 0")
        sql.append("ORDER BY price_cents, name LIMIT ?")
        params.append(max(1, min(limit, MAX_ROWS)))
        with self.db.read_only() as conn:
            rows = conn.execute(" ".join(sql), params).fetchall()
        return [self._product(r) for r in rows]

    def product(self, product_id: int) -> dict[str, Any] | None:
        with self.db.read_only() as conn:
            row = conn.execute("SELECT product_id, sku, name, category, price_cents, stock, avg_rating, rating_count "
                               "FROM v_catalog WHERE product_id = ?", (product_id,)).fetchone()
        return self._product(row) if row else None

    @staticmethod
    def _product(row: sqlite3.Row) -> dict[str, Any]:
        return {"product_id": row["product_id"], "sku": row["sku"], "name": row["name"], "category": row["category"],
                "price": money(row["price_cents"]), "in_stock": row["stock"] > 0,
                "rating": row["avg_rating"], "ratings": row["rating_count"]}

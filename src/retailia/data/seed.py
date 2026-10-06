"""Deterministic synthetic store data that matches ``schema.sql`` exactly.

No real people: customers are ``customer01``... with ``@example.com`` emails and
made-up street addresses. All demo accounts share one password chosen by the
caller (the CLI generates a random one and prints it once); only its scrypt
hash is stored.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from retailia.auth.passwords import hash_password
from retailia.data.db import StoreDB

CATALOG = {
    "Electronics": ["Wireless Earbuds", "Bluetooth Speaker", "USB-C Charger", "Smart Watch", "Laptop Stand",
                    "Mechanical Keyboard"],
    "Home & Kitchen": ["Chef Knife", "French Press", "Cast Iron Pan", "Bamboo Cutting Board", "Electric Kettle",
                       "Storage Jar Set"],
    "Clothing": ["Rain Jacket", "Merino Sweater", "Running Shorts", "Denim Jeans", "Wool Socks", "Linen Shirt"],
    "Books": ["Field Guide to Birds", "Weeknight Recipes", "Intro to Watercolour", "Pocket Atlas",
              "Houseplant Handbook", "Puzzle Collection"],
    "Sports & Outdoors": ["Yoga Mat", "Trail Backpack", "Water Bottle", "Camping Lantern", "Resistance Bands",
                          "Hiking Poles"],
    "Beauty": ["Face Moisturiser", "Mineral Sunscreen", "Lip Balm Trio", "Hair Oil", "Clay Mask", "Hand Cream"],
}
VARIANTS = ["Classic", "Pro", "Lite", "Eco", "Max"]
PRICE_RANGE = {"Electronics": (1500, 19900), "Home & Kitchen": (900, 8900), "Clothing": (1200, 12900),
               "Books": (700, 3900), "Sports & Outdoors": (800, 9900), "Beauty": (500, 4500)}
CITIES = ["Northbridge", "Lakeside", "Riverton", "Maple Falls", "Harbor City", "Cedar Grove"]
STREETS = ["Example Street", "Sample Avenue", "Placeholder Road", "Demo Lane", "Test Boulevard"]
STATUSES = ["delivered"] * 6 + ["shipped"] * 2 + ["processing", "cancelled", "returned"]
COMMENTS = {5: "Excellent, exactly as described.", 4: "Good value, would buy again.", 3: "It's okay.",
            2: "Not great, quality could be better.", 1: "Disappointed with this one."}


@dataclass(frozen=True)
class SeedReport:
    customers: int
    staff: int
    products: int
    orders: int
    feedback: int


def _ts(day: date, rng: random.Random) -> str:
    return datetime.combine(day, time(rng.randint(8, 21), rng.randint(0, 59))).strftime("%Y-%m-%dT%H:%M:%S")


def seed_store(db: StoreDB, *, demo_password: str, seed: int = 11, customers: int = 20, staff: int = 1,
               today: date | None = None, reset: bool = True) -> SeedReport:
    """Create the schema and fill it. With ``reset`` (default) existing rows are replaced, never duplicated."""
    rng = random.Random(seed)
    today = today or date.today()
    db.create_schema()
    with db.read_write() as conn:
        if reset:
            for table in ("feedback", "order_items", "orders", "cart_items", "carts", "products", "categories",
                          "customers"):
                conn.execute(f"DELETE FROM {table}")  # fixed table names, no user input

        created = today.strftime("%Y-%m-%dT00:00:00")
        for n in range(1, customers + 1):
            conn.execute(
                "INSERT INTO customers (customer_id, username, password_hash, role, display_name, email, "
                "shipping_address, city, created_at) VALUES (?, ?, ?, 'customer', ?, ?, ?, ?, ?)",
                (n, f"customer{n:02d}", hash_password(demo_password), f"Customer {n:02d}",
                 f"customer{n:02d}@example.com", f"{rng.randint(1, 999)} {rng.choice(STREETS)}",
                 rng.choice(CITIES), created),
            )
        for s in range(1, staff + 1):
            conn.execute(
                "INSERT INTO customers (customer_id, username, password_hash, role, display_name, email, created_at) "
                "VALUES (?, ?, ?, 'staff', ?, ?, ?)",
                (1000 + s, f"staff{s:02d}", hash_password(demo_password), f"Staff {s:02d}",
                 f"staff{s:02d}@example.com", created),
            )

        product_prices: dict[int, int] = {}
        product_id = 0
        for category_id, (category, nouns) in enumerate(CATALOG.items(), start=1):
            conn.execute("INSERT INTO categories (category_id, name) VALUES (?, ?)", (category_id, category))
            low, high = PRICE_RANGE[category]
            for noun in nouns:
                for variant in rng.sample(VARIANTS, k=3):
                    product_id += 1
                    price = rng.randrange(low, high, 100) - 1  # e.g. 2499
                    product_prices[product_id] = price
                    conn.execute(
                        "INSERT INTO products (product_id, sku, name, description, price_cents, stock, category_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (product_id, f"SKU-{category_id}{product_id:04d}", f"{noun} {variant}",
                         f"{variant} edition of our {noun.lower()} in the {category} range.", price,
                         rng.choice([0, 3, 12, 25, 40, 80]), category_id),
                    )

        order_id = feedback_count = 0
        rated: set[tuple[int, int]] = set()
        for customer_id in range(1, customers + 1):
            conn.execute("INSERT INTO carts (cart_id, customer_id) VALUES (?, ?)", (customer_id, customer_id))
            for pid in rng.sample(sorted(product_prices), k=rng.randint(0, 3)):
                conn.execute("INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (?, ?, ?)",
                             (customer_id, pid, rng.randint(1, 3)))
            for _ in range(rng.randint(1, 5)):
                order_id += 1
                placed = today - timedelta(days=rng.randint(1, 180))
                status = rng.choice(STATUSES)
                if placed > today - timedelta(days=3):
                    status = "processing"
                items = {pid: rng.randint(1, 3) for pid in rng.sample(sorted(product_prices), k=rng.randint(1, 4))}
                total = sum(product_prices[p] * q for p, q in items.items())
                tracking = f"TRK{rng.randint(10**9, 10**10 - 1)}" if status in ("shipped", "delivered") else None
                conn.execute(
                    "INSERT INTO orders (order_id, customer_id, status, placed_at, total_cents, tracking_code) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, customer_id, status, _ts(placed, rng), total, tracking),
                )
                for pid, qty in items.items():
                    conn.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents) "
                                 "VALUES (?, ?, ?, ?)", (order_id, pid, qty, product_prices[pid]))
                    if status == "delivered" and (customer_id, pid) not in rated and rng.random() < 0.5:
                        rated.add((customer_id, pid))
                        rating = rng.choices([1, 2, 3, 4, 5], weights=[1, 1, 2, 4, 5])[0]
                        feedback_count += 1
                        conn.execute(
                            "INSERT INTO feedback (customer_id, product_id, rating, comment, created_at) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (customer_id, pid, rating, COMMENTS[rating], _ts(placed + timedelta(days=7), rng)),
                        )
    return SeedReport(customers, staff, product_id, order_id, feedback_count)

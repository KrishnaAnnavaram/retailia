-- Retailia store schema (SQLite). One schema for accounts and store data, so a
-- customer id means the same thing everywhere. Money is stored in integer cents.

CREATE TABLE IF NOT EXISTS customers (
    customer_id      INTEGER PRIMARY KEY,
    username         TEXT NOT NULL UNIQUE,
    password_hash    TEXT NOT NULL,          -- scrypt, never plaintext
    role             TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'staff')),
    display_name     TEXT NOT NULL,
    email            TEXT NOT NULL UNIQUE,
    shipping_address TEXT,
    city             TEXT,
    failed_logins    INTEGER NOT NULL DEFAULT 0,
    locked_until     TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
    product_id  INTEGER PRIMARY KEY,
    sku         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
    stock       INTEGER NOT NULL CHECK (stock >= 0),
    category_id INTEGER NOT NULL REFERENCES categories (category_id)
);

CREATE TABLE IF NOT EXISTS carts (
    cart_id     INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL UNIQUE REFERENCES customers (customer_id)
);

CREATE TABLE IF NOT EXISTS cart_items (
    cart_id    INTEGER NOT NULL REFERENCES carts (cart_id),
    product_id INTEGER NOT NULL REFERENCES products (product_id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (cart_id, product_id)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers (customer_id),
    status        TEXT NOT NULL CHECK (status IN ('processing', 'shipped', 'delivered', 'cancelled', 'returned')),
    placed_at     TEXT NOT NULL,
    total_cents   INTEGER NOT NULL CHECK (total_cents >= 0),
    tracking_code TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id         INTEGER NOT NULL REFERENCES orders (order_id),
    product_id       INTEGER NOT NULL REFERENCES products (product_id),
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents > 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (customer_id),
    product_id  INTEGER NOT NULL REFERENCES products (product_id),
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment     TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (customer_id, product_id)
);

CREATE INDEX IF NOT EXISTS ix_orders_customer ON orders (customer_id, placed_at);
CREATE INDEX IF NOT EXISTS ix_products_category ON products (category_id);

-- PII-free views: the only objects staff analytics queries may read.
CREATE VIEW IF NOT EXISTS v_catalog AS
SELECT p.product_id, p.sku, p.name, c.name AS category, p.price_cents, p.stock,
       ROUND(AVG(f.rating), 2) AS avg_rating, COUNT(f.feedback_id) AS rating_count
FROM products p
JOIN categories c ON c.category_id = p.category_id
LEFT JOIN feedback f ON f.product_id = p.product_id
GROUP BY p.product_id;

CREATE VIEW IF NOT EXISTS v_product_sales AS
SELECT p.product_id, p.name, c.name AS category,
       COALESCE(SUM(s.quantity), 0) AS units_sold,
       COALESCE(SUM(s.quantity * s.unit_price_cents), 0) AS revenue_cents
FROM products p
JOIN categories c ON c.category_id = p.category_id
LEFT JOIN (
    SELECT oi.product_id, oi.quantity, oi.unit_price_cents
    FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
    WHERE o.status NOT IN ('cancelled', 'returned')
) s ON s.product_id = p.product_id
GROUP BY p.product_id;

CREATE VIEW IF NOT EXISTS v_orders_by_month AS
SELECT substr(placed_at, 1, 7) AS month, status, COUNT(*) AS orders, SUM(total_cents) AS revenue_cents
FROM orders
GROUP BY month, status;

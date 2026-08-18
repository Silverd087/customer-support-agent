-- Sample data across TWO tenants, specifically so you can test that
-- tenant isolation actually holds (query as tenant 1, confirm tenant 2's
-- data never shows up, and vice versa) — not just that the happy path works.

INSERT INTO tenants (name, slug, plan, status) VALUES
    ('Lumen Home', 'lumen-home', 'pro', 'active'),
    ('Bright Kettle Coffee Co.', 'bright-kettle', 'starter', 'active');
-- tenant_id 1 = Lumen Home, tenant_id 2 = Bright Kettle (just to prove isolation)

INSERT INTO customers (tenant_id, email, full_name) VALUES
    (1, 'alex@example.com', 'Alex Rivera'),
    (1, 'jamie@example.com', 'Jamie Chen'),
    (2, 'alex@example.com', 'Alex Rivera');  -- same email as tenant 1's customer, different tenant — must not collide

INSERT INTO products (tenant_id, sku, name, category, price_cents) VALUES
    (1, 'LUM-CAM-01', 'Lumen Indoor Camera', 'camera', 5999),
    (1, 'LUM-THERM-01', 'Lumen Smart Thermostat', 'thermostat', 8999),
    (1, 'LUM-PLUG-02', 'Lumen Smart Plug (2-pack)', 'plug', 2499);

-- Tenant 1 (Lumen Home), Alex: matches knowledge_base/README.md's test question
-- ("What's the status of my order #48213?")
INSERT INTO orders (tenant_id, order_number, customer_id, status, shipping_method, tracking_number, placed_at, shipped_at, eta_date, total_cents)
VALUES (1, 'ORD-48213', 1, 'shipped', 'standard', '1Z999AA10123456784',
        now() - interval '3 days', now() - interval '2 days', current_date + interval '2 days', 5999);

INSERT INTO order_items (tenant_id, order_id, product_id, quantity, unit_price_cents, warranty_months)
VALUES (1, 1, 1, 1, 5999, 24);  -- 24 months: Lumen+ was active at purchase

INSERT INTO subscriptions (tenant_id, customer_id, plan, billing_cycle, status, current_period_start, current_period_end)
VALUES (1, 1, 'individual', 'monthly', 'active', date_trunc('month', now())::date, (date_trunc('month', now()) + interval '1 month')::date);

-- Tenant 1, Jamie: delivered order, no subscription — good compound-refund test case
INSERT INTO orders (tenant_id, order_number, customer_id, status, shipping_method, tracking_number, placed_at, shipped_at, delivered_at, eta_date, total_cents)
VALUES (1, 'ORD-51002', 2, 'delivered', 'expedited', '1Z999AA10198765432',
        now() - interval '10 days', now() - interval '9 days', now() - interval '6 days', current_date - interval '6 days', 8999);

INSERT INTO order_items (tenant_id, order_id, product_id, quantity, unit_price_cents, warranty_months)
VALUES (1, 2, 2, 1, 8999, 12);

-- Tenant 2 (Bright Kettle) has NO products/orders seeded on purpose — the
-- test is that a tenant-1-scoped query for 'ORD-48213' run under tenant 2's
-- context returns nothing, even though the order_number alone isn't
-- globally unique (see UNIQUE(tenant_id, order_number) in schema.sql).

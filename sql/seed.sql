-- Sample data across TWO tenants, specifically so you can test that
-- tenant isolation actually holds (query as tenant 1, confirm tenant 2's
-- data never shows up, and vice versa) — not just that the happy path works.
--
-- IDs are UUIDs, matching src/database/*.py (the ORM models are the source
-- of truth). Hardcoded (not gen_random_uuid()) on purpose — this is test
-- fixture data meant to be referenced by a stable, known id every time you
-- re-seed (e.g. knowledge_base/README.md's "order #48213" test question, or
-- a pytest fixture), not real production data.
-- First hex group marks the "kind" of row for readability while skimming:
-- a... = tenant, b... = customer, c... = product, d... = order_item, f... = order.

INSERT INTO tenants (id, name, slug, plan, status) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'Lumen Home', 'lumen-home', 'pro', 'active'),
    ('a0000000-0000-0000-0000-000000000002', 'Bright Kettle Coffee Co.', 'bright-kettle', 'starter', 'active');
-- tenant a...1 = Lumen Home, tenant a...2 = Bright Kettle (just to prove isolation)

INSERT INTO customers (id, tenant_id, email, full_name) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'alex@example.com', 'Alex Rivera'),
    ('b0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'jamie@example.com', 'Jamie Chen'),
    ('b0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000002', 'alex@example.com', 'Alex Rivera');  -- same email as tenant 1's customer, different tenant — must not collide

INSERT INTO products (id, tenant_id, sku, name, category, price_cents) VALUES
    ('c0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'LUM-CAM-01', 'Lumen Indoor Camera', 'camera', 5999),
    ('c0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'LUM-THERM-01', 'Lumen Smart Thermostat', 'thermostat', 8999),
    ('c0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000001', 'LUM-PLUG-02', 'Lumen Smart Plug (2-pack)', 'plug', 2499);

-- Order id is a UUID surrogate key now; `number` is the human-facing value
-- ('ORD-48213') that customers actually type — see the UniqueConstraint on
-- (tenant_id, number) in database/order.py. Tenant 1 (Lumen Home), Alex:
-- matches knowledge_base/README.md's test question
-- ("What's the status of my order #48213?")
INSERT INTO orders (id, tenant_id, customer_id, number, status, shipping_method, tracking_number, placed_at, shipped_at, eta_date, total_cents)
VALUES ('f0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'ORD-48213', 'shipped', 'standard', '1Z999AA10123456784',
        now() - interval '3 days', now() - interval '2 days', current_date + interval '2 days', 5999);

INSERT INTO order_items (id, tenant_id, order_id, product_id, quantity, unit_price_cents, warranty_months)
VALUES ('d0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'f0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', 1, 5999, 24);  -- 24 months: Lumen+ was active at purchase

INSERT INTO subscriptions (id, tenant_id, customer_id, plan, billing_cycle, status, current_period_start, current_period_end)
VALUES ('e0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'individual', 'monthly', 'active', date_trunc('month', now()), date_trunc('month', now()) + interval '1 month');

-- Tenant 1, Jamie: delivered order, no subscription — good compound-refund test case
INSERT INTO orders (id, tenant_id, customer_id, number, status, shipping_method, tracking_number, placed_at, shipped_at, delivered_at, eta_date, total_cents)
VALUES ('f0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000002', 'ORD-51002', 'delivered', 'expedited', '1Z999AA10198765432',
        now() - interval '10 days', now() - interval '9 days', now() - interval '6 days', current_date - interval '6 days', 8999);

INSERT INTO order_items (id, tenant_id, order_id, product_id, quantity, unit_price_cents, warranty_months)
VALUES ('d0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'f0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000002', 1, 8999, 12);

-- Tenant 2 (Bright Kettle) has NO products/orders seeded on purpose — the
-- test is that a tenant-1-scoped query for order number 'ORD-48213' run
-- under tenant 2's context returns nothing, even though `number` isn't
-- globally unique by itself — only UNIQUE(tenant_id, number) is enforced,
-- so tenant 2 could reuse 'ORD-48213' for a totally different order without
-- colliding, and a lookup must still be scoped correctly to find the right one.

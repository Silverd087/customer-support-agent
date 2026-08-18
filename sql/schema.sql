-- Lumen Home support database schema — multi-tenant.
-- Every business (tenant) using this product gets isolated rows across
-- every table. tenant_id is denormalized onto every table directly
-- (not just reachable via joins) so every query can filter on it without
-- relying on a join being written correctly — see roles.sql for the
-- optional Row-Level Security policies that enforce this at the DB level too.

CREATE TABLE tenants (
    tenant_id   SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,             -- e.g. 'Lumen Home'
    slug        TEXT NOT NULL UNIQUE,      -- e.g. 'lumen-home', used in URLs/config
    plan        TEXT NOT NULL DEFAULT 'trial' CHECK (plan IN ('trial', 'starter', 'pro', 'enterprise')),
    status      TEXT NOT NULL DEFAULT 'trial' CHECK (status IN ('trial', 'active', 'suspended')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customers (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(tenant_id),
    email           TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    household_id    INTEGER REFERENCES customers(id),   -- Lumen+ Family grouping
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)   -- unique per tenant, not globally — two businesses
                                 -- can each have a customer with the same email
);
CREATE INDEX idx_customers_tenant ON customers(tenant_id);

CREATE TABLE products (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(tenant_id),
    sku             TEXT NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN ('camera', 'plug', 'thermostat', 'sensor')),
    price_cents     INTEGER NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (tenant_id, sku)
);
CREATE INDEX idx_products_tenant ON products(tenant_id);

CREATE TABLE orders (
    id              SERIAL PRIMARY KEY,           -- internal surrogate key
    tenant_id       INTEGER NOT NULL REFERENCES tenants(tenant_id),
    order_number    TEXT NOT NULL,                 -- what the customer types, e.g. 'ORD-48213'
    customer_id     INTEGER NOT NULL REFERENCES customers(id),
    status          TEXT NOT NULL CHECK (status IN ('processing', 'shipped', 'delivered', 'cancelled', 'returned')),
    shipping_method TEXT NOT NULL CHECK (shipping_method IN ('standard', 'expedited', 'overnight')),
    tracking_number TEXT,
    placed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    shipped_at      TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    eta_date        DATE,
    total_cents     INTEGER NOT NULL,
    UNIQUE (tenant_id, order_number)   -- 'ORD-48213' only needs to be unique WITHIN a tenant
);
CREATE INDEX idx_orders_tenant ON orders(tenant_id);
CREATE INDEX idx_orders_customer ON orders(customer_id);

CREATE TABLE order_items (
    id               SERIAL PRIMARY KEY,
    tenant_id        INTEGER NOT NULL REFERENCES tenants(tenant_id),   -- denormalized for query safety
    order_id         INTEGER NOT NULL REFERENCES orders(id),
    product_id       INTEGER NOT NULL REFERENCES products(id),
    quantity         INTEGER NOT NULL DEFAULT 1,
    unit_price_cents INTEGER NOT NULL,
    warranty_months  INTEGER NOT NULL DEFAULT 12
);
CREATE INDEX idx_order_items_tenant ON order_items(tenant_id);

CREATE TABLE subscriptions (
    id                    SERIAL PRIMARY KEY,
    tenant_id             INTEGER NOT NULL REFERENCES tenants(tenant_id),
    customer_id           INTEGER NOT NULL REFERENCES customers(id),
    plan                  TEXT NOT NULL CHECK (plan IN ('individual', 'family')),
    billing_cycle         TEXT NOT NULL CHECK (billing_cycle IN ('monthly', 'annual')),
    status                TEXT NOT NULL CHECK (status IN ('active', 'canceled', 'past_due')),
    current_period_start  DATE NOT NULL,
    current_period_end    DATE NOT NULL,
    canceled_at           TIMESTAMPTZ
);
CREATE INDEX idx_subscriptions_tenant ON subscriptions(tenant_id);
CREATE INDEX idx_subscriptions_customer ON subscriptions(customer_id);

CREATE TABLE payments (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(tenant_id),
    customer_id     INTEGER NOT NULL REFERENCES customers(id),
    order_id        INTEGER REFERENCES orders(id),
    subscription_id INTEGER REFERENCES subscriptions(id),
    amount_cents    INTEGER NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'refunded')),
    charged_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (order_id IS NOT NULL OR subscription_id IS NOT NULL)
);
CREATE INDEX idx_payments_tenant ON payments(tenant_id);

CREATE TABLE returns (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(tenant_id),
    order_item_id   INTEGER NOT NULL REFERENCES order_items(id),
    reason          TEXT,
    status          TEXT NOT NULL CHECK (status IN ('requested', 'label_generated', 'received', 'refunded')),
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    refunded_at     TIMESTAMPTZ
);
CREATE INDEX idx_returns_tenant ON returns(tenant_id);

CREATE TABLE warranty_claims (
    id                SERIAL PRIMARY KEY,
    tenant_id         INTEGER NOT NULL REFERENCES tenants(tenant_id),
    order_item_id     INTEGER NOT NULL REFERENCES order_items(id),
    issue_description TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('submitted', 'approved', 'replacement_shipped', 'closed')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_warranty_claims_tenant ON warranty_claims(tenant_id);

-- The ONLY table create_refund_request (agent tool) can write to.
CREATE TABLE pending_refunds (
    id                SERIAL PRIMARY KEY,
    tenant_id         INTEGER NOT NULL REFERENCES tenants(tenant_id),
    order_id          INTEGER NOT NULL REFERENCES orders(id),
    customer_email    TEXT NOT NULL,
    reason            TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review', 'approved', 'rejected')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by       TEXT,
    reviewed_at       TIMESTAMPTZ
);
CREATE INDEX idx_pending_refunds_tenant ON pending_refunds(tenant_id);

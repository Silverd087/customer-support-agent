-- Lumen Home support database schema — multi-tenant.
-- Every business (tenant) using this product gets isolated rows across
-- every table. tenant_id is denormalized onto every table directly
-- (not just reachable via joins) so every query can filter on it without
-- relying on a join being written correctly — see roles.sql for the
-- Row-Level Security policies that enforce this at the DB level too.
--
-- IDs are UUIDs throughout, matching src/database/*.py (the SQLAlchemy
-- models are the source of truth — this file is a readable reference, not
-- what's executed; Base.metadata.create_all() builds the real database).
-- Requires pgcrypto for gen_random_uuid() on Postgres < 13.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,             -- e.g. 'Lumen Home'
    slug        TEXT NOT NULL UNIQUE,      -- e.g. 'lumen-home', used in URLs/config
    plan        TEXT NOT NULL DEFAULT 'trial' CHECK (plan IN ('trial', 'starter', 'pro', 'enterprise')),
    status      TEXT NOT NULL DEFAULT 'trial' CHECK (status IN ('trial', 'active', 'suspended')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    email           TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    household_id    UUID REFERENCES customers(id),   -- Lumen+ Family grouping
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)   -- unique per tenant, not globally — two businesses
                                 -- can each have a customer with the same email
);
CREATE INDEX idx_customers_tenant ON customers(tenant_id);

CREATE TABLE products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    sku             TEXT NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN ('camera', 'plug', 'thermostat', 'sensor')),
    price_cents     INTEGER NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (tenant_id, sku)
);
CREATE INDEX idx_products_tenant ON products(tenant_id);

-- id is a surrogate key; `number` is the human-facing value customers
-- actually type (e.g. 'ORD-48213') — unique within a tenant, not globally.
CREATE TABLE orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    number          TEXT NOT NULL,
    customer_id     UUID NOT NULL REFERENCES customers(id),
    status          TEXT NOT NULL CHECK (status IN ('processing', 'shipped', 'delivered', 'cancelled', 'returned')),
    shipping_method TEXT NOT NULL CHECK (shipping_method IN ('standard', 'expedited', 'overnight')),
    tracking_number TEXT,
    placed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    shipped_at      TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    eta_date        TIMESTAMPTZ,
    total_cents     INTEGER NOT NULL,
    UNIQUE (tenant_id, number)   -- 'ORD-48213' only needs to be unique WITHIN a tenant
);
CREATE INDEX idx_orders_tenant ON orders(tenant_id);
CREATE INDEX idx_orders_customer ON orders(customer_id);

CREATE TABLE order_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id),   -- denormalized for query safety
    order_id         UUID NOT NULL REFERENCES orders(id),
    product_id       UUID NOT NULL REFERENCES products(id),
    quantity         INTEGER NOT NULL DEFAULT 1,
    unit_price_cents INTEGER NOT NULL,
    warranty_months  INTEGER NOT NULL DEFAULT 12
);
CREATE INDEX idx_order_items_tenant ON order_items(tenant_id);

CREATE TABLE subscriptions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants(id),
    customer_id           UUID NOT NULL REFERENCES customers(id),
    plan                  TEXT NOT NULL CHECK (plan IN ('individual', 'family')),
    billing_cycle         TEXT NOT NULL CHECK (billing_cycle IN ('monthly', 'annually')),
    status                TEXT NOT NULL CHECK (status IN ('active', 'cancelled', 'past_due')),
    current_period_start  TIMESTAMPTZ,
    current_period_end    TIMESTAMPTZ,
    cancelled_at          TIMESTAMPTZ
);
CREATE INDEX idx_subscriptions_tenant ON subscriptions(tenant_id);
CREATE INDEX idx_subscriptions_customer ON subscriptions(customer_id);

CREATE TABLE payments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    customer_id     UUID NOT NULL REFERENCES customers(id),
    order_id        UUID REFERENCES orders(id),
    subscription_id UUID REFERENCES subscriptions(id),
    amount_cents    INTEGER NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'refunded')),
    charged_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (order_id IS NOT NULL OR subscription_id IS NOT NULL)
);
CREATE INDEX idx_payments_tenant ON payments(tenant_id);

CREATE TABLE order_returns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    order_item_id   UUID NOT NULL REFERENCES order_items(id),
    reason          TEXT,
    status          TEXT NOT NULL CHECK (status IN ('requested', 'label_generated', 'received', 'refunded')),
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    refunded_at     TIMESTAMPTZ
);
CREATE INDEX idx_order_returns_tenant ON order_returns(tenant_id);

CREATE TABLE warranty_claims (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants(id),
    order_item_id     UUID NOT NULL REFERENCES order_items(id),
    issue_description TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('submitted', 'approved', 'replacement_shipped', 'closed')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_warranty_claims_tenant ON warranty_claims(tenant_id);

-- The ONLY table create_refund_request (agent tool) can write to.
CREATE TABLE pending_refunds (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants(id),
    order_id          UUID NOT NULL REFERENCES orders(id),
    customer_email    TEXT NOT NULL,
    reason            TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review', 'approved', 'rejected')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by       TEXT,
    reviewed_at       TIMESTAMPTZ
);
CREATE INDEX idx_pending_refunds_tenant ON pending_refunds(tenant_id);

-- The ONLY table escalate_to_human (agent tool) can write to. thread_id ties
-- back to the LangGraph checkpointer so a human can pull the full
-- conversation, not just the summary. status/resolved_* set up Sprint 15's
-- "paused for human" flag and live escalation view for free.
CREATE TABLE escalations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    thread_id       TEXT NOT NULL,
    channel         TEXT NOT NULL CHECK (channel IN ('web', 'whatsapp', 'email', 'voice')),
    customer_email  TEXT,   -- nullable: not always known yet at escalation time (e.g. anonymous web chat)
    summary         TEXT NOT NULL,
    reason          TEXT NOT NULL CHECK (reason IN ('customer_requested', 'low_confidence', 'security_sensitive')),
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_by     TEXT,
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX idx_escalations_tenant ON escalations(tenant_id);
CREATE INDEX idx_escalations_tenant_status ON escalations(tenant_id, status);   -- Sprint 15's "show me open escalations"

-- Tracks Gmail drafts the agent has created, pending a human's approval to
-- actually send. The conversational Gmail specialist only ever inserts a
-- 'pending_review' row here (create_draft) — it never sends. A separate,
-- human-driven approval process (outside the LangGraph conversation
-- entirely) is the only thing that transitions a row to 'approved'/'sent'
-- and is the only actor that actually calls Gmail's send.
CREATE TABLE pending_email_sends (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    thread_id       TEXT NOT NULL,          -- LangGraph conversation thread, for traceability
    gmail_draft_id  TEXT NOT NULL,          -- the actual Gmail API draft id — what gets sent
    customer_email  TEXT NOT NULL,
    subject         TEXT NOT NULL,          -- so a human can triage without opening Gmail first
    status          TEXT NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review', 'approved', 'rejected', 'sent')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by     TEXT,
    reviewed_at     TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ
);
CREATE INDEX idx_pending_email_sends_tenant ON pending_email_sends(tenant_id);
CREATE INDEX idx_pending_email_sends_tenant_status ON pending_email_sends(tenant_id, status);

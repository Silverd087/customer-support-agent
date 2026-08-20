-- Two roles for the DB specialist's two tools, per guide §7's non-negotiable
-- rules — plus, now that this is multi-tenant, Row-Level Security (RLS) as a
-- second, DB-enforced layer of tenant isolation on top of application-level
-- `WHERE tenant_id = ...` filtering. The idea: even if a tool's query ever
-- forgot the tenant_id filter (a bug, not a hypothetical — this is the single
-- most common multi-tenant SaaS vulnerability), RLS still blocks cross-tenant
-- reads/writes at the database itself.
--
-- Replace passwords before running anywhere real; these are placeholders.

-- get_order_status: read-only, nothing else.
CREATE ROLE agent_read LOGIN PASSWORD 'change_me';
GRANT CONNECT ON DATABASE lumen_support TO agent_read;
GRANT USAGE ON SCHEMA public TO agent_read;
GRANT SELECT ON customers, orders, order_items, products, subscriptions, order_returns, warranty_claims
    TO agent_read;

-- create_refund_request: can verify the order exists, can only INSERT into
-- pending_refunds — cannot touch orders, payments, or returns directly.
CREATE ROLE agent_refund_writer LOGIN PASSWORD 'change_me';
GRANT CONNECT ON DATABASE lumen_support TO agent_refund_writer;
GRANT USAGE ON SCHEMA public TO agent_refund_writer;
GRANT SELECT ON customers TO agent_refund_writer;
GRANT SELECT ON orders TO agent_refund_writer;
GRANT INSERT ON pending_refunds TO agent_refund_writer;
-- No sequence grant needed — pending_refunds.id is UUID DEFAULT
-- gen_random_uuid(), not SERIAL, so there's no backing sequence.

-- Also used by escalate_to_human — reusing this role rather than a
-- dedicated one, since it already has a wired-up engine/connection.
-- Trade-off: this role now spans multiple unrelated write paths (refunds,
-- escalations, and below, email drafts) instead of being narrowly scoped
-- to one. Fine for now; split into per-purpose roles later if that starts
-- to matter.
GRANT INSERT ON escalations TO agent_refund_writer;

-- create_draft (Gmail specialist): inserts a pending_review row here.
-- This role never gets UPDATE on this table — it can create a pending
-- send request, but only the human_reviewer role below can approve or
-- mark one sent. That split is what actually enforces "no send without a
-- human", not just a prompt instruction.
GRANT INSERT ON pending_email_sends TO agent_refund_writer;

-- The human-driven approval process — deliberately NOT used by any LLM
-- tool. Whatever small script/endpoint a person runs to review and
-- approve/reject pending drafts connects as this role, not as
-- agent_refund_writer. Needs SELECT to list pending rows and UPDATE to
-- transition status/reviewed_by/reviewed_at/sent_at — no INSERT, no DELETE.
CREATE ROLE human_reviewer LOGIN PASSWORD 'change_me';
GRANT CONNECT ON DATABASE lumen_support TO human_reviewer;
GRANT USAGE ON SCHEMA public TO human_reviewer;
GRANT SELECT, UPDATE ON pending_email_sends TO human_reviewer;

-- --- Row-Level Security: enable per table, one policy per table ---
-- Application code sets the current tenant once per connection/request:
--   SET app.current_tenant_id = '<tenant_id>';
-- before running any query. Every query on these tables is then
-- automatically filtered to that tenant, regardless of what WHERE clause
-- the application code did or didn't include.

ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON customers
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON orders
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON order_items
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON products
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON subscriptions
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

ALTER TABLE order_returns ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON order_returns
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

ALTER TABLE warranty_claims ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON warranty_claims
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

ALTER TABLE pending_refunds ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON pending_refunds
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

ALTER TABLE escalations ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON escalations
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

ALTER TABLE pending_email_sends ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON pending_email_sends
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Both agent roles must NOT have BYPASSRLS (the default for non-superuser
-- roles already excludes it — just don't grant it).

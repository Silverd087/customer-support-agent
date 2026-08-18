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
GRANT SELECT ON customers, orders, order_items, products, subscriptions, returns, warranty_claims
    TO agent_read;

-- create_refund_request: can verify the order exists, can only INSERT into
-- pending_refunds — cannot touch orders, payments, or returns directly.
CREATE ROLE agent_refund_writer LOGIN PASSWORD 'change_me';
GRANT CONNECT ON DATABASE lumen_support TO agent_refund_writer;
GRANT USAGE ON SCHEMA public TO agent_refund_writer;
GRANT SELECT ON orders TO agent_refund_writer;
GRANT INSERT ON pending_refunds TO agent_refund_writer;
GRANT USAGE, SELECT ON SEQUENCE pending_refunds_id_seq TO agent_refund_writer;

-- --- Row-Level Security: enable per table, one policy per table ---
-- Application code sets the current tenant once per connection/request:
--   SET app.current_tenant_id = '<tenant_id>';
-- before running any query. Every query on these tables is then
-- automatically filtered to that tenant, regardless of what WHERE clause
-- the application code did or didn't include.

ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON customers
    USING (tenant_id = current_setting('app.current_tenant_id')::int);

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON orders
    USING (tenant_id = current_setting('app.current_tenant_id')::int);

ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON order_items
    USING (tenant_id = current_setting('app.current_tenant_id')::int);

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON products
    USING (tenant_id = current_setting('app.current_tenant_id')::int);

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON subscriptions
    USING (tenant_id = current_setting('app.current_tenant_id')::int);

ALTER TABLE returns ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON returns
    USING (tenant_id = current_setting('app.current_tenant_id')::int);

ALTER TABLE warranty_claims ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON warranty_claims
    USING (tenant_id = current_setting('app.current_tenant_id')::int);

ALTER TABLE pending_refunds ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON pending_refunds
    USING (tenant_id = current_setting('app.current_tenant_id')::int);

-- Both agent roles must NOT have BYPASSRLS (the default for non-superuser
-- roles already excludes it — just don't grant it).

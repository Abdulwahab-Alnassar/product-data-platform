CREATE TABLE IF NOT EXISTS catalog_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision BIGINT NOT NULL);
INSERT INTO catalog_state(singleton, revision) VALUES (1, 0) ON CONFLICT(singleton) DO NOTHING;
CREATE TABLE IF NOT EXISTS catalog_changes (
    change_id BIGINT PRIMARY KEY, product_id TEXT NOT NULL,
    operation TEXT NOT NULL, changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory (
    product_id TEXT PRIMARY KEY REFERENCES products(product_id) ON DELETE CASCADE,
    stock_quantity BIGINT CHECK(stock_quantity >= 0)
);
CREATE TABLE IF NOT EXISTS product_versions (product_id TEXT PRIMARY KEY, source_version BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL,
    product_id TEXT NOT NULL, source_version BIGINT NOT NULL,
    outcome TEXT NOT NULL
);

-- A single revision row serializes commits, so polling cannot skip a late commit
-- the way a sequence-only cursor can.
CREATE OR REPLACE FUNCTION capture_catalog_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE next_revision BIGINT; affected_id TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN affected_id := OLD.product_id;
    ELSE affected_id := NEW.product_id;
    END IF;
    UPDATE catalog_state SET revision=revision+1 WHERE singleton=1 RETURNING revision INTO next_revision;
    INSERT INTO catalog_changes(change_id, product_id, operation, changed_at)
    VALUES(next_revision, affected_id, TG_TABLE_NAME || '_' || lower(TG_OP),
           to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'));
    RETURN NULL;
END;
$$;

CREATE OR REPLACE TRIGGER capture_products AFTER INSERT OR UPDATE OR DELETE ON products
FOR EACH ROW EXECUTE FUNCTION capture_catalog_change();

CREATE OR REPLACE TRIGGER capture_inventory AFTER INSERT OR UPDATE OR DELETE ON inventory
FOR EACH ROW EXECUTE FUNCTION capture_catalog_change();

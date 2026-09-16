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

CREATE TRIGGER IF NOT EXISTS capture_products_insert AFTER INSERT ON products
BEGIN
    UPDATE catalog_state SET revision=revision+1 WHERE singleton=1;
    INSERT INTO catalog_changes(change_id, product_id, operation, changed_at)
    SELECT revision, NEW.product_id, 'products_insert', strftime('%Y-%m-%dT%H:%M:%fZ','now')
    FROM catalog_state WHERE singleton=1;
END;

CREATE TRIGGER IF NOT EXISTS capture_products_update AFTER UPDATE ON products
BEGIN
    UPDATE catalog_state SET revision=revision+1 WHERE singleton=1;
    INSERT INTO catalog_changes(change_id, product_id, operation, changed_at)
    SELECT revision, NEW.product_id, 'products_update', strftime('%Y-%m-%dT%H:%M:%fZ','now')
    FROM catalog_state WHERE singleton=1;
END;

CREATE TRIGGER IF NOT EXISTS capture_products_delete AFTER DELETE ON products
BEGIN
    UPDATE catalog_state SET revision=revision+1 WHERE singleton=1;
    INSERT INTO catalog_changes(change_id, product_id, operation, changed_at)
    SELECT revision, OLD.product_id, 'products_delete', strftime('%Y-%m-%dT%H:%M:%fZ','now')
    FROM catalog_state WHERE singleton=1;
END;

CREATE TRIGGER IF NOT EXISTS capture_inventory_insert AFTER INSERT ON inventory
BEGIN
    UPDATE catalog_state SET revision=revision+1 WHERE singleton=1;
    INSERT INTO catalog_changes(change_id, product_id, operation, changed_at)
    SELECT revision, NEW.product_id, 'inventory_insert', strftime('%Y-%m-%dT%H:%M:%fZ','now')
    FROM catalog_state WHERE singleton=1;
END;

CREATE TRIGGER IF NOT EXISTS capture_inventory_update AFTER UPDATE ON inventory
BEGIN
    UPDATE catalog_state SET revision=revision+1 WHERE singleton=1;
    INSERT INTO catalog_changes(change_id, product_id, operation, changed_at)
    SELECT revision, NEW.product_id, 'inventory_update', strftime('%Y-%m-%dT%H:%M:%fZ','now')
    FROM catalog_state WHERE singleton=1;
END;

CREATE TRIGGER IF NOT EXISTS capture_inventory_delete AFTER DELETE ON inventory
BEGIN
    UPDATE catalog_state SET revision=revision+1 WHERE singleton=1;
    INSERT INTO catalog_changes(change_id, product_id, operation, changed_at)
    SELECT revision, OLD.product_id, 'inventory_delete', strftime('%Y-%m-%dT%H:%M:%fZ','now')
    FROM catalog_state WHERE singleton=1;
END;

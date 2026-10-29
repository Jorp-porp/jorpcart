CREATE TABLE IF NOT EXISTS deals (
    id           BIGSERIAL PRIMARY KEY,
    store        TEXT NOT NULL,
    store_location TEXT,
    product_name TEXT NOT NULL,
    price        NUMERIC(10,2),
    unit_price   NUMERIC(10,4),
    unit        TEXT,
    deal_text    TEXT,
    valid_from   DATE,
    valid_to     DATE,
    source       TEXT NOT NULL,
    raw          JSONB,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (store, product_name, deal_text, valid_from)
);

CREATE INDEX IF NOT EXISTS idx_deals_store_dates
    ON deals (store, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_deals_name_trgm
    ON deals USING gin (product_name gin_trgm_ops);

CREATE EXTENSION IF NOT EXISTS pg_trgm;

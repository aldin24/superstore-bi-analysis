-- ============================================================
-- Superstore Star Schema — DDL
-- Conventions: fact_ prefix, dim_ prefix, <thing>_key PKs/FKs
-- All surrogate PKs are SERIAL except dim_date (YYYYMMDD int)
-- ============================================================

-- --------------------------------------------------------
-- dim_date
-- Role-playing: referenced as order_date_key AND ship_date_key
-- Key is YYYYMMDD integer (Kimball standard)
-- --------------------------------------------------------
CREATE TABLE dim_date (
    date_key        INTEGER      PRIMARY KEY,       -- YYYYMMDD e.g. 20160108
    full_date       DATE         NOT NULL UNIQUE,
    day_of_week     SMALLINT     NOT NULL,          -- ISO: 1=Mon … 7=Sun
    day_name        TEXT         NOT NULL,
    day_of_month    SMALLINT     NOT NULL,
    day_of_year     SMALLINT     NOT NULL,
    week_of_year    SMALLINT     NOT NULL,
    month_num       SMALLINT     NOT NULL,
    month_name      TEXT         NOT NULL,
    quarter         SMALLINT     NOT NULL,
    year            SMALLINT     NOT NULL,
    is_weekend      BOOLEAN      NOT NULL
);

COMMENT ON TABLE  dim_date              IS 'Calendar dimension — role-played as order date and ship date';
COMMENT ON COLUMN dim_date.date_key     IS 'YYYYMMDD integer surrogate key';
COMMENT ON COLUMN dim_date.week_of_year IS 'ISO week number (1–53)';


-- --------------------------------------------------------
-- dim_customer
-- --------------------------------------------------------
CREATE TABLE dim_customer (
    customer_key    SERIAL       PRIMARY KEY,
    customer_id     TEXT         NOT NULL UNIQUE,   -- natural key e.g. CG-12520
    customer_name   TEXT         NOT NULL,
    segment         TEXT         NOT NULL            -- Consumer | Corporate | Home Office
);

COMMENT ON TABLE  dim_customer           IS 'Customers and their segment';
COMMENT ON COLUMN dim_customer.segment   IS 'Consumer, Corporate, or Home Office';


-- --------------------------------------------------------
-- dim_product
-- NOTE: product_id is NOT a clean natural key — 32 IDs map to multiple names in source.
--       Natural key is composite (product_id, product_name).
-- --------------------------------------------------------
CREATE TABLE dim_product (
    product_key     SERIAL       PRIMARY KEY,
    product_id      TEXT         NOT NULL,          -- source key e.g. FUR-BO-10001798
    product_name    TEXT         NOT NULL,
    category        TEXT         NOT NULL,          -- Furniture | Office Supplies | Technology
    sub_category    TEXT         NOT NULL,          -- 17 distinct values
    UNIQUE (product_id, product_name)               -- ETL upserts on (product_id, product_name)
);

COMMENT ON TABLE  dim_product            IS 'Products with their category hierarchy';
COMMENT ON COLUMN dim_product.product_id IS 'Not unique alone — 32 IDs map to multiple names in source; use (product_id, product_name) as the natural key';
COMMENT ON COLUMN dim_product.category   IS 'Furniture, Office Supplies, or Technology';


-- --------------------------------------------------------
-- dim_geography
-- Grain: postal_code (631 distinct); hierarchy: postal→city→state→region→country
-- NOTE: postal 92024 maps to two cities in source ("Encinitas" + "San Diego", both CA)
--       so UNIQUE(postal_code) alone would fail — composite key used instead.
-- --------------------------------------------------------
CREATE TABLE dim_geography (
    geography_key   SERIAL       PRIMARY KEY,
    postal_code     TEXT         NOT NULL,          -- TEXT to preserve leading zeros
    city            TEXT         NOT NULL,
    state           TEXT         NOT NULL,
    region          TEXT         NOT NULL,          -- East | West | Central | South
    country         TEXT         NOT NULL DEFAULT 'United States',
    UNIQUE (postal_code, city)                      -- ETL looks up by (postal_code, city)
);

COMMENT ON TABLE  dim_geography              IS 'Geographic hierarchy: postal → city → state → region → country';
COMMENT ON COLUMN dim_geography.postal_code  IS 'TEXT to preserve leading zeros; not unique alone — postal 92024 maps to two cities in source';


-- --------------------------------------------------------
-- dim_ship_mode
-- --------------------------------------------------------
CREATE TABLE dim_ship_mode (
    ship_mode_key   SERIAL       PRIMARY KEY,
    ship_mode       TEXT         NOT NULL UNIQUE    -- 4 values
);

COMMENT ON TABLE dim_ship_mode IS 'Shipping mode lookup (4 values: Standard Class, Second Class, First Class, Same Day)';


-- --------------------------------------------------------
-- fact_order_lines
-- Grain: one row per order line item (order_id + product)
-- --------------------------------------------------------
CREATE TABLE fact_order_lines (
    order_line_key  SERIAL          PRIMARY KEY,
    source_row_id   INTEGER         NOT NULL UNIQUE,            -- CSV Row ID; ETL upsert anchor
    order_id        TEXT            NOT NULL,                   -- degenerate dimension
    order_date_key  INTEGER         NOT NULL
                      REFERENCES dim_date(date_key),
    ship_date_key   INTEGER         NOT NULL
                      REFERENCES dim_date(date_key),
    customer_key    INTEGER         NOT NULL
                      REFERENCES dim_customer(customer_key),
    product_key     INTEGER         NOT NULL
                      REFERENCES dim_product(product_key),
    geography_key   INTEGER         NOT NULL
                      REFERENCES dim_geography(geography_key),
    ship_mode_key   INTEGER         NOT NULL
                      REFERENCES dim_ship_mode(ship_mode_key),
    sales           NUMERIC(12,4)   NOT NULL,
    quantity        SMALLINT        NOT NULL,
    discount        NUMERIC(5,4)    NOT NULL,
    profit          NUMERIC(12,4)   NOT NULL,
    days_to_ship    SMALLINT        NOT NULL        -- ship_date - order_date, pre-computed
);

COMMENT ON TABLE  fact_order_lines               IS 'Grain: one row per order line item. Measures: sales, quantity, discount, profit.';
COMMENT ON COLUMN fact_order_lines.source_row_id IS 'CSV Row ID (1–9994) — idempotency anchor for ON CONFLICT (source_row_id) DO UPDATE';
COMMENT ON COLUMN fact_order_lines.order_id      IS 'Degenerate dimension — groups line items belonging to the same order';
COMMENT ON COLUMN fact_order_lines.days_to_ship  IS 'Pre-computed (ship_date - order_date) to avoid date arithmetic in every query';
COMMENT ON COLUMN fact_order_lines.discount      IS 'Fractional discount (0.0–0.8), not percentage';

-- Indexes for common BI filter patterns
CREATE INDEX idx_fol_order_date  ON fact_order_lines (order_date_key);
CREATE INDEX idx_fol_ship_date   ON fact_order_lines (ship_date_key);
CREATE INDEX idx_fol_customer    ON fact_order_lines (customer_key);
CREATE INDEX idx_fol_product     ON fact_order_lines (product_key);
CREATE INDEX idx_fol_geography   ON fact_order_lines (geography_key);
CREATE INDEX idx_fol_order_id    ON fact_order_lines (order_id);

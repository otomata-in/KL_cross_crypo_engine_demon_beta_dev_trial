-- ============================================================
-- TimescaleDB Schema for Arbitrage Opportunities
-- ============================================================
-- Runs on first container startup via docker-entrypoint-initdb.d

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create the opportunities table
CREATE TABLE IF NOT EXISTS opportunities (
    timestamp_utc   TIMESTAMPTZ       NOT NULL,
    token           VARCHAR(10)       NOT NULL,
    ex_buy          VARCHAR(12)       NOT NULL,
    ex_sell         VARCHAR(12)       NOT NULL,
    direction       VARCHAR(30)       NOT NULL,
    gross_spread    DOUBLE PRECISION  NOT NULL,
    net_spread      DOUBLE PRECISION  NOT NULL,
    pair_fees       DOUBLE PRECISION  NOT NULL,
    buy_ask         DOUBLE PRECISION  NOT NULL,
    sell_bid        DOUBLE PRECISION  NOT NULL,
    usdt_usdc_rate  DOUBLE PRECISION  NOT NULL DEFAULT 1.0
);

-- Convert to hypertable, partitioned by timestamp (7-day chunks)
SELECT create_hypertable('opportunities', 'timestamp_utc',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Index: token lookups for analytics (top coins by max net spread)
CREATE INDEX IF NOT EXISTS idx_opp_token
    ON opportunities (token, timestamp_utc DESC);

-- Index: route analytics (group by exchange pair)
CREATE INDEX IF NOT EXISTS idx_opp_route
    ON opportunities (ex_buy, ex_sell, timestamp_utc DESC);

-- Index: net spread filtering (find profitable opportunities fast)
CREATE INDEX IF NOT EXISTS idx_opp_net_spread
    ON opportunities (net_spread DESC, timestamp_utc DESC);

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

-- ============================================================
-- Orders Table — Trade Execution Tracking
-- ============================================================

CREATE TABLE IF NOT EXISTS orders (
    created_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ,
    order_id      VARCHAR(20)       NOT NULL,
    trade_id      VARCHAR(20)       NOT NULL DEFAULT '',
    exchange      VARCHAR(12)       NOT NULL,
    side          VARCHAR(4)        NOT NULL,   -- 'buy' or 'sell'
    symbol        VARCHAR(20)       NOT NULL,   -- e.g. "SOL/USDT"
    qty           DOUBLE PRECISION  NOT NULL,
    price         DOUBLE PRECISION  NOT NULL,
    status        VARCHAR(10)       NOT NULL DEFAULT 'pending',
    filled_qty    DOUBLE PRECISION  NOT NULL DEFAULT 0,
    filled_price  DOUBLE PRECISION  NOT NULL DEFAULT 0,
    fee           DOUBLE PRECISION  NOT NULL DEFAULT 0,
    net_pnl       DOUBLE PRECISION,
    is_mock       BOOLEAN           NOT NULL DEFAULT TRUE,
    error         TEXT
);

-- Convert to hypertable (7-day chunks)
SELECT create_hypertable('orders', 'created_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Index: order lookup by order_id
CREATE INDEX IF NOT EXISTS idx_order_id
    ON orders (order_id);

-- Index: trade correlation (find both legs of a trade)
CREATE INDEX IF NOT EXISTS idx_order_trade_id
    ON orders (trade_id, created_at DESC);

-- Index: open orders
CREATE INDEX IF NOT EXISTS idx_order_status
    ON orders (status, created_at DESC);

-- ============================================================
-- Trade Groups Table — Linking Simultaneous Arbitrage Legs
-- ============================================================

CREATE TABLE IF NOT EXISTS trade_groups (
    trade_id      VARCHAR(20)       PRIMARY KEY,
    created_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    token         VARCHAR(10)       NOT NULL,
    route         VARCHAR(30)       NOT NULL,
    target_spread DOUBLE PRECISION  NOT NULL,
    status        VARCHAR(20)       NOT NULL DEFAULT 'executing',
    realized_pnl  DOUBLE PRECISION,
    is_mock       BOOLEAN           NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_trade_group_status
    ON trade_groups (status, created_at DESC);

-- ============================================================
-- Rebalance Transfers Table — Tracking Solana Inventory Moves
-- ============================================================

CREATE TABLE IF NOT EXISTS rebalance_transfers (
    transfer_id   VARCHAR(40)       PRIMARY KEY,
    created_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ,
    asset         VARCHAR(10)       NOT NULL,
    amount        DOUBLE PRECISION  NOT NULL,
    source_ex     VARCHAR(12)       NOT NULL,
    dest_ex       VARCHAR(12)       NOT NULL,
    status        VARCHAR(20)       NOT NULL DEFAULT 'pending',
    tx_hash       TEXT,
    is_mock       BOOLEAN           NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_rebalance_status
    ON rebalance_transfers (status, created_at DESC);

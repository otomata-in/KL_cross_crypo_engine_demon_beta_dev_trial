"""
db_service.py — TimescaleDB Operations for Arbitrage Bot
=========================================================
Replaces CSV read/write operations with SQL queries against TimescaleDB.
All functions are async and use the connection pool from db.py.

This module mirrors the CSV operations in ws_server.py:
  - insert_opportunity()   → replaces OpportunityLogger.log()
  - get_recent()           → replaces deque-based CSV tail read
  - run_analytics_db()     → replaces run_analytics() full CSV scan
  - reset_opportunities()  → replaces reset_logs() CSV truncate
"""

from datetime import datetime, timezone, timedelta
from db import get_pool


# ── Write ────────────────────────────────────────────────────────

async def insert_opportunity(record: dict) -> bool:
    """
    Insert a single opportunity record into TimescaleDB.
    
    Args:
        record: dict with keys matching the CSV columns:
            timestamp_utc, token, ex_buy, ex_sell, direction,
            gross_spread_pct, net_spread_pct, pair_fees_pct,
            buy_ask, sell_bid, usdt_usdc_rate
    
    Returns:
        True if inserted successfully, False on error.
    """
    pool = get_pool()
    if not pool:
        return False

    try:
        # Parse the ISO timestamp string into a proper datetime
        ts_str = record.get("timestamp_utc", "")
        if isinstance(ts_str, str):
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            ts = ts_str

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO opportunities (
                    timestamp_utc, token, ex_buy, ex_sell, direction,
                    gross_spread, net_spread, pair_fees,
                    buy_ask, sell_bid, usdt_usdc_rate
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                ts,
                str(record.get("token", "")),
                str(record.get("ex_buy", "")),
                str(record.get("ex_sell", "")),
                str(record.get("direction", "")),
                float(record.get("gross_spread_pct", 0)),
                float(record.get("net_spread_pct", 0)),
                float(record.get("pair_fees_pct", 0)),
                float(record.get("buy_ask", 0)),
                float(record.get("sell_bid", 0)),
                float(record.get("usdt_usdc_rate", 1.0)),
            )
        return True
    except Exception as e:
        print(f"[db_service] Insert error: {e}")
        return False


# ── Read: Recent Opportunities ───────────────────────────────────

async def get_recent(limit: int = 100) -> list[dict]:
    """
    Fetch the most recent N opportunities from TimescaleDB.
    Returns list of dicts matching the CSV column names (for frontend compatibility).
    """
    pool = get_pool()
    if not pool:
        return []

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    timestamp_utc, token, ex_buy, ex_sell, direction,
                    gross_spread AS gross_spread_pct,
                    net_spread AS net_spread_pct,
                    pair_fees AS pair_fees_pct,
                    buy_ask, sell_bid, usdt_usdc_rate
                FROM opportunities
                ORDER BY timestamp_utc DESC
                LIMIT $1
                """,
                limit,
            )
            # Convert asyncpg Record objects to plain dicts with string values
            # (matching the CSV reader output format the frontend expects)
            return [
                {
                    "timestamp_utc": row["timestamp_utc"].isoformat(),
                    "token": row["token"],
                    "ex_buy": row["ex_buy"],
                    "ex_sell": row["ex_sell"],
                    "direction": row["direction"],
                    "gross_spread_pct": str(row["gross_spread_pct"]),
                    "net_spread_pct": str(row["net_spread_pct"]),
                    "pair_fees_pct": str(row["pair_fees_pct"]),
                    "buy_ask": str(row["buy_ask"]),
                    "sell_bid": str(row["sell_bid"]),
                    "usdt_usdc_rate": str(row["usdt_usdc_rate"]),
                }
                for row in rows
            ]
    except Exception as e:
        print(f"[db_service] get_recent error: {e}")
        return []


# ── Read: Analytics ──────────────────────────────────────────────

async def run_analytics_db() -> dict:
    """
    Compute analytics from TimescaleDB using optimized SQL queries.
    Returns the same structure as the CSV-based run_analytics():
    {
        "top_coins": [{"token", "count", "best_route", "max_net"}, ...],
        "peak_hour": ("02:00 PM", 1234) or None,
        "peak_day": ("Monday", 567) or None,
        "total_opps": int
    }
    """
    pool = get_pool()
    if not pool:
        return {"top_coins": [], "peak_hour": None, "peak_day": None, "total_opps": 0}

    try:
        async with pool.acquire() as conn:
            # ── Total count ──────────────────────────────────
            total_opps = await conn.fetchval("SELECT COUNT(*) FROM opportunities")

            if total_opps == 0:
                return {"top_coins": [], "peak_hour": None, "peak_day": None, "total_opps": 0}

            # ── Top 5 coins by max net spread ────────────────
            top_rows = await conn.fetch(
                """
                SELECT token,
                       COUNT(*) AS count,
                       MAX(net_spread) AS max_net
                FROM opportunities
                GROUP BY token
                ORDER BY max_net DESC
                LIMIT 5
                """
            )

            # ── Best route per token (for top 5) ─────────────
            top_tokens = [r["token"] for r in top_rows]
            route_rows = await conn.fetch(
                """
                SELECT token, ex_buy || '->' || ex_sell AS route, COUNT(*) AS cnt
                FROM opportunities
                WHERE token = ANY($1)
                GROUP BY token, ex_buy, ex_sell
                ORDER BY token, cnt DESC
                """,
                top_tokens,
            )

            # Build best route lookup: {token: route_string}
            best_routes = {}
            for row in route_rows:
                t = row["token"]
                if t not in best_routes:
                    best_routes[t] = row["route"]

            top_coins_data = [
                {
                    "token": r["token"],
                    "count": r["count"],
                    "best_route": best_routes.get(r["token"]),
                    "max_net": round(r["max_net"], 4),
                }
                for r in top_rows
            ]

            # ── Peak hour (IST = UTC+5:30) ───────────────────
            peak_hour_row = await conn.fetchrow(
                """
                SELECT to_char(
                    date_trunc('hour', timestamp_utc AT TIME ZONE 'Asia/Kolkata'),
                    'HH12:00 AM'
                ) AS hour_ist,
                COUNT(*) AS cnt
                FROM opportunities
                GROUP BY 1
                ORDER BY cnt DESC
                LIMIT 1
                """
            )
            peak_hour = None
            if peak_hour_row:
                # Format to match CSV output: "02:00 PM" style
                hour_str = peak_hour_row["hour_ist"].strip().upper()
                peak_hour = (hour_str, peak_hour_row["cnt"])

            # ── Peak day ─────────────────────────────────────
            peak_day_row = await conn.fetchrow(
                """
                SELECT to_char(
                    timestamp_utc AT TIME ZONE 'Asia/Kolkata', 'Day'
                ) AS day_name,
                COUNT(*) AS cnt
                FROM opportunities
                GROUP BY 1
                ORDER BY cnt DESC
                LIMIT 1
                """
            )
            peak_day = None
            if peak_day_row:
                day_str = peak_day_row["day_name"].strip()
                peak_day = (day_str, peak_day_row["cnt"])

            return {
                "top_coins": top_coins_data,
                "peak_hour": peak_hour,
                "peak_day": peak_day,
                "total_opps": total_opps,
            }

    except Exception as e:
        print(f"[db_service] Analytics error: {e}")
        return {"top_coins": [], "peak_hour": None, "peak_day": None, "total_opps": 0}


# ── Reset ────────────────────────────────────────────────────────

async def reset_opportunities() -> bool:
    """Truncate all opportunity records from TimescaleDB."""
    pool = get_pool()
    if not pool:
        return False

    try:
        async with pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE opportunities")
        print("[db_service] Opportunities table truncated")
        return True
    except Exception as e:
        print(f"[db_service] Reset error: {e}")
        return False

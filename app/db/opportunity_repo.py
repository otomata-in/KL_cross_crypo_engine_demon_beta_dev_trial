"""
app/db/opportunity_repo.py — Opportunity Repository
=====================================================
CRUD operations for the `opportunities` hypertable.

All functions are async and use the shared connection pool.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional

from app.db.pool import get_pool
from app.models.opportunity import OPPORTUNITY_INSERT_SQL


async def insert(record: dict) -> None:
    """
    Insert a single opportunity record into TimescaleDB.

    Args:
        record: Dict with keys matching OPPORTUNITY_COLUMNS.
    """
    pool = get_pool()
    if pool is None:
        return

    ts = record["timestamp_utc"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))

    await pool.execute(
        OPPORTUNITY_INSERT_SQL,
        ts,
        record["token"],
        record["ex_buy"],
        record["ex_sell"],
        record["direction"],
        float(record["gross_spread_pct"]),
        float(record["net_spread_pct"]),
        float(record["pair_fees_pct"]),
        float(record["buy_ask"]),
        float(record["sell_bid"]),
        float(record.get("usdt_usdc_rate", 1.0)),
    )


async def get_recent(limit: int = 100) -> List[dict]:
    """
    Fetch the most recent N opportunities from TimescaleDB.
    Returns list of dicts matching the column names (for frontend compatibility).
    """
    pool = get_pool()
    if pool is None:
        return []

    rows = await pool.fetch(
        """
        SELECT timestamp_utc, token, ex_buy, ex_sell, direction,
               gross_spread_pct, net_spread_pct, pair_fees_pct,
               buy_ask, sell_bid, usdt_usdc_rate
        FROM opportunities
        ORDER BY timestamp_utc DESC
        LIMIT $1
        """,
        limit,
    )

    result = []
    for row in rows:
        result.append({
            "timestamp_utc": row["timestamp_utc"].isoformat(),
            "token":            row["token"],
            "ex_buy":           row["ex_buy"],
            "ex_sell":          row["ex_sell"],
            "direction":        row["direction"],
            "gross_spread_pct": float(row["gross_spread_pct"]),
            "net_spread_pct":   float(row["net_spread_pct"]),
            "pair_fees_pct":    float(row["pair_fees_pct"]),
            "buy_ask":          float(row["buy_ask"]),
            "sell_bid":         float(row["sell_bid"]),
            "usdt_usdc_rate":   float(row["usdt_usdc_rate"]),
        })
    return result


async def run_analytics() -> dict:
    """
    Compute analytics from all stored opportunities using SQL.
    Returns dict compatible with the frontend analytics page.
    """
    pool = get_pool()
    if pool is None:
        return {"top_coins": [], "peak_hour": None, "peak_day": None, "total_opps": 0}

    async with pool.acquire() as conn:
        # Total count
        total = await conn.fetchval("SELECT COUNT(*) FROM opportunities")

        # Top 5 coins by max net spread
        top_rows = await conn.fetch("""
            SELECT token,
                   COUNT(*)            AS opp_count,
                   MAX(net_spread_pct) AS max_net
            FROM opportunities
            GROUP BY token
            ORDER BY max_net DESC
            LIMIT 5
        """)

        top_coins = []
        for r in top_rows:
            token = r["token"]
            # Best route for this token
            route_row = await conn.fetchrow("""
                SELECT ex_buy || '->' || ex_sell AS route, COUNT(*) AS cnt
                FROM opportunities
                WHERE token = $1
                GROUP BY route
                ORDER BY cnt DESC
                LIMIT 1
            """, token)
            top_coins.append({
                "token":      token,
                "count":      r["opp_count"],
                "best_route": route_row["route"] if route_row else None,
                "max_net":    round(float(r["max_net"]), 4),
            })

        # Peak hour (IST = UTC + 5:30)
        peak_hour_row = await conn.fetchrow("""
            SELECT TO_CHAR(
                       timestamp_utc AT TIME ZONE 'Asia/Kolkata',
                       'HH12:00 AM'
                   ) AS hour_label,
                   COUNT(*) AS cnt
            FROM opportunities
            GROUP BY hour_label
            ORDER BY cnt DESC
            LIMIT 1
        """)
        peak_hour = None
        if peak_hour_row:
            peak_hour = (peak_hour_row["hour_label"].strip(), peak_hour_row["cnt"])

        # Peak day of week (IST)
        peak_day_row = await conn.fetchrow("""
            SELECT TO_CHAR(
                       timestamp_utc AT TIME ZONE 'Asia/Kolkata',
                       'Day'
                   ) AS day_label,
                   COUNT(*) AS cnt
            FROM opportunities
            GROUP BY day_label
            ORDER BY cnt DESC
            LIMIT 1
        """)
        peak_day = None
        if peak_day_row:
            peak_day = (peak_day_row["day_label"].strip(), peak_day_row["cnt"])

    return {
        "top_coins":  top_coins,
        "peak_hour":  peak_hour,
        "peak_day":   peak_day,
        "total_opps": total,
    }


async def reset() -> None:
    """Truncate all opportunity data from TimescaleDB."""
    pool = get_pool()
    if pool is None:
        return
    await pool.execute("TRUNCATE TABLE opportunities")
    print("[db] Opportunities table truncated")

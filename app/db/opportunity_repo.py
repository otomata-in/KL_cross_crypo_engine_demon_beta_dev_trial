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


async def get_timeseries_data(token: str, interval: str = "5 minutes", limit: int = 100) -> List[dict]:
    """
    Fetch downsampled time-series data for a specific token using TimescaleDB time_bucket.
    """
    pool = get_pool()
    if pool is None:
        return []

    # Valid intervals: '1 minute', '5 minutes', '15 minutes', '1 hour'
    safe_interval = interval if interval in ['1 minute', '5 minutes', '15 minutes', '1 hour'] else '5 minutes'

    rows = await pool.fetch(
        f"""
        SELECT time_bucket('{safe_interval}', timestamp_utc) AS bucket,
               MAX(net_spread_pct) AS max_net,
               AVG(net_spread_pct) AS avg_net
        FROM opportunities
        WHERE token = $1
        GROUP BY bucket
        ORDER BY bucket DESC
        LIMIT $2
        """,
        token, limit
    )

    result = []
    for row in rows:
        result.append({
            "bucket": row["bucket"].isoformat(),
            "max_net": round(float(row["max_net"]), 4),
            "avg_net": round(float(row["avg_net"]), 4),
        })
    return result


async def get_consistency_metrics(limit: int = 10) -> List[dict]:
    """
    Find consistent spreads by calculating the duration between the first and last
    seen timestamp of a sustained spread opportunity.
    """
    pool = get_pool()
    if pool is None:
        return []

    # A simple consistency check: groups opportunities by token and route within 
    # a recent timeframe and finds routes that were sustained for more than X seconds.
    # We use a 10-minute lookback for "current" consistency.
    rows = await pool.fetch(
        """
        WITH recent_opps AS (
            SELECT token, ex_buy || '->' || ex_sell AS route,
                   timestamp_utc, net_spread_pct
            FROM opportunities
            WHERE timestamp_utc > NOW() - INTERVAL '30 minutes'
              AND net_spread_pct > 0
        ),
        grouped AS (
            SELECT token, route,
                   MIN(timestamp_utc) AS first_seen,
                   MAX(timestamp_utc) AS last_seen,
                   MAX(net_spread_pct) AS max_net,
                   COUNT(*) AS observations
            FROM recent_opps
            GROUP BY token, route
        )
        SELECT token, route,
               first_seen, last_seen,
               EXTRACT(EPOCH FROM (last_seen - first_seen)) AS duration_seconds,
               max_net, observations
        FROM grouped
        WHERE EXTRACT(EPOCH FROM (last_seen - first_seen)) > 2 -- At least 2 seconds duration
        ORDER BY duration_seconds DESC
        LIMIT $1
        """,
        limit
    )

    result = []
    for row in rows:
        result.append({
            "token": row["token"],
            "route": row["route"],
            "first_seen": row["first_seen"].isoformat(),
            "last_seen": row["last_seen"].isoformat(),
            "duration_seconds": float(row["duration_seconds"]),
            "max_net": round(float(row["max_net"]), 4),
            "observations": row["observations"],
        })
    return result
